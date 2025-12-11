#!/usr/bin/env python3
"""
Diagnostic script to test Google Sheets credentials initialization
Run this on Render to debug credential issues
"""

import os
import base64
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_credentials():
    """Test Google Sheets credentials loading"""

    print("\n" + "="*60)
    print("GOOGLE SHEETS CREDENTIALS DIAGNOSTIC")
    print("="*60 + "\n")

    # Check environment variables
    creds_file = os.getenv("GOOGLE_SHEETS_CREDENTIALS", "service_account.json")
    creds_json = os.getenv("GOOGLE_SHEETS_CREDENTIALS_JSON", "")

    print(f"1. Environment Variables:")
    print(f"   GOOGLE_SHEETS_CREDENTIALS = {creds_file}")
    print(f"   GOOGLE_SHEETS_CREDENTIALS_JSON exists: {bool(creds_json)}")
    if creds_json:
        print(f"   GOOGLE_SHEETS_CREDENTIALS_JSON length: {len(creds_json)}")
        print(f"   First 50 chars: {creds_json[:50]}...")
    print()

    # Check if file exists
    print(f"2. File Check:")
    file_exists = os.path.exists(creds_file)
    print(f"   File '{creds_file}' exists: {file_exists}")
    print()

    # Try to decode JSON from environment variable
    if creds_json:
        print(f"3. Decoding GOOGLE_SHEETS_CREDENTIALS_JSON:")

        # Test 1: Try as base64
        try:
            cleaned_base64 = creds_json.replace(' ', '').replace('\n', '').replace('\r', '').replace('\t', '')
            print(f"   Cleaned base64 length: {len(cleaned_base64)}")

            decoded_json = base64.b64decode(cleaned_base64).decode('utf-8')
            print(f"   ✅ Successfully decoded as base64")
            print(f"   Decoded JSON length: {len(decoded_json)}")

            # Try to parse JSON
            try:
                creds_dict = json.loads(decoded_json)
                print(f"   ✅ Successfully parsed as JSON")
                print(f"   JSON keys: {list(creds_dict.keys())}")

                # Check required fields
                required_fields = ['type', 'project_id', 'private_key_id', 'private_key', 'client_email']
                missing_fields = [f for f in required_fields if f not in creds_dict]
                if missing_fields:
                    print(f"   ⚠️ Missing required fields: {missing_fields}")
                else:
                    print(f"   ✅ All required fields present")

            except json.JSONDecodeError as e:
                print(f"   ❌ Failed to parse as JSON: {e}")
                print(f"   First 200 chars of decoded: {decoded_json[:200]}")

        except Exception as e:
            print(f"   ⚠️ Failed to decode as base64: {e}")

            # Test 2: Try as plain JSON
            try:
                print(f"\n   Trying as plain JSON (not base64)...")
                # Replace escaped newlines
                plain_json = creds_json.replace('\\n', '\n')
                creds_dict = json.loads(plain_json)
                print(f"   ✅ Successfully parsed as plain JSON")
                print(f"   JSON keys: {list(creds_dict.keys())}")
            except Exception as e2:
                print(f"   ❌ Failed to parse as plain JSON: {e2}")
                print(f"   First 200 chars: {creds_json[:200]}")
    else:
        print(f"3. GOOGLE_SHEETS_CREDENTIALS_JSON not set")

    print()

    # Try to initialize EmailSheetsManager
    print(f"4. Testing EmailSheetsManager initialization:")
    try:
        from email_sheets_manager import EmailSheetsManager

        email_sheets = EmailSheetsManager(creds_file, "PostBD", creds_json)
        print(f"   ✅ EmailSheetsManager initialized successfully!")

        # Try to get spreadsheet info
        try:
            spreadsheet = email_sheets.spreadsheet
            print(f"   ✅ Connected to spreadsheet: {spreadsheet.title}")
            print(f"   Spreadsheet ID: {spreadsheet.id}")
            print(f"   Worksheet count: {len(spreadsheet.worksheets())}")
        except Exception as e:
            print(f"   ⚠️ Connected but couldn't get spreadsheet info: {e}")

    except Exception as e:
        print(f"   ❌ Failed to initialize EmailSheetsManager: {e}")
        import traceback
        print(f"\n   Full traceback:")
        print("   " + "\n   ".join(traceback.format_exc().split('\n')))

    print()
    print("="*60)
    print("DIAGNOSTIC COMPLETE")
    print("="*60)

if __name__ == "__main__":
    test_credentials()
