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

## Build EXE

### Prerequisites

```bash
pip install pyinstaller websockets aiortc av numpy pillow
```

### Build All

```bash
# Build P_new server
cd release/server
pyinstaller --onefile --name server_H264wss_testP_new server_H264wss_testP_new.py

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
