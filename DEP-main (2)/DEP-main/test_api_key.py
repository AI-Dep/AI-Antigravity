"""
Quick test to verify OpenAI API key works
Paste your NEW API key below to test it
"""

import os

# PASTE YOUR NEW API KEY HERE (the one you added to Streamlit Cloud Secrets)
TEST_API_KEY = "sk-proj-PASTE-YOUR-NEW-KEY-HERE"

os.environ['OPENAI_API_KEY'] = TEST_API_KEY

try:
    from openai import OpenAI
    client = OpenAI()

    print("Testing API key...")
    response = client.models.list()

    print("=" * 60)
    print("✅ SUCCESS! Your new API key works!")
    print("=" * 60)
    print(f"✅ Found {len(response.data)} models")
    print("✅ Billing is enabled")
    print("✅ Key is valid")
    print()
    print("Your Streamlit Cloud Secrets should work now!")
    print("Make sure you used this exact format in Secrets:")
    print(f'OPENAI_API_KEY = "{TEST_API_KEY}"')
    print("=" * 60)

except Exception as e:
    print("=" * 60)
    print("❌ ERROR: API key test failed")
    print("=" * 60)
    print(f"Error: {e}")
    print()
    print("Possible issues:")
    print("1. Key is invalid")
    print("2. Billing not enabled")
    print("3. Key was revoked")
    print()
    print("Go to: https://platform.openai.com/account/billing")
    print("=" * 60)
