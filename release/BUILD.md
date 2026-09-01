# Hướng dẫn Build Binary (EXE) cho Screen Share Server

## 1. Mục đích

Đóng gói app thành file `.exe` để chạy mà **không cần cài Python** trên máy đích. Binary dùng PyInstaller (onefile) — tất cả thư viện, DLL, chứng chỉ SSL, file web được nhúng chung vào exe.

## 2. Cấu trúc 2 folder (debug / release)

| Folder | Vai trò | Nội dung |
|---|---|---|
| `Xemmanhinh/server` | **Debug** — code đang chạy, giữ nguyên, không sửa trực tiếp | source + cert + key |
| `Xemmanhinh/release` | **Release** — code bản exe, được copy từ debug, sửa cho frozen-aware | server/ (source + cert + exe) + web/ + BUILD.md |

Nguyên tắc: **không sửa trực tiếp trên code debug**. Muốn thay đổi cho bản exe → copy sang `release` và sửa ở đó; khi ổn định mới gộp ngược về debug.

## 3. Điều kiện cần

### 3.1. Máy build
- Windows (64-bit).
- Python 3.x đã cài (build dùng `C:\Python314\python.exe`).
- Cài PyInstaller: `python -m pip install pyinstaller`
- Đủ các thư viện runtime: `av` (PyAV), `dxcam`, `websockets`, `numpy`.

### 3.2. Máy chạy exe
- Windows 64-bit.
- GPU encoder (để nét + nhẹ): **bất kỳ** card nào sau đây — tự động phát hiện:
  - NVIDIA → `h264_nvenc`
  - Intel (iGPU) → `h264_qsv`
  - AMD → `h264_amf`
  - Không có GPU → fallback `libx264` (chạy được nhưng nặng CPU, tụt FPS ở 1080p60).
- GPU cần driver mới (đủ encode H264).

## 4. Quá trình tạo binary

### 4.1. Chuẩn bị folder release
```
cd Xemmanhinh
mkdir -p release/server release/web
cp server/server_H264wss.py server/server_manager.py server/cert.pem server/key.pem release/server/
cp web/*.js web/*.wasm web/*.html release/web/
```

### 4.2. Sửa code cho frozen-aware
Trong `release/server/`:

**`server_H264wss.py`** — đường dẫn tài nguyên khi chạy exe:
```python
if getattr(sys, 'frozen', False):
    _BASE_DIR = sys._MEIPASS          # temp giải nén của PyInstaller
else:
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_CERT_DIR = _BASE_DIR
SSL_CERT = os.path.join(_CERT_DIR, "cert.pem")
SSL_KEY = os.path.join(_CERT_DIR, "key.pem")
WEB_DIR = os.path.join(_BASE_DIR, "web")
```

**`server_manager.py`** — folder thật của exe (khác `__file__` khi frozen):
```python
FROZEN = getattr(sys, 'frozen', False)
if FROZEN:
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
```
- Spawn server con: khi frozen → chạy `SERVER_EXE` (server_H264wss.exe cùng folder), ngược lại chạy `python -u -X utf8 server_H264wss.py`.
- Relaunch admin: khi frozen → `ShellExecuteW(runas, sys.executable, None, ...)`.

> Lưu ý quan trọng: trong onefile, `__file__` trỏ vào temp giải nén, **không phải** folder chứa exe. `server_manager.py` bắt buộc dùng `dirname(sys.executable)` để tìm `server_H264wss.exe` và ghi `server_manager.pid` cạnh exe.

### 4.3. Build server chính (chứa PyAV/dxcam/websockets + cert + web)
```
cd release/server
python -m PyInstaller --noconfirm --clean --onefile --console --name server_H264wss ^
  --collect-all av --collect-all dxcam --collect-all websockets ^
  --add-data "cert.pem;." --add-data "key.pem;." ^
  --add-data "../web/audio-processor.js;web" ^
  --add-data "../web/broadway-avc.wasm;web" ^
  --add-data "../web/broadway-decoder.js;web" ^
  --add-data "../web/broadway-player.js;web" ^
  --add-data "../web/broadway-yuv.js;web" ^
  --add-data "../web/viewer.html;web" ^
  --add-data "../web/viewer_H264wss.html;web" ^
  server_H264wss.py
```

