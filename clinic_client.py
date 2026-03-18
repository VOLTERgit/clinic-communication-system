"""
Clinic Connect Client — Apple Liquid Glass UI
visionOS-inspired: frosted glass panels, soft gradient mesh background,
Apple Blue accents, translucent surfaces, clean SF-style typography
"""

import sys
import json
import threading
import time
from datetime import datetime
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QScrollArea,
    QFrame, QStackedWidget, QListWidget, QListWidgetItem,
    QSystemTrayIcon, QMenu, QGraphicsDropShadowEffect,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, QRectF
from PyQt6.QtGui import (
    QColor, QIcon, QPixmap, QPainter, QPainterPath,
    QLinearGradient, QRadialGradient, QBrush, QPen,
)
import websocket
import os

# ─── Config ───────────────────────────────────────────────────────────────────

SERVER_PORT = 8765
CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(sys.argv[0])), "clinic_config.json"
)

def load_config():
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except Exception:
        return {}

def save_config(data):
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Config save error: {e}")

def get_server_host():
    return load_config().get("server_ip", "")

# ─── Users ────────────────────────────────────────────────────────────────────

USERS = {
    "dr_anchal":  {"display": "Dr. Anchal Shah",   "role": "doctor",    "password": "Anchal"},
    "dr_diwaker": {"display": "Dr. Diwaker Sharma", "role": "doctor",    "password": "Diwaker"},
    "reception1": {"display": "Reception 1",         "role": "reception", "password": "Krishna"},
    "reception2": {"display": "Reception 2",         "role": "reception", "password": "Mansi"},
    "dhaval":     {"display": "Dhaval",              "role": "photo",     "password": "Dhaval"},
    "vaibhav":    {"display": "Vaibhav",             "role": "photo",     "password": "Vaibhav"},
}
RECEPTIONS  = ["reception1", "reception2"]
DOCTORS     = ["dr_anchal", "dr_diwaker"]
PHOTO_STAFF = ["dhaval", "vaibhav"]

# ─── Design Tokens ────────────────────────────────────────────────────────────

BLUE       = "#0A84FF"
BLUE_SOFT  = "#4DA3FF"
BLUE_PALE  = "#DCEEFF"
GREEN      = "#30D158"
RED        = "#FF453A"
ORANGE     = "#FF9F0A"

TEXT_MAIN  = "#1D1D1F"
TEXT_SEC   = "#6E6E73"
TEXT_LITE  = "#8E8E93"

# ─── Global stylesheet ────────────────────────────────────────────────────────

APP_STYLE = """
QMainWindow, QWidget {
    background: #EAF2FB;
    font-family: 'SF Pro Display', 'Segoe UI', Arial, sans-serif;
    color: #1D1D1F;
}
QScrollArea  { border: none; background: transparent; }
QScrollBar:vertical {
    background: transparent; width: 6px; margin: 4px 2px;
}
QScrollBar::handle:vertical {
    background: rgba(0,0,0,0.14); border-radius: 3px; min-height: 28px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QLabel  { background: transparent; }
QFrame  { border: none; }
"""

# ─── Style helpers ────────────────────────────────────────────────────────────

def input_style():
    return (
        "QLineEdit {"
        " background: rgba(255,255,255,0.75);"
        " border: 1px solid rgba(0,0,0,0.10);"
        " border-radius: 12px;"
        " padding: 11px 16px;"
        " font-size: 14px;"
        f" color: {TEXT_MAIN};"
        "}"
        "QLineEdit:focus {"
        f" border: 1.5px solid {BLUE};"
        " background: rgba(255,255,255,0.95);"
        "}"
    )

def pill_btn(bg=None, hover=None, text="white", radius=12, font_size=14, padding="11px 22px"):
    bg    = bg    or BLUE
    hover = hover or BLUE_SOFT
    return (
        f"QPushButton {{"
        f" background: {bg}; color: {text}; border-radius: {radius}px; border: none;"
        f" padding: {padding}; font-size: {font_size}px; font-weight: 600;"
        f"}}"
        f"QPushButton:hover {{ background: {hover}; }}"
        f"QPushButton:pressed {{ opacity: 0.85; }}"
    )

def ghost_pill(radius=9):
    return (
        f"QPushButton {{"
        f" background: rgba(255,255,255,0.55); color: {TEXT_SEC};"
        f" border: 1px solid rgba(0,0,0,0.09); border-radius: {radius}px;"
        f" padding: 7px 14px; font-size: 12px; font-weight: 500;"
        f"}}"
        f"QPushButton:hover {{"
        f" background: rgba(10,132,255,0.10); color: {BLUE}; border-color: {BLUE}44;"
        f"}}"
    )

def toggle_style(active):
    if active:
        return (
            f"QPushButton {{"
            f" background: {BLUE}; color: white; border-radius: 9px; border: none;"
            f" padding: 7px 16px; font-size: 12px; font-weight: 600;"
            f"}}"
        )
    return (
        f"QPushButton {{"
        f" background: rgba(255,255,255,0.60); color: {TEXT_SEC};"
        f" border: 1px solid rgba(0,0,0,0.09); border-radius: 9px;"
        f" padding: 7px 16px; font-size: 12px;"
        f"}}"
        f"QPushButton:hover {{"
        f" background: {BLUE_PALE}; color: {BLUE}; border-color: {BLUE}44;"
        f"}}"
    )

def tab_style(active):
    if active:
        return (
            f"QPushButton {{"
            f" background: {BLUE}; color: white; border-radius: 8px; border: none;"
            f" padding: 7px 20px; font-size: 13px; font-weight: 600;"
            f"}}"
        )
    return (
        f"QPushButton {{"
        f" background: transparent; color: {TEXT_SEC}; border-radius: 8px;"
        f" padding: 7px 20px; font-size: 13px;"
        f"}}"
        f"QPushButton:hover {{ background: rgba(10,132,255,0.09); color: {BLUE}; }}"
    )

def _shadow(widget, blur=28, dy=8, alpha=32):
    s = QGraphicsDropShadowEffect()
    s.setBlurRadius(blur)
    s.setOffset(0, dy)
    s.setColor(QColor(0, 0, 0, alpha))
    widget.setGraphicsEffect(s)

# ─── Gradient background ──────────────────────────────────────────────────────

