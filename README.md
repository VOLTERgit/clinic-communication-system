# 🏥 Clinic Connect — Internal Communication System

A real-time LAN-based communication system for clinic staff.  
Built with Python · FastAPI · WebSockets · PyQt6 · SQLite

---

## 📁 Project Structure

```
clinic_app/
├── server/
│   ├── server.py                 ← FastAPI WebSocket server
│   ├── requirements_server.txt
│   └── clinic_server.spec        ← PyInstaller spec (server .exe)
│
└── client/
    ├── client.py                 ← PyQt6 desktop client
    ├── requirements_client.txt
    ├── clinic_client.spec        ← PyInstaller spec (client .exe)
    └── startup.bat               ← Windows auto-start helper
```

---

## ⚙️ Features

| Feature | Status |
|---|---|
| Doctor status buttons (Resting / Wants Patient) | ✅ |
| Send to Reception 1 / 2 / Both | ✅ |
| Photo request (Dhaval / Vaibhav / Both) | ✅ |
| Real-time popup notifications (stay until OK) | ✅ |
| Direct messaging with tick status | ✅ |
| Offline message queue (SQLite) | ✅ |
| Auto-deliver queued messages on reconnect | ✅ |
| 🟢🔴🟡 Online/Offline presence indicators | ✅ |
| System tray (minimize to background) | ✅ |
| Auto-reconnect on network drop | ✅ |
| Login screen (role selection, no password) | ✅ |
| LAN-only, no internet required | ✅ |
| PyInstaller .exe packaging | ✅ |

---

## 🖥️ Setup: Server PC (One Machine Only)

The server runs on **one PC** on your LAN (e.g., the main reception PC or a dedicated machine).

### Step 1 — Install Python 3.11+
Download from https://python.org  
✅ Check "Add Python to PATH" during install.

### Step 2 — Install server dependencies
```cmd
cd clinic_app\server
pip install -r requirements_server.txt
```

### Step 3 — Find your LAN IP address
```cmd
ipconfig
```
Note your **IPv4 Address** — e.g. `192.168.1.10`  
You will need this for all client machines.

### Step 4 — Run the server
```cmd
python server.py
```
Server starts at: `ws://0.0.0.0:8765`  
Keep this window open (or package as .exe — see below).

---

## 💻 Setup: Client PCs (All Staff Machines)

### Step 1 — Edit the server IP in `client.py`
Open `client/client.py` and find line 30:
```python
SERVER_HOST = "127.0.0.1"   # Change to server PC's LAN IP
```
Change `127.0.0.1` to your server PC's IP address:
```python
SERVER_HOST = "192.168.1.10"  # ← Your server's IP
```

### Step 2 — Install client dependencies
```cmd
cd clinic_app\client
pip install -r requirements_client.txt
```

### Step 3 — Run the client
```cmd
python client.py
```

---

## 📦 Packaging as Windows .exe (PyInstaller)

### Install PyInstaller
```cmd
pip install pyinstaller
```

### Build the Client .exe
```cmd
cd clinic_app\client
pyinstaller clinic_client.spec
```
Output: `client/dist/ClinicConnect.exe`

### Build the Server .exe
```cmd
cd clinic_app\server
pyinstaller clinic_server.spec
```
Output: `server/dist/ClinicServer.exe`

### Distribute
- Copy `ClinicConnect.exe` to each staff PC.
- Run `ClinicServer.exe` on the server PC only.

---

## 🚀 Auto-Start on Windows Login

### Method 1 — Startup Folder (Easy)
1. Press `Win + R`, type: `shell:startup`, press Enter
2. Copy `startup.bat` into the Startup folder  
3. Edit `startup.bat` to point to your `ClinicConnect.exe` location

### Method 2 — Task Scheduler (More Reliable)
1. Open Task Scheduler → "Create Basic Task"
2. Trigger: "When I log on"
3. Action: Start program → browse to `ClinicConnect.exe`
4. ✅ Check "Run with highest privileges"

---

## 🌐 Network / Firewall

On the **server PC**, allow port 8765 through Windows Firewall:
```cmd
netsh advfirewall firewall add rule name="Clinic Connect Server" dir=in action=allow protocol=TCP localport=8765
```

---

## 👥 Users

| Login Name | Role | Can Do |
|---|---|---|
| Dr. Anchal Shah | Doctor | Send Resting / Wants Patient to reception |
| Dr. Diwaker Sharma | Doctor | Send Resting / Wants Patient to reception |
| Reception 1 | Reception | Send photo requests, receive doctor alerts |
| Reception 2 | Reception | Send photo requests, receive doctor alerts |
| Dhaval | Photo Staff | Receive photo requests |
| Vaibhav | Photo Staff | Receive photo requests |

All users can message each other directly.

---

## 🔔 Popup Notification Rules

- ✅ Appears instantly over all windows
- ✅ Stays on screen until **OK** is clicked
- ✅ Never auto-closes
- ✅ Shows sender name, message, and time
- ✅ Shows 📦 badge if delivered from offline queue

---

## 💬 Message Tick Status

| Tick | Meaning |
|---|---|
| ✓ | Sent (Pending) |
| ✓✓ (grey) | Delivered to device |
| ✓✓ (blue) | Read by recipient |

---

## 🛠️ Troubleshooting

**Client can't connect to server**
- Check `SERVER_HOST` IP is correct in `client.py`
- Ensure server is running (`ClinicServer.exe`)
- Check Windows Firewall allows port 8765

**Messages not delivering**
- Messages queue in SQLite when recipient offline
- They auto-deliver when recipient connects
- Check server console for errors

**Popup not appearing on top**
- Windows may block "always on top" for some apps
- Try right-clicking the task in Task Scheduler → "Run with highest privileges"

---

## 🔮 Future Improvements (as discussed)

- [ ] Patient queue system
- [ ] Sound notifications
- [ ] Priority/urgent alerts
- [ ] Message history search
- [ ] Dark/light mode toggle
- [ ] Admin panel with message logs
- [ ] Read receipts in chat list

---

*Clinic Connect — Built for internal LAN use only.*
