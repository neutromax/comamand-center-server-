import os
from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
from models import db, Report
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, and_
import pytz

# Get project root directory
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Create Flask app
app = Flask(
    __name__,
    static_folder=os.path.join(BASE_DIR, "static"),
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_url_path="/static"
)

# Enable CORS
CORS(app)

# Database configuration
DATABASE_PATH = os.path.join(BASE_DIR, "monitoring.db")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DATABASE_PATH}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Initialize database
db.init_app(app)

print("=" * 60)
print("SYSTEM STATUS:")
print(f"Database: {DATABASE_PATH}")
print(f"Static Folder: {app.static_folder}")
print(f"Template Folder: {app.template_folder}")
print("=" * 60)

# Helper function to convert UTC to IST
def utc_to_ist(utc_dt):
    """Convert UTC datetime to Indian Standard Time (IST)"""
    if utc_dt:
        utc_dt = utc_dt.replace(tzinfo=timezone.utc)
        ist = pytz.timezone('Asia/Kolkata')
        return utc_dt.astimezone(ist)
    return None

# Helper function for ISO format with timezone
def to_iso_with_timezone(dt):
    """Convert datetime to ISO format with timezone"""
    if dt:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    return None

# Static file serving
@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory(app.static_folder, filename)

# Dashboard route
@app.route("/")
def dashboard():
    return render_template("dashboard.html")

# API: Receive report from agent
@app.route("/api/report", methods=["POST"])
def receive_report():
    try:
        data = request.json
        
        # Validate required fields
        required_fields = ["agent_id", "cpu", "memory", "disk"]
        if not all(field in data for field in required_fields):
            return jsonify({"status": "error", "message": "Missing required fields"}), 400
        
        # Create and save report
        report = Report(
            agent_id=data["agent_id"],
            cpu=float(data["cpu"]),
            memory=float(data["memory"]),
            disk=float(data["disk"])
        )
        
        db.session.add(report)
        db.session.commit()
        
        print(f"✓ Report saved: {report.agent_id} at {report.timestamp}")
        return jsonify({
            "status": "ok",
            "message": "Report received",
            "timestamp": to_iso_with_timezone(report.timestamp)
        })
        
    except Exception as e:
        print(f"✗ Error saving report: {e}")
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

# API: Get live agents
@app.route("/api/agents")
def get_agents():
    try:
        # Agents active in last 60 seconds
        threshold = datetime.now(timezone.utc) - timedelta(seconds=60)
        
        # Get latest report for each agent
        latest_report_subquery = db.session.query(
            Report.agent_id,
            func.max(Report.timestamp).label("latest_time")
        ).group_by(Report.agent_id).subquery()

        # Get agents with recent reports
        live_agents = db.session.query(Report).join(
            latest_report_subquery,
            and_(
                Report.agent_id == latest_report_subquery.c.agent_id,
                Report.timestamp == latest_report_subquery.c.latest_time,
                Report.timestamp >= threshold
            )
        ).order_by(Report.timestamp.desc()).all()

        # Prepare response with IST time
        agents_data = []
        for agent in live_agents:
            ist_time = utc_to_ist(agent.timestamp)
            agents_data.append({
                "agent_id": agent.agent_id,
                "cpu": round(agent.cpu, 2),
                "memory": round(agent.memory, 2),
                "disk": round(agent.disk, 2),
                "timestamp": to_iso_with_timezone(ist_time),
                "status": "online"
            })

        return jsonify(agents_data)
        
    except Exception as e:
        print(f"Error getting agents: {e}")
        return jsonify([])

# API: Get report history for agent
@app.route("/api/reports/history/<string:agent_id>")
def report_history(agent_id):
    try:
        # Get last 20 reports for the agent
        reports = (
            Report.query
            .filter_by(agent_id=agent_id)
            .order_by(Report.timestamp.desc())
            .limit(20)
            .all()
        )
        
        # Prepare response with IST time (oldest first for chart)
        reports.reverse()
        history_data = []
        
        for report in reports:
            ist_time = utc_to_ist(report.timestamp)
            history_data.append({
                "cpu_percent": round(report.cpu, 2),
                "memory_percent": round(report.memory, 2),
                "disk_percent": round(report.disk, 2),
                "timestamp": to_iso_with_timezone(ist_time)
            })

        return jsonify(history_data)
        
    except Exception as e:
        print(f"Error getting history for {agent_id}: {e}")
        return jsonify([])

# API: Clear database (for testing)
@app.route("/api/debug/clear", methods=["POST"])
def clear_database():
    """Clear all reports from database"""
    try:
        Report.query.delete()
        db.session.commit()
        return jsonify({"status": "ok", "message": "Database cleared"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# API: Add sample data (for testing)
@app.route("/api/debug/add-sample", methods=["POST"])
def add_sample_data():
    """Add sample data for testing"""
    try:
        import random
        from datetime import datetime, timezone
        
        agent_id = "sample_server"
        now = datetime.now(timezone.utc)
        
        # Clear existing sample data
        Report.query.filter_by(agent_id=agent_id).delete()
        
        # Add 20 sample reports
        for i in range(20):
            report = Report(
                agent_id=agent_id,
                cpu=random.uniform(20, 80),
                memory=random.uniform(30, 70),
                disk=random.uniform(40, 90),
                timestamp=now - timedelta(minutes=(19 - i) * 5)  # 95 minutes span
            )
            db.session.add(report)
        
        db.session.commit()
        return jsonify({
            "status": "ok", 
            "message": f"Added 20 sample reports for {agent_id}"
        })
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# API: Get server info
@app.route("/api/server/info")
def server_info():
    """Get server information"""
    try:
        total_reports = Report.query.count()
        unique_agents = db.session.query(Report.agent_id).distinct().count()
        
        return jsonify({
            "status": "online",
            "server_time_ist": to_iso_with_timezone(
                datetime.now(pytz.timezone('Asia/Kolkata'))
            ),
            "database": {
                "total_reports": total_reports,
                "unique_agents": unique_agents
            }
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# Initialize database on startup
with app.app_context():
    db.create_all()
    print("✓ Database initialized successfully")

# Main entry point
if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("MONITORING SERVER STARTING...")
    print("Dashboard: http://127.0.0.1:5000")
    print("API Status: http://127.0.0.1:5000/api/server/info")
    print("Press Ctrl+C to stop")
    print("=" * 60 + "\n")
    
    app.run(host="0.0.0.0", port=5000, debug=True)