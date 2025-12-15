# floating_brush_ocr_final_full.py
# Final integrated tool (Windows) — Lens-like Brush OCR
# - Full-screen screenshot, paint selection, Done -> hide overlay, OCR on background thread
# - Auto-copy OCR result to clipboard (no popup on Done)
# - Handles exponents (10^6 form), superscripts, and roots normalization
# - Draggable floating bubble with menu and Toggle OCR Window (view last OCR)
# Requirements:
#   pip install PyQt5 pillow pytesseract numpy
# Set your Tesseract path below if needed.

import sys, os, tempfile, traceback, re
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt, QRect, QPoint, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QPainter, QColor, QImage, QPixmap, QPen, QPainterPath
from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton, QLabel, QVBoxLayout, QHBoxLayout,
    QSlider, QMessageBox, QFileDialog, QTextEdit
)
from PIL import Image, ImageGrab, ImageOps, ImageEnhance
import numpy as np
import pytesseract

# ---------------- CONFIG ----------------
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
OCR_LANG = "eng+hin"  # change as needed
# ----------------------------------------

ICON_TEXT = "✂"

# ---------- Exponent + root normalization (improved) ----------
_SUPERSCRIPT_MAP = {
    "⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4", "⁵": "5",
    "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9", "⁺": "+", "⁻": "-",
    "⁽": "(", "⁾": ")", "ⁿ": "n", "ᵗ": "t"
}

def normalize_exponents_and_roots(text: str, enable_heuristic: bool = True) -> str:
    """
    Normalize exponent and root notations from OCR output.
    - Converts unicode superscripts to ^N: 10¹² -> 10^12
    - Repairs scientific notation variants: 6.4 x 10 6 -> 6.4 × 10^6
    - Converts √x -> sqrt(x) and ³√8 or 3√8 -> root(3,8)
    """
    if not text:
        return text

    s = text

    # 1) Convert superscript runs to ^digits
    def _sup_repl(m):
        seq = m.group(0)
        mapped = "".join(_SUPERSCRIPT_MAP.get(ch, "") for ch in seq)
        return "^" + mapped if mapped else seq

    s = re.sub(r"[⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁽⁾ⁿᵗ]+", _sup_repl, s)

    # 2) Tidy caret spacing/braces
    s = re.sub(r"\^\s*\{\s*([0-9+-]+)\s*\}", r"^\1", s)
    s = re.sub(r"\^\s*\(\s*([0-9+-]+)\s*\)", r"^\1", s)
    s = re.sub(r"\^\s+([0-9]+)", r"^\1", s)

    # 3) Handle scientific notation: 6.4 x 10^6, 6.4 x 10 6, etc.
    # Ensure we map common separators to a consistent "× 10" prefix and caret exponent
    # First, normalize patterns where exponent is immediately superscript (e.g., 6.4 x 10⁶)
    s = re.sub(
        r"(\d+(?:\.\d+)?)\s*[x×*]\s*10\s*([⁰¹²³⁴⁵⁶⁷⁸⁹]+)",
        lambda m: f"{m.group(1)} × 10^{''.join(_SUPERSCRIPT_MAP.get(ch,'') for ch in m.group(2))}",
        s
    )
    # Patterns like "6.4 x 10 6" or "6.4 x 10   6"
    s = re.sub(
        r"(\d+(?:\.\d+)?)\s*[x×*]\s*10\s+([0-9]{1,4})",
        lambda m: f"{m.group(1)} × 10^{m.group(2)}",
        s
    )
    # If someone used plain "6.4 10 6" (caret totally lost) be conservative: only convert "10 n" after a decimal or digit
    if enable_heuristic:
        s = re.sub(
            r"(\d+(?:\.\d+)?)\s+10\s+([0-9]{1,4})",
            lambda m: f"{m.group(1)} × 10^{m.group(2)}",
            s
        )

    # 4) Scientific 'e' notation spacing fixes: "1 e 12" -> "1e12"
    s = re.sub(r"\b([0-9]+(?:\.[0-9]+)?)\s*[eE]\s+([0-9]{1,4})\b", r"\1e\2", s)

    # 5) Normalize stray double carets or spaces around caret
    s = re.sub(r"\s*\^\s*\^\s*", "^", s)
    s = re.sub(r"\s*\^\s*", "^", s)

    # 6) Roots handling:
    # Superscript before √: ³√8 -> root(3,8)
    def _nth_root_sup_repl(m):
        sup = m.group("sup")
        mapped = "".join(_SUPERSCRIPT_MAP.get(ch, "") for ch in sup)
        return f"root({mapped},"

    s = re.sub(r"(?P<sup>[⁰¹²³⁴⁵⁶⁷⁸⁹])√\s*\(?", _nth_root_sup_repl, s)
    # Digit before √: 3√8 or 3 √ 8 -> root(3,8) (conservative only single-digit root)
    s = re.sub(r"\b([2-9])\s*√\s*\(?\s*([A-Za-z0-9\.\-_\{\}\^\+\(\)]+)\s*\)?",
               lambda m: f"root({m.group(1)},{m.group(2)})", s)
    # Plain square root: √(x) or √x -> sqrt(x)
    s = re.sub(r"√\s*\(\s*([^\)]+)\s*\)", r"sqrt(\1)", s)
    s = re.sub(r"√\s*([A-Za-z0-9\.\-_\{\}\^\+\(\)]+)", r"sqrt(\1)", s)
    s = re.sub(r"\bsq\s*rt\b\s*\(?\s*([A-Za-z0-9\.\-_\{\}\^\+\(\)]+)\s*\)?", r"sqrt(\1)", s, flags=re.IGNORECASE)
    s = re.sub(r"\bsqrt\s*\(?\s*([A-Za-z0-9\.\-_\{\}\^\+\(\)]+)\s*\)?", r"sqrt(\1)", s, flags=re.IGNORECASE)

    # 7) Final cleanup
    s = re.sub(r"[ \t]{2,}", " ", s).strip()

    return s

