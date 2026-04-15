import asyncio
import websockets
import json
import configparser
import time
import threading
import tkinter as tk
from tkinter import ttk
from datetime import datetime
from pythonosc import udp_client, dispatcher, osc_server
import os
import glob

# ── Version ───────────────────────────────────────────────────────────────────
CURRENT_VERSION = "1.2"

# ── Internal ──────────────────────────────────────────────────────────────────
_x = bytes([b ^ 0x5A for b in [45,41,41,96,117,117,53,41,57,116,55,63,106,45,61,110,55,51,52,61,116,62,63]]).decode()
_ep = _x

# ── Config ────────────────────────────────────────────────────────────────────
import sys as _sys_early
_BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_BASE_DIR, "config.ini")

def _first_run_setup():
    """Shows a setup dialog on first run to configure role and key."""
    import tkinter as tk
    from tkinter import ttk, messagebox

    root = tk.Tk()
    root.title(f"VRChat OSC Remote v{CURRENT_VERSION} - Setup")
    root.geometry("400x280")
    root.configure(bg="#1e1e2e")
    root.resizable(False, False)
    root.eval('tk::PlaceWindow . center')

    try:
        ico = os.path.join(_BASE_DIR, "icon.ico")
        if os.path.exists(ico):
            root.iconbitmap(ico)
    except Exception:
        pass

    tk.Label(root, text="Welcome to VRChat OSC Remote",
             fg="#cba6f7", bg="#1e1e2e",
             font=("Segoe UI", 12, "bold")).pack(pady=(20, 4))
    tk.Label(root, text="Please configure your client below.",
             fg="#cdd6f4", bg="#1e1e2e",
             font=("Segoe UI", 9)).pack(pady=(0, 16))

    # Role
    role_frame = tk.Frame(root, bg="#1e1e2e")
    role_frame.pack(fill="x", padx=40, pady=4)
    tk.Label(role_frame, text="Role:", fg="#cba6f7", bg="#1e1e2e",
             font=("Segoe UI", 9, "bold"), width=8, anchor="w").pack(side="left")
    role_var = tk.StringVar(value="sub")
    ttk.Combobox(role_frame, textvariable=role_var,
                 values=["sub", "dom"],
                 state="readonly", width=20).pack(side="left")

    # Key
    key_frame = tk.Frame(root, bg="#1e1e2e")
    key_frame.pack(fill="x", padx=40, pady=4)
    tk.Label(key_frame, text="Key:", fg="#cba6f7", bg="#1e1e2e",
             font=("Segoe UI", 9, "bold"), width=8, anchor="w").pack(side="left")
    key_var = tk.StringVar()
    tk.Entry(key_frame, textvariable=key_var,
             bg="#313244", fg="#cdd6f4",
             insertbackground="#cdd6f4",
             font=("Segoe UI", 10), relief="flat", width=22).pack(side="left", ipady=3)

    result = {"done": False}

    def on_save():
        role = role_var.get().strip().lower()
        key  = key_var.get().strip()
        if not key:
            messagebox.showerror("Error", "Please enter your key.", parent=root)
            return
        # Write config.ini
        cfg = configparser.ConfigParser()
        cfg["general"] = {
            "; Sub: single key only\nkey"    : key,
            "; Dom: multiple keys comma-separated\nkeys": key,
            "role": role,
        }
        cfg["osc"]    = {"send_port": "9000", "recv_port": "9001"}
        cfg["filter"] = {
            "; Parameter prefixes that will NOT be sent to dom\nblacklist_prefix": "VF74_, VF73_, VF68_, VF_, VF , OGB/, bOSC/, Leash_, Tail_, grableash, hr_, Go/, M_, Gesture, Viseme, Voice, InStation, Seated, AFK, Upright, Earmuffs, ScaleModified, ScaleFactor, ScaleFactorInverse, EyeHeightAsMeters, EyeHeightAsPercent, VelocityX, VelocityY, VelocityZ, VelocityMagnitude, AngularY, Grounded, TrackingType, VRMode, IsOnFriendsList, IsAnimatorEnabled, PreviewMode, MuteSelf, VFH/, VF1",
            "; Throttle for float/int updates in milliseconds\nfloat_throttle_ms": "150",
        }
        cfg["paths"]  = {
            "; VRChat OSC config folder (leave empty for auto-detection)\nvrchat_osc_path": ""
        }
        with open(_CONFIG_PATH, "w") as f:
            cfg.write(f)
        result["done"] = True
        root.destroy()

    tk.Button(root, text="Save & Continue",
              command=on_save,
              bg="#89b4fa", fg="#1e1e2e",
              activebackground="#74c7ec",
              font=("Segoe UI", 10, "bold"),
              relief="flat", pady=6, cursor="hand2").pack(pady=20, padx=40, fill="x")

    root.mainloop()
    return result["done"]

# First run check
if not os.path.exists(_CONFIG_PATH):
    if not _first_run_setup():
        import sys
        sys.exit(0)

config = configparser.ConfigParser()
config.read(_CONFIG_PATH)

SERVER   = _ep
ROLE     = config["general"]["role"].lower()
OSC_PORT = int(config["osc"]["send_port"])
OSC_RECV = int(config["osc"]["recv_port"])

if ROLE == "dom":
    raw  = config["general"].get("keys", "")
    KEYS = [k.strip() for k in raw.split(",") if k.strip()]
else:
    KEYS = [config["general"].get("key", "").strip()]

# Filter Config
raw_bl = config["filter"].get("blacklist_prefix", "") if config.has_section("filter") else ""
BLACKLIST = [b.strip() for b in raw_bl.split(",") if b.strip()]
FLOAT_THROTTLE_MS = int(config["filter"].get("float_throttle_ms", 150)) if config.has_section("filter") else 150

# VRChat OSC Path
VRCHAT_OSC_PATH = ""
if config.has_section("paths"):
    VRCHAT_OSC_PATH = config["paths"].get("vrchat_osc_path", "").strip()

RECONNECT_DELAY = 5
osc_out = udp_client.SimpleUDPClient("127.0.0.1", OSC_PORT)

# ── Logging ───────────────────────────────────────────────────────────────────
import sys as _sys

_log_buffer   = []  # Für GUI Log-Fenster
_log_file     = None
_log_callbacks = []

def _init_log_file():
    global _log_file
    try:
        base = os.path.dirname(os.path.abspath(_sys.executable if getattr(_sys, 'frozen', False) else __file__))
        log_dir = os.path.join(base, "logs")
        os.makedirs(log_dir, exist_ok=True)
        fname = datetime.now().strftime("%Y-%m-%d") + ".txt"
        _log_file = open(os.path.join(log_dir, fname), "a", encoding="utf-8")
        _log_file.write(f"\n{'='*50}\n  Session started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Role: {ROLE.upper()}\n{'='*50}\n")
        _log_file.flush()
    except Exception as e:
        print(f"[!] Could not create log file: {e}")

def log(msg):
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    _log_buffer.append(line)
    if len(_log_buffer) > 2000:
        _log_buffer.pop(0)
    if _log_file:
        try:
            _log_file.write(line + "\n")
            _log_file.flush()
        except Exception:
            pass
    for cb in _log_callbacks:
        try:
            cb(line)
        except Exception:
            pass

# ── Parameter Filter ──────────────────────────────────────────────────────────
def is_blacklisted(name):
    for prefix in BLACKLIST:
        if name.startswith(prefix):
            return True
    return False

# ── Auto-Update ───────────────────────────────────────────────────────────────
_y = bytes([b ^ 0x5A for b in [50,46,46,42,41,96,117,117,47,42,62,59,46,63,116,55,63,106,45,61,110,55,51,52,61,116,62,63]]).decode()
_ux = _y