class GradientBg(QWidget):
    """Soft blue-white radial mesh. Always sits behind everything."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.lower()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()
        w, h = r.width(), r.height()

        # Solid base first — prevents any black showing through
        p.fillRect(r, QColor("#EAF2FB"))

        # Soft gradient layer
        grad = QLinearGradient(0, 0, w * 0.6, h)
        grad.setColorAt(0.0, QColor("#EAF2FB"))
        grad.setColorAt(0.55, QColor("#E0ECF8"))
        grad.setColorAt(1.0, QColor("#D4E6F4"))
        p.fillRect(r, QBrush(grad))

        # Top-right orb
        o1 = QRadialGradient(w * 0.78, h * 0.12, w * 0.42)
        o1.setColorAt(0.0, QColor(190, 220, 255, 130))
        o1.setColorAt(1.0, QColor(190, 220, 255, 0))
        p.fillRect(r, QBrush(o1))

        # Bottom-left orb
        o2 = QRadialGradient(w * 0.18, h * 0.88, w * 0.38)
        o2.setColorAt(0.0, QColor(215, 235, 255, 100))
        o2.setColorAt(1.0, QColor(215, 235, 255, 0))
        p.fillRect(r, QBrush(o2))
        p.end()

# ─── Glass Card ───────────────────────────────────────────────────────────────

class GlassCard(QFrame):
    """
    Custom-painted frosted glass card.
    All children are placed in a QVBoxLayout inside.
    Usage: card = GlassCard(); layout = QVBoxLayout(card); ...
    """
    def __init__(self, parent=None, radius=20, bg_alpha=158,
                 shadow_blur=32, shadow_y=10, shadow_alpha=30):
        super().__init__(parent)
        self._r = radius
        self._a = bg_alpha
        self.setStyleSheet("QFrame { background: rgba(255,255,255,0); border: none; }")
        _shadow(self, shadow_blur, shadow_y, shadow_alpha)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        path = QPainterPath()
        path.addRoundedRect(0, 0, rect.width(), rect.height(), self._r, self._r)

        # Glass fill
        p.setClipPath(path)
        p.fillPath(path, QColor(255, 255, 255, self._a))

        # Top highlight shimmer
        hi = QLinearGradient(0, 0, 0, min(50, rect.height() // 4))
        hi.setColorAt(0.0, QColor(255, 255, 255, 90))
        hi.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillPath(path, QBrush(hi))

        # Outer border
        p.setClipping(False)
        pen = QPen(QColor(255, 255, 255, 150))
        pen.setWidthF(1.0)
        p.setPen(pen)
        p.drawRoundedRect(
            QRectF(0.5, 0.5, rect.width() - 1.0, rect.height() - 1.0),
            self._r, self._r
        )
        p.end()

# ─── WebSocket Worker ─────────────────────────────────────────────────────────

class WSWorker(QThread):
    # Define signals directly on the QThread subclass — safest approach
    message_received = pyqtSignal(dict)
    connected        = pyqtSignal()
    disconnected     = pyqtSignal()
    presence_updated = pyqtSignal(list)

    def __init__(self, user_id):
        super().__init__()
        self.user_id = user_id
        self.ws = None
        self._running = True
        self._queue = []
        self._lock = threading.Lock()

    def run(self):
        while self._running:
            try:
                url = f"ws://{get_server_host()}:{SERVER_PORT}/ws/{self.user_id}"
                self.ws = websocket.WebSocketApp(
                    url,
                    on_open=self._on_open, on_message=self._on_message,
                    on_error=self._on_error, on_close=self._on_close,
                )
                self.ws.run_forever(
                    ping_interval=15, ping_timeout=10, skip_utf8_validation=True
                )
            except Exception as e:
                print(f"WS: {e}")
            if self._running:
                self.disconnected.emit()
                time.sleep(3)

    def _on_open(self, ws):
        self.connected.emit()
        with self._lock:
            for m in self._queue:
                ws.send(m)
            self._queue.clear()

    def _on_message(self, ws, raw):
        try:
            data = json.loads(raw)
            if data.get("type") == "presence_update":
                self.presence_updated.emit(data.get("online_users", []))
            else:
                self.message_received.emit(data)
        except Exception as e:
            print(f"Parse: {e}")

    def _on_error(self, ws, error): print(f"WS err: {error}")
    def _on_close(self, ws, code, msg): self.disconnected.emit()

    def send(self, data):
        payload = json.dumps(data)
        if self.ws and self.ws.sock and self.ws.sock.connected:
            try:
                self.ws.send(payload); return
            except Exception:
                pass
        with self._lock:
            self._queue.append(payload)

    def stop(self):
        self._running = False
        if self.ws:
            self.ws.close()

# ─── Popup Notification ───────────────────────────────────────────────────────

_active_popups = []

class PopupNotification(QWidget):
    def __init__(self, sender_display, msg_type, content,
                 timestamp, msg_id, ws_worker,
                 original_sender_id=None, offline=False,
                 reply_callback=None):
        super().__init__(None)
        self.msg_id = msg_id
        self.ws_worker = ws_worker
        self.original_sender_id = original_sender_id
        self.reply_callback = reply_callback

        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Window
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setStyleSheet("background: #F0F6FC; border-radius: 20px;")
        self.setWindowTitle("Clinic")
        self.setMinimumWidth(360)
        self._build(sender_display, msg_type, content, timestamp, offline)
        self.adjustSize()
        self._position()

    def _build(self, sender, msg_type, content, timestamp, offline):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)

        type_meta = {
            "doctor_resting":       ("😴", RED,    "Doctor Status"),
            "doctor_wants_patient": ("🏥", GREEN,  "Doctor Status"),
            "photo_request":        ("📸", BLUE,   "Photo Request"),
            "message":              ("💬", BLUE,   "Message"),
        }
        icon, color, label = type_meta.get(msg_type, ("📢", BLUE, "Notification"))

        card = GlassCard(radius=20, bg_alpha=235, shadow_blur=44, shadow_y=14, shadow_alpha=50)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(22, 18, 22, 20)
        cl.setSpacing(10)

        # Header row
        top = QHBoxLayout()
        badge = QLabel(icon)
        badge.setFixedSize(42, 42)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(
            f"background: {color}20; border-radius: 12px; font-size: 20px;"
            f" border: 1.5px solid {color}40;"
        )
        lbl_col = QVBoxLayout(); lbl_col.setSpacing(1)
        type_lbl = QLabel(label.upper())
        type_lbl.setStyleSheet(
            f"font-size: 10px; font-weight: 700; color: {color}; letter-spacing: 1.5px;"
        )
        sender_lbl = QLabel(sender)
        sender_lbl.setStyleSheet(
            f"font-size: 16px; font-weight: 700; color: {TEXT_MAIN};"
        )
        lbl_col.addWidget(type_lbl); lbl_col.addWidget(sender_lbl)
        top.addWidget(badge); top.addSpacing(10)
        top.addLayout(lbl_col); top.addStretch()
        if offline:
            chip = QLabel("Queued")
            chip.setStyleSheet(
                f"background: {ORANGE}20; color: {ORANGE}; border-radius: 8px;"
                f" padding: 3px 9px; font-size: 10px; font-weight: 700;"
                f" border: 1px solid {ORANGE}40;"
            )
            top.addWidget(chip)
        cl.addLayout(top)

        div = QFrame(); div.setFixedHeight(1)
        div.setStyleSheet("background: rgba(0,0,0,0.06);")
        cl.addWidget(div)

        content_lbl = QLabel(content)
        content_lbl.setWordWrap(True)
        content_lbl.setStyleSheet(f"font-size: 14px; color: {TEXT_SEC};")
        cl.addWidget(content_lbl)

        time_lbl = QLabel(timestamp)
        time_lbl.setStyleSheet(f"font-size: 11px; color: {TEXT_LITE};")
        cl.addWidget(time_lbl)

        if msg_type == "message":
            self._reply_input = QLineEdit()
            self._reply_input.setPlaceholderText("Reply…")
            self._reply_input.setStyleSheet(input_style())
            self._reply_input.returnPressed.connect(self._on_reply)
            cl.addWidget(self._reply_input)
            rbtn = QPushButton("↩  Reply")
            rbtn.setStyleSheet(pill_btn(BLUE, BLUE_SOFT, "white", 12, 13, "10px 18px"))
            rbtn.clicked.connect(self._on_reply)
            cl.addWidget(rbtn)
        else:
            self._reply_input = None

        ok_btn = QPushButton("✓  Got it")
        ok_btn.setStyleSheet(
            f"QPushButton {{ background: {color}; color: white; border-radius: 12px;"
            f" border: none; padding: 12px; font-size: 14px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: {color}cc; }}"
        )
        ok_btn.clicked.connect(self._on_ok)
        cl.addWidget(ok_btn)
        outer.addWidget(card)

    def _position(self):
        s = QApplication.primaryScreen().availableGeometry()
        self.move(s.right() - self.width() - 20, s.bottom() - self.height() - 20)

    def _on_ok(self):
        if self.msg_id and self.ws_worker and self.original_sender_id:
            self.ws_worker.send({
                "type": "mark_read", "id": self.msg_id,
                "original_sender": self.original_sender_id,
            })
        self._dismiss()

    def _on_reply(self):
        if not self._reply_input: return
        text = self._reply_input.text().strip()
        if not text:
            self._reply_input.setFocus(); return
        if self.reply_callback:
            self.reply_callback(self.original_sender_id, text)
        if self.msg_id and self.ws_worker and self.original_sender_id:
            self.ws_worker.send({
                "type": "mark_read", "id": self.msg_id,
                "original_sender": self.original_sender_id,
            })
        self._dismiss()

    def _dismiss(self):
        if self in _active_popups:
            _active_popups.remove(self)
        if hasattr(self, '_timer'):
            self._timer.stop()
        self.close()

    def closeEvent(self, event):
        if self in _active_popups:
            event.ignore(); self.raise_(); self.activateWindow()
        else:
            event.accept()

    def show_popup(self):
        _active_popups.append(self)
        self.show(); self.raise_(); self.activateWindow()
        self._timer = QTimer(self)
        self._timer.timeout.connect(
            lambda: (self.raise_(), self.activateWindow()) if self.isVisible() else None
        )
        self._timer.start(2000)

# ─── IP Setup Screen ──────────────────────────────────────────────────────────

class IPSetupScreen(QWidget):
    ip_saved = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._bg = GradientBg(self)
        self._build()

    def resizeEvent(self, event):
        self._bg.setGeometry(0, 0, self.width(), self.height()); super().resizeEvent(event)

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(40, 40, 40, 40)

        card = GlassCard(radius=26, bg_alpha=185, shadow_blur=56, shadow_y=18, shadow_alpha=28)
        card.setMaximumWidth(440)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(42, 38, 42, 42)
        cl.setSpacing(14)

        logo = QLabel("🏥")
        logo.setStyleSheet("font-size: 56px;")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(logo)

        title = QLabel("Clinic Connect")
        title.setStyleSheet(
            f"font-size: 28px; font-weight: 700; color: {TEXT_MAIN}; letter-spacing: -0.5px;"
        )
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(title)

        sub = QLabel("Internal Communication System")
        sub.setStyleSheet(f"font-size: 13px; color: {TEXT_SEC};")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(sub)

        div = QFrame(); div.setFixedHeight(1)
        div.setStyleSheet("background: rgba(0,0,0,0.07); margin: 2px 0;")
        cl.addWidget(div)

        setup_lbl = QLabel("FIRST TIME SETUP")
        setup_lbl.setStyleSheet(
            f"font-size: 10px; font-weight: 700; color: {BLUE}; letter-spacing: 1.5px;"
        )
        cl.addWidget(setup_lbl)

        desc = QLabel("Enter Dhaval's PC IP address.\nYou only need to do this once.")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"font-size: 13px; color: {TEXT_SEC}; line-height: 1.6;")
        cl.addWidget(desc)

        hint = QFrame()
        hint.setStyleSheet(
            f"QFrame {{ background: {BLUE_PALE}; border-radius: 14px;"
            f" border: 1px solid rgba(10,132,255,0.18); }}"
        )
        hl = QVBoxLayout(hint); hl.setContentsMargins(14, 11, 14, 11)
        hint_lbl = QLabel(
            "💡  Dhaval's PC → Command Prompt → ipconfig\n"
            "     Look for IPv4 Address  e.g.  192.168.1.15"
        )
        hint_lbl.setStyleSheet(f"font-size: 12px; color: {BLUE};")
        hl.addWidget(hint_lbl)
        cl.addWidget(hint)

        ip_lbl = QLabel("Server IP Address")
        ip_lbl.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {TEXT_MAIN};")
        cl.addWidget(ip_lbl)

        self.ip_input = QLineEdit()
        self.ip_input.setPlaceholderText("e.g.  192.168.1.15")
        self.ip_input.setStyleSheet(input_style())
        existing = get_server_host()
        if existing:
            self.ip_input.setText(existing)
        self.ip_input.returnPressed.connect(self._save)
        cl.addWidget(self.ip_input)

        self.err_lbl = QLabel("")
        self.err_lbl.setStyleSheet(f"color: {RED}; font-size: 12px; font-weight: 600;")
        self.err_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(self.err_lbl)

        save_btn = QPushButton("Save & Continue  →")
        save_btn.setStyleSheet(pill_btn(BLUE, BLUE_SOFT, "white", 14, 15, "13px 22px"))
        save_btn.setFixedHeight(50)
        save_btn.clicked.connect(self._save)
        cl.addWidget(save_btn)

        layout.addWidget(card, alignment=Qt.AlignmentFlag.AlignCenter)

    def _save(self):
        ip = self.ip_input.text().strip()
        if not ip:
            self.err_lbl.setText("Please enter the server IP address."); return
        parts = ip.split(".")
        if len(parts) != 4 or not all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
            self.err_lbl.setText("Invalid IP. Example: 192.168.1.15"); return
        save_config({"server_ip": ip})
        self.err_lbl.setText("")
        self.ip_saved.emit()

# ─── Login Screen ─────────────────────────────────────────────────────────────

class LoginScreen(QWidget):
    user_selected = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.selected_uid = None
        self._bg = GradientBg(self)
        self._build()

    def resizeEvent(self, event):
        self._bg.setGeometry(0, 0, self.width(), self.height()); super().resizeEvent(event)

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(40, 40, 40, 40)

        card = GlassCard(radius=26, bg_alpha=185, shadow_blur=56, shadow_y=18, shadow_alpha=28)
        card.setMaximumWidth(490)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(42, 36, 42, 40)
        cl.setSpacing(10)

        logo = QLabel("🏥")
        logo.setStyleSheet("font-size: 52px;")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(logo)

        title = QLabel("Clinic Connect")
        title.setStyleSheet(
            f"font-size: 26px; font-weight: 700; color: {TEXT_MAIN}; letter-spacing: -0.5px;"
        )
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(title)

        div = QFrame(); div.setFixedHeight(1)
        div.setStyleSheet("background: rgba(0,0,0,0.07); margin: 4px 0;")
        cl.addWidget(div)

        # Step 1
        s1 = QLabel("SELECT YOUR NAME")
        s1.setStyleSheet(f"font-size: 10px; font-weight: 700; color: {BLUE}; letter-spacing: 1.5px;")
        cl.addWidget(s1)

        sections = [("DOCTORS", DOCTORS), ("RECEPTION", RECEPTIONS), ("PHOTO STAFF", PHOTO_STAFF)]
        self.user_btns = {}
        for sec_title, uids in sections:
            sec_lbl = QLabel(sec_title)
            sec_lbl.setStyleSheet(
                f"font-size: 10px; color: {TEXT_LITE}; letter-spacing: 1.2px; margin-top: 6px;"
            )
            cl.addWidget(sec_lbl)
            row = QHBoxLayout(); row.setSpacing(8)
            for uid in uids:
                btn = QPushButton(USERS[uid]['display'])
                btn._uid = uid; btn._active = False
                self._style_user(btn, False)
                btn.clicked.connect(lambda _, u=uid, b=btn: self._select(u, b))
                self.user_btns[uid] = btn
                row.addWidget(btn)
            cl.addLayout(row)

        div2 = QFrame(); div2.setFixedHeight(1)
        div2.setStyleSheet("background: rgba(0,0,0,0.07); margin: 6px 0;")
        cl.addWidget(div2)

        s2 = QLabel("ENTER YOUR PASSWORD")
        s2.setStyleSheet(f"font-size: 10px; font-weight: 700; color: {BLUE}; letter-spacing: 1.5px;")
        cl.addWidget(s2)

        self.pw_input = QLineEdit()
        self.pw_input.setPlaceholderText("Password")
        self.pw_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pw_input.setStyleSheet(input_style())
        self.pw_input.returnPressed.connect(self._login)
        cl.addWidget(self.pw_input)

        self.err_lbl = QLabel("")
        self.err_lbl.setStyleSheet(f"color: {RED}; font-size: 12px; font-weight: 600;")
        self.err_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(self.err_lbl)

        login_btn = QPushButton("Sign In  →")
        login_btn.setStyleSheet(pill_btn(BLUE, BLUE_SOFT, "white", 14, 15, "13px 22px"))
        login_btn.setFixedHeight(50)
        login_btn.clicked.connect(self._login)
        cl.addWidget(login_btn)

        layout.addWidget(card, alignment=Qt.AlignmentFlag.AlignCenter)

    def _style_user(self, btn, active):
        if active:
            btn.setStyleSheet(
                f"QPushButton {{ background: {BLUE}; color: white; border-radius: 10px;"
                f" padding: 9px 14px; font-size: 13px; font-weight: 600; border: none; }}"
            )
        else:
            btn.setStyleSheet(
                f"QPushButton {{ background: rgba(255,255,255,0.65); color: {TEXT_SEC};"
                f" border: 1px solid rgba(0,0,0,0.09); border-radius: 10px;"
                f" padding: 9px 14px; font-size: 13px; }}"
                f"QPushButton:hover {{ background: {BLUE_PALE}; color: {BLUE}; border-color: {BLUE}44; }}"
            )

    def _select(self, uid, btn):
        for u, b in self.user_btns.items():
            self._style_user(b, False)
        self._style_user(btn, True)
        self.selected_uid = uid
        self.err_lbl.setText("")
        self.pw_input.setFocus()

    def _login(self):
        if not self.selected_uid:
            self.err_lbl.setText("Please select your name first."); return
        if self.pw_input.text().strip() == USERS[self.selected_uid]['password']:
            self.err_lbl.setText(""); self.pw_input.clear()
            self.user_selected.emit(self.selected_uid)
        else:
            self.err_lbl.setText("Incorrect password. Try again.")
            self.pw_input.clear(); self.pw_input.setFocus()

# ─── Chat Bubble ──────────────────────────────────────────────────────────────

class MessageBubble(QFrame):
    def __init__(self, sender_display, content, timestamp, is_mine,
                 status="delivered", msg_id=None):
        super().__init__()
        self.is_mine = is_mine
        self.msg_id  = msg_id
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)

        bubble = QFrame()
        bubble.setMaximumWidth(310)
        bl = QVBoxLayout(bubble)
        bl.setContentsMargins(14, 10, 14, 8)
        bl.setSpacing(3)

        if is_mine:
            bubble.setStyleSheet(
                f"QFrame {{ background: {BLUE}; border-radius: 18px;"
                f" border-bottom-right-radius: 5px; }}"
            )
        else:
            bubble.setStyleSheet(
                f"QFrame {{ background: rgba(255,255,255,0.85);"
                f" border-radius: 18px; border-bottom-left-radius: 5px;"
                f" border: 1px solid rgba(0,0,0,0.07); }}"
            )

        if not is_mine:
            sl = QLabel(sender_display)
            sl.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {BLUE};")
            bl.addWidget(sl)

        ml = QLabel(content)
        ml.setWordWrap(True)
        ml.setStyleSheet(
            f"font-size: 14px; color: {'white' if is_mine else TEXT_MAIN}; line-height: 1.45;"
        )
        bl.addWidget(ml)

        meta = QHBoxLayout(); meta.setContentsMargins(0, 0, 0, 0); meta.addStretch()
        tl = QLabel(timestamp)
        tl.setStyleSheet(
            f"font-size: 10px; color: {'rgba(255,255,255,0.70)' if is_mine else TEXT_LITE};"
        )
        meta.addWidget(tl)
        if is_mine:
            self._tick = QLabel()
            self._set_ticks(status)
            meta.addWidget(self._tick)
        else:
            self._tick = None
        bl.addLayout(meta)

        row = QHBoxLayout(); row.setContentsMargins(0, 0, 0, 0)
        if is_mine:
            row.addStretch(); row.addWidget(bubble)
        else:
            row.addWidget(bubble); row.addStretch()
        layout.addLayout(row)

    def _set_ticks(self, status):
        if not self._tick: return
        if status == "read":
            self._tick.setText("✓✓")
            self._tick.setStyleSheet("font-size: 10px; font-weight: 700; color: #5BD1FF;")
            self._tick.setToolTip("Read")
        elif status == "delivered":
            self._tick.setText("✓✓")
            self._tick.setStyleSheet("font-size: 10px; font-weight: 700; color: rgba(255,255,255,0.55);")
            self._tick.setToolTip("Delivered")
        else:
            self._tick.setText("✓")
            self._tick.setStyleSheet("font-size: 10px; font-weight: 700; color: rgba(255,255,255,0.55);")
            self._tick.setToolTip("Sent")

    def update_status(self, status):
        self._set_ticks(status)


class StatusMessage(QFrame):
    """Doctor/photo status — normal chat message with coloured left accent."""
    def __init__(self, sender_display, msg_type, content, timestamp):
        super().__init__()
        meta = {
            "doctor_resting":       ("😴", RED),
            "doctor_wants_patient": ("🏥", GREEN),
            "photo_request":        ("📸", BLUE),
        }
        icon, color = meta.get(msg_type, ("📢", BLUE))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 3, 0, 3)

        bubble = QFrame()
        bubble.setMaximumWidth(310)
        bubble.setStyleSheet(
            f"QFrame {{ background: rgba(255,255,255,0.85);"
            f" border-radius: 18px; border-bottom-left-radius: 5px;"
            f" border: 1px solid rgba(0,0,0,0.07);"
            f" border-left: 3.5px solid {color}; }}"
        )
        bl = QVBoxLayout(bubble)
        bl.setContentsMargins(14, 10, 14, 8)
        bl.setSpacing(3)

        sl = QLabel(sender_display)
        sl.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {color};")
        bl.addWidget(sl)

        msg_row = QHBoxLayout(); msg_row.setSpacing(7)
        ic = QLabel(icon); ic.setStyleSheet("font-size: 16px;")
        txt = QLabel(content)
        txt.setWordWrap(True)
        txt.setStyleSheet(f"font-size: 14px; color: {TEXT_MAIN};")
        msg_row.addWidget(ic); msg_row.addWidget(txt, 1)
        bl.addLayout(msg_row)

        tl = QLabel(timestamp)
        tl.setStyleSheet(f"font-size: 10px; color: {TEXT_LITE};")
        tl.setAlignment(Qt.AlignmentFlag.AlignRight)
        bl.addWidget(tl)

        row = QHBoxLayout(); row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(bubble); row.addStretch()
        layout.addLayout(row)

# ─── Messaging Window ─────────────────────────────────────────────────────────

class MessagingWindow(QWidget):
    send_message = pyqtSignal(dict)

    def __init__(self, current_uid, current_info, all_users):
        super().__init__()
        self.current_uid   = current_uid
        self.current_info  = current_info
        self.all_users     = all_users
        self.chat_target   = None
        self.online_users  = []
        self._history      = {}
        self._bubbles      = {}
        self._temp_counter = 0
        self._build()

    def _build(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Sidebar ──────────────────────────────────────────────────
        sidebar = QFrame()
        sidebar.setFixedWidth(224)
        sidebar.setStyleSheet(
            "QFrame { background: rgba(255,255,255,0.52);"
            " border-right: 1px solid rgba(0,0,0,0.07); }"
        )
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(0)

        sb_head = QFrame()
        sb_head.setFixedHeight(54)
        sb_head.setStyleSheet(
            "QFrame { background: transparent;"
            " border-bottom: 1px solid rgba(0,0,0,0.06); }"
        )
        sh = QHBoxLayout(sb_head); sh.setContentsMargins(18, 0, 18, 0)
        sb_title = QLabel("Messages")
        sb_title.setStyleSheet(
            f"font-size: 16px; font-weight: 700; color: {TEXT_MAIN}; letter-spacing: -0.3px;"
        )
        sh.addWidget(sb_title)
        sl.addWidget(sb_head)

        self.contact_list = QListWidget()
        self.contact_list.setStyleSheet(
            f"QListWidget {{ background: transparent; border: none; outline: none; }}"
            f"QListWidget::item {{ padding: 13px 18px; color: {TEXT_SEC}; font-size: 13px;"
            f" border-bottom: 1px solid rgba(0,0,0,0.04); }}"
            f"QListWidget::item:selected {{ background: {BLUE_PALE}; color: {TEXT_MAIN};"
            f" border-left: 3px solid {BLUE}; }}"
            f"QListWidget::item:hover {{ background: rgba(10,132,255,0.07); }}"
        )
        for uid, info in self.all_users.items():
            if uid == self.current_uid: continue
            item = QListWidgetItem(f"  {info['display']}")
            item.setData(Qt.ItemDataRole.UserRole, uid)
            self.contact_list.addItem(item)
        self.contact_list.currentItemChanged.connect(self._on_contact)
        sl.addWidget(self.contact_list)

        # ── Chat area ────────────────────────────────────────────────
        chat = QFrame()
        chat.setStyleSheet("QFrame { background: #EDF4FB; }")
        cl = QVBoxLayout(chat)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)

        # Header
        self._ch = QFrame()
        self._ch.setFixedHeight(58)
        self._ch.setStyleSheet(
            "QFrame { background: rgba(255,255,255,0.68);"
            " border-bottom: 1px solid rgba(0,0,0,0.07); }"
        )
        ch_l = QHBoxLayout(self._ch); ch_l.setContentsMargins(20, 0, 20, 0)
        self._dot = QLabel()
        self._dot.setFixedSize(9, 9)
        self._dot.setStyleSheet(f"background: {TEXT_LITE}; border-radius: 4px;")
        self._ch_title = QLabel("Select a contact")
        self._ch_title.setStyleSheet(
            f"font-size: 16px; font-weight: 700; color: {TEXT_MAIN}; letter-spacing: -0.3px;"
        )
        ch_l.addWidget(self._dot); ch_l.addSpacing(8)
        ch_l.addWidget(self._ch_title); ch_l.addStretch()
        cl.addWidget(self._ch)

        # Scroll
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { background: #EDF4FB; border: none; }")
        self.msg_container = QWidget()
        self.msg_container.setStyleSheet("background: #EDF4FB;")
        self.msg_layout = QVBoxLayout(self.msg_container)
        self.msg_layout.setContentsMargins(18, 18, 18, 18)
        self.msg_layout.setSpacing(2)
        self.msg_layout.addStretch()
        self.scroll.setWidget(self.msg_container)
        cl.addWidget(self.scroll)

        # Input bar
        inp = QFrame()
        inp.setFixedHeight(68)
        inp.setStyleSheet(
            "QFrame { background: rgba(255,255,255,0.68);"
            " border-top: 1px solid rgba(0,0,0,0.07); }"
        )
        il = QHBoxLayout(inp); il.setContentsMargins(14, 12, 14, 12); il.setSpacing(10)

        self.msg_input = QLineEdit()
        self.msg_input.setPlaceholderText("Message…")
        self.msg_input.setStyleSheet(
            f"QLineEdit {{ background: rgba(255,255,255,0.78);"
            f" border: 1px solid rgba(0,0,0,0.09); border-radius: 22px;"
            f" padding: 10px 18px; font-size: 14px; color: {TEXT_MAIN}; }}"
            f"QLineEdit:focus {{ border-color: {BLUE}; background: white; }}"
        )
        self.msg_input.returnPressed.connect(self._send)

        send_btn = QPushButton("↑")
        send_btn.setFixedSize(42, 42)
        send_btn.setStyleSheet(
            f"QPushButton {{ background: {BLUE}; color: white; border-radius: 21px;"
            f" font-size: 18px; font-weight: 700; border: none; }}"
            f"QPushButton:hover {{ background: {BLUE_SOFT}; }}"
        )
        send_btn.clicked.connect(self._send)

        il.addWidget(self.msg_input); il.addWidget(send_btn)
        cl.addWidget(inp)

        layout.addWidget(sidebar)
        layout.addWidget(chat, 1)

    # ── contact / chat logic ─────────────────────────────────────────

    def _on_contact(self, item):
        if not item: return
        self.chat_target = item.data(Qt.ItemDataRole.UserRole)
        info = self.all_users[self.chat_target]
        self._ch_title.setText(info['display'])
        online = self.chat_target in self.online_users
        self._dot.setStyleSheet(
            f"background: {GREEN if online else TEXT_LITE}; border-radius: 4px;"
        )
        self._redraw_chat()

    def _redraw_chat(self):
        while self.msg_layout.count() > 1:
            it = self.msg_layout.takeAt(0)
            if it.widget(): it.widget().deleteLater()
        for entry in self._history.get(self.chat_target, []):
            w = self._make_widget(entry)
            if w: self.msg_layout.insertWidget(self.msg_layout.count() - 1, w)
        QTimer.singleShot(50, self._scroll_bottom)

    def _make_widget(self, entry):
        sid    = entry["sender_id"]
        mtype  = entry["msg_type"]
        cont   = entry["content"]
        ts     = entry["timestamp"]
        status = entry.get("status", "delivered")
        mid    = entry.get("msg_id")
        if mtype in ("doctor_resting", "doctor_wants_patient", "photo_request"):
            return StatusMessage(
                self.all_users.get(sid, {}).get("display", sid), mtype, cont, ts
            )
        is_mine = (sid == self.current_uid)
        b = MessageBubble(
            self.all_users.get(sid, {}).get("display", sid),
            cont, ts, is_mine, status, mid
        )
        if mid: self._bubbles[mid] = b
        return b

    def add_status_to_recipient(self, recipient_id, sender_id, content, timestamp, msg_type):
        """
        Store a status/photo message directly under a specific recipient's thread,
        completely ignoring whatever chat is currently open.
        """
        entry = {"sender_id": sender_id, "msg_type": msg_type,
                 "content": content, "timestamp": timestamp,
                 "status": "delivered", "msg_id": None}
        if recipient_id not in self._history:
            self._history[recipient_id] = []
        self._history[recipient_id].append(entry)
        # Only render if that recipient's chat is currently open
        if recipient_id == self.chat_target:
            w = self._make_widget(entry)
            if w:
                self.msg_layout.insertWidget(self.msg_layout.count() - 1, w)
                QTimer.singleShot(50, self._scroll_bottom)

    def add_message(self, sender_id, content, timestamp,
                    status="delivered", msg_id=None, msg_type="message"):
        is_mine    = (sender_id == self.current_uid)
        contact_id = self.chat_target if is_mine else sender_id
        if not contact_id: return
        entry = {"sender_id": sender_id, "msg_type": msg_type,
                 "content": content, "timestamp": timestamp,
                 "status": status, "msg_id": msg_id}
        if contact_id not in self._history:
            self._history[contact_id] = []
        self._history[contact_id].append(entry)
        if contact_id == self.chat_target:
            w = self._make_widget(entry)
            if w:
                self.msg_layout.insertWidget(self.msg_layout.count() - 1, w)
                QTimer.singleShot(50, self._scroll_bottom)

    def load_history(self, messages):
        for m in messages:
            sender_id  = m["sender"]
            recipient  = m["recipient"]
            mtype      = m["message_type"]
            content    = m["content"]
            ts         = m["timestamp"]
            status     = m.get("status", "delivered")
            mid        = m["id"]
            is_mine    = (sender_id == self.current_uid)
            contact_id = recipient if is_mine else sender_id
            entry = {"sender_id": sender_id, "msg_type": mtype,
                     "content": content, "timestamp": ts,
                     "status": status, "msg_id": mid}
            if contact_id not in self._history:
                self._history[contact_id] = []
            self._history[contact_id].append(entry)
        if self.chat_target:
            self._redraw_chat()

    def update_bubble_status(self, msg_id, status, temp_id=None):
        if temp_id is not None and temp_id in self._bubbles:
            bubble = self._bubbles.pop(temp_id)
            self._bubbles[msg_id] = bubble
            bubble.msg_id = msg_id
            for entries in self._history.values():
                for i, e in enumerate(entries):
                    if e.get("msg_id") == temp_id:
                        entries[i]["msg_id"] = msg_id
                        entries[i]["status"] = status
        if msg_id in self._bubbles:
            self._bubbles[msg_id].update_status(status)
        for entries in self._history.values():
            for e in entries:
                if e.get("msg_id") == msg_id:
                    e["status"] = status

    def _scroll_bottom(self):
        sb = self.scroll.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _send(self):
        if not self.chat_target: return
        text = self.msg_input.text().strip()
        if not text: return
        self.msg_input.clear()
        ts = datetime.now().strftime("%I:%M %p")
        self._temp_counter += 1
        temp_id = -self._temp_counter
        self.add_message(self.current_uid, text, ts, "pending", temp_id, "message")
        self.send_message.emit({
            "type": "message", "recipients": [self.chat_target],
            "content": text, "timestamp": ts, "temp_id": temp_id,
        })

    def reply_to(self, recipient_id, text):
        old = self.chat_target
        self.chat_target = recipient_id
        ts = datetime.now().strftime("%I:%M %p")
        self._temp_counter += 1
        temp_id = -self._temp_counter
        self.add_message(self.current_uid, text, ts, "pending", temp_id, "message")
        self.chat_target = old
        self.send_message.emit({
            "type": "message", "recipients": [recipient_id],
            "content": text, "timestamp": ts, "temp_id": temp_id,
        })

    def update_presence(self, online_users):
        self.online_users = online_users
        for i in range(self.contact_list.count()):
            item = self.contact_list.item(i)
            uid  = item.data(Qt.ItemDataRole.UserRole)
            dot  = "🟢 " if uid in online_users else "⚫ "
            item.setText(f"  {dot}{self.all_users[uid]['display']}")
        if self.chat_target:
            online = self.chat_target in online_users
            self._dot.setStyleSheet(
                f"background: {GREEN if online else TEXT_LITE}; border-radius: 4px;"
            )

# ─── Doctor Panel ─────────────────────────────────────────────────────────────

class DoctorPanel(QWidget):
    send_notification = pyqtSignal(dict)

    def __init__(self, user_id, user_info):
        super().__init__()
        self.user_id = user_id
        self.user_info = user_info
        self.recipient_choice = "both"
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(18)

        name_lbl = QLabel(f"👨‍⚕️  {self.user_info['display']}")
        name_lbl.setStyleSheet(
            f"font-size: 22px; font-weight: 700; color: {TEXT_MAIN}; letter-spacing: -0.3px;"
        )
        layout.addWidget(name_lbl)

        card = GlassCard(radius=22, bg_alpha=155, shadow_blur=28, shadow_y=8, shadow_alpha=22)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(24, 22, 24, 24)
        cl.setSpacing(14)

        title_lbl = QLabel("Notify Reception")
        title_lbl.setStyleSheet(
            f"font-size: 15px; font-weight: 600; color: {TEXT_MAIN};"
        )
        cl.addWidget(title_lbl)

        recip_lbl = QLabel("Send to")
        recip_lbl.setStyleSheet(f"font-size: 12px; color: {TEXT_LITE}; font-weight: 500;")
        cl.addWidget(recip_lbl)

        self.rboth = QPushButton("Both")
        self.rr1   = QPushButton("Reception 1")
        self.rr2   = QPushButton("Reception 2")
        for b, active in [(self.rboth, True), (self.rr1, False), (self.rr2, False)]:
            b._active = active
            b.setStyleSheet(toggle_style(active))
        self.rboth.clicked.connect(lambda: self._set_recip("both"))
        self.rr1.clicked.connect(lambda: self._set_recip("r1"))
        self.rr2.clicked.connect(lambda: self._set_recip("r2"))

        rrow = QHBoxLayout(); rrow.setSpacing(8)
        rrow.addWidget(self.rboth); rrow.addWidget(self.rr1); rrow.addWidget(self.rr2)
        rrow.addStretch()
        cl.addLayout(rrow)

        div = QFrame(); div.setFixedHeight(1)
        div.setStyleSheet("background: rgba(0,0,0,0.06);")
        cl.addWidget(div)

        btn_row = QHBoxLayout(); btn_row.setSpacing(14)

        rest_btn = QPushButton("😴  Resting")
        rest_btn.setStyleSheet(
            f"QPushButton {{ background: rgba(255,69,58,0.10); color: {RED};"
            f" border: 1.5px solid rgba(255,69,58,0.22); border-radius: 16px;"
            f" padding: 18px 16px; font-size: 15px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: rgba(255,69,58,0.18); }}"
        )
        rest_btn.clicked.connect(self._send_resting)

        want_btn = QPushButton("🏥  Patient Ready")
        want_btn.setStyleSheet(
            f"QPushButton {{ background: rgba(48,209,88,0.10); color: {GREEN};"
            f" border: 1.5px solid rgba(48,209,88,0.22); border-radius: 16px;"
            f" padding: 18px 16px; font-size: 15px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: rgba(48,209,88,0.18); }}"
        )
        want_btn.clicked.connect(self._send_wants)

        btn_row.addWidget(rest_btn); btn_row.addWidget(want_btn)
        cl.addLayout(btn_row)

        layout.addWidget(card)
        layout.addStretch()

    def _set_recip(self, choice):
        self.recipient_choice = choice
        for b, c in [(self.rboth, "both"), (self.rr1, "r1"), (self.rr2, "r2")]:
            b._active = (choice == c); b.setStyleSheet(toggle_style(b._active))

    def _get_recipients(self):
        if self.recipient_choice == "r1": return ["reception1"]
        if self.recipient_choice == "r2": return ["reception2"]
        return ["reception1", "reception2"]

    def _send_resting(self):
        self.send_notification.emit({
            "type": "doctor_resting", "recipients": self._get_recipients(),
            "content": f"{self.user_info['display']} is Resting",
            "timestamp": datetime.now().strftime("%I:%M %p"),
        })

    def _send_wants(self):
        self.send_notification.emit({
            "type": "doctor_wants_patient", "recipients": self._get_recipients(),
            "content": f"{self.user_info['display']} - Patient Ready",
            "timestamp": datetime.now().strftime("%I:%M %p"),
        })

# ─── Reception Panel ──────────────────────────────────────────────────────────

class ReceptionPanel(QWidget):
    send_notification = pyqtSignal(dict)

    def __init__(self, user_id, user_info):
        super().__init__()
        self.user_id = user_id
        self.user_info = user_info
        self.photo_recip = "both"
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(18)

        name_lbl = QLabel(f"🏨  {self.user_info['display']}")
        name_lbl.setStyleSheet(
            f"font-size: 22px; font-weight: 700; color: {TEXT_MAIN};"
        )
        layout.addWidget(name_lbl)

        card = GlassCard(radius=22, bg_alpha=155, shadow_blur=28, shadow_y=8, shadow_alpha=22)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(24, 22, 24, 24)
        cl.setSpacing(14)

        title_lbl = QLabel("Send Photo Request")
        title_lbl.setStyleSheet(f"font-size: 15px; font-weight: 600; color: {TEXT_MAIN};")
        cl.addWidget(title_lbl)

        recip_lbl = QLabel("Send to")
        recip_lbl.setStyleSheet(f"font-size: 12px; color: {TEXT_LITE}; font-weight: 500;")
        cl.addWidget(recip_lbl)

        self.pboth    = QPushButton("Both")
        self.pdhaval  = QPushButton("Dhaval")
        self.pvaibhav = QPushButton("Vaibhav")
        for b, active in [(self.pboth, True), (self.pdhaval, False), (self.pvaibhav, False)]:
            b._active = active; b.setStyleSheet(toggle_style(active))
        self.pboth.clicked.connect(lambda: self._set_photo("both"))
        self.pdhaval.clicked.connect(lambda: self._set_photo("dhaval"))
        self.pvaibhav.clicked.connect(lambda: self._set_photo("vaibhav"))

        rrow = QHBoxLayout(); rrow.setSpacing(8)
        rrow.addWidget(self.pboth); rrow.addWidget(self.pdhaval); rrow.addWidget(self.pvaibhav)
        rrow.addStretch()
        cl.addLayout(rrow)

        photo_btn = QPushButton("📸  Send Photo Request")
        photo_btn.setStyleSheet(pill_btn(BLUE, BLUE_SOFT, "white", 16, 15, "16px 22px"))
        photo_btn.setFixedHeight(54)
        photo_btn.clicked.connect(self._send_photo)
        cl.addWidget(photo_btn)

        layout.addWidget(card)
        layout.addStretch()

    def _set_photo(self, choice):
        self.photo_recip = choice
        for b, c in [(self.pboth, "both"), (self.pdhaval, "dhaval"), (self.pvaibhav, "vaibhav")]:
            b._active = (choice == c); b.setStyleSheet(toggle_style(b._active))

    def _get_recipients(self):
        if self.photo_recip == "dhaval":  return ["dhaval"]
        if self.photo_recip == "vaibhav": return ["vaibhav"]
        return ["dhaval", "vaibhav"]

    def _send_photo(self):
        self.send_notification.emit({
            "type": "photo_request", "recipients": self._get_recipients(),
            "content": "Photo Required",
            "timestamp": datetime.now().strftime("%I:%M %p"),
        })

# ─── Status Dot ───────────────────────────────────────────────────────────────

class StatusDot(QLabel):
    def __init__(self):
        super().__init__()
        self.setFixedSize(9, 9)
        self.set_offline()

    def set_online(self):
        self.setStyleSheet(f"background: {GREEN}; border-radius: 4px;")
        self.setToolTip("Online")

    def set_offline(self):
        self.setStyleSheet(f"background: {RED}; border-radius: 4px;")
        self.setToolTip("Offline")

    def set_reconnecting(self):
        self.setStyleSheet(f"background: {ORANGE}; border-radius: 4px;")
        self.setToolTip("Reconnecting…")

# ─── Main Window ──────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.current_uid = None
        self.ws_worker   = None
        self.setWindowTitle("Clinic Connect")
        self.setMinimumSize(960, 660)
        self.setStyleSheet(APP_STYLE)

        central = QWidget()
        central.setStyleSheet("background: #EAF2FB;")
        self.setCentralWidget(central)
        ml = QVBoxLayout(central)
        ml.setContentsMargins(0, 0, 0, 0)

        self.stack = QStackedWidget(central)
        ml.addWidget(self.stack)

        self.ip_screen = IPSetupScreen()
        self.ip_screen.ip_saved.connect(lambda: self.stack.setCurrentIndex(1))
        self.stack.addWidget(self.ip_screen)

        self.login_screen = LoginScreen()
        self.login_screen.user_selected.connect(self.on_login)
        self.stack.addWidget(self.login_screen)

        self.app_widget = None
        self._setup_tray()

        if get_server_host():
            self.stack.setCurrentIndex(1)
        else:
            self.stack.setCurrentIndex(0)

    def _setup_tray(self):
        self.tray = QSystemTrayIcon(self)
        pix = QPixmap(32, 32); pix.fill(QColor(10, 132, 255))
        self.tray.setIcon(QIcon(pix))
        menu = QMenu()
        menu.addAction("Show").triggered.connect(self._show)
        menu.addSeparator()
        menu.addAction("⚙️  Change Server IP").triggered.connect(self._open_ip)
        menu.addSeparator()
        menu.addAction("Quit").triggered.connect(QApplication.quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda r: self._show()
            if r == QSystemTrayIcon.ActivationReason.DoubleClick else None
        )
        self.tray.show()

    def _show(self):
        self.show(); self.raise_(); self.activateWindow()

    def _open_ip(self):
        self.ip_screen.ip_input.setText(get_server_host())
        self.ip_screen.err_lbl.setText("")
        self.stack.setCurrentIndex(0)
        self._show()

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self.tray.showMessage(
            "Clinic Connect", "Running in background.",
            QSystemTrayIcon.MessageIcon.Information, 2000
        )

    def on_login(self, user_id):
        self.current_uid = user_id
        self._build_app(user_id, USERS[user_id])
        self.stack.setCurrentIndex(2)
        self._start_ws(user_id)

    def _build_app(self, user_id, info):
        if self.app_widget:
            self.stack.removeWidget(self.app_widget)
            self.app_widget.deleteLater()

        self.app_widget = QWidget()
        self.app_widget.setStyleSheet("background: #EAF2FB;")

        # Gradient background (fills whole app area)
        self._app_bg = GradientBg(self.app_widget)

        ol = QVBoxLayout(self.app_widget)
        ol.setContentsMargins(0, 0, 0, 0)
        ol.setSpacing(0)

        # ── Topbar ──────────────────────────────────────────────────
        topbar = QFrame()
        topbar.setFixedHeight(56)
        topbar.setStyleSheet(
            "QFrame { background: rgba(255,255,255,0.70);"
            " border-bottom: 1px solid rgba(0,0,0,0.07); }"
        )
        tl = QHBoxLayout(topbar); tl.setContentsMargins(22, 0, 22, 0)

        logo = QLabel("🏥  Clinic Connect")
        logo.setStyleSheet(
            f"font-size: 16px; font-weight: 700; color: {TEXT_MAIN}; letter-spacing: -0.3px;"
        )

        self.conn_dot = StatusDot()
        self.conn_lbl = QLabel("Connecting…")
        self.conn_lbl.setStyleSheet(f"font-size: 12px; color: {TEXT_LITE};")

        user_pill = QLabel(f"  {info['display']}  ")
        user_pill.setStyleSheet(
            f"font-size: 13px; font-weight: 600; color: {BLUE};"
            f" background: {BLUE_PALE}; border-radius: 11px; padding: 5px 13px;"
        )

        settings_btn = QPushButton("⚙")
        settings_btn.setFixedSize(34, 34)
        settings_btn.setStyleSheet(ghost_pill(9))
        settings_btn.clicked.connect(self._open_ip)

        logout_btn = QPushButton("Sign Out")
        logout_btn.setStyleSheet(ghost_pill(9))
        logout_btn.clicked.connect(self._logout)

        tl.addWidget(logo); tl.addStretch()
        tl.addWidget(self.conn_dot); tl.addSpacing(5)
        tl.addWidget(self.conn_lbl); tl.addSpacing(16)
        tl.addWidget(user_pill); tl.addSpacing(8)
        tl.addWidget(settings_btn); tl.addSpacing(4)
        tl.addWidget(logout_btn)
        ol.addWidget(topbar)

        # ── Tab bar ─────────────────────────────────────────────────
        tabbar = QFrame()
        tabbar.setFixedHeight(48)
        tabbar.setStyleSheet(
            "QFrame { background: rgba(255,255,255,0.52);"
            " border-bottom: 1px solid rgba(0,0,0,0.06); }"
        )
        tabl = QHBoxLayout(tabbar); tabl.setContentsMargins(16, 0, 16, 0); tabl.setSpacing(4)

        self.panel_stack = QStackedWidget()
        panels = []

        if info["role"] == "doctor":
            p = DoctorPanel(user_id, info)
            p.send_notification.connect(self._on_send)
            panels.append(("Status", p))
        elif info["role"] == "reception":
            p = ReceptionPanel(user_id, info)
            p.send_notification.connect(self._on_send)
            panels.append(("Requests", p))
        else:
            ph = QWidget()
            pl = QVBoxLayout(ph)
            pl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pl.addWidget(QLabel("📸  Photo Staff"))
            pl.addWidget(QLabel("You will receive photo requests from reception."))
            panels.append(("Dashboard", ph))

        self.msg_window = MessagingWindow(user_id, info, USERS)
        self.msg_window.send_message.connect(self._on_send)
        panels.append(("Messages", self.msg_window))

        self.tab_btns = []
        for i, (name, panel) in enumerate(panels):
            self.panel_stack.addWidget(panel)
            btn = QPushButton(name)
            btn.setStyleSheet(tab_style(i == 0))
            btn.clicked.connect(lambda _, idx=i: self._switch_tab(idx))
            tabl.addWidget(btn)
            self.tab_btns.append(btn)
        tabl.addStretch()

        ol.addWidget(tabbar)
        ol.addWidget(self.panel_stack)
        self.stack.addWidget(self.app_widget)

    def _switch_tab(self, idx):
        self.panel_stack.setCurrentIndex(idx)
        for i, btn in enumerate(self.tab_btns):
            btn.setStyleSheet(tab_style(i == idx))

    def resizeEvent(self, event):
        if hasattr(self, '_app_bg') and self.app_widget:
            self._app_bg.setGeometry(0, 0, self.app_widget.width(), self.app_widget.height())
        super().resizeEvent(event)

    def _start_ws(self, user_id):
        if self.ws_worker: self.ws_worker.stop()
        self.ws_worker = WSWorker(user_id)
        self.ws_worker.message_received.connect(
            self._on_msg, Qt.ConnectionType.QueuedConnection)
        self.ws_worker.connected.connect(
            self._on_connected, Qt.ConnectionType.QueuedConnection)
        self.ws_worker.disconnected.connect(
            self._on_disconnected, Qt.ConnectionType.QueuedConnection)
        self.ws_worker.presence_updated.connect(
            self._on_presence, Qt.ConnectionType.QueuedConnection)
        self.ws_worker.start()

    def _on_connected(self):
        if hasattr(self, 'conn_dot'):
            self.conn_dot.set_online()
            self.conn_lbl.setText("Online")
            self.conn_lbl.setStyleSheet(
                f"font-size: 12px; color: {GREEN}; font-weight: 600;"
            )

    def _on_disconnected(self):
        QTimer.singleShot(4000, self._show_reconnecting)

    def _show_reconnecting(self):
        if hasattr(self, 'conn_dot'):
            self.conn_dot.set_reconnecting()
            self.conn_lbl.setText("Reconnecting…")
            self.conn_lbl.setStyleSheet(f"font-size: 12px; color: {ORANGE};")

    def _on_presence(self, online_users):
        if hasattr(self, 'msg_window'):
            self.msg_window.update_presence(online_users)

    def _on_send(self, data):
        if self.ws_worker: self.ws_worker.send(data)
        mtype = data.get("type")
        if mtype in ("doctor_resting", "doctor_wants_patient", "photo_request"):
            if hasattr(self, 'msg_window'):
                for recip in data.get("recipients", []):
                    # Store under each recipient's thread directly — never use chat_target
                    self.msg_window.add_status_to_recipient(
                        recip,
                        self.current_uid,
                        data.get("content", ""),
                        data.get("timestamp", ""),
                        mtype
                    )

    def _on_msg(self, data):
        mtype = data.get("type")

        if mtype == "history":
            if hasattr(self, 'msg_window'):
                self.msg_window.load_history(data.get("messages", []))
            return

        if mtype == "status_update":
            mid     = data.get("id")
            status  = data.get("status", "delivered")
            temp_id = data.get("temp_id")
            if mid and hasattr(self, 'msg_window'):
                self.msg_window.update_bubble_status(mid, status, temp_id)
            return

        if mtype == "pong":
            return

        if mtype != "notification":
            return

        sender_id   = data.get("sender", "")
        sender_disp = USERS.get(sender_id, {}).get("display", sender_id)
        content     = data.get("content", "")
        timestamp   = data.get("timestamp", "")
        notif_type  = data.get("message_type", "message")
        msg_id      = data.get("id")
        offline     = data.get("offline_delivery", False)

        if hasattr(self, 'msg_window'):
            self.msg_window.add_message(
                sender_id, content, timestamp, "delivered", msg_id, notif_type
            )

        popup = PopupNotification(
            sender_disp, notif_type, content,
            timestamp, msg_id, self.ws_worker,
            original_sender_id=sender_id,
            offline=offline,
            reply_callback=self._on_popup_reply,
        )
        popup.show_popup()

    def _on_popup_reply(self, recipient_id, text):
        if not text.strip() or not recipient_id: return
        if hasattr(self, 'msg_window'):
            self.msg_window.reply_to(recipient_id, text)

    def _logout(self):
        if self.ws_worker:
            self.ws_worker.stop(); self.ws_worker = None
        self.current_uid = None
        self.stack.setCurrentIndex(1)

# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("Clinic Connect")
    app.setQuitOnLastWindowClosed(False)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
