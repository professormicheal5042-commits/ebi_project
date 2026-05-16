from pathlib import Path

p = Path(__file__).resolve().parent / "public/module/add_product/add_product.html"
text = p.read_text(encoding="utf-8")

barcode_panel = """
          <motion class="ocr-panel" id="panelBarcode">
            <motion class="ocr-icon">📊</motion>
            <motion class="ocr-title">Scan Barcode or QR Code</motion>
            <motion class="ocr-desc">Upload a photo of the code or use your camera to detect it.</motion>
            <input type="file" id="barcodeInput" class="ocr-input" accept="image/*" onchange="scanBarcodeFile(this.files)" />
            <video id="barcodeCameraStream" autoplay playsinline></video>
            <canvas id="barcodeCameraCanvas"></canvas>
            <motion class="camera-actions">
              <button type="button" class="btn-ocr" onclick="document.getElementById('barcodeInput').click()">📂 Upload Code Image</button>
              <button type="button" class="btn-ocr" id="btnStartBarcodeCam" onclick="startBarcodeCamera()">▶️ Start Camera</button>
              <button type="button" class="btn-ocr" id="btnCaptureBarcode" onclick="captureAndScanBarcode()" style="display:none">
                <span id="barcodeCaptureText">📸 Capture &amp; Scan Code</span>
                <span id="barcodeCaptureLoading" style="display:none"><span class="spinner"></span> Scanning...</span>
              </button>
              <button type="button" class="btn-ocr-red" id="btnStopBarcodeCam" onclick="stopBarcodeCamera()" style="display:none">⏹ Stop</button>
            </motion>
          </motion>
"""
barcode_panel = (
    barcode_panel.replace("<motion ", "<div ")
    .replace("</motion>", "</motion>")
)
barcode_panel = barcode_panel.replace("</motion>", "</div>")

marker = '        <div class="ocr-divider">Or enter manually</div>'
idx = text.find(marker)
if idx == -1:
    raise SystemExit("marker not found")
insert_at = text.rfind("        </div>", 0, idx)
if insert_at == -1:
    raise SystemExit("closing div not found")
text = text[:insert_at] + barcode_panel + "\n" + text[insert_at:]
p.write_text(text, encoding="utf-8")
print("patched at", insert_at)