# ---------- OCR preprocessing ----------
def preprocess_for_ocr(pil_img):
    try:
        if pil_img.mode != "RGBA":
            pil_img = pil_img.convert("RGBA")
        alpha = pil_img.split()[-1]
        gray = ImageOps.grayscale(pil_img)
        white_bg = Image.new("L", gray.size, 255)
        composed = Image.composite(gray, white_bg, alpha)
        composed = ImageOps.autocontrast(composed)
        composed = ImageEnhance.Contrast(composed).enhance(1.4)
        composed = ImageEnhance.Sharpness(composed).enhance(1.1)
        max_side = max(composed.size)
        if max_side < 1000:
            scale = max(1, int(1000 / max_side))
            composed = composed.resize((composed.width * scale, composed.height * scale), Image.LANCZOS)
        return composed
    except Exception:
        return pil_img.convert("L")

# ---------- OCR Worker (background) ----------
class OCRWorker(QThread):
    finished_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)

    def __init__(self, pil_image):
        super().__init__()
        self.pil_image = pil_image

    def run(self):
        try:
            proc = preprocess_for_ocr(self.pil_image)
            text = pytesseract.image_to_string(proc, lang=OCR_LANG, config="--oem 3 --psm 6")
            self.finished_signal.emit(text)
        except Exception as e:
            self.error_signal.emit(str(e))

