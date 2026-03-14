"""
Clinic Connect - Server
Simple websocket server using Python built-in asyncio + websockets library.
No FastAPI, no uvicorn — works perfectly as a .exe with no keyboard input needed.
"""

import asyncio
import json
import sqlite3
import logging
import os
import sys
from datetime import datetime

# ── Work directory fix for PyInstaller ──
if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

os.chdir(APP_DIR)
DB_PATH = os.path.join(APP_DIR, "clinic.db")

import websockets
from websockets.server import serve

# ── Disable Windows Quick Edit Mode ──────────────────────────────────────────
# Quick Edit Mode pauses the server when user clicks the console window.
# Disabling it means the server never freezes due to accidental mouse clicks.
def disable_quick_edit():
    try:
        import ctypes
        import ctypes.wintypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-10)  # STD_INPUT_HANDLE
        mode = ctypes.wintypes.DWORD()
        kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        # Clear ENABLE_QUICK_EDIT_MODE (0x0040) and ENABLE_INSERT_MODE (0x0020)
        mode.value &= ~0x0040
        mode.value &= ~0x0020
        kernel32.SetConsoleMode(handle, mode)
    except Exception:
        pass  # Not on Windows or no console — ignore

disable_quick_edit()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger(__name__)

# ── Database ──────────────────────────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            sender       TEXT,
            recipient    TEXT,
            message_type TEXT,
            content      TEXT,
            timestamp    TEXT,
            status       TEXT DEFAULT 'pending',
            read_at      TEXT
        )
    """)
    conn.commit()
    conn.close()
    log.info(f"Database: {DB_PATH}")

def db_save(sender, recipient, mtype, content, timestamp):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(
        "INSERT INTO messages (sender,recipient,message_type,content,timestamp,status) VALUES (?,?,?,?,?,'pending')",
        (sender, recipient, mtype, content, timestamp)
    )
    conn.commit()
    mid = cur.lastrowid
    conn.close()
    return mid

def db_set_status(mid, status):
    conn = sqlite3.connect(DB_PATH)
    if status == "read":
        conn.execute("UPDATE messages SET status=?,read_at=? WHERE id=?",
                     (status, datetime.now().isoformat(), mid))
    else:
        conn.execute("UPDATE messages SET status=? WHERE id=?", (status, mid))
    conn.commit()
    conn.close()

def db_pending(user_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM messages WHERE recipient=? AND status='pending' ORDER BY timestamp",
        (user_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ── Connection Manager ────────────────────────────────────────────────────────

# user_id -> websocket
CLIENTS = {}

async def send_to(user_id, data):
    ws = CLIENTS.get(user_id)
    if not ws:
        return False
    try:
        await ws.send(json.dumps(data))
        return True
    except Exception:
        CLIENTS.pop(user_id, None)
        return False

async def broadcast_presence():
    online = list(CLIENTS.keys())
    msg = json.dumps({"type": "presence_update", "online_users": online})
    for uid, ws in list(CLIENTS.items()):
        try:
            await ws.send(msg)
        except Exception:
            pass

# ── Message Handler ───────────────────────────────────────────────────────────

async def handle(sender, data):
    t = data.get("type", "")

    if t == "ping":
        await send_to(sender, {"type": "pong"})
        return

    if t == "mark_read":
        mid = data.get("id")
        if mid:
            db_set_status(mid, "read")
            orig = data.get("original_sender")
            if orig:
                await send_to(orig, {"type": "status_update", "id": mid, "status": "read"})
        return

    # Route notification/message to recipients
    recipients = data.get("recipients", [])
    if isinstance(recipients, str):
        recipients = [recipients]
    timestamp = data.get("timestamp", datetime.now().strftime("%I:%M %p"))
    content = data.get("content", "")
    temp_id = data.get("temp_id")

    for recipient in recipients:
        mid = db_save(sender, recipient, t, content, timestamp)
        delivered = await send_to(recipient, {
            "type": "notification",
            "id": mid,
            "sender": sender,
            "recipient": recipient,
            "message_type": t,
            "content": content,
            "timestamp": timestamp,
            "offline_delivery": False,
        })
        status = "delivered" if delivered else "pending"
        db_set_status(mid, status)
        # Tell sender: delivered (with temp_id so client can remap bubble)
        await send_to(sender, {
            "type": "status_update",
            "id": mid,
            "temp_id": temp_id,
            "status": status,
        })

# ── WebSocket Connection ──────────────────────────────────────────────────────

async def on_connect(websocket):
    # Extract user_id from path e.g. /ws/dr_anchal
    path = websocket.request.path if hasattr(websocket, 'request') else getattr(websocket, 'path', '/')
    user_id = path.strip("/").split("/")[-1]

    CLIENTS[user_id] = websocket
    log.info(f"CONNECTED: {user_id}  |  Online: {list(CLIENTS.keys())}")
    await broadcast_presence()

    # Deliver pending messages
    pending = db_pending(user_id)
    for msg in pending:
        await send_to(user_id, {
            "type": "notification",
            "id": msg["id"],
            "sender": msg["sender"],
            "recipient": msg["recipient"],
            "message_type": msg["message_type"],
            "content": msg["content"],
            "timestamp": msg["timestamp"],
            "offline_delivery": True,
        })
        db_set_status(msg["id"], "delivered")
    if pending:
        log.info(f"Delivered {len(pending)} queued msgs to {user_id}")

    try:
        async for raw in websocket:
            try:
                data = json.loads(raw)
                await handle(user_id, data)
            except Exception as e:
                log.error(f"Handle error [{user_id}]: {e}")
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        CLIENTS.pop(user_id, None)
        log.info(f"DISCONNECTED: {user_id}  |  Online: {list(CLIENTS.keys())}")
        await broadcast_presence()

# ── Main ─────────────────────────────────────────────────────────────────────

async def main():
    init_db()
    print("=" * 50)
    print("  Clinic Connect - Server")
    print("  Listening on: 0.0.0.0:8765")
    print(f"  Database: {DB_PATH}")
    print("  Running... (minimize this window)")
    print("=" * 50)
    async with serve(on_connect, "0.0.0.0", 8765, ping_interval=30, ping_timeout=20):
        log.info("Server started on port 8765")
        await asyncio.Future()  # run forever

if __name__ == "__main__":
    asyncio.run(main())
