import os
import sys
import shutil
import subprocess

_BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
_APP_NAME    = "VRChatOSCRemote"

if os.name == "nt":
    _APPDATA_DIR = os.path.join(os.environ.get("APPDATA", ""), _APP_NAME)
else:
    _APPDATA_DIR = os.path.join(os.path.expanduser("~"), f".{_APP_NAME}")
_APPDATA_CLIENT = os.path.join(_APPDATA_DIR, "client.py")
_INSTALL_CLIENT = os.path.join(_BASE_DIR, "client.py")

# Migrate client.py from install dir to AppData if not already there
if not os.path.exists(_APPDATA_CLIENT) and os.path.exists(_INSTALL_CLIENT):
    os.makedirs(_APPDATA_DIR, exist_ok=True)
    shutil.copy2(_INSTALL_CLIENT, _APPDATA_CLIENT)

# If client.py now exists in AppData, delete it from install dir
if os.path.exists(_APPDATA_CLIENT) and os.path.exists(_INSTALL_CLIENT):
    try:
        os.remove(_INSTALL_CLIENT)
    except Exception:
        pass

script = _APPDATA_CLIENT if os.path.exists(_APPDATA_CLIENT) else _INSTALL_CLIENT

python = os.path.join(_BASE_DIR, "python", "pythonw.exe")
if not os.path.exists(python):
    python = sys.executable

subprocess.Popen([python, script])