# ---------- Toast ----------
class Toast(QWidget):
    def __init__(self, message, timeout_ms=1400, parent=None):
        super().__init__(parent, Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowFlag(Qt.WindowDoesNotAcceptFocus)
        self.setFixedSize(240, 56)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        label = QLabel(message, self)
        label.setStyleSheet("color:white; font-weight:600;")
        layout.addWidget(label, alignment=Qt.AlignCenter)
        self.setStyleSheet("background: rgba(10,10,12,0.92); border-radius:8px;")
        screen = QApplication.primaryScreen().geometry()
        margin = 20
        self.move(screen.width() - self.width() - margin, margin + 40)
        QTimer.singleShot(timeout_ms, self.close)

# ---------- Processing dialog ----------
class ProcessingDialog(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(240, 90)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12,12,12,12)
        lbl = QLabel("Processing OCR...\nRunning in background")
        lbl.setStyleSheet("color:white;")
        layout.addWidget(lbl, alignment=Qt.AlignCenter)
        self.setStyleSheet("background: rgba(10,10,12,0.92); border-radius:8px; color:white;")
        screen = QApplication.primaryScreen().geometry()
        self.move((screen.width() - self.width()) // 2, (screen.height() - self.height()) // 2)

# ---------- OCR viewer dialog ----------
class OCRResultDialog(QtWidgets.QDialog):
    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle("Last OCR Result")
        self.resize(700, 420)
        layout = QVBoxLayout(self)
        self.textedit = QTextEdit(); self.textedit.setPlainText(text)
        layout.addWidget(self.textedit)
        row = QHBoxLayout()
        btn_copy = QPushButton("Copy"); btn_copy.clicked.connect(self.copy); row.addWidget(btn_copy)
        btn_save = QPushButton("Save as .txt"); btn_save.clicked.connect(self.save_txt); row.addWidget(btn_save)
        btn_close = QPushButton("Close"); btn_close.clicked.connect(self.close); row.addWidget(btn_close)
        layout.addLayout(row)

    def set_text(self, t: str):
        self.textedit.setPlainText(t or "")

    def copy(self):
        QApplication.clipboard().setText(self.textedit.toPlainText())
        QMessageBox.information(None, "Copied", "Text copied to clipboard.")

    def save_txt(self):
        path, _ = QFileDialog.getSaveFileName(None, "Save text", "ocr_result.txt", "Text Files (*.txt)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.textedit.toPlainText())
            QMessageBox.information(None, "Saved", f"Saved to {path}")

# ---------- Done button ----------
class DoneButton(QWidget):
    clicked = pyqtSignal()
    def __init__(self):
        super().__init__(None, Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(80,36)
        btn = QPushButton("Done", self); btn.setFixedSize(80,36)
        btn.setStyleSheet("QPushButton{background:#10b981;color:white;border-radius:6px;padding:6px}")
        btn.clicked.connect(self.clicked.emit)

# ---------- Paint overlay ----------
class PaintOverlay(QWidget):
    selection_ready = pyqtSignal(QImage, QRect)
    done_requested = pyqtSignal(QImage, QRect, str)
    closed = pyqtSignal()

    def __init__(self, brush_size=36, screenshot_path=None):
        super().__init__(None, Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground); self.setMouseTracking(True)
        self.brush_size = brush_size; self.drawing = False; self.last_pos = None
        self.screenshot_path = screenshot_path
        screen = QApplication.primaryScreen(); rect = screen.geometry(); self.setGeometry(rect)
        w, h = rect.width(), rect.height()
        if screenshot_path and os.path.exists(screenshot_path):
            self.bg_pix = QPixmap(screenshot_path).scaled(w, h)
        else:
            self.bg_pix = QPixmap(w, h); self.bg_pix.fill(QColor(255,255,255))
        self.mask = QImage(w, h, QImage.Format_RGBA8888); self.mask.fill(Qt.transparent)
        self.cursor_pos = QPoint(-1, -1)
        self._last_mask = None; self._last_bbox = None
        self.hint = QLabel("Left-drag paint. Right-drag erase. Enter/Done to OCR. Esc to cancel.", self)
        self.hint.setStyleSheet("color:white; background: rgba(0,0,0,0.45); padding:6px; border-radius:6px;")
        self.hint.move(18, 40)
        self.setAttribute(Qt.WA_OpaquePaintEvent, False)

    def set_screenshot(self, path):
        self.screenshot_path = path
        if path and os.path.exists(path):
            screen = QApplication.primaryScreen(); rect = screen.geometry()
            w, h = rect.width(), rect.height()
            self.bg_pix = QPixmap(path).scaled(w, h)
            self.update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.closed.emit(); self.close()
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.trigger_done()

    def mousePressEvent(self, event):
        if event.buttons() & Qt.LeftButton or event.buttons() & Qt.RightButton:
            self.drawing = True; self.last_pos = event.pos()
            self._paint_point(self.last_pos, left=(event.button()==Qt.LeftButton))

    def mouseMoveEvent(self, event):
        self.cursor_pos = event.pos()
        if self.drawing and self.last_pos:
            left = bool(event.buttons() & Qt.LeftButton)
            self._paint_line(self.last_pos, event.pos(), left=left); self.last_pos = event.pos()
        self.update()

    def mouseReleaseEvent(self, event):
        self.drawing = False; self.last_pos = None; self._emit_selection_ready()

    def _paint_point(self, pos: QPoint, left=True):
        painter = QPainter(self.mask); painter.setRenderHint(QPainter.Antialiasing)
        if left:
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            pen = QPen(QColor(255,255,255,230), self.brush_size, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        else:
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            pen = QPen(QColor(0,0,0,0), self.brush_size, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen); painter.drawPoint(pos); painter.end()

    def _paint_line(self, a: QPoint, b: QPoint, left=True):
        painter = QPainter(self.mask); painter.setRenderHint(QPainter.Antialiasing)
        if left:
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            pen = QPen(QColor(255,255,255,230), self.brush_size, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        else:
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            pen = QPen(QColor(0,0,0,0), self.brush_size, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen); path = QPainterPath(); path.moveTo(a); path.lineTo(b); painter.drawPath(path); painter.end(); self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self.bg_pix)
        overlay_pix = QPixmap(self.bg_pix.size()); overlay_pix.fill(QColor(0,0,0,140))
        mask_pix = QPixmap.fromImage(self.mask)
        mask_painter = QPainter(overlay_pix); mask_painter.setCompositionMode(QPainter.CompositionMode_DestinationOut)
        mask_painter.drawPixmap(0, 0, mask_pix); mask_painter.end()
        painter.drawPixmap(0, 0, overlay_pix)
        if self.cursor_pos.x() >= 0:
            painter.setPen(QPen(QColor(255,255,255,160), 2)); painter.setBrush(Qt.NoBrush)
            radius = max(8, self.brush_size // 2); painter.drawEllipse(self.cursor_pos, radius, radius)
        painter.end()

    def _emit_selection_ready(self):
        w, h = self.mask.width(), self.mask.height()
        ptr = self.mask.bits(); ptr.setsize(self.mask.byteCount())
        arr = np.frombuffer(ptr, dtype=np.uint8).reshape((h, w, 4))
        alpha = arr[:, :, 3]
        ys, xs = np.nonzero(alpha > 10)
        if len(xs) == 0: return
        minx, maxx = int(xs.min()), int(xs.max()); miny, maxy = int(ys.min()), int(ys.max())
        pad = max(4, int(self.brush_size * 0.6)); minx = max(0, minx - pad); miny = max(0, miny - pad)
        maxx = min(w - 1, maxx + pad); maxy = min(h - 1, maxy + pad)
        bbox = QRect(minx, miny, maxx - minx + 1, maxy - miny + 1)
        self._last_mask = self.mask.copy(); self._last_bbox = bbox
        self.selection_ready.emit(self._last_mask, bbox)

    def trigger_done(self):
        w, h = self.mask.width(), self.mask.height()
        ptr = self.mask.bits(); ptr.setsize(self.mask.byteCount())
        arr = np.frombuffer(ptr, dtype=np.uint8).reshape((h, w, 4))
        alpha = arr[:, :, 3]
        ys, xs = np.nonzero(alpha > 10)
        if len(xs) == 0:
            QMessageBox.information(None, "No selection", "Paint a region first.")
            return
        minx, maxx = int(xs.min()), int(xs.max()); miny, maxy = int(ys.min()), int(ys.max())
        pad = max(4, int(self.brush_size * 0.6)); minx = max(0, minx - pad); miny = max(0, miny - pad)
        maxx = min(w - 1, maxx + pad); maxy = min(h - 1, maxy + pad)
        bbox = QRect(minx, miny, maxx - minx + 1, maxy - miny + 1)
        self._last_mask = self.mask.copy(); self._last_bbox = bbox
        self.done_requested.emit(self._last_mask, bbox, self.screenshot_path)

    def clear_mask(self):
        self.mask.fill(Qt.transparent); self.update()

# ---------- Floating bubble (controller) ----------
class FloatingBubble(QWidget):
    def __init__(self):
        super().__init__(None, Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(66, 66)
        self._drag_pos = None
        self._dragging = False

        self.brush_size = 36
        self.overlay = None
        self._temp_screenshot = None
        self._done_btn = None
        self._processing = None
        self._ocr_worker = None
        self._last_text = ""
        self._ocr_dialog = None

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6,6,6,6)
        self.btn = QPushButton(ICON_TEXT, self)
        self.btn.setFixedSize(56,56)
        self.btn.setCursor(Qt.OpenHandCursor)
        self.btn.setToolTip("Click to open menu — drag to move")
        self.btn.setStyleSheet("""
            QPushButton { border-radius:28px;
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #06b6d4, stop:1 #34d399);
                color: #012; font-weight:700; font-size:20px; }
        """)
        layout.addWidget(self.btn, alignment=Qt.AlignCenter)
        self.btn.clicked.connect(self.toggle_menu)
        self.btn.installEventFilter(self)
        self.menu = MenuWindow(self); self.menu.hide()

    def eventFilter(self, obj, event):
        if obj is self.btn:
            if event.type() == QtCore.QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
                self._dragging = True
                self.btn.setCursor(Qt.ClosedHandCursor)
                return False
            elif event.type() == QtCore.QEvent.MouseMove and self._dragging and (event.buttons() & Qt.LeftButton):
                self.move(event.globalPos() - self._drag_pos)
                return True
            elif event.type() in (QtCore.QEvent.MouseButtonRelease, QtCore.QEvent.Leave):
                if self._dragging:
                    self._dragging = False
                    self._drag_pos = None
                    self.btn.setCursor(Qt.OpenHandCursor)
                return False
        return super().eventFilter(obj, event)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPos() - self.frameGeometry().topLeft()
            self._dragging = True
            e.accept()

    def mouseMoveEvent(self, e):
        if self._dragging and (e.buttons() & Qt.LeftButton):
            self.move(e.globalPos() - self._drag_pos)
            e.accept()

    def mouseReleaseEvent(self, e):
        self._dragging = False
        self._drag_pos = None
        self.btn.setCursor(Qt.OpenHandCursor)

    def toggle_menu(self):
        if self.menu.isVisible():
            self.menu.hide()
        else:
            pos = QtGui.QCursor.pos()
            self.menu.move(pos + QPoint(12,12))
            self.menu.show()

    def start_select(self):
        try:
            fd, tmp = tempfile.mkstemp(prefix="lens_shot_", suffix=".png")
            os.close(fd)
            img = ImageGrab.grab(all_screens=True)
            img.save(tmp)
            self._temp_screenshot = tmp
        except Exception as e:
            QMessageBox.critical(None, "Screenshot failed", f"Could not take screenshot:\n{e}")
            return

        if self._done_btn is None:
            self._done_btn = DoneButton()
            self._done_btn.hide()

        if self.overlay is None:
            self.overlay = PaintOverlay(self.brush_size, screenshot_path=self._temp_screenshot)
            self.overlay.selection_ready.connect(self.on_selection_ready)
            self.overlay.done_requested.connect(self._on_done_hide_overlay_and_start_ocr)
            self.overlay.closed.connect(self._on_overlay_closed_delete_temp)
            self.overlay.showFullScreen()
            self.menu.hide()
            self._done_btn.clicked.connect(lambda: self.overlay.trigger_done())
        else:
            self.overlay.set_screenshot(self._temp_screenshot)
            self.overlay.raise_()
            self.overlay.activateWindow()

    def on_selection_ready(self, mask_qimage: QImage, bbox: QRect):
        if self._done_btn is None: return
        screen_geom = QApplication.primaryScreen().geometry()
        px = bbox.x() + bbox.width() + 8
        py = bbox.y()
        if px + self._done_btn.width() > screen_geom.width():
            px = max(8, bbox.x() - self._done_btn.width() - 8)
        if py + self._done_btn.height() > screen_geom.height():
            py = max(8, screen_geom.height() - self._done_btn.height() - 8)
        self._done_btn.move(px, py)
        self._done_btn.show()
        self._done_btn.raise_()

    def _on_done_hide_overlay_and_start_ocr(self, mask_qimage: QImage, bbox: QRect, screenshot_path: str):
        try:
            pil_full = Image.open(screenshot_path).convert("RGBA")
            x, y, w, h = bbox.x(), bbox.y(), bbox.width(), bbox.height()
            crop = pil_full.crop((x, y, x + w, y + h))
            mask_crop = mask_qimage.copy(x, y, w, h)
            ptr = mask_crop.bits(); ptr.setsize(mask_crop.byteCount())
            arr = np.frombuffer(ptr, dtype=np.uint8).reshape((mask_crop.height(), mask_crop.width(), 4))
            alpha = arr[:, :, 3]
            from PIL import Image as PilImage
            pil_mask = PilImage.fromarray(alpha).convert("L")
            crop.putalpha(pil_mask)
        except Exception as e:
            QMessageBox.critical(None, "Capture error", f"Failed to crop screenshot: {e}")
            crop = None

        try:
            if self._done_btn:
                self._done_btn.hide()
        except Exception:
            pass
        try:
            if self.overlay:
                self.overlay.hide()
        except Exception:
            pass

        if crop is None:
            self._cleanup_overlay_and_temp()
            return

        self._processing = ProcessingDialog()
        self._processing.show()

        self._ocr_worker = OCRWorker(crop)
        self._ocr_worker.finished_signal.connect(self._on_ocr_finished_auto_copy)
        self._ocr_worker.error_signal.connect(self._on_ocr_error)
        self._ocr_worker.start()

    def _on_ocr_finished_auto_copy(self, text):
        normalized = normalize_exponents_and_roots(text, enable_heuristic=True)
        try:
            QApplication.clipboard().setText(normalized or "")
        except Exception:
            pass
        self._last_text = normalized or ""

        if self._ocr_dialog and self._ocr_dialog.isVisible():
            self._ocr_dialog.set_text(self._last_text)

        if self._processing:
            try: self._processing.close()
            except: pass
            self._processing = None
        Toast("Copied to clipboard ✓").show()
        self._cleanup_overlay_and_temp()

    def _on_ocr_error(self, err):
        if self._processing:
            try: self._processing.close()
            except: pass
            self._processing = None
        QMessageBox.critical(None, "OCR error", f"OCR failed:\n{err}\n\n{traceback.format_exc()}")
        self._cleanup_overlay_and_temp()

    def _cleanup_overlay_and_temp(self):
        try:
            if self.overlay:
                self.overlay.close()
        except Exception:
            pass
        self.overlay = None
        if self._ocr_worker:
            try:
                if self._ocr_worker.isRunning():
                    self._ocr_worker.quit()
                    self._ocr_worker.wait(200)
            except Exception:
                pass
            self._ocr_worker = None
        try:
            if self._temp_screenshot and os.path.exists(self._temp_screenshot):
                os.remove(self._temp_screenshot)
        except Exception:
            pass
        self._temp_screenshot = None
        if self._done_btn:
            try: self._done_btn.hide()
            except: pass

    def _on_overlay_closed_delete_temp(self):
        if self._done_btn:
            try: self._done_btn.hide()
            except: pass
        if self._ocr_worker:
            try:
                if self._ocr_worker.isRunning():
                    self._ocr_worker.quit()
                    self._ocr_worker.wait(200)
            except Exception:
                pass
            self._ocr_worker = None
        try:
            if self._temp_screenshot and os.path.exists(self._temp_screenshot):
                os.remove(self._temp_screenshot)
        except Exception:
            pass
        self._temp_screenshot = None
        self.overlay = None
        if self._processing:
            try: self._processing.close()
            except: pass
            self._processing = None

    # Toggle OCR viewer window
    def toggle_ocr_window(self):
        if self._ocr_dialog and self._ocr_dialog.isVisible():
            try: self._ocr_dialog.close()
            except: pass
            self._ocr_dialog = None
            return
        self._ocr_dialog = OCRResultDialog(self._last_text or "", parent=None)
        self._ocr_dialog.setWindowFlags(self._ocr_dialog.windowFlags() | Qt.WindowStaysOnTopHint)
        self._ocr_dialog.show()
        self._ocr_dialog.raise_()
        self._ocr_dialog.activateWindow()

# ---------- Bubble menu ----------
class MenuWindow(QWidget):
    def __init__(self, parent: FloatingBubble):
        super().__init__(None, Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.parent = parent
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.init_ui()

    def init_ui(self):
        self.setStyleSheet("QWidget#card { background: rgba(18,18,20,0.96); border-radius:8px; }")
        container = QWidget(self); container.setObjectName("card")
        layout = QVBoxLayout(container); layout.setContentsMargins(10,10,10,10); layout.setSpacing(8)

        lbl = QLabel("Lens-like Brush OCR")
        lbl.setStyleSheet("color:white; font-weight:700;")
        layout.addWidget(lbl)

        btn = QPushButton("Start Select (paint)")
        btn.setStyleSheet("background:#06b6d4;padding:8px;border-radius:6px;color:#012;font-weight:600;")
        btn.clicked.connect(lambda: self.parent.start_select())
        layout.addWidget(btn)

        row = QHBoxLayout()
        row.addWidget(QLabel("Brush size:"))
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(6); self.slider.setMaximum(160); self.slider.setValue(self.parent.brush_size)
        self.slider.valueChanged.connect(self.on_slider)
        row.addWidget(self.slider)
        layout.addLayout(row)

        btn_toggle_view = QPushButton("Toggle OCR Window (open/close)")
        btn_toggle_view.setStyleSheet("padding:6px; border-radius:6px;")
        btn_toggle_view.clicked.connect(self.parent.toggle_ocr_window)
        layout.addWidget(btn_toggle_view)

        btn_clear = QPushButton("Clear last OCR")
        btn_clear.clicked.connect(self.on_clear_last)
        layout.addWidget(btn_clear)

        self.setFixedSize(340, 230)
        wrapper = QVBoxLayout(self); wrapper.setContentsMargins(0,0,0,0); wrapper.addWidget(container)

    def on_slider(self, v):
        self.parent.brush_size = v

    def on_clear_last(self):
        self.parent._last_text = ""
        QMessageBox.information(self, "Cleared", "Last OCR text cleared.")

# ---------- main ----------
def main():
    app = QApplication(sys.argv)
    # Prevent Qt from quitting when last window closes (bubble keeps running)
    app.setQuitOnLastWindowClosed(False)

    bubble = FloatingBubble()
    screen = QApplication.primaryScreen().geometry()
    bubble.move(screen.width() - 120, 100)
    bubble.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
