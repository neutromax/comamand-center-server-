# app.py
from flask import Flask, request, jsonify, render_template, send_from_directory
from models import db
import database_handler
from file_transfer_handler import file_transfer_bp
import os


app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///monitoring_data.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['COMMAND_QUEUE'] = {}
db.init_app(app)

app.register_blueprint(file_transfer_bp, url_prefix='/api')

@app.route("/")
def dashboard():
    return render_template('dashboard.html')

@app.route("/api/agents")
def get_agents():
    from models import AgentStatus
    agents = AgentStatus.query.order_by(AgentStatus.last_seen.desc()).all()
    return jsonify([{
        'agent_id': a.agent_id, 'cpu_percent': a.cpu_percent,
        'memory_percent': a.memory_percent, 'disk_percent': a.disk_percent,
        'boot_time': a.boot_time, 'last_seen': a.last_seen.isoformat()
    } for a in agents])

@app.route("/api/alerts")
def get_alerts():
    from models import Alert
    alerts = Alert.query.order_by(Alert.timestamp.desc()).all()
    return jsonify([{
        'agent_id': a.agent_id, 'issue_description': a.issue_description,
        'metric_data': a.metric_data, 'timestamp': a.timestamp.isoformat()
    } for a in alerts])

@app.route("/api/report", methods=['POST'])
def receive_report():
    success = database_handler.save_report(request.json)
    if success:
        return jsonify({"status": "success", "message": "Report saved."}), 200
    return jsonify({"status": "error", "message": "Failed to save report."}), 500

@app.route('/api/commands/<string:agent_id>', methods=['GET'])
def get_commands(agent_id):
    command_queue = app.config['COMMAND_QUEUE']
    if agent_id in command_queue and command_queue[agent_id]:
        command = command_queue[agent_id].pop(0)
        return jsonify(command)
    return jsonify({})

@app.route('/api/download/host/<string:filename>', methods=['GET'])
def download_from_host(filename):
    host_uploads_path = os.path.join(app.config['UPLOAD_FOLDER'], 'host_uploads')
    return send_from_directory(host_uploads_path, filename, as_attachment=True)

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)