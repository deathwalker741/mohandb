#!/usr/bin/env python3
"""
Deployment helper script for School Management Dashboard
"""

import os
import subprocess
import sys

def check_git():
    """Check if git is installed and initialized"""
    try:
        result = subprocess.run(['git', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ Git is installed")
            return True
        else:
            print("❌ Git is not installed")
            return False
    except FileNotFoundError:
        print("❌ Git is not installed")
        return False

def init_git_repo():
    """Initialize git repository"""
    try:
        # Check if already a git repo
        if os.path.exists('.git'):
            print("✅ Git repository already initialized")
            return True
        
        # Initialize git
        subprocess.run(['git', 'init'], check=True)
        print("✅ Git repository initialized")
        
        # Add all files
        subprocess.run(['git', 'add', '.'], check=True)
        print("✅ Files added to git")
        
        # Initial commit
        subprocess.run(['git', 'commit', '-m', 'Initial commit - School Dashboard'], check=True)
        print("✅ Initial commit created")
        
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Git error: {e}")
        return False

def create_github_repo_instructions():
    """Print instructions for creating GitHub repository"""
    print("\n📋 Next Steps:")
    print("1. Go to https://github.com/new")
    print("2. Create a new repository named 'school-dashboard'")
    print("3. Don't initialize with README (we already have files)")
    print("4. Copy the repository URL")
    print("5. Run these commands:")
    print("   git remote add origin <your-repo-url>")
    print("   git branch -M main")
    print("   git push -u origin main")

def main():
    """Main deployment setup function"""
    print("🚀 School Dashboard Deployment Setup")
    print("=" * 50)
    
    # Check git
    if not check_git():
        print("\n❌ Please install Git first:")
        print("   Windows: https://git-scm.com/download/win")
        print("   Mac: brew install git")
        print("   Linux: sudo apt install git")
        return False
    
    # Initialize git repo
    if not init_git_repo():
        return False
    
    # Show next steps
    create_github_repo_instructions()
    
    print("\n🎯 Deployment Options:")
    print("1. Railway (Recommended): https://railway.app")
    print("2. Render: https://render.com")
    print("3. Heroku: https://heroku.com")
    
    print("\n📖 For detailed instructions, see DEPLOYMENT_GUIDE.md")
    
    return True

if __name__ == "__main__":
    success = main()
    if not success:
        sys.exit(1)
