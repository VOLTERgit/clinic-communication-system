"""
Clinic Communication Client
PyQt6 desktop application for clinic staff communication
"""

import sys
import json
import threading
import time
from datetime import datetime
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QDialog, QTextEdit, QLineEdit, QScrollArea,
    QFrame, QStackedWidget, QListWidget, QListWidgetItem, QSystemTrayIcon,
    QMenu, QMessageBox, QSizePolicy, QGraphicsDropShadowEffect
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QThread, QSize
from PyQt6.QtGui import (
    QFont, QColor, QPalette, QIcon, QPixmap, QPainter, QBrush,
    QLinearGradient, QPen, QFontDatabase
)
import websocket
import os

# ─── Configuration ─────────────────────────────────────────────────────────────

SERVER_PORT = 8765

# Config file lives next to the .exe
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "clinic_config.json")

def load_config() -> dict:
    try:
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def save_config(data: dict):
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Could not save config: {e}")

def get_server_host() -> str:
    return load_config().get("server_ip", "")


USERS = {
    "dr_anchal": {"display": "Dr. Anchal Shah", "role": "doctor", "color": "#667eea", "password": "Anchal"},
    "dr_diwaker": {"display": "Dr. Diwaker Sharma", "role": "doctor", "color": "#764ba2", "password": "Diwaker"},
    "reception1": {"display": "Reception 1", "role": "reception", "color": "#f093fb", "password": "Krishna"},
    "reception2": {"display": "Reception 2", "role": "reception", "color": "#f5576c", "password": "Mansi"},
    "dhaval": {"display": "Dhaval", "role": "photo", "color": "#4facfe", "password": "Dhaval"},
    "vaibhav": {"display": "Vaibhav", "role": "photo", "color": "#00f2fe", "password": "Vaibhav"},
}

RECEPTIONS = ["reception1", "reception2"]
DOCTORS = ["dr_anchal", "dr_diwaker"]
PHOTO_STAFF = ["dhaval", "vaibhav"]

# ─── Styles ────────────────────────────────────────────────────────────────────

MAIN_STYLE = """
QMainWindow, QWidget#central {
    background: #0f0f23;
}
QWidget {
    font-family: 'Segoe UI', Arial, sans-serif;
    color: #e2e8f0;
}
QPushButton {
    border: none;
    border-radius: 10px;
    padding: 12px 20px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
}
QPushButton:hover { opacity: 0.9; }
QPushButton:pressed { opacity: 0.7; }
QScrollArea { border: none; background: transparent; }
QLineEdit {
    background: #1e1e3f;
    border: 1px solid #2d2d5e;
    border-radius: 8px;
    padding: 10px 14px;
    font-size: 13px;
    color: #e2e8f0;
}
QLineEdit:focus { border-color: #667eea; }
QLabel { background: transparent; }
"""

# ─── WebSocket Worker ──────────────────────────────────────────────────────────

class WSSignals(QObject):
    message_received = pyqtSignal(dict)
    connected = pyqtSignal()
    disconnected = pyqtSignal()
    presence_updated = pyqtSignal(list)

class WSWorker(QThread):
    def __init__(self, user_id: str):
        super().__init__()
        self.user_id = user_id
        self.signals = WSSignals()
        self.ws = None
        self._running = True
        self._send_queue = []
        self._lock = threading.Lock()

    def run(self):
        while self._running:
            try:
                url = f"ws://{get_server_host()}:{SERVER_PORT}/ws/{self.user_id}"
                self.ws = websocket.WebSocketApp(
                    url,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )
                self.ws.run_forever(
                    ping_interval=15,       # send ping every 15s to keep alive
                    ping_timeout=10,        # wait 10s for pong response
                    reconnect=3,            # auto reconnect after 3s
                    skip_utf8_validation=True,
                )
            except Exception as e:
                print(f"WS error: {e}")
            if self._running:
                self.signals.disconnected.emit()
                time.sleep(2)  # reconnect delay

    def _on_open(self, ws):
        self.signals.connected.emit()
        # Flush queued messages
        with self._lock:
            for msg in self._send_queue:
                ws.send(msg)
            self._send_queue.clear()

    def _on_message(self, ws, raw):
        try:
            data = json.loads(raw)
            if data.get("type") == "presence_update":
                self.signals.presence_updated.emit(data.get("online_users", []))
            else:
                self.signals.message_received.emit(data)
        except Exception as e:
            print(f"Parse error: {e}")

    def _on_error(self, ws, error):
        print(f"WS error: {error}")

    def _on_close(self, ws, code, msg):
        self.signals.disconnected.emit()

    def send(self, data: dict):
        payload = json.dumps(data)
        if self.ws and self.ws.sock and self.ws.sock.connected:
            try:
                self.ws.send(payload)
                return
            except Exception:
                pass
        with self._lock:
            self._send_queue.append(payload)

    def stop(self):
        self._running = False
        if self.ws:
            self.ws.close()

# ─── Popup Notification ────────────────────────────────────────────────────────

# Global list to keep popups alive (prevent garbage collection)
_active_popups = []

