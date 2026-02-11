#!/usr/bin/env python3
"""
Command Center Agent - SIMPLE WORKING VERSION
"""

import psutil
import requests
import time
import socket
import platform
import sys
import argparse
from datetime import datetime

def get_metrics():
    """Get system metrics with slight variation for realistic testing"""
    import random
    
    # Get actual system metrics
    base_cpu = psutil.cpu_percent(interval=0.5)
    base_memory = psutil.virtual_memory().percent
    
    # Add slight variation for realistic testing (±5%)
    cpu = max(0, min(100, base_cpu + random.uniform(-2, 2)))
    memory = max(0, min(100, base_memory + random.uniform(-2, 2)))
    
    # Disk usage usually changes slowly
    if platform.system() == "Windows":
        base_disk = psutil.disk_usage('C:\\').percent
    else:
        base_disk = psutil.disk_usage('/').percent
    
    disk = max(0, min(100, base_disk + random.uniform(-1, 1)))
    
    return round(cpu, 2), round(memory, 2), round(disk, 2)

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Command Center Agent')
    parser.add_argument('--server', default='http://127.0.0.1:5000', 
                       help='Server URL (default: http://127.0.0.1:5000)')
    parser.add_argument('--interval', type=int, default=10,
                       help='Update interval in seconds (default: 10)')
    parser.add_argument('--name', help='Custom agent name')
    
    args = parser.parse_args()
    
    SERVER_URL = args.server.rstrip('/')
    INTERVAL = args.interval
    
    # Generate agent ID
    if args.name:
        AGENT_ID = args.name
    else:
        AGENT_ID = f"{socket.gethostname()}-{platform.system()}"
    
    print("=" * 60)
    print("🤖 COMMAND CENTER AGENT")
    print("=" * 60)
    print(f"Agent ID: {AGENT_ID}")
    print(f"Server: {SERVER_URL}")
    print(f"Interval: {INTERVAL} seconds")
    print("=" * 60)
    
    # Test connection first
    print("\n🔍 Testing server connection...")
    try:
        response = requests.get(f"{SERVER_URL}/api/server/info", timeout=5)
        if response.status_code == 200:
            print("✅ Connected to server!")
            print(f"   Server status: {response.json().get('status', 'unknown')}")
        else:
            print(f"⚠️ Server returned: {response.status_code}")
            print("   But let's try to send data anyway...")
    except Exception as e:
        print(f"❌ Cannot connect to server: {e}")
        print("\nTROUBLESHOOTING:")
        print("1. Make sure server is running: python app.py")
        print("2. Check if URL is correct: http://127.0.0.1:5000")
        print("3. Check firewall/antivirus settings")
        print("4. Try using: http://localhost:5000")
        return
    
    print(f"\n📡 Starting to send metrics every {INTERVAL} seconds...")
    print("Press Ctrl+C to stop\n")
    
    count = 0
    try:
        while True:
            count += 1
            
            # Get system metrics
            cpu, memory, disk = get_metrics()
            
            # Prepare data for server
            data = {
                "agent_id": AGENT_ID,
                "cpu": cpu,
                "memory": memory,
                "disk": disk
            }
            
            # Display metrics
            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"[{timestamp}] #{count:03d} CPU: {cpu:5.1f}% | RAM: {memory:5.1f}% | Disk: {disk:5.1f}%", end="")
            
            # Send to server
            try:
                response = requests.post(
                    f"{SERVER_URL}/api/report",
                    json=data,
                    timeout=5
                )
                
                if response.status_code == 200:
                    print(" ✅ Sent to server")
                else:
                    print(f" ❌ Server error: {response.status_code}")
                    
            except requests.exceptions.ConnectionError:
                print(" ❌ Connection refused")
                print("   Is server still running?")
            except requests.exceptions.Timeout:
                print(" ⏱️ Timeout")
            except Exception as e:
                print(f" ❌ Error: {str(e)[:30]}...")
            
            # Wait before next report
            time.sleep(INTERVAL)
            
    except KeyboardInterrupt:
        print("\n\n👋 Agent stopped by user")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Check if required packages are installed
    try:
        import psutil
        import requests
    except ImportError:
        print("Installing required packages...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "psutil", "requests"])
        import psutil
        import requests
    
    main()