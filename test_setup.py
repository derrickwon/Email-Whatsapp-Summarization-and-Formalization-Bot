#!/usr/bin/env python3
"""
Test script to verify the Gmail-WhatsApp automation setup
Run this after installing dependencies to check if everything is configured correctly
"""

import os
import sys
from dotenv import load_dotenv

def test_environment_variables():
    """Test if all required environment variables are set"""
    print("🔍 Testing environment variables...")
    
    load_dotenv()
    
    required_vars = [
        'TWILIO_ACCOUNT_SID',
        'TWILIO_AUTH_TOKEN', 
        'TWILIO_WHATSAPP_NUMBER',
        'MY_WHATSAPP_NUMBER'
    ]
    
    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        print(f"❌ Missing environment variables: {', '.join(missing_vars)}")
        print("   Please check your .env file")
        return False
    else:
        print("✅ All required environment variables are set")
        return True

def test_google_credentials():
    """Test if Google credentials file exists"""
    print("🔍 Testing Google credentials...")
    
    if os.path.exists('credentials.json'):
        print("✅ credentials.json found")
        return True
    else:
        print("❌ credentials.json not found")
        print("   Please download OAuth credentials from Google Cloud Console")
        return False

def test_dependencies():
    """Test if all required packages are installed"""
    print("🔍 Testing Python dependencies...")
    
    required_packages = [
        'flask',
        'twilio', 
        'google-api-python-client',
        'google-auth',
        'python-dotenv',
        'transformers',
        'torch'
    ]
    
    missing_packages = []
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print(f"❌ Missing packages: {', '.join(missing_packages)}")
        print("   Run: pip install -r requirements.txt")
        return False
    else:
        print("✅ All required packages are installed")
        return True

def test_services():
    """Test if services can be imported"""
    print("🔍 Testing service imports...")
    
    try:
        from gmail_service import GmailService
        from whatsapp_service import WhatsAppService
        from summarizer_local import EmailSummarizer
        from formalizer_local import ReplyFormalizer
        print("✅ All service modules can be imported")
        return True
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False

def main():
    """Run all tests"""
    print("🚀 Gmail-WhatsApp Automation Setup Test")
    print("=" * 50)
    
    tests = [
        test_dependencies,
        test_environment_variables,
        test_google_credentials,
        test_services
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        print()
    
    print("=" * 50)
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Your setup is ready.")
        print("\nNext steps:")
        print("1. Run: python main.py")
        print("2. Set up ngrok: ngrok http 5000")
        print("3. Configure Twilio webhook URL")
    else:
        print("⚠️  Some tests failed. Please fix the issues above.")
        sys.exit(1)

if __name__ == "__main__":
    main()
