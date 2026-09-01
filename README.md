# Xemmanhinh - H264 WebRTC Screen Viewer

Remote desktop viewer using H264 encoding + WebSocket transport, viewable directly in browser.

## Features

- H264 hardware encoding (NVENC/CUDA/AMF)
- WebSocket real-time streaming
- Browser-side Broadway.js decoding
- Virtual display driver support

## Quick Start (Pre-built)

1. Run `server_manager_P_new.exe` (auto-detects and spawns server)
2. Open browser: `http://localhost:8765`

## Installation (From Source)

### 1. Python Dependencies

```bash
pip install websockets aiortc av numpy pillow
```

### 2. Virtual Display (Optional)

```bash
cd tools/virtual_display_driver
Cai_Dat_Man_Hinh_Ao.bat
```

### 3. Generate SSL Certificate

```bash
cd server
openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 365 -nodes
```

### 4. Run from Source

```bash
python server/server_manager.py
```

Open `http://localhost:8765` in browser.

## Build EXE

### Build P_new Server

```bash
cd release/server
pyinstaller --onefile --name server_H264wss_testP_new server_H264wss_testP_new.py
```

### Build Manager

```bash
cd server
pyinstaller --onefile --name server_manager_P_new server_manager.py
```

Output: `dist/` folder in each directory.

## Source Files

| File | Size | Description |
|------|------|-------------|
| `server/server_manager.py` | 14KB | Process manager (detects version, spawns server) |
| `release/server/server_H264wss_testP_new.py` | 108KB | P_new server source (used for exe build) |

## Pre-built Releases

GitHub Release includes:
- `server_manager_P_new.exe` - Process manager
- `server_H264wss_testP_new.exe` - P_new server

## Project Structure

```
Xemmanhinh/
  server/
    server_manager.py              Process manager
  web/
    viewer_H264wss_P_new.html     P_new viewer
    broadway-*.js                  H264 decoder
  tools/
    virtual_display_driver/        Virtual display driver
  release/
    server/
      server_H264wss_testP_new.py    P_new server source
      server_H264wss_testP_new.exe   Pre-built P_new server
      server_manager_P_new.exe       Pre-built P_new manager
```
