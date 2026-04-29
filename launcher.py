import os
import sys
import subprocess

_BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
_APP_NAME       = "VRChatOSCRemote"
_APPDATA_CLIENT = os.path.join(os.environ.get("APPDATA", ""), _APP_NAME, "client.py")
_INSTALL_CLIENT = os.path.join(_BASE_DIR, "client.py")

script = _APPDATA_CLIENT if os.path.exists(_APPDATA_CLIENT) else _INSTALL_CLIENT

python = os.path.join(_BASE_DIR, "python", "pythonw.exe")
if not os.path.exists(python):
    python = sys.executable

subprocess.Popen([python, script])
