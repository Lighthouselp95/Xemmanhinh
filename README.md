# Xemmanhinh - H264 WebRTC Screen Viewer

Remote desktop viewer using H264 encoding + WebSocket transport, viewable directly in browser.

## Features

- H264 hardware encoding (NVENC/CUDA/AMF)
- WebSocket real-time streaming
- Browser-side Broadway.js decoding
- Virtual display driver support

## Quick Start (Pre-built)

1. Run `server_manager_P_new.exe` (auto-detects and spawns server)
2. Open browser: `https://localhost:8765`
3. Open `web/viewer_H264wss_P_new.html` as viewer

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

Then open `web/viewer_H264wss_P_new.html` in browser.

## Build EXE

### Build P_new Server

```bash
cd release/server
pyinstaller --onefile server_H264wss_testP_new.py
```

### Build Manager

```bash
cd server
pyinstaller --onefile server_manager.py
```

Output: `dist/` folder in each directory.

**Note:** The manager auto-detects which server to spawn based on its exe name:
- `server_manager_P_new.exe` spawns `server_H264wss_testP_new.exe`
- `server_manager.exe` spawns `server_H264wss.exe` (base)

## Source Files

| File | Size | Description |
|------|------|-------------|
| `server/server_manager.py` | 14KB | Process manager (detects version, spawns server) |
| `server/server_H264wss.py` | 71KB | Base server source |
| `release/server/server_H264wss_testP_new.py` | 108KB | P_new server source (used for exe build) |
| `web/viewer_H264wss_P_new.html` | 94KB | P_new viewer |

## Pre-built Releases

GitHub Release includes:
- `server_manager_P_new.exe` - Process manager
- `server_H264wss_testP_new.exe` - P_new server

## Project Structure

```
Xemmanhinh/
  server/
    server_manager.py              Process manager
    server_H264wss.py              Base server source
  web/
    viewer_H264wss_P_new.html     P_new viewer (main)
    viewer_H264wss_P_wgl.html     P_new viewer (WebGL)
    viewer_H264wss_O_new.html     O_new viewer
    broadway-*.js                  H264 decoder
  tools/
    virtual_display_driver/        Virtual display driver
  release/
    server/
      server_H264wss_testP_new.py    P_new server source
      server_H264wss_testP_new.exe   Pre-built P_new server
      server_manager_P_new.exe       Pre-built P_new manager
```
