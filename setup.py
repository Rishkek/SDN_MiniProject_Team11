#!/usr/bin/env python3
"""
Automated Setup and Prerequisite Installer.
Topic 27: Congestion Detection and Traffic Rerouting.

Behavior:
- Checks all required system packages and Python libraries.
- If everything is already installed: seamlessly executes run.py.
- If anything is missing: installs prerequisites automatically, then executes run.py.
"""

import sys
import os
import subprocess
import shutil
import platform

REQUIRED_PYTHON_MODULES = [
    ("matplotlib", "matplotlib"),
    ("networkx", "networkx"),
    ("tabulate", "tabulate"),
    ("rich", "rich"),
    ("psutil", "psutil"),
    ("pytest", "pytest"),
    ("PyQt6", "PyQt6")
]

LINUX_SYSTEM_PACKAGES = [
    ("mn", "mininet"),
    ("ovs-vsctl", "openvswitch-switch"),
    ("ovs-ofctl", "openvswitch-switch"),
    ("ifconfig", "net-tools")
]


def check_python_modules():
    """Returns a list of missing Python package names."""
    missing = []
    for mod_name, pip_name in REQUIRED_PYTHON_MODULES:
        try:
            __import__(mod_name)
        except ImportError:
            missing.append(pip_name)
    return missing


def check_linux_system_tools():
    """Returns a list of missing Linux system apt packages."""
    if platform.system().lower() != "linux":
        return []
    missing_pkgs = []
    for cmd, pkg in LINUX_SYSTEM_PACKAGES:
        if shutil.which(cmd) is None and pkg not in missing_pkgs:
            missing_pkgs.append(pkg)
    return missing_pkgs


def install_python_requirements(missing):
    """Installs missing Python packages via pip."""
    print(f"\n[*] Installing missing Python packages: {', '.join(missing)}...")
    req_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "requirements.txt")
    if os.path.exists(req_file):
        cmd = [sys.executable, "-m", "pip", "install", "-r", req_file]
    else:
        cmd = [sys.executable, "-m", "pip", "install"] + missing

    try:
        subprocess.check_call(cmd)
        print("[OK] Python packages installed successfully!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[!] Pip installation failed: {e}", file=sys.stderr)
        return False


def install_linux_packages(missing_pkgs):
    """Installs missing Linux apt packages using sudo if available."""
    print(f"\n[*] Installing required Linux system packages: {', '.join(missing_pkgs)}...")
    is_root = (os.geteuid() == 0) if hasattr(os, "geteuid") else False
    prefix = [] if is_root else ["sudo"]

    try:
        print("[*] Updating package index (apt update)...")
        subprocess.check_call(prefix + ["apt-get", "update", "-y"])
        print(f"[*] Installing packages: {missing_pkgs}...")
        subprocess.check_call(prefix + ["apt-get", "install", "-y"] + missing_pkgs)
        # Ensure Open vSwitch service is active
        try:
            subprocess.run(prefix + ["service", "openvswitch-switch", "start"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
        print("[OK] Linux system packages installed successfully!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[!] System package installation failed: {e}", file=sys.stderr)
        print("[!] Please run manually: sudo apt-get update && sudo apt-get install -y mininet openvswitch-switch net-tools")
        return False


def launch_run_py():
    """Transitions execution directly to run.py."""
    run_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run.py")
    if not os.path.exists(run_path):
        print(f"[!] Could not locate run.py at {run_path}", file=sys.stderr)
        sys.exit(1)

    print("\n" + "=" * 60)
    print(" [OK] Ready! Launching application via run.py...")
    print("=" * 60 + "\n")

    sys.stdout.flush()

    # Pass any extra CLI arguments through to run.py
    forward_args = [sys.executable, run_path] + sys.argv[1:]

    # On POSIX (Linux/Mac), use execv for a seamless process replacement
    if hasattr(os, "execv") and platform.system().lower() != "windows":
        os.execv(sys.executable, forward_args)
    else:
        # On Windows
        exit_code = subprocess.call(forward_args)
        sys.exit(exit_code)


def main():
    print("=" * 60)
    print("      SDN Project Setup & Dependency Verification")
    print(f"      Platform: {platform.system()} {platform.release()} | Python {platform.python_version()}")
    print("=" * 60)

    missing_py = check_python_modules()
    missing_linux = check_linux_system_tools()

    if not missing_py and not missing_linux:
        print("[OK] All system prerequisites and Python packages are already satisfied!")
        print("[OK] Automatically redirecting to run.py...\n")
        launch_run_py()
        return

    # Something is missing -> Install
    if missing_linux:
        print(f"[!] Missing Linux system utilities: {missing_linux}")
        install_linux_packages(missing_linux)

    if missing_py:
        print(f"[!] Missing Python libraries: {missing_py}")
        install_python_requirements(missing_py)

    # Re-verify
    re_missing_py = check_python_modules()
    if re_missing_py:
        print(f"[!] Warning: Some Python packages still missing: {re_missing_py}")

    launch_run_py()


if __name__ == "__main__":
    main()
