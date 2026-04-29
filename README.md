# VRChat OSC Remote

A remote control tool for VRChat avatars using OSC protocol. Allows a **Dom** to control a **Sub**'s avatar parameters, movement, and more in real-time over a secure WebSocket connection.

---

## Features

- 🎮 **Real-time avatar parameter control** – Toggle Bool/Int parameters remotely
- 🔍 **Parameter search/filter** – Quickly find parameters by name
- 💾 **Preset system** – Save and load parameter combinations per avatar
- 🕹️ **Movement control** – Forward, back, left, right, rotate, jump, spin, run
- 💬 **Chatbox control** – Send messages to the sub's chatbox
- 🔄 **Auto-update** – Client updates itself automatically on startup
- 🔒 **Secure** – Key-based authentication, routed through Cloudflare Tunnel
- 📋 **Live logs** – Both Dom and Sub have a built-in log viewer
- ⚙️ **Settings** – Change role and key without reinstalling
- 💾 **Window position** – Remembers window size and position between sessions
- 🤝 **Permission system** – Doms request access via Discord; Sub approves or denies
- ☁️ **Server-side lists** – Whitelist and Sub lists are stored server-side, never locally

---

## Download

Head to the [Releases](../../releases) page and download the latest `VRChatOSCRemote-Setup.exe`.

> ✅ **0/72 on VirusTotal** – The installer is signed and clean.

https://www.virustotal.com/gui/file/d93439c36d55aaf55b8429ddff1b040b34983a236a8716bdf93f7537cb8f1fe9

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
3. Click **🔑 Request Key** button
4. A private ticket channel will be created with your key
5. Type `/redeem <key>` in the ticket channel to activate it
6. Add the key to your client via **⚙ Settings**

---

## Connecting Dom to Sub

Once both have keys, the Dom needs permission to connect:

1. Dom uses `/control @Sub` in Discord
2. A private channel is created where Sub sees an **Accept** or **Deny** button
3. If Sub accepts, both keys are added to the server-side lists automatically
4. Dom opens the client – the Sub will appear in their list automatically
5. Sub opens the client – the Dom will appear in their whitelist automatically

No manual key entry needed after the initial setup key.

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
- The **Dom** connects to the server and is routed to their approved Subs
- All traffic is routed through Cloudflare – the server IP is never exposed
- Communication is encrypted via WSS (TLS)
- Whitelist and Sub lists are stored **server-side only** – the client never saves them locally

---

## Configuration

The `config.ini` file is created automatically on first launch. It only stores the minimum required settings:

```ini
[general]
role = sub            ; sub or dom
key = YOUR_KEY_HERE   ; your personal key

[osc]
send_port = 9000      ; VRChat OSC receive port
recv_port = 9001      ; VRChat OSC send port

[filter]
float_throttle_ms = 150
category_filter = System, FaceTrack, GoGo, OGB, Leash, Other

[paths]
; Leave empty for auto-detection
vrchat_osc_path =
```

> Whitelist and Sub Keys are no longer stored in `config.ini` – they are managed server-side.

---

## Discord Commands

| Command | Who | Description |
|---|---|---|
| `/control @user` | Dom | Request to control a Sub's avatar |
| `/allow @user` | Sub | Manually allow a Dom to connect |
| `/remove @user` | Sub | Remove a Dom from your whitelist |
| `/whitelist` | Sub | Show your current whitelist |
| `/mykey` | Anyone | Show your current key |
| `/redeem <key>` | Anyone | Activate your key in the ticket channel |
| `/help` | Anyone | Show all commands |

---

## Preset System

The Dom can save parameter combinations as presets per avatar:

1. Connect to a Sub with an avatar loaded
2. Set the desired parameters
3. Click **💾 Save** and give the preset a name
4. Later, select the preset from the dropdown and click **▶ Load**

Presets are stored locally in `presets.json` and are tied to the avatar ID.

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
- 🤝 Doms must be explicitly approved by the Sub before connecting
- 🚫 Keys can be revoked at any time by the server admin
- 📡 All traffic is TLS encrypted
- 🔐 Server address is obfuscated in the client binary
- ☁️ Whitelist and Sub lists are stored server-side only – not on your PC

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