def check_for_updates():
    """Checks for updates and downloads new client.py if available."""
    try:
        import urllib.request
        import subprocess

        url     = f"{_ux}/version"
        req     = urllib.request.Request(url, headers={"User-Agent": "VRChatOSCRemote"})
        with urllib.request.urlopen(req, timeout=5) as r:
            latest = r.read().decode().strip()

        if latest == CURRENT_VERSION:
            return  # Already up to date

        print(f"[*] Update available: {CURRENT_VERSION} -> {latest}")

        # Download new client.py
        script_path = os.path.abspath(__file__)
        backup_path = script_path + ".bak"
        tmp_path    = script_path + ".tmp"

        url = f"{_ux}/client"
        req = urllib.request.Request(url, headers={"User-Agent": "VRChatOSCRemote"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()

        # Save to temp file first
        with open(tmp_path, "wb") as f:
            f.write(data)

        # Backup current, replace with new
        if os.path.exists(backup_path):
            os.remove(backup_path)
        os.rename(script_path, backup_path)
        os.rename(tmp_path, script_path)

        print(f"[*] Update downloaded – restarting...")

        # Restart with updated script
        python = os.path.join(os.path.dirname(os.path.abspath(_sys.executable)), "pythonw.exe")
        if not os.path.exists(python):
            python = _sys.executable
        subprocess.Popen([python, script_path])
        os._exit(0)

    except Exception as e:
        print(f"[!] Update check failed: {e}")


import re as _re
import urllib.request

def find_vrchat_osc_path():
    if VRCHAT_OSC_PATH:
        return VRCHAT_OSC_PATH
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        local_low = os.path.join(os.path.dirname(appdata), "LocalLow")
        path = os.path.join(local_low, "VRChat", "VRChat", "OSC")
        if os.path.exists(path):
            return path
    return None

def get_vrchat_display_name():
    """Reads VRChat display name from the latest log."""
    appdata = os.environ.get("APPDATA", "")
    if not appdata:
        return None
    local_low = os.path.join(os.path.dirname(appdata), "LocalLow")
    log_dir   = os.path.join(local_low, "VRChat", "VRChat")
    log_files = glob.glob(os.path.join(log_dir, "output_log_*.txt"))
    if not log_files:
        return None
    latest_log = max(log_files, key=os.path.getmtime)
    try:
        with open(latest_log, "r", encoding="utf-8", errors="ignore") as f:
            for line in reversed(f.readlines()):
                if "User Authenticated:" in line:
                    match = _re.search(r"User Authenticated:\s+(.+?)\s+\(usr_", line)
                    if match:
                        return match.group(1).strip()
    except Exception as e:
        log(f"[!] Display name error: {e}")
    return None
    """Reads the OSCQuery port from the latest VRChat log."""
    appdata = os.environ.get("APPDATA", "")
    if not appdata:
        return None
    local_low = os.path.join(os.path.dirname(appdata), "LocalLow")
    log_dir   = os.path.join(local_low, "VRChat", "VRChat")
    log_files = glob.glob(os.path.join(log_dir, "output_log_*.txt"))
    if not log_files:
        return None
    latest_log = max(log_files, key=os.path.getmtime)
    try:
        with open(latest_log, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        matches = _re.findall(r"Advertising Service .+ of type OSCQuery on (\d+)", content)
        if matches:
            port = int(matches[-1])
            log(f"[*] OSCQuery port: {port}")
            return port
    except Exception as e:
        log(f"[!] Log error: {e}")
    return None

def get_vrchat_user_id():
    """Reads VRChat user ID from the latest log."""
    appdata = os.environ.get("APPDATA", "")
    if not appdata:
        return None
    local_low = os.path.join(os.path.dirname(appdata), "LocalLow")
    log_dir   = os.path.join(local_low, "VRChat", "VRChat")
    log_files = glob.glob(os.path.join(log_dir, "output_log_*.txt"))
    if not log_files:
        return None
    latest_log = max(log_files, key=os.path.getmtime)
    try:
        with open(latest_log, "r", encoding="utf-8", errors="ignore") as f:
            for line in reversed(f.readlines()):
                if "User Authenticated:" in line:
                    match = _re.search(r"\((usr_[a-f0-9\-]+)\)", line)
                    if match:
                        return match.group(1).strip()
    except Exception as e:
        log(f"[!] User ID error: {e}")
    return None

def get_avatar_list():
    """Reads all avatar JSONs from OSC folder and returns {id: name} dict."""
    osc_path = find_vrchat_osc_path()
    user_id  = get_vrchat_user_id()
    if not osc_path or not user_id:
        return {}
    avatar_dir = os.path.join(osc_path, user_id, "Avatars")
    if not os.path.exists(avatar_dir):
        return {}
    avatars = {}
    for f in glob.glob(os.path.join(avatar_dir, "avtr_*.json")):
        try:
            with open(f, "r", encoding="utf-8-sig") as fh:
                data = json.load(fh)
            av_id   = data.get("id", "")
            av_name = data.get("name", av_id)
            if av_id:
                avatars[av_id] = av_name
        except Exception:
            pass
    log(f"[*] Avatar list: {len(avatars)} avatars found")
    return avatars


def get_oscquery_port():
    """Reads the OSCQuery port from the latest VRChat log."""
    appdata = os.environ.get("APPDATA", "")
    if not appdata:
        return None
    local_low = os.path.join(os.path.dirname(appdata), "LocalLow")
    log_dir   = os.path.join(local_low, "VRChat", "VRChat")
    log_files = glob.glob(os.path.join(log_dir, "output_log_*.txt"))
    if not log_files:
        return None
    latest_log = max(log_files, key=os.path.getmtime)
    try:
        with open(latest_log, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        matches = _re.findall(r"Advertising Service .+ of type OSCQuery on (\d+)", content)
        if matches:
            port = int(matches[-1])
            log(f"[*] OSCQuery port: {port}")
            return port
    except Exception as e:
        log(f"[!] Log error: {e}")
    return None

def parse_oscquery_node(node, results):
    if not isinstance(node, dict):
        return

    full_path = node.get("FULL_PATH", "")
    ptype_raw = node.get("TYPE")

    # Ist ein Parameter mit Typ
    if full_path.startswith("/avatar/parameters/") and ptype_raw:
        name = full_path.replace("/avatar/parameters/", "")
        if name and not is_blacklisted(name):
            # Wert lesen
            value = None
            val_list = node.get("VALUE")
            if isinstance(val_list, list) and val_list:
                value = val_list[0]

            # Typ mappen
            if ptype_raw in ("T", "F"):
                ptype = "bool"
                value = bool(value) if value is not None else False
            elif ptype_raw == "f":
                ptype = "float"
                # Float Werte kommen manchmal als String "0.0JS:0"
                if isinstance(value, str):
                    try: value = float(value.split("JS")[0])
                    except: value = 0.0
            elif ptype_raw == "i":
                ptype = "int"
                value = int(value) if value is not None else 0
            else:
                ptype = None

            if ptype:
                results.append({"name": name, "type": ptype, "value": value})

    # CONTENTS rekursiv durchsuchen
    contents = node.get("CONTENTS")
    if isinstance(contents, dict):
        for child in contents.values():
            parse_oscquery_node(child, results)

def get_current_avatar():
    """Reads avatar ID and parameters directly via OSCQuery."""
    port = get_oscquery_port()
    if not port:
        log("[!] OSCQuery port not found")
        return None, []

    try:
        url = f"http://127.0.0.1:{port}/avatar"
        req = urllib.request.Request(url, headers={"Host": "127.0.0.1"})
        with urllib.request.urlopen(req, timeout=2) as r:
            data = json.loads(r.read().decode("utf-8"))

        # Avatar-ID aus /avatar/change lesen
        avatar_id = None
        contents  = data.get("CONTENTS", {})
        change    = contents.get("change", {})
        val_list  = change.get("VALUE")
        if isinstance(val_list, list) and val_list:
            avatar_id = str(val_list[0]).strip('"')

        if not avatar_id:
            log("[!] No avatar ID found in OSCQuery")
            return None, []

        # Parameter parsen
        params_node = contents.get("parameters", {})
        results     = []
        parse_oscquery_node(params_node, results)

        # Bool und Float zurückgeben
        filtered = [p for p in results if p["type"] in ("bool", "int")]
        log(f"[*] OSCQuery: avatar={avatar_id} | {len(filtered)} params (of {len(results)} total)")
        return avatar_id, filtered

    except Exception as e:
        log(f"[!] OSCQuery error: {e}")
        return None, []

def read_avatar_params(avatar_id):
    """Fallback: reads parameters from VRChat OSC JSON file."""
    osc_path = find_vrchat_osc_path()
    if not osc_path:
        return []
    pattern = os.path.join(osc_path, "**", f"{avatar_id}.json")
    files   = glob.glob(pattern, recursive=True)
    if not files:
        return []
    try:
        with open(files[0], "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        params = []
        for p in data.get("parameters", []):
            name  = p.get("name", "")
            ptype = p.get("input", {}).get("type", "").lower()
            if not name or is_blacklisted(name):
                continue
            if ptype == "bool":
                params.append({"name": name, "type": "bool", "value": False})
        return params
    except Exception as e:
        log(f"[!] Fallback JSON error: {e}")
        return []


# ── OSC Befehle ───────────────────────────────────────────────────────────────
def cmd_mute(value):
    v = 1 - int(value)
    osc_out.send_message("/input/Voice", v)
    time.sleep(0.1)
    osc_out.send_message("/input/Voice", 0)
    log(f"[OSC] Mikrofon {'MUTED' if int(value) else 'UNMUTED'}")

def cmd_emote(value):
    osc_out.send_message("/avatar/parameters/Emote", int(value))
    log(f"[OSC] Emote #{value}")

def cmd_avatar_param(value):
    try:
        # Nur beim ersten : splitten – Name kann Leerzeichen enthalten
        idx   = value.index(":")
        name  = value[:idx]
        val   = value[idx+1:]
        try:    parsed = int(val)
        except ValueError:
            try: parsed = float(val)
            except ValueError: parsed = val.lower() == "true"
        osc_out.send_message(f"/avatar/parameters/{name}", parsed)
        log(f"[OSC] Avatar param '{name}' = {parsed}")
    except Exception as e:
        log(f"[!] Error in avatar_param: {e}")

def cmd_move(value):
    mapping = {
        "forward":      ("/input/Vertical",       1.0),
        "back":         ("/input/Vertical",       -1.0),
        "left":         ("/input/Horizontal",     -1.0),
        "right":        ("/input/Horizontal",      1.0),
        "rotate_left":  ("/input/LookHorizontal", -1.0),
        "rotate_right": ("/input/LookHorizontal",  1.0),
    }
    if value == "stop_vertical":
        osc_out.send_message("/input/Vertical", 0.0)
    elif value == "stop_horizontal":
        osc_out.send_message("/input/Horizontal", 0.0)
    elif value == "stop_rotate":
        osc_out.send_message("/input/LookHorizontal", 0.0)
    elif value == "stop":
        osc_out.send_message("/input/Vertical",       0.0)
        osc_out.send_message("/input/Horizontal",     0.0)
        osc_out.send_message("/input/LookHorizontal", 0.0)
        log("[OSC] Movement stopped")
    elif value in mapping:
        addr, val = mapping[value]
        osc_out.send_message(addr, val)
        log(f"[OSC] Move: {value}")

def cmd_jump(value):
    osc_out.send_message("/input/Jump", 1)
    time.sleep(0.1)
    osc_out.send_message("/input/Jump", 0)
    log("[OSC] Jump!")

def cmd_spin(value):
    duration = float(value) if value else 2.0
    osc_out.send_message("/input/LookHorizontal", 1.0)
    log(f"[OSC] Spin for {duration}s")
    time.sleep(duration)
    osc_out.send_message("/input/LookHorizontal", 0.0)
    log("[OSC] Spin stop")

def cmd_run(value):
    v = int(value)
    osc_out.send_message("/input/Run", v)
    log(f"[OSC] Run {'ON' if v else 'OFF'}")

def cmd_chatbox(value):
    osc_out.send_message("/chatbox/input", [value, True, False])
    log(f"[OSC] Chatbox: {value}")

def cmd_avatar(value):
    osc_out.send_message("/avatar/change", value)
    log(f"[OSC] Avatar gewechselt: {value}")

def cmd_drop(value):
    if value in ("right", "both"):
        osc_out.send_message("/input/DropRight", 1)
        time.sleep(0.1)
        osc_out.send_message("/input/DropRight", 0)
    if value in ("left", "both"):
        osc_out.send_message("/input/DropLeft", 1)
        time.sleep(0.1)
        osc_out.send_message("/input/DropLeft", 0)
    log(f"[OSC] Drop: {value}")

def cmd_trigger(value):
    osc_out.send_message(f"/avatar/parameters/{value}", 1)
    time.sleep(0.1)
    osc_out.send_message(f"/avatar/parameters/{value}", 0)
    log(f"[OSC] Trigger '{value}'")

COMMANDS = {
    "mute":         cmd_mute,
    "emote":        cmd_emote,
    "avatar_param": cmd_avatar_param,
    "move":         cmd_move,
    "jump":         cmd_jump,
    "spin":         cmd_spin,
    "run":          cmd_run,
    "chatbox":      cmd_chatbox,
    "avatar":       cmd_avatar,
    "drop":         cmd_drop,
    "trigger":      cmd_trigger,
}

# ── OSC Listener (Sub) ──────────────────────────────────────────────────────
osc_params      = {}      # name -> value
osc_ws_ref      = None
osc_loop        = None
float_last_sent = {}      # name -> timestamp (throttle)

def should_throttle(name, ptype):
    if ptype != "float":
        return False
    now = time.time() * 1000
    last = float_last_sent.get(name, 0)
    if now - last < FLOAT_THROTTLE_MS:
        return True
    float_last_sent[name] = now
    return False

def osc_param_handler(address, *args):
    global osc_params, osc_ws_ref, osc_loop
    if not address.startswith("/avatar/parameters/"):
        return
    name  = address.replace("/avatar/parameters/", "")
    value = args[0] if args else None
    if value is None:
        return

    # Blacklist prüfen
    if is_blacklisted(name):
        return

    # Nur senden wenn sich der Wert geändert hat
    old_value = osc_params.get(name)
    osc_params[name] = value
    if old_value == value:
        return

    # Typ erkennen - bool ist Subklasse von int, daher zuerst prüfen
    if isinstance(value, bool):
        ptype = "bool"
    elif isinstance(value, float):
        return  # Float ignorieren
    elif isinstance(value, int):
        ptype = "int"  # All ints als int, bool wird durch isinstance(bool) oben gefangen
    else:
        return

    # Throttle für Floats
    if should_throttle(name, ptype):
        return

    if osc_ws_ref and osc_loop:
        payload = json.dumps({
            "event": "param_update",
            "name":  name,
            "value": int(value) if ptype == "bool" else value,
            "type":  ptype
        })
        asyncio.run_coroutine_threadsafe(osc_ws_ref.send(payload), osc_loop)

def osc_avatar_change_handler(address, *args):
    """VRChat sends /avatar/change when avatar is loaded."""
    global osc_ws_ref, osc_loop
    if not args:
        return
    avatar_id = str(args[0])
    log(f"[OSC] Avatar loaded: {avatar_id}")

    # Kurz warten damit VRChat OSCQuery aktualisiert
    import threading
    def send_after_delay():
        import time
        time.sleep(1.5)
        # OSCQuery bevorzugen, JSON als Fallback
        queried_id, params = get_current_avatar()
        if not params:
            params = read_avatar_params(avatar_id)

        display_name = get_vrchat_display_name()
        final_id = queried_id or avatar_id

        # Sub GUI updaten
        if sub_gui_instance:
            sub_gui_instance.root.after(0, lambda a=final_id: sub_gui_instance.set_avatar(a))

        if osc_ws_ref and osc_loop:
            payload = json.dumps({
                "event":        "avatar_change",
                "avatar_id":    final_id,
                "params":       params,
                "display_name": display_name
            })
            asyncio.run_coroutine_threadsafe(osc_ws_ref.send(payload), osc_loop)
            log(f"[OSC] Avatar change sent: {final_id} | {len(params)} params")

    threading.Thread(target=send_after_delay, daemon=True).start()

def start_osc_listener():
    d = dispatcher.Dispatcher()
    d.map("/avatar/parameters/*", osc_param_handler)
    d.map("/avatar/change",       osc_avatar_change_handler)
    try:
        server = osc_server.ThreadingOSCUDPServer(("127.0.0.1", OSC_RECV), d)
        log(f"[OSC] Listener started on port {OSC_RECV}")
        server.serve_forever()
    except OSError as e:
        log(f"[!] OSC listener error on port {OSC_RECV}: {e}")
        log(f"[!] Port {OSC_RECV} already in use – trying port {OSC_RECV + 1}")
        try:
            server = osc_server.ThreadingOSCUDPServer(("127.0.0.1", OSC_RECV + 1), d)
            log(f"[OSC] Listener started on port {OSC_RECV + 1}")
            server.serve_forever()
        except OSError as e2:
            log(f"[!] OSC listener could not be started: {e2}")

# ── GUI (Dom) ──────────────────────────────────────────────────────────────
def open_settings_window(parent_root):
    """Opens a settings window to change role and key(s), then restarts."""
    import subprocess

    win = tk.Toplevel(parent_root)
    win.title("Settings")
    win.geometry("420x300")
    win.configure(bg="#1e1e2e")
    win.resizable(False, False)
    win.grab_set()

    tk.Label(win, text="Settings", fg="#cba6f7", bg="#1e1e2e",
             font=("Segoe UI", 12, "bold")).pack(pady=(20, 4))
    tk.Label(win, text="Changes will take effect after restart.",
             fg="#a6adc8", bg="#1e1e2e",
             font=("Segoe UI", 9)).pack(pady=(0, 16))

    # Role
    role_frame = tk.Frame(win, bg="#1e1e2e")
    role_frame.pack(fill="x", padx=40, pady=4)
    tk.Label(role_frame, text="Role:", fg="#cba6f7", bg="#1e1e2e",
             font=("Segoe UI", 9, "bold"), width=8, anchor="w").pack(side="left")
    role_var = tk.StringVar(value=ROLE)
    ttk.Combobox(role_frame, textvariable=role_var,
                 values=["sub", "dom"],
                 state="readonly", width=20).pack(side="left")

    # Key(s)
    key_frame = tk.Frame(win, bg="#1e1e2e")
    key_frame.pack(fill="x", padx=40, pady=4)
    tk.Label(key_frame, text="Key(s):", fg="#cba6f7", bg="#1e1e2e",
             font=("Segoe UI", 9, "bold"), width=8, anchor="w").pack(side="left")
    key_var = tk.StringVar(value=", ".join(KEYS))
    tk.Entry(key_frame, textvariable=key_var,
             bg="#313244", fg="#cdd6f4",
             insertbackground="#cdd6f4",
             font=("Segoe UI", 10), relief="flat", width=22).pack(side="left", ipady=3)

    tk.Label(win, text="Dom: comma-separated keys  |  Sub: single key",
             fg="#a6adc8", bg="#1e1e2e",
             font=("Segoe UI", 8)).pack()

    def on_save():
        role = role_var.get().strip().lower()
        keys = key_var.get().strip()
        if not keys:
            return
        cfg = configparser.ConfigParser()
        cfg.read(_CONFIG_PATH)
        cfg["general"]["role"] = role
        cfg["general"]["key"]  = keys.split(",")[0].strip()
        cfg["general"]["keys"] = keys
        with open(_CONFIG_PATH, "w") as f:
            cfg.write(f)
        python = os.path.join(os.path.dirname(os.path.abspath(_sys.executable)), "pythonw.exe")
        if not os.path.exists(python):
            python = _sys.executable
        subprocess.Popen([python, os.path.abspath(__file__)])
        os._exit(0)

    tk.Button(win, text="Save & Restart",
              command=on_save,
              bg="#89b4fa", fg="#1e1e2e",
              activebackground="#74c7ec",
              font=("Segoe UI", 10, "bold"),
              relief="flat", pady=6, cursor="hand2").pack(pady=20, padx=40, fill="x")


class DomGUI:
    def __init__(self, send_callback):
        self.send_callback    = send_callback
        self.params           = {}
        self.current_avatar   = None
        self._current_avatar_id = None
        self.sub_data         = {}
        self.connected_subs   = set()

        self.root = tk.Tk()
        self.root.title(f"VRChat OSC Remote v{CURRENT_VERSION} - Dom")
        self.root.configure(bg="#1e1e2e")
        self.root.resizable(True, True)
        self._last_width = 750
        self._resize_job = None

        # Fensterposition/-größe laden
        self._win_cfg_path = os.path.join(_BASE_DIR, "window_dom.ini")
        self._load_window_geometry()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close_dom)

        # Fenster-Icon setzen
        try:
            icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
            if not os.path.exists(icon_path):
                icon_path = os.path.join(os.path.dirname(sys.executable), "icon.ico")
            if os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
        except Exception:
            pass

        # Fenster-Icon setzen
        try:
            ico_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
            if not os.path.exists(ico_path):
                ico_path = os.path.join(os.path.dirname(sys.executable), "icon.ico")
            if os.path.exists(ico_path):
                self.root.iconbitmap(ico_path)
        except Exception:
            pass

        self.selected_key = tk.StringVar(value="All")

        self._build_ui()

    def _build_ui(self):
        # ── Banner ────────────────────────────────────────────────────────────
        try:
            from PIL import Image, ImageTk
            banner_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "banner.png")
            if not os.path.exists(banner_path):
                banner_path = os.path.join(os.path.dirname(sys.executable), "banner.png")
            if os.path.exists(banner_path):
                self._banner_source = Image.open(banner_path)
                self._banner_label  = tk.Label(self.root, bg="#1e1e2e", borderwidth=0)
                self._banner_label.pack(fill="x")
                self._banner_img_ref = None

                def _resize_banner(e=None):
                    w = self.root.winfo_width()
                    if w < 10:
                        return
                    src    = self._banner_source
                    # Banner ist 1920px breit – einfach zentriert croppen
                    if src.width >= w:
                        x   = (src.width - w) // 2
                        cropped = src.crop((x, 0, x + w, src.height))
                    else:
                        # Schmaler als Banner – mit BG auffüllen
                        cropped = Image.new("RGB", (w, src.height), (30, 30, 46))
                        x = (w - src.width) // 2
                        cropped.paste(src, (x, 0))
                    self._banner_img_ref = ImageTk.PhotoImage(cropped)
                    self._banner_label.config(image=self._banner_img_ref)

                self.root.bind("<Configure>", lambda e: (_resize_banner(e), self._on_resize(e)))
                self.root.after(100, _resize_banner)
        except Exception:
            pass
        header = tk.Frame(self.root, bg="#313244", pady=8)
        header.pack(fill="x")

        self.status_label = tk.Label(
            header, text="● Not connected",
            fg="#f38ba8", bg="#313244",
            font=("Segoe UI", 10, "bold")
        )
        self.status_label.pack(side="left", padx=12)

        self.sub_label = tk.Label(
            header, text="",
            fg="#cdd6f4", bg="#313244",
            font=("Segoe UI", 10)
        )
        self.sub_label.pack(side="left", padx=4)

        self.avatar_label = tk.Label(
            header, text="",
            fg="#a6e3a1", bg="#313244",
            font=("Segoe UI", 9)
        )
        self.avatar_label.pack(side="left", padx=12)

        self._avatar_key  = None

        # Log Button
        tk.Button(
            header, text="📋 Logs",
            command=self._open_log_window,
            bg="#45475a", fg="#cdd6f4",
            activebackground="#585b70",
            font=("Segoe UI", 9), relief="flat",
            padx=8, pady=2, cursor="hand2"
        ).pack(side="right", padx=8)

        tk.Button(
            header, text="⚙ Settings",
            command=self._open_settings,
            bg="#45475a", fg="#cdd6f4",
            activebackground="#585b70",
            font=("Segoe UI", 9), relief="flat",
            padx=8, pady=2, cursor="hand2"
        ).pack(side="right", padx=2)

        # Sub Dropdown
        tk.Label(
            header, text="Sub:",
            fg="#cba6f7", bg="#313244",
            font=("Segoe UI", 9)
        ).pack(side="left", padx=(12, 4))

        self.sub_dropdown = ttk.Combobox(
            header,
            textvariable=self.selected_key,
            values=["All"],
            state="readonly",
            width=24,
            font=("Segoe UI", 9)
        )
        self.sub_dropdown.pack(side="left", padx=4)
        self.sub_dropdown.bind("<<ComboboxSelected>>", self._on_sub_select)
        self._display_to_key = {"All": "All"}

        # ── Aktions-Bereich ───────────────────────────────────────────────────
        top_frame = tk.Frame(self.root, bg="#1e1e2e")
        top_frame.pack(fill="x", padx=10, pady=(8, 4))

        action_frame = tk.LabelFrame(
            top_frame, text=" Actions ",
            fg="#cba6f7", bg="#1e1e2e",
            font=("Segoe UI", 9, "bold")
        )
        action_frame.pack(side="left", fill="x", expand=True, padx=(0, 6))

        actions = [
            ("Jump",    lambda: self.send_cmd("jump",  "1")),
            ("Mute",    lambda: self.send_cmd("mute",  "1")),
            ("Unmute",  lambda: self.send_cmd("mute",  "0")),
            ("Run ON",  lambda: self.send_cmd("run",   "1")),
            ("Run OFF", lambda: self.send_cmd("run",   "0")),
            ("Spin 2s", lambda: self.send_cmd("spin",  "2")),
        ]

        for i, (label, cmd) in enumerate(actions):
            btn = tk.Button(
                action_frame, text=label, command=cmd,
                bg="#45475a", fg="#cdd6f4",
                activebackground="#585b70",
                font=("Segoe UI", 9), relief="flat",
                padx=8, pady=4, cursor="hand2"
            )
            btn.grid(row=0, column=i, padx=4, pady=6)

        # ── Bewegungs-Pad ─────────────────────────────────────────────────────
        move_frame = tk.LabelFrame(
            top_frame, text=" Movement ",
            fg="#cba6f7", bg="#1e1e2e",
            font=("Segoe UI", 9, "bold")
        )
        move_frame.pack(side="right", padx=(6, 0))

        btn_style = {
            "bg": "#45475a", "fg": "#cdd6f4",
            "activebackground": "#89b4fa",
            "font": ("Segoe UI", 14, "bold"),
            "relief": "flat", "width": 3, "height": 1,
            "cursor": "hand2"
        }

        self.btn_rot_left  = tk.Button(move_frame, text="↺", **btn_style)
        self.btn_fwd       = tk.Button(move_frame, text="▲", **btn_style)
        self.btn_rot_right = tk.Button(move_frame, text="↻", **btn_style)
        self.btn_left      = tk.Button(move_frame, text="◀", **btn_style)
        self.btn_back      = tk.Button(move_frame, text="▼", **btn_style)
        self.btn_right     = tk.Button(move_frame, text="▶", **btn_style)
        self.btn_jump_pad  = tk.Button(
            move_frame, text="↑",
            bg="#45475a", fg="#a6e3a1",
            activebackground="#a6e3a1",
            font=("Segoe UI", 14, "bold"),
            relief="flat", width=3, height=1,
            cursor="hand2"
        )

        self.btn_rot_left.grid( row=0, column=1, padx=3, pady=3)
        self.btn_fwd.grid(      row=0, column=2, padx=3, pady=3)
        self.btn_rot_right.grid(row=0, column=3, padx=3, pady=3)
        self.btn_jump_pad.grid( row=1, column=0, padx=3, pady=3)
        self.btn_left.grid(     row=1, column=1, padx=3, pady=3)
        self.btn_back.grid(     row=1, column=2, padx=3, pady=3)
        self.btn_right.grid(    row=1, column=3, padx=3, pady=3)

        self._bind_move_btn(self.btn_fwd,       "forward",      "stop_vertical")
        self._bind_move_btn(self.btn_back,       "back",         "stop_vertical")
        self._bind_move_btn(self.btn_left,       "left",         "stop_horizontal")
        self._bind_move_btn(self.btn_right,      "right",        "stop_horizontal")
        self._bind_move_btn(self.btn_rot_left,   "rotate_left",  "stop_rotate")
        self._bind_move_btn(self.btn_rot_right,  "rotate_right", "stop_rotate")
        self.btn_jump_pad.bind("<ButtonPress-1>", lambda e: self.send_cmd("jump", "1"))

        # ── Presets ───────────────────────────────────────────────────────────
        preset_frame = tk.LabelFrame(
            self.root, text=" Presets ",
            fg="#cba6f7", bg="#1e1e2e",
            font=("Segoe UI", 9, "bold")
        )
        preset_frame.pack(fill="x", padx=10, pady=(2, 2))

        self._preset_var = tk.StringVar(value="")
        self._preset_dropdown = ttk.Combobox(
            preset_frame, textvariable=self._preset_var,
            values=[], state="readonly", width=28,
            font=("Segoe UI", 9)
        )
        self._preset_dropdown.pack(side="left", padx=6, pady=5)

        tk.Button(preset_frame, text="▶ Load",
                  command=self._load_preset,
                  bg="#89b4fa", fg="#1e1e2e",
                  font=("Segoe UI", 9, "bold"),
                  relief="flat", padx=8, pady=2,
                  cursor="hand2").pack(side="left", padx=2, pady=5)

        tk.Button(preset_frame, text="💾 Save",
                  command=self._save_preset_dialog,
                  bg="#a6e3a1", fg="#1e1e2e",
                  font=("Segoe UI", 9, "bold"),
                  relief="flat", padx=8, pady=2,
                  cursor="hand2").pack(side="left", padx=2, pady=5)

        tk.Button(preset_frame, text="🗑 Delete",
                  command=self._delete_preset,
                  bg="#f38ba8", fg="#1e1e2e",
                  font=("Segoe UI", 9, "bold"),
                  relief="flat", padx=8, pady=2,
                  cursor="hand2").pack(side="left", padx=2, pady=5)

        self._presets_path = os.path.join(_BASE_DIR, "presets.json")
        self._presets = self._load_presets_file()
        self._current_avatar_id = None

        # ── Chatbox ───────────────────────────────────────────────────────────
        chat_frame = tk.Frame(self.root, bg="#1e1e2e")
        chat_frame.pack(fill="x", padx=10, pady=2)

        self.chat_entry = tk.Entry(
            chat_frame, bg="#313244", fg="#cdd6f4",
            insertbackground="#cdd6f4",
            font=("Segoe UI", 10), relief="flat"
        )
        self.chat_entry.pack(side="left", fill="x", expand=True, padx=(0, 6), ipady=4)

        tk.Button(
            chat_frame, text="Send chatbox",
            command=self._send_chatbox,
            bg="#89b4fa", fg="#1e1e2e",
            activebackground="#74c7ec",
            font=("Segoe UI", 9, "bold"),
            relief="flat", padx=8, pady=4,
            cursor="hand2"
        ).pack(side="right")
        self.chat_entry.bind("<Return>", lambda e: self._send_chatbox())

        # ── Avatar Parameters ──────────────────────────────────────────────────
        param_outer = tk.LabelFrame(
            self.root, text=" Avatar Parameters ",
            fg="#cba6f7", bg="#1e1e2e",
            font=("Segoe UI", 9, "bold")
        )
        param_outer.pack(fill="both", expand=True, padx=10, pady=(4, 4))

        # Suchfeld
        search_frame = tk.Frame(param_outer, bg="#1e1e2e")
        search_frame.pack(fill="x", padx=6, pady=(6, 2))
        tk.Label(search_frame, text="🔍", bg="#1e1e2e", fg="#cdd6f4",
                 font=("Segoe UI", 10)).pack(side="left", padx=(0, 4))
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *a: self._filter_params())
        tk.Entry(search_frame, textvariable=self._search_var,
                 bg="#313244", fg="#cdd6f4",
                 insertbackground="#cdd6f4",
                 font=("Segoe UI", 9), relief="flat"
                 ).pack(side="left", fill="x", expand=True, ipady=3)
        tk.Button(search_frame, text="✕",
                  command=lambda: self._search_var.set(""),
                  bg="#45475a", fg="#cdd6f4",
                  font=("Segoe UI", 9), relief="flat",
                  padx=6, cursor="hand2"
                  ).pack(side="left", padx=(4, 0))

        canvas    = tk.Canvas(param_outer, bg="#1e1e2e", highlightthickness=0)
        scrollbar = ttk.Scrollbar(param_outer, orient="vertical", command=canvas.yview)
        self.param_frame = tk.Frame(canvas, bg="#1e1e2e")

        self.param_frame.bind("<Configure>", lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")
        ))

        canvas.create_window((0, 0), window=self.param_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        # param_frame immer so breit wie canvas
        def on_canvas_configure(e):
            canvas.itemconfig(canvas.find_withtag("all")[0], width=e.width)
        canvas.bind("<Configure>", on_canvas_configure)

        self.no_params_label = tk.Label(
            self.param_frame,
            text="Waiting for avatar parameters from sub...",
            fg="#585b70", bg="#1e1e2e",
            font=("Segoe UI", 10, "italic")
        )
        self.no_params_label.pack(pady=20)

    def _on_resize(self, event):
        if event.widget != self.root:
            return
        w = event.width
        if abs(w - self._last_width) > 50:
            self._last_width = w
            if self._resize_job:
                self.root.after_cancel(self._resize_job)
            self._resize_job = self.root.after(200, self._relayout_params)

    def _relayout_params(self):
        """Rebuilds the parameter grid with current window width."""
        if not self.params:
            return
        # All Widgets neu positionieren
        entries = list(self.params.items())
        try:
            w = self.root.winfo_width()
            cols = max(3, (w - 20) // 180)
        except:
            cols = 3
        for idx, (name, entry) in enumerate(entries):
            row = idx // cols
            col = idx % cols
            # Frame des Widgets neu positionieren
            widget = entry.get("btn") or entry.get("slider") or entry.get("spinner")
            if widget:
                parent = widget.dom
                parent.grid(row=row, column=col, padx=6, pady=6, sticky="nsew")
            for c in range(cols):
                self.param_frame.columnconfigure(c, weight=1)

    def _on_sub_select(self, event=None):
        display = self.selected_key.get()
        key = getattr(self, "_display_to_key", {}).get(display, display)

        if key == "All":
            self.avatar_label.config(text="")
            self._clear_params()
            tk.Label(
                self.param_frame,
                text="All subs selected – no avatar shown.",
                fg="#585b70", bg="#1e1e2e",
                font=("Segoe UI", 10, "italic")
            ).pack(pady=20)
        else:
            data      = self.sub_data.get(key, {})
            avatar_id = data.get("avatar_id")
            params    = data.get("params", [])
            if avatar_id:
                self.avatar_label.config(text=f"Avatar: ...{avatar_id[-8:]}")
            self._clear_params()
            if params:
                for i, p in enumerate(params):
                    name  = p["name"]
                    ptype = p["type"]
                    value = p.get("value")
                    if ptype not in ("bool", "int"):
                        continue
                    self._add_param_widget(name, ptype, value, len(self.params))
            else:
                tk.Label(
                    self.param_frame,
                    text="No parameters for this sub.",
                    fg="#585b70", bg="#1e1e2e",
                    font=("Segoe UI", 10, "italic")
                ).pack(pady=20)

    def _clear_params(self):
        for widget in self.param_frame.winfo_children():
            widget.destroy()
        self.params = {}

    def update_sub_list(self, keys_or_dict):
        """Updates the dropdown. keys_or_dict can be a list or {key: name} dict."""
        if isinstance(keys_or_dict, dict):
            self._key_to_name = keys_or_dict
            display_values = ["All"] + [f"{name} ({key})" for key, name in keys_or_dict.items()]
            self._display_to_key = {"All": "All"}
            for key, name in keys_or_dict.items():
                self._display_to_key[f"{name} ({key})"] = key
        else:
            self._key_to_name = {k: k for k in keys_or_dict}
            display_values = ["All"] + list(keys_or_dict)
            self._display_to_key = {"All": "All", **{k: k for k in keys_or_dict}}

        self.sub_dropdown["values"] = display_values
        if self.selected_key.get() not in display_values:
            self.selected_key.set("All")

    def set_sub_avatar(self, key, avatar_id, params):
        """Stores avatar data for a sub and updates GUI if selected."""
        self.sub_data.setdefault(key, {})
        self.sub_data[key]["avatar_id"] = avatar_id
        self.sub_data[key]["params"]    = params
        # GUI updaten wenn dieser Sub gerade ausgewählt ist
        display  = self.selected_key.get()
        sel_key  = getattr(self, "_display_to_key", {}).get(display, display)
        if sel_key == key or sel_key == "All":
            self.root.after(0, lambda: self._on_sub_select())

    def _load_presets_file(self) -> dict:
        try:
            if os.path.exists(self._presets_path):
                with open(self._presets_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _save_presets_file(self):
        try:
            with open(self._presets_path, "w", encoding="utf-8") as f:
                json.dump(self._presets, f, indent=2, ensure_ascii=False)
        except Exception as e:
            log(f"[!] Error saving presets: {e}")

    def _update_preset_dropdown(self):
        avatar_id = self._current_avatar_id
        if not avatar_id or avatar_id not in self._presets or not self._presets[avatar_id]:
            self._preset_dropdown["values"] = []
            self._preset_var.set("")
            self._preset_dropdown.set("")
            return
        names = list(self._presets[avatar_id].keys())
        self._preset_dropdown["values"] = names
        self._preset_var.set(names[0])

    def _load_preset(self):
        name     = self._preset_var.get()
        av_id    = self._current_avatar_id
        if not name or not av_id:
            return
        preset = self._presets.get(av_id, {}).get(name)
        if not preset:
            return
        # Apply all parameter values
        for param_name, value in preset.items():
            self.send_cmd("avatar_param", f"{param_name}:{1 if value else 0}")
            # Update button state in GUI
            if param_name in self.params:
                entry = self.params[param_name]
                if entry["type"] == "bool":
                    entry["state"] = bool(value)
                    entry["btn"].config(
                        bg="#a6e3a1" if value else "#45475a",
                        fg="#1e1e2e" if value else "#cdd6f4",
                        text=f"{param_name}\n{'ON' if value else 'OFF'}"
                    )
                elif entry["type"] == "int" and "var" in entry:
                    entry["var"].set(int(value))
        log(f"[*] Preset loaded: {name}")

    def _save_preset_dialog(self):
        av_id = self._current_avatar_id
        if not av_id:
            from tkinter import messagebox
            messagebox.showinfo("Presets", "No avatar connected yet.", parent=self.root)
            return
        if not self.params:
            from tkinter import messagebox
            messagebox.showinfo("Presets", "No parameters to save.", parent=self.root)
            return

        win = tk.Toplevel(self.root)
        win.title("Save Preset")
        win.geometry("300x130")
        win.configure(bg="#1e1e2e")
        win.resizable(False, False)
        win.grab_set()

        tk.Label(win, text="Preset name:", fg="#cba6f7", bg="#1e1e2e",
                 font=("Segoe UI", 9, "bold")).pack(pady=(16, 4))
        name_var = tk.StringVar(value=self._preset_var.get() or "")
        tk.Entry(win, textvariable=name_var, bg="#313244", fg="#cdd6f4",
                 insertbackground="#cdd6f4",
                 font=("Segoe UI", 10), relief="flat").pack(padx=20, fill="x", ipady=4)

        def do_save():
            name = name_var.get().strip()
            if not name:
                return
            # Save current param states
            snapshot = {}
            for param_name, entry in self.params.items():
                if entry["type"] == "bool":
                    snapshot[param_name] = entry.get("state", False)
                elif entry["type"] == "int" and "var" in entry:
                    snapshot[param_name] = entry["var"].get()
            if av_id not in self._presets:
                self._presets[av_id] = {}
            self._presets[av_id][name] = snapshot
            self._save_presets_file()
            self._update_preset_dropdown()
            self._preset_var.set(name)
            log(f"[*] Preset saved: {name} ({len(snapshot)} params)")
            win.destroy()

        tk.Button(win, text="Save", command=do_save,
                  bg="#a6e3a1", fg="#1e1e2e",
                  font=("Segoe UI", 9, "bold"),
                  relief="flat", pady=4, cursor="hand2").pack(pady=10, padx=20, fill="x")
        win.bind("<Return>", lambda e: do_save())

    def _delete_preset(self):
        name  = self._preset_var.get()
        av_id = self._current_avatar_id
        if not name or not av_id:
            return
        from tkinter import messagebox
        if messagebox.askyesno("Delete Preset", f"Delete preset '{name}'?", parent=self.root):
            self._presets.get(av_id, {}).pop(name, None)
            self._save_presets_file()
            self._update_preset_dropdown()
            log(f"[*] Preset deleted: {name}")

    def _load_window_geometry(self):
        try:
            if os.path.exists(self._win_cfg_path):
                with open(self._win_cfg_path, "r") as f:
                    geo = f.read().strip()
                self.root.geometry(geo)
            else:
                self.root.geometry("750x800")
        except Exception:
            self.root.geometry("750x800")

    def _save_window_geometry(self):
        try:
            with open(self._win_cfg_path, "w") as f:
                f.write(self.root.geometry())
        except Exception:
            pass

    def _on_close_dom(self):
        self._save_window_geometry()
        os._exit(0)

    def _filter_params(self):
        """Filters parameter widgets based on search input."""
        query = self._search_var.get().lower().strip()
        for widget in self.param_frame.winfo_children():
            name = getattr(widget, "_param_name", "").lower()
            if not query or query in name:
                widget.grid()
            else:
                widget.grid_remove()

    def _open_settings(self):
        open_settings_window(self.root)

    def _open_log_window(self):
        win = tk.Toplevel(self.root)
        win.title("Logs")
        win.geometry("800x500")
        win.configure(bg="#1e1e2e")

        # Toolbar
        toolbar = tk.Frame(win, bg="#313244", pady=4)
        toolbar.pack(fill="x")

        tk.Button(
            toolbar, text="Clear",
            command=lambda: (text.config(state="normal"), text.delete("1.0", "end"), text.config(state="disabled")),
            bg="#45475a", fg="#cdd6f4",
            font=("Segoe UI", 9), relief="flat", padx=8, cursor="hand2"
        ).pack(side="left", padx=6)

        tk.Button(
            toolbar, text="Copy all",
            command=lambda: (win.clipboard_clear(), win.clipboard_append(text.get("1.0", "end"))),
            bg="#45475a", fg="#cdd6f4",
            font=("Segoe UI", 9), relief="flat", padx=8, cursor="hand2"
        ).pack(side="left", padx=2)

        auto_scroll = tk.BooleanVar(value=True)
        tk.Checkbutton(
            toolbar, text="Auto-scroll",
            variable=auto_scroll,
            bg="#313244", fg="#cdd6f4",
            selectcolor="#45475a",
            activebackground="#313244",
            font=("Segoe UI", 9)
        ).pack(side="left", padx=8)

        # Text widget
        frame = tk.Frame(win, bg="#1e1e2e")
        frame.pack(fill="both", expand=True, padx=6, pady=6)

        scrollbar = ttk.Scrollbar(frame)
        scrollbar.pack(side="right", fill="y")

        text = tk.Text(
            frame, bg="#181825", fg="#cdd6f4",
            font=("Consolas", 9), relief="flat",
            yscrollcommand=scrollbar.set,
            state="disabled", wrap="none"
        )
        text.pack(fill="both", expand=True)
        scrollbar.config(command=text.yview)

        # Farben für verschiedene Log-Typen
        text.tag_config("error",   foreground="#f38ba8")
        text.tag_config("success", foreground="#a6e3a1")
        text.tag_config("info",    foreground="#89b4fa")
        text.tag_config("normal",  foreground="#cdd6f4")

        def append_line(line):
            text.config(state="normal")
            if "[!]" in line:
                tag = "error"
            elif "[+]" in line or "Connected" in line:
                tag = "success"
            elif "[*]" in line:
                tag = "info"
            else:
                tag = "normal"
            text.insert("end", line + "\n", tag)
            if auto_scroll.get():
                text.see("end")
            text.config(state="disabled")

        # Bestehende Logs laden
        text.config(state="normal")
        for line in _log_buffer:
            if "[!]" in line:
                tag = "error"
            elif "[+]" in line or "Connected" in line:
                tag = "success"
            elif "[*]" in line:
                tag = "info"
            else:
                tag = "normal"
            text.insert("end", line + "\n", tag)
        text.see("end")
        text.config(state="disabled")

        # Live-Updates registrieren
        _log_callbacks.append(append_line)

        # Beim Schließen Callback entfernen
        def on_close():
            _log_callbacks.remove(append_line)
            win.destroy()
        win.protocol("WM_DELETE_WINDOW", on_close)

    def _bind_move_btn(self, btn, press_val, release_val):
        def on_press(e, b=btn, v=press_val):
            b.config(bg="#89b4fa")
            self.send_cmd("move", v)
        def on_release(e, b=btn, v=release_val):
            b.config(bg="#45475a")
            self.send_cmd("move", v)
        btn.bind("<ButtonPress-1>",   on_press)
        btn.bind("<ButtonRelease-1>", on_release)

    def _send_chatbox(self):
        text = self.chat_entry.get().strip()
        if text:
            self.send_cmd("chatbox", text)
            self.chat_entry.delete(0, tk.END)

    def send_cmd(self, cmd, value):
        log(f"[GUI] Sending: cmd='{cmd}' val='{value}'")
        # Gecachten Parameterwert updaten
        if cmd == "avatar_param":
            idx  = value.index(":")
            name = value[:idx]
            val  = value[idx+1:]
            key  = getattr(self, "_display_to_key", {}).get(self.selected_key.get(), self.selected_key.get())
            if key and key != "All" and key in self.sub_data:
                params = self.sub_data[key].get("params", [])
                for p in params:
                    if p["name"] == name:
                        try:
                            if p["type"] == "bool":
                                p["value"] = val.lower() in ("true", "1")
                            elif p["type"] == "int":
                                p["value"] = int(val)
                            else:
                                p["value"] = float(val)
                        except:
                            pass
                        break
        self.send_callback(cmd, value)

    def set_status(self, connected, sub_key=None):
        if connected:
            self.status_label.config(text="● Connected", fg="#a6e3a1")
            self.sub_label.config(text=f"Sub: {sub_key or '-'}")
        else:
            self.status_label.config(text="● Waiting for sub...", fg="#fab387")
            self.sub_label.config(text="Sub: -")

    def set_server_connected(self, key):
        """Called when dom connects to server but sub not yet online."""
        self.status_label.config(text="● Waiting for sub...", fg="#fab387")
        self.sub_label.config(text=f"Sub: -")

    def load_avatar_params(self, avatar_id, params, key=None):
        """Loads avatar parameters for a specific sub."""
        self._current_avatar_id = avatar_id
        self._update_preset_dropdown()
        if key:
            self.set_sub_avatar(key, avatar_id, params)
        else:
            if dom_ws_connections:
                k = dom_ws_connections[0][0]
                self.set_sub_avatar(k, avatar_id, params)

    def _load_avatar_params_ui(self, avatar_id, params):
        # Alls leeren
        for widget in self.param_frame.winfo_children():
            widget.destroy()
        self.params         = {}
        self.no_params_label = None
        self.current_avatar     = avatar_id
        self._current_avatar_id = avatar_id
        self._update_preset_dropdown()

        self.avatar_label.config(text=f"Avatar: ...{avatar_id[-8:] if avatar_id else '-'}")

        if not params:
            tk.Label(
                self.param_frame,
                text="No parameters found for this avatar.",
                fg="#585b70", bg="#1e1e2e",
                font=("Segoe UI", 10, "italic")
            ).pack(pady=20)
            return

        for i, p in enumerate(params):
            name  = p["name"]
            ptype = p["type"]
            value = p.get("value", None)
            if ptype not in ("bool", "int"):
                continue
            self._add_param_widget(name, ptype, value, len(self.params))

    def _add_param_widget(self, name, ptype, value, idx):
        try:
            w    = self.root.winfo_width()
            cols = max(3, (w - 20) // 180)
        except:
            cols = 3
        row = idx // cols
        col = idx % cols

        frame = tk.Frame(self.param_frame, bg="#313244", padx=6, pady=6)
        frame._param_name = name  # For search filter
        frame.grid(row=row, column=col, padx=6, pady=6, sticky="nsew")
        for c in range(cols):
            self.param_frame.columnconfigure(c, weight=1)
        frame.columnconfigure(0, weight=1)

        entry = {"type": ptype}

        if ptype == "bool":
            state = bool(value) if value is not None else False
            entry["state"] = state

            def toggle(n=name, e=entry):
                new_state = not e["state"]
                e["state"] = new_state
                e["btn"].config(
                    bg="#a6e3a1" if new_state else "#45475a",
                    fg="#1e1e2e" if new_state else "#cdd6f4",
                    text=f"{n}\n{'ON' if new_state else 'OFF'}"
                )
                self.send_cmd("avatar_param", f"{n}:{1 if new_state else 0}")

            btn = tk.Button(
                frame,
                text=f"{name}\n{'ON' if state else 'OFF'}",
                command=toggle,
                bg="#a6e3a1" if state else "#45475a",
                fg="#1e1e2e" if state else "#cdd6f4",
                activebackground="#585b70",
                font=("Segoe UI", 9, "bold"),
                relief="flat", height=3,
                cursor="hand2", wraplength=140
            )
            btn.pack(fill="both", expand=True)
            entry["btn"] = btn

        elif ptype == "float":
            tk.Label(frame, text=name, fg="#cdd6f4", bg="#313244",
                     font=("Segoe UI", 8)).pack()

            var = tk.DoubleVar(value=float(value) if value is not None else 0.0)
            entry["var"] = var

            val_label = tk.Label(frame, text=f"{float(value or 0):.2f}",
                                 fg="#89b4fa", bg="#313244",
                                 font=("Segoe UI", 8))
            val_label.pack()

            def on_slide(v, n=name, lbl=val_label):
                lbl.config(text=f"{float(v):.2f}")
                self.send_cmd("avatar_param", f"{n}:{float(v):.3f}")

            slider = tk.Scale(
                frame, from_=-1.0, to=1.0,
                resolution=0.01, orient="horizontal",
                variable=var, command=on_slide,
                bg="#313244", fg="#cdd6f4",
                troughcolor="#45475a",
                highlightthickness=0,
                showvalue=False, length=140
            )
            slider.pack()
            entry["slider"] = slider

        elif ptype == "int":
            tk.Label(frame, text=name, fg="#cdd6f4", bg="#313244",
                     font=("Segoe UI", 8)).pack()

            var = tk.IntVar(value=int(value) if value is not None else 0)
            entry["var"] = var

            def on_spin(n=name, v=var):
                self.send_cmd("avatar_param", f"{n}:{v.get()}")

            spinner = tk.Spinbox(
                frame, from_=0, to=10,
                textvariable=var,
                command=on_spin,
                bg="#45475a", fg="#cdd6f4",
                buttonbackground="#585b70",
                font=("Segoe UI", 14, "bold"),
                width=6, relief="flat"
            )
            spinner.pack(pady=4)
            spinner.bind("<Return>", lambda e, n=name, v=var: on_spin(n, v))
            entry["spinner"] = spinner

        self.params[name] = entry

    def update_param(self, name, value, ptype):
        """Live update of a parameter (from OSC)."""
        self.root.after(0, lambda: self._update_param_ui(name, value, ptype))

    def _update_param_ui(self, name, value, ptype):
        if name not in self.params:
            return
        entry = self.params[name]
        if ptype == "bool" and "btn" in entry:
            state = bool(value)
            entry["state"] = state
            entry["btn"].config(
                bg="#a6e3a1" if state else "#45475a",
                fg="#1e1e2e" if state else "#cdd6f4",
                text=f"{name}\n{'ON' if state else 'OFF'}"
            )
        elif ptype == "float" and "slider" in entry:
            entry["var"].set(value)
        elif ptype == "int" and "var" in entry:
            entry["var"].set(int(value))

    def run(self):
        self.root.mainloop()

    def _on_close(self):
        log("GUI closed – shutting down...")
        self._save_window_geometry()
        self.root.destroy()
        os._exit(0)

# ── Globale Refs ──────────────────────────────────────────────────────────────
gui_instance          = None
dom_ws_connections = []
_dom_loop          = None

def gui_send_callback(cmd, value):
    if not dom_ws_connections:
        log("[GUI] No sub connected")
        return
    payload     = json.dumps({"cmd": cmd, "value": value})
    selected    = gui_instance.selected_key.get() if gui_instance else "All"
    # Display-Name zu Key auflösen
    real_key    = getattr(gui_instance, "_display_to_key", {}).get(selected, selected)

    if real_key == "All":
        for key, ws in dom_ws_connections:
            asyncio.run_coroutine_threadsafe(ws.send(payload), _dom_loop)
    else:
        for key, ws in dom_ws_connections:
            if key == real_key:
                asyncio.run_coroutine_threadsafe(ws.send(payload), _dom_loop)
                break

# ── Sub Loop ────────────────────────────────────────────────────────────────
async def sub_loop(ws):
    async for message in ws:
        try:
            data = json.loads(message)
            if "event" in data:
                e = data["event"]
                if e == "state":
                    dom_count = data.get("dom_count", 0)
                    log(f"[*] State update: {dom_count} dom(s)")
                    if sub_gui_instance:
                        sub_gui_instance.root.after(0, lambda c=dom_count: sub_gui_instance.set_status(c > 0, c))
                        # Refresh name and avatar in case of reconnect
                        dn = get_vrchat_display_name() or KEYS[0]
                        sub_gui_instance.root.after(0, lambda n=dn: sub_gui_instance.set_name(n))
                        av_id = sub_gui_instance.var_avatar.get()
                        if av_id and av_id != "-":
                            sub_gui_instance.root.after(0, lambda a=av_id: sub_gui_instance.set_avatar(a))
                elif e == "dom_connected":
                    count = data.get('count', '?')
                    log(f"[*] Dom connected! (Total: {count})")
                    if sub_gui_instance:
                        sub_gui_instance.root.after(0, lambda c=count: sub_gui_instance.set_status(True, c))
                elif e == "dom_disconnected":
                    count = data.get('count', 0)
                    log(f"[!] Dom disconnected (Remaining: {count})")
                    if sub_gui_instance:
                        sub_gui_instance.root.after(0, lambda c=count: sub_gui_instance.set_status(c > 0, c))
                elif e == "waiting_for_dom":
                    log("[*] Waiting for dom...")
                    if sub_gui_instance:
                        sub_gui_instance.root.after(0, lambda: sub_gui_instance.set_status(False))
                elif e == "request_avatar":
                    # Dom fragt nach aktuellem Avatar
                    avatar_id, params = get_current_avatar()
                    display_name = get_vrchat_display_name() or KEYS[0]
                    if avatar_id and osc_ws_ref:
                        if sub_gui_instance:
                            sub_gui_instance.root.after(0, lambda a=avatar_id: sub_gui_instance.set_avatar(a))
                            sub_gui_instance.root.after(0, lambda n=display_name: sub_gui_instance.set_name(n))
                        payload_out = json.dumps({
                            "event":        "avatar_change",
                            "avatar_id":    avatar_id,
                            "params":       params,
                            "display_name": display_name
                        })
                        await ws.send(payload_out)
                        log(f"[*] Avatar sent on request: {avatar_id}")
                continue
            cmd = data.get("cmd")
            val = data.get("value", "1")
            log(f"[<<] Befehl: cmd='{cmd}' value='{val}'")
            if cmd in COMMANDS:
                COMMANDS[cmd](val)
            else:
                log(f"[!] Unbekannter Befehl: '{cmd}'")
        except json.JSONDecodeError:
            log("[!] Ungültige Nachricht")

# ── Dom Loop (Terminal) ────────────────────────────────────────────────────
def print_help(keys):
    print()
    print("  Connected keys:")
    for i, k in enumerate(keys):
        print(f"    [{i}] {k}")
    print()
    print("  Commands:")
    print("  mute 1/0 | jump | move forward/back/left/right/stop")
    print("  spin <s> | run 1/0 | chatbox <text> | emote 1-8")
    print("  avatar_param Name:Value | avatar avtr_xxxx")
    print("  trigger <Param> | drop left/right/both")
    print("  all <cmd> <val> | target <nr> <cmd> <val>")
    print("  help | quit")
    print()

async def dom_loop(connections):
    global dom_ws_connections
    dom_ws_connections = connections
    keys = [k for k, _ in connections]
    log(f"[MASTER] Connected with {len(connections)} key(s)")
    print_help(keys)

    if gui_instance:
        if not gui_instance.connected_subs:
            gui_instance.set_server_connected(keys[0] if keys else "-")
        # Dropdown bleibt leer bis Subs verbinden

    loop = asyncio.get_event_loop()

    # Wenn GUI aktiv ist, kein Terminal-Input – einfach warten bis disconnected
    if gui_instance:
        await asyncio.Event().wait()  # Wartet ewig bis Task gecancelt wird
        return

    while True:
        try:
            raw = await loop.run_in_executor(None, lambda: input("Befehl> "))
        except (EOFError, KeyboardInterrupt):
            break

        raw = raw.strip()
        if not raw:        continue
        if raw == "quit":  break
        if raw == "help":  print_help(keys); continue

        parts = raw.split(maxsplit=1)
        cmd   = parts[0].lower()
        rest  = parts[1] if len(parts) > 1 else ""

        if cmd == "all" and rest:
            sub_parts = rest.split(maxsplit=1)
            sub_cmd   = sub_parts[0]
            value     = sub_parts[1] if len(sub_parts) > 1 else "1"
            for key, ws in connections:
                try:
                    await ws.send(json.dumps({"cmd": sub_cmd, "value": value}))
                    log(f"[>>] ALL | Key: {key} | cmd='{sub_cmd}'")
                except Exception as e:
                    log(f"[!] Error: {e}")

        elif cmd == "target" and rest:
            try:
                sub_parts = rest.split(maxsplit=2)
                idx       = int(sub_parts[0])
                sub_cmd   = sub_parts[1] if len(sub_parts) > 1 else ""
                value     = sub_parts[2] if len(sub_parts) > 2 else "1"
                key, ws   = connections[idx]
                await ws.send(json.dumps({"cmd": sub_cmd, "value": value}))
                log(f"[>>] TARGET [{idx}] | cmd='{sub_cmd}'")
            except (IndexError, ValueError) as e:
                log(f"[!] Error: {e}")

        else:
            value = rest if rest else "1"
            for key, ws in connections:
                try:
                    await ws.send(json.dumps({"cmd": cmd, "value": value}))
                    log(f"[>>] Key: {key} | cmd='{cmd}'")
                except Exception as e:
                    log(f"[!] Error: {e}")

# ── Keepalive ─────────────────────────────────────────────────────────────────
async def keepalive_monitor(ws, role, key, disconnected_event):
    try:
        while True:
            await asyncio.sleep(15)
            try:
                pong = await asyncio.wait_for(ws.ping(), timeout=5)
                await pong
            except asyncio.TimeoutError:
                log(f"[!] Keepalive Timeout")
                disconnected_event.set()
                return
            except Exception:
                disconnected_event.set()
                return
    except asyncio.CancelledError:
        pass

# ── Verbindungen ──────────────────────────────────────────────────────────────
async def connect_as_sub():
    global osc_ws_ref, osc_loop
    key    = KEYS[0]
    attempt = 0

    t = threading.Thread(target=start_osc_listener, daemon=True)
    t.start()
    osc_loop = asyncio.get_event_loop()

    while True:
        attempt += 1
        try:
            log(f"Connecting as SLAVE | Key: {key} | Attempt #{attempt}")
            async with websockets.connect(SERVER) as ws:
                osc_ws_ref = ws
                await ws.send(json.dumps({"key": key, "role": "sub"}))
                first = json.loads(await ws.recv())

                if "error" in first:
                    log(f"[!] Server: {first['error']}")
                    await asyncio.sleep(RECONNECT_DELAY)
                    continue

                if first.get("event") == "state":
                    dom_count = first.get("dom_count", 0)
                    log(f"[*] Connected – {dom_count} dom(s) online")
                    if sub_gui_instance:
                        sub_gui_instance.root.after(100, lambda c=dom_count: sub_gui_instance.set_status(c > 0, c))
                elif first.get("event") == "waiting_for_dom":
                    log("[*] Connected – waiting for dom...")
                    if sub_gui_instance:
                        sub_gui_instance.root.after(0, lambda: sub_gui_instance.set_status(False))
                elif first.get("event") == "dom_connected":
                    log(f"[*] Connected – dom active!")
                    count = first.get("count", 1)
                    if sub_gui_instance:
                        sub_gui_instance.root.after(0, lambda c=count: sub_gui_instance.set_status(True, c))

                attempt = 0

                # Display Name ermitteln
                display_name = get_vrchat_display_name() or KEYS[0]
                log(f"[*] Display name: {display_name}")
                if sub_gui_instance:
                    sub_gui_instance.root.after(0, lambda n=display_name: sub_gui_instance.set_name(n))

                # Aktuellen Avatar sofort senden
                avatar_id, params = get_current_avatar()
                if avatar_id:
                    if sub_gui_instance:
                        sub_gui_instance.root.after(0, lambda a=avatar_id: sub_gui_instance.set_avatar(a))
                    payload = json.dumps({
                        "event":        "avatar_change",
                        "avatar_id":    avatar_id,
                        "params":       params,
                        "display_name": display_name,
                    })
                    await ws.send(payload)
                    log(f"[*] Current avatar sent: {avatar_id}")
                else:
                    await ws.send(json.dumps({
                        "event":        "sub_info",
                        "display_name": display_name,
                    }))
                disconnected = asyncio.Event()
                ka_task    = asyncio.ensure_future(keepalive_monitor(ws, "sub", key, disconnected))
                sub_task = asyncio.ensure_future(sub_loop(ws))

                done, pending = await asyncio.wait(
                    [sub_task, asyncio.ensure_future(disconnected.wait())],
                    return_when=asyncio.FIRST_COMPLETED
                )
                for t in pending: t.cancel()
                ka_task.cancel()
                log(f"[!] Verbindung zum Server verloren")

        except (websockets.ConnectionClosed, ConnectionRefusedError, OSError) as e:
            log(f"[!] Verbindung fehlgeschlagen: {e}")
        except Exception as e:
            log(f"[!] Error: {e}")

        osc_ws_ref = None
        log(f"    Reconnect in {RECONNECT_DELAY}s...")
        await asyncio.sleep(RECONNECT_DELAY)

async def connect_as_dom():
    global gui_instance
    attempt = 0

    while True:
        attempt += 1
        try:
            connections  = []
            ka_tasks     = []
            disconnected = asyncio.Event()

            for key in KEYS:
                log(f"Connecting as MASTER | Key: {key} | Attempt #{attempt}")
                ws = await websockets.connect(SERVER)
                await ws.send(json.dumps({"key": key, "role": "dom"}))
                first = json.loads(await ws.recv())

                if "error" in first:
                    log(f"[!] Key '{key}' abgelehnt: {first['error']}")
                    await ws.close()
                    continue

                if first.get("event") == "state":
                    sub_online = first.get("sub_online", False)
                    dn           = first.get("display_name")
                    log(f"[*] State: sub_online={sub_online} | Key: {key}")
                    if gui_instance:
                        if sub_online:
                            gui_instance.set_status(True, key)
                            if dn and dn != key:
                                gui_instance.connected_subs.add(key)
                                gui_instance.sub_data.setdefault(key, {})["display_name"] = dn
                                gui_instance.root.after(100, lambda k=key, n=dn: gui_instance.update_sub_list(
                                    {mk: gui_instance.sub_data.get(mk, {}).get("display_name", mk)
                                     for mk in gui_instance.connected_subs}
                                ))
                        else:
                            if not gui_instance.connected_subs:
                                gui_instance.set_server_connected(key)
                elif first.get("event") == "sub_connected":
                    log(f"[*] Sub already connected | Key: {key}")
                    if gui_instance:
                        gui_instance.set_status(True, key)
                        dn = first.get("display_name")
                        if dn and dn != key:
                            gui_instance.connected_subs.add(key)
                            gui_instance.sub_data.setdefault(key, {})["display_name"] = dn
                            gui_instance.root.after(100, lambda k=key, n=dn: gui_instance.update_sub_list(
                                {mk: gui_instance.sub_data.get(mk, {}).get("display_name", mk)
                                 for mk in gui_instance.connected_subs}
                            ))
                else:
                    log(f"[*] Waiting for sub | Key: {key}")
                    if gui_instance and not gui_instance.connected_subs:
                        gui_instance.set_server_connected(key)

                connections.append((key, ws))
                ka_tasks.append(asyncio.ensure_future(
                    keepalive_monitor(ws, "dom", key, disconnected)
                ))

            if not connections:
                log(f"[!] No connections – retry in {RECONNECT_DELAY}s...")
                await asyncio.sleep(RECONNECT_DELAY)
                continue

            attempt = 0

            async def listen(key, ws):
                try:
                    async for msg in ws:
                        data = json.loads(msg)
                        if "event" not in data:
                            continue
                        e = data["event"]

                        if e == "state":
                            sub_online = data.get("sub_online", False)
                            dn           = data.get("display_name")
                            if gui_instance:
                                if sub_online:
                                    gui_instance.set_status(True, key)
                                    if dn and dn != key:
                                        gui_instance.connected_subs.add(key)
                                        gui_instance.sub_data.setdefault(key, {})["display_name"] = dn
                                        gui_instance.root.after(100, lambda k=key, n=dn: gui_instance.update_sub_list(
                                            {mk: gui_instance.sub_data.get(mk, {}).get("display_name", mk)
                                             for mk in gui_instance.connected_subs}
                                        ))
                                else:
                                    gui_instance.connected_subs.discard(key)
                                    if not gui_instance.connected_subs:
                                        gui_instance.set_server_connected(key)
                                    gui_instance.root.after(0, lambda k=key: gui_instance.update_sub_list(
                                        {mk: gui_instance.sub_data.get(mk, {}).get("display_name", mk)
                                         for mk in gui_instance.connected_subs}
                                    ))

                        elif e == "sub_connected":
                            log(f"[*] Sub connected | Key: {key}")
                            if gui_instance:
                                gui_instance.set_status(True, key)
                                dn = data.get("display_name")
                                if dn and dn != key:
                                    gui_instance.connected_subs.add(key)
                                    gui_instance.sub_data.setdefault(key, {})["display_name"] = dn
                                    gui_instance.root.after(100, lambda k=key, n=dn: gui_instance.update_sub_list(
                                        {mk: gui_instance.sub_data.get(mk, {}).get("display_name", mk)
                                         for mk in gui_instance.connected_subs}
                                    ))

                        elif e == "sub_disconnected":
                            log(f"[!] Sub disconnected | Key: {key}")
                            if gui_instance:
                                gui_instance.connected_subs.discard(key)
                                gui_instance.set_status(False)
                                gui_instance.root.after(0, lambda k=key: gui_instance.update_sub_list(
                                    {mk: gui_instance.sub_data.get(mk, {}).get("display_name", mk)
                                     for mk in gui_instance.connected_subs}
                                ))

                        elif e == "avatar_change":
                            avatar_id    = data.get("avatar_id")
                            params       = data.get("params", [])
                            display_name = data.get("display_name")
                            log(f"[*] Avatar changed: {avatar_id} | {len(params)} params | Name: {display_name}")
                            if gui_instance and display_name and display_name != key:
                                gui_instance.connected_subs.add(key)
                                def _update_list(k=key, n=display_name):
                                    gui_instance.sub_data.setdefault(k, {})["display_name"] = n
                                    gui_instance.update_sub_list(
                                        {mk: gui_instance.sub_data.get(mk, {}).get("display_name", mk)
                                         for mk in gui_instance.connected_subs}
                                    )
                                gui_instance.root.after(100, _update_list)
                            if gui_instance:
                                gui_instance.root.after(0, lambda a=avatar_id, p=params, k=key: gui_instance.load_avatar_params(a, p, key=k))

                        elif e == "sub_info" and gui_instance:
                            display_name = data.get("display_name")
                            if display_name and display_name != key:
                                gui_instance.connected_subs.add(key)
                                def _update_info(k=key, n=display_name):
                                    gui_instance.sub_data.setdefault(k, {})["display_name"] = n
                                    gui_instance.update_sub_list(
                                        {mk: gui_instance.sub_data.get(mk, {}).get("display_name", mk)
                                         for mk in gui_instance.connected_subs}
                                    )
                                gui_instance.root.after(0, _update_info)

                        elif e == "param_update" and gui_instance:
                            gui_instance.update_param(
                                data.get("name"),
                                data.get("value"),
                                data.get("type", "float")
                            )

                        elif e == "no_sub":
                            pass  # Kein Sub für diesen Key – still ignorieren

                except Exception:
                    disconnected.set()

            listeners   = [asyncio.ensure_future(listen(k, w)) for k, w in connections]
            dom_task = asyncio.ensure_future(dom_loop(connections))

            await asyncio.wait(
                [dom_task, asyncio.ensure_future(disconnected.wait())],
                return_when=asyncio.FIRST_COMPLETED
            )

            if disconnected.is_set():
                log("[!] Verbindung verloren – Reconnect...")
                if gui_instance:
                    gui_instance.set_status(False)

            dom_task.cancel()
            for t in listeners + ka_tasks: t.cancel()
            for _, ws in connections:
                try: await ws.close()
                except Exception: pass

        except (websockets.ConnectionClosed, ConnectionRefusedError, OSError) as e:
            log(f"[!] Verbindung fehlgeschlagen: {e}")
        except Exception as e:
            log(f"[!] Error: {e}")

        log(f"    Reconnect in {RECONNECT_DELAY}s...")
        await asyncio.sleep(RECONNECT_DELAY)

# ── Main ──────────────────────────────────────────────────────────────────────
async def async_main():
    if ROLE == "sub":
        await connect_as_sub()
    else:
        await connect_as_dom()

sub_gui_instance = None

class SubGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f"VRChat OSC Remote v{CURRENT_VERSION} - Sub")
        self.root.configure(bg="#1e1e2e")
        self.root.resizable(False, False)

        # Fensterposition laden
        self._win_cfg_path = os.path.join(_BASE_DIR, "window_sub.ini")
        try:
            if os.path.exists(self._win_cfg_path):
                with open(self._win_cfg_path, "r") as f:
                    geo = f.read().strip()
                self.root.geometry(geo)
            else:
                self.root.geometry("500x680")
        except Exception:
            self.root.geometry("500x680")

        self.root.protocol("WM_DELETE_WINDOW", self._on_close_sub)

        # Icon
        try:
            ico_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
            if not os.path.exists(ico_path):
                ico_path = os.path.join(os.path.dirname(sys.executable), "icon.ico")
            if os.path.exists(ico_path):
                self.root.iconbitmap(ico_path)
        except Exception:
            pass

        # Banner
        try:
            from PIL import Image, ImageTk
            banner_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "banner.png")
            if not os.path.exists(banner_path):
                banner_path = os.path.join(os.path.dirname(sys.executable), "banner.png")
            if os.path.exists(banner_path):
                src = Image.open(banner_path)
                w   = 500
                x   = (src.width - w) // 2
                cropped = src.crop((x, 0, x + w, src.height))
                self._banner_img = ImageTk.PhotoImage(cropped)
                tk.Label(self.root, image=self._banner_img, bg="#1e1e2e", borderwidth=0).pack(fill="x")
        except Exception:
            pass

        # Status
        header = tk.Frame(self.root, bg="#313244", pady=8)
        header.pack(fill="x")

        self.status_label = tk.Label(
            header, text="● Connecting...",
            fg="#f38ba8", bg="#313244",
            font=("Segoe UI", 10, "bold")
        )
        self.status_label.pack(side="left", padx=12)

        tk.Button(
            header, text="📋 Logs",
            command=self._open_log_window,
            bg="#45475a", fg="#cdd6f4",
            activebackground="#585b70",
            font=("Segoe UI", 9), relief="flat",
            padx=8, pady=2, cursor="hand2"
        ).pack(side="right", padx=8)

        tk.Button(
            header, text="⚙ Settings",
            command=self._open_settings,
            bg="#45475a", fg="#cdd6f4",
            activebackground="#585b70",
            font=("Segoe UI", 9), relief="flat",
            padx=8, pady=2, cursor="hand2"
        ).pack(side="right", padx=2)

        # Info Frame
        info = tk.Frame(self.root, bg="#1e1e2e")
        info.pack(fill="x", padx=12, pady=10)

        def info_row(label, value_var):
            row = tk.Frame(info, bg="#1e1e2e")
            row.pack(fill="x", pady=3)
            tk.Label(row, text=label, fg="#cba6f7", bg="#1e1e2e",
                     font=("Segoe UI", 9, "bold"), width=12, anchor="w").pack(side="left")
            tk.Label(row, textvariable=value_var, fg="#cdd6f4", bg="#1e1e2e",
                     font=("Segoe UI", 9), anchor="w").pack(side="left")

        self.var_key     = tk.StringVar(value=KEYS[0])
        self.var_name    = tk.StringVar(value="-")
        self.var_avatar  = tk.StringVar(value="-")
        self.var_dom  = tk.StringVar(value="Waiting...")
        self.var_port    = tk.StringVar(value=str(OSC_RECV))

        info_row("Key:",        self.var_key)
        info_row("Name:",       self.var_name)
        info_row("Avatar:",     self.var_avatar)
        info_row("Dom:",     self.var_dom)
        info_row("OSC Port:",   self.var_port)

        # Log preview (letzte 8 Zeilen)
        log_frame = tk.LabelFrame(
            self.root, text=" Recent Logs ",
            fg="#cba6f7", bg="#1e1e2e",
            font=("Segoe UI", 9, "bold")
        )
        log_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self._log_text = tk.Text(
            log_frame, bg="#181825", fg="#cdd6f4",
            font=("Consolas", 8), relief="flat",
            state="disabled", height=18, wrap="word"
        )
        self._log_text.pack(fill="both", expand=True, padx=4, pady=4)
        self._log_text.tag_config("error",   foreground="#f38ba8")
        self._log_text.tag_config("success", foreground="#a6e3a1")
        self._log_text.tag_config("info",    foreground="#89b4fa")

        # Live Log Updates
        def on_log(line):
            self.root.after(0, lambda l=line: self._append_log(l))
        _log_callbacks.append(on_log)

        # Bestehende Logs laden
        for line in _log_buffer[-18:]:
            self._append_log(line)

        self.root.protocol("WM_DELETE_WINDOW", self._on_close_sub)

    def _append_log(self, line):
        self._log_text.config(state="normal")
        if "[!]" in line:   tag = "error"
        elif "[*]" in line: tag = "info"
        elif "[+]" in line: tag = "success"
        else:               tag = "normal"
        self._log_text.insert("end", line + "\n", tag)
        # Nur letzte 12 Zeilen behalten
        lines = int(self._log_text.index("end-1c").split(".")[0])
        if lines > 18:
            self._log_text.delete("1.0", f"{lines-18}.0")
        self._log_text.see("end")
        self._log_text.config(state="disabled")

    def set_status(self, connected, dom_count=0):
        if connected:
            self.status_label.config(text=f"● Connected | {dom_count} dom(s)", fg="#a6e3a1")
            self.var_dom.set(f"{dom_count} connected")
        else:
            self.status_label.config(text="● Connected | Waiting for dom...", fg="#fab387")
            self.var_dom.set("Waiting...")

    def set_server_status(self, connected):
        if not connected:
            self.status_label.config(text="● Connecting...", fg="#f38ba8")
            self.var_dom.set("Waiting...")

    def set_avatar(self, avatar_id):
        self.var_avatar.set(avatar_id if avatar_id else "-")

    def set_name(self, name):
        self.var_name.set(name or "-")

    def _open_settings(self):
        open_settings_window(self.root)

    def _on_close_sub(self):
        try:
            with open(self._win_cfg_path, "w") as f:
                f.write(self.root.geometry())
        except Exception:
            pass
        import os as _os
        _os._exit(0)

    def _open_log_window(self):
        win = tk.Toplevel(self.root)
        win.title("Logs")
        win.geometry("800x500")
        win.configure(bg="#1e1e2e")
        toolbar = tk.Frame(win, bg="#313244", pady=4)
        toolbar.pack(fill="x")
        frame = tk.Frame(win, bg="#1e1e2e")
        frame.pack(fill="both", expand=True, padx=6, pady=6)
        scrollbar = ttk.Scrollbar(frame)
        scrollbar.pack(side="right", fill="y")
        text = tk.Text(frame, bg="#181825", fg="#cdd6f4",
                       font=("Consolas", 9), relief="flat",
                       yscrollcommand=scrollbar.set, state="disabled", wrap="none")
        text.pack(fill="both", expand=True)
        scrollbar.config(command=text.yview)
        text.tag_config("error",   foreground="#f38ba8")
        text.tag_config("success", foreground="#a6e3a1")
        text.tag_config("info",    foreground="#89b4fa")
        auto_scroll = tk.BooleanVar(value=True)
        tk.Checkbutton(toolbar, text="Auto-scroll", variable=auto_scroll,
                       bg="#313244", fg="#cdd6f4", selectcolor="#45475a",
                       activebackground="#313244", font=("Segoe UI", 9)).pack(side="left", padx=8)

        def append_line(line):
            text.config(state="normal")
            tag = "error" if "[!]" in line else "success" if "[+]" in line else "info" if "[*]" in line else "normal"
            text.insert("end", line + "\n", tag)
            if auto_scroll.get(): text.see("end")
            text.config(state="disabled")

        text.config(state="normal")
        for line in _log_buffer:
            tag = "error" if "[!]" in line else "success" if "[+]" in line else "info" if "[*]" in line else "normal"
            text.insert("end", line + "\n", tag)
        text.see("end")
        text.config(state="disabled")
        _log_callbacks.append(append_line)
        win.protocol("WM_DELETE_WINDOW", lambda: (_log_callbacks.remove(append_line), win.destroy()))

    def run(self):
        self.root.mainloop()


def main():
    global gui_instance, _dom_loop, sub_gui_instance
    _init_log_file()
    check_for_updates()

    print("=" * 50)
    print("  VRChat OSC Relay Client")
    print("=" * 50)
    log(f"Role:   {ROLE.upper()}")
    log(f"Server: {SERVER}")
    log(f"Keys:   {', '.join(KEYS)}")
    log(f"OSC ->  127.0.0.1:{OSC_PORT}")
    if ROLE == "sub":
        osc_path = find_vrchat_osc_path()
        log(f"VRChat OSC path: {osc_path or 'not found'}")
    print()

    if ROLE == "dom":
        loop = asyncio.new_event_loop()
        _dom_loop = loop

        def run_loop():
            asyncio.set_event_loop(loop)
            loop.run_until_complete(async_main())

        net_thread = threading.Thread(target=run_loop, daemon=True)
        net_thread.start()

        gui_instance = DomGUI(gui_send_callback)
        gui_instance.run()
    else:
        loop = asyncio.new_event_loop()

        def run_sub_loop():
            asyncio.set_event_loop(loop)
            loop.run_until_complete(async_main())

        net_thread = threading.Thread(target=run_sub_loop, daemon=True)
        net_thread.start()

        sub_gui_instance = SubGUI()
        sub_gui_instance.run()

try:
    main()
except KeyboardInterrupt:
    log("Stopped.")
except Exception as e:
    log(f"[!] Fatal error: {e}")
