# Xemmanhinh - H264 WebRTC Screen Viewer

Remote desktop viewer using H264 encoding + WebSocket transport, viewable directly in browser.

## Features

- H264 hardware encoding (NVENC/CUDA/AMF)
- WebSocket real-time streaming
- Browser-side Broadway.js decoding
- Virtual display driver support

## Quick Start

1. Run `server_manager_P_new.exe`
2. Open browser: `http://localhost:8765`

## Run from Source

### Install Dependencies

```bash
pip install websockets aiortc av numpy pillow
```

### Generate SSL Certificate

```bash
cd server
openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 365 -nodes
```

### Start Server

```bash
python server/server_manager.py
```

Open `http://localhost:8765` in browser.

### Virtual Display (Optional)

If no physical display available, install virtual display driver:

```bash
cd tools/virtual_display_driver
# Run as Administrator
Cai_Dat_Man_Hinh_Ao.bat
```

## Build EXE

### Prerequisites

```bash
pip install pyinstaller websockets aiortc av numpy pillow
```

### Build All

```bash
# Build P_new server
cd release/server
pyinstaller --onefile server_H264wss_testP_new.py

# Build P_new manager
cd ../../server
pyinstaller --onefile --name server_manager_P_new server_manager.py
```

### Output

- `release/server/dist/server_H264wss_testP_new.exe` - Main server
- `server/dist/server_manager_P_new.exe` - Process manager

Copy both exe to same folder, run `server_manager_P_new.exe` to start.

## Project Structure

```
Xemmanhinh/
  server/
    server_manager.py              Manager source
  web/
    viewer_H264wss_P_new.html     P_new viewer
    broadway-*.js                  H264 decoder
  tools/
    virtual_display_driver/        Virtual display driver
  release/
    server/
      server_H264wss_testP_new.py    P_new server source
```
