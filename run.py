import os
import sys
import subprocess
import venv
from pathlib import Path

# Constants
BASE_DIR = Path(__file__).parent.resolve()
VENV_DIR = BASE_DIR / "venv"
REQUIREMENTS_FILE = BASE_DIR / "requirements.txt"

def is_virtual_environment():
    """Check if running inside a virtual environment."""
    return (hasattr(sys, 'real_prefix') or
            (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix))

def get_venv_python():
    """Get the path to the virtual environment's python executable."""
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"

def create_venv():
    """Create the virtual environment if it doesn't exist."""
    print(f"[*] Creating virtual environment in {VENV_DIR}...")
    venv.create(VENV_DIR, with_pip=True)

def install_dependencies():
    """Install dependencies from requirements.txt."""
    python_exec = get_venv_python()
    print(f"[*] Installing dependencies from {REQUIREMENTS_FILE.name}...")
    try:
        subprocess.check_call([str(python_exec), "-m", "pip", "install", "-r", str(REQUIREMENTS_FILE)])
    except subprocess.CalledProcessError as e:
        print(f"[!] Failed to install dependencies: {e}")
        sys.exit(1)

def run_in_venv():
    """Restart the script using the virtual environment interpreter."""
    python_exec = get_venv_python()
    if not python_exec.exists():
        print(f"[!] Error: Virtual environment python not found at {python_exec}")
        sys.exit(1)
    
    # Run the script with the same arguments
    try:
        subprocess.check_call([str(python_exec), __file__] + sys.argv[1:])
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)
    except KeyboardInterrupt:
        sys.exit(0)

import shutil

def check_system_deps():
    """Check and install system dependencies (Linux only)."""
    if sys.platform == "linux":
        # 1. dbus-x11 (Required for gnome-terminal via sudo)
        if not shutil.which("dbus-launch"):
            print("[*] Missing system dependency: dbus-x11")
            print("[*] Installing dbus-x11 (requires sudo)...")
            try:
                subprocess.check_call(["sudo", "apt-get", "update"])
                subprocess.check_call(["sudo", "apt-get", "install", "-y", "dbus-x11"])
                print("[*] Installed dbus-x11 successfully.")
            except subprocess.CalledProcessError as e:
                print(f"[!] Failed to install dbus-x11: {e}")

        # 2. xterm (Reliable fallback)
        if not shutil.which("xterm"):
            print("[*] Missing system dependency: xterm")
            print("[*] Installing xterm (requires sudo)...")
            try:
                subprocess.check_call(["sudo", "apt-get", "install", "-y", "xterm"])
                print("[*] Installed xterm successfully.")
            except subprocess.CalledProcessError as e:
                print(f"[!] Failed to install xterm: {e}")

def main():
    if not is_virtual_environment():
        # Setup logic
        check_system_deps()
        
        if not VENV_DIR.exists():
            print("[*] First time setup detected.")
            create_venv()
            install_dependencies()
            print("[*] Setup complete.")
        
        # Handover to venv
        run_in_venv()
        return

    # Application logic (running inside venv)
    try:
        from usb_sentry.main import app
        app()
    except ImportError as e:
        print(f"[!] Critical Error: Failed to import application ({e}).")
        print("[!] The environment might be corrupted. Try deleting the 'venv' folder and running again.")
        sys.exit(1)

if __name__ == "__main__":
    main()
