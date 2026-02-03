#!/usr/bin/env python
import sys
import os
import subprocess
import shutil

def check_pyinstaller():
    try:
        import PyInstaller
        return True
    except ImportError:
        return False

def install_pyinstaller():
    print("Installing PyInstaller...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
    print("PyInstaller installed successfully!")

def build_server():
    print("\n=== Building FRPS Server ===")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", "frps",
        "--console",
        "--clean",
        "frps_standalone.py"
    ]
    
    try:
        subprocess.check_call(cmd)
        print("FRPS Server built successfully!")
        print("Executable: dist/frps.exe")
    except subprocess.CalledProcessError as e:
        print(f"Error building FRPS: {e}")
        return False
    return True

def build_client():
    print("\n=== Building FRPC Client ===")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", "frpc",
        "--console",
        "--clean",
        "frpc_standalone.py"
    ]
    
    try:
        subprocess.check_call(cmd)
        print("FRPC Client built successfully!")
        print("Executable: dist/frpc.exe")
    except subprocess.CalledProcessError as e:
        print(f"Error building FRPC: {e}")
        return False
    return True

def main():
    print("FRP-Python Build Script")
    print("=" * 40)
    
    if not check_pyinstaller():
        print("PyInstaller not found. Installing...")
        install_pyinstaller()
    
    if len(sys.argv) > 1:
        target = sys.argv[1].lower()
        if target == "server" or target == "frps":
            build_server()
        elif target == "client" or target == "frpc":
            build_client()
        elif target == "all":
            if build_server() and build_client():
                print("\n=== Build Complete ===")
                print("Executables:")
                print("  - dist/frps.exe (Server)")
                print("  - dist/frpc.exe (Client)")
            else:
                print("\nBuild failed!")
                sys.exit(1)
        else:
            print(f"Unknown target: {target}")
            print("Usage: python build.py [server|client|all]")
            sys.exit(1)
    else:
        print("Building both server and client...")
        if build_server() and build_client():
            print("\n=== Build Complete ===")
            print("Executables:")
            print("  - dist/frps.exe (Server)")
            print("  - dist/frpc.exe (Client)")
        else:
            print("\nBuild failed!")
            sys.exit(1)

if __name__ == "__main__":
    main()
