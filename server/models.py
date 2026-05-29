from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone

db = SQLAlchemy()

class User(db.Model):
    """Database model for dashboard users"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    
    def __repr__(self):
        return f"<User {self.username}>"

class Report(db.Model):
    """Database model for agent reports"""
    __tablename__ = 'reports'
    
    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.String(100), nullable=False, index=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    
    __table_args__ = (
        db.Index('idx_agent_timestamp', 'agent_id', 'timestamp'),
    )
    
    # Metrics
    cpu = db.Column(db.Float, nullable=False)      # CPU usage percentage
    memory = db.Column(db.Float, nullable=False)   # Memory usage percentage
    disk = db.Column(db.Float, nullable=False)     # Disk usage percentage
    
    def __repr__(self):
        return f"<Report {self.agent_id} - CPU:{self.cpu}% at {self.timestamp}>"
    
    def to_dict(self):
        """Convert report to dictionary"""
        return {
            'id': self.id,
            'agent_id': self.agent_id,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'cpu': self.cpu,
            'memory': self.memory,
            'disk': self.disk
        }

class DeviceThreshold(db.Model):
    """Database model for per-device alert thresholds"""
    __tablename__ = 'device_thresholds'
    
    agent_id = db.Column(db.String(100), primary_key=True)
    
    cpu_warning = db.Column(db.Float, nullable=False, default=60.0)
    cpu_critical = db.Column(db.Float, nullable=False, default=80.0)
    
    memory_warning = db.Column(db.Float, nullable=False, default=60.0)
    memory_critical = db.Column(db.Float, nullable=False, default=80.0)
    
    disk_warning = db.Column(db.Float, nullable=False, default=60.0)
    disk_critical = db.Column(db.Float, nullable=False, default=80.0)
    
    def __repr__(self):
        return f"<DeviceThreshold {self.agent_id}>"

class Incident(db.Model):
    """Database model for tracking incident alerts timeline"""
    __tablename__ = 'incidents'
    
    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.String(100), nullable=False, index=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    metric = db.Column(db.String(50), nullable=False) # "cpu", "memory", "disk", or "connection"
    value = db.Column(db.Float, nullable=True)
    status = db.Column(db.String(50), nullable=False) # "warning", "critical", or "resolved"
    
    def __repr__(self):
        return f"<Incident {self.agent_id} {self.metric} {self.status} at {self.timestamp}>"

class Command(db.Model):
    """Database model for queuing device operations"""
    __tablename__ = 'commands'
    
    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.String(100), nullable=False, index=True)
    action = db.Column(db.String(50), nullable=False) # "list_processes", "kill_process", "run_shell"
    payload = db.Column(db.String(255), nullable=True) # e.g. command arguments or pid
    status = db.Column(db.String(50), nullable=False, default="pending") # "pending", "running", "completed", "failed"
    output = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = db.Column(db.DateTime, nullable=True)
    
    def __repr__(self):
        return f"<Command {self.agent_id} {self.action} {self.status}>"