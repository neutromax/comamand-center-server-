from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone

db = SQLAlchemy()

class Report(db.Model):
    """Database model for agent reports"""
    __tablename__ = 'reports'
    
    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.String(100), nullable=False, index=True)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    
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