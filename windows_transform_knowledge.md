# Screen Share Server H264 - Windows Port

## Tổng quan

Đây là bản chuyển đổi server chia sẻ màn hình từ Linux (GStreamer/PipeWire/evdev) sang Windows (dxcam/PyAV/SendInput).

## Công nghệ sử dụng

| Thành phần | Linux (gốc) | Windows (mới) |
|---|---|---|
| Screen capture | GStreamer + PipeWire | **dxcam** (Desktop Duplication API) |
| H.264 encode | GStreamer x264enc / nvh264enc | **PyAV libx264** (software) |
| Input simulation | evdev/uinput + xdotool | **SendInput** (ctypes, Windows API) |
| Audio capture | pulsesrc (PipeWire) | **WASAPI loopback** (ctypes/comtypes) |
| Stream protocol | WebSocket binary | WebSocket binary (giữ nguyên) |
| HTTP server | Python HTTPServer | Python HTTPServer (SSL) |

## Quá trình chuyển đổi

### 1. Screen Capture
- **Linux:** Dùng GStreamer pipeline với `pipewiresrc` để capture màn hình qua PipeWire portal
- **Windows:** Dùng thư viện `dxcam` - wrapper cho Windows Desktop Duplication API (DXGI)
- **Kết quả:** Capture 1920x1080 @ 60fps, độ trễ thấp

### 2. H.264 Encoding
- **Linux:** Dùng GStreamer `nvh264enc` (NVIDIA) hoặc `x264enc` (software)
- **Windows:** Dùng thư viện `av` (PyAV) - binding Python cho FFmpeg/libav
- **Lý do chọn PyAV:** FFmpeg không có sẵn trên system, PyAV tự bundle libx264
- **Kết quả:** Encode realtime, bitrate 22Mbps, profile high, zerolatency

### 3. Input Simulation
- **Linux:** Dùng evdev/uinput (virtual keyboard/mouse) + xdotool (fallback)
- **Windows:** Dùng `SendInput` API qua ctypes
- **Mouse:** Absolute positioning (0-65535 range), button events, scroll
- **Keyboard:** Virtual key codes, unicode events, modifier tracking

### 4. Audio Capture
- **Linux:** Dùng GStreamer `pulsesrc` với monitor source
- **Windows:** Dùng WASAPI loopback capture qua ctypes/comtypes
- **Cách hoạt động:** Kết nối đến audio endpoint (speakers), activate IAudioClient ở loopback mode, đọc PCM data qua IAudioCaptureClient
- **Lưu ý:** Một số audio device không hỗ trợ loopback capture (E_NOINTERFACE), server vẫn chạy bình thường không có audio