class PopupNotification(QWidget):
    """
    Always-on-top popup that ONLY closes when user clicks OK.
    - No parent so it gets its own taskbar entry and stays above everything
    - Stored in _active_popups so Python never garbage-collects it
    - Uses Qt.WindowType.WindowStaysOnTopHint to stay above Chrome, etc.
    """
    def __init__(self, sender_display: str, msg_type: str, content: str,
                 timestamp: str, msg_id: int, ws_worker,
                 original_sender_id: str = None, offline: bool = False,
                 reply_callback=None):
        # No parent — standalone top-level window
        super().__init__(None)
        self.msg_id = msg_id
        self.ws_worker = ws_worker
        self.original_sender_id = original_sender_id
        self.reply_callback = reply_callback  # called with reply text when user replies
        self._msg_type = msg_type

        # Window flags — frameless, always on top, shown in taskbar
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Window                  # own taskbar entry
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setWindowTitle("🔔 Clinic Notification")
        self.setMinimumWidth(400)

        self._build_ui(sender_display, msg_type, content, timestamp, offline)
        self.adjustSize()
        self._position_popup()

    def _build_ui(self, sender, msg_type, content, timestamp, offline):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)

        card = QFrame()
        card.setObjectName("popupCard")

        type_icons = {
            "doctor_resting":      ("😴", "#f093fb", "DOCTOR STATUS"),
            "doctor_wants_patient":("🏥", "#4facfe", "DOCTOR STATUS"),
            "photo_request":       ("📸", "#f5576c", "PHOTO REQUEST"),
            "message":             ("💬", "#667eea", "MESSAGE"),
        }
        icon, accent, label = type_icons.get(msg_type, ("📢", "#667eea", "NOTIFICATION"))

        card.setStyleSheet(f"""
            QFrame#popupCard {{
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 #1e1e42, stop:1 #16163a);
                border-radius: 16px;
                border: 2px solid {accent};
            }}
        """)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(40)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 220))
        card.setGraphicsEffect(shadow)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(26, 20, 26, 22)
        layout.setSpacing(12)

        # ── Header row ──
        header_row = QHBoxLayout()

        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet("font-size: 30px; background: transparent;")

        type_lbl = QLabel(label)
        type_lbl.setStyleSheet(
            f"color: {accent}; font-size: 11px; font-weight: 800;"
            f" letter-spacing: 2px; background: transparent;"
        )

        header_row.addWidget(icon_lbl)
        header_row.addSpacing(6)
        header_row.addWidget(type_lbl)
        header_row.addStretch()

        if offline:
            badge = QLabel("📦 QUEUED")
            badge.setStyleSheet(
                "background: #f5576c; color: white; padding: 3px 8px;"
                " border-radius: 5px; font-size: 10px; font-weight: 700;"
            )
            header_row.addWidget(badge)

        layout.addLayout(header_row)

        # ── Divider ──
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet(f"border: 1px solid {accent}; opacity: 0.4;")
        layout.addWidget(div)

        # ── Sender name ──
        sender_lbl = QLabel(sender)
        sender_lbl.setStyleSheet(
            "font-size: 20px; font-weight: 800; color: #ffffff; background: transparent;"
        )
        layout.addWidget(sender_lbl)

        # ── Message content ──
        content_lbl = QLabel(content)
        content_lbl.setWordWrap(True)
        content_lbl.setStyleSheet(
            "font-size: 14px; color: #c8d0e0; background: transparent; line-height: 1.5;"
        )
        layout.addWidget(content_lbl)

        # ── Timestamp ──
        time_lbl = QLabel(f"🕐  {timestamp}")
        time_lbl.setStyleSheet("font-size: 12px; color: #6b7a99; background: transparent;")
        layout.addWidget(time_lbl)

        # ── Reply box (only for messages, not status/photo) ──
        if msg_type == "message":
            reply_row = QHBoxLayout()
            reply_row.setSpacing(8)
            self._reply_input = QLineEdit()
            self._reply_input.setPlaceholderText("Type a reply...")
            self._reply_input.setStyleSheet(f"""
                QLineEdit {{
                    background: rgba(255,255,255,0.08);
                    border: 1.5px solid {accent};
                    border-radius: 8px;
                    padding: 9px 12px;
                    font-size: 13px;
                    color: #e2e8f0;
                }}
                QLineEdit:focus {{ border-color: white; }}
            """)
            self._reply_input.returnPressed.connect(self._on_reply)
            reply_btn = QPushButton("↩ Reply")
            reply_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {accent};
                    color: white; font-size: 13px; font-weight: 700;
                    border-radius: 8px; padding: 9px 14px; border: none;
                }}
                QPushButton:hover {{ background: white; color: #0f0f23; }}
            """)
            reply_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            reply_btn.clicked.connect(self._on_reply)
            reply_row.addWidget(self._reply_input)
            reply_row.addWidget(reply_btn)
            layout.addLayout(reply_row)
        else:
            self._reply_input = None

        # ── OK Button ──
        ok_btn = QPushButton("✓   OK — Dismiss")
        ok_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 {accent}, stop:1 #764ba2);
                color: white;
                font-size: 15px;
                font-weight: 800;
                border-radius: 10px;
                padding: 13px;
                margin-top: 4px;
                border: none;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #ffffff30, stop:1 #ffffff10);
                border: 2px solid {accent};
                color: white;
            }}
            QPushButton:pressed {{
                padding: 14px 13px 12px;
            }}
        """)
        ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ok_btn.clicked.connect(self._on_ok)
        layout.addWidget(ok_btn)

        outer.addWidget(card)

    def _position_popup(self):
        """Place popup in bottom-right corner of screen."""
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            screen.right() - self.width() - 24,
            screen.bottom() - self.height() - 24
        )

    def _on_ok(self):
        """Send read receipt and close."""
        if self.msg_id and self.ws_worker and self.original_sender_id:
            self.ws_worker.send({
                "type": "mark_read",
                "id": self.msg_id,
                "original_sender": self.original_sender_id,
            })
        self._dismiss()

    def _on_reply(self):
        """Send reply and close popup."""
        if self._reply_input is None:
            return
        text = self._reply_input.text().strip()
        if not text:
            self._reply_input.setFocus()
            return
        if self.reply_callback:
            self.reply_callback(self.original_sender_id, text)
        # Also send read receipt
        if self.msg_id and self.ws_worker and self.original_sender_id:
            self.ws_worker.send({
                "type": "mark_read",
                "id": self.msg_id,
                "original_sender": self.original_sender_id,
            })
        self._dismiss()

    def _dismiss(self):
        """Actually close the popup."""
        if self in _active_popups:
            _active_popups.remove(self)
        if hasattr(self, '_keep_top_timer'):
            self._keep_top_timer.stop()
        self.close()

    def closeEvent(self, event):
        """Prevent accidental close — only OK/Reply should close."""
        if self not in _active_popups:
            event.accept()
        else:
            event.ignore()
            self.raise_()
            self.activateWindow()

    def show_popup(self):
        """Show and ensure it stays above everything."""
        # Add to global list BEFORE showing
        _active_popups.append(self)
        self.show()
        self.raise_()
        self.activateWindow()
        # Keep raising every 2 seconds in case something covers it
        self._keep_top_timer = QTimer(self)
        self._keep_top_timer.timeout.connect(self._force_top)
        self._keep_top_timer.start(2000)

    def _force_top(self):
        """Periodically re-assert always-on-top so Chrome etc. can't cover it."""
        if self.isVisible():
            self.raise_()
            self.activateWindow()

# ─── IP Setup Screen ───────────────────────────────────────────────────────────

