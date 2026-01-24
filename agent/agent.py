import psutil
import requests
import time
import socket
import platform
from datetime import datetime

class RealMonitoringAgent:
    def __init__(self, agent_id):
        self.agent_id = agent_id
        self.server_url = "http://127.0.0.1:5000"  # Change to your server IP when deploying
    
    def get_real_metrics(self):
        """Get ACTUAL system metrics (not random)"""
        # CPU usage (1-second interval for accuracy)
        cpu_percent = psutil.cpu_percent(interval=1)
        
        # Memory usage
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        
        # Disk usage (main drive - C:/ on Windows, / on Linux/Mac)
        if platform.system() == "Windows":
            disk = psutil.disk_usage('C:\\')
        else:
            disk = psutil.disk_usage('/')
        disk_percent = disk.percent
        
        return {
            "cpu": round(cpu_percent, 2),
            "memory": round(memory_percent, 2),
            "disk": round(disk_percent, 2)
        }
    
    def send_report(self):
        """Send REAL metrics to server"""
        metrics = self.get_real_metrics()
        payload = {
            "agent_id": self.agent_id,
            **metrics
        }
        
        try:
            response = requests.post(
                f"{self.server_url}/api/report",
                json=payload,
                timeout=5
            )
            
            current_time = datetime.now().strftime("%H:%M:%S")
            
            if response.status_code == 200:
                print(f"[{current_time}] {self.agent_id}: "
                      f"CPU={metrics['cpu']:5.1f}% | "
                      f"Memory={metrics['memory']:5.1f}% | "
                      f"Disk={metrics['disk']:5.1f}%")
            else:
                print(f"[{current_time}] Error: {response.status_code}")
                
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Error: {e}")
    
    def run(self, interval=5):
        """Run the agent continuously"""
        print(f"\n{'='*60}")
        print(f"REAL SYSTEM MONITOR: {self.agent_id}")
        print(f"Collecting ACTUAL system metrics every {interval} seconds")
        print("Press Ctrl+C to stop")
        print(f"{'='*60}\n")
        
        try:
            while True:
                self.send_report()
                time.sleep(interval)
        except KeyboardInterrupt:
            print(f"\nAgent {self.agent_id} stopped.")

def main():
    # Get agent name from computer hostname
    agent_id = socket.gethostname()  # This gets your computer name
    
    # Or use custom name
    # agent_id = "OfficePC1"  # Uncomment and change this
    
    agent = RealMonitoringAgent(agent_id)
    agent.run(interval=5)

if __name__ == "__main__":
    # Check if psutil is installed
    try:
        import psutil
    except ImportError:
        print("Installing psutil package...")
        import subprocess
        import sys
        subprocess.check_call([sys.executable, "-m", "pip", "install", "psutil"])
        import psutil
    
    main()