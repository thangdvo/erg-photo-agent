"""
Erg Photo Agent - Fixed Version
Changes from last working version:
1. Prompt explicitly clarifies summary row vs split rows
2. HEIC support via pillow-heif
3. Image resizing under 4MB
4. Duplicate processing prevention
5. Sheet tab name without quotes
"""

import os
import json
import time
import base64
import logging
import io
from pathlib import Path
from datetime import datetime

import anthropic
from PIL import Image
from PIL.ExifTags import TAGS
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Register HEIC support if pillow-heif is installed
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIC_SUPPORTED = True
except ImportError:
    HEIC_SUPPORTED = False

# ─── CONFIGURATION ─────────────────────────────────────────────────────────────

WATCH_FOLDER     = r"G:\My Drive\Sps rowing\Erg pics"
PROCESSED_FOLDER = r"G:\My Drive\Sps rowing\Erg pics\Processed"
FAILED_FOLDER    = r"G:\My Drive\Sps rowing\Erg pics\Failed"

CREDENTIALS_FILE = "google_credentials.json"
GOOGLE_SHEET_ID  = "1yslroKc4PEj2drmX48gyi64-4HLLSFE4iRHf4fdVy9s"
SHEET_TAB_NAME   = "ErgLog"

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp"}
MAX_IMAGE_BYTES  = 4 * 1024 * 1024  # 4MB — safely under Claude's 5MB limit

SHEET_COLUMNS = [
    "Last Name", "First Name", "Date", "Workout Type",
    "Piece #", "of Total", "Total Dist (m)", "Total Time",
    "Avg Split", "Avg SPM",
    "Split 1", "SPM 1",
    "Split 2", "SPM 2",
    "Split 3", "SPM 3",
    "Split 4", "SPM 4",
    "Split 5", "SPM 5",
    "Photo File", "Notes",
]

# ─── LOGGING ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("erg_agent.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

_processing = set()

# ─── EXIF ──────────────────────────────────────────────────────────────────────

def get_exif_date(image_path):
    try:
        img = Image.open(image_path)
        # HEIC files (via pillow-heif) use getexif(), not _getexif()
        try:
            exif_data = img.getexif()
        except Exception:
            exif_data = img._getexif() if hasattr(img, '_getexif') else None
        if not exif_data:
            return None
        for tag_id, value in exif_data.items():
            if TAGS.get(tag_id) in ("DateTimeOriginal", "DateTime"):
                dt = datetime.strptime(str(value), "%Y:%m:%d %H:%M:%S")
                return dt.strftime("%Y-%m-%d")
    except Exception as e:
        log.warning(f"Could not read EXIF: {e}")
    return None

# ─── IMAGE RESIZE ──────────────────────────────────────────────────────────────

def prepare_image(image_path):
    """Resize image to under 4MB and return (base64, media_type)."""
    img = Image.open(image_path)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=85)
    size = buffer.tell()

    quality = 85
    scale = 1.0
    while size > MAX_IMAGE_BYTES:
        buffer = io.BytesIO()
        if quality > 50:
            quality -= 10
        else:
            scale -= 0.1
            img = img.resize(
                (int(img.width * scale), int(img.height * scale)),
                Image.LANCZOS
            )
        img.save(buffer, format="JPEG", quality=quality)
        size = buffer.tell()

    log.info(f"  Image: {size:,} bytes (quality={quality}, scale={scale:.1f})")
    buffer.seek(0)
    return base64.standard_b64encode(buffer.read()).decode("utf-8"), "image/jpeg"

# ─── CLAUDE VISION ─────────────────────────────────────────────────────────────

