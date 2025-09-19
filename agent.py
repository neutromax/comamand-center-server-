# agent.py
import requests
import psutil
import time
import socket
import os
from datetime import datetime

# --- Configuration ---
# For local testing, use 127.0.0.1. 
# For deployment, change this to your cloud server's public IP address.
SERVER_URL = "http://127.0.0.1:5000" 

# Get the computer's name to use as a unique ID
AGENT_ID = socket.gethostname()

# Define where downloaded files will be stored
DOWNLOADS_FOLDER = 'agent_downloads'

# --- Setup ---
# Create the downloads folder if it doesn't already exist
os.makedirs(DOWNLOADS_FOLDER, exist_ok=True)

# --- Core Functions ---
def get_system_metrics():
    """Gathers all the detailed system metrics."""
    # Get boot time and format it nicely
    boot_time = datetime.fromtimestamp(psutil.boot_time()).strftime("%Y-%m-%d %H:%M:%S")
    # Get disk usage for the main partition (e.g., C:\ drive)
    disk_usage = psutil.disk_usage('/')
    
    return {
        "agent_id": AGENT_ID,
        "cpu_percent": psutil.cpu_percent(interval=1),
        "memory_percent": psutil.virtual_memory().percent,
        "disk_percent": disk_usage.percent,
        "boot_time": boot_time,
    }

def report_to_server():
    """Collects metrics and sends a health report to the central server."""
    try:
        metrics = get_system_metrics()
        print(f"Sending health report: {metrics}")
        # Send the data to the server's '/api/report' endpoint
        requests.post(f"{SERVER_URL}/api/report", json=metrics, timeout=10)
    except requests.exceptions.RequestException as e:
        print(f"Error sending report: {e}")

def check_for_commands():
    """Asks the server if there are any pending commands to execute."""
    try:
        url = f"{SERVER_URL}/api/commands/{AGENT_ID}"
        response = requests.get(url, timeout=10)
        command = response.json()
        
        # If the server sends a command, and that command is a 'download' task...
        if command and command.get('task') == 'download_from_host':
            filename = command.get('filename')
            if filename:
                print(f"Received command to download: {filename}")
                download_file(filename)
    except requests.exceptions.RequestException as e:
        print(f"Error checking for commands: {e}")

def download_file(filename):
    """Downloads a specific file from the server's shared host folder."""
    try:
        url = f"{SERVER_URL}/api/download/host/{filename}"
        response = requests.get(url, stream=True)
        if response.status_code == 200:
            # Save the downloaded file into the local 'agent_downloads' folder
            filepath = os.path.join(DOWNLOADS_FOLDER, filename)
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            print(f"Successfully downloaded '{filename}' to '{DOWNLOADS_FOLDER}'.")
        else:
            print(f"Failed to download file. Server responded with: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"Error downloading file: {e}")

# --- Main Loop ---
if __name__ == "__main__":
    print(f"--- Starting Agent '{AGENT_ID}' ---")
    while True:
        report_to_server()
        check_for_commands()
        # Wait for 10 seconds before the next cycle
        time.sleep(10)