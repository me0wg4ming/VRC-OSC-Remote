# Build Instructions

## Requirements

- Windows 10/11
- Python 3.11 (via `py install 3.11`)
- Inno Setup 6 ([download](https://jrsoftware.org/isinfo.php))

## Step 1 – Install Python dependencies

```cmd
py -m pip install python-osc websockets Pillow pyinstaller
```

## Step 2 – Prepare Python Embeddable

1. Download [Python 3.11 Embeddable](https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip)
2. Extract to `python_embed\`
3. Install dependencies into embed:
```cmd
py -3.11 -m pip install python-osc websockets Pillow --target python_embed\Lib\site-packages
```
4. Copy tkinter files from your Python 3.11 installation:
```powershell
$src = "C:\Users\<you>\AppData\Local\Python\pythoncore-3.11-64"
$dst = "python_embed"
Copy-Item "$src\Lib\tkinter" "$dst\Lib\tkinter" -Recurse
Copy-Item "$src\DLLs\_tkinter.pyd" "$dst"
Copy-Item "$src\DLLs\tcl86t.dll" "$dst"
Copy-Item "$src\DLLs\tk86t.dll" "$dst"
Copy-Item "$src\tcl" "$dst\tcl" -Recurse
```

## Step 3 – Build installer

1. Open `setup.iss` in Inno Setup
2. Press F9
3. Find the installer in `installer\VRChatOSCRemote-Setup.exe`

## File structure

```
VRChatOSCRemote/
├── client.py           ← Main client
├── config.ini          ← User config (auto-created on first run)
├── banner.png          ← GUI banner
├── icon.ico            ← App icon
├── setup.iss           ← Inno Setup script
├── start.bat           ← Manual start fallback
├── python_embed/       ← Bundled Python runtime
└── installer/          ← Output directory
    └── VRChatOSCRemote-Setup.exe
```
