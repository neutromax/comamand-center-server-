# database_handler.py
from models import db, AgentStatus, Alert

def save_report(data):
    try:
        agent_id = data.get('agent_id')
        agent = AgentStatus.query.get(agent_id)

        if float(data.get('cpu_percent', 0)) > 90.0:
            handle_alert(agent_id, "High CPU Usage", f"CPU at {data.get('cpu_percent')}%")

        if agent:
            agent.cpu_percent = data.get('cpu_percent')
            agent.memory_percent = data.get('memory_percent')
            agent.disk_percent = data.get('disk_percent')
            agent.boot_time = data.get('boot_time')
        else:
            if AgentStatus.query.count() >= 10:
                oldest = AgentStatus.query.order_by(AgentStatus.last_seen).first()
                db.session.delete(oldest)
            new_agent = AgentStatus(**data)
            db.session.add(new_agent)
        
        db.session.commit()
        return True
    except Exception as e:
        print(f"Database Error: {e}")
        db.session.rollback()
        return False

def handle_alert(agent_id, issue, metrics):
    if Alert.query.count() >= 10:
        oldest_alert = Alert.query.order_by(Alert.timestamp).first()
        db.session.delete(oldest_alert)
    new_alert = Alert(agent_id=agent_id, issue_description=issue, metric_data=metrics)
    db.session.add(new_alert)