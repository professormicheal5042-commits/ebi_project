import os
import io
import json
import re
from pathlib import Path
from html import unescape
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import FastAPI, File, UploadFile, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image

# Load .env locally (Render uses dashboard env vars)
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

app = FastAPI(title="EBI OCR API", version="1.1.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Unversioned names (e.g. gemini-1.5-flash) return 404 on v1beta — use current stable IDs.
_DEFAULT_GEMINI_MODELS = (
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-flash-latest",
)


def _gemini_models() -> tuple[str, ...]:
    override = os.environ.get("GEMINI_MODEL", "").strip()
    if override:
        return (override, *_DEFAULT_GEMINI_MODELS)
    return _DEFAULT_GEMINI_MODELS

_URL_PATTERN = re.compile(r"^https?://", re.IGNORECASE)
_FETCH_USER_AGENT = (
    "Mozilla/5.0 (compatible; EBI-Product-Bot/1.0; +https://ebi-project.onrender.com)"
)

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
            detail="GEMINI_API_KEY is not set. Add it in Render Dashboard → Environment Variables.",
        )

    genai.configure(api_key=api_key)
    errors: list[str] = []

    for model_name in _gemini_models():
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
            errors.append(f"{model_name}: empty response")
        except Exception as exc:
            errors.append(f"{model_name}: {exc}")
            continue

    raise HTTPException(
        status_code=500,
        detail="Gemini Vision failed for all models. " + " | ".join(errors[-3:]),
    )


def _run_gemini_text(prompt: str) -> str:
    import google.generativeai as genai

    api_key = _gemini_key()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="GEMINI_API_KEY is not set. Add it in Render Dashboard → Environment Variables.",
        )

    genai.configure(api_key=api_key)
    errors: list[str] = []

    for model_name in _gemini_models():
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            text = (response.text or "").strip()
            if text:
                return text
            errors.append(f"{model_name}: empty response")
        except Exception as exc:
            errors.append(f"{model_name}: {exc}")
            continue

    raise HTTPException(
        status_code=500,
        detail="Gemini text extraction failed. " + " | ".join(errors[-3:]),
    )


def _html_to_text(html: str, max_chars: int = 14000) -> str:
    cleaned = re.sub(r"<script[^>]*>[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
    cleaned = re.sub(r"<style[^>]*>[\s\S]*?</style>", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<noscript[^>]*>[\s\S]*?</noscript>", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = unescape(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:max_chars]


def _fetch_url_text(url: str, timeout: int = 15) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": _FETCH_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as resp:
            raw = resp.read(512_000)
            charset = resp.headers.get_content_charset() or "utf-8"
    except HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Could not open QR link (HTTP {exc.code}): {url}",
        ) from exc
    except (URLError, TimeoutError) as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Could not open QR link: {exc}",
        ) from exc

    try:
        html = raw.decode(charset, errors="replace")
    except LookupError:
        html = raw.decode("utf-8", errors="replace")

    text = _html_to_text(html)
    if not text:
        raise HTTPException(
            status_code=422,
            detail="The QR link opened but the page had no readable text to extract.",
        )
    return text


def _extract_product_from_webpage(url: str, page_text: str) -> dict:
    prompt = f"""You extract structured product details from a product web page.
The user scanned a QR code (grid pattern) that links to this URL:
{url}

Page text (may be truncated):
\"\"\"
{page_text}
\"\"\"

Respond ONLY with a valid JSON object — no markdown:
{{
  "name": "product name as shown on the page, or 'Unknown'",
  "category": "one of: Food, Medicine, Cosmetics, Household, Other",
  "mfg_date": "manufacturing date YYYY-MM-DD, or 'Not found'",
  "expiry": "expiry/best-before/use-by date YYYY-MM-DD, or 'Not found'",
  "barcode": "GTIN/EAN/UPC digits only if visible, or 'Not found'",
  "brand": "brand name or null",
  "raw_text": "short summary of key product facts from the page"
}}

Rules:
- Prefer explicit dates on the page; normalize to YYYY-MM-DD
- For month/year only use last day of month
- category must be exactly one of the five allowed values"""

    data = _parse_gemini_json(_run_gemini_text(prompt))
    return {
        "name": data.get("name", "Unknown"),
        "category": data.get("category", "Other"),
        "mfg_date": data.get("mfg_date", "Not found"),
        "expiry": data.get("expiry", "Not found"),
        "barcode": data.get("barcode", "Not found"),
        "brand": data.get("brand"),
        "raw_text": data.get("raw_text", ""),
    }


