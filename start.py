#!/usr/bin/env python3
"""
Startup script for Gmail-WhatsApp automation bot
This script handles initialization and provides helpful startup information
"""

import os
import sys
import time
from dotenv import load_dotenv

def check_setup():
    """Check if basic setup is complete"""
    print("🔍 Checking setup...")
    
    # Load environment variables
    load_dotenv()
    
    # Check for required files
    required_files = ['credentials.json']
    missing_files = [f for f in required_files if not os.path.exists(f)]
    
    if missing_files:
        print(f"❌ Missing files: {', '.join(missing_files)}")
        print("   Please ensure you have downloaded credentials.json from Google Cloud Console")
        return False
    
    # Check for environment variables
    required_vars = ['TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'TWILIO_WHATSAPP_NUMBER', 'MY_WHATSAPP_NUMBER']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print(f"❌ Missing environment variables: {', '.join(missing_vars)}")
        print("   Please check your .env file")
        return False
    
    print("✅ Basic setup looks good!")
    return True

def print_startup_info():
    """Print helpful startup information"""
    print("\n" + "="*60)
    print("🚀 Gmail-WhatsApp Automation Bot Starting...")
    print("="*60)
    print()
    print("📋 What this bot does:")
    print("   1. Polls Gmail every 60 seconds for new emails")
    print("   2. Summarizes emails using AI (BART model)")
    print("   3. Sends summaries to your WhatsApp")
    print("   4. Formalizes your WhatsApp replies using AI (FLAN-T5)")
    print("   5. Sends formalized emails back to Gmail")
    print()
    print("📱 WhatsApp Commands:")
    print("   • Any text → Formalize as email reply")
    print("   • 'CONFIRM' → Send the current draft")
    print("   • 'EDIT [instructions]' → Modify the draft")
    print()
    print("🌐 Webhook Setup:")
    print("   1. Run 'ngrok http 5000' in another terminal")
    print("   2. Copy the HTTPS URL (e.g., https://abc123.ngrok.io)")
    print("   3. Set Twilio webhook URL to: https://abc123.ngrok.io/whatsapp")
    print()
    print("📊 Monitoring:")
    print("   • Health check: http://localhost:5000/health")
    print("   • Status: http://localhost:5000/status")
    print("   • Logs: Check app.log file")
    print()
    print("⚠️  Note: First run will download AI models (~3GB)")
    print("   This may take several minutes depending on your internet speed.")
    print()
    print("="*60)

def main():
    """Main startup function"""
    try:
        # Check basic setup
        if not check_setup():
            print("\n❌ Setup incomplete. Please fix the issues above.")
            print("   Run 'python test_setup.py' for detailed diagnostics.")
            sys.exit(1)
        
        # Print startup information
        print_startup_info()
        
        # Give user time to read
        print("⏳ Starting in 5 seconds... (Press Ctrl+C to cancel)")
        for i in range(5, 0, -1):
            print(f"   {i}...")
            time.sleep(1)
        
        print("\n🚀 Starting Flask application...")
        
        # Import and start the main application
        from main import app, initialize_services
        import threading
        
        # Initialize services
        initialize_services()
        
        # Start Flask app
        app.run(host='0.0.0.0', port=5000, debug=False)
        
    except KeyboardInterrupt:
        print("\n\n👋 Shutting down gracefully...")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Startup error: {e}")
        print("   Check your configuration and try again.")
        sys.exit(1)

if __name__ == "__main__":
    main()