### 4.4. Build wrapper manager (nhẹ, không cần collect)
```
cd release/server
python -m PyInstaller --noconfirm --clean --onefile --console --name server_manager server_manager.py
```

Kết quả nằm trong `release/server/dist/`: `server_manager.exe` (~9MB) + `server_H264wss.exe` (~92MB). **Cả 2 exe phải ở cùng folder.**

### 4.5. Build manager cho các bản test (K/L/O/P)
`server_manager.py` tự nhận diện tên exe của chính nó để chọn server cần wrap:

| Manager exe | Server được wrap |
|---|---|
| `server_manager.exe` | `server_H264wss.exe` (production) |
| `server_manager_K.exe` | `server_H264wss_testK.exe` |
| `server_manager_L.exe` | `server_H264wss_testL.exe` |
| `server_manager_O.exe` | `server_H264wss_testO.exe` |
| `server_manager_P.exe` | `server_H264wss_testP.exe` |

Build từng bản bằng spec file tương ứng:
```
cd release/server
python -m PyInstaller --noconfirm --clean server_manager_K.spec
python -m PyInstaller --noconfirm --clean server_manager_L.spec
python -m PyInstaller --noconfirm --clean server_manager_O.spec
python -m PyInstaller --noconfirm --clean server_manager_P.spec
```

> Lưu ý: PID lock riêng theo từng wrapper (`server_manager_K.pid`, ...) — 2 wrapper khác nhau có thể chạy song song mỗi cái wrap 1 server khác nhau. Nhưng các server vẫn dùng chung 3 port (8765/8766/8767) → **chỉ nên chạy 1 wrapper/server tại 1 thời điểm**. Muốn test bản khác, tắt wrapper đang chạy trước.

## 5. Cách dùng

- Chạy `server_manager.exe` (double-click). Nó sẽ:
  1. Tự nâng quyền admin (UAC) nếu cần.
  2. Giữ 3 ports (8765/8766/8767), đợi client.
  3. Khi phone kết nối → spawn `server_H264wss.exe` tự động.
  4. Hết client 60s → server con tự thoát, wrapper vẫn sống.
- Phone mở: `https://<IP_máy>:8765/viewer_H264wss.html`
- Xem 3 file log: `server_log.txt`, `server_out.txt`, `server_out_new.txt` cạnh exe.

## 6. Lưu ý quan trọng

1. **`--collect-all av` bắt buộc** với PyAV — nếu thiếu sẽ lỗi thiếu `libavcodec.dll` lúc chạy.
2. **Đường dẫn `--add-data` tính theo cwd** (thư mục build). Web nằm ngoài server → dùng `../web/...`.
3. **Chỉ đóng gói file cần thiết**, không gói `*.bak*` (tránh exe phình to / lỗi).
4. **Cả 2 exe cùng folder** — `server_manager.exe` spawn `server_H264wss.exe` theo đường dẫn tương đối.
5. **Exe chạy chậm hơn** script ~5-10s lần đầu (onefile giải nén ra temp). Khởi động lần sau nhanh hơn.
6. **Exe release và code debug có thể chạy song song trên 2 port khác nhau?** Không — cả 2 dùng chung 3 port 8765/8766/8767. Muốn test exe, tắt bản debug (kill wrapper đang giữ port) trước.
7. **Bitrate/encoder**: cấu hình nằm trong `server_H264wss.py` (`H264_BITRATE`, `H264_ENCODER="auto"`). Muốn đổi → sửa source → build lại.
8. **Lỗi bind port 10048** khi chạy exe nghĩa là port đang bị process khác giữ (bản debug) — không phải lỗi exe.
9. **Antivirus/SmartScreen** có thể chặn exe PyInstaller (unsigned). Cho phép chạy thủ công nếu bị chặn.