def extract_erg_data(image_path, exif_date):
    client = anthropic.Anthropic()
    image_data, media_type = prepare_image(image_path)

    date_note = (
        f"The photo was taken on {exif_date} — use this as the workout date."
        if exif_date
        else "Read the date from the sticky note if present."
    )

    prompt = f"""You are reading a Concept2 rowing ergometer "View Detail" screen.

{date_note}

The sticky note below the monitor has the rower's name (Last, First) and optionally a piece number.

THE SCREEN LAYOUT IS:
  View Detail
  [workout type, e.g. 5:00]
  [erg date — ignore this]
  time    meter   /500m   s/m
  ─────────────────────────────
  5:00.0  XXXX   X:XX.X  XX    ← SUMMARY ROW (total for whole piece)
  1:00.0   XXX   X:XX.X  XX    ← split 1 (first minute)
  2:00.0   XXX   X:XX.X  XX    ← split 2 (second minute)
  3:00.0   XXX   X:XX.X  XX    ← split 3 (third minute)
  4:00.0   XXX   X:XX.X  XX    ← split 4 (fourth minute)
  5:00.0   XXX   X:XX.X  XX    ← split 5 (fifth minute)

CRITICAL RULES:
- The SUMMARY ROW is the FIRST data row (time matches total workout duration e.g. 5:00.0)
- The SPLIT ROWS are below the summary, starting with 1:00.0, 2:00.0, etc.
- total_distance_m = meters from SUMMARY ROW only
- total_time = time from SUMMARY ROW (e.g. "5:00.0")
- avg_split = /500m from SUMMARY ROW only
- avg_spm = s/m from SUMMARY ROW only
- splits array = the SPLIT ROWS only (1:00, 2:00, 3:00, 4:00, 5:00)

Example for L. Groll photo (1144m total, avg split 2:11.1):
{{
  "last_name": "Groll",
  "first_name": "L",
  "date": "2026-01-19",
  "workout_type": "5:00",
  "piece_number": 1,
  "pieces_total": 1,
  "total_distance_m": 1144,
  "total_time": "5:00.0",
  "avg_split": "2:11.1",
  "avg_spm": 30,
  "splits": [
    {{"interval": "0:00-1:00", "distance_m": 241, "split": "2:04.4", "spm": 30}},
    {{"interval": "1:00-2:00", "distance_m": 236, "split": "2:07.1", "spm": 29}},
    {{"interval": "2:00-3:00", "distance_m": 223, "split": "2:14.5", "spm": 30}},
    {{"interval": "3:00-4:00", "distance_m": 218, "split": "2:17.6", "spm": 29}},
    {{"interval": "4:00-5:00", "distance_m": 227, "split": "2:12.1", "spm": 32}}
  ],
  "notes": ""
}}

Now read the actual photo and return the correct JSON. Return ONLY valid JSON, no other text."""

    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1500,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_data}},
                {"type": "text", "text": prompt}
            ]
        }]
    )

    raw = response.content[0].text.strip()
    if "```" in raw:
        parts = raw.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                raw = part
                break

    data = json.loads(raw)
    log.info(f"  Read: {data.get('last_name')}, {data.get('first_name')} | {data.get('date')} | {data.get('workout_type')} | avg {data.get('avg_split')} | {data.get('total_distance_m')}m")
    return data

# ─── GOOGLE SHEETS ─────────────────────────────────────────────────────────────

