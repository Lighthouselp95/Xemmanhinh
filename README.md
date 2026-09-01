# Xemmanhinh - H264 WebRTC Screen Viewer

Remote desktop viewer using H264 encoding + WebSocket transport, viewable directly in browser.

## Features

- H264 hardware encoding (NVENC/CUDA/AMF)
- WebSocket real-time streaming
- Browser-side Broadway.js decoding
- Virtual display driver support

## Installation

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

## Usage

### Start Server

```bash
cd server
python server_manager.py
```

### Open Browser

Open `web/viewer_H264wss_P_new.html` in browser (the P_new viewer).

```
https://localhost:8765
```

## Build EXE

### PyInstaller Packaging (P_new)

```bash
cd release/server
pyinstaller --onefile server_H264wss_testP_new.py
pyinstaller --onefile ../server/server_manager.py
```

Output: `release/server/dist/`

### Source Files for Building

- `server/server_H264wss.py` - Base server source (71KB)
- `server/server_manager.py` - Process manager source (14KB)
- `release/server/server_H264wss_testP_new.py` - P_new source (108KB, used for exe build)
- `web/viewer_H264wss_P_new.html` - P_new viewer (94KB)

## Pre-built Releases

The GitHub Release includes pre-built EXEs compiled from **P_new** source:

- `server_H264wss_testP_new.exe` - Main server (dxcam stability, dithering, QP tuning)
- `server_manager_P_new.exe` - Process manager

## Project Structure

```
Xemmanhinh/
  server/
    server_H264wss.py              Base server source
    server_manager.py              Process manager source
  web/
    viewer_H264wss_P_new.html     P_new viewer (main)
    viewer_H264wss_P_wgl.html     P_new viewer (WebGL)
    viewer_H264wss_O_new.html     O_new viewer
    viewer_H264wss_O_wgl.html     O_new viewer (WebGL)
    viewer_H264wss.html           Base viewer
    broadway-*.js                 H264 decoder
  tools/
    virtual_display_driver/       Virtual display driver
  release/
    server/
      server_H264wss_testP_new.py   P_new server source
      server_H264wss_testP_new.exe  Pre-built P_new server
      server_manager_P_new.exe      Pre-built P_new manager
```
