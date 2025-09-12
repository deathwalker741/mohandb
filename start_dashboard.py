#!/usr/bin/env python3
"""
Startup script for the School Management Dashboard
"""

import os
import sys
import subprocess
from pathlib import Path

def check_dependencies():
    """Check if required dependencies are installed"""
    try:
        import flask
        import pandas
        import openpyxl
        print("✅ All dependencies are installed")
        return True
    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        print("Please run: pip install -r requirements.txt")
        return False

def check_excel_file():
    """Check if Excel file exists"""
    excel_path = r"C:\Users\mnage\Downloads\Tracker 2025-26.xlsx"
    if os.path.exists(excel_path):
        print(f"✅ Excel file found: {excel_path}")
        return True
    else:
        print(f"❌ Excel file not found: {excel_path}")
        print("Please ensure the Excel file is in the correct location.")
        return False

def main():
    """Main startup function"""
    print("🚀 Starting School Management Dashboard...")
    print("=" * 50)
    
    # Check dependencies
    if not check_dependencies():
        return False
    
    # Check Excel file
    if not check_excel_file():
        return False
    
    print("\n📋 System Information:")
    print(f"  - Python version: {sys.version}")
    print(f"  - Working directory: {os.getcwd()}")
    print(f"  - Flask app: app.py")
    
    print("\n🌐 Starting web server...")
    print("  - URL: http://localhost:5000")
    print("  - Press Ctrl+C to stop the server")
    print("=" * 50)
    
    try:
        # Start the Flask application
        subprocess.run([sys.executable, "app.py"], check=True)
    except KeyboardInterrupt:
        print("\n👋 Dashboard stopped by user")
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Error starting dashboard: {e}")
        return False
    
    return True

if __name__ == "__main__":
    success = main()
    if not success:
        sys.exit(1)
