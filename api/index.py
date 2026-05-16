import os
import io
import json
import re
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from fastapi import FastAPI, File, UploadFile, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image

# Load .env locally (Vercel uses dashboard env vars)
ROOT_DIR = Path(__file__).resolve().parent.parent
DOTENV_PATH = ROOT_DIR / ".env"
if DOTENV_PATH.exists():
    with DOTENV_PATH.open("r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value

app = FastAPI(title="EBI OCR API", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

GEMINI_MODELS = ("gemini-2.0-flash", "gemini-1.5-flash")

OFF_CATEGORIES = {
    "en:beverages": "Food",
    "en:snacks": "Food",
    "en:dairy": "Food",
    "en:meats": "Food",
    "en:frozen-foods": "Food",
    "en:plant-based-foods-and-beverages": "Food",
    "en:medicines": "Medicine",
    "en:cosmetics": "Cosmetics",
    "en:cleaning-products": "Household",
}


def _gemini_key() -> str:
    return os.environ.get("GEMINI_API_KEY", "").strip()


def _parse_gemini_json(raw_response: str) -> dict:
    raw_response = re.sub(r"^```(?:json)?\s*", "", raw_response.strip())
    raw_response = re.sub(r"\s*```$", "", raw_response)
    try:
        return json.loads(raw_response)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Gemini returned non-JSON: {raw_response[:200]}",
        ) from exc


def _run_gemini(image_bytes: bytes, prompt: str) -> str:
    import google.generativeai as genai

    api_key = _gemini_key()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="GEMINI_API_KEY is not set. Add it in Vercel → Project → Settings → Environment Variables.",
        )

    genai.configure(api_key=api_key)
    last_error = None

    for model_name in GEMINI_MODELS:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(
                [
                    prompt,
                    {"mime_type": "image/jpeg", "data": image_bytes},
                ]
            )
            text = (response.text or "").strip()
            if text:
                return text
        except Exception as exc:
            last_error = exc
            continue

    raise HTTPException(
        status_code=500,
        detail=f"Gemini Vision error: {last_error}",
    )


async def _read_image_jpeg(file: UploadFile) -> bytes:
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=422, detail="Empty file uploaded.")

    try:
        image = Image.open(io.BytesIO(contents))
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Cannot open image: {exc}") from exc

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


def _try_pyzbar(image_bytes: bytes) -> dict | None:
    try:
        from pyzbar.pyzbar import decode as pyzbar_decode
    except ImportError:
        return None

    try:
        image = Image.open(io.BytesIO(image_bytes))
        codes = pyzbar_decode(image)
        if not codes:
            return None
        first = codes[0]
        barcode = first.data.decode("utf-8", errors="ignore").strip()
        if not barcode:
            return None
        return {
            "barcode": barcode,
            "format": first.type or "UNKNOWN",
            "source": "pyzbar",
        }
    except Exception:
        return None


def _map_off_category(tags: list) -> str:
    for tag in tags or []:
        if tag in OFF_CATEGORIES:
            return OFF_CATEGORIES[tag]
    return "Other"


@app.get("/")
def root():
    return {
        "status": "ok",
        "service": "EBI OCR API",
        "health": "/api/health",
        "extract": "POST /api/extract-expiry",
        "scan_barcode": "POST /api/scan-barcode",
        "lookup_barcode": "GET /api/lookup-barcode?code=...",
        "gemini_configured": bool(_gemini_key()),
    }


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "gemini_configured": bool(_gemini_key()),
    }


@app.post("/api/extract-expiry")
async def extract_expiry(file: UploadFile = File(...)):
    image_bytes = await _read_image_jpeg(file)

    prompt = """You are an AI that reads product labels and packaging.
Analyze this image and extract the following information.
Respond ONLY with a valid JSON object — no markdown, no explanation, just the JSON.

{
  "name": "product name as written on the label, or 'Unknown' if not found",
  "category": "one of: Food, Medicine, Cosmetics, Household, Other",
  "mfg_date": "manufacturing/production date in YYYY-MM-DD format, or 'Not found'",
  "expiry": "expiry/best-before/use-by date in YYYY-MM-DD format, or 'Not found'",
  "raw_text": "all readable text on the label as a single string"
}

Rules:
- For dates like '12/2027' use the last day of that month: '2027-12-31'
- For dates like '15/06/2027' use '2027-06-15'
- Look for labels like: EXP, BEST BEFORE, USE BY, BBE, MFG, MFD, MANUFACTURED, DOM, PROD DATE
- Category must be exactly one of: Food, Medicine, Cosmetics, Household, Other"""

    data = _parse_gemini_json(_run_gemini(image_bytes, prompt))

    return {
        "name": data.get("name", "Unknown"),
        "category": data.get("category", "Other"),
        "expiry": data.get("expiry", "Not found"),
        "mfg_date": data.get("mfg_date", "Not found"),
        "raw_text": data.get("raw_text", ""),
    }


@app.post("/api/scan-barcode")
async def scan_barcode(file: UploadFile = File(...)):
    image_bytes = await _read_image_jpeg(file)

    pyzbar_result = _try_pyzbar(image_bytes)
    if pyzbar_result:
        return {
            **pyzbar_result,
            "raw_text": "",
        }

    prompt = """You are a barcode and QR code reader.
Analyze this image and find any barcode or QR code.
Respond ONLY with a valid JSON object — no markdown, no explanation.

{
  "barcode": "the numeric or alphanumeric code only, or 'Not found' if none visible",
  "format": "symbology e.g. EAN_13, UPC_A, QR_CODE, CODE_128, or 'Unknown'",
  "raw_text": "any other readable text near the code"
}

Rules:
- Return digits/letters of the code only, no spaces unless part of the code
- If multiple codes, return the clearest one
- If no code is visible, set barcode to 'Not found'"""

    data = _parse_gemini_json(_run_gemini(image_bytes, prompt))
    barcode = str(data.get("barcode", "Not found")).strip()

    if barcode.lower() in ("not found", "none", "unknown", ""):
        raise HTTPException(
            status_code=422,
            detail="No barcode detected in image. Try a clearer photo of the code.",
        )

    return {
        "barcode": barcode,
        "format": data.get("format", "Unknown"),
        "raw_text": data.get("raw_text", ""),
        "source": "gemini",
    }


@app.get("/api/lookup-barcode")
def lookup_barcode(code: str = Query(..., min_length=3, max_length=64)):
    clean = re.sub(r"\s+", "", code.strip())
    if not clean:
        raise HTTPException(status_code=422, detail="Barcode code is required.")

    url = f"https://world.openfoodfacts.org/api/v0/product/{clean}.json"
    try:
        with urlopen(url, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Product lookup failed: {exc}",
        ) from exc

    if payload.get("status") != 1:
        return {
            "found": False,
            "barcode": clean,
            "name": None,
            "category": None,
            "brand": None,
        }

    product = payload.get("product") or {}
    name = product.get("product_name") or product.get("product_name_en") or product.get("generic_name")
    brand = product.get("brands")
    tags = product.get("categories_tags") or []

    return {
        "found": bool(name),
        "barcode": clean,
        "name": name,
        "category": _map_off_category(tags),
        "brand": brand,
    }
