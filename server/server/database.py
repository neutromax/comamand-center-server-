# This file is no longer needed as functions are integrated into app.py
# Keeping it for backward compatibility
from models import db, Report
from datetime import datetime, timedelta
from sqlalchemy import func, and_

def save_report(data):
    """Compatibility function - use app.py's receive_report instead"""
    print("Warning: Use app.py's receive_report endpoint instead")
    return False

def get_live_agents():
    """Compatibility function - use app.py's get_agents instead"""
    print("Warning: Use app.py's get_agents endpoint instead")
    return []

def get_last_10_reports(agent_id):
    """Compatibility function - use app.py's report_history instead"""
    print("Warning: Use app.py's report_history endpoint instead")
    return []