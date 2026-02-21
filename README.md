# Erg Photo Agent

An AI-powered agent that automatically reads Concept2 rowing ergometer screen photos and logs workout data to Google Sheets.

## What It Does

Coaches and athletes photograph the Concept2 erg's "View Detail" screen after each workout. This agent:

1. **Watches** a Google Drive folder for new photos (JPEG, HEIC, PNG, WebP)
2. **Reads** each photo using Claude Vision AI to extract workout data
3. **Logs** the data to a Google Sheet — one row per workout
4. **Organizes** processed photos into dated subfolders

No manual data entry. Drop a photo, the sheet updates automatically.

## Data Captured

For each workout:
- Athlete name (from sticky note on the monitor)
- Date (from photo EXIF or sticky note)
- Workout type (e.g. `5:00`, `2000m`)
- Piece number and total pieces
- Total distance (meters)
- Total time and average split (/500m)
- Average stroke rate (s/m)
- Up to 5 individual split intervals (split + stroke rate each)

## Setup

### Prerequisites

- Python 3.11+
- Google Drive for Desktop (mounted as `G:\My Drive`)
- Anthropic API key
- Google Cloud service account with Sheets API access

### Installation

```bash
git clone https://github.com/thangdvo/erg-photo-agent.git
cd erg-photo-agent
python -m venv .venv
.venv\Scripts\activate
pip install anthropic pillow pillow-heif google-api-python-client google-auth watchdog
```

### Configuration

1. Copy `.env.example` to `.env` and fill in your Anthropic API key:
   ```
   ANTHROPIC_API_KEY=sk-ant-...
   ```

2. Place your Google service account credentials file at:
   ```
   google_credentials.json
   ```

3. Edit the config block at the top of `erg_agent.py`:
   ```python
   WATCH_FOLDER     = r"G:\My Drive\YourFolder\Erg pics"
   PROCESSED_FOLDER = r"G:\My Drive\YourFolder\Erg pics\Processed"
   FAILED_FOLDER    = r"G:\My Drive\YourFolder\Erg pics\Failed"
   GOOGLE_SHEET_ID  = "your-sheet-id-here"
   SHEET_TAB_NAME   = "ErgLog"   # must match the tab name exactly, no spaces
   ```

4. Share your Google Sheet with the service account email (found in `google_credentials.json` under `client_email`), giving it Editor access.

5. Rename the target tab in your Google Sheet to match `SHEET_TAB_NAME` exactly.

### Running

```bash
# Set API key in environment (or load from .env)
export ANTHROPIC_API_KEY=sk-ant-...

python -X utf8 erg_agent.py
```

The agent processes any photos already in the watch folder on startup, then stays running and watches for new ones. Press `Ctrl+C` to stop.

## Folder Structure

```
Erg pics/
├── IMG_3167.HEIC          ← new photos land here
├── Processed/
│   └── 2026-01-19/
│       └── 2026-01-19_Davison-K_p1.heic   ← moved here after logging
└── Failed/
    └── IMG_3167_error_....heic             ← moved here if processing fails
```

## Photo Requirements

- The Concept2 monitor must be on the **"View Detail"** screen
- A sticky note on the monitor should show **Last, First** name and optionally a piece number
- Supported formats: `.jpg`, `.jpeg`, `.heic`, `.heif`, `.png`, `.webp`
- iPhone HEIC photos are fully supported via `pillow-heif`

## Troubleshooting

**Sheet tab not found** — Make sure `SHEET_TAB_NAME` in `erg_agent.py` exactly matches the tab name in Google Sheets (case-sensitive, no leading/trailing spaces).

**ANTHROPIC_API_KEY not found** — On Windows/Git Bash, add `export ANTHROPIC_API_KEY=...` to `~/.bash_profile`.

**Google Drive File On-Demand** — If photos are cloud-only placeholders, the agent will fail to read them. Open the file in Explorer first to force a download, or disable Files On-Demand in Google Drive settings.

**Date shows "unknown-date"** — HEIC files from some iPhones may not expose EXIF via pillow-heif. The date will fall back to what Claude reads from the erg screen or sticky note.

## Files

| File | Description |
|------|-------------|
| `erg_agent.py` | Main agent — run this |
| `test_sheets_connection.py` | Verify Google Sheets API connectivity |
| `test_exif.py` | Inspect EXIF data in a HEIC file |
| `google_credentials.json` | Service account key (not in repo) |
| `.env` | API keys (not in repo) |
| `.env.example` | Template showing required env vars |
