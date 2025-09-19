# models.py
from flask_sqlalchemy import SQLAlchemy
import datetime

db = SQLAlchemy()

class AgentStatus(db.Model):
    agent_id = db.Column(db.String(80), primary_key=True)
    cpu_percent = db.Column(db.Float, nullable=False)
    memory_percent = db.Column(db.Float, nullable=False)
    disk_percent = db.Column(db.Float, nullable=False)
    boot_time = db.Column(db.String(80), nullable=False)
    last_seen = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class Alert(db.Model):
    alert_id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.String(80), nullable=False)
    issue_description = db.Column(db.String(200), nullable=False)
    metric_data = db.Column(db.String(200), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)