def get_sheets_service():
    creds = Credentials.from_service_account_file(
        CREDENTIALS_FILE,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    return build("sheets", "v4", credentials=creds).spreadsheets()

def append_to_sheet(data, photo_filename):
    sheets = get_sheets_service()

    splits = data.get("splits") or []
    split_cols = []
    for i in range(5):
        if i < len(splits):
            split_cols.append(splits[i].get("split") or "")
            split_cols.append(splits[i].get("spm") or "")
        else:
            split_cols.extend(["", ""])

    row = [
        data.get("last_name") or "",
        data.get("first_name") or "",
        data.get("date") or "",
        data.get("workout_type") or "",
        data.get("piece_number") or 1,
        data.get("pieces_total") or 1,
        data.get("total_distance_m") or "",
        data.get("total_time") or "",
        data.get("avg_split") or "",
        data.get("avg_spm") or "",
        *split_cols,
        photo_filename,
        data.get("notes") or "",
    ]

    sheets.values().append(
        spreadsheetId=GOOGLE_SHEET_ID,
        range=f"{SHEET_TAB_NAME}!A:W",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": [row]}
    ).execute()

    log.info(f"  Sheet updated: {data.get('last_name')} | {data.get('date')} | avg {data.get('avg_split')} | {data.get('total_distance_m')}m")

# ─── FILE PROCESSING ───────────────────────────────────────────────────────────

def build_destination(data, original_path):
    date = data.get("date") or "unknown-date"
    name = f"{data.get('last_name', 'Unknown')}-{data.get('first_name', '')}".strip("-")
    piece = data.get("piece_number") or 1
    ext = Path(original_path).suffix.lower()
    filename = f"{date}_{name}_p{piece}{ext}"
    return Path(PROCESSED_FOLDER) / date / filename

def process_image(image_path):
    abs_path = str(Path(image_path).resolve())
    if abs_path in _processing:
        return
    _processing.add(abs_path)

    log.info(f"Processing: {Path(image_path).name}")
    try:
        if not Path(image_path).exists():
            log.warning(f"  File no longer exists, skipping.")
            return

        exif_date = get_exif_date(image_path)
        log.info(f"  EXIF date: {exif_date or 'not found'}")

        data = extract_erg_data(image_path, exif_date)

        dest = build_destination(data, image_path)
        dest.parent.mkdir(parents=True, exist_ok=True)

        if dest.exists():
            dest = dest.parent / f"{dest.stem}_{int(time.time())}{dest.suffix}"

        append_to_sheet(data, dest.name)
        Path(image_path).rename(dest)
        log.info(f"  Done: {dest.name}")

    except json.JSONDecodeError as e:
        log.error(f"  JSON error: {e}")
        move_to_failed(image_path, "json-error")
    except Exception as e:
        log.error(f"  Failed: {e}", exc_info=True)
        move_to_failed(image_path, "error")
    finally:
        _processing.discard(abs_path)

def move_to_failed(image_path, reason):
    try:
        if not Path(image_path).exists():
            return
        failed_dir = Path(FAILED_FOLDER)
        failed_dir.mkdir(parents=True, exist_ok=True)
        p = Path(image_path)
        dest = failed_dir / f"{p.stem}_{reason}_{int(time.time())}{p.suffix}"
        p.rename(dest)
        log.warning(f"  -> Failed: {dest.name}")
    except Exception as e:
        log.error(f"  Could not move to Failed: {e}")

# ─── FOLDER WATCHER ────────────────────────────────────────────────────────────

class ErgPhotoHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() in SUPPORTED_EXTENSIONS:
            abs_path = str(path.resolve())
            if abs_path in _processing:
                return
            log.info(f"New photo: {path.name} — waiting 5s for sync...")
            time.sleep(5)
            process_image(str(path))

# ─── MAIN ──────────────────────────────────────────────────────────────────────

def process_existing_images():
    watch = Path(WATCH_FOLDER)
    images = sorted([
        f for f in watch.iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    ])
    if images:
        log.info(f"Found {len(images)} photo(s) to process.")
        for img in images:
            process_image(str(img))
    else:
        log.info("No photos found — watching for new ones.")

def main():
    log.info("=" * 50)
    log.info("Erg Agent starting...")

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise EnvironmentError("ANTHROPIC_API_KEY is not set.")
    if not Path(CREDENTIALS_FILE).exists():
        raise FileNotFoundError(f"Missing: {CREDENTIALS_FILE}")

    if HEIC_SUPPORTED:
        log.info("HEIC support: enabled")
    else:
        log.warning("HEIC support: NOT available — run: pip install pillow-heif")

    Path(WATCH_FOLDER).mkdir(parents=True, exist_ok=True)
    log.info(f"Watch: {WATCH_FOLDER}")
    log.info(f"Tab:   {SHEET_TAB_NAME}")
    log.info("=" * 50)

    process_existing_images()

    handler = ErgPhotoHandler()
    observer = Observer()
    observer.schedule(handler, WATCH_FOLDER, recursive=False)
    observer.start()
    log.info("Watching for new photos... (Ctrl+C to stop)")

    try:
        while True:
            time.sleep(5)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
    log.info("Erg Agent stopped.")

if __name__ == "__main__":
    main()
