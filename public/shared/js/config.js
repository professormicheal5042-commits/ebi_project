/** Backend API base URL — Vercel. Override locally: window.EBI_API_BASE = 'http://localhost:8000' */
export const API_BASE =
  (typeof window !== "undefined" && window.EBI_API_BASE) ||
  (typeof window !== "undefined" &&
  (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1")
    ? "http://localhost:8000"
    : "https://ebi-project.vercel.app");

export const OCR_API = `${API_BASE}/api/extract-expiry`;
export const BARCODE_SCAN_API = `${API_BASE}/api/scan-barcode`;
export const BARCODE_LOOKUP_API = `${API_BASE}/api/lookup-barcode`;
export const API_HEALTH = `${API_BASE}/api/health`;
