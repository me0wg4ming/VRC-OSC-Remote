# VRChat OSC Remote

A remote control tool for VRChat avatars using OSC protocol. Allows a **Dom** to control a **Sub**'s avatar parameters, movement, and more in real-time over a secure WebSocket connection.

---

## Features

- 🎮 **Real-time avatar parameter control** – Toggle Bool/Int parameters remotely
- 🕹️ **Movement control** – Forward, back, left, right, rotate, jump, spin, run
- 💬 **Chatbox control** – Send messages to the sub's chatbox
- 🔄 **Auto-update** – Client updates itself automatically on startup
- 🔒 **Secure** – Key-based authentication, routed through Cloudflare Tunnel
- 📋 **Live logs** – Both Dom and Sub have a built-in log viewer
- ⚙️ **Settings** – Change role and key without reinstalling

---

## Download

Head to the [Releases](../../releases) page and download the latest `VRChatOSCRemote-Setup.exe`.

> ✅ **1/72 on VirusTotal** – The installer is flagged by only 1 antivirus (Trapmine, low confidence false positive). This is a known issue with Python-based installers.

---

## Installation

1. Download `VRChatOSCRemote-Setup.exe` from [Releases](../../releases)
2. Run the installer
3. On first launch, a setup dialog will appear asking for:
   - **Role**: `sub` or `dom`
   - **Key**: Your personal access key (obtained via Discord)
4. Done!

---

## Getting a Key

Keys are distributed via our Discord server through a bot:

1. Join the Discord server: **https://discord.gg/tRmTDESbck**
2. Go to the `#key-request` channel
3. Type `/request`
4. A private ticket channel will be created with your key
5. Type `/redeem <your-key>` in the ticket channel to activate it
6. Add the key to your client via **⚙ Settings**

---

## How it works

```
Dom PC ──► wss://osc.me0wg4ming.de ◄── Sub PC
                (Cloudflare Tunnel)
                      │
                Sub PC ◄──► VRChat
                    (OSC port 9000/9001)
```

- The **Sub** runs VRChat and the OSC Remote client in sub mode
- The **Dom** connects using the sub's key to control their avatar
- All traffic is routed through Cloudflare – the server IP is never exposed
- Communication is encrypted via WSS (TLS)

---

## Configuration

The `config.ini` file is created automatically on first launch. You can also edit it manually:

```ini
[general]
role = sub            ; sub or dom
key = YOUR_KEY_HERE   ; your personal key (sub: one key, dom: comma-separated)

[osc]
send_port = 9000      ; VRChat OSC receive port
recv_port = 9001      ; VRChat OSC send port

[filter]
; Parameters starting with these prefixes will NOT be sent to dom
blacklist_prefix = VF74_, VF73_, ...
float_throttle_ms = 150

[paths]
; Leave empty for auto-detection
vrchat_osc_path =
```

---

## Building from source

### Requirements
- Python 3.11
- `pip install python-osc websockets Pillow`

### Run directly
```bash
python client.py
```

### Build installer (Windows)
See `build_instructions.md` for full steps.

---

## VRChat Setup

Make sure OSC is enabled in VRChat:
1. Open VRChat
2. Action Menu → OSC → Enable OSC
3. The client will auto-detect your OSC configuration

---

## Privacy & Security

- 🔒 Your server IP is never exposed (Cloudflare Tunnel)
- 🔑 Only users with valid keys can connect
- 🚫 Keys can be revoked at any time by the server admin
- 📡 All traffic is TLS encrypted

---

## License

© 2026 me0wg4ming. All rights reserved.

This project is **source-available** – you may view and study the code, but you may **not**:
- Copy, redistribute, or republish this software or any part of it
- Use this code or any derivative in your own projects without explicit written permission
- Sell or commercially exploit this software

The source code is provided for transparency and community trust only.

---

## Disclaimer

This tool is intended for consensual use between trusted parties. Always ensure the person running the sub client has given explicit consent. The developers are not responsible for misuse.
