import os
import subprocess
import sys

# Define required Python and pip versions
REQUIRED_PYTHON = (3, 10) # e.g., Python 3.10
REQUIRED_PIP_VERSION = (24, 2)  # e.g., pip 24.2 or later

def check_python_version():
    current_python = sys.version_info[:2]
    if current_python < REQUIRED_PYTHON:
        print(f"Python {REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]} or higher is required.")
        sys.exit(1)
    print(f"Python {current_python[0]}.{current_python[1]} is installed. Good to go.")

def check_pip_version():
    pip_version = subprocess.check_output([sys.executable, "-m", "pip", "--version"]).decode("utf-8")
    pip_version_number = tuple(map(int, pip_version.split()[1].split(".")))
    if pip_version_number < REQUIRED_PIP_VERSION:
        print(f"pip {REQUIRED_PIP_VERSION[0]}.{REQUIRED_PIP_VERSION[1]} or higher is required.")
        update_pip()
    else:
        print(f"pip {pip_version_number[0]}.{pip_version_number[1]} is installed. Good to go.")

def update_pip():
    print("Updating pip...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    print("pip updated successfully.")

def install_requirements():
    print("Installing required packages...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
    print("Packages installed successfully.")

def run_pyqt_app():
    print("Running PyQt5 application...")
    os.system(f"{sys.executable} app.py")

if __name__ == "__main__":
    check_python_version()
    check_pip_version()
    install_requirements()
    run_pyqt_app()