def _decode_code_from_image(image_bytes: bytes) -> tuple[str, str, str]:
    pyzbar_result = _try_pyzbar(image_bytes)
    if pyzbar_result:
        return (
            pyzbar_result["barcode"],
            pyzbar_result.get("format", "UNKNOWN"),
            pyzbar_result.get("source", "pyzbar"),
        )

    prompt = """You are a barcode and QR code reader (including grid-style Data Matrix / QR codes).
Analyze this image and find the encoded payload.
Respond ONLY with valid JSON — no markdown.

{
  "barcode": "decoded payload: URL, GTIN, or alphanumeric code, or 'Not found'",
  "format": "symbology e.g. QR_CODE, DATA_MATRIX, EAN_13, or 'Unknown'"
}

Rules:
- For QR codes, return the full URL if present (https://...)
- Return digits/letters only for linear barcodes
- If multiple codes, return the clearest one"""

    data = _parse_gemini_json(_run_gemini(image_bytes, prompt))
    payload = str(data.get("barcode", "Not found")).strip()
    if payload.lower() in ("not found", "none", "unknown", ""):
        raise HTTPException(
            status_code=422,
            detail="No QR or barcode detected in image. Crop tightly around the grid code.",
        )
    return payload, str(data.get("format", "Unknown")), "gemini"


def _lookup_off_product(code: str) -> dict:
    clean = re.sub(r"\s+", "", code.strip())
    url = f"https://world.openfoodfacts.org/api/v0/product/{clean}.json"
    try:
        with urlopen(url, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (URLError, TimeoutError, json.JSONDecodeError):
        return {"found": False, "barcode": clean}

    if payload.get("status") != 1:
        return {"found": False, "barcode": clean}

    product = payload.get("product") or {}
    name = (
        product.get("product_name")
        or product.get("product_name_en")
        or product.get("generic_name")
    )
    tags = product.get("categories_tags") or []
    return {
        "found": bool(name),
        "barcode": clean,
        "name": name,
        "category": _map_off_category(tags),
        "brand": product.get("brands"),
    }


def _parse_gs1(payload: str) -> dict:
    """Parse GS1 Application Identifiers from barcode data.
    Handles formats like: (01)89080009...(17)280430(10)T72601(21)OLAPLEZA-5
    """
    result = {}
    matches = re.findall(r'\((\d{2,4})\)([^(]*)', payload)
    if not matches:
        return result

    for ai, value in matches:
        value = value.strip()
        if ai == '01':
            result['gtin'] = re.sub(r'\D', '', value)
        elif ai == '10':
            result['batch'] = value
        elif ai == '11':
            result['mfg_date'] = _gs1_date(value)
        elif ai == '15':
            result['expiry'] = _gs1_date(value)
        elif ai == '17':
            result['expiry'] = _gs1_date(value)
        elif ai == '21':
            result['serial'] = value
    return result


def _gs1_date(raw: str) -> str:
    """Convert GS1 YYMMDD to YYYY-MM-DD."""
    raw = re.sub(r'\D', '', raw.strip())
    if len(raw) < 6:
        return "Not found"
        
    if len(raw) == 8 and (raw.startswith('20') or raw.startswith('19')):
        year = int(raw[:4])
        mm = raw[4:6]
        dd = raw[6:8]
    else:
        yy = int(raw[:2])
        mm = raw[2:4]
        dd = raw[4:6]
        year = 2000 + yy if yy < 50 else 1900 + yy
        
    if dd == '00':
        import calendar
        dd = str(calendar.monthrange(year, int(mm))[1]).zfill(2)
    return f"{year}-{mm}-{dd}"


def _enrich_payload(payload: str) -> dict:
    if _URL_PATTERN.match(payload):
        page_text = _fetch_url_text(payload)
        extracted = _extract_product_from_webpage(payload, page_text)
        barcode = extracted.get("barcode", "Not found")
        clean_barcode = re.sub(r"\D", "", str(barcode)) if barcode not in (
            "Not found",
            "",
            None,
        ) else ""
        if clean_barcode and len(clean_barcode) >= 8:
            off = _lookup_off_product(clean_barcode)
            if off.get("found"):
                if not extracted.get("name") or extracted.get("name") == "Unknown":
                    extracted["name"] = off.get("name")
                if extracted.get("category") in (None, "Other") and off.get("category"):
                    extracted["category"] = off.get("category")
                if not extracted.get("brand"):
                    extracted["brand"] = off.get("brand")
        return {
            **extracted,
            "payload": payload,
            "url": payload,
            "enrichment": "web_scrape",
        }

    # ── Try GS1 parsing (pharmaceutical / industrial QR codes) ──
    gs1 = _parse_gs1(payload)
    if gs1:
        gtin = gs1.get('gtin', '')
        expiry = gs1.get('expiry', 'Not found')
        mfg_date = gs1.get('mfg_date', 'Not found')
        batch = gs1.get('batch', '')
        serial = gs1.get('serial', '')

        # Look up product name from GTIN on OpenFoodFacts
        name = 'Unknown'
        category = 'Other'
        brand = None
        if gtin and len(gtin) >= 8:
            off = _lookup_off_product(gtin)
            if off.get('found'):
                name = off.get('name') or 'Unknown'
                category = off.get('category') or 'Other'
                brand = off.get('brand')

        # If OFF didn't find it, ask Gemini to identify the product
        if name == 'Unknown':
            try:
                prompt = f"""Identify this product from its scanned barcode/QR data.
Raw scanned data: "{payload}"
GTIN: {gtin or 'unknown'}
Serial: {serial or 'unknown'}
Batch: {batch or 'unknown'}

Respond ONLY with valid JSON — no markdown:
{{
  "name": "the product name (your best guess from the serial number, GTIN, or any clue in the data)",
  "category": "one of: Food, Medicine, Cosmetics, Household, Other",
  "brand": "brand/manufacturer name or null"
}}

Rules:
- The serial field often contains the product name (e.g. 'OLAPLEZA-5 MD' means Olapleza 5mg Medicine)
- If the GTIN starts with 890 it is likely an Indian pharmaceutical product
- Make your best guess — never return 'Unknown' if there are any clues"""
                gemini_result = _parse_gemini_json(_run_gemini_text(prompt))
                if gemini_result.get('name') and gemini_result['name'] != 'Unknown':
                    name = gemini_result['name']
                if gemini_result.get('category') and gemini_result['category'] != 'Other':
                    category = gemini_result['category']
                if gemini_result.get('brand'):
                    brand = gemini_result['brand']
            except Exception:
                pass

        return {
            'name': name,
            'category': category,
            'mfg_date': mfg_date,
            'expiry': expiry,
            'barcode': gtin or payload,
            'brand': brand,
            'raw_text': payload,
            'payload': payload,
            'enrichment': 'gs1',
        }

    # ── Plain numeric barcode → OpenFoodFacts lookup ──
    clean = re.sub(r"\s+", "", payload)
    off = _lookup_off_product(clean) if clean.isdigit() and len(clean) >= 8 else {"found": False}
    if off.get("found"):
        return {
            "name": off.get("name") or "Unknown",
            "category": off.get("category") or "Other",
            "mfg_date": "Not found",
            "expiry": "Not found",
            "barcode": clean,
            "brand": off.get("brand"),
            "raw_text": "",
            "payload": payload,
            "enrichment": "openfoodfacts",
        }

    # ── Fallback: send any non-trivial text to Gemini to parse ──
    if len(payload.strip()) > 5:
        try:
            prompt = f"""Extract product details from this scanned barcode/QR data:
"{payload}"

Respond ONLY with valid JSON — no markdown:
{{
  "name": "product name (best guess from the data)",
  "category": "one of: Food, Medicine, Cosmetics, Household, Other",
  "mfg_date": "manufacturing date YYYY-MM-DD or 'Not found'",
  "expiry": "expiry date YYYY-MM-DD or 'Not found'",
  "brand": "brand name or null"
}}"""
            gemini_result = _parse_gemini_json(_run_gemini_text(prompt))
            return {
                'name': gemini_result.get('name', 'Unknown'),
                'category': gemini_result.get('category', 'Other'),
                'mfg_date': gemini_result.get('mfg_date', 'Not found'),
                'expiry': gemini_result.get('expiry', 'Not found'),
                'barcode': clean or payload,
                'brand': gemini_result.get('brand'),
                'raw_text': payload,
                'payload': payload,
                'enrichment': 'gemini_text',
            }
        except Exception:
            pass

    return {
        "name": "Unknown",
        "category": "Other",
        "mfg_date": "Not found",
        "expiry": "Not found",
        "barcode": clean or payload,
        "brand": None,
        "raw_text": "",
        "payload": payload,
        "enrichment": "none",
    }


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
        "scan_qr_product": "POST /api/scan-qr-product",
        "enrich_qr_payload": "POST /api/enrich-qr-payload",
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
  "name": "Extract the primary product name, brand name, or the largest text on the label. Make your absolute best guess. Never return 'Unknown' if there is any readable text. If the text is just a barcode or GS1 string, extract the name from it.",
  "category": "one of: Food, Medicine, Cosmetics, Household, Other",
  "mfg_date": "manufacturing/production date in YYYY-MM-DD format, or 'Not found' if completely absent.",
  "expiry": "expiry/best-before/use-by date in YYYY-MM-DD format, or 'Not found' if completely absent.",
  "raw_text": "all readable text on the label as a single string"
}

Rules:
- You MUST extract a product name. Pick the most prominent text if unsure. NEVER output 'QR Code' or 'Barcode' as the product name.
- If you see a GS1 barcode string like (01)890...(17)20280430...(21)OLAPLEZA-5, the (21) part is the product name, (17) is expiry (YYMMDD), and (11) is mfg date. Extract these correctly!
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


@app.post("/api/scan-qr-product")
async def scan_qr_product(file: UploadFile = File(...)):
    """Decode a grid QR / Data Matrix from an image and enrich from its URL or barcode."""
    image_bytes = await _read_image_jpeg(file)
    payload, code_format, source = _decode_code_from_image(image_bytes)
    enriched = _enrich_payload(payload)

    barcode_value = enriched.get("barcode", payload)
    if isinstance(barcode_value, str) and barcode_value.lower() in ("not found", "unknown", ""):
        barcode_value = re.sub(r"\s+", "", payload) if not _URL_PATTERN.match(payload) else payload

    return {
        "payload": payload,
        "barcode": barcode_value,
        "format": code_format,
        "source": source,
        "url": enriched.get("url"),
        "enrichment": enriched.get("enrichment"),
        "name": enriched.get("name", "Unknown"),
        "category": enriched.get("category", "Other"),
        "expiry": enriched.get("expiry", "Not found"),
        "mfg_date": enriched.get("mfg_date", "Not found"),
        "brand": enriched.get("brand"),
        "raw_text": enriched.get("raw_text", ""),
    }


from fastapi import Form


@app.post("/api/enrich-qr-payload")
async def enrich_qr_payload(payload: str = Form(...)):
    """Enrich an already-decoded QR/barcode string (URL or numeric code) into product details.
    
    Use this when the client-side scanner (e.g. jsQR) has already decoded the QR code text.
    This avoids re-sending the full image and re-decoding it.
    """
    payload = payload.strip()
    if not payload:
        raise HTTPException(status_code=422, detail="payload is required and cannot be empty.")

    enriched = _enrich_payload(payload)

    barcode_value = enriched.get("barcode", payload)
    if isinstance(barcode_value, str) and barcode_value.lower() in ("not found", "unknown", ""):
        barcode_value = re.sub(r"\s+", "", payload) if not _URL_PATTERN.match(payload) else payload

    return {
        "payload": payload,
        "barcode": barcode_value,
        "format": "QR_CODE",
        "source": "client_jsqr",
        "url": enriched.get("url"),
        "enrichment": enriched.get("enrichment"),
        "name": enriched.get("name", "Unknown"),
        "category": enriched.get("category", "Other"),
        "expiry": enriched.get("expiry", "Not found"),
        "mfg_date": enriched.get("mfg_date", "Not found"),
        "brand": enriched.get("brand"),
        "raw_text": enriched.get("raw_text", ""),
    }


@app.post("/api/scan-barcode")
async def scan_barcode(file: UploadFile = File(...)):
    image_bytes = await _read_image_jpeg(file)
    payload, code_format, source = _decode_code_from_image(image_bytes)

    if _URL_PATTERN.match(payload):
        # Reject known non-product generic domains
        bad_domains = ["youtube.com", "youtu.be", "google.com", "facebook.com", "instagram.com", "twitter.com", "x.com"]
        if any(domain in payload.lower() for domain in bad_domains):
            raise HTTPException(
                status_code=422,
                detail=f"The scanned QR code is a generic link ({payload}) and is not a valid product."
            )

        enriched = _enrich_payload(payload)
        barcode_value = enriched.get("barcode", "")
        if isinstance(barcode_value, str) and (barcode_value.lower() in ("not found", "unknown", "") or _URL_PATTERN.match(barcode_value)):
            barcode_value = "" # Do not populate URL into the barcode field

        # If it's a URL and we couldn't extract ANY product name, reject it
        if enriched.get("name") == "Unknown" and not barcode_value:
            raise HTTPException(
                status_code=422,
                detail=f"The scanned QR code URL ({payload}) does not contain recognizable product details."
            )

        return {
            "barcode": barcode_value,
            "format": code_format,
            "source": source,
            "payload": payload,
            "url": payload,
            "enrichment": enriched.get("enrichment"),
            "name": enriched.get("name"),
            "category": enriched.get("category"),
            "expiry": enriched.get("expiry"),
            "mfg_date": enriched.get("mfg_date"),
            "brand": enriched.get("brand"),
            "raw_text": enriched.get("raw_text", ""),
        }

    result = {
        "barcode": re.sub(r"\s+", "", payload),
        "format": code_format,
        "source": source,
        "raw_text": "",
        "payload": payload,
    }

    off = _lookup_off_product(result["barcode"])
    if off.get("found"):
        result["enrichment"] = "openfoodfacts"
        result["name"] = off.get("name")
        result["category"] = off.get("category")
        result["brand"] = off.get("brand")

    return result


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

@app.post("/api/generate-summary")
async def generate_summary(name: str = Form(...), category: str = Form(...)):
    """Generate a detailed summary for a product using Gemini."""
    if not _gemini_key():
        return {"summary": "Detailed AI summary unavailable (Gemini API key missing)."}
        
    try:
        prompt = (
            f"Write a professional, detailed summary for a product named '{name}' "
            f"in the '{category}' category. Include general uses, storage instructions, "
            f"and important warnings or side effects (especially if it is medicine or food). "
            f"Format it as plain text paragraphs without markdown asterisks."
        )
        
        response = _run_gemini(b"", prompt) # no image needed
        if not response:
            return {"summary": "Detailed summary not available."}
            
        return {"summary": response.strip()}
    except Exception as e:
        logger.error(f"Error generating summary: {str(e)}")
        return {"summary": "Detailed summary not available due to an error."}

