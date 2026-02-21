"""
Quick test to verify your Google Sheets connection is working.
Run this before running the full erg_agent.py

Usage: python test_sheets_connection.py
"""

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

CREDENTIALS_FILE = "google_credentials.json"
GOOGLE_SHEET_ID = "1yslroKc4PEj2drmX48gyi64-4HLLSFE4iRHf4fdVy9s"  # ← paste your sheet ID here

def test_connection():
    print("Testing Google Sheets connection...\n")

    # 1. Load credentials
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scopes)
        print("✅ Credentials file loaded successfully")
    except FileNotFoundError:
        print("❌ google_credentials.json not found — make sure it's in the same folder as this script")
        return
    except Exception as e:
        print(f"❌ Error loading credentials: {e}")
        return

    # 2. Connect to Sheets API
    try:
        service = build("sheets", "v4", credentials=creds)
        sheets = service.spreadsheets()
        print("✅ Connected to Google Sheets API")
    except Exception as e:
        print(f"❌ Could not connect to Sheets API: {e}")
        return

    # 3. Try to read the sheet
    try:
        result = sheets.get(spreadsheetId=GOOGLE_SHEET_ID).execute()
        print(f"✅ Sheet found: '{result['properties']['title']}'")
        tabs = [s['properties']['title'] for s in result['sheets']]
        print(f"   Tabs: {tabs}")
    except Exception as e:
        print(f"❌ Could not read sheet: {e}")
        print("   → Double-check your GOOGLE_SHEET_ID")
        print("   → Make sure you shared the sheet with the service account email")
        return

    # 4. Try to write a test row
    try:
        sheets.values().append(
            spreadsheetId=GOOGLE_SHEET_ID,
            range="Sheet1!A:A",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [["✅ Erg Agent connection test — you can delete this row"]]}
        ).execute()
        print("✅ Successfully wrote a test row to your sheet!")
        print("\n🎉 Everything is working. You can delete the test row from your sheet.")
    except Exception as e:
        print(f"❌ Could not write to sheet: {e}")
        print("   → Make sure the service account has Editor (not just Viewer) access")

if __name__ == "__main__":
    test_connection()
