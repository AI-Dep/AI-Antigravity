#!/usr/bin/env python3
"""
Verify Fixed Asset AI environment setup
"""

import os
from dotenv import load_dotenv

print("=" * 60)
print("Fixed Asset AI - Configuration Verification")
print("=" * 60)
print()

# Load .env file
load_dotenv()

# Check .env file exists
if os.path.exists('.env'):
    print("✅ .env file found")
else:
    print("❌ .env file NOT found")
    print("   Run: ./setup_env.sh")
    exit(1)

print()

# Check OpenAI API Key
api_key = os.getenv('OPENAI_API_KEY')
if api_key:
    if api_key.startswith('sk-'):
        # Mask the key for security
        masked_key = api_key[:7] + "*" * (len(api_key) - 11) + api_key[-4:]
        print(f"✅ OPENAI_API_KEY is set: {masked_key}")

        # Test OpenAI connection
        try:
            from openai import OpenAI
            client = OpenAI()

            # Try a minimal API call
            print("   Testing OpenAI connection...")
            response = client.models.list()
            print("   ✅ OpenAI connection successful!")

        except Exception as e:
            print(f"   ⚠️  OpenAI connection failed: {str(e)}")
            print("   Check:")
            print("   - API key is valid")
            print("   - You have API credits")
            print("   - Internet connection is working")
    else:
        print("❌ OPENAI_API_KEY format is incorrect")
        print("   Should start with 'sk-'")
else:
    print("❌ OPENAI_API_KEY is NOT set")
    print("   Add it to .env file")

print()

# Check App Password
app_pass = os.getenv('APP_PASSWORD')
if app_pass:
    masked_pass = "*" * len(app_pass)
    print(f"✅ APP_PASSWORD is set: {masked_pass}")
    if len(app_pass) < 12:
        print("   ⚠️  Password is short. Consider using 12+ characters")
else:
    print("❌ APP_PASSWORD is NOT set")
    print("   Add it to .env file")

print()
print("=" * 60)

# Summary
all_good = (
    os.path.exists('.env') and
    api_key and
    api_key.startswith('sk-') and
    app_pass
)

if all_good:
    print("✅ Configuration is COMPLETE!")
    print()
    print("Next steps:")
    print("  1. Start the app: streamlit run fixed_asset_ai/app.py")
    print("  2. Login with your APP_PASSWORD")
    print("  3. Upload your fixed asset data")
else:
    print("⚠️  Configuration is INCOMPLETE")
    print()
    print("Fix the issues above, then run this script again")

print("=" * 60)
