import os
import subprocess

def setup_project():
    print("Setting up Monitoring System...")
    
    # Create directory structure
    directories = [
        "static/css",
        "static/js", 
        "templates"
    ]
    
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
        print(f"Created directory: {directory}")
    
    # Install dependencies
    print("\nInstalling dependencies...")
    subprocess.run(["pip", "install", "-r", "requirements.txt"])
    
    print("\nSetup complete!")
    print("\nTo run the system:")
    print("1. Start the server: python app.py")
    print("2. Run sample agents: python agent_simulator.py [agent_name]")
    print("3. Open browser: http://127.0.0.1:5000")

if __name__ == "__main__":
    setup_project()