import os
import re
import time
import logging
from functools import wraps
import hmac
import hashlib
from flask import Flask, request, jsonify, render_template, send_from_directory, session, redirect, url_for
from flask_cors import CORS
from models import db, Report, User, DeviceThreshold, Incident, Command
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, and_, event
from sqlalchemy.engine import Engine
from werkzeug.security import generate_password_hash, check_password_hash
import pytz

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Get project root directory
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Create Flask app
app = Flask(
    __name__,
    static_folder=os.path.join(BASE_DIR, "static"),
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_url_path="/static"
)

# --- Configuration from Environment ---
API_KEY = os.environ.get("COMMAND_CENTER_API_KEY", "")
DEBUG_MODE = os.environ.get("COMMAND_CENTER_DEBUG", "false").lower() == "true"
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "*").split(",")

# Enable CORS with configurable origins
CORS(app, origins=ALLOWED_ORIGINS)

# Database configuration
DATABASE_PATH = os.environ.get("DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'monitoring.db')}")
if DATABASE_PATH.startswith("postgres://"):
    DATABASE_PATH = DATABASE_PATH.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_PATH
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True, "pool_recycle": 300}
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.secret_key = os.environ.get("SESSION_SECRET", "command_center_session_secure_secret_key_123")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)

# Initialize database
db.init_app(app)

# SQLite Concurrency Tuning: WAL mode, Normal sync, busy timeout
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    try:
        if type(dbapi_connection).__module__ == 'sqlite3':
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()
    except Exception as e:
        logger.error(f"Error setting SQLite WAL mode: {e}")

logger.info("=" * 60)
logger.info("SYSTEM STATUS:")
logger.info(f"Database: {DATABASE_PATH}")
logger.info(f"Debug Mode: {DEBUG_MODE}")
logger.info(f"API Key Set: {bool(API_KEY)}")
logger.info("=" * 60)

# ============================================================
# Security Helpers
# ============================================================

_rate_limit_store = {}

def rate_limit(max_requests=10, window=10):
    """Simple in-memory rate limiter decorator"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            import random
            client_ip = request.remote_addr or "unknown"
            
            # Prune expired keys occasionally (1% chance) to avoid memory leaks
            if random.random() < 0.01:
                now_check = time.time()
                expired_keys = []
                for k, v in list(_rate_limit_store.items()):
                    active = [t for t in v if now_check - t < 60]
                    if not active:
                        expired_keys.append(k)
                    else:
                        _rate_limit_store[k] = active
                for k in expired_keys:
                    _rate_limit_store.pop(k, None)
            
            # Identify client by agent_id if possible (avoiding IP collisions for different agents)
            agent_id = None
            if request.is_json:
                try:
                    data = request.get_json(silent=True)
                    if data and isinstance(data, dict):
                        agent_id = data.get("agent_id")
                except Exception:
                    pass
            
            key_identifier = agent_id if (agent_id and isinstance(agent_id, str)) else client_ip
            key = f"{f.__name__}:{key_identifier}"
            now = time.time()
            if key in _rate_limit_store:
                _rate_limit_store[key] = [t for t in _rate_limit_store[key] if now - t < window]
            else:
                _rate_limit_store[key] = []
            if len(_rate_limit_store[key]) >= max_requests:
                return jsonify({"status": "error", "message": "Rate limit exceeded. Try again later."}), 429
            _rate_limit_store[key].append(now)
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def require_api_key(f):
    """Decorator to require API key or HMAC signature authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not API_KEY:
            return f(*args, **kwargs)
            
        # Verify HMAC signature first
        signature = request.headers.get("X-Signature")
        if signature:
            raw_data = request.get_data()
            expected_signature = hmac.new(
                API_KEY.encode('utf-8'),
                raw_data,
                hashlib.sha256
            ).hexdigest()
            if hmac.compare_digest(signature, expected_signature):
                return f(*args, **kwargs)
                
        # Direct API Key fallback
        provided_key = request.headers.get("X-API-Key") or request.args.get("api_key")
        if provided_key != API_KEY:
            return jsonify({"status": "error", "message": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated_function

def login_required(f):
    """Decorator to require user session authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            if request.path.startswith("/api/"):
                return jsonify({"status": "error", "message": "Unauthorized"}), 401
            return redirect(url_for("login_view"))
        return f(*args, **kwargs)
    return decorated_function

AGENT_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_\-\.]{1,100}$')

def validate_agent_id(agent_id):
    """Validate agent_id format — alphanumeric, dashes, underscores, dots only"""
    if not agent_id or not isinstance(agent_id, str):
        return False
    return bool(AGENT_ID_PATTERN.match(agent_id))

def validate_metric(value):
    """Validate metric value is a number between 0 and 100"""
    try:
        v = float(value)
        return 0 <= v <= 100
    except (TypeError, ValueError):
        return False

def sanitize_error(e):
    """Return safe error message without leaking internals"""
    logger.error(f"Internal error: {e}")
    return "An internal error occurred"

# Security headers middleware
@app.after_request
def add_security_headers(response):
    """Add security headers to every response"""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://fonts.googleapis.com; "
        "font-src 'self' https://cdnjs.cloudflare.com https://fonts.gstatic.com; "
        "img-src 'self' data: https://img.shields.io; "
        "connect-src 'self'"
    )
    return response

# ============================================================
# Helper Functions
# ============================================================

def utc_to_ist(utc_dt):
    """Convert UTC datetime to Indian Standard Time (IST)"""
    if utc_dt:
        utc_dt = utc_dt.replace(tzinfo=timezone.utc)
        ist = pytz.timezone('Asia/Kolkata')
        return utc_dt.astimezone(ist)
    return None

def to_iso_with_timezone(dt):
    """Convert datetime to ISO format with timezone"""
    if dt:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    return None

def cleanup_old_reports(max_age_days=30):
    """Remove reports older than max_age_days"""
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        deleted = Report.query.filter(Report.timestamp < cutoff).delete()
        db.session.commit()
        if deleted > 0:
            logger.info(f"Cleanup: Removed {deleted} reports older than {max_age_days} days")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Cleanup error: {e}")

# ============================================================
# Routes
# ============================================================

# Static file serving
@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory(app.static_folder, filename)

# Dashboard route (protected by session login)
@app.route("/")
@login_required
def dashboard():
    server_url = request.url_root.rstrip('/')
    return render_template("dashboard.html", server_url=server_url)

# Login view
@app.route("/login", methods=["GET"])
def login_view():
    if session.get("logged_in"):
        return redirect(url_for("dashboard"))
    return render_template("login.html")

# Auth endpoints
@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    try:
        data = request.get_json(silent=True)
        if not data or "username" not in data or "password" not in data:
            return jsonify({"status": "error", "message": "Username and password required"}), 400
            
        user = User.query.filter_by(username=data["username"]).first()
        if user and check_password_hash(user.password_hash, data["password"]):
            session["logged_in"] = True
            session["username"] = user.username
            if data.get("remember"):
                session.permanent = True
            else:
                session.permanent = False
            return jsonify({"status": "ok", "message": "Login successful"})
            
        return jsonify({"status": "error", "message": "Invalid credentials"}), 401
    except Exception as e:
        return jsonify({"status": "error", "message": sanitize_error(e)}), 500

@app.route("/api/auth/register", methods=["POST"])
def auth_register():
    try:
        data = request.get_json(silent=True)
        if not data or "username" not in data or "password" not in data:
            return jsonify({"status": "error", "message": "Username and password required"}), 400
            
        username = data["username"].strip()
        password = data["password"]
        
        if not username or not password:
            return jsonify({"status": "error", "message": "Username and password cannot be empty"}), 400
            
        if len(username) < 3 or len(username) > 50:
            return jsonify({"status": "error", "message": "Username must be between 3 and 50 characters"}), 400
            
        if not re.match(r"^[a-zA-Z0-9_-]+$", username):
            return jsonify({"status": "error", "message": "Username can only contain letters, numbers, underscores, and dashes"}), 400
            
        if len(password) < 6:
            return jsonify({"status": "error", "message": "Password must be at least 6 characters"}), 400
            
        # Check if user already exists
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            return jsonify({"status": "error", "message": "Username already exists"}), 400
            
        # Create user
        new_user = User(
            username=username,
            password_hash=generate_password_hash(password)
        )
        db.session.add(new_user)
        db.session.commit()
        
        # Log user in
        session["logged_in"] = True
        session["username"] = username
        
        logger.info(f"User registered successfully: {username}")
        return jsonify({"status": "ok", "message": "Registration successful"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": sanitize_error(e)}), 500

@app.route("/api/auth/logout", methods=["POST"])
def auth_logout():
    session.pop("logged_in", None)
    session.pop("username", None)
    return jsonify({"status": "ok", "message": "Logged out successfully"})

@app.route("/api/auth/status")
def auth_status():
    if session.get("logged_in"):
        return jsonify({
            "authenticated": True,
            "username": session.get("username")
        })
    return jsonify({
        "authenticated": False
    })

# Health check endpoint
@app.route("/health")
def health_check():
    """Health check for container orchestration"""
    return jsonify({"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()})

# Test endpoint
@app.route("/test")
def test_connection():
    """Test endpoint to verify server is working"""
    return jsonify({
        "status": "ok",
        "message": "Server is running",
        "timestamp": datetime.now(timezone.utc).isoformat()
    })

# API: Receive report from agent
@app.route("/api/report", methods=["POST"])
@require_api_key
@rate_limit(max_requests=10, window=10)
def receive_report():
    try:
        data = request.get_json(silent=True)
        if not data or not isinstance(data, dict):
            return jsonify({"status": "error", "message": "Invalid JSON body"}), 400

        # Validate required fields
        required_fields = ["agent_id", "cpu", "memory", "disk"]
        if not all(field in data for field in required_fields):
            return jsonify({"status": "error", "message": "Missing required fields"}), 400

        # Validate agent_id format (CRIT-2 / HIGH-1 fix)
        if not validate_agent_id(data["agent_id"]):
            return jsonify({"status": "error", "message": "Invalid agent_id. Use alphanumeric, dashes, underscores, dots. Max 100 chars."}), 400

        # Validate metric ranges (HIGH-2 fix)
        for field in ["cpu", "memory", "disk"]:
            if not validate_metric(data[field]):
                return jsonify({"status": "error", "message": f"Invalid {field} value. Must be 0-100."}), 400

        # Create and save report
        report = Report(
            agent_id=data["agent_id"],
            cpu=round(float(data["cpu"]), 2),
            memory=round(float(data["memory"]), 2),
            disk=round(float(data["disk"]), 2)
        )

        db.session.add(report)

        # Check connection recovery
        last_conn_inc = (
            Incident.query
            .filter_by(agent_id=report.agent_id, metric="connection")
            .order_by(Incident.timestamp.desc())
            .first()
        )
        if last_conn_inc and last_conn_inc.status == "critical":
            conn_resolved = Incident(
                agent_id=report.agent_id,
                metric="connection",
                status="resolved",
                value=None
            )
            db.session.add(conn_resolved)

        # Evaluate threshold alerts
        thresh = DeviceThreshold.query.filter_by(agent_id=report.agent_id).first()
        metrics_list = [
            ("cpu", report.cpu, getattr(thresh, "cpu_warning", 60.0) if thresh else 60.0, getattr(thresh, "cpu_critical", 80.0) if thresh else 80.0),
            ("memory", report.memory, getattr(thresh, "memory_warning", 60.0) if thresh else 60.0, getattr(thresh, "memory_critical", 80.0) if thresh else 80.0),
            ("disk", report.disk, getattr(thresh, "disk_warning", 60.0) if thresh else 60.0, getattr(thresh, "disk_critical", 80.0) if thresh else 80.0)
        ]
        
        for m_name, m_val, warning_limit, critical_limit in metrics_list:
            if m_val > critical_limit:
                current_status = "critical"
            elif m_val > warning_limit:
                current_status = "warning"
            else:
                current_status = "resolved"
                
            last_inc = (
                Incident.query
                .filter_by(agent_id=report.agent_id, metric=m_name)
                .order_by(Incident.timestamp.desc())
                .first()
            )
            
            last_status = last_inc.status if last_inc else "resolved"
            
            if current_status != last_status:
                incident = Incident(
                    agent_id=report.agent_id,
                    metric=m_name,
                    value=m_val,
                    status=current_status
                )
                db.session.add(incident)

        db.session.commit()

        # Check for any pending command for this agent (SSM-like polling)
        pending_command = (
            Command.query
            .filter_by(agent_id=report.agent_id, status="pending")
            .order_by(Command.created_at.asc())
            .first()
        )
        command_data = None
        if pending_command:
            pending_command.status = "running"
            db.session.commit()
            command_data = {
                "id": pending_command.id,
                "action": pending_command.action,
                "payload": pending_command.payload
            }

        logger.info(f"Report saved: {report.agent_id} at {report.timestamp}")
        return jsonify({
            "status": "ok",
            "message": "Report received",
            "timestamp": to_iso_with_timezone(report.timestamp),
            "command": command_data
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": sanitize_error(e)}), 500

# API: Create command to execute on an agent
@app.route("/api/command/create", methods=["POST"])
@login_required
def create_command():
    try:
        data = request.get_json(silent=True)
        if not data or "agent_id" not in data or "action" not in data:
            return jsonify({"status": "error", "message": "agent_id and action are required"}), 400
            
        # Validate action
        valid_actions = ["list_processes", "kill_process", "run_shell"]
        if data["action"] not in valid_actions:
            return jsonify({"status": "error", "message": f"Invalid action. Choose from {valid_actions}"}), 400
            
        # Create and queue command
        cmd = Command(
            agent_id=data["agent_id"],
            action=data["action"],
            payload=data.get("payload", ""),
            status="pending"
        )
        db.session.add(cmd)
        db.session.commit()
        
        logger.info(f"Command queued: {cmd.action} for {cmd.agent_id}")
        return jsonify({
            "status": "ok",
            "message": "Command queued successfully",
            "command_id": cmd.id
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": sanitize_error(e)}), 500

# API: Post execution result from agent
@app.route("/api/command/result", methods=["POST"])
@require_api_key
def post_command_result():
    try:
        data = request.get_json(silent=True)
        if not data or "command_id" not in data or "status" not in data:
            return jsonify({"status": "error", "message": "command_id and status are required"}), 400
            
        cmd = Command.query.get(data["command_id"])
        if not cmd:
            return jsonify({"status": "error", "message": "Command not found"}), 404
            
        cmd.status = data["status"] # "completed" or "failed"
        cmd.output = data.get("output", "")
        cmd.completed_at = datetime.now(timezone.utc)
        db.session.commit()
        
        logger.info(f"Command finished: {cmd.id} for {cmd.agent_id} with status {cmd.status}")
        return jsonify({"status": "ok", "message": "Result updated"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": sanitize_error(e)}), 500

# API: Poll command status
@app.route("/api/command/<int:command_id>/status")
@login_required
def get_command_status(command_id):
    try:
        cmd = Command.query.get(command_id)
        if not cmd:
            return jsonify({"status": "error", "message": "Command not found"}), 404
            
        return jsonify({
            "id": cmd.id,
            "agent_id": cmd.agent_id,
            "action": cmd.action,
            "status": cmd.status,
            "output": cmd.output,
            "created_at": to_iso_with_timezone(cmd.created_at),
            "completed_at": to_iso_with_timezone(cmd.completed_at)
        })
    except Exception as e:
        return jsonify({"status": "error", "message": sanitize_error(e)}), 500

# API: Get live agents
@app.route("/api/agents")
@login_required
def get_agents():
    try:
        # Agents active in last 60 seconds
        threshold = datetime.now(timezone.utc) - timedelta(seconds=60)

        # Get latest report for each agent in the last 60 seconds (optimizes query scale)
        latest_report_subquery = db.session.query(
            Report.agent_id,
            func.max(Report.timestamp).label("latest_time")
        ).filter(Report.timestamp >= threshold).group_by(Report.agent_id).subquery()

        # Get agents with recent reports
        live_agents = db.session.query(Report).join(
            latest_report_subquery,
            and_(
                Report.agent_id == latest_report_subquery.c.agent_id,
                Report.timestamp == latest_report_subquery.c.latest_time
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
        logger.error(f"Error getting agents: {e}")
        return jsonify([])

# API: Get report history for agent
@app.route("/api/reports/history/<string:agent_id>")
@login_required
def report_history(agent_id):
    try:
        if not validate_agent_id(agent_id):
            return jsonify([])

        range_value = request.args.get("range", "30")
        try:
            range_value = int(range_value)
            range_value = max(1, min(range_value, 1440))  # Cap at 24 hours
        except (ValueError, TypeError):
            range_value = 30

        time_threshold = datetime.now(timezone.utc) - timedelta(minutes=range_value)

        # Get reports with a limit to prevent unbounded results (SCALE-3 fix)
        reports = (
            Report.query
            .filter(Report.agent_id == agent_id)
            .filter(Report.timestamp >= time_threshold)
            .order_by(Report.timestamp.asc())
            .limit(500)
            .all()
        )

        # Prepare response with IST time (oldest first for chart)
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
        logger.error(f"Error getting history for {agent_id}: {e}")
        return jsonify([])

# API: Get latest data for specific agent
@app.route("/api/agent/<string:agent_id>/latest")
@login_required
def get_agent_latest(agent_id):
    try:
        if not validate_agent_id(agent_id):
            return jsonify({"error": "Invalid agent_id"}), 400

        latest_report = (
            Report.query
            .filter_by(agent_id=agent_id)
            .order_by(Report.timestamp.desc())
            .first()
        )

        if not latest_report:
            return jsonify({"error": "No data found"}), 404

        ist_time = utc_to_ist(latest_report.timestamp)
        return jsonify({
            "agent_id": latest_report.agent_id,
            "cpu": round(latest_report.cpu, 2),
            "memory": round(latest_report.memory, 2),
            "disk": round(latest_report.disk, 2),
            "timestamp": to_iso_with_timezone(ist_time)
        })

    except Exception as e:
        return jsonify({"error": sanitize_error(e)}), 500

# API: Get threshold limits for a device
@app.route("/api/thresholds/<string:agent_id>", methods=["GET"])
@login_required
def get_device_thresholds(agent_id):
    try:
        if not validate_agent_id(agent_id):
            return jsonify({"status": "error", "message": "Invalid agent_id"}), 400
            
        thresh = DeviceThreshold.query.filter_by(agent_id=agent_id).first()
        if not thresh:
            return jsonify({
                "agent_id": agent_id,
                "cpu_warning": 60.0,
                "cpu_critical": 80.0,
                "memory_warning": 60.0,
                "memory_critical": 80.0,
                "disk_warning": 60.0,
                "disk_critical": 80.0
            })
            
        return jsonify({
            "agent_id": thresh.agent_id,
            "cpu_warning": thresh.cpu_warning,
            "cpu_critical": thresh.cpu_critical,
            "memory_warning": thresh.memory_warning,
            "memory_critical": thresh.memory_critical,
            "disk_warning": thresh.disk_warning,
            "disk_critical": thresh.disk_critical
        })
    except Exception as e:
        return jsonify({"status": "error", "message": sanitize_error(e)}), 500

# API: Save threshold limits for a device
@app.route("/api/thresholds/<string:agent_id>", methods=["POST"])
@login_required
def save_device_thresholds(agent_id):
    try:
        if not validate_agent_id(agent_id):
            return jsonify({"status": "error", "message": "Invalid agent_id"}), 400
            
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"status": "error", "message": "Invalid JSON"}), 400
            
        thresh = DeviceThreshold.query.filter_by(agent_id=agent_id).first()
        if not thresh:
            thresh = DeviceThreshold(agent_id=agent_id)
            db.session.add(thresh)
            
        thresh.cpu_warning = float(data.get("cpu_warning", 60.0))
        thresh.cpu_critical = float(data.get("cpu_critical", 80.0))
        thresh.memory_warning = float(data.get("memory_warning", 60.0))
        thresh.memory_critical = float(data.get("memory_critical", 80.0))
        thresh.disk_warning = float(data.get("disk_warning", 60.0))
        thresh.disk_critical = float(data.get("disk_critical", 80.0))
        
        db.session.commit()
        return jsonify({"status": "ok", "message": "Thresholds saved successfully"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": sanitize_error(e)}), 500

# API: Get incident timeline logs for a device
@app.route("/api/incidents/<string:agent_id>", methods=["GET"])
@login_required
def get_device_incidents(agent_id):
    try:
        if not validate_agent_id(agent_id):
            return jsonify([])
            
        incidents = (
            Incident.query
            .filter_by(agent_id=agent_id)
            .order_by(Incident.timestamp.desc())
            .limit(100)
            .all()
        )
        
        inc_data = []
        for inc in incidents:
            ist_time = utc_to_ist(inc.timestamp)
            inc_data.append({
                "id": inc.id,
                "agent_id": inc.agent_id,
                "timestamp": to_iso_with_timezone(ist_time),
                "metric": inc.metric,
                "value": inc.value,
                "status": inc.status
            })
            
        return jsonify(inc_data)
    except Exception as e:
        logger.error(f"Error getting incidents for {agent_id}: {e}")
        return jsonify([])

# --- Debug endpoints: ONLY available when COMMAND_CENTER_DEBUG=true (CRIT-1 fix) ---
if DEBUG_MODE:
    @app.route("/api/debug/clear", methods=["POST"])
    def clear_database():
        """Clear all reports from database (DEBUG ONLY)"""
        try:
            Report.query.delete()
            db.session.commit()
            return jsonify({"status": "ok", "message": "Database cleared"})
        except Exception as e:
            return jsonify({"status": "error", "message": sanitize_error(e)}), 500

    @app.route("/api/debug/add-sample", methods=["POST"])
    def add_sample_data():
        """Add sample data for testing (DEBUG ONLY)"""
        try:
            import random
            agent_id = "sample_server"
            now = datetime.now(timezone.utc)
            Report.query.filter_by(agent_id=agent_id).delete()
            for i in range(50):
                report = Report(
                    agent_id=agent_id,
                    cpu=round(random.uniform(20, 90), 2),
                    memory=round(random.uniform(30, 85), 2),
                    disk=round(random.uniform(40, 95), 2),
                    timestamp=now - timedelta(seconds=(49 - i) * 10)
                )
                db.session.add(report)
            db.session.commit()
            return jsonify({"status": "ok", "message": f"Added 50 sample reports for {agent_id}"})
        except Exception as e:
            return jsonify({"status": "error", "message": sanitize_error(e)}), 500

    logger.warning("DEBUG MODE ENABLED — debug endpoints are accessible!")

# Download agent file
@app.route("/download/agent")
@login_required
def download_agent():
    agent_path = os.path.dirname(BASE_DIR)  # project root
    return send_from_directory(
        agent_path,
        "agent.py",
        as_attachment=True
    )

@app.route("/api/server/info")
@login_required
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
        return jsonify({"status": "error", "message": sanitize_error(e)}), 500

# Initialize database on startup
with app.app_context():
    db.create_all()
    logger.info("Database initialized successfully")
    cleanup_old_reports()
    
    # Auto-create default admin user if database is empty
    if User.query.first() is None:
        default_pwd = os.environ.get("ADMIN_PASSWORD", "admin123")
        admin = User(
            username="admin",
            password_hash=generate_password_hash(default_pwd)
        )
        db.session.add(admin)
        db.session.commit()
        logger.info(f"Default admin user created with password: {default_pwd}")

    # Start periodic background cleanup thread (hourly)
    import threading
    def run_periodic_cleanup():
        while True:
            time.sleep(3600)  # Every hour
            try:
                with app.app_context():
                    cleanup_old_reports(max_age_days=30)
            except Exception as e:
                logger.error(f"Background cleanup error: {e}")
                
    cleanup_thread = threading.Thread(target=run_periodic_cleanup, daemon=True)
    cleanup_thread.start()

    # Start periodic background offline heartbeat check thread (every 10 seconds)
    def run_heartbeat_scanner():
        while True:
            time.sleep(10)  # Check every 10 seconds
            try:
                with app.app_context():
                    # Query all agents that reported in the last 1 hour
                    hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
                    latest_reports = (
                        db.session.query(
                            Report.agent_id,
                            func.max(Report.timestamp).label("max_ts")
                        )
                        .filter(Report.timestamp >= hour_ago)
                        .group_by(Report.agent_id)
                        .all()
                    )
                    
                    now = datetime.now(timezone.utc)
                    for agent_id, max_ts in latest_reports:
                        if max_ts.tzinfo is None:
                            max_ts = max_ts.replace(tzinfo=timezone.utc)
                            
                        # If silence > 35 seconds, mark offline
                        if (now - max_ts).total_seconds() > 35:
                            last_conn = (
                                Incident.query
                                .filter_by(agent_id=agent_id, metric="connection")
                                .order_by(Incident.timestamp.desc())
                                .first()
                            )
                            if not last_conn or last_conn.status == "resolved":
                                # Mark offline
                                offline_incident = Incident(
                                    agent_id=agent_id,
                                    metric="connection",
                                    status="critical",
                                    value=None
                                )
                                db.session.add(offline_incident)
                                db.session.commit()
                                logger.warning(f"Device {agent_id} detected OFFLINE (last heartbeat: {max_ts})")
            except Exception as e:
                logger.error(f"Heartbeat scanner error: {e}")
                
    heartbeat_thread = threading.Thread(target=run_heartbeat_scanner, daemon=True)
    heartbeat_thread.start()

# Main entry point
if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("MONITORING SERVER STARTING...")
    logger.info("Dashboard: http://127.0.0.1:5000")
    logger.info("API Status: http://127.0.0.1:5000/api/server/info")
    logger.info("Press Ctrl+C to stop")
    logger.info("=" * 60)

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=DEBUG_MODE, threaded=True)