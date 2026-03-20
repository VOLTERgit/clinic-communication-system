"""
Clinic Connect - Server v2
Auto-opens Windows Firewall port 8765
Shows all local IPs so staff know which one to use
"""

import asyncio
import json
import sqlite3
import logging
import os
import sys
import socket
import subprocess
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
def disable_quick_edit():
    try:
        import ctypes, ctypes.wintypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-10)
        mode = ctypes.wintypes.DWORD()
        kernel32.GetConsoleMode(handle, ctypes.byref(mode))
        mode.value &= ~0x0040
        mode.value &= ~0x0020
        kernel32.SetConsoleMode(handle, mode)
    except Exception:
        pass

disable_quick_edit()

# ── Auto-open firewall port ───────────────────────────────────────────────────
def open_firewall_port():
    """Add Windows Firewall rule for port 8765 automatically."""
    try:
        rule_name = "Clinic Connect Server"
        # Delete old rule first (ignore errors)
        subprocess.run(
            ["netsh", "advfirewall", "firewall", "delete", "rule",
             f"name={rule_name}"],
            capture_output=True
        )
        # Add new inbound rule
        result = subprocess.run(
            ["netsh", "advfirewall", "firewall", "add", "rule",
             f"name={rule_name}",
             "dir=in",
             "action=allow",
             "protocol=TCP",
             f"localport=8765"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            print("  Firewall: Port 8765 opened successfully")
        else:
            print("  Firewall: Could not auto-open port (run as Admin to fix)")
            print("  Manual fix: Allow port 8765 in Windows Firewall")
    except Exception as e:
        print(f"  Firewall: {e}")

# ── Get all local IPs ─────────────────────────────────────────────────────────
def get_local_ips():
    ips = []
    try:
        hostname = socket.gethostname()
        infos = socket.getaddrinfo(hostname, None)
        for info in infos:
            ip = info[4][0]
            if ip.startswith("192.168.") or ip.startswith("10.") or ip.startswith("172."):
                if ip not in ips:
                    ips.append(ip)
    except Exception:
        pass
    # Fallback method
    if not ips:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ips.append(s.getsockname()[0])
            s.close()
        except Exception:
            pass
    return ips

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger(__name__)

# ── Database ──────────────────────────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_PATH)
    # Create table if it doesn't exist at all
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            sender       TEXT NOT NULL,
            recipient    TEXT NOT NULL,
            message_type TEXT NOT NULL,
            content      TEXT NOT NULL,
            timestamp    TEXT NOT NULL,
            status       TEXT DEFAULT 'pending',
            read_at      TEXT,
            created_at   TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()

    # ── Migrate old databases that are missing the created_at column ──
    columns = [row[1] for row in conn.execute("PRAGMA table_info(messages)").fetchall()]
    if "created_at" not in columns:
        conn.execute("ALTER TABLE messages ADD COLUMN created_at TEXT")
        # Fill existing rows with a sensible default
        conn.execute("UPDATE messages SET created_at = datetime('now') WHERE created_at IS NULL")
        conn.commit()
        log.info("Database migrated: added created_at column")

    conn.close()

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
        "SELECT * FROM messages WHERE recipient=? AND status='pending' ORDER BY created_at",
        (user_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def db_history(user_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT * FROM messages
           WHERE (sender=? OR recipient=?)
             AND status != 'pending'
             AND created_at >= datetime('now', '-7 days')
           ORDER BY created_at""",
        (user_id, user_id)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ── Connection Manager ────────────────────────────────────────────────────────

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

    recipients = data.get("recipients", [])
    if isinstance(recipients, str):
        recipients = [recipients]
    timestamp = data.get("timestamp", datetime.now().strftime("%I:%M %p"))
    content   = data.get("content", "")
    temp_id   = data.get("temp_id")

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
        await send_to(sender, {
            "type": "status_update",
            "id": mid,
            "temp_id": temp_id,
            "status": status,
        })

# ── WebSocket Connection ──────────────────────────────────────────────────────

async def on_connect(websocket):
    path = websocket.request.path if hasattr(websocket, 'request') else getattr(websocket, 'path', '/')
    user_id = path.strip("/").split("/")[-1]

    CLIENTS[user_id] = websocket
    log.info(f"CONNECTED: {user_id}  |  Online: {list(CLIENTS.keys())}")
    await broadcast_presence()

    # Send full history
    history = db_history(user_id)
    if history:
        await send_to(user_id, {
            "type": "history",
            "messages": [
                {
                    "id": m["id"],
                    "sender": m["sender"],
                    "recipient": m["recipient"],
                    "message_type": m["message_type"],
                    "content": m["content"],
                    "timestamp": m["timestamp"],
                    "status": m["status"],
                }
                for m in history
            ]
        })

    # Deliver pending offline messages
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

    # Auto open firewall
    open_firewall_port()

    # Get IPs
    ips = get_local_ips()

    print("")
    print("=" * 52)
    print("   Clinic Connect - Server")
    print("=" * 52)
    print("")
    if ips:
        print("  >>> USE THIS IP ON OTHER PCs <<<")
        print("")
        for ip in ips:
            print(f"      IP ADDRESS:  {ip}")
        print("")
    else:
        print("  Could not detect IP. Run ipconfig in cmd.")
        print("")
    print("  Port:     8765")
    print(f"  Database: {DB_PATH}")
    print("")
    print("  Status: RUNNING - minimize this window")
    print("=" * 52)
    print("")

    async with serve(on_connect, "0.0.0.0", 8765, ping_interval=30, ping_timeout=20):
        log.info("Server ready and waiting for connections...")
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
