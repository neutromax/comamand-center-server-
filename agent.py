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

def handle_server_command(server_url, api_key, command_info):
    """Executes a command sent by the server and reports the output back"""
    import subprocess
    import json
    import psutil
    
    cmd_id = command_info.get("id")
    action = command_info.get("action")
    payload = command_info.get("payload", "")
    
    print(f"\n⚙️ Received command #{cmd_id}: {action} (payload: {payload})")
    
    status = "failed"
    output = ""
    
    try:
        if action == "list_processes":
            # List top processes by CPU/Memory
            proc_list = []
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                try:
                    pinfo = proc.info
                    if pinfo['cpu_percent'] is None:
                        pinfo['cpu_percent'] = 0.0
                    if pinfo['memory_percent'] is None:
                        pinfo['memory_percent'] = 0.0
                    proc_list.append(pinfo)
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
            # Sort by CPU percent desc, limit to 20 processes
            proc_list.sort(key=lambda x: x.get('cpu_percent', 0), reverse=True)
            top_procs = proc_list[:20]
            
            output = json.dumps(top_procs)
            status = "completed"
            
        elif action == "kill_process":
            try:
                pid = int(payload)
                proc = psutil.Process(pid)
                proc.terminate()
                output = f"Successfully terminated process with PID {pid} ({proc.name()})"
                status = "completed"
            except Exception as e:
                output = f"Failed to kill process {payload}: {e}"
                status = "failed"
                
        elif action == "run_shell":
            # Command whitelist check for safety
            whitelist = [
                "df -h", "df", "uptime", "free -m", "free", 
                "ipconfig", "ifconfig", "ls", "dir", "netstat -an"
            ]
            cmd_cleaned = payload.strip().lower()
            
            is_whitelisted = False
            for w in whitelist:
                if cmd_cleaned.startswith(w):
                    is_whitelisted = True
                    break
            
            if not is_whitelisted:
                output = f"Command rejected: '{payload}' is not in the security whitelist."
                status = "failed"
            else:
                try:
                    res = subprocess.run(
                        payload,
                        shell=True,
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    output = res.stdout if res.returncode == 0 else f"Error (Exit {res.returncode}):\n{res.stderr}\nStdout:\n{res.stdout}"
                    status = "completed" if res.returncode == 0 else "failed"
                except subprocess.TimeoutExpired:
                    output = "Command execution timed out (10s limit)"
                    status = "failed"
                except Exception as e:
                    output = f"Command execution error: {e}"
                    status = "failed"
                    
    except Exception as e:
        output = f"Unexpected agent execution error: {e}"
        status = "failed"
        
    # Send result back to server
    result_url = f"{server_url}/api/command/result"
    result_data = {
        "command_id": cmd_id,
        "status": status,
        "output": output
    }
    
    # Calculate signature if key is set
    raw_payload = json.dumps(result_data).encode('utf-8')
    headers = {"Content-Type": "application/json"}
    if api_key:
        import hmac
        import hashlib
        signature = hmac.new(
            api_key.encode('utf-8'),
            raw_payload,
            hashlib.sha256
        ).hexdigest()
        headers["X-Signature"] = signature
        
    try:
        resp = requests.post(result_url, data=raw_payload, headers=headers, timeout=5)
        if resp.status_code == 200:
            print(f"✅ Sent result for command #{cmd_id} (Status: {status})")
        else:
            print(f"❌ Failed to report command #{cmd_id} result: {resp.status_code}")
    except Exception as e:
        print(f"❌ Connection error sending command result: {e}")

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Command Center Agent')
    parser.add_argument('--server', default='http://127.0.0.1:5000', 
                       help='Server URL (default: http://127.0.0.1:5000)')
    parser.add_argument('--interval', type=int, default=10,
                       help='Update interval in seconds (default: 10)')
    parser.add_argument('--name', help='Custom agent name')
    parser.add_argument('--key', default='',
                       help='API Key for HMAC authentication')
    
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
            
            # Serialize JSON explicitly and sign for HMAC verification
            import json
            import hmac
            import hashlib
            raw_payload = json.dumps(data).encode('utf-8')
            
            headers = {"Content-Type": "application/json"}
            if args.key:
                signature = hmac.new(
                    args.key.encode('utf-8'),
                    raw_payload,
                    hashlib.sha256
                ).hexdigest()
                headers["X-Signature"] = signature
            
            # Send to server
            try:
                response = requests.post(
                    f"{SERVER_URL}/api/report",
                    data=raw_payload,
                    headers=headers,
                    timeout=5
                )
                
                if response.status_code == 200:
                    print(" ✅ Sent to server")
                    # Check if server returned a pending command
                    try:
                        resp_json = response.json()
                        command_info = resp_json.get("command")
                        if command_info:
                            handle_server_command(SERVER_URL, args.key, command_info)
                    except Exception as e:
                        print(f" ⚠️ Command check error: {e}")
                else:
                    print(f" ❌ Server error: {response.status_code}")
                    
            except requests.exceptions.ConnectionError:
                print(" ❌ Connection refused")
                print("   Is server still running?")
            except requests.exceptions.Timeout:
                print(" ⏱️ Timeout")
            except Exception as e:
                print(f" ❌ Error: {str(e)[:30]}...")
            
            
            time.sleep(INTERVAL)
            
    except KeyboardInterrupt:
        print("\n\n👋 Agent stopped by user")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":

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