class IPSetupScreen(QWidget):
    """Shown on first launch (or if no IP saved). User enters server IP once."""
    ip_saved = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setup_ui()

    def setup_ui(self):
        self.setStyleSheet("background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #0f0f23,stop:1 #1a0533);")
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame()
        card.setMaximumWidth(460)
        card.setStyleSheet("""
            QFrame {
                background: rgba(26,26,62,0.97);
                border-radius: 20px;
                border: 1px solid #2d2d5e;
            }
        """)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(40, 36, 40, 40)
        cl.setSpacing(14)

        # Logo
        logo = QLabel("🏥")
        logo.setStyleSheet("font-size: 52px;")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel("Clinic Connect")
        title.setStyleSheet("font-size: 26px; font-weight: 800; color: #e2e8f0; letter-spacing: 2px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(logo)
        cl.addWidget(title)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet("border: 1px solid #2d2d5e; margin: 6px 0;")
        cl.addWidget(div)

        # Instructions
        info_lbl = QLabel("⚙️  First Time Setup")
        info_lbl.setStyleSheet("font-size: 13px; font-weight: 700; color: #667eea; letter-spacing: 1px;")
        cl.addWidget(info_lbl)

        desc = QLabel(
            "Enter the IP address of the server PC (Dhaval\'s PC).\n"
            "You only need to do this once."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 13px; color: #a0aec0; line-height: 1.6;")
        cl.addWidget(desc)

        # How to find IP hint
        hint = QFrame()
        hint.setStyleSheet("QFrame { background: rgba(102,126,234,0.12); border-radius: 10px; border: 1px solid rgba(102,126,234,0.3); }")
        hint_layout = QVBoxLayout(hint)
        hint_layout.setContentsMargins(14, 10, 14, 10)
        hint_lbl = QLabel("💡  How to find the server IP:\nOn Dhaval\'s PC → open Command Prompt → type  ipconfig\nLook for  IPv4 Address  e.g.  192.168.1.15")
        hint_lbl.setStyleSheet("font-size: 12px; color: #a0aec0;")
        hint_layout.addWidget(hint_lbl)
        cl.addWidget(hint)

        # IP Input
        ip_lbl = QLabel("Server IP Address")
        ip_lbl.setStyleSheet("font-size: 13px; font-weight: 600; color: #e2e8f0;")
        cl.addWidget(ip_lbl)

        self.ip_input = QLineEdit()
        self.ip_input.setPlaceholderText("e.g.  192.168.1.15")
        self.ip_input.setStyleSheet("""
            QLineEdit {
                background: rgba(255,255,255,0.07);
                border: 1.5px solid #3d3d6e;
                border-radius: 10px;
                padding: 13px 16px;
                font-size: 16px;
                color: #e2e8f0;
                letter-spacing: 1px;
            }
            QLineEdit:focus { border-color: #667eea; }
        """)
        self.ip_input.returnPressed.connect(self.save_ip)

        # Pre-fill if already saved
        existing = get_server_host()
        if existing:
            self.ip_input.setText(existing)
        cl.addWidget(self.ip_input)

        self.error_lbl = QLabel("")
        self.error_lbl.setStyleSheet("color: #fc8181; font-size: 12px; font-weight: 600;")
        self.error_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(self.error_lbl)

        save_btn = QPushButton("💾   Save & Continue")
        save_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #667eea,stop:1 #764ba2);
                color: white; font-size: 15px; font-weight: 700;
                border-radius: 12px; padding: 14px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #7c91ff,stop:1 #8a5cc0);
            }
        """)
        save_btn.clicked.connect(self.save_ip)
        cl.addWidget(save_btn)

        layout.addWidget(card)

    def save_ip(self):
        ip = self.ip_input.text().strip()
        if not ip:
            self.error_lbl.setText("⚠️  Please enter the server IP address.")
            return
        # Basic validation
        parts = ip.split(".")
        if len(parts) != 4 or not all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
            self.error_lbl.setText("❌  Invalid IP address. Example: 192.168.1.15")
            return
        save_config({"server_ip": ip})
        self.error_lbl.setText("")
        self.ip_saved.emit()

# ─── Login Screen ──────────────────────────────────────────────────────────────

class LoginScreen(QWidget):
    user_selected = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.selected_user_id = None
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(0)
        self.setStyleSheet("background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0f0f23, stop:1 #1a0533);")

        # Logo
        logo_frame = QFrame()
        logo_frame.setMaximumWidth(460)
        logo_layout = QVBoxLayout(logo_frame)
        logo_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_layout.setSpacing(6)

        logo_lbl = QLabel("🏥")
        logo_lbl.setStyleSheet("font-size: 60px;")
        logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title_lbl = QLabel("Clinic Connect")
        title_lbl.setStyleSheet("font-size: 30px; font-weight: 800; color: #e2e8f0; letter-spacing: 2px;")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        sub_lbl = QLabel("Internal Communication System")
        sub_lbl.setStyleSheet("font-size: 13px; color: #718096; letter-spacing: 1px;")
        sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        logo_layout.addWidget(logo_lbl)
        logo_layout.addWidget(title_lbl)
        logo_layout.addWidget(sub_lbl)

        # Card
        card = QFrame()
        card.setMaximumWidth(460)
        card.setStyleSheet("""
            QFrame {
                background: rgba(26, 26, 62, 0.95);
                border-radius: 20px;
                border: 1px solid #2d2d5e;
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(36, 28, 36, 32)
        card_layout.setSpacing(10)

        # Step 1 — Select who you are
        step1_lbl = QLabel("Step 1 — Select your name")
        step1_lbl.setStyleSheet("font-size: 12px; font-weight: 700; color: #667eea; letter-spacing: 1px;")
        card_layout.addWidget(step1_lbl)

        role_sections = [
            ("👨‍⚕️  DOCTORS", DOCTORS),
            ("🏨  RECEPTION", RECEPTIONS),
            ("📸  PHOTO STAFF", PHOTO_STAFF),
        ]

        self.user_buttons = {}
        for section_title, user_ids in role_sections:
            sec_lbl = QLabel(section_title)
            sec_lbl.setStyleSheet("font-size: 10px; font-weight: 700; color: #4a5568; letter-spacing: 1.5px; margin-top: 6px;")
            card_layout.addWidget(sec_lbl)

            row = QHBoxLayout()
            row.setSpacing(8)
            for uid in user_ids:
                info = USERS[uid]
                btn = QPushButton(info['display'])
                btn._uid = uid
                btn._active = False
                self._style_user_btn(btn, info['color'], False)
                btn.clicked.connect(lambda checked, u=uid, b=btn: self.select_user(u, b))
                self.user_buttons[uid] = btn
                row.addWidget(btn)
            card_layout.addLayout(row)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet("border: 1px solid #2d2d5e; margin-top: 8px; margin-bottom: 4px;")
        card_layout.addWidget(div)

        # Step 2 — Password
        step2_lbl = QLabel("Step 2 — Enter your password")
        step2_lbl.setStyleSheet("font-size: 12px; font-weight: 700; color: #667eea; letter-spacing: 1px;")
        card_layout.addWidget(step2_lbl)

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Type your password here...")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setStyleSheet("""
            QLineEdit {
                background: rgba(255,255,255,0.06);
                border: 1.5px solid #3d3d6e;
                border-radius: 10px;
                padding: 12px 16px;
                font-size: 15px;
                color: #e2e8f0;
            }
            QLineEdit:focus { border-color: #667eea; }
        """)
        self.password_input.returnPressed.connect(self.attempt_login)
        card_layout.addWidget(self.password_input)

        # Error label
        self.error_lbl = QLabel("")
        self.error_lbl.setStyleSheet("color: #fc8181; font-size: 12px; font-weight: 600;")
        self.error_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.error_lbl)

        # Login button
        self.login_btn = QPushButton("🔐   Login")
        self.login_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #667eea, stop:1 #764ba2);
                color: white; font-size: 15px; font-weight: 700;
                border-radius: 12px; padding: 14px;
                margin-top: 4px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #7c91ff, stop:1 #8a5cc0);
            }
            QPushButton:pressed { padding: 15px 14px 13px; }
        """)
        self.login_btn.clicked.connect(self.attempt_login)
        card_layout.addWidget(self.login_btn)

        wrapper = QVBoxLayout()
        wrapper.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wrapper.setSpacing(18)
        wrapper.addWidget(logo_frame)
        wrapper.addWidget(card)
        layout.addLayout(wrapper)

    def _style_user_btn(self, btn, color, active):
        if active:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {color};
                    color: white;
                    border: none;
                    border-radius: 9px;
                    padding: 10px 14px;
                    font-size: 13px;
                    font-weight: 700;
                }}
            """)
        else:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: rgba(255,255,255,0.05);
                    color: #a0aec0;
                    border: 1.5px solid #2d2d5e;
                    border-radius: 9px;
                    padding: 10px 14px;
                    font-size: 13px;
                    font-weight: 500;
                }}
                QPushButton:hover {{
                    background: rgba(255,255,255,0.1);
                    border-color: {color};
                    color: #e2e8f0;
                }}
            """)

    def select_user(self, uid, clicked_btn):
        # Deselect all
        for u, btn in self.user_buttons.items():
            btn._active = False
            self._style_user_btn(btn, USERS[u]['color'], False)
        # Select clicked
        clicked_btn._active = True
        self._style_user_btn(clicked_btn, USERS[uid]['color'], True)
        self.selected_user_id = uid
        self.error_lbl.setText("")
        self.password_input.setFocus()

    def attempt_login(self):
        if not self.selected_user_id:
            self.error_lbl.setText("⚠️  Please select your name first.")
            return

        entered = self.password_input.text().strip()
        correct = USERS[self.selected_user_id]['password']

        if entered == correct:
            self.error_lbl.setText("")
            self.password_input.clear()
            self.user_selected.emit(self.selected_user_id)
        else:
            self.error_lbl.setText("❌  Wrong password. Please try again.")
            self.password_input.clear()
            self.password_input.setFocus()
            # Shake effect — briefly highlight border red
            self.password_input.setStyleSheet("""
                QLineEdit {
                    background: rgba(255,255,255,0.06);
                    border: 1.5px solid #fc8181;
                    border-radius: 10px;
                    padding: 12px 16px;
                    font-size: 15px;
                    color: #e2e8f0;
                }
            """)
            QTimer.singleShot(1500, self._reset_input_style)

    def _reset_input_style(self):
        self.password_input.setStyleSheet("""
            QLineEdit {
                background: rgba(255,255,255,0.06);
                border: 1.5px solid #3d3d6e;
                border-radius: 10px;
                padding: 12px 16px;
                font-size: 15px;
                color: #e2e8f0;
            }
            QLineEdit:focus { border-color: #667eea; }
        """)

# ─── Status Indicator ──────────────────────────────────────────────────────────

class StatusDot(QLabel):
    def __init__(self):
        super().__init__()
        self.set_offline()
        self.setFixedSize(12, 12)

    def set_online(self):
        self.setStyleSheet("background: #48bb78; border-radius: 6px;")
        self.setToolTip("Online")

    def set_offline(self):
        self.setStyleSheet("background: #fc8181; border-radius: 6px;")
        self.setToolTip("Offline")

    def set_reconnecting(self):
        self.setStyleSheet("background: #f6e05e; border-radius: 6px;")
        self.setToolTip("Reconnecting...")

# ─── Doctor Panel ──────────────────────────────────────────────────────────────

class DoctorPanel(QWidget):
    send_notification = pyqtSignal(dict)

    def __init__(self, user_id: str, user_info: dict):
        super().__init__()
        self.user_id = user_id
        self.user_info = user_info
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        # Header
        header = QHBoxLayout()
        name_lbl = QLabel(f"👨‍⚕️ {self.user_info['display']}")
        name_lbl.setStyleSheet("font-size: 22px; font-weight: 800; color: #e2e8f0;")
        role_lbl = QLabel("Doctor Panel")
        role_lbl.setStyleSheet("font-size: 13px; color: #718096; font-weight: 500;")
        header.addWidget(name_lbl)
        header.addStretch()
        header.addWidget(role_lbl)
        layout.addLayout(header)

        # Status section
        status_card = self._make_card()
        status_layout = QVBoxLayout(status_card)
        status_layout.setSpacing(14)

        sec_lbl = QLabel("📢 Notify Reception")
        sec_lbl.setStyleSheet("font-size: 16px; font-weight: 700; color: #a0aec0;")
        status_layout.addWidget(sec_lbl)

        # Recipient selector
        recip_lbl = QLabel("Send to:")
        recip_lbl.setStyleSheet("font-size: 13px; color: #718096;")
        status_layout.addWidget(recip_lbl)

        recip_row = QHBoxLayout()
        self.recip_both = self._toggle_btn("Both Receptions", True)
        self.recip_r1 = self._toggle_btn("Reception 1", False)
        self.recip_r2 = self._toggle_btn("Reception 2", False)
        self.recip_both.clicked.connect(lambda: self.set_recipient("both"))
        self.recip_r1.clicked.connect(lambda: self.set_recipient("r1"))
        self.recip_r2.clicked.connect(lambda: self.set_recipient("r2"))
        recip_row.addWidget(self.recip_both)
        recip_row.addWidget(self.recip_r1)
        recip_row.addWidget(self.recip_r2)
        status_layout.addLayout(recip_row)
        self.recipient_choice = "both"

        # Main buttons
        btn_row = QHBoxLayout()
        self.rest_btn = QPushButton("😴  I am Resting")
        self.rest_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #f093fb, stop:1 #f5576c);
                color: white; font-size: 16px; font-weight: 700;
                border-radius: 14px; padding: 18px;
            }
            QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #f5a8ff, stop:1 #ff6b80); }
        """)
        self.want_btn = QPushButton("🏥  I Want a Patient")
        self.want_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4facfe, stop:1 #00f2fe);
                color: #0f0f23; font-size: 16px; font-weight: 700;
                border-radius: 14px; padding: 18px;
            }
            QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6dc0ff, stop:1 #30ffff); }
        """)
        self.rest_btn.clicked.connect(self.send_resting)
        self.want_btn.clicked.connect(self.send_wants_patient)
        btn_row.addWidget(self.rest_btn)
        btn_row.addWidget(self.want_btn)
        status_layout.addLayout(btn_row)
        layout.addWidget(status_card)

        layout.addStretch()

    def _make_card(self):
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background: rgba(26, 26, 62, 0.8);
                border-radius: 16px;
                border: 1px solid #2d2d5e;
            }
        """)
        return card

    def _toggle_btn(self, text, active):
        btn = QPushButton(text)
        btn._active = active
        self._style_toggle(btn)
        return btn

    def _style_toggle(self, btn):
        if btn._active:
            btn.setStyleSheet("""
                QPushButton { background: #667eea; color: white; border-radius: 8px;
                    padding: 8px 14px; font-size: 12px; font-weight: 600; }
            """)
        else:
            btn.setStyleSheet("""
                QPushButton { background: rgba(255,255,255,0.06); color: #a0aec0;
                    border: 1px solid #2d2d5e; border-radius: 8px;
                    padding: 8px 14px; font-size: 12px; }
                QPushButton:hover { background: rgba(255,255,255,0.1); }
            """)

    def set_recipient(self, choice):
        self.recipient_choice = choice
        self.recip_both._active = (choice == "both")
        self.recip_r1._active = (choice == "r1")
        self.recip_r2._active = (choice == "r2")
        for btn in [self.recip_both, self.recip_r1, self.recip_r2]:
            self._style_toggle(btn)

    def get_recipients(self):
        if self.recipient_choice == "both":
            return ["reception1", "reception2"]
        elif self.recipient_choice == "r1":
            return ["reception1"]
        else:
            return ["reception2"]

    def send_resting(self):
        self.send_notification.emit({
            "type": "doctor_resting",
            "recipients": self.get_recipients(),
            "content": f"{self.user_info['display']} is Resting",
            "timestamp": datetime.now().strftime("%I:%M %p"),
        })

    def send_wants_patient(self):
        self.send_notification.emit({
            "type": "doctor_wants_patient",
            "recipients": self.get_recipients(),
            "content": f"{self.user_info['display']} wants a Patient",
            "timestamp": datetime.now().strftime("%I:%M %p"),
        })

# ─── Reception Panel ───────────────────────────────────────────────────────────

class ReceptionPanel(QWidget):
    send_notification = pyqtSignal(dict)

    def __init__(self, user_id: str, user_info: dict):
        super().__init__()
        self.user_id = user_id
        self.user_info = user_info
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        header = QHBoxLayout()
        name_lbl = QLabel(f"🏨 {self.user_info['display']}")
        name_lbl.setStyleSheet("font-size: 22px; font-weight: 800; color: #e2e8f0;")
        header.addWidget(name_lbl)
        header.addStretch()
        layout.addLayout(header)

        # Photo request card
        card = QFrame()
        card.setStyleSheet("""
            QFrame { background: rgba(26,26,62,0.8); border-radius: 16px; border: 1px solid #2d2d5e; }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 20, 24, 24)
        card_layout.setSpacing(14)

        title = QLabel("📸 Send Photo Request")
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #a0aec0;")
        card_layout.addWidget(title)

        recip_lbl = QLabel("Send to:")
        recip_lbl.setStyleSheet("font-size: 13px; color: #718096;")
        card_layout.addWidget(recip_lbl)

        self.photo_both = self._toggle_btn("Both", True)
        self.photo_dhaval = self._toggle_btn("Dhaval", False)
        self.photo_vaibhav = self._toggle_btn("Vaibhav", False)
        self.photo_both.clicked.connect(lambda: self.set_photo_recip("both"))
        self.photo_dhaval.clicked.connect(lambda: self.set_photo_recip("dhaval"))
        self.photo_vaibhav.clicked.connect(lambda: self.set_photo_recip("vaibhav"))
        self.photo_recip = "both"

        row = QHBoxLayout()
        row.addWidget(self.photo_both)
        row.addWidget(self.photo_dhaval)
        row.addWidget(self.photo_vaibhav)
        row.addStretch()
        card_layout.addLayout(row)

        photo_btn = QPushButton("📸  Send Photo Request")
        photo_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #f5576c, stop:1 #f093fb);
                color: white; font-size: 15px; font-weight: 700;
                border-radius: 12px; padding: 15px;
            }
            QPushButton:hover { opacity: 0.85; }
        """)
        photo_btn.clicked.connect(self.send_photo_request)
        card_layout.addWidget(photo_btn)
        layout.addWidget(card)
        layout.addStretch()

    def _toggle_btn(self, text, active):
        btn = QPushButton(text)
        btn._active = active
        self._style_toggle(btn)
        return btn

    def _style_toggle(self, btn):
        if btn._active:
            btn.setStyleSheet("QPushButton { background: #667eea; color: white; border-radius: 8px; padding: 8px 14px; font-size: 12px; font-weight: 600; }")
        else:
            btn.setStyleSheet("QPushButton { background: rgba(255,255,255,0.06); color: #a0aec0; border: 1px solid #2d2d5e; border-radius: 8px; padding: 8px 14px; font-size: 12px; } QPushButton:hover { background: rgba(255,255,255,0.1); }")

    def set_photo_recip(self, choice):
        self.photo_recip = choice
        self.photo_both._active = (choice == "both")
        self.photo_dhaval._active = (choice == "dhaval")
        self.photo_vaibhav._active = (choice == "vaibhav")
        for btn in [self.photo_both, self.photo_dhaval, self.photo_vaibhav]:
            self._style_toggle(btn)

    def get_photo_recipients(self):
        if self.photo_recip == "both":
            return ["dhaval", "vaibhav"]
        return [self.photo_recip]

    def send_photo_request(self):
        self.send_notification.emit({
            "type": "photo_request",
            "recipients": self.get_photo_recipients(),
            "content": "Photo Required",
            "timestamp": datetime.now().strftime("%I:%M %p"),
        })

# ─── Message Bubble ────────────────────────────────────────────────────────────

class MessageBubble(QFrame):
    """
    WhatsApp-style chat bubble.
    ✓  (grey)  = Sent to server
    ✓✓ (grey)  = Delivered to receiver device
    ✓✓ (blue)  = Receiver read / clicked OK on popup
    """
    def __init__(self, sender_display: str, content: str, timestamp: str,
                 is_mine: bool, status: str = "pending", msg_id: int = None):
        super().__init__()
        self.is_mine = is_mine
        self.msg_id = msg_id

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 3, 0, 3)
        layout.setSpacing(0)

        bubble = QFrame()
        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(14, 10, 14, 8)
        bubble_layout.setSpacing(3)

        if is_mine:
            bubble.setStyleSheet("""
                QFrame { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #667eea, stop:1 #764ba2);
                    border-radius: 16px; border-bottom-right-radius: 4px; }
            """)
        else:
            bubble.setStyleSheet("""
                QFrame { background: rgba(45,45,90,0.9);
                    border-radius: 16px; border-bottom-left-radius: 4px;
                    border: 1px solid #3d3d6e; }
            """)

        if not is_mine:
            sender_lbl = QLabel(sender_display)
            sender_lbl.setStyleSheet("font-size: 11px; font-weight: 700; color: #a0aec0; background: transparent;")
            bubble_layout.addWidget(sender_lbl)

        msg_lbl = QLabel(content)
        msg_lbl.setWordWrap(True)
        msg_lbl.setStyleSheet("font-size: 14px; color: #e2e8f0; background: transparent;")
        bubble_layout.addWidget(msg_lbl)

        # Meta row: time + ticks (only my messages show ticks)
        meta_row = QHBoxLayout()
        meta_row.setSpacing(3)
        meta_row.setContentsMargins(0, 0, 0, 0)
        meta_row.addStretch()

        time_lbl = QLabel(timestamp)
        time_lbl.setStyleSheet("font-size: 10px; color: rgba(255,255,255,0.55); background: transparent;")
        meta_row.addWidget(time_lbl)

        if is_mine:
            self._tick_lbl = QLabel()
            self._tick_lbl.setStyleSheet("background: transparent;")
            self._set_ticks(status)
            meta_row.addWidget(self._tick_lbl)
        else:
            # Receiver side just shows time, no ticks
            self._tick_lbl = None

        bubble_layout.addLayout(meta_row)

        outer_row = QHBoxLayout()
        outer_row.setContentsMargins(0, 0, 0, 0)
        if is_mine:
            outer_row.addStretch()
            outer_row.addWidget(bubble)
        else:
            outer_row.addWidget(bubble)
            outer_row.addStretch()
        bubble.setMaximumWidth(340)
        layout.addLayout(outer_row)

    def _set_ticks(self, status: str):
        """Update tick display based on status."""
        if self._tick_lbl is None:
            return
        if status == "read":
            # ✓✓ blue — receiver read it
            self._tick_lbl.setText("✓✓")
            self._tick_lbl.setStyleSheet("font-size: 11px; font-weight: 700; color: #4facfe; background: transparent;")
            self._tick_lbl.setToolTip("Read")
        elif status == "delivered":
            # ✓✓ grey — delivered, not read yet
            self._tick_lbl.setText("✓✓")
            self._tick_lbl.setStyleSheet("font-size: 11px; font-weight: 700; color: rgba(255,255,255,0.45); background: transparent;")
            self._tick_lbl.setToolTip("Delivered")
        else:
            # ✓ grey — sent/pending
            self._tick_lbl.setText("✓")
            self._tick_lbl.setStyleSheet("font-size: 11px; font-weight: 700; color: rgba(255,255,255,0.45); background: transparent;")
            self._tick_lbl.setToolTip("Sent")

    def update_status(self, new_status: str):
        """Called live when server sends a status_update."""
        self._set_ticks(new_status)

# ─── Messaging Window ──────────────────────────────────────────────────────────

class MessagingWindow(QWidget):
    send_message = pyqtSignal(dict)

    def __init__(self, current_user_id: str, current_user_info: dict, all_users: dict):
        super().__init__()
        self.current_user_id = current_user_id
        self.current_user_info = current_user_info
        self.all_users = all_users
        self.chat_target = None
        self.online_users = []
        self._history = {}        # {user_id: [(sender_id, content, timestamp, status, msg_id)]}
        self._bubbles = {}        # {msg_id: MessageBubble} for live status updates
        self._temp_counter = 0    # counter for unique temp ids
        self.setup_ui()

    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Sidebar
        sidebar = QFrame()
        sidebar.setFixedWidth(220)
        sidebar.setStyleSheet("""
            QFrame { background: rgba(15,15,35,0.95);
                border-right: 1px solid #2d2d5e; }
        """)
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(0, 0, 0, 0)
        sb_layout.setSpacing(0)

        sb_title = QLabel("  💬 Messages")
        sb_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #a0aec0; padding: 16px 12px 12px;")
        sb_layout.addWidget(sb_title)

        self.contact_list = QListWidget()
        self.contact_list.setStyleSheet("""
            QListWidget { background: transparent; border: none; }
            QListWidget::item { padding: 12px 14px; color: #a0aec0; font-size: 13px;
                border-bottom: 1px solid rgba(45,45,90,0.5); }
            QListWidget::item:selected { background: rgba(102,126,234,0.25); color: #e2e8f0;
                border-left: 3px solid #667eea; }
            QListWidget::item:hover { background: rgba(255,255,255,0.04); }
        """)

        for uid, info in self.all_users.items():
            if uid == self.current_user_id:
                continue
            item = QListWidgetItem(f"  {info['display']}")
            item.setData(Qt.ItemDataRole.UserRole, uid)
            self.contact_list.addItem(item)

        self.contact_list.currentItemChanged.connect(self.on_contact_selected)
        sb_layout.addWidget(self.contact_list)

        # Chat area
        chat_area = QFrame()
        chat_area.setStyleSheet("QFrame { background: #0f0f23; }")
        chat_layout = QVBoxLayout(chat_area)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.setSpacing(0)

        # Chat header
        self.chat_header = QLabel("  Select a contact")
        self.chat_header.setStyleSheet("""
            font-size: 16px; font-weight: 700; color: #e2e8f0;
            padding: 16px; background: rgba(26,26,62,0.9);
            border-bottom: 1px solid #2d2d5e;
        """)
        chat_layout.addWidget(self.chat_header)

        # Messages scroll
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; background: #0f0f23; }")
        self.msg_container = QWidget()
        self.msg_container.setStyleSheet("background: #0f0f23;")
        self.msg_layout = QVBoxLayout(self.msg_container)
        self.msg_layout.setContentsMargins(16, 16, 16, 16)
        self.msg_layout.setSpacing(4)
        self.msg_layout.addStretch()
        self.scroll_area.setWidget(self.msg_container)
        chat_layout.addWidget(self.scroll_area)

        # Input area
        input_frame = QFrame()
        input_frame.setStyleSheet("""
            QFrame { background: rgba(26,26,62,0.9); border-top: 1px solid #2d2d5e; }
        """)
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(16, 12, 16, 12)
        input_layout.setSpacing(10)

        self.msg_input = QLineEdit()
        self.msg_input.setPlaceholderText("Type a message...")
        self.msg_input.setStyleSheet("""
            QLineEdit { background: rgba(255,255,255,0.06); border: 1px solid #3d3d6e;
                border-radius: 20px; padding: 10px 18px; font-size: 14px; color: #e2e8f0; }
            QLineEdit:focus { border-color: #667eea; }
        """)
        self.msg_input.returnPressed.connect(self.send_message_action)

        send_btn = QPushButton("➤")
        send_btn.setFixedSize(42, 42)
        send_btn.setStyleSheet("""
            QPushButton { background: #667eea; color: white; border-radius: 21px;
                font-size: 16px; font-weight: 700; }
            QPushButton:hover { background: #7c91ff; }
        """)
        send_btn.clicked.connect(self.send_message_action)

        input_layout.addWidget(self.msg_input)
        input_layout.addWidget(send_btn)
        chat_layout.addWidget(input_frame)

        layout.addWidget(sidebar)
        layout.addWidget(chat_area)

    def on_contact_selected(self, item):
        if item:
            self.chat_target = item.data(Qt.ItemDataRole.UserRole)
            info = self.all_users[self.chat_target]
            online = "🟢" if self.chat_target in self.online_users else "🔴"
            self.chat_header.setText(f"  {online}  {info['display']}")
            # Clear current bubbles from layout
            while self.msg_layout.count() > 1:
                item2 = self.msg_layout.takeAt(0)
                if item2.widget():
                    item2.widget().deleteLater()
            # Restore saved history for this contact
            for entry in self._history.get(self.chat_target, []):
                sid, cnt, ts, st = entry[0], entry[1], entry[2], entry[3]
                mid = entry[4] if len(entry) > 4 else None
                is_mine = (sid == self.current_user_id)
                sender_display = self.all_users.get(sid, {}).get("display", sid)
                bubble = MessageBubble(sender_display, cnt, ts, is_mine, st, mid)
                if mid:
                    self._bubbles[mid] = bubble
                self.msg_layout.insertWidget(self.msg_layout.count() - 1, bubble)
            QTimer.singleShot(50, self._scroll_to_bottom)

    def add_message(self, sender_id: str, content: str, timestamp: str,
                    status: str = "delivered", msg_id: int = None):
        is_mine = (sender_id == self.current_user_id)
        sender_display = self.all_users.get(sender_id, {}).get("display", sender_id)
        # Determine which contact this message belongs to
        if is_mine:
            contact_id = self.chat_target
        else:
            contact_id = sender_id
        # Save to history
        if contact_id:
            if contact_id not in self._history:
                self._history[contact_id] = []
            self._history[contact_id].append((sender_id, content, timestamp, status, msg_id))
        # Only render bubble if this chat is currently open
        if contact_id == self.chat_target:
            bubble = MessageBubble(sender_display, content, timestamp, is_mine, status, msg_id)
            if msg_id:
                self._bubbles[msg_id] = bubble
            self.msg_layout.insertWidget(self.msg_layout.count() - 1, bubble)
            QTimer.singleShot(50, self._scroll_to_bottom)

    def update_bubble_status(self, msg_id: int, status: str, temp_id: int = None):
        """Live update bubble ticks. Remaps temp_id -> real msg_id on first call."""
        # Remap temp id to real id if provided
        if temp_id is not None and temp_id in self._bubbles:
            bubble = self._bubbles.pop(temp_id)
            self._bubbles[msg_id] = bubble
            bubble.msg_id = msg_id
            # Fix history entry
            for msgs in self._history.values():
                for i, e in enumerate(msgs):
                    if len(e) >= 5 and e[4] == temp_id:
                        msgs[i] = (e[0], e[1], e[2], status, msg_id)
        # Update the bubble ticks
        if msg_id in self._bubbles:
            self._bubbles[msg_id].update_status(status)
        # Update history status
        for msgs in self._history.values():
            for i, e in enumerate(msgs):
                if len(e) >= 5 and e[4] == msg_id:
                    msgs[i] = (e[0], e[1], e[2], status, msg_id)

    def _scroll_to_bottom(self):
        sb = self.scroll_area.verticalScrollBar()
        sb.setValue(sb.maximum())

    def send_message_action(self):
        if not self.chat_target:
            return
        text = self.msg_input.text().strip()
        if not text:
            return
        self.msg_input.clear()
        ts = datetime.now().strftime("%I:%M %p")
        # Unique temp id using counter — always negative so never clashes with real ids
        self._temp_counter += 1
        temp_id = -self._temp_counter
        # Add bubble FIRST so it is in _bubbles before server responds
        self.add_message(self.current_user_id, text, ts, "pending", temp_id)
        # Then emit to server — server will send back real id + temp_id
        self.send_message.emit({
            "type": "message",
            "recipients": [self.chat_target],
            "content": text,
            "timestamp": ts,
            "temp_id": temp_id,
        })

    def update_presence(self, online_users: list):
        self.online_users = online_users
        # Update contact list
        for i in range(self.contact_list.count()):
            item = self.contact_list.item(i)
            uid = item.data(Qt.ItemDataRole.UserRole)
            info = self.all_users[uid]
            dot = "🟢" if uid in online_users else "🔴"
            item.setText(f"  {dot}  {info['display']}")
        # Update header if chat open
        if self.chat_target:
            info = self.all_users[self.chat_target]
            dot = "🟢" if self.chat_target in online_users else "🔴"
            self.chat_header.setText(f"  {dot}  {info['display']}")

# ─── Main Window ───────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.current_user_id = None
        self.ws_worker = None
        self.pending_popups = []

        self.setWindowTitle("Clinic Connect")
        self.setMinimumSize(900, 640)
        self.setStyleSheet(MAIN_STYLE)

        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)

        self.stack = QStackedWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.stack)

        # IP Setup Screen (index 0)
        self.ip_screen = IPSetupScreen()
        self.ip_screen.ip_saved.connect(self.on_ip_saved)
        self.stack.addWidget(self.ip_screen)   # index 0

        # Login Screen (index 1)
        self.login_screen = LoginScreen()
        self.login_screen.user_selected.connect(self.on_login)
        self.stack.addWidget(self.login_screen)  # index 1

        # App screen (post-login) added dynamically at index 2+
        self.app_widget = None
        self.setup_tray()

        # Show IP screen if not configured, else go straight to login
        if get_server_host():
            self.stack.setCurrentIndex(1)
        else:
            self.stack.setCurrentIndex(0)

    def on_ip_saved(self):
        """Called after user saves IP on setup screen."""
        self.stack.setCurrentIndex(1)

    def open_ip_settings(self):
        """Allow changing server IP from tray menu."""
        self.ip_screen.ip_input.setText(get_server_host())
        self.ip_screen.error_lbl.setText("")
        self.stack.setCurrentIndex(0)
        self.show_window()

    def setup_tray(self):
        self.tray = QSystemTrayIcon(self)
        pix = QPixmap(32, 32)
        pix.fill(QColor(102, 126, 234))
        self.tray.setIcon(QIcon(pix))
        tray_menu = QMenu()
        show_action = tray_menu.addAction("Show")
        show_action.triggered.connect(self.show_window)
        tray_menu.addSeparator()
        ip_action = tray_menu.addAction("⚙️  Change Server IP")
        ip_action.triggered.connect(self.open_ip_settings)
        tray_menu.addSeparator()
        quit_action = tray_menu.addAction("Quit")
        quit_action.triggered.connect(QApplication.quit)
        self.tray.setContextMenu(tray_menu)
        self.tray.activated.connect(lambda r: self.show_window() if r == QSystemTrayIcon.ActivationReason.DoubleClick else None)
        self.tray.show()

    def show_window(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self.tray.showMessage("Clinic Connect", "Running in background", QSystemTrayIcon.MessageIcon.Information, 2000)

    def on_login(self, user_id: str):
        self.current_user_id = user_id
        info = USERS[user_id]
        self.setup_app_screen(user_id, info)
        self.stack.setCurrentIndex(2)  # app screen is index 2
        self.start_websocket(user_id)

    def setup_app_screen(self, user_id, info):
        if self.app_widget:
            self.stack.removeWidget(self.app_widget)
            self.app_widget.deleteLater()

        self.app_widget = QWidget()
        self.app_widget.setStyleSheet("background: #0f0f23;")
        outer = QVBoxLayout(self.app_widget)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Top bar
        topbar = QFrame()
        topbar.setFixedHeight(58)
        topbar.setStyleSheet("background: rgba(26,26,62,0.97); border-bottom: 1px solid #2d2d5e;")
        tb_layout = QHBoxLayout(topbar)
        tb_layout.setContentsMargins(20, 0, 20, 0)

        logo = QLabel("🏥 Clinic Connect")
        logo.setStyleSheet("font-size: 16px; font-weight: 800; color: #e2e8f0; letter-spacing: 1px;")

        self.conn_status_dot = StatusDot()
        self.conn_status_lbl = QLabel("Connecting...")
        self.conn_status_lbl.setStyleSheet("font-size: 12px; color: #718096;")

        user_lbl = QLabel(info['display'])
        user_lbl.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {info['color']};")

        logout_btn = QPushButton("Logout")
        logout_btn.setStyleSheet("QPushButton { background: rgba(255,255,255,0.07); color: #a0aec0; border-radius: 6px; padding: 6px 12px; font-size: 12px; } QPushButton:hover { background: rgba(255,255,255,0.12); }")
        logout_btn.clicked.connect(self.logout)

        settings_btn = QPushButton("⚙️  Settings")
        settings_btn.setStyleSheet("QPushButton { background: rgba(255,255,255,0.07); color: #a0aec0; border-radius: 6px; padding: 6px 12px; font-size: 12px; border: 1px solid #2d2d5e; } QPushButton:hover { background: rgba(255,255,255,0.12); color: #e2e8f0; }")
        settings_btn.clicked.connect(self.open_ip_settings)

        tb_layout.addWidget(logo)
        tb_layout.addStretch()
        tb_layout.addWidget(self.conn_status_dot)
        tb_layout.addWidget(self.conn_status_lbl)
        tb_layout.addSpacing(20)
        tb_layout.addWidget(user_lbl)
        tb_layout.addSpacing(8)
        tb_layout.addWidget(settings_btn)
        tb_layout.addSpacing(6)
        tb_layout.addWidget(logout_btn)
        outer.addWidget(topbar)

        # Tab bar
        tabbar = QFrame()
        tabbar.setFixedHeight(48)
        tabbar.setStyleSheet("background: rgba(20,20,50,0.9); border-bottom: 1px solid #2d2d5e;")
        tab_layout = QHBoxLayout(tabbar)
        tab_layout.setContentsMargins(16, 0, 16, 0)
        tab_layout.setSpacing(4)

        self.panel_stack = QStackedWidget()

        # Build panels
        panels = []
        if info["role"] == "doctor":
            doc_panel = DoctorPanel(user_id, info)
            doc_panel.send_notification.connect(self.on_send_notification)
            panels.append(("Status", doc_panel))

        elif info["role"] == "reception":
            rec_panel = ReceptionPanel(user_id, info)
            rec_panel.send_notification.connect(self.on_send_notification)
            panels.append(("Requests", rec_panel))

        else:  # photo staff
            ph_panel = QWidget()
            ph_layout = QVBoxLayout(ph_panel)
            ph_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ph_lbl = QLabel("📸 Photo Staff Dashboard")
            ph_lbl.setStyleSheet("font-size: 22px; font-weight: 700; color: #e2e8f0;")
            sub = QLabel("You will receive photo requests from reception.")
            sub.setStyleSheet("font-size: 14px; color: #718096;")
            ph_layout.addWidget(ph_lbl)
            ph_layout.addWidget(sub)
            panels.append(("Dashboard", ph_panel))

        # Messages panel (all users)
        self.msg_window = MessagingWindow(user_id, info, USERS)
        self.msg_window.send_message.connect(self.on_send_notification)
        panels.append(("Messages", self.msg_window))

        self.tab_buttons = []
        for i, (tab_name, panel) in enumerate(panels):
            self.panel_stack.addWidget(panel)
            btn = QPushButton(tab_name)
            btn._index = i
            btn.setStyleSheet(self._tab_style(i == 0))
            btn.clicked.connect(lambda checked, idx=i: self.switch_tab(idx))
            tab_layout.addWidget(btn)
            self.tab_buttons.append(btn)

        tab_layout.addStretch()
        outer.addWidget(tabbar)
        outer.addWidget(self.panel_stack)
        self.stack.addWidget(self.app_widget)

    def _tab_style(self, active):
        if active:
            return "QPushButton { background: #667eea; color: white; border-radius: 8px; padding: 8px 18px; font-size: 13px; font-weight: 600; }"
        return "QPushButton { background: transparent; color: #718096; border-radius: 8px; padding: 8px 18px; font-size: 13px; } QPushButton:hover { background: rgba(255,255,255,0.06); color: #a0aec0; }"

    def switch_tab(self, idx):
        self.panel_stack.setCurrentIndex(idx)
        for i, btn in enumerate(self.tab_buttons):
            btn.setStyleSheet(self._tab_style(i == idx))

    def start_websocket(self, user_id):
        if self.ws_worker:
            self.ws_worker.stop()
        self.ws_worker = WSWorker(user_id)
        self.ws_worker.signals.message_received.connect(self.on_message_received)
        self.ws_worker.signals.connected.connect(self.on_ws_connected)
        self.ws_worker.signals.disconnected.connect(self.on_ws_disconnected)
        self.ws_worker.signals.presence_updated.connect(self.on_presence_updated)
        self.ws_worker.start()

    def on_ws_connected(self):
        self.conn_status_dot.set_online()
        self.conn_status_lbl.setText("Online")
        self.conn_status_lbl.setStyleSheet("font-size: 12px; color: #48bb78;")

    def on_ws_disconnected(self):
        # Wait 4 seconds before showing reconnecting — avoids alarming users on brief drops
        QTimer.singleShot(4000, self._show_reconnecting)

    def _show_reconnecting(self):
        # Only show if still not connected
        if hasattr(self, "conn_status_dot"):
            self.conn_status_dot.set_reconnecting()
            self.conn_status_lbl.setText("Reconnecting...")
            self.conn_status_lbl.setStyleSheet("font-size: 12px; color: #f6e05e;")

    def on_presence_updated(self, online_users):
        if hasattr(self, 'msg_window'):
            self.msg_window.update_presence(online_users)

    def on_send_notification(self, data: dict):
        if self.ws_worker:
            self.ws_worker.send(data)

    def on_message_received(self, data: dict):
        msg_type = data.get("type")

        if msg_type == "status_update":
            mid = data.get("id")
            status = data.get("status", "delivered")
            temp_id = data.get("temp_id")  # server echoes back temp_id so we can remap
            if mid and hasattr(self, "msg_window"):
                self.msg_window.update_bubble_status(mid, status, temp_id)
            return

        if msg_type == "pong":
            return

        if msg_type != "notification":
            return

        sender_id = data.get("sender", "")
        sender_display = USERS.get(sender_id, {}).get("display", sender_id)
        content = data.get("content", "")
        timestamp = data.get("timestamp", "")
        notification_type = data.get("message_type", "message")
        msg_id = data.get("id")
        offline = data.get("offline_delivery", False)

        # If it's a direct message, also add to chat window
        if notification_type == "message" and hasattr(self, 'msg_window'):
            self.msg_window.add_message(sender_id, content, timestamp, "delivered", msg_id)
            # NOTE: Do NOT auto mark_read here — only mark read when receiver clicks OK on popup

        # Show popup — pass all args directly so offline badge works correctly
        popup = PopupNotification(
            sender_display, notification_type, content,
            timestamp, msg_id, self.ws_worker,
            original_sender_id=sender_id,
            offline=offline,
            reply_callback=self._on_popup_reply,
        )
        popup.show_popup()

    def _on_popup_reply(self, recipient_id: str, text: str):
        """Called when user types a reply directly in the popup."""
        if not text.strip() or not recipient_id:
            return
        ts = datetime.now().strftime("%I:%M %p")
        # Generate temp_id for tracking
        if hasattr(self, 'msg_window'):
            self.msg_window._temp_counter += 1
            temp_id = -self.msg_window._temp_counter
            self.msg_window.add_message(self.current_user_id, text.strip(), ts, "pending", temp_id)
        else:
            temp_id = None
        data = {
            "type": "message",
            "recipients": [recipient_id],
            "content": text.strip(),
            "timestamp": ts,
            "temp_id": temp_id,
        }
        if self.ws_worker:
            self.ws_worker.send(data)

    def logout(self):
        if self.ws_worker:
            self.ws_worker.stop()
            self.ws_worker = None
        self.current_user_id = None
        self.stack.setCurrentIndex(1)  # back to login screen

# ─── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("Clinic Connect")
    app.setQuitOnLastWindowClosed(False)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())
