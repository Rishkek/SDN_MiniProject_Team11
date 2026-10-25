#!/usr/bin/env python3
"""
Automated Setup and Prerequisite Installer for Ubuntu / Linux VM.
Topic 27: Congestion Detection and Traffic Rerouting.

Installs all system utilities and Python dependencies in a single bulk
apt-get command using native Ubuntu packages (python3-xyz):
- mininet, openvswitch-switch, net-tools
- python3-matplotlib, python3-networkx, python3-pyqt6, python3-tabulate,
  python3-psutil, python3-pytest, python3-rich
"""

import sys
import os
import subprocess
import shutil
import platform

# Complete list of native Ubuntu packages (System tools + python3-xyz)
UBUNTU_BULK_APT_PACKAGES = [
    "mininet",
    "openvswitch-switch",
    "net-tools",
    "iperf",
    "tcpdump",
    "python3-pip",
    "python3-matplotlib",
    "python3-networkx",
    "python3-pyqt6",
    "python3-tabulate",
    "python3-psutil",
    "python3-pytest",
    "python3-rich",
    "python3-pyqtgraph"
]

REQUIRED_PYTHON_MODULES = [
    ("matplotlib", "python3-matplotlib"),
    ("networkx", "python3-networkx"),
    ("tabulate", "python3-tabulate"),
    ("rich", "python3-rich"),
    ("psutil", "python3-psutil"),
    ("pytest", "python3-pytest"),
    ("PyQt6", "python3-pyqt6"),
    ("pyqtgraph", "python3-pyqtgraph")
]

REQUIRED_SYSTEM_TOOLS = [
    ("mn", "mininet"),
    ("ovs-vsctl", "openvswitch-switch"),
    ("ovs-ofctl", "openvswitch-switch"),
    ("ifconfig", "net-tools")
]


def check_prerequisites():
    """Checks if all required Python modules and system commands are available."""
    missing_modules = []
    for mod_name, _ in REQUIRED_PYTHON_MODULES:
        try:
            __import__(mod_name)
        except ImportError:
            missing_modules.append(mod_name)

    missing_tools = []
    if platform.system().lower() == "linux":
        for cmd, _ in REQUIRED_SYSTEM_TOOLS:
            if shutil.which(cmd) is None:
                missing_tools.append(cmd)

    return missing_modules, missing_tools


def install_ubuntu_bulk():
    """Executes a single bulk sudo apt install command for all packages."""
    print("\n" + "=" * 65)
    print(" [*] Executing Bulk Ubuntu Package Installation (apt-get install)")
    print("=" * 65)
    print(f" Packages: {' '.join(UBUNTU_BULK_APT_PACKAGES)}\n")

    is_root = (os.geteuid() == 0) if hasattr(os, "geteuid") else False
    prefix = [] if is_root else ["sudo"]

    try:
        # Step 1: apt-get update
        print("[*] Running: sudo apt-get update -y...")
        subprocess.check_call(prefix + ["apt-get", "update", "-y"])

        # Step 2: Bulk apt-get install in one command
        cmd = prefix + ["apt-get", "install", "-y", "--no-install-recommends"] + UBUNTU_BULK_APT_PACKAGES
        print(f"\n[*] Running: {' '.join(cmd)}...")
        subprocess.check_call(cmd)

        # Step 3: Ensure Open vSwitch service is running
        print("\n[*] Starting Open vSwitch system service...")
        try:
            subprocess.run(prefix + ["service", "openvswitch-switch", "start"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

        print("\n[OK] Bulk apt package installation completed successfully!")
        return True

    except subprocess.CalledProcessError as e:
        print(f"\n[!] Bulk apt installation failed with exit code {e.returncode}.", file=sys.stderr)
        print("[!] Trying pip fallback for any missing Python packages...", file=sys.stderr)
        try:
            pip_cmd = [sys.executable, "-m", "pip", "install", "--break-system-packages", "matplotlib", "networkx", "PyQt6", "tabulate", "psutil", "pytest", "rich"]
            subprocess.call(pip_cmd)
        except Exception:
            pass
        return False


def launch_run_py():
    """Transitions execution seamlessly to run.py."""
    run_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run.py")
    if not os.path.exists(run_path):
        print(f"[!] Could not locate run.py at {run_path}", file=sys.stderr)
        sys.exit(1)

    print("\n" + "=" * 65)
    print(" [OK] All prerequisites satisfied! Launching application via run.py...")
    print("=" * 65 + "\n")
    sys.stdout.flush()

    forward_args = [sys.executable, run_path] + sys.argv[1:]

    # On Linux/macOS, use os.execv for direct process replacement
    if hasattr(os, "execv") and platform.system().lower() != "windows":
        os.execv(sys.executable, forward_args)
    else:
        exit_code = subprocess.call(forward_args)
        sys.exit(exit_code)


def main():
    print("=" * 65)
    print("      SDN Project Setup & Ubuntu VM Prerequisite Installer")
    print(f"      Platform: {platform.system()} {platform.release()} | Python {platform.python_version()}")
    print("=" * 65)

    missing_modules, missing_tools = check_prerequisites()

    # If already installed, jump straight to run.py
    if not missing_modules and not missing_tools:
        print("[OK] All system prerequisites and Python packages are already satisfied!")
        print("[OK] Automatically launching run.py...\n")
        launch_run_py()
        return

    # If running on Linux (Ubuntu VM), run bulk apt install
    if platform.system().lower() == "linux":
        print(f"[!] Missing detected: Modules={missing_modules}, Tools={missing_tools}")
        install_ubuntu_bulk()
    else:
        # Windows fallback: install via pip
        print("[*] Running on Windows. Installing Python packages via pip...")
        subprocess.call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])

    # Launch run.py
    launch_run_py()


if __name__ == "__main__":
    main()
