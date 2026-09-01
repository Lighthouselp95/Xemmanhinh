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

```
https://localhost:8765
```

## Build EXE

### PyInstaller Packaging

```bash
cd server
pyinstaller --onefile server_H264wss.py
pyinstaller --onefile server_manager.py
```

Output: release/server/dist/

## Project Structure

```
Xemmanhinh/
  server/
    server_H264wss.py       Main server (H264 + WebSocket)
    server_manager.py       Process manager
  web/
    viewer_H264wss.html     Main viewer
    broadway-*.js           H264 decoder
  tools/
    virtual_display_driver/ Virtual display driver
  release/
    BUILD.md                Build documentation
    CHANGELOG.md            Changelog
```