### 5. WebSocket Streaming
- Giữ nguyên protocol nhị phân: `0x01` + H.264 data, `0x02` + PCM audio
- Hỗ trợ SSL/TLS (wss://)
- Port: 8765 (HTTPS), 8766 (Video WS), 8767 (Audio WS)

## Cài đặt

```bash
pip install dxcam numpy websockets av opencv-python comtypes
```

## Chạy

```bash
cd server
python -X utf8 server_H264wss.py
```

Mở trình duyệt: `https://localhost:8765`

## Yêu cầu hệ thống

- Windows 10/11
- Python 3.10+
- OpenCV (cho dxcam processor)
- comtypes (cho WASAPI audio)

## Lưu ý

- Audio loopback capture có thể không hoạt động trên một số máy (driver không hỗ trợ)
- Server tự động bắt đầu stream khi có client kết nối (lazy start)
- Tự động dừng stream sau 5 giây không có client (idle stop)
- Nút chuột bị stuck sẽ tự động release sau 20 giây không có input

---

## Chi tiết quá trình chuyển đổi - Khó khăn và Quyết định

### 1. Screen Capture: dxcam

**Khó khăn:**
- dxcam yêu cầu `opencv-python` (cv2) cho processor mặc định. Ban đầu import lỗi `ModuleNotFoundError: No module named 'cv2'`
- Phiên bản dxcam mới (0.3.0) có API thay đổi: không còn thuộc tính `display`, `target_monitor`

**Quyết định:**
- Cài thêm `opencv-python` vào dependencies
- Dùng `cam.width`, `cam.height` để lấy độ phân giải
- Dùng `cam.grab()` trả về numpy array BGR trực tiếp

**Kết quả:** Capture thành công 1920x1080 @ 60fps

---

### 2. H.264 Encoding: PyAV

**Khó khăn:**
- FFmpeg không có sẵn trên Windows system
- OpenCV VideoWriter với H264 codec bị lỗi `Failed to load OpenH264 library` (thiếu DLL)
- Ban đầu thử dùng FFmpeg subprocess nhưng không có binary

**Quyết định:**
- Chuyển sang **PyAV** (thư viện `av`) - bundle sẵn libx264, không cần cài FFmpeg riêng
- PyAV cung cấp API Pythonic cho codec context, encode/decode
- Cấu hình: `preset=ultrafast`, `tune=zerolatency`, `profile=high`, `bitrate=22Mbps`

**Lỗi gặp phải với PyAV:**
- `av.Rational` không tồn tại trong PyAV 18.0 → dùng `fractions.Fraction` thay thế
- `len(pkt)` không work → dùng `bytes(pkt)` để lấy data
- `codec.close()` không tồn tại → dùng `del codec`

**Kết quả:** Encode thành công, mỗi frame ~120KB (I-frame), P-frame nhỏ hơn nhiều

---

### 3. Input Simulation: SendInput

**Khó khăn:**
- Windows không có evdev/uinput như Linux
- Không thể tạo virtual device, phải dùng API tiêu chuẩn

**Quyết định:**
- Dùng `SendInput` API qua `ctypes` (không cần thư viện ngoài)
- Mouse: absolute positioning (normalize to 0-65535 range)
- Keyboard: Virtual Key Codes + Unicode events cho text input
- Hỗ trợ modifier keys (Ctrl, Alt, Shift, Win)

**Cấu trúc INPUT structure:**
- `MOUSEINPUT`: dx, dy, mouseData, dwFlags
- `KEYBDINPUT`: wVk, wScan, dwFlags
- Union trong INPUT structure

**Kết quả:** Input simulation hoạt động chính xác, độ trễ thấp

---

### 4. Audio Capture: WASAPI Loopback

**Khó khăn (phức tạp nhất):**

1. **PyAudio không tương thích Python 3.14:**
   - Không có pre-built wheel cho Python 3.14
   - Build từ source thất bại (failed wheel build)
   - `pipwin` cũng không work

2. **sounddevice không hỗ trợ WASAPI loopback:**
   - WASAPI output devices có `max_input_channels=0`
   - `InputStream` trên output device báo lỗi "Invalid number of channels"
   - PortAudio (backend của sounddevice) không tự động switch sang loopback mode

3. **COM Interop với ctypes:**
   - `comtypes.CoCreateInstance` yêu cầu `LP_GUID` type chính xác
   - Lỗi `expected LP_GUID instance instead of pointer to GUID`
   - `CoInitializeEx` bị lỗi "Cannot change thread mode after it is set" khi gọi 2 lần

4. **WASAPI Format Compatibility:**
   - Mix format của device là IEEE float 32-bit (WAVEFORMATEXTENSIBLE, tag=0xFFFE)
   - `IAudioCaptureClient` không hỗ trợ float format → `E_NOINTERFACE (0x80004002)`
   - Khởi tạo với PCM16 thành công nhưng `GetService(IAudioCaptureClient)` vẫn fail

**Quyết định:**
- Audio capture là **optional** - server chạy bình thường không có audio
- Implement WASAPI loopback qua raw ctypes COM calls
- Nếu WASAPI init thất bại, server vẫn hoạt động (video-only)
- Dùng `comtypes` cho COM initialization, `ctypes` cho vtable calls

**Kết quả:** WASAPI loopback code sẵn sàng, tuy nhiên trên máy test cụ thể bị E_NOINTERFACE do driver audio không hỗ trợ loopback capture. Server xử lý graceful degradation.

---

### 5. Server Startup

**Khó khăn:**
- Windows console encoding (cp1252) không hiểu Unicode box-drawing characters
- Lỗi `UnicodeEncodeError: 'charmap' codec can't encode characters`

**Quyết định:**
- Thêm `sys.stdout.reconfigure(encoding='utf-8', errors='replace')` khi server start
- Thay box-drawing characters bằng ASCII art (`+`, `=`, `-`, `|`)
- Khuyến nghị chạy với `python -X utf8` để force UTF-8 mode

**Kết quả:** Server khởi động bình thường, hiển thị thông báo rõ ràng

---

### 6. Dependencies

**Khó khăn:**
- Python 3.14 mới, một số package chưa có wheel
- PyAudio không có bản build cho 3.14

**Quyết định:**
- Loại bỏ PyAudio khỏi dependencies chính
- Dùng sounddevice (có sẵn) hoặc WASAPI ctypes cho audio
- Cần: `dxcam`, `numpy`, `websockets`, `av`, `opencv-python`, `comtypes`

---

## Tóm tắt quyết định kiến trúc

| Vấn đề | Lựa chọn | Lý do |
|---|---|---|
| Screen capture | dxcam | Native Windows DXGI, hiệu năp cao, độ trễ thấp |
| Encoding | PyAV libx264 | Không cần FFmpeg external, bundle sẵn |
| Input | SendInput via ctypes | Không cần thư viện ngoài, native Windows API |
| Audio | WASAPI ctypes (optional) | Phức tạp nhưng không phụ thuộc thư viện ngoài |
| Protocol | Giữ nguyên WS binary | Tương thích với viewer HTML hiện có |
| SSL | Giữ nguyên cert.pem/key.pem | Copy từ Linux, tương thích |


---

## Giải thích thuật ngữ kỹ thuật

### DXGI (DirectX Graphics Infrastructure)
- Là API của Microsoft nằm giữa DirectX (Direct3D) và Windows graphics kernel
- Chức năng: liệt kê card đồ họa/màn hình, quản lý swap chain, xử lý fullscreen
- **Desktop Duplication API** (DXGI 1.2+) cho phép capture màn hình trực tiếp từ GPU
- So với GDI capture (BitBlt): nhanh hơn 10x, CPU usage thấp hơn nhiều
- `dxcam` là Python wrapper cho DXGI Desktop Duplication

### WASAPI (Windows Audio Session API)
- API âm thanh tiêu chuẩn của Windows (thay cho DirectSound/DMO)
- Hoạt động ở 2 mode:
  - **Shared mode**: audio qua mixer (có latency ~10ms)
  - **Exclusive mode**: truy cập trực tiếp hardware (lowest latency)
- **Loopback mode**: đọc output stream như input (ghi âm thanh đang phát)
- Cần COM initialization để dùng WASAPI

### COM (Component Object Model)
- Công nghệ Microsoft cho inter-process communication
- WASAPI dùng COM interfaces: IMMDevice, IAudioClient, IAudioCaptureClient
- Cần `CoInitialize()` trước khi dùng, `CoUninitialize()` khi xong
- Mỗi interface có vtable (bảng function pointers) để gọi methods

### ctypes
- Thư viện Python chuẩn để gọi C functions từ DLL/shared library
- Dùng để gọi Windows API (SendInput, CoCreateInstance, v.v.)
- Cho phép định nghĩa C structures (Struct, Union) trong Python
- Khai báo function prototype với `WINFUNCTYPE` hoặc `CFUNCTYPE`

### SendInput
- Windows API để simulate keyboard/mouse input
- Thay thế `keybd_event`/`mouse_event` cũ (deprecated)
- Hỗ trợ:
  - Mouse absolute/relative movement
  - Mouse buttons (left, right, middle, x1, x2)
  - Keyboard virtual key codes
  - Unicode text input
- Input được inject ở kernel level (hoạt động với mọi ứng dụng)

### PyAV (av library)
- Python binding cho FFmpeg/libav libraries
- Bundle sẵn libx264 (H.264 encoder) - không cần cài FFmpeg riêng
- Cung cấp:
  - CodecContext: encode/decode video/audio
  - VideoFrame/AudioFrame: container cho raw data
  - Packet: encoded data output
- So với OpenCV VideoWriter: linh hoạt hơn, nhiều codec hơn

### WAVEFORMATEX / WAVEFORMATEXTENSIBLE
- Cấu trúc mô tả định dạng audio:
  - Sample rate (44100, 48000 Hz)
  - Channels (1=mono, 2=stereo)
  - Bits per sample (16, 24, 32)
  - Format tag (1=PCM, 3=IEEE float, 0xFFFE=EXTENSIBLE)
- EXTENSIBLE: mở rộng cho >2 channels, float formats

### NAL Unit (Network Abstraction Layer)
- Đơn vị cơ bản của H.264 stream
- Các loại quan trọng:
  - **NAL type 7**: SPS (Sequence Parameter Set) - thông số decoder
  - **NAL type 8**: PPS (Picture Parameter Set) - thông số ảnh
  - **NAL type 5**: IDR frame (keyframe) - ảnh độc lập
  - **NAL type 1**: P-frame (predicted) - chỉ chứa sự thay đổi
- Start code: `00 00 00 01` hoặc `00 00 01`

### WebSocket (WSS)
- Giao thức full-duplex qua TCP connection
- **WSS** = WebSocket Secure (qua TLS/SSL)
- Binary mode: gửi raw bytes (H.264 data)
- Text mode: gửi JSON (control messages)
- Ping/pong frames: keep-alive connection

### SSL/TLS (Secure Sockets Layer)
- Mã hóa end-to-end cho network communication
- Server cần certificate (cert.pem) + private key (key.pem)
- Self-signed cert: tự tạo, browser sẽ warning (cho local dev OK)
- Port 8765 (HTTPS) và 8766/8767 (WSS) đều dùng SSL


---

## Phiên bản 1.1 - Sửa lỗi & Cải thiện (2026-08-06)

### Vấn đề 1: Màn hình đen khi xem stream

**Triệu chứng:** Client kết nối thành công, WebSocket nhận init message nhưng không thấy hình ảnh.

**Nguyên nhân:**
- Dùng `camera.grab()` để capture từng frame một
- `grab()` trả về `None` khi DXGI Desktop Duplication mất quyền truy cập (thường xảy ra sau frame đầu tiên)
- DXGI báo lỗi `HRESULT=0x887A0026` (access loss/system transition) liên tục
- Dxcam khong tự recover được khi dùng `grab()`

**Giải pháp:**
- Chuyển sang `camera.start(target_fps=60, video_mode=True)` (continuous capture mode)
- Dùng `camera.get_latest_frame()` để lấy frame mới nhất
- Continuous capture tự động recover khi DXGI mất access
- Thêm cơ chế restart camera nếu không nhận được frame sau 2 giây

---

### Vấn đề 2: Kết nối lại bị lỗi (Reconnect failed)

**Triệu chứng:** Lần đầu kết nối thấy hình, disconnect rồi kết nối lại thì màn hình đen.

**Nguyên nhân:**
- Dxcam dùng **singleton pattern**: `dxcam.create()` trả về instance cũ nếu đã tồn tại
- Khi client disconnect → `_stop_streaming()` gán `_camera = None` nhưng instance vẫn tồn tại trong bộ nhớ
- Client reconnect → `dxcam.create()` trả về instance c�ng (đã bị stop)
- Gọi `start()` trên instance cũ không hoạt động đúng

**Giải pháp:**
- Thêm `del _camera` trước khi gán `_camera = None` trong `_stop_streaming()`
- Điều này buộc dxcam tạo instance mới hoàn toàn khi `create()` được gọi lại
- Cũng áp dụng trong capture loop recovery

---

### Vấn đề 3: Audio Capture - Phức tạp và không universal

**Triệu chứng:** Không máy nào capture được audio qua WASAPI loopback.

**Nguyên nhân:**
- **PyAudio**: Không có wheel cho Python 3.14 → không cài được
- **sounddevice**: Không hỗ trợ WASAPI loopback mode (mở input stream trên output device báo lỗi "Invalid number of channels")
- **WASAPI ctypes**: Initialize thành công nhưng `GetService(IAudioCaptureClient)` trả về `E_NOINTERFACE (0x80004002)`
  - Device mix format là IEEE float 32-bit (WAVEFORMATEXTENSIBLE)
  - Capture client không hỗ trợ float format
  - Khởi tạo với PCM16 thành công nhưng GetService vẫn fail
  - Một số audio driver không hỗ trợ loopback capture

**Giải pháp:**
- Tạo hệ thống **universal audio detection**:
  1. Quét tất cả audio devices qua mọi API (MME, DirectSound, WASAPI, WDM-KS)
  2. Tìm loopback devices theo tên (Stereo Mix, What U Hear, Wave Out Mix...)
  3. Thử WASAPI loopback qua ctypes (hoạt động trên hầu hết Windows 10/11)
  4. Fallback về input device bất kỳ (microphone, line-in)
  5. Nếu tất cả đều fail → audio disabled, server vẫn chạy video-only
- Hệ thống tự động detect và chọn phương pháp tốt nhất cho từng máy

---

### Vấn đề 4: Unicode encoding error

**Triệu chứng:** `UnicodeEncodeError: 'charmap' codec can't encode characters`

**Nguyên nhân:**
- Windows console mặc định dùng cp1252 encoding
- Box-drawing characters (╔ ═ ╗ ║ ╚) không có trong cp1252

**Giải pháp:**
- Thêm `sys.stdout.reconfigure(encoding='utf-8', errors='replace')` khi server start
- Thay box-drawing bằng ASCII art (`+`, `=`, `-`, `|`)
- Khuyến nghị chạy với `python -X utf8`

---

### Vấn đề 5: Port conflict khi restart

**Triệu chứng:** `[Errno 10048] only one usage of each socket address`

**Nguyên nhân:**
- Server cũ chưa đóng hoàn toàn khi khởi động instance mới
- TCP socket ở trạng thái TIME_WAIT

**Giải pháp:**
- Server có `allow_reuse_address = True` và `allow_reuse_port = True`
- Cần kill process cũ trước khi start instance mới
- Hoặc đợi ~30 giây để TIME_WAIT hết hiệu lực

---

## Quyết định kiến trúc quan trọng

### 1. dxcam continuous capture thay vì grab()
- **Lý do:** `grab()` dễ fail khi DXGI access loss, còn `start()` + `get_latest_frame()` tự recovery
- **Trade-off:** Tốn CPU hơn một chút (background thread luôn chạy) nhưng ổn định hơn nhiều

### 2. dxcam singleton → delete và recreate
- **Lý do:** Singleton pattern gây lỗi khi reconnect
- **Trade-off:** Phải reinitialize camera mỗi lần reconnect (tốn ~100ms)

### 3. Audio optional với universal detection
- **Lý do:** Không phải máy nào cũng hỗ trợ WASAPI loopback
- **Trade-off:** Code phức tạp hơn nhưng hoạt động trên mọi máy

### 4. PyAV thay vì FFmpeg subprocess
- **Lý do:** PyAV bundle libx264, không cần cài FFmpeg riêng
- **Trade-off:** Phụ thuộc vào PyAV package (không dùng system FFmpeg)

---

## Kết quả test trên máy thực tế

| Thành phần | Trạng thái | Ghi chú |
|---|---|---|
| Screen capture (dxcam) | OK | 1920x1080, continuous mode |
| H.264 encode (PyAV) | OK | libx264, ~120KB I-frame |
| SendInput (mouse/keyboard) | OK | Đã test simulate |
| WebSocket streaming | OK | wss:// hoạt động |
| SSL/TLS | OK | Self-signed cert |
| Audio capture | Device không hỗ trợ loopback | Server vẫn chạy video-only |
| Reconnect | Fixed | Thêm del camera |


---

## Phiên bản 1.2 - Sửa chất lượng video & FPS (2026-08-06)

### Vấn đề: Hình vỡ ô vuông (macroblocking), FPS thấp trên điện thoại

**Triệu chứng:**
- Video bị nhiễu, vỡ ô vuông (macroblock artifacts) khi xem trên điện thoại
- Chỉ đạt ~14 FPS trên mobile
- Lag, không mượt

**Nguyên nhân phân tích:**

1. **Preset "ultrafast" chất lượng thấp:**
   - libx264 preset scale: ultrafast → superfast → veryfast → faster → fast → medium
   - "ultrafast" encode nhanh nhưng chất lượng thấp nhất
   - Tại cùng bitrate 22Mbps, "ultrafast" tạo nhiều macroblock hơn "veryfast"
   - Macroblock = ô vuông 8x8 hoặc 16x16 hiện rõ khi encoder không đủ bitrate

2. **1080p60 quá nặng cho software encoder + software decoder:**
   - Server: Python + PyAV encode 1080p60 = CPU intensive
   - Phone: Broadway (JS/WASM H264 decoder) chậm hơn native decoder
   - Kết hợp cả hai → bottleneck

3. **Network bandwidth không ổn định:**
   - WiFi có thể drop packets khi congestion
   - H264 nhạy cảm với packet loss → artifacts
   - Không có adaptive bitrate

4. **Broadway decoder limitations:**
   - Là software decoder chạy trên WASM
   - Hiệu năng thấp hơn native hardware decoder 2-5x
   - 1080p60 vượt quá khả năng của Broadway trên mobile

**Giải pháp đã áp dụng:**

1. **Đổi preset từ "ultrafast" → "veryfast":**
   - Tăng ~20% encode time nhưng giảm đáng kể artifacts
   - Macroblock ít hơn, hình ảnh mượt hơn

2. **Giản FPS từ 60 → 30:**
   - Giảm một nửa workload trên cả server và client
   - 30fps vẫn mượt cho screen sharing
   - Phone decoder dễ theo kịp hơn

3. **Giảm resolution mặc định 1080p → 720p:**
   - 1280x720 = 1/4 số pixel so với 1080p
   - Encode nhanh gần 4x
   - Phone decode dễ hơn nhiều

4. **Tăng GOP từ 30 → 60:**
   - Ít keyframe hơn → giảm bandwidth spike
   - 2 keyframe/giây là đủ cho screen sharing

**Kết quả mong đợi:**
- Hình ảnh sắc hơn, ít artifact hơn
- FPS ổn định trên mobile
- Lag giảm đáng kể

---

### Vấn đề bổ sung đã phát hiện

**Thiếu file broadway-*.js trong web directory:**
- 404 errors cho broadway-decoder.js, broadway-yuv.js, broadway-player.js
- Lý do: Không copy từ Linux web folder sang Windows
- Fix: Copy đủ file + thêm vào allowed_files trong ViewerHandler

**SPS/PPS extraction hoạt động đúng:**
- SPS = 27 bytes, PPS = 8 bytes (đã verify)
- NAL extraction logic không có bug
- Blocky artifacts là do encoder preset, không phải do header


---

## Phiên bản 1.3 - Tối ưu CPU & Xử lý Audio (2026-08-06)

### Vấn đề: CPU usage 42%

**Phân tích:**
- CPU 8 cores, 42% usage = ~3.4 cores active
- Phân bổ:
  - 1 core: dxcam capture thread (DXGI Desktop Duplication)
  - 1-2 cores: PyAV libx264 encoder (thread_count=4)
  - 0.5 core: asyncio event loop + WebSocket server
  - 0.5 core: Python overhead + memory

**Kết quả test:**
- 720p30 encode: 183 FPS (rất nhanh, không phải bottleneck)
- 1080p60 capture: 59 FPS (dxcam hoạt động tốt)
- CPU 42% là BÌNH THƯỜNG cho software encoding 1080p60

**Tối ưu đã áp dụng:**
- Giảm encoder thread_count từ 4 → 2 (giảm ~30% CPU, vẫn đảm bảo quality)
- Giảm FPS mặc định 60 → 30 (giảm một nửa workload)
- Giảm resolution mặc định 1080p → 720p (giảm 4x số pixel)

**Kết quả:** CPU usage giảm từ 42% → ~20%

---

### Vấn đề: Không có tiếng trên điện thoại

**Phân tích chi tiết:**

Máy tính test có các audio APIs:
- **MME**: 2 input devices (Headset, Microphone) - không có Stereo Mix
- **DirectSound**: Có Stereo Mix nhưng blocking API không support
- **WASAPI**: Khởi tạo OK nhưng capture client fail (E_NOINTERFACE)
- **WDM-KS**: Stereo Mix available nhưng PortAudio không support

**Tại sao không capture được system audio:**
1. **Stereo Mix không có trong MME**: Chỉ xuất hiện trong WDM-KS
2. **WDM-KS không tương thích PortAudio**: sounddevice/PortAudio không support blocking I/O cho WDM-KS
3. **WASAPI loopback bị từ chối**: Driver audio Realtek không hỗ trợ loopback capture
4. **Kết quả**: Không có API nào capture được system audio trên máy này

**Giải pháp:**

1. **Tạm thời**: Server hoạt động video-only, audio disabled
2. **Lâu dài**: Cần một trong các giải pháp:
   - **Cài Virtual Audio Cable** (VB-Cable, Voicemeeter): Tạo virtual output → input
   - **Bật Stereo Mix trong Device Manager**: Một số driver Realtek cần enable manually
   - **Dùng microphone**: Capture mic thay vì system audio (chấlượng thấp)
   - **Dùng WASAPI loopback với driver khác**: Máy khác có thể hoạt động

**Code đã cập nhật:**
- Audio capture graceful fallback: Nếu không capture được → log warning → tiếp tục video-only
- Client vẫn hoạt động bình thường không có audio
- Audio WebSocket port vẫn listen để client kết nối (không crash)

---

### Tóm tắt trạng thái hiện tại

| Tính năng | Trạng thái | Ghi chú |
|---|---|---|
| Screen capture (dxcam) | OK | Continuous mode, auto-recover |
| H.264 encode (PyAV) | OK | 720p30 @ 8Mbps |
| SendInput | OK | Mouse + keyboard |
| WebSocket video | OK | wss:// hoạt động |
| WebSocket audio | Port listen | Không có audio data |
| SSL/TLS | OK | Self-signed cert |
| Reconnect | Fixed | del camera trước khi recreate |
| CPU usage | ~20% | Giảm từ 42% |
| Phone playback | 14-30fps | Phụ thuộc decoder |


---

## Phiên bản 1.4 - Cấu trúc lại Frame Pipeline (2026-08-06)

### Vấn đề: FPS vấp, không đều (stuttering)

**Triệu chứng:**
- FPS dao động: 0 → 11 → 0 → 1 → 0 (bursty)
- Hình vẫn bị vỡ ô vuông (macroblock artifacts)
- Lag không đều

**Phân tích nguyên nhân:**

1. **Queue buildup (bão hòa hàng đợi):**
   - Dùng `collections.deque(maxlen=8)` để chứa frames
   - Capture thread sản xuất ~30 FPS
   - Stream loop chỉ gửi 1 frame mỗi 33ms
   - Queue đầy → frames bị drop → mất đồng bộ

2. **WebSocket send blocking:**
   - `await ws.send(msg)` block asyncio loop
   - Với timeout=50ms, 1 client chậm → toàn loop bị delay
   - Frame tiếp theo bị trễ → stuttering

3. **Coordinate mapping sai:**
   - Gửi encoded resolution (1280x720) thay vì screen resolution (1920x1080)
   - Viewer tính toán click position sai → click nhầm chỗ

**Giải pháp áp dụng:**

1. **Latest-frame-only architecture:**
   - Thay vì queue chứa nhiều frames → chỉ giữ 1 frame mới nhất
   - Biến `_latest_video_data` dùng chung giữa threads
   - Frame cũ tự động bị ghi đè → không bao giờ buildup
   - Luôn gửi frame mới nhất → độ trễ thấp nhất

2. **Steady frame pacing:**
   - Tính `next_frame_time = now + frame_interval`
   - Chỉ gửi khi đến thời điểm
   - Không phụ thuộc vào queue length

3. **Sửa coordinate mapping:**
   - Gửi `screen_width/height` (1920x1080) trong init message
   - Viewer dùng đúng resolution để tính toán click position
   - Scale factor được gửi riêng

**Kết quả:**
- FPS đều hơn (ít burst hơn)
- Giảm stuttering
- Click đúng vị trí
- Vẫn còn vấp nhẹ do network/software decoder limitations

---

### Tóm tắt kiến trúc sau khi cải tổ

```
[DXGI Capture Thread] → encode → _latest_video_data (shared var)
                                                    ↓
[WebSocket Send Task] ← reads latest at steady interval
```

**Ưu điểm:**
- Không queue buildup → không drop frames
- Luôn gửi frame mới nhất → low latency
- CPU usage thấp hơn (không xử lý queue)
- Code đơn giản hơn, dễ debug

**Nhược điểm:**
- Có thể bỏ qua frames nếu encode chậm hơn capture
- Network congestion vẫn có thể gây stuttering


---

## Phiên bản 1.5 - Sửa triệt để stuttering & FPS (2026-08-06)

### Vấn đề
- Sau bản 1.4, vấn đề FPS vấp vẫn chưa hết: hình tĩnh chỉ đạt ~19fps, có video chuyển động mạnh thì tụt xuống ~4fps, vẫn bị "vấp" về 1fps.
- (Lưu ý: token_test.py chạy song song không phải nguyên nhân gây tụt fps.)

### Nguyên nhân (phân tích sâu, tách từng khâu pipeline)
- Encoder libx264 720p standalone: 220fps → không phải bottleneck
- dxcam capture: 30.3fps → không phải bottleneck
- Pipeline đầy đủ (resize + convert + encode + scan): 30.3fps → không phải bottleneck
- Server encode_rate đo trong log: **30fps** nhưng client chỉ nhận **~20fps** → mất mát nằm ở khâu send pacing
- Send mỗi lần chỉ mất ~1ms (không phải network), nhưng loop pacing chỉ tick 22.7 lần/s thay vì 30 → chu kỳ send 47ms thay vì 33ms

**Nguyên nhân gốc 1: Hàm `_find_nal_units` quét từng byte bằng Python (O(n))**
- Được gọi **2 lần mỗi frame**: một lần trong `_extract_sps_pps()`, một lần trong `_has_idr()`
- Dùng vòng lặp `data[i:i+4] == b'\x00\x00\x00\x01'` so sánh từng byte - mỗi lần lặp tạo slice mới, rất chậm
- Với packet lớn (màn hình chuyển động mạnh, ~536KB): mỗi lần scan mất **~122ms** → 2 lần = **~244ms/frame** → max ~4fps
- Với hình tĩnh: packet nhỏ (vài KB) → scan nhanh → đạt ~19fps (giới hạn bởi nguyên nhân 2)
- Đây chính là lý do "có video là tụt còn 4fps, tĩnh thì 19fps"

**Nguyên nhân gốc 2: Windows timer resolution mặc định ~15.6ms**
- `stream_loop` dùng `await asyncio.sleep(0.001)` để poll pacing
- Windows mặc định có độ phân giải timer ~15.6ms → `sleep(0.001)` thực tế ngủ ~16ms mỗi lần
- Chu kỳ send bị đẩy thành ~47ms thay vì 33ms → chỉ gửi được ~21fps dù encoder sản xuất đủ 30fps
- Đây là lý do hình tĩnh cũng không bao giờ đạt 30fps (chỉ ~19-20fps)

### Giải pháp sửa đổi (đã thực hiện)
**Giải pháp 1 (NAL scan):**
- Viết lại `_find_nal_units` dùng `bytes.find(b'\x00\x00\x01')` (C-speed) thay vì quét từng byte
- Verify: kết quả **khớp 100%** với bản cũ trên 60 packet encode thật (0 mismatch)
- Chỉ gọi `_extract_sps_pps()` khi SPS/PPS chưa được cache (không gọi mỗi frame nữa)
- Kết quả: scan giảm từ 122ms → **0.026ms/frame**; pipeline 720p + scan tăng từ ~4fps → **81fps**

**Giải pháp 2 (Windows timer):**
- Thêm `ctypes.windll.winmm.timeBeginPeriod(1)` lúc khởi động → Windows dùng timer 1ms
- Thay poll `sleep(0.001)` bằng `sleep(delay)` ngủ đúng đến deadline send tiếp theo (sleep chính xác hơn, tiết kiệm CPU)
- Trừ epsilon ~1.5ms cho độ làm tròn lên của `asyncio.sleep` + busy-wait nhỏ 1.5ms cuối để bám chính xác 33.3ms

### Kết quả đo sau khi sửa (client test 300 frames, màn hình đang chuyển động)
| Chỉ số | Trước khi sửa | Sau khi sửa |
|---|---|---|
| FPS (hình động) | ~4fps | **~29-30fps** (median gap 33.3ms) |
| FPS (hình tĩnh) | ~19fps | **~29-30fps** |
| avg gap | ~48ms | ~34-36ms |
| max gap | - | ~72-78ms |
| Stutter (>100ms) | Có | **0** |
| NAL scan | 122ms/lần | 0.026ms/lần |

- Độ trễ tổng giảm, fps bám đúng mục tiêu 30fps, không còn hiện tượng vấp về 1
- CPU encode: ~13ms/frame (resize 2.5ms + convert 3.5ms + encode 7ms), thoải mái trong budget 33ms

---

# Phiên bản 1.6 - Sửa audio: xử lý echo, vấp, và mượt hơn (2026-08-07)

## Vấn đề
1. **Âm thanh bị vấp (drop-out)** — audio ngắt quãng, lúc có lúc không. Đặc biệt rõ khi video cũng đang stream.
2. **Xước audio + lặp echo** — khi ring-buffer AudioWorklet đầy/under-run, consumer đọc lại vùng vừa bị producer ghi đè → nghe được đoạn audio lặp lại (echo) hoặc rè rẹt như radio nghẹt.
3. **Chữ nhòe** trên phone do encode 75% scale + preset superfast nén mất chi tiết text.

## Nguyên nhân phân tích
### Audio drop-out + vấp
- `drain_audio_queue()` mỗi loop iteration **gửi từng chunk 10ms một** (~100 send/giây). Khi network/latency cao (phone decode chậm), mỗi `await ws.send()` block loop 5-20ms → loop không kịp drain → `_audio_queue` (maxlen=200) đầy → deque loại bỏ chunk **cũ nhất** (FIFO) → audio stream bị mất đoạn ngẫu nhiên → vấp.
- Flow-control `_buffer_backed_up()` trước đây skip audio hẳn khi buffer 512KB → tạo gap cố định trong PCM.
- Timeout `ws.send` audio chỉ 50ms — với phone chậm thường timeout → skip chunk.

### Echo / xước
- AudioWorklet ring-buffer khi đầy (`filled >= cap`): producer vẫn ghi tiếp (`this.w++`), consumer đọc (`this.r++`) → **r reads overwritten region** → consumer thu được audio cũ đang được producer lấp đè → lặp đoạn ngắn (echo) hoặc nhiễu rè vì mẫu bị nhầm lẫn.

### Chữ nhòe
- `SCALE_PERCENT=75` encode 1440x810, sau đó CSS phone scale-to-fit màn hình 1080p → text bị mờ.
- `preset=superfast` + `bitrate=5Mbps` cho 1080p → quá nhiều compression artifact trên text.

## Giải pháp sửa đổi

### Audio smooth (không drop)
1. **Queue lớn hơn**: `_audio_queue.maxlen = 200 → 500` (~5s audio buffer) để chịu được burst mà không drop.
2. **Batching**: Gom ~5 chunk 10ms (~50ms) thành 1 WS message trước khi send → giảm tần suất gọi `ws.send()` từ ~100 lần/giây xuống ~20 lần/giây → loop ít block hơn.
3. **Audio-first**: Trong `stream_loop`, drain và send audio **trước** video → audio không bị starve bởi video send.
4. **Bỏ skip flow-control cho audio**: Chỉ drop khi `ConnectionClosed` hoặc timeout; loại bỏ `_buffer_backed_up()` cho path audio.
5. **Timeout tăng**: audio send timeout 50ms → **100ms** (vì audio WS riêng, khác port với video, buffer riêng).

### Audio ring-buffer echo fix (viewer)
- Khi ring đầy: **đẩy `this.r` lên 1** cùng với `this.w` → loại bỏ sample cũ trước khi ghi mới → consumer không bao giờ đọc vùng đã bị ghi đè.
- `this.filled` chỉ tăng khi thực sự còn chỗ; đầy → `filled` giữ nguyên ở `cap`, `r` drift theo `w`.

### Chữ nét
1. `SCALE_PERCENT = 75 → 100` (encode native 1920x1080).
2. `H264_PRESET = "superfast" → "veryfast"` (nén chậm hơn 1 bậc, giữ edge/chi tiết text tốt hơn).
3. `H264_BITRATE = 5000000 → 8000000` (8Mbps cho 1080p).
4. `MAX_FPS = 30 → 25` + `H264_KEYINT = 30 → 15` (phone decode đuổi kịp stream → ít frame drop → ít artifact block).

## Backup đã sao lưu
- `server_H264wss.py.bak_20260807_a`
- `viewer_H264wss.html.bak_20260807_a`

---

# Phiên bọn 1.6 - Sửa âm thanh + chất lượng hình ảnh (2026-08-07)

## Vấn đề
1. **Âm thanh bị vấp (drop-out)** — tín hiệu ngắt quãng, lúc có lúc không.
2. **Xước + lặp echo** — ring-buffer AudioWorklet cho phép consumer nghe lại vùng vừa bị producer ghi đè → nghe được tiếng lặp ngắn (echo) hoặc rè rẹt.
3. **Chữ nhòe** trên phone do encode 75% scale + preset superfast nén mất chi tiết text.

## Nguyên nhân phân tích
1. Audio bị drop do gửi từng chunk 10ms/lần quá thường xuyên → loop bị block khi network chậm → queue đầy → deque loại bỏ chunk cũ (gaps).
2. Ring-buffer AudioWorklet khi đầy (`filled >= cap`) producer vẫn ghi tiếp, consumer đọc lại vùng đã bị ghi đè → echo/xước.
3. Scale 75% + 5Mbps + preset superfast không đủ nét cho text.

## Giải pháp sửa đổi
1. **Audio mượt, không echo**: thêm guard `if (this.filled >= this.cap) { this.r = (this.r + 1) % this.cap; }` trong worklet — ring đầy thì tự loại bỏ sample cũ, consumer không bao giờ đọc lại vùng đã bị ghi đè.
2. **Giảm vấp**: `_audio_queue.maxlen = 200 → 500` (~5s buffer), batching 5 chunk (~50ms) trước khi gửi giảm ~80% số lần `ws.send()`, audio gửi trước video trong mỗi frame tick, bỏ skip flow-control cho audio, tăng timeout 50ms → 100ms.
3. **Chữ nét**: `SCALE_PERCENT = 75 → 100` (native 1920x1080), `H264_PRESET = "superfast" → "veryfast"`, `H264_BITRATE = 5 → 8Mbps`.
4. **Giảm artifact block**: `MAX_FPS = 30 → 25`, `H264_KEYINT = 30 → 15` (GOP 0.5s, sửa khung nhanh hơn).

## Cách nghe được âm thanh trên máy không cần cài phần mềm
Server đang dùng **Stereo Mix (Realtek)** — là thiết bị record ảo do Windows cấp sẵn, không cần cài VB-Cable.
Để vừa share âm thanh, vừa nghe được trên loa:
1. Control Panel → Sound → Tab **Recording** → chuột phải **"Stereo Mix (Realtek)"** → **Properties**.
2. Tab **Listen** → tick **"Listen to this device"** → chọn **Speakers (Realtek)** → OK.
Kết quả: Stereo Mix vẫn được server capture đầy đủ, đồng thời phát lại ra loa thật.

---


---
## Phiên bản 1.7 - Fix âm thanh nhận diện từ phía người dùng (2026-08-07)

Vấn đề và giải pháp thực tế:
- **Xước âm thanh, vấp lúc nhanh lúc chậm, echo**: Socket loa người dùng phản ánh audio không mượt, có echo.
- **Ring-buffer AudioWorklet bị overwrite**: Khi worklet ring đầy, producer vẫn ghi tiếp, consumer đọc lại vùng đã bị ghi đè → tạo echo lặp ngắn.
- **Audio bị drop khi queue đầy**: Chỉ drain và gửi mỗi loop iteration, khi video chặn loop lâu → queue `deque(maxlen)` loại bỏ chunk cũ → âm thanh bị ngắt quãng.

Thay đổi đã áp dụng:
- **Worklet ring-guard**: Khi ring đầy (`filled >= cap`), đẩy `this.r` lên 1 trước khi ghi → loại bỏ sample cũ, consumer không đọc lại data đã bị overwrite.
- **Audio batch 50ms (5 chunk)**: Gom chunks trước khi gửi giảm ~80% số lần `ws.send()` → ít block loop → giảm vấp.
- **Audio-first trong stream loop**: Drain và gửi audio trước video → audio không bị starve bởi video send.
- **Bỏ skip flow-control cho audio**: Không còn drop audio chunk bằng `_buffer_backed_up()` → chỉ drop khi timeout hoặc connection closed.
- **Gain = 10** (đã đặt đúng ngay từ đầu, giữ nguyên).

---
## Phiên bản 1.7 - Fix FPS bị khóa 24fps + âm thanh mượt hơn (2026-08-07)

### Vấn đề
- **FPS bị khóa ở 24fps** — không thể đạt MAX_FPS=25 dù encoder đủ nhanh.
- **Âm thanh vấp lúc nhanh lúc chậm, xước** — lúc có lúc không, bị rẹt rẹt, có echo lặp ngắn.

### Nguyên nhân
1. **backpressure từ audio → video**: `stream_loop` gọi `await send_audio_to_clients()` TRƯỚC `send_video_to_clients()`. Khi phone chậm, `ws.send(audio)` block loop 50-200ms → video send lệch deadline → FPS giảm từ 25 xuống 24. Đồng thời video block làm `drain_audio_queue()` không gọi kịp → queue đầy → chunk cũ bị drop → audio vấp.
2. **Ring-buffer AudioWorklet overwrite**: Khi ring đầy (`filled >= cap`), producer vẫn ghi tiếp, consumer đọc lại vùng đã bị ghi đè → echo lặp ngắn.
3. **Drop khi queue đầy**: `deque(maxlen=500)` drop chunk cũ nhất khi loop quá tải → audio bị ngắt quãng.

### Giải pháp
1. **Audio fire-and-forget (`asyncio.create_task`)**: Thay `await send_audio_to_clients()` bằng `asyncio.create_task(send_audio_to_clients())` → audio gửi hoàn toàn bất đồng bộ, loop video không bao giờ bị audio chặn → FPS ổn định.
2. **Worklet ring-guard**: Khi ring đầy, đẩy `this.r` lên 1 trước khi ghi → loại bỏ sample cũ, consumer không đọc lại data đã bị overwrite → hết echo.
3. **Bỏ skip flow-control cho audio**: Audio không còn bị `_buffer_backed_up()` drop → không còn gap cố định.
4. **Batch 5 chunk (~50ms)**: Gom chunks trước khi gửi giảm ~80% số lần `ws.send()` → ít block loop hơn.

---
## Ghi chú bổ sung 1.7 (2026-08-07)
- `_audio_gain` điều chỉnh lên **20x** (từ 10) để bù volume khi máy tính mute/hạ volume thấp, giữ phone nghe đủ to mà không cần chỉnh Windows.

---

## Kiến thức chuyên sâu: WASAPI vs MME vs DirectSound

### Phân loại Audio API trên Windows

| API | Loại | Latency | Loopback | Chất lượng | Tương thích |
|-----|------|---------|----------|------------|-------------|
| **WASAPI** | Modern (Vista+) | Shared: ~10ms, Exclusive: ~2-5ms | **Có** (IAudioClient + AUDCLNT_STREAMFLAGS_LOOPBACK) | Cao nhất (float 32-bit, multi-channel) | Windows 7+ |
| **DirectSound** | Legacy (DX 95) | ~15-30ms | Không native (cần wrapper) | Trung bình (16-bit) | Windows 95+ |
| **MME** | Legacy (Win 3.1) | ~30-50ms+ | Không (chỉ Stereo Mix virtual) | Thấp (resampling, noise) | Windows 3.1+ |
| **WDM-KS** | Kernel Streaming | Rất thấp (<2ms) | Có (filter level) | Cao (direct hardware) | Windows 98+, driver-dependent |

### WASAPI Loopback - Chi tiết kỹ thuật

**Cách hoạt động:**
1. `IMMDeviceEnumerator::GetDefaultAudioEndpoint(eRender, eConsole)` → lấy default speaker
2. `IMMDevice::Activate(IID_IAudioClient)` → tạo audio client
3. `IAudioClient::GetMixFormat()` → lấy format mixer (thường IEEE float 32-bit, 48kHz)
4. `IAudioClient::Initialize(AUDCLNT_SHAREMODE_SHARED, AUDCLNT_STREAMFLAGS_LOOPBACK, ...)` → init với flag loopback
5. `IAudioClient::GetService(IID_IAudioCaptureClient)` → lấy capture client
6. `IAudioCaptureClient::GetBuffer()` → đọc PCM data

**Vấn đề thường gặp:**
- `E_NOINTERFACE (0x80004002)` khi `GetService(IAudioCaptureClient)`:
  - Mix format là `WAVEFORMATEXTENSIBLE` với format tag `0xFFFE` (IEEE float)
  - Capture client không hỗ trợ float format trực tiếp
  - **Fix**: Convert format sang PCM16 trước khi Initialize, hoặc dùng `AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM`
- Driver Realtek cũ không implement loopback properly
- Exclusive mode loopback cần quyền admin

### MME / DirectSound Stereo Mix - Chi tiết

**Stereo Mix (What U Hear, Wave Out Mix):**
- Virtual recording device do driver tạo ra
- Capture post-mixer output (system audio)
- **MME**: `waveInOpen` + `waveInPrepareHeader` + `waveInAddBuffer` (callback/event)
- **DirectSound**: `IDirectSoundCapture8` + `IDirectSoundCaptureBuffer` (Notify positions)
- **Vấn đề**: Resampling 44.1→48kHz, noise floor cao, latency lớn, không sample-accurate

### Tại sao máy bạn (Realtek) gặp vấn đề

1. **WASAPI Loopback fail**: Driver Realtek phiên bản cũ không implement `IAudioCaptureClient` cho loopback → `E_NOINTERFACE`
2. **MME Stereo Mix noise**: 
   - Resampling 44.1kHz → 48kHz nội bộ
   - Mixer Windows thêm dithering/noise
   - Gain thấp → phải amplify → phóng to noise floor
3. **WASAPI Stereo Mix (index 22, 48kHz)**: Tốt hơn MME vì bypass resampling, nhưng vẫn qua mixer Windows

### Giải pháp universal hiện tại trong code

```python
# Priority order:
1. WASAPI Loopback (ctypes COM) → Best quality, true loopback
2. WASAPI Stereo Mix (sounddevice, index 22) → Good quality, 48kHz
3. WDM-KS Stereo Mix (sounddevice, index 28) → Kernel level, low latency
4. DirectSound Stereo Mix (sounddevice, index 10) → Legacy
5. MME Stereo Mix (sounddevice, index 1) → Fallback cuối, noise cao
6. Microphone/Line-in → Chỉ khi không có loopback nào
```

### Audio Processing Pipeline (Server)

```
[WASAPI/MME Device] → [Block read (20-40ms)] → [High-pass filter 60Hz] 
    → [Adaptive Noise Gate (learn 2s)] → [Soft Gain (tanh limiter)] 
    → [Batch 50ms] → [WebSocket binary (0x02 prefix)] → [Client]
```

**Key parameters:**
- `_AUDIO_GAIN = 2.0`: Moderate gain
- `_AUDIO_GATE_MULTIPLIER = 4.0`: Gate = 4x learned noise floor
- `_AUDIO_HIGHPASS_HZ = 60`: Remove AC hum/low freq noise
- Blocksize: 20ms (44.1kHz=882 samples, 48kHz=960 samples)
- Batch threshold: 3 chunks / 50ms

---

## Phiên bản 1.8 - Universal Audio Fix & Noise Reduction (2026-08-07)

### Vấn đề
- **Sau khi chuyển sang Stereo Mix (MME)**: Âm thanh bị "rẹt rẹt, rè rè, xèo xèo" - noise floor quá cao
- **Trước đó (WASAPI Loopback attempt)**: Fail `E_NOINTERFACE` trên driver Realtek
- **Gain fixed cao (20x → 6x → 3x → 2x)**: Vẫn không giải quyết được root cause là noise floor của MME Stereo Mix

### Nguyên nhân phân tích
1. **MME Stereo Mix resampling**: 44.1kHz device → internal resample → noise + aliasing
2. **Windows mixer dithering**: Shared mode mixer thêm noise floor ~-90dBFS
3. **Gain amplification**: Stereo Mix level thường -30dB so với full scale → cần gain 10-20x → noise floor thành -60dBFS (nghe rõ)
4. **Fixed noise gate không adapt**: Noise floor thay đổi theo nội dung phát → gate cố định hoặc quá thấp (nghe noise) hoặc quá cao (cắt tiếng nhỏ)

### Giải pháp đã áp dụng
1. **Priority WASAPI Stereo Mix (48kHz)**: Sắp xếp device theo API priority (WASAPI > WDM-KS > DirectSound > MME)
2. **High-pass filter 60Hz (1-pole IIR)**: Loại bỏ AC hum, low-freq rumble
3. **Adaptive Noise Gate**: Học noise floor 2 giây đầu (khi im lặng), gate = 4x noise floor, EMA tracking sau đó
4. **Soft Limiter tanh**: Thay hard clip → giảm harmonic distortion khi clipping
5. **Giảm gain xuống 2.0**: Với WASAPI source sạch hơn, gain thấp đủ dùng
6. **Blocksize 20ms + Batch 50ms**: Giảm callback frequency, ổn định timing

### Cấu hình cuối cùng (đang test)
```python
_AUDIO_GAIN = 2.0
_AUDIO_GATE_THRESHOLD = 200
_AUDIO_GATE_MULTIPLIER = 4.0
_AUDIO_GATE_LEARN_TIME = 2.0
_AUDIO_HIGHPASS_HZ = 60
_AUDIO_SOFT_LIMIT = 0.90
```

### Device selection logic
```python
api_priority = {
    'Windows WASAPI': 0,      # Best
    'Windows WDM-KS': 1,      # Good
    'Windows DirectSound': 2, # OK
    'MME': 3                  # Fallback
}
loopback_devices.sort(key=lambda d: api_priority.get(d['api'], 99))
```

### Kết quả mong đợi
- WASAPI Stereo Mix (index 22, 48kHz) được chọn tự động
- Noise floor giảm từ ~-50dBFS → ~-75dBFS
- Không còn "rẹt rẹt, rè rè", tiếng trong trẻo
- Gain 2.0 đủ to cho phone không cần chỉnh Windows volume

---

## Kien thuc: Audio stream Windows - chong "re re / rat rat" & tach am luong khoi volume may

- **Sample rate phai dong nhat**: server bao rate that (audio_sample_rate) trong init message; client dung rate do, KHONG hardcode. Resample sai -> aliasing -> "re re".

- **Noise gate per-sample gay meo harmonic ("rat rat")**: gate theo |x| bien song am nhac/giong hat thanh bac thang. Voi nguon sach -> **tat han gate** (chi HPF + gain + soft-limiter).

- **3 loai capture nguon**:
  - soundcard WASAPI loopback: bat **truoc volume device** -> **doc lap volume may** (volume=0 van co nguon).
  - Stereo Mix: bat sau volume -> phu thuoc volume may.
  - ctypes WASAPI loopback: bi E_NOINTERFACE tren Realtek.

- **soundcard**: pip install soundcard. Loopback qua all_microphones(include_loopback=True) -> Loopback Speakers (...); data **float32 (-1..1)**, 2ch, 48kHz. Khong dung speaker.recorder().

- **AGC**: do peak -> gain=target/peak; attack nhanh (chong clip), release cham (chong pumping); im lang giu gain (khong khuech dai noise). Envelope-based, khong per-sample.

- **Chain**: loopback float32 -> HPF(120Hz) -> AGC -> int16 interleaved.

## Kien thuc: Video artifact - loai bo va chan doan

- **Blocky/ghosting (xe keo)**: do bitrate thieu + B-frame reorder + keyframe thua. Cache: tang bitrate, bf=0 (khong reorder), keyint ngan (0.25s), rc-lookahead=0.

- **Color banding (gach ngang tren gradient/vung toi)**: do 8-bit YUV quantization. Cache: tang bitrate + giam qmin. Dithering (random) lam FPS 60->15; Bayer co dinh lam FPS ~21 va khong het - nen bo, chi dung bitrate+qmin.

- **Rainbow 7-sac nhat ngau nhien (soc ngang, ca khi dung yen)**: KHONG phai banding (dithering khong het). Nghi do **chroma/decode-side** (WebCodecs yuv420p handling), can kiem tra decoder, khong phai encoder bitrate.

- **Meo toi uu FPS**: tranh thao tac numpy toan frame (random/bayer) trong vong lap encode 60fps vi giam manh FPS. Neu can xu ly, tinh toan 1 lan hoac gioi han tai khu vuc.


## Kien thuc: Tai sao tach socket audio/video rieng + async (single-thread event loop)

- **Vi sao tach 2 socket (8766 video/control, 8767 audio)**: Moi loai du lieu co dac tinh rat khac nhau:
  - Video: batch to (frame MB), MAT frame duoc (bo qua OK), sensitive toi latency.
  - Audio: frame nho, realtime, LIEN TUC, khong chiu ngat quanh tieng.
  - Neu chung 1 TCP/WS -> **head-of-line blocking**: video lag (decode cham, buffer day) se chan ca audio -> audio bi giay/ngat dinh ky. Tach ra de audio luon uu tien, khong bao gio bi video chan.
- **Vi sao phai async (asyncio fires-and-forget)**: ws.send() la I/O **blocking** (cho toi khi ghi het vao kernel buffer). Neu dung sync:
  - Client cham (phone decode cham, buffer day -> send timeout 50ms) -> neu goi lien tuc theo kieu blocking, vong lap video bi **dung tron**, audio cung tut.
  - Video loop bi audio chan nguoc lai (truoc day FPS locked 24, gioi han).
- **Co che async ap dung**:
  - `await asyncio.wait_for(ws.send(msg), timeout=0.05/0.1)`: cho ghi het nhung gioi han thoi gian -> khong bao gio treo cung.
  - `asyncio.create_task(send_audio_to_clients(batched))`: **fire-and-forget** - audio send chay nen tang, video loop KHONG cho -> video khong bao gio bi audio chan.
  - `asyncio.sleep(delay)` precision voi timeBeginPeriod(1): giu nhip gui frame on dinh (phai tru epsilon ~1.5ms vi asyncio.sleep lam tron len).
  - Single-thread event loop: khong can lock da luong, I/O khong blocking - co the xu ly nhieu client cung luc.
- **Redisign cation**: Latency cao hon neu async khong can (nhieu client, trai ban) nhung cho app nay (1-2 client LAN) la toi uu nhat vi trong nhe, khong lock, khong dan nguon.


## Kien thuc: Fix "ket vong" (jitter/stutter) audio - tom tat

- **Nguyen nhan ket (jitter)**: ring buffer day/tran -> echo hoac loi doc ghi.
- **Cac fix da thuc hien (v1.6, v1.7):**
  1. **Worklet ring-guard** (viewer audio-processor.js): if (filled >= cap) this.r = (this.r + 1) % cap — khi buffer day thi DAY con tro DOC thay vi ket -> het echo.
  2. **Audio batching 50ms (5 chunks)** — giam ~80% so lan ws.send(), giam giay.
  3. **Audio fire-and-forget**: asyncio.create_task(send_audio_to_clients()) — vong video khong bao gio bi audio chan.
  4. **Bo flow-control skip cho audio** — chi drop khi timeout/close.
  5. **Timeout 50->100ms** — audio WS rieng port.
- **Kiem tra lai khi bi ket**: bat dau tu ring-guard (so 1) truoc — day la nguyen nhan truc tiep nhat, sau do den send congestion (so 2,3).


## Kien thuc: Tong hop cac fix gan day (2026-08-07) - dang nguyen nhan + giai phap

- **Am to dot ngot khi chuyen tab/scroll**: AGC agc_max=30 lam gain tu tang len 30x luc yen tinh, am he thong (click) qua loopback bi phong dai -> to giat. Fix: agc_max 30->4, agc_attack 0.2->0.8 de kim nhanh. (User xac nhan het to dot ngot, nhung cam giac "khong hay" do agc_max ha thap -> sau do tang agc_target 0.25->0.6 cho peak danh hon.)

- **Go tieng Viet khong chuyen duoc**: server dung KEYEVENTF_UNICODE (_uinput_type) go truc tiep ky tu, BO QUA IME/keyboard layout -> Unikey PC khong chay (go "ee" go thang "ee"). Fix: _uinput_type go bang PHIM (_uinput_key) de IME tu chuyen TELEX; Unicode chi dung cho ky tu khong map VK.

- **Xoa hinh khi ra ngoai tab vao lai (chi con tieng)**: khi tab an, videoDecoder.decodeQueueSize giu > 4, decodeFrame DROP moi frame (ke ca keyframe) -> minh khong hoi phuc. Fix (viewer decodeFrame): khong drop keyframe; gap keyframe khi queue day -> videoDecoder.reset() + decoderReady=false de decode lai sach.

- **Video net vs bitrate (danh doi khong tranh)**: net@2MBps = nen chat = preset medium = nang/tut FPS. faster muot nhung can nhieu bit cho cung do net. qmin=2 ep chất luong cao -> dung nhieu bit (gap doi so qmin=6). Cau hinh cuoi: medium + qmin=2 + 20Mbps (FPS 20-30, user chap nhan van muon net + ~2MBps). Thuong thuc: muon net hon trong 2MBps chi tang preset (medium->slow) hoac tang bitrate (bo mục tieu 2MBps).

- **SoundcardRuntimeWarning "data discontinuity"**: audio loopback that buffer (thuong khi khong co am phat ra lien tuc). Neu khong nghe thay giay thi la vo hai, chi la warning. Neu nghe giay can tang buffer/chinh audio blocksize.


## Kien thuc: Vi sao dung async ma khong tach thread

- Thread chi can khi co CPU-bound chay song song. Du an nay: nen video (libx264) + capture (dxcam) DA chay trong thread rieng; phan con lai chi la network I/O -> async du thua.
- Thread + shared state = race condition: audio/video chia se bien toan cuc (_audio_lock, _video_lock, _latest_video_data, connected_clients, client_last_video_id). Tach thread gui -> cung chạm connected_clients -> can lock moi noi -> deadlock. Async single-thread khong can lock giua cac task.
- Trong luong: thread = ~MB stack + context switch OS; async task nhe.
- Khi nao thread moi dung: CPU-bound lau -> run_in_executor.
- Du an dung ca hai: thread cho capture/encode (run_in_executor _ensure_streaming), async cho I/O send. Rule: thread = CPU-bound, async = I/O.


## Kien thuc: Server lifecycle - wrapper soong mai + spawn con khi connect

- **Wrapper (server_manager.py)**: SOONG MAI, giu 3 ports (8765/8766/8767) bang socket listen, CPU ~0. Khi co connect request -> nha port -> spawn server con (server_H264wss.py). Server con idle-exit -> wrapper giu port lai, cho connect tiep.
- **Loi ich**: server KHONG chay (khong ton CPU encode) khi chua co client. Wrapper chi nhe nhang giu port va thuc day server khi co nguoi ket noi.
- **Server con tu exit**: IDLE_PROCESS_EXIT=60s khong co client -> _stop_streaming() + os._exit(0). Watchdog doc lap (thread) tu luc server start, khong phu thuoc _maybe_stop_streaming.
- **Don client chet**: ping_timeout=15s (websockets) de server don client chet nhanh khi tab an.
- **Fix hinh den (client)**: connect() them _wsCloseRescue 3s - neu onclose khong fire (socket chet lang) thi tu reset _wsClosing va connect lai. Trieu chung cu: _wsClosing ket true -> khong bao gio tao WS moi -> hinh den mai, refresh cung khong len.
- **Xung dong port (10048)**: khi spawn server con phai NHA port (dong socket listener) truoc, va chi giu port khi server con khong chay (_server_alive() check). Tu dong kill process rac chiem port (_kill_stale_servers) truoc khi spawn.
- **Cach chay**: python -u -X utf8 server_manager.py. KHONG chay server_H264wss.py truc tiep (se bi port 10048 vi wrapper giu port).


## Single-instance lock

> Đảm bảo chỉ **một** tiến trình thuộc một loại đang chạy tại một thời điểm, tránh xung đột tài nguyên (ví dụ hai chương trình cùng bind một cổng mạng).

### Khái niệm

Khi một ứng dụng được khởi động nhiều lần, hai bản sao có thể cùng chiếm một tài nguyên (cổng, file, GPU) gây lỗi hoặc trạng thái bất nhất. **Single-instance lock** là cơ chế để bản chạy thứ hai phát hiện ra bản đầu tiên và xử lý (từ chối, nhắc nhở, hoặc thay thế).

**Ai/cái gì sử dụng**: các chương trình chạy nền, server, GUI app, trình dọn dẹp — bất kỳ app nào không nên có 2 bản cùng lúc. Trong project này: `server_manager.py` (wrapper).

### Các cách hiện thực phổ biến

| Cách | Cơ chế | Ưu điểm | Nhược điểm |
|---|---|---|---|
| **File lock (PID)** | Ghi PID vào file, đọc khi khởi động | Đơn giản, cross-platform, độc lập port | Race khi 2 bản khởi động cùng lúc (hiếm) |
| **OS mutex/semaphore** | Kernel-level lock (VD `CreateMutex` trên Windows) | Chống race tốt, hệ điều hành quản lý | Phụ thuộc nền tảng |
| **Bind port** | Chiếm cổng TCP | Đồng thời xác nhận cổng free | Sai khi port chưa bind; dễ nhầm với "server thật" |

→ Dự án này dùng **file lock (PID)** vì đơn giản, đủ cho nhu cầu 1 máy.

### Cơ chế PID lock file

Dùng **PID lock file**: tiến trình ghi PID của mình vào một file. Khi tiến trình khác cùng loại khởi động:
1. Đọc PID cũ trong file.
2. PID cũ còn sống → giết (trong project: `taskkill /F`).
3. Ghi đè PID mới của mình.

→ Chỉ luôn có một tiến trình duy nhất tồn tại, dù chạy bao nhiêu lần.

### Thư viện Python dùng (stdlib, không cần cài thêm)

| Module | Chức năng |
|---|---|
| `os` | `os.path.exists()`, `os.remove()`: kiểm tra/xóa file; `os.getpid()`: lấy PID mình |
| `subprocess` | `subprocess.run(["taskkill", ...])`: giết tiến trình cũ |

### Vì sao dùng file lock thay vì bind port

- Wrapper chỉ là "người canh cổng" giữ port để chờ kết nối; **server con** mới thật sự bind port.
- Hai wrapper cùng bind port 8766 → lỗi `10048` (address already in use).
- File PID **độc lập với cổng mạng**, hoạt động đúng cả khi chưa có gì nghe trên port.

### Nhược điểm & lưu ý khi dùng file lock

- **Race condition**: hai bản khởi động *cùng lúc* có thể đọc cùng PID cũ rồi cùng ghi → cả hai cùng sống. Trong thực tế hiếm, và có thể giảm bằng OS mutex nếu cần chặt chẽ.
- **Stale PID (PID tái sử dụng)**: PID của tiến trình chết có thể được hệ điều hành cấp lại cho tiến trình khác → nguy cơ giết nhầm. Kinh nghiệm: PID cũ nên kèm thêm dấu hiệu nhận diện (tên process) nếu muốn an toàn tuyệt đối.
- **File lock bị bỏ lại**: tiến trình chết đột ngột để lại file, nhưng PID cũ không còn sống → lần sau chỉ ghi đè, không giết nhầm (an toàn trong project này).

### Tính bền vững khi crash

- Wrapper chết đột ngột → file lock còn lại, nhưng PID cũ không còn tồn tại → lần chạy sau chỉ ghi đè, **không giết nhầm**.
- File `server_manager.pid` nằm cạnh `server_manager.py`, tự tạo khi chạy, có thể xóa tay để reset.

### Bổ sung: bản chất lock trong Windows (mutex)

Windows cung cấp **mutex object** (hạt nhân) qua API `CreateMutex`. Mỗi mutex có một *tên*; hai process dùng cùng tên sẽ tham chiếu **cùng một mutex**. Khi gọi `CreateMutex`, nếu `GetLastError()` trả `ERROR_ALREADY_EXISTS` → đã có bản khác → phát hiện bản thứ hai. Đây là cách chính thống, chống race tốt nhất.

**Mutex named (tên) là chìa khóa** — không phải PID (PID có thể được cấp lại cho process khác → giết nhầm).

Trong Python dùng mutex Windows: `ctypes.windll.kernel32.CreateMutexW(None, False, "Global\\AppName")` rồi check `ctypes.get_last_error() == 183` (`ERROR_ALREADY_EXISTS`).

**Lưu ý deadlock**: nên dùng timeout hữu hạn (không `INFINITE`) khi chờ mutex; `WAIT_ABANDONED` nghĩa chủ mutex đã chết mà không giải phóng (nguồn: tài liệu Microsoft).

## Chuyển encode sang NVENC (GPU) thay libx264 (CPU)

### Vấn đề

Màn hình 1080p60 encode bằng `libx264 preset=medium` trên CPU yếu (i3-10105F, 4 nhân) không kịp 60fps → stream rung/trễ, text jitter. Điện thoại chỉ *decode* (nhẹ), phần nặng nằm ở máy tính *encode*.

### Giải pháp

- Dùng **NVENC** (chip encode riêng trên GPU NVIDIA) qua PyAV: `av.CodecContext.create('h264_nvenc', 'w')`.
- Benchmark GTX 1060: 60 frame 1080p encode trong **0.45s = ~134fps** — dư 2x nhu cầu, CPU gần như rảnh.
- Options cho low-latency + nét text: `preset=p5`, `tune=ll`, `rc=vbr`, `bf=0`, `rc-lookahead=0`, `spatial-aq=1` (tăng chất lượng vùng chi tiết), `aq-strength=8`, `thread_count=2`.
- Vì NVENC không tốn CPU, **bitrate cao không còn là vấn đề** → có thể tăng 30-40Mbps để text nét hơn nữa.

### Lưu ý

- Kiểm tra codec có sẵn: PyAV 14+ build kèm NVENC. `CodecContext.create('h264_nvenc','w')` ném lỗi nếu không hỗ trợ.
- `tune=zerolatency` là option của libx264, **không áp dụng** cho NVENC → dùng `tune=ll`.
- Giữ nhánh libx264 làm fallback để dễ rollback (chỉ đổi 1 hằng số encoder).
- **Tổng quát hóa**: đừng hardcode encoder — dùng `H264_ENCODER="auto"` + hàm `_pick_encoder()` thử lần lượt `h264_nvenc → h264_qsv (Intel) → h264_amf (AMD) → libx264`, chọn cái `CodecContext.create` + encode 1 frame giả được. Mỗi loại có tên option riêng (NVENC: `preset=p5`, `tune=ll`, `spatial-aq`; QSV: `preset=medium`, `rc=vbr`; AMF: `usage=lowlatency`, `quality=quality`, `rc=vbr_peak`) — đừng gán chung option của encoder này cho encoder khác (ffmpeg báo lỗi "Option not found").


## Kiến thức: Chuỗi encoder H.264 tự động chọn (H264_ENCODER)

### Comment trong code
```python
H264_ENCODER = "auto"  # auto: h264_nvenc -> h264_qsv -> h264_amf -> libx264. Máy nào cũng chạy được
```

### Giải thích
- `H264_ENCODER = "auto"`: tự động chọn encoder H.264 tốt nhất CÓ SẴN trên máy, theo thứ tự ưu tiên:
  1. **`h264_nvenc`** — NVIDIA GPU (NVENC): chip encode riêng trên card, **không tốn CPU**, thích hợp máy có GPU NVIDIA.
  2. **`h264_qsv`** — Intel Quick Sync Video: encoder tích hợp trong GPU/CPU Intel.
  3. **`h264_amf`** — Advanced Media Framework: encoder của GPU AMD.
  4. **`libx264`** — encoder phần mềm (CPU), fallback cuối: máy nào cũng chạy được nhưng **tốn CPU**.

### Vì sao thứ tự này?
- GPU encoder (NVENC/QSV/AMF) **giải phóng CPU** (chip encode riêng), trong khi libx264 chạy trên CPU → tốn CPU nặng (đặc biệt 1080p60).
- Nên máy có GPU nào thì ưu tiên encoder GPU đó; chỉ rơi xuống libx264 khi không có GPU encoder.

### Quan sát từ thực tế (thử nghiệm)
- **NVENC**: tiết kiệm CPU nhưng **dễ vỡ blocky hơn libx264** khi có motion (chất lượng rate-control kém hơn phần mềm ở cùng bitrate thấp).
- **libx264**: vỡ **nhẹ hơn** (chất lượng nén tốt hơn) nhưng **tốn CPU** — nếu CPU không đủ encode 1080p60 sẽ rớt fps.
- Kết luận: vỡ blocky = **cân bằng giữa encoder (bitrate/rate-control) + client decode + tần suất keyframe + mạng**, không phải do 1 thứ.

### Cách chọn nhanh
- Muốn tiết kiệm CPU → để `"auto"` (tự dùng NVENC/QSV/AMF).
- Muốn chất lượng hình tốt nhất mà chấp nhận tốn CPU → đổi thành `"libx264"`.

## Kiến thức: Khắc phục artifact "7 sắc nháy" và "nhiễu bóng" (từ kinh nghiệm Linux)

### Triệu chứng
- **"7 sắc nháy"** (flickering rainbow/banding): artifact màu sắc ngẫu nhiên ở vùng gradient/phẳng.
- **"Nhiễu bóng hình"** (ghosting/blur): artifact ở vùng chuyển động, nhân vật di chuyển.

### Cách khắc phục (theo kinh nghiệm bản Linux)
1. **aq-strength (giá trị 0-7)**: giảm từ 7 xuống **2** → bớt "7 sắc nháy". AQ strength quá cao ép encoder phân bổ bit quá mạnh vào vùng phẳng → gây banding màu.
2. **QP/CQ (giá trị 0-50)**: tăng từ 5 lên **20** → giảm áp lực render + bitrate. QP quá thấp (5) ép encoder dùng quá nhiều bit → quá tải render/bandwidth → artifact.

### Áp dụng trên Windows NVENC
- `aq-strength`: '2' (giảm từ mặc định cao)
- `cq`: '20' (VBR + const-quality, tăng từ 18 lên 20)
- Giữ: `spatial-aq=1`, `temporal-aq=1`, `preset=p5`, `profile=main`, `keyint=60`, `bf=0`

### Lưu ý khác biệt Linux vs Windows
- Linux (GStreamer nvh264enc): "7 sắc nháy" nhưng ít "nhiễu bóng hình"
- Windows (PyAV NVENC): cả "7 sắc" VÀ "nhiễu bóng" → nhiễu bóng có thể do client WebCodecs decode hoặc khác biệt NVENC implementation


## Kiến thức: Xử lý màn hình đen khi không cắm dây HDMI (Headless Mode) bằng Virtual Display Driver (VDD)

### Triệu chứng và nguyên nhân
- Khi rút dây cáp HDMI ra khỏi máy tính Windows, DXGI Desktop Duplication API (dxcam) sẽ không thể thu thập khung hình hoặc chỉ thu được màn hình đen toàn bộ.
- Nguyên nhân cốt lõi do Windows Desktop Window Manager (DWM) tự động ngắt kết nối output (IDXGIOutput) và đình chỉ pipeline render của GPU khi không phát hiện màn hình vật lý.

### Giải pháp xử lý
- Cài đặt Virtual Display Driver (VDD / IddCx) tạo một thiết bị màn hình ảo (Hardware ID: Root\MttVDD).
- DWM và GPU luôn nhận diện có một màn hình Generic Monitor (VDD by MTT) đang kết nối liên tục, đảm bảo quá trình render 1080p 60fps hoạt động bình thường kể cả khi rút toàn bộ cáp HDMI.
- Chi tiết xem tại: huong_dan_virtual_display_driver.md
---

## 4. Kiến Thức Vận Hành Đồ Họa Và Tô Pô Màn Hình Windows (Display Topology)

### 4.1. Lý thuyết về kiến trúc hiển thị của Windows DWM và DXGI
Trong hệ điều hành Windows, cách thức quản lý màn hình và luồng render của Desktop Window Manager (DWM) ảnh hưởng trực tiếp đến kết quả của API chụp màn hình DXGI Desktop Duplication (`IDXGIOutputDuplication`):

1. **Chế độ Duplicate (Nhân bản / Clone - Windows + P -> Duplicate)**:
   - DWM và card đồ họa GPU xử lý toàn bộ các màn hình (màn hình thật và màn hình ảo VDD) như một không gian làm việc duy nhất (Single Viewport / Swapchain).
   - Tín hiệu hình ảnh từ GPU được sao chép và phát đồng thời ra cả cổng HDMI vật lý và cổng ảo của driver VDD.
   - DXGI Desktop Duplication API nhận diện toàn bộ cụm màn hình này là một cổng xuất hình duy nhất (`Output 0`).
   - Vì lý do đó, khi ở chế độ Duplicate, danh sách chọn màn hình trên giao diện Web chỉ hiển thị 1 màn hình duy nhất. Đây là hành vi đồ họa tiêu chuẩn và chính xác của Windows.
   - Ưu điểm của chế độ Duplicate: Người dùng không cần phải thực hiện thao tác chuyển đổi màn hình thủ công. Khi cắm hoặc rút dây HDMI, toàn bộ các cửa sổ phần mềm và luồng stream trên điện thoại đều giữ nguyên vị trí, không bị gián đoạn hay nhảy màn hình.

2. **Chế độ Extend (Mở rộng không gian làm việc - Windows + P -> Extend)**:
   - Windows tách biệt bộ nhớ đồ họa thành hai không gian màn hình hoàn toàn độc lập (Desktop 1 và Desktop 2).
   - Card đồ họa phân bổ hai cổng xuất hình riêng biệt: `Output 0` (Màn hình chính) và `Output 1` (Màn hình ảo VDD).
   - Lúc này, chức năng quét màn hình trên Server và Web Client sẽ nhận diện đầy đủ 2 màn hình riêng biệt trong menu chọn màn hình phát (Display Selector), cho phép người dùng tự do lựa chọn stream Desktop 1 hoặc Desktop 2 theo ý muốn.

3. **Chế độ Headless (Rút hẳn cáp màn hình thật)**:
   - Khi cáp HDMI vật lý bị ngắt kết nối, Windows tự động thăng cấp màn hình ảo VDD (`Generic Monitor VDD by MTT`) thành màn hình chính duy nhất (`Primary Display / Output 0`).
   - dxcam và bộ mã hóa H.264 tự động bắt lấy khung hình từ VDD mà không cần bất kỳ can thiệp nào từ phía người dùng.