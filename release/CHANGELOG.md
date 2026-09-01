# CHANGELOG - Xemmanhinh Release Server

## 2026-08-07: Chuyển libx264 encoder sang CRF

### Vấn đề
libx264 encoder đang dùng chế độ bitrate-targeted (maxrate, bufsize, qmin) gây ra chất lượng không ổn định, bandwidth spike không kiểm soát được.

### Nguyên nhân
- `maxrate` + `bufsize` tạo constraint VBV không cần thiết cho streaming local network, gây quality fluctuation
- `qmin=2` quá thấp tạo ra banding artifacts
- Không tận dụng được CRF - cơ chế kiểm soát chất lượng nhất quán của libx264

### Giải pháp sửa đổi
- Xóa `maxrate`, `bufsize`, `qmin` khỏi options của libx264 encoder
- Thêm `crf: '20'` để kiểm soát chất lượng theo CRF (Constant Rate Factor)
- Giữ nguyên các tham số khác: preset, tune, profile, keyint, bf=0, rc-lookahead=0, threads=all cores
## 2026-08-07: NVENC encoder chuyển sang CRF-like (vbr + cq không b)

### Vấn đề
NVENC encoder đang dùng `b` (target bitrate), `maxrate`, `bufsize`, `rc-lookahead` gây quality fluctuation không cần thiết.

### Nguyên nhân
- `b` + `maxrate` + `bufsize` tạo ràng buộc VBV, encoder bị ép phân bổ bitrate cố định thay vì theo chất lượng
- `rc-lookahead=8` gây latency không cần thiết cho streaming low-latency
- Muốn encoder tự phân bổ bitrate theo chất lượng mục tiêu (CRF-like), không bị giới hạn cứng

### Giải pháp sửa đổi
- Xóa `b`, `maxrate`, `bufsize`, `rc-lookahead` khỏi NVENC options
- Giữ `rc: vbr`, `cq: 20` - encoder tự phân bổ bitrate theo chất lượng mục tiêu
- Giữ nguyên các tham số khác: preset=p5, tune=ll, bf=0, spatial-aq=OFF, temporal-aq=ON, aq-strength=2, forced-idr=1

## CHECKPOINT 2026-08-07 22:20: Toàn bộ config encoder hiện tại (còn nhiễu/banding)

### General Config
```
MAX_FPS = 45
SCALE_PERCENT = 100
H264_BITRATE = 22000000        # (chỉ dùng QSV/AMF, libx264 & NVENC đã bỏ)
H264_MAXRATE = 50000000        # (chỉ dùng QSV/AMF)
H264_BUFSIZE = 25000000        # (chỉ dùng QSV/AMF)
H264_PRESET = "medium"
H264_ENCODER = "libx264"       # [TEST] force libx264
H264_TUNE = "zerolatency"
H264_PROFILE = "main"
H264_KEYINT = 60               # keyframe mỗi ~1.3s @45fps
```

### NVENC
```
rc=vbr, cq=20 (CRF-like, không b)
preset=p5, tune=ll, bf=0
spatial-aq=OFF, temporal-aq=ON, aq-strength=2
forced-idr=1, min-keyint=60
threads=2
```

### QSV (chưa đụng, vẫn bitrate-targeted)
```
rc=vbr, maxrate=50M, bufsize=25M, bf=0
preset=medium, threads=2
```

### AMF (chưa đụng, vẫn bitrate-targeted)
```
usage=lowlatency, quality=quality
rc=vbr_peak, maxrate=50M, bufsize=25M, bf=0
threads=2
```

### libx264
```
crf=20 (không maxrate/bufsize/qmin)
preset=medium, tune=zerolatency, profile=main
bf=0, rc-lookahead=0
keyint=60, min-keyint=60
threads=all_cores
```

### Vấn đề tồn tại (known issues)
- Banding trên gradient vẫn còn (crf=20 hơi cao + spatial-aq OFF)
- QSV/AMF vẫn dùng bitrate-targeted, chưa đồng bộ CRF
- H264_ENCODER đang force libx264 để test, sau này nên về auto
- Chưa test thực tế trên máy có GPU (NVENC/QSV/AMF)

## 2026-08-07: Tăng chất lượng CRF 18 + Keyint 120

### Vấn đề
- 800KBps (~6.4Mbps) cho 1080p45: CRF=20 nén quá mạnh, khi motion nhiều thiếu bit → giật khựng
- Keyint=60 (1.3s): keyframe spike quá thường xuyên → khựng theo chu kỳ trên network yếu

### Nguyên nhân
- CRF=20: x264 scale 0-51, 18 là visually lossless, 20 đã có compression artifacts thấy được
- Keyint quá nhỏ → mỗi 1.3s bắt buộc encode 1 frame I (to gấp 5-10x frame P), tạo spike bitrate → network buffer overflow → khựng

### Giải pháp sửa đổi
- CRF 20 → 18: thêm ~30-50% bitrate cho motion, giảm artifacts
- Keyint 60 → 120: keyframe mỗi ~2.7s, giảm 50% tần suất I-frame spike
- Client mới kết nối vẫn có forced-idr riêng, không phụ thuộc keyint
- Cập nhật cả libx264 (crf=18) và NVENC (cq=18)

### Ý nghĩa các tham số
- **CRF (Constant Rate Factor)**: thang 0-51, 0=lossless, 18=visually lossless, 23=mặc định, 51=tệ nhất. CRF thấp hơn = chất lượng cao hơn = bitrate cao hơn
- **Keyint (GOP size)**: khoảng cách giữa 2 keyframe (I-frame). Keyint lớn hơn = ít I-frame hơn = ít spike hơn = mượt hơn trên network, nhưng seek chậm hơn
- **bf=0**: tắt B-frames → không reorder → low latency, không ghosting
- **rc-lookahead=0**: không nhìn trước → giảm latency encode
- **spatial-aq=OFF**: tắt adaptive quantization theo không gian → giảm banding trên gradient
- **temporal-aq=ON**: bật AQ theo thời gian → phân bổ bit cho vùng chuyển động
- **aq-strength=2**: cường độ AQ vừa phải (thang 1-15, thấp = nhẹ nhàng hơn)

## TEST A 2026-08-07: CRF=14 (giảm banding)

### Cấu hình test
- CRF=14 (libx264), cq=14 (NVENC)
- Keyint=120 (giữ nguyên)
- Exe: `server_H264wss_testA.exe`

### Kết quả
- Banding/nhiễu: giảm mạnh, còn ~0.5/10 (hầu như không thấy)
- Hình ảnh: sắc nét, gradient mượt
- Vẫn còn hiện tượng khựng hình sau 1 thời gian (do keyint=120 I-frame spike dày)

### Phân tích
- CRF 14 = gần lossless, encoder cấp đủ bit cho mọi frame → gradient, motion được mã hóa đầy đủ → hết banding
- Bitrate ước tính: ~25-35Mbps cho 1080p45 (tăng ~3-4x so với CRF=18)
- Khựng định kỳ: không phải do CRF, mà do keyint=120 → I-frame spike mỗi 2.7s → network buffer overflow

### Hướng tiếp theo
- Test B: Keyint=300 để giảm tần suất I-frame spike → fix khựng định kỳ

## TEST F 2026-08-07: Dithering ±2 (random mỗi frame)

### Cấu hình
- CRF=18, Keyint=120
- Dithering: tạo mảng random 1920x1080x3 mỗi frame

### Kết quả
- Banding giảm đáng kể
- **FPS rơi xuống 9-10**: CPU không kịp tạo random mỗi frame
- Không khả dụng

## TEST G 2026-08-07: Dithering tối ưu (tile 64x64 cố định)

### Cấu hình
- CRF=18, Keyint=120
- Dithering: tile 64x64 cố định, không tạo random mỗi frame

### Kết quả
- Banding gần như biến mất
- FPS ổn định hơn (~20-28)
- Vẫn còn "sọc đám nháy" do compression artifacts/macroblocking

## TEST H 2026-08-07: NVENC auto + CRF=14 + Keyint=150 + dithering

### Cấu hình
- H264_ENCODER=auto (ưu tiên NVENC)
- NVENC: rc=vbr, cq=14
- libx264 fallback: crf=14
- Keyint=150, dithering ±2

### Kết quả
- Hết nhễu
- Vẫn còn sọc/macroblocking do compression
- Bitrate chỉ ~800KBps (~6.4Mbps) - thấp cho 1080p45

## TEST I 2026-08-07: NVENC rc=cq + cq=12 + weighted_pred + aq-strength=8 + dithering

### Cấu hình
- H264_ENCODER=auto
- NVENC: rc=cq, cq=12, weighted_pred=1, spatial-aq=1, temporal-aq=1, aq-strength=8
- libx264 fallback: crf=14
- Keyint=150, dithering ±2

### Mục tiêu
- Tăng bitrate thực tế cho NVENC bằng rc=cq
- Bảo vệ edge/text bằng spatial-aq + weighted_pred
- Giảm macroblocking trên screen capture

## TEST J (planned): HEVC NVENC

### Cấu hình dự kiến
- Encoder: hevc_nvenc hoặc libx265
- Cấu hình tương tự Test I

### Mục tiêu
- HEVC hiệu quả hơn H264, ít artifacts hơn ở cùng bitrate
- Kiểm tra WebCodecs client có decode được không

## TEST I (retry) 2026-08-07: NVENC VBR cq=12 + b=0/maxrate=0/bufsize=0 + spatial-aq + aq-strength=8

### Vấn đề Test I trước
- `rc=cq` xung đột với `spatial-aq`/`aq-strength`/`weighted_pred` → lỗi `avcodec_open2 returned 22`
- NVENC H264 không hỗ trợ `rc=cq` kết hợp với các AQ options

### Cấu hình sửa lại
- H264_ENCODER=auto
- NVENC: rc=vbr, cq=12, b=0, maxrate=0, bufsize=0 (true quality VBR)
- spatial-aq=1, temporal-aq=1, aq-strength=8
- Bỏ weighted_pred
- Keyint=150, dithering ±2
- libx264 fallback: crf=14

### Mục tiêu
- Tăng bitrate thực tế cho NVENC
- Bảo vệ edge/text bằng spatial-aq mạnh
- Giảm macroblocking trên screen capture

### Trạng thái
- Build bị lỗi do file exe đang bị giữ bởi process đang chạy
- Cần tắt bản Test I cũ rồi build lại

## TEST J (retry) 2026-08-07: NVENC HEVC

### Vấn đề Test J trước
- Code rơi vào branch libx264 vì không có branch `hevc_nvenc`
- Dùng options H264 cho HEVC → lỗi `avcodec_open2 returned 22`

### Cấu hình sửa lại
- H264_ENCODER=hevc_nvenc
- Thêm branch `hevc_nvenc` trong `_init_encoder` với options HEVC
- Cập nhật `_extract_sps_pps` và `_has_idr` để nhận diện NAL types của HEVC
  - HEVC SPS=33, PPS=34, IDR=19/20
  - H264 SPS=7, PPS=8, IDR=5 (giữ nguyên)
- NVENC HEVC: rc=vbr, cq=12, b=0, maxrate=0, bufsize=0
- spatial-aq=1, temporal-aq=1, aq-strength=8
- Keyint=150, dithering ±2

### Lưu ý
- Client WebCodecs trên phone có thể không decode HEVC
- Nếu màn hình đen hoặc lỗi decoder thì client chưa hỗ trợ

## TEST K 2026-08-07: NVENC H264 + cq=14 + dithering ±1

### Cấu hình
- H264_ENCODER=auto (ưu tiên NVENC)
- NVENC: rc=vbr, cq=14, b=0, maxrate=0, bufsize=0
- spatial-aq=1, temporal-aq=1, aq-strength=8
- libx264 fallback: crf=14
- Keyint=150
- Dithering: ±1 (giảm từ ±2)

### Mục tiêu
- Giảm "đám 7 sắc" còn sót lại từ Test I
- Giảm dithering xuống ±1 để nhiễu ít visible hơn
- Tăng cq từ 12 lên 14 để giảm bitrate, có thể giảm artifacts

### Trạng thái
- Build thành công
- Chờ test kết quả

## TEST L 2026-08-07: H264 4:4:4 full chroma

### Vấn đề
- H264 4:2:0 subsampling gây artifacts màu sắc, text/UI bị bleeding
- "Đám 7 sắc" còn sót lại có thể do chroma bị giảm 1/4 độ phân giải

### Cấu hình dự kiến
- H264_ENCODER=auto (ưu tiên NVENC)
- pix_fmt=yuv444p (full chroma, không subsampling)
- profile=high444p cho NVENC, high444 cho libx264
- NVENC: rc=vbr, cq=14, b=0, maxrate=0, bufsize=0
- spatial-aq=1, temporal-aq=1, aq-strength=8
- libx264 fallback: crf=14, profile=high444
- Keyint=150, dithering ±1

### Mục tiêu
- Giữ full độ phân giải màu sắc → text/UI sắc nét
- Giảm artifacts màu sắc, banding
- Kiểm tra WebCodecs client có decode được H264 4:4:4 không

### Lưu ý
- WebCodecs trên phone có thể không hỗ trợ 4:4:4
- Bitrate sẽ cao hơn đáng kể so với 4:2:0
- NVENC có thể không hỗ trợ H264 4:4:4 trên một số GPU

## TEST L 2026-08-07: Cập nhật kết quả test H264 4:4:4

### Kết quả
- WebCodecs client decode được H264 4:4:4 (codec string: `avc1.f42002a`)
- Bitrate ~3.5MBps (~28Mbps)
- Hết nhễu
- Vẫn còn artifacts lâu lâu mới có
- Chất lượng hình ảnh chưa cao

### Phân tích
- 4:4:4 cần bitrate cao hơn nhiều so với 4:2:0
- cq=14 có thể chưa đủ cho 4:4:4
- Cần kiểm tra log xem encoder là NVENC hay libx264 fallback
- Nếu là libx264: CPU gánh nặng, chất lượng có thể không ổn định
- Nếu là NVENC: cần giảm cq xuống 10-12

### Hướng tiếp theo
- Kiểm tra log encoder
- Nếu NVENC: thử cq=10-12
- Nếu libx264: cần giảm resolution/FPS hoặc chấp nhận chất lượng

## TEST O 2026-08-07: NVENC H264 cq=16 + spatial-aq + dithering ±1

### Cấu hình
- H264_ENCODER=auto (ưu tiên NVENC)
- NVENC: rc=vbr, cq=16, b=0, maxrate=0, bufsize=0
- spatial-aq=1, temporal-aq=1, aq-strength=4
- libx264 fallback: crf=16
- Keyint=120
- Dithering: ±1

### Mục tiêu
- Cân bằng giữa bitrate thấp (~1-2MBps) và chất lượng
- Dithering phá banding
- spatial-aq bảo vệ edge/text
- Giữ tương thích WebCodecs (4:2:0)

### Trạng thái
- Build thành công
- Chờ test kết quả

## TEST P 2026-08-07: Bản gốc bitrate-targeted + dithering ±1

### Cấu hình
- H264_ENCODER=libx264 (force)
- H264_BITRATE=22M, H264_MAXRATE=50M, H264_BUFSIZE=25M
- H264_KEYINT=60
- libx264: preset=medium, tune=zerolatency, profile=main
  - qmin=2, maxrate=50M, bufsize=25M
  - Không dùng CRF
- NVENC: rc=vbr, cq=20, b=22M, maxrate=50M, bufsize=25M
  - rc-lookahead=8, spatial-aq=0, temporal-aq=1, aq-strength=2
- Dithering: ±1

### Mục tiêu
- Giữ bitrate thấp (<1MBps) như bản gốc
- Thêm dithering để phá banding
- Kiểm tra chất lượng so với các bản CRF

### Trạng thái
- Build thành công
- Chờ test kết quả

## TEST O 2026-08-07: Phân tích kết quả - config tốt nhất hiện tại

### Kết quả
- Hết nhễu
- Chất lượng tốt nhất trong các test
- Bitrate peak ~3.2MBps
- Còn đám 7 sắc nhẹ khi video nhanh

### Phân tích chi tiết cấu hình

```python
H264_ENCODER = "auto"           # Tự động chọn NVENC nếu có
NVENC: rc=vbr, cq=16            # VBR quality mode, chất lượng cao
      b=0, maxrate=0, bufsize=0  # Không ràng buộc bitrate
      spatial-aq=1              # Bảo vệ edge/text
      temporal-aq=1             # Phân bổ bit cho motion
      aq-strength=4             # Cường độ AQ vừa phải
libx264 fallback: crf=16        # Fallback chất lượng cao
Keyint=120                      # Keyframe mỗi ~2.7s
Dithering ±1                    # Phá banding, không tạo nhiễu visible
pix_fmt = yuv420p               # Giữ tương thích WebCodecs
```

### Tại sao tốt?
1. Dithering ±1 vừa đủ phá banding mà không tạo nhiễu
2. cq=16 cho chất lượng cao hơn cq=18/20
3. spatial-aq=1 giúp text/UI sắc nét
4. VBR không ràng buộc cho encoder tự điều chỉnh bitrate

### Vấn đề còn lại
- Đám 7 sắc nhẹ khi video nhanh → do 4:2:0 chroma subsampling + motion
- Bitrate peak 3.2MBps → hơi cao khi motion nhiều

### Hướng cải thiện
- Tăng aq-strength lên 6-8 hoặc giảm cq xuống 14 để giảm đám 7 sắc
- Tăng keyint lên 150 để giảm bitrate peak

## 2026-08-08: Sửa double-click giữ chuột → drag + check touch lặp double-click

### Vấn đề
1. Double click giữ chuột (không thả) không thực hiện được drag đúng cách; sau khi kéo xong còn gửi click thừa.
2. Nghi ngờ touch dễ bị đi vào thao tác khác (scroll/click nhầm) và dễ lặp double-click.

### Nguyên nhân (phân tích)
- **Mouse**: browser bắn chuỗi `mousedown → mouseup → click → dblclick`; handler `dblclick` cũ gửi 2x `mouse_click` thừa ngay cả sau khi đã drag → server nhận click lạ.
- **Touch – lặp double-click**: có fallback `lastTapTime < 750ms` — khi click đơn của tap 1 đã được gửi (sau 500ms), tap 2 trong 750ms sau đó vẫn bị biến thành double-tap → server nhận **click + double-click** (lặp).
- **Touch – đi vào cái khác**: 
  - Không kiểm tra khoảng cách giữa 2 tap → tap A rồi tap B xa nhau vẫn thành double-click tại B.
  - Ngưỡng vào scroll mode chỉ `dist > 2px` → tay rung nhẹ >2px làm hủy click + gửi scroll nhầm.
  - Sau timeout 250ms, `doubleTapSelecting = false` → kéo double-tap bị biến thành scroll.

### Giải pháp sửa đổi (đã thực hiện)
- **Mouse** (`viewer_H264wss.html`):
  - Theo dõi `_mouseBtnDown` / `_mouseDragged`; kéo rồi nhả → đặt `_suppressClick` để chặn `click` + `dblclick` thừa.
  - Reset `_suppressClick` ở `mousedown` (đầu gesture mới) chứ không reset trong `click` (vì sau drag browser bắn click rồi dblclick — cần giữ flag cho cả 2).
- **Touch**:
  - Bỏ fallback `lastTapTime < 750ms` — double-tap chỉ khi tap 2 tới trong lúc click tap 1 còn chờ (`singleTapTimer`) VÀ gần vị trí tap 1.
  - Thêm `DT_MAX_DIST = 50px` kiểm tra khoảng cách 2 tap → tap xa nhau không thành double-click.
  - Nâng ngưỡng vào scroll từ `2px` → `10px` và chặn khi đang `doubleTapSelecting`/`_mouseHeld`.
  - Drag tiếp tục kể cả sau timeout 250ms bằng cách thêm `_mouseHeld` vào điều kiện gửi `mouse_move`.
- **Build manager wrap K/L/O/P** (`server_manager.py`):
  - `_detect_target()` tự nhận diện tên exe của chính manager → wrap đúng server tương ứng (production / testK / testL / testO / testP).
  - PID lock riêng theo từng wrapper (`server_manager.pid`, `server_manager_testK.pid`, ...).
  - Thêm spec `server_manager_{K,L,O,P}.spec`; đã build đủ 4 exe + rebuild `server_manager.exe`.
  - Cập nhật BUILD.md mục 4.5.

## 2026-08-08: CHI TIẾT kỹ 4 lỗi touch (giải thích sâu) + build manager wrap K/L/O/P

> Entry này bổ sung chi tiết cho entry "Sửa double-click giữ chuột → drag + check touch" phía trên.

### Cơ chế gốc của double-tap
Tap đơn KHÔNG gửi click ngay → chờ 500ms (`singleTapTimer`) xem có tap 2 không:
- Có tap 2 trong 500ms → HỦY click tap 1, thành double-tap (gửi mouse_down → kéo → mouse_up)
- Không có tap 2 → gửi 1 click (`mouse_click`)

### Lỗi 1: Lặp double-click (bỏ fallback 750ms)
- **Code cũ**: ngoài nhánh `singleTapTimer` còn có fallback `else if (now - lastTapTime < 750)` → doubleTapSelecting = true.
- **Vì sao lặp**: `lastTapTime` được đặt trong callback của timer 500ms (dòng 1708: `lastTapTime = Date.now()`) — tức là SAU khi click đơn của tap 1 ĐÃ gửi. Tap 2 trong 750ms sau đó vẫn kích hoạt fallback → thành double-tap → server nhận thêm down/up/click trong khi click tap 1 đã đi rồi = **click + double-click**.
- **Sửa**: bỏ hẳn fallback. Chỉ `if (singleTapTimer && nearPrev)` mới là double-tap. Click tap 1 đã gửi → tap 2 là click riêng.

### Lỗi 2: Double-click nhầm khi tap xa (thêm DT_MAX_DIST = 50px)
- **Code cũ**: chỉ xét thời gian, KHÔNG xét khoảng cách 2 tap → tap A rồi tap B cách 300px (khác icon) trong 500ms → B bị double-click nhầm.
- **Sửa**: thêm `pendingTapClient` lưu vị trí tap 1 (client px); tính `nearPrev = Math.hypot(dx, dy) < 50`. Tap 2 phải GẦN tap 1 mới là double-tap; xa nhau = 2 click riêng ở đúng vị trí.

### Lỗi 3: Rung nhẹ thành scroll (ngưỡng 2px → 10px)
- **Code cũ**: `const justEnteredScroll = !scrollMode && dist > 2` — chỉ cần dịch 2px là vào scroll → click bị hủy + gửi scroll nhầm khi tay rung 3-5px (rất hay xảy ra trên phone).
- **Sửa**: `!scrollMode && !doubleTapSelecting && !_mouseHeld && dist > 10` — nâng lên 10px + chặn vào scroll khi đang double-tap/giữ (tránh xung đột với drag).

### Lỗi 4: Drag ngắt sau 250ms (thêm _mouseHeld)
- **Code cũ**: `if (doubleTapSelecting) { sendMsg mouse_move } else if (scrollMode) { scroll }`. Nhưng `doubleTapSelecting` tự tắt sau 250ms (timer `DT_RELEASE_MS` ở touchstart) → kéo >250ms bị rơi xuống nhánh scrollMode → **drag biến thành scroll**.
- **Sửa**: `if (doubleTapSelecting || _mouseHeld)` — `_mouseHeld` (nút chuột đang giữ) chỉ tắt ở touchend → kéo giữ bao lâu cũng gửi mouse_move đúng.

### Bổ sung: chặn click thừa sau drag trên desktop mouse
- **Vấn đề**: sau khi kéo bằng chuột và nhả, browser bắn `click` rồi `dblclick` → 2 event thừa gửi `mouse_click` lạ.
- **Sửa**: `_suppressClick` được đặt ở `mouseup` khi `_mouseDragged=true`. Reset ở `mousedown` (đầu gesture mới), KHÔNG reset trong `click` — vì cần giữ flag để chặn cả click lẫn dblclick.

### Build server_manager wrap K/L/O/P (đã hoàn thành)
- `server_manager.py` thêm `_detect_target()`: tự nhận diện tên exe → wrap đúng server.
- Bảng ánh xạ: `server_manager.exe`→production, `_K`→testK, `_L`→testL, `_O`→testO, `_P`→testP.
- PID lock riêng từng wrapper (`server_manager.pid`, `server_manager_testK.pid`, ...).
- Đã build đủ 5 exe trong `dist/`: `server_manager.exe` + `server_manager_K/L/O/P.exe`.
- Đã thêm spec `server_manager_{K,L,O,P}.spec` + cập nhật BUILD.md mục 4.5.
- Lưu ý: các server test dùng chung 3 port → chỉ chạy 1 wrapper tại 1 thời điểm.

## 2026-08-08: Rebuild Test O + Test P theo changelog (html mới nhất nhúng trong exe)

### Vấn đề
- Exe test đã build từ trước chứa HTML cũ → fix drag/touch (mousedown/mousedup/dblclick + 4 lỗi touch) KHÔNG có hiệu lực khi chạy exe (server đọc web từ bên trong exe qua `sys._MEIPASS`).
- Source `server_H264wss.py` không còn code dithering (bị ghi đè bởi config production).

### Nguyên nhân
- Exe đóng gói `web/viewer_H264wss.html` qua PyInstaller `--add-data`; sửa html trên đĩa không ảnh hưởng exe cũ → phải REBUILD mới nhúng được.
- Dithering chỉ tồn tại trong exe test cũ, không còn trong source/backup → phải trích xuất từ pyc của exe testO.

### Giải pháp sửa đổi (đã thực hiện)
1. **Trích xuất code dithering từ exe testO** (pyinstxtractor-ng + xdis đọc bytecode):
   - `H264_DITHER = 1` (cường độ ±1), `_dither_tile = None` global.
   - Trong `_encode_frame`: nếu `H264_DITHER > 0` → tạo tile 64x64 cố định `np.random.randint(-H264_DITHER, H264_DITHER+1, (64,64,3), dtype=int16)`, `np.tile` ra đúng kích thước frame, `np.clip(frame.astype(int16)+tile, 0, 255).astype(uint8)` trước khi encode.

2. **Rebuild 2 exe server** (từ source sửa config theo changelog):
   - **`server_H264wss_testO.exe`**: NVENC rc=vbr cq=16, spatial-aq=1, temporal-aq=1, aq-strength=4, keyint=120, preset p5; libx264 fallback crf=16; `H264_DITHER=0` (O chỉ tích hợp html, không dither).
   - **`server_H264wss_testP.exe`**: config v1.56→v1.59 — constqp qp=22, qmin=20, qmax=40, maxrate 20M, bufsize 12M, preset p6, bf=0, lookahead 12, multipass fullres, aq-strength 6, keyint 60; `H264_DITHER=1` (cả html + dither).
   - Cả 2 đều nhúng HTML mới nhất (fix double-click drag + 4 lỗi touch). Đã verify bằng cách extract exe: html trong bundle chứa `_mouseBtnDown`/`DT_MAX_DIST`/`_suppressClick`.

3. **Rebuild 2 wrapper**: `server_manager_O.exe`, `server_manager_P.exe`.

4. **Khôi phục source** về config P + dither (bản backup `.bak_Pv156`).

### Trạng thái
- 4 exe mới trong `dist/`: `server_H264wss_testO.exe`, `server_H264wss_testP.exe`, `server_manager_O.exe`, `server_manager_P.exe`.
- Các exe khác (production, K, L, testA-J) giữ nguyên HTML cũ → muốn có fix phải rebuild riêng.

## 2026-08-08: Rebuild Test K + Test L (html mới nhất nhúng trong exe)

### Vấn đề
- Kế tiếp Test O/P: build thêm Test K và Test L với html mới nhất (fix drag/touch).

### Giải pháp sửa đổi (đã thực hiện)
1. **`server_H264wss_testK.exe`**: NVENC rc=vbr cq=14, spatial-aq=1, temporal-aq=1, aq-strength=8, keyint=150, preset p5; libx264 fallback crf=14; `H264_DITHER=1`.
2. **`server_H264wss_testL.exe`**: NVENC rc=vbr cq=14, aq-strength=8, keyint=150, preset p5, **pix_fmt=yuv444p + profile high444p** (4:4:4 full chroma); libx264 fallback profile=high444 + crf=14; `H264_DITHER=1`.
3. **Rebuild wrapper**: `server_manager_K.exe`, `server_manager_L.exe`.
4. Khôi phục source về config P + dither.

### Trạng thái
- 8 exe KLOP đầy đủ trong `dist/`: server testK/L/O/P.exe + manager K/L/O/P.exe, tất cả nhúng html mới nhất.
- So sánh config: K/O giống nhau chỉ khác cq (14 vs 16) và aq-strength (8 vs 4) + keyint (150 vs 120); L = K nhưng 4:4:4 full chroma.

## 2026-08-08: Phân tích P bị delayed hình ảnh hơn app khác (so sánh config exe O vs P)

### Vấn đề
- App P (testP) hiển thị hình ảnh bị delay rõ rệt hơn các bản khác (O/K/L) dù cùng nguồn capture.

### Nguyên nhân (phân tích)
- Trích xuất và đọc pyc trực tiếp từ `server_H264wss_testO.exe` / `server_H264wss_testP.exe` (pyinstxtractor-ng + marshal), so sánh dict options NVENC thực tế:

| Thông số | testO | testP |
|---|---|---|
| rc | vbr cq=16 | constqp qp=22 (qmin20/qmax40) |
| preset | p5 | p6 |
| b/maxrate/bufsize | không set | 20M/20M/12M |
| rc-lookahead | không set (~0) | **12** |
| multipass | không set | **fullres (2-pass)** |
| aq | spatial+temporal, strength 4 | spatial, strength 6 |
| bf | 0 | 0 |
| keyint | 120 | 60 |

- 3 yếu tố gây delay của P (O/K/L không có):
  1. **`rc-lookahead=12`**: NVENC giữ 12 frame trước khi encode để phân tích → +200ms delay ở 60fps.
  2. **`multipass=fullres`**: 2-pass full resolution, encoder phải buffer nhiều frame cho pass 1 rồi mới encode pass 2 → nguồn delay lớn nhất.
  3. **preset p6**: chậm hơn p5, thời gian encode mỗi frame dài hơn.
- Kết luận: delay do cấu hình encoder NVENC, không phải mạng/decode.

### Giải pháp đề xuất (chưa thực hiện)
- Thử `rc-lookahead=12 -> 0` (hoặc 2-4) và `multipass=fullres -> quarterres` (hoặc bỏ multipass) để giảm latency, giữ constqp qp=22 + cap 20M.
- Nếu cần mượt: đổi preset p6 -> p5.

### Bổ sung: So sánh latency K/L vs O/P (đã đọc config thực tế cả 4 exe)

| Thông số | K | L | O | P |
|---|---|---|---|---|
| rc | vbr cq=14 | vbr cq=14 | vbr cq=16 | constqp qp=22 |
| preset | p5 | p5 | p5 | p6 |
| rc-lookahead | 0 | 0 | 0 | 12 |
| multipass | không | không | không | fullres |
| profile | main | high444p | main | main |
| fps | 45 | 45 | 60 | 60 |
| keyint | 150 | 150 | 120 | 60 |

- Thứ tự nhanh -> chậm: **K ≈ O > L > P**.
  - K và O nhanh nhất, ngang nhau (p5, không lookahead/multipass); cq=14 (K) nặng hơn cq=16 (O) nhưng K 45fps / O 60fps nên độ trễ gần tương đương.
  - L chậm hơn K một chút: 4:4:4 high444p (~1.5x chroma) -> encode lâu hơn mỗi frame.
  - P chậm nhất: lookahead=12 (+200ms @60fps) + multipass=fullres (2-pass) + preset p6.
- Nếu cần 4:4:4 dùng L (chậm hơn K không đáng kể); muốn latency thấp nhất chọn K hoặc O.

## 2026-08-08: Test L đen màn hình khi thoát/vào lại + không xin lại được keyframe

### Vấn đề
- Điện thoại thoát app rồi quay lại → màn hình đen vĩnh viễn trên Test L (4:4:4), các bản 4:2:0 (O/K/P) ít gặp. Client có gửi `request_keyframe` nhưng không nhận được keyframe để decode lại.
- Test L còn bị nhiễu hơn các bản khác.

### Nguyên nhân (phân tích code)
- **Server skip keyframe khi nghẽn** (`server_H264wss.py` `send_video_to_clients`):
  - L là 4:4:4 → bitrate ~1.5x, điện thoại decode chậm → WebSocket nghẽn (`_buffer_backed_up`, buffer > 2MB).
  - Khi nghẽn: server skip frame + đánh dấu `client_needs_keyframe.add(ws)`. Nhưng nhánh `_buffer_backed_up` chạy TRƯỚC điều kiện gửi → **keyframe cũng bị skip** khi buffer vẫn đầy.
  - Quay lại tab: client `request_keyframe` → server encode IDR → nhưng không gửi được (buffer đầy) → client không bao giờ nhận keyframe → đen mãi. Client chỉ decode khi `isKey` (điều kiện `!isKey && !decoderReady` → bỏ frame + xin keyframe tiếp).
- **Vòng lặp chết phía client** (`viewer_H264wss.html` `decodeFrame`):
  - `decodeQueueSize > 4` → drop delta + `videoDecoder.reset()` + `decoderReady=false` → reset xong lại cần keyframe; càng nghẽn càng xin, càng không nhận được.
- Race `_force_keyframe_next` (set trong stream_loop async, đọc trong capture thread) chỉ là yếu tố phụ.
- **Nhiễu L**: NVENC 4:4:4 kém hiệu quả + dither ±1 áp lên cả 3 kênh đầy đủ (4:4:4 không bị chroma subsample che) → noise/banding thấy rõ; cq=14 không đủ bit cho vùng phức tạp khi 4:4:4.
- **Nhận xét thêm (user test)**: L còn có nhiều **đám nháy sọc ngang 7 sắc** (rainbow line artifact) — KHÔNG phải do 4:4:4 và KHÔNG phải do dither (vì từ đầu tới giờ app nào cũng bị, có trước khi thêm dither). Khả năng do encoder/NVENC, cần điều tra riêng nếu muốn hết.

### Giải pháp sửa đổi (đã thực hiện)
- **Server** (`send_video_to_clients` trong tất cả file `server_H264wss*.py`): khi `_buffer_backed_up(ws)` mà frame là keyframe VÀ ws đang nằm trong `client_needs_keyframe` → KHÔNG skip, ưu tiên gửi keyframe (`await ws.send(msg)` timeout 0.1), reset `_buf_skip_count=0`, rồi `client_needs_keyframe.discard` + `client_keyframe_wait_until.pop`. Nếu gửi timeout/đóng → đánh dấu stale. Client đen sẽ nhận lại keyframe để decode sạch.
- **Client** (`viewer_H264wss.html` `decodeFrame`): khi `decodeQueueSize > 4` và gặp keyframe → `videoDecoder.reset()` + `decoderReady=false` + **`requestRemoteKeyframe()`** ngay (trước chỉ reset không xin keyframe → vòng lặp chết).
- **Rebuild 4 exe** `server_H264wss_testK/L/O/P.exe` từ file py riêng (đã verify: HTML có `requestRemoteKeyframe`, bytecode chứa nhánh timeout 0.1 ưu tiên keyframe).
- **Bổ sung 3 fix server (điều tra tiếp vấn đề mất frame)**:
  1. **Không nhận frame khi kết nối vào**: `ws_handler` đặt `client_last_video_id[ws] = get_video_id()` → keyframe đầu có vid == vid treo hiện tại bị skip (`vid == last_vid`). **Sửa**: đặt `client_last_video_id[ws] = -1` → frame đầu (kể cả đang treo) luôn được gửi.
  2. **Watchdog keyframe timeout**: `client_keyframe_wait_until` trước là code chết (set 0.5s nhưng không bao giờ được đọc). **Sửa**: biến thành deadline 3s thật — khi nhận `request_keyframe` hoặc connect đặt `now + 3.0`; trong `stream_loop`, client nào cần keyframe mà quá 3s vẫn chưa nhận → `ws.close()` để client reconnect sạch (tránh đen vĩnh viễn).
  3. **Rò rỉ ws khi keyframe-priority timeout**: nhánh `_buffer_backed_up` + keyframe gửi timeout chỉ `stale.add(ws)` nhưng không bao giờ remove khỏi `connected_clients` (chỉ nhánh ConnectionClosed mới áp dụng). **Sửa**: áp dụng `connected_clients.difference_update(stale)` cho MỌI nhánh sau vòng lặp.
- Nếu L chỉ để test 4:4:4: chấp nhận nhiễu do bản chất 4:4:4, hoặc tăng cq/bitrate; không nên đưa 4:4:4 vào production.

## 2026-08-08: Double-tap ra double-click THẬT (hết đổi tên file) + touch nhạy + scroll nhạy + idle timeout 5 phút

### Vấn đề
- Double-tap trên điện thoại đôi khi KHÔNG mở được file/folder mà bị **nhầm thành đổi tên file** (rename). Nghi do double-tap không thành double-click ở cấp Windows.
- Chạm tay cảm giác "lì": con trỏ chuột chưa đến vị trí chạm ngay.
- Scroll chậm/bị cần di chuyển xa mới vào scroll mode.
- Server tự thoát sau 60s không có client (log `[IDLE] No clients for 60.0s`).

### Nguyên nhân (phân tích code)
- **Double-tap không thành double-click thật**:
  - Client gửi 3 lệnh rời rạc qua network: `mouse_down` → `mouse_up` → `mouse_click`.
  - Mỗi lệnh là 1 round-trip WebSocket riêng; `mouse_click` trên server còn `time.sleep(0.02)`. Khoảng cách giữa 2 lần `mouse_down` thực tế có thể vượt `GetDoubleClickTime()` (500ms) do jitter mạng → Windows không nhận là double-click → **chỉ 1 click vào file đang chọn = RENAME**.
- **Chuột không nhạy**: `onTouchStart` không gửi `mouse_move` (chờ vào scroll mode >10px hoặc click gửi sau 500ms mới move).
- **Scroll lì**: ngưỡng vào scroll mode `dist > 10px`.
- **Idle 60s**: `IDLE_PROCESS_EXIT = 60.0`.

### Giải pháp sửa đổi (đã thực hiện)
- **Server** (5 file `server_H264wss*.py`): thêm lệnh `mouse_dblclick` — thực hiện `_mouse_move` + down/up/down/up **LIỀN MẠCH trong 1 hàm** (sleep 30ms giữa các bước), không bị gián đoạn bởi network → Windows luôn nhận đúng double-click, không thành rename.
- **Client** (`viewer_H264wss.html`):
  - Double-tap: touchstart tap 2 **không gửi mouse_down ngay**; touchend release nhanh (<250ms) → gửi **1 lệnh `mouse_dblclick`** duy nhất tại vị trí tap 2 (`doubleTapPos2`); giữ lâu (timeout 250ms) → mới gửi `mouse_down` để bôi đen. Xoá nhánh gửi `mouse_up`+`mouse_click` rời cũ.
  - `DT_MAX_DIST` 50 → **1000000** (gần như không giới hạn): 2 tap trong cửa sổ thời gian luôn là double-tap, nhận tại vị trí tap 2.
  - Touch nhạy: `onTouchStart` 1 ngón gửi `mouse_move` NGAY tại vị trí chạm (không chờ scroll/click).
  - Scroll nhạy: ngưỡng vào scroll mode `dist > 10` → **`dist > 3`**.
  - Cleanup `doubleTapPos2` ở touchcancel + cuối onTouchEnd.
- **Idle timeout**: `IDLE_PROCESS_EXIT` 60.0 → **300.0 (5 phút)** trong cả 5 file server.
- **Rebuild** `server_H264wss_testO.exe` (đã build với đủ fix).

### Trạng thái
- Đã đồng bộ `mouse_dblclick` + touch nhạy + scroll nhạy + idle 5 phút vào source 5 file.
- testO đã build; testK/L/P chưa rebuild lần cuối với các fix này (cần build khi test).

## 2026-08-08: O lag 25-29fps dù NVENC → nguyên nhân DITHERING là nút thắt CPU → bỏ dither O/P, K/L giữ nguyên

### Vấn đề
- Test O chạy NVENC 1920x1080 nhưng encode chỉ đạt 25-29fps (target 60), hình lag lag dù chỉ 1 client.

### Nguyên nhân (phân tích + đo benchmark)
- Log `[ENCODER] NVENC h264: 1920x1080` → KHÔNG phải fallback libx264 (dòng `threads=8` trong FPS log chỉ là số lõi CPU, không phải thread encoder).
- **Dithering numpy là nút thắt**: mỗi frame 1080p chạy `frame.astype(int16) + tile` + `np.clip` + `astype(uint8)` trên CPU = **~30ms/frame → giới hạn ~34fps** — đúng khớp encode=29-36 thực tế.
- NVENC encode nhanh nhưng phải chờ frame đã qua dithering CPU → encode fps bị kéo xuống.

### Giải pháp sửa đổi (đã thực hiện)
1. **Tối ưu dither** (5 file server): thay vì int16+clip mỗi frame (~30ms), cache 2 mảng uint8 0/1 (`pos=+1`, `neg=-1`) và áp dụng bằng `cv2.add`/`cv2.subtract` saturate → **~7ms/frame** (nhanh gấp ~4x). Đo benchmark: 6.9ms → không còn nút thắt.
2. **Bỏ dither cho O và P** (`H264_DITHER = 0`): O/P ưu tiên 60fps mượt, không cần dither (banding không phải vấn đề chính trên O/P). Rebuild `server_H264wss_testO.exe` (13:13) + `server_H264wss_testP.exe` (13:12).
3. **K và L GIỮ NGUYÊN dither (=1)** — chưa chuyển (K 45fps, L 4:4:4; nếu sau này muốn bỏ thì đổi 1 dòng `H264_DITHER = 1 -> 0` rồi rebuild).

### Đoạn code mẫu (dither tối ưu bằng cv2)
```python
# Cache 1 lần (khi frame đổi size)
tile = np.random.randint(-H264_DITHER, H264_DITHER + 1, (64, 64, 3), dtype=np.int8)
tile_full = np.tile(tile, (h // 64 + 1, w // 64 + 1, 1))[:h, :w]
_dither_tile = ((tile_full > 0).astype(np.uint8), (tile_full < 0).astype(np.uint8))
# Mỗi frame:
bgr_frame = bgr_frame.copy()
cv2.add(bgr_frame, _dither_tile[0], dst=bgr_frame)
cv2.subtract(bgr_frame, _dither_tile[1], dst=bgr_frame)
```

## 2026-08-08: Sửa DOUBLE-TAP hoàn toàn KHÔNG ăn — `clearLongPress()` xóa nhầm `_dtReleaseTimeout`

### Vấn đề
- Double-tap trên O (và các bản khác): chỉ thấy **con trỏ chuột di chuyển** tới vị trí tap nhưng KHÔNG double-click vào file/folder. Dù đã chuyển sang cơ chế `mouse_dblclick` (1 lệnh duy nhất) nhưng double-tap vẫn không bao giờ được gửi đi.

### Nguyên nhân (phân tích code)
- `onTouchEnd()` gọi `clearLongPress()` **ở dòng đầu hàm** trước khi xử lý nhánh double-tap.
- `clearLongPress()` xóa **cả** `_dtReleaseTimeout` (timer quyết định release nhanh → `mouse_dblclick`).
- Khi tới nhánh `if (_dtReleaseTimeout && !scrollMode)` thì `_dtReleaseTimeout` **đã là null** → nhánh `mouse_dblclick` không bao giờ chạy, rơi vào nhánh `else` → **không gửi gì** ngoài `mouse_move` đã gửi ở touchstart → đúng hiện tượng "chỉ thấy chuột di chuyển".
- Bug này có từ lúc chuyển sang cơ chế `mouse_dblclick` (build O 13:19, L 13:24, P 13:25, production 13:23) — exe chưa bao giờ chứa fix.

### Giải pháp sửa đổi (đã thực hiện)
- **Client** (`viewer_H264wss.html`):
  - Thêm hàm mới `clearLongPressTimer()` — **chỉ** clear `longPressTimer` (click phải giữ), KHÔNG đụng `_dtReleaseTimeout`.
  - `onTouchEnd()` dùng `clearLongPressTimer()` thay cho `clearLongPress()` → `_dtReleaseTimeout` còn sống khi nhánh double-tap kiểm tra → `mouse_dblclick` được gửi.
  - Nhánh `touchcancel` tự clear `_dtReleaseTimeout` riêng (vì `clearLongPress()` không còn được gọi ở đầu `onTouchEnd`).
  - Cập nhật comment nhánh double-tap: "250ms" cũ → `DT_RELEASE_MS`.
- **Không đổi server** — `mouse_dblclick` đã đúng.
- **Rebuild toàn bộ**: `server_H264wss.exe` 13:58, `testL` 13:59, `testO` 13:59, `testP` 14:00 (cùng file HTML).

## 2026-08-08: Sửa banner encoder gây hiểu lầm — in đúng encoder thực tế (NVENC/libx264)

### Vấn đề
- Banner khởi động in cố định "PyAV libx264 (software)" dù code tự chọn NVENC → người dùng tưởng P dùng encoder phần mềm.

### Nguyên nhân (phân tích code)
- Banner line ~1893 là `print("|  Encode  : PyAV libx264 (software)              |")` **tĩnh** — in y hệt bất kể `_pick_encoder()` trả về gì. Encoder thật chỉ hiện ở log `[ENCODER]` khi có client kết nối (line ~486).
- Test thực tế trên máy: `h264_nvenc` encode OK; `h264_qsv`/`h264_amf` fail → `_pick_encoder()` trả **h264_nvenc** → P thực sự dùng NVENC, không phải libx264.

### Giải pháp sửa đổi (đã thực hiện)
- 5 file (`server_H264wss.py`, `testK/L/O/P.py`): banner gọi `_pick_encoder()` và in `PyAV {enc_name.ljust(30)}` → hiển thị đúng encoder thật (VD: `PyAV h264_nvenc`).
- **Rebuild toàn bộ**: production 14:07, L 14:07, O 14:07, P 14:07, K 14:08.

## 2026-08-08: Giảm ô vuông (macroblocking) ở P — constqp qp 22->16, qmax 40->28, aq 6->8, keyint 60->150, preset p6->p5

### Vấn đề
- P bị ô vuông (macroblocking) rõ rệt, nhất là vùng phức tạp / motion nhanh.

### Nguyên nhân (phân tích code + kinh nghiệm ghi chép)
- P dùng **constqp qp=22 (qmin20/qmax40)** — QP cố định cao + cho phép QP lên 40 khi bị cap → blocky.
- So sánh với K/O (vbr cq=14/16, aq-strength 8/4, keyint 150) — ít ô vuông hơn hẳn (ghi chép TEST I/I-retry/K/O: cq thấp + aq cao + keyint lớn giảm macroblocking).
- keyint 60 → bitrate spike mỗi 1s, dễ khựng.

### Giải pháp sửa đổi (đã thực hiện)
- `server_H264wss_testP.py`: giữ constqp, **qp 22->16**, **qmin 20->16**, **qmax 40->28** (chặn blocky cực độ), **aq-strength 6->8** (chuẩn K), **preset p6->p5** (nhanh hơn, chất lượng tương đương), **keyint 60->150** (giảm bitrate spike).
- Dự kiến bitrate tăng ~2-3x (từ <1MBps lên 2-3MBps) — chấp nhận được để hết ô vuông.
- **Rebuild** `server_H264wss_testP.exe` 14:13. Backup config cũ: `server_H264wss_testP.py.bak_qp22`.

## 2026-08-08: Thử bản dither tối ưu cv2 ở O/P → fps 50 gây nhiễu → TRỞ VỀ config dither cũ (int16+clip)

### Vấn đề
- Bật lại dither cho O và P bằng **bản tối ưu cv2** (`cv2.add`/`cv2.subtract` ~7ms) → kết quả **fps cao (~50) gây nhiễu** trên màn hình.

### Nguyên nhân (phân tích code + backup cũ)
- Bản cv2: `dtype=np.int8`, `_dither_tile` là **tuple 2 mảng uint8** (`pos=+1`, `neg=-1`), áp dụng bằng `cv2.add/subtract` saturate.
- Config CŨ (backup `.bak_Pv156` / `.bak_P`): `dtype=np.int16`, `_dither_tile` là **mảng int16 đơn**, áp dụng bằng `np.clip(bgr_frame.astype(np.int16) + _dither_tile, 0, 255)`.
- Sự khác biệt cấu hình giữa 2 bản: kiểu dtype (int8 vs int16), cấu trúc cache (tuple uint8 vs mảng int16), phép áp dụng (cv2 saturate vs int16+clip) → bản mới + fps 50 tạo nhiễu nhìn thấy được.

### Giải pháp sửa đổi (đã thực hiện)
- **Trở về đúng config dither cũ (int16+clip)** cho O và P — khôi phục code từ backup.
- `H264_DITHER`: O **= 0** (không dither — đúng changelog: testO không dither), P **= 1** (có dither — đúng changelog: testP H264_DITHER=1).
- **Rebuild** `server_H264wss_testO.exe` + `server_H264wss_testP.exe` 23:23.
- K/L/production giữ nguyên (dither cv2 hiện tại).

## 2026-08-08: Fix màn hình đen khi client mới connect (NVENC bỏ qua force IDR do min-keyint)

### Vấn đề
- Khi điện thoại mở tab mới (192.168.3.203, khác subnet máy 192.168.1.12) kết nối thành công ("Connected") nhưng **màn hình đen** — cả local máy tính lẫn điện thoại đều đen dù send fps vẫn ~37fps (server gửi video đều).

### Nguyên nhân (phân tích code)
- Client mới connect → `ws_handler` set `client_needs_keyframe.add()` + `_force_keyframe_next=True` (server_H264wss_testP.py:1575-1578), capture loop encode frame với `frame.pict_type = PictureType.I` (dòng 617-620, 565-567).
- Nhưng NVENC option `min-keyint = H264_KEYINT = 150` khiến NVENC **bỏ qua** yêu cầu IDR nếu chưa đủ 150 frame kể từ IDR gần nhất → vẫn xuất P-frame.
- Client mới chỉ nhận P-frame (không có IDR) → decoder (WebCodecs/Broadway) không khởi tạo được → đen mãi.
- Watchdog chỉ chờ 3s (`client_keyframe_wait_until`, dòng 1577) nhưng IDR tự nhiên mỗi 150 frame @ ~38fps = ~3.9s > 3s → ws bị đóng (dòng 1795-1805) → client reconnect → lại đen → **vòng lặp vô hạn**.
- Lần đổi `keyint 60→150` (14:13) đã vô tình nâng `min-keyint` lên 150 luôn vì viết `'min-keyint': str(H264_KEYINT)`.

### Giải pháp sửa đổi (đã thực hiện)
- Cả 5 file NVENC (K/L/O/P/production): `'min-keyint': str(H264_KEYINT)` → **`'min-keyint': '1'`** (cho phép force IDR bất cứ lúc nào), giữ nguyên `'g' = H264_KEYINT` cho IDR định kỳ.
- Nhánh libx264 fallback 5 file: `'min-keyint'` cũng → `'1'` cho đồng bộ.
- **Rebuild** `server_H264wss_testP.exe` (bản đang test).
- Cần rebuild lại K/L/O/production khi dùng đến (chưa build ở lần này).

## 2026-08-08: Fix "Keyframe timeout force reconnect" liên tục (NVENC bỏ qua pict_type=I khi rc-lookahead>0)

### Vấn đề
- Sau khi sửa min-keyint=1, client kết nối được nhưng log server vẫn in **"[WS] Keyframe timeout ... force reconnect"** liên tục → client bị đóng/reconnect vòng lặp, màn hình không hiện được.

### Nguyên nhân (phân tích code + test trực tiếp PyAV/NVENC)
- Test thật với `h264_nvenc`: với `rc-lookahead=12`, đặt `frame.pict_type = PictureType.I` giữa luồng encode **bị NVENC bỏ qua hoàn toàn** (không sinh IDR mới, chỉ có IDR đầu luồng + theo GOP).
- Với `rc-lookahead=0`, ép IDR **hoạt động** (sinh IDR ngay, trễ ~2 frame).
- Hệ quả: client mới connect → server set `_force_keyframe_next=True` + `pict_type=I` nhưng NVENC không tạo IDR → client chỉ nhận P-frame → decoder không khởi tạo → watchdog (3s) đóng ws → reconnect → lặp vô hạn.

### Giải pháp sửa đổi (đã thực hiện)
- `server_H264wss_testP.py`: `rc-lookahead: 12 → 0` (NVENC lúc này tôn trọng ép IDR). Với chế độ constqp, lookahead ít ảnh hưởng chất lượng (AQ vẫn hoạt động).
- Tăng watchdog `client_keyframe_wait_until` từ `+3.0s` → `+8.0s` (2 chỗ: ws_handler + request_keyframe) để "thưa ra", không gấp gáp khi mạng chậm.
- **Rebuild** `server_H264wss_testP.exe`.
- Các bản K/L/O/production chưa đổi lookahead (đang dùng 12) — nếu gặp cùng triệu chứng cần áp dụng tương tự.

## 2026-08-08: Khôi phục dither bản tối ưu cv2 cho O/P + ghi nhận nghi ngờ rc-lookahead gây nhễu

### Vấn đề
- Trước đó tạm hồi quy dither O/P về bản cũ int16+clip vì nghi "bản dither mới (cv2) + fps 50 gây nhễu".
- Sau khi fix `rc-lookahead` (12→0, NVENC bỏ qua pict_type=I khi lookahead>0), **nhễu đã hết** → xác nhận nguyên nhân gây nhễu thực sự là `rc-lookahead`, **không phải** bản dither cv2.

### Nguyên nhân (phân tích code + test)
- Kết quả test PyAV/NVENC: lookahead>0 khiến NVENC không tôn trọng `pict_type=I` (ép IDR) → vừa gây "Keyframe timeout" reconnect vòng lặp, vừa tương quan với nhiễu hình khi fps cao.
- Do đó nghi vấn ban đầu đổ lỗi cho dither cv2 là sai.

### Giải pháp sửa đổi (đã thực hiện)
- `server_H264wss_testO.py` + `server_H264wss_testP.py`: khôi phục code dither **bản tối ưu cv2** (cache 2 mảng uint8 0/1 + `cv2.add`/`cv2.subtract` ~7ms) — nhanh gấp ~4x so với int16+clip (~30ms).
- Giữ config chuẩn: `H264_DITHER`: O **= 0** (không dither), P **= 1** (có dither).
- **Rebuild** `server_H264wss_testO.exe` + `server_H264wss_testP.exe` 23:51.

## 2026-08-08: Ghi chú — O chỉ sửa dither code, encoder KHÔNG đổi (O ≠ P)

### Vấn đề
- Sau khi build lại O+P cùng lúc, cần làm rõ: lần build O chỉ thay **code dither** (khôi phục bản cv2 tối ưu ~7ms) + cập nhật comment/khai báo `_dither_tile`, **không đụng config encoder**.

### Nguyên nhân
- `server_H264wss_testO.py` và `server_H264wss_testP.py` hiện **khác nhau ở nhiều config encoder** — chưa đồng bộ.

### Giải pháp sửa đổi (đã thực hiện)
- Ghi nhận **sự khác biệt O vs P** (để thống nhất sau):
  - `rc`: O = VBR cq=16 / P = constqp qp=16
  - `rc-lookahead`: O = không set (mặc định NVENC) / P = 0
  - `qmin/qmax`: O = không set / P = 16/28
  - `multipass`: O = không set / P = fullres
  - `temporal-aq`: O = 1 / P = không set
  - `aq-strength`: O = 4 / P = 8
  - bitrate/buf: O = 22M/50M/25M / P = 20M/20M/12M
  - keyint: O = 120 / P = 150
  - `H264_DITHER`: O = 0 (tắt) / P = 1 (bật cv2)
- Code dither cv2 tối ưu: **cả 2 đều có** (O để tắt cờ, P bật cờ).

## 2026-08-08: Hồi quy dither L/O/P về bản cũ int16+clip (bản cv2 mới nghi gây nhễu) + sửa retry watchdog L/O

### Vấn đề
- Bản dither tối ưu cv2 (add/subtract ~7ms) được bật lại nhưng **nghi gây nhễu** → cần hồi quy.
- L và O chưa được sửa retry watchdog (vẫn 3.0s) — khác P đã sửa 8.0s.

### Nguyên nhân (phân tích code + test)
- Khác biệt 2 bản dither:
  - Bản cv2: `dtype=int8`, `_dither_tile` tuple 2 mảng uint8, `cv2.add`/`cv2.subtract` saturate (~7ms).
  - Bản cũ int16+clip: `dtype=int16`, `_dither_tile` mảng int16 đơn, `np.clip(int16+tile)` (~30ms).
- L/O watchdog `+3.0s` làm watchdog đóng ws quá sớm nếu mạng chậm (P đã `+8.0s`).

### Giải pháp sửa đổi (đã thực hiện)
- `server_H264wss_testL.py` + `server_H264wss_testO.py` + `server_H264wss_testP.py`: code dither → **hồi quy về bản cũ int16+clip** (khôi phục theo backup `.bak_Pv156`). Giữ cờ: O=0, P=1, L=1.
- `server_H264wss_testL.py` + `server_H264wss_testO.py`: watchdog `client_keyframe_wait_until` `+3.0s → +8.0s` (2 chỗ mỗi file) — đồng bộ với P.
- **Rebuild** cả 3 exe 00:02-00:03.

## 2026-08-08: Phân tích — vì sao P ít nhễu hơn L và O

### Vấn đề
- Cần làm rõ nguyên nhân P (constqp) ít nhễu hơn L và O (VBR) khi cùng code dither int16+clip ±1.

### Nguyên nhân (phân tích code — khác biệt encoder config)
| Option | P | L | O | Ảnh hưởng nhễu |
|---|---|---|---|---|
| `rc` | constqp | vbr cq14 | vbr cq16 | constqp QP cố định đều khắp khung, ít dao động chất lượng |
| `qmin/qmax` | 16/28 | không set | không set | P chặn QP≤28 → không bao giờ blocky nặng |
| `multipass` | fullres | không set | không set | 2-pass phân bổ bit tối ưu cho motion |
| `aq-strength` | 8 | 8 | 4 | O aq=4 yếu → vùng chi tiết dễ blocky/nhễu |
| `temporal-aq` | không set | 1 | 1 | dồn bit theo motion → vùng tĩnh ít bit, dither/rò bit nổi rõ |
| `profile` | main | high444p | main | L giữ dither ±1 đầy đủ (4:4:4) → hạt nhễu hiện rõ hơn |

### Giải pháp sửa đổi (đã thực hiện)
- Ghi nhận kết luận: P ít nhễu nhờ (1) constqp+qmax=28 không "đói bit" blocky như VBR khi chạm cap (L/O cap 50M), (2) multipass fullres phân bổ bit tối ưu, (3) KHÔNG dùng temporal-aq (L/O có → vùng tĩnh ít bit, dither ±1 bị phóng đại thành nhễu thấy rõ).
- Chưa thay đổi code — chỉ ghi chú. Hướng cải thiện tiềm năng cho L/O: chuyển sang constqp (như P) hoặc bật multipass/aq-strength=8 / tắt temporal-aq.

## 2026-08-08: Fix màn đen khi quay lại tab sau khi ra ngoài (WS đã chết, không reconnect)

### Vấn đề
- Điện thoại ra ngoài (tab ẩn + mất mạng) → WS video bị đóng → quay lại tab: kết nối được (`[WS] +`, send≈37fps) nhưng **màn hình đen**, trang reload lặp lại nhiều lần.

### Nguyên nhân (phân tích code viewer)
- `scheduleReconnect()` (viewer_H264wss.html): `if (document.hidden) return;` → khi tab ẩn, WS đóng thì **không hẹn connect lại**.
- `visibilitychange` khi hiện tab chỉ gọi `requestRemoteKeyframe()` — nếu WS đã chết (readyState≠OPEN) thì không gửi được gì → không bao giờ tạo WS mới → treo "Connected" ảo + màn đen.

### Giải pháp sửa đổi (đã thực hiện)
- `web/viewer_H264wss.html` (visibilitychange khi hiện lại): nếu `ws` còn OPEN → request keyframe; nếu **WS đã chết → `_wsClosing=false` + gọi `connect()`** để tạo kết nối mới.
- **Rebuild 5 exe** (HTML nhúng trong exe): production 00:12:07, K 00:12:07, L 00:12:53, O 00:12:54, P 00:12:55.

## 2026-08-09: Chống 2 tab cùng lúc gây đen màn hình (BroadcastChannel single-tab lock)

### Vấn đề
- Điện thoại mở 2 tab cùng lúc cùng URL → cả 2 cùng decode → màn hình đen liên tục (server vẫn gửi đều send≈45fps, không lỗi gửi), F5 cũng không hết.

### Nguyên nhân (phân tích code viewer)
- Server gửi đúng cho mọi client; 2 tab cùng nhận stream, cạnh tranh tài nguyên decode trên thiết bị hoặc trình duyệt chặn decode tab sau → đen.
- Viewer trước đây không có cơ chế giới hạn 1 tab.

### Giải pháp sửa đổi (đã thực hiện)
- `web/viewer_H264wss.html` — thêm **BroadcastChannel `h264wss_single_tab`**:
  - Mỗi tab có `_tabId = Date.now()+random`; gửi `claim` ngay + mỗi 3s.
  - Tab nhận `claim` có id **lớn hơn** (mở sau) → `supersede()`: đóng WS/audio, dừng decode, hiện "Đã bị thay thế bởi tab khác".
  - `pagehide`/`beforeunload` gửi `bye` → tab cũ nhận `bye` → **nhận lại quyền** (reconnect).
  - `connect()` + `scheduleReconnect()` chặn khi `_superseded`.
  - Khởi tạo `initSingleTab()` trước `connect()` (delay 300ms để claim kịp).
- **Rebuild 5 exe** 00:22: production, K, L, O, P.

## 2026-08-09: K — sửa retry watchdog 3s → 8s (đồng bộ L/O/P)

### Vấn đề
- K chưa được nâng `client_keyframe_wait_until` lên 8.0s như L/O/P (còn 3.0s) → watchdog đóng WS sớm khi mạng chậm.

### Giải pháp sửa đổi (đã thực hiện)
- `server_H264wss_testK.py` (2 chỗ: ws_handler + request_keyframe): `+3.0s → +8.0s`.
- **Rebuild** `server_H264wss_testK.exe` 00:24.

## 2026-08-09: Phân tích — khác biệt K vs L (encoder gần giống nhau, chỉ khác profile)

### Vấn đề
- Làm rõ vì sao K và L tuy gần giống hệt nhưng trông nhễu khác nhau.

### Nguyên nhân (phân tích code)
- K và L có **mọi option NVENC giống nhau**: VBR cq=14, aq-strength=8, spatial-aq+temporal-aq, bf=0, keyint=150, min-keyint=1, forced-idr=1, dither=1, bitrate 22M/50M/25M.
- **Khác đúng 1 điểm: `H264_PROFILE`** — K = `main` (4:2:0), L = `high444p` (4:4:4).
  - L (4:4:4): giữ nguyên 100% chroma → gradient màu mượt, **hết banding** → **không nhễu**.
  - K (4:2:0): chroma bị subsample còn 1/4 → vùng gradient màu bị **banding/răng cưa** → **nhễu thấy rõ**.

### Giải pháp sửa đổi (đã thực hiện)
- Ghi nhận kết luận chính thức (đã xác nhận thực tế trên màn hình): **L (4:4:4) không nhễu, K (4:2:0) nhễu** — do 4:2:0 gây banding màu. **P (constqp) không nhễu.**
- Chưa thay đổi code — chỉ ghi chú.

## 2026-08-09: Phân tích — khác biệt K vs P (nguồn nhễu của K)

### Vấn đề
- K nhễu trong khi P ít nhễu — cần làm rõ nguyên nhân.

### Nguyên nhân (phân tích code — so sánh encoder config)
| Option | K | P (không nhễu) | Ảnh hưởng |
|---|---|---|---|
| `rc` | vbr cq=14 | constqp qp=16 | VBR chạm cap 50M → QP cao → blocky; P QP cố định |
| `qmin/qmax` | không set | 16/28 | P chặn QP≤28, K không có giới hạn |
| `multipass` | không set | fullres | P 2-pass phân bổ bit tối ưu hơn |
| `temporal-aq` | 1 | không set | K dồn bit theo motion → vùng tĩnh ít bit, dither/rò bit nổi rõ |
| `aq-strength` | 8 | 8 | giống nhau |
| `rc-lookahead` | không set | 0 | — |
| `profile` | main | main | giống nhau |
| dither | int16+clip ±1 | int16+clip ±1 | giống nhau |

### Giải pháp sửa đổi (đã thực hiện)
- Ghi nhận kết luận: K nhễu hơn P do (1) VBR không chặn QP khi chạm cap, (2) temporal-aq làm vùng tĩnh đói bit → dither ±1 phóng đại, (3) thiếu multipass fullres.
- Chưa thay đổi code — chỉ ghi chú. Hướng cải thiện K: chuyển sang config P (constqp + multipass + bỏ temporal-aq).

## 2026-08-09: Fix kẹt đen do tab chủ chết đột ngột — viewer tự nhận lại quyền sau 5s

### Vấn đề
- O không reconnect sau khi ra ngoài quay lại → vẫn là bệnh "WS chết không reconnect" nhưng ở nhánh mới của BroadcastChannel.
- Khi tab bị thay thế (`_superseded`), nó ngừng decode chờ tab chủ đóng. Tab chủ đóng bình thường gửi `bye` → tab cũ lấy lại quyền. Nhưng tab chủ chết **đột ngột** (crash/tắt trình duyệt/mất mạng, không fire `pagehide`/`beforeunload`) → không gửi `bye` → tab phụ **kẹt `_superseded=true` vĩnh viễn** → không bao giờ reconnect → đen mãi.

### Nguyên nhân (phân tích code)
- `web/viewer_H264wss.html` cơ chế single-tab chỉ dựa vào `bye` khi đóng tab; không có watchdog phát hiện tab chủ biến mất không báo.

### Giải pháp sửa đổi (đã thực hiện)
- Thêm `_lastClaimSeen` (cập nhật mỗi khi nhận claim từ tab khác).
- Trong `supersede()`: thêm **watchdog 5s** — nếu vẫn `_superseded` mà `Date.now() - _lastClaimSeen > 5000` (không còn claim nào = tab chủ đã chết) → tự gỡ `_superseded` + `scheduleReconnect(500)`.
- **Rebuild 5 exe** 00:34: production, K, L, O, P.

## 2026-08-09: Phân tích — dự đoán O nhễu hơn P (chờ xác nhận thực tế + hướng xử lý)

### Vấn đề
- Xác định mức nhễu tương đối O vs P trước khi quyết định hướng xử lý.

### Nguyên nhân (phân tích code — so sánh encoder config)
| Option | O | P | Ảnh hưởng |
|---|---|---|---|
| `rc` | vbr cq=16 | constqp qp=16 | VBR chạm cap 50M → QP cao → blocky; P QP cố định |
| `qmin/qmax` | không set | 16/28 | P chặn QP≤28 |
| `multipass` | không set | fullres | P phân bổ bit tối ưu hơn |
| `temporal-aq` | 1 | không set | O dồn bit theo motion → vùng tĩnh đói bit |
| `aq-strength` | 4 | 8 | O aq yếu nhất → vùng chi tiết dễ blocky |
| `H264_DITHER` | **0 (tắt)** | **1 (bật)** | O KHÔNG có hạt phá banding → banding nặng nhất |
| `rc-lookahead` | không set | 0 | — |
| `profile` | main | main | giống nhau |

### Giải pháp sửa đổi (đã thực hiện)
- Dự đoán thứ tự nhễu (nhiều → ít): **O > K > L ≈ P** — O tệ nhất do dither tắt + aq=4 + VBR + temporal-aq; K nhễu do 4:2:0 + VBR + temporal-aq; L và P không nhễu (L 4:4:4 giữ nguyên chroma, P constqp chặn QP).
- Chưa thay đổi code — chờ kiểm chứng thực tế trên màn hình và quyết hướng xử lý (gợi ý: O có thể bật lại dither hoặc chuyển sang config P).

## 2026-08-09: LƯU Ý QUAN TRỌNG — nhễu có thể do cấu hình đẩy FPS cao gây ra

> **⚠️ LƯU Ý QUAN TRỌNG: Nhễu trên màn hình có thể KHÔNG phải do chất lượng encode, mà do cấu hình encoder khiến FPS tăng cao gây ra nhiễu hình ảnh (kèm ghi chú các trường hợp đã từng gặp: dither cv2 + fps ~50 gây nhễu; rc-lookahead cũng bị nghi ngờ gây nhễu ở fps cao). Khi phân tích nhễu sau này, PHẢI xét cả yếu tố FPS hiện tại chứ không chỉ so sánh config encoder.**

- Các bản hiện tại: K/L = 45fps, O/production = 60fps, P = 32fps.
- O nhễu (dự đoán, fps cao 60fps), K nhễu (45fps), L không nhễu (45fps), P không nhễu (32fps) — fps khác nhau nên không thể quy fps là nguyên nhân duy nhất, cần so sánh thêm config encoder.

### BỔ SUNG (hiệu chỉnh theo thực tế)
- **P KHÔNG bị nhễu** (xác nhận thực tế trên màn hình).
- **P thực tế chỉ đạt ~32fps (encode), KHÔNG cao bằng O.** → giả thuyết "P nhễu do fps cao" là sai; P fps thấp hơn vẫn không nhễu.
- **Kết luận: P không nhễu là do config constqp (chặn QP qmax=28, multipass fullres, không temporal-aq, dither bật), không phải do fps.**
- Giả thuyết "nhễu do fps cao" chỉ đáng xét cho các bản thực sự chạy fps cao (O/production ~60fps, từng ghi nhận cv2 + ~50fps gây nhễu).

### BẢNG SO SÁNH TOÀN BỘ (K/L/O/P/production)

| Config | production | K | L | O | P |
|---|---|---|---|---|---|
| MAX_FPS | 60 | 45 | 45 | 60 | 60 |
| rc | constqp qp=16 | vbr cq=14 | vbr cq=14 | vbr cq=16 | constqp qp=16 |
| qmin/qmax | 16/28 | không set | không set | không set | 16/28 |
| multipass | fullres | không set | không set | không set | fullres |
| aq-strength | 8 | 8 | 8 | 4 | 8 |
| temporal-aq | không set | 1 | 1 | 1 | không set |
| profile | main | main | high444p | main | main |
| rc-lookahead | 12 | không set | không set | không set | 0 |
| H264_DITHER | 1 | 1 | 1 | 0 | 1 |
| H264_KEYINT | 60 | 150 | 150 | 120 | 150 |
| H264_BITRATE | 20M | 22M | 22M | 22M | 20M |
| H264_MAXRATE | 20M | 50M | 50M | 50M | 20M |
| REALISTIC FPS | ~60 | ~38 | ~38 | ~60 | ~32 |
| Nhễu (thực tế) | — | nhễu | không nhễu | nhễu (dự đoán) | không nhễu |

## 2026-08-09: Fix "quay lại tab thì không điều khiển được" (touch bị chặn) — viewer

### Vấn đề
- Khi chuyển app/khóa màn hình rồi quay lại tab: hình ảnh reconnect OK nhưng **không điều khiển được gì cả** (không move, không click/touch). Refresh trang thì hoạt động bình thường.

### Nguyên nhân (phân tích code)
- `viewer_H264wss.html` touch 1 ngón bị chặn ở dòng `if (_blockRemote || twoFingerActive) return;` trong `onTouchStart`.
- `_blockRemote=true` + `twoFingerActive=true` được set khi **2 ngón chạm** (pinch/zoom). Khi kết thúc bình thường, `touchend` reset về `false`.
- Khi **khóa màn hình / chuyển app / tắt màn hình giữa lúc đang pinch 2 ngón** → trình duyệt KHÔNG fire `touchend`/`touchcancel` (chỉ fire `visibilitychange`) → `twoFingerActive` và `_blockRemote` **kẹt `true` vĩnh viễn**.
- Quay lại tab: video reconnect OK (hình hiện lại) nhưng dòng chặn trên **chặn toàn bộ touch** → không điều khiển được. Refresh trang = reset toàn bộ biến JS → hoạt động lại. → khớp đúng triệu chứng user báo.

### Giải pháp sửa đổi (đã thực hiện)
- Trong handler `visibilitychange` (khi tab hiện lại), thêm **reset toàn bộ gesture state**: `twoFingerActive`, `wasTwoFinger`, `_blockRemote`, `gestureActive`, `scrollMode`, `_scrollAccum`, `doubleTapSelecting`, `oneFingerDrag`, `scrollStarted`, `longPressFired`, `touchStartPos`, `touchLastY`, `twoFingerLastDist`, `twoFingerLastMid`, `twoFingerInitialized`; clear các timer (`singleTapTimer`, `longPressTimer`, `_scrollExitTimer`, `_dtReleaseTimeout`); nếu đang giữ chuột `_mouseHeld` → gửi `mouse_up` dự phòng để không kẹt nút ở server.
- **Rebuild 5 exe**: production + K/L/O/P (~01:06-01:09), viewer mới nằm trong `release/server/web/viewer_H264wss.html`.

## 2026-08-09: Test L — bỏ temporal-aq, thêm qmin/qmax, thêm multipass

### Vấn đề
- L (4:4:4) vẫn nhễu nhẹ dù đã hết banding chroma.

### Nguyên nhân
- L dùng VBR không chặn QP (qmin/qmax), temporal-aq=1 làm vùng tĩnh đói bit, thiếu multipass phân bổ bit tối ưu.

### Giải pháp sửa đổi (đã thực hiện)
- Bỏ `temporal-aq`
- Thêm `qmin=16`, `qmax=28`
- Thêm `multipass=fullres`
- Giữ nguyên VBR cq=14, profile high444p, spatial-aq, aq-strength=8
- Rebuild L ~01:14

### Kết quả test thực tế (xác nhận từ user)
- **L (4:4:4 VBR cq=14 qmin=16 qmax=28 multipass=fullres, không temporal-aq)**: nhễu **hết hoàn toàn, không một tí gì**. Độ nét và độ mượt khung hình chưa đánh giá.

## 2026-08-09: Test O — bỏ temporal-aq, thêm qmin/qmax, thêm multipass

### Vấn đề
- O dự đoán nhễu nặng nhất (dither OFF + 4:2:0 + temporal-aq + không qmin/qmax + không multipass).

### Giải pháp sửa đổi (đã thực hiện)
- Bỏ `temporal-aq`
- Thêm `qmin=16`, `qmax=28`
- Thêm `multipass=fullres`
- Giữ nguyên: VBR cq=16, aq-strength=4, dither OFF, profile main (4:2:0), keyint=120, maxrate=50M, bitrate=22M
- Rebuild O ~01:27

## 2026-08-09: Fix P_new — UnboundLocalError _dither_tile trong _encode_loop (encode loop chết, không xuất frame)
O_new và P_new là bản tối ưu LAG so với O/P gốc (2026-08-09 mục "Test O_new + Test P_new" trong CHANGELOG):
Khác biệt chính so với O/P cũ
Phần	O/P cũ	O_new/P_new
Capture + encode	Cùng 1 thread, encode chậm block capture	Tách thread, queue size=1, drop frame cũ khi encoder chậm
BGR→YUV420P	NVENC tự convert	frame.reformat(yuv420p) qua sw_scale nội bộ PyAV
IDR tự động	_encode_gop_count tự đánh I mỗi H264_KEYINT	NVENC min-keyint=1 đã handle, bỏ đếm tay
Dither (P_new)	Trong capture thread	Trong encode thread (không làm capture chậm)
NVENC lookahead O_new	Có thể có	Bỏ rc-lookahead để force-IDR hoạt động đúng
Viewer NAL parse	Byte-scan + alloc mỗi NAL	_nalSlots reuse, _findStartCode linear scan
Viewer AVCC	data.slice + alloc Uint8Array mỗi frame	_avccOut reuse buffer
Viewer decode queue	Reset khi queue > 4 (giật khi queue tạm tăng)	2-tier: SOFT=2 (giữ mượt), HARD=4 (chống lag)
Viewer render	Mặc định 2D canvas	_new.html = 2D, _wgl.html = WebGL GPU path
Viewer đi kèm
- viewer_H264wss_O_new.html — O + NAL/AVCC/queue tối ưu
- viewer_H264wss_P_new.html — P + tương tự
- viewer_H264wss_O_wgl.html — O + WebGL
- viewer_H264wss_P_wgl.html — P + WebGL
Có cần thiết không?
Có, vì:
- Nếu chỉ giữ O/P gốc thì không có fix queue, không có WebGL path.
- O/P cũ vẫn dùng được nhưng lag + nhễu + không có GPU render.
Nếu muốn đơn giản: bỏ O/P cũ, lấy O_new/P_new làm bản chính (đổi VIEWER_FILE trong spec).

### Vấn đề
- Chạy server_manager_P_new.exe (wrap server_H264wss_testP_new.exe): client connect thành công, server log [STREAM] Started, [CAPTURE] Continuous capture started (encode thread detached), **NHƯNG** log có dòng:
  
  Exception in thread encode-loop:
  File "server_H264wss_testP_new.py", line 594, in _encode_loop
  UnboundLocalError: cannot access local variable '_dither_tile' where it is not associated with a value

  Sau đó [FPS] encode=0.0 send=0.0 mãi, client nhận WS nhưng không bao giờ nhận được keyframe → bị watchdog Keyframe timeout → force reconnect → vòng lặp vô tận.
- O_new không lỗi vì H264_DITHER=0 (nhánh if không vào, không đụng _dither_tile).

### Nguyên nhân
- Trong _encode_loop(), có nhánh if H264_DITHER > 0: rồi bên trong gán _dither_tile = np.tile(...). Python phân tích biến tên _dither_tile xuất hiện gán trong hàm → coi nó là **local** của hàm, kể cả khi global cùng tên đã tồn tại.
- Khi đọc _dither_tile ở dòng if _dither_tile is None ... (chạy trước dòng gán), Python báo UnboundLocalError vì local chưa được gán giá trị nào trước đó trong scope hàm.
- Bản P cũ (cùng thread) chạy được vì code dither nằm trong _encode_frame (hàm khác), _dither_tile ở đó là global đúng cách. Sau khi tách thread, đoạn dither được move sang _encode_loop nhưng quên global _dither_tile ở đầu hàm.

### Giải pháp sửa đổi (đã thực hiện)
- Thêm global _dither_tile ngay đầu nhánh if H264_DITHER > 0: trong _encode_loop của server_H264wss_testP_new.py (line ~591).
- Rebuild server_H264wss_testP_new.exe (kích thước giảm nhẹ vì không còn bug path).
- O_new không lỗi (DITHER=0) nhưng vẫn có global _dither_tile để tránh tương tự nếu sau này bật dither.
### File thay đổi
- release/server/server_H264wss_testP_new.py (+1 dòng global _dither_tile)
- release/server/server_H264wss_testP_new.exe (rebuild ~91.9 MB)

## 2026-08-09: Kết luận WebGL viewer (test O_wgl + P_wgl)

### Test thực tế
- **WebGL path (viewer_H264wss_O_wgl.html / _P_wgl.html)**: VideoFrame upload trực tiếp lên GPU qua `texImage2D`, fragment shader vẽ fullscreen quad. Stats hiển thị `#N (WebGL)` xác nhận GPU path active.

### Kết luận
- **Hình ảnh nhẹ hơn (CPU rảnh)**: drawImage 2D canvas copy frame qua CPU mỗi lần → tốn ~5-10ms/frame + render pipeline nặng. WebGL zero-copy qua GPU → CPU gần như rảnh, paint chỉ còn GPU shader (1-2ms).
- **Độ trễ vẫn còn**: WebGL không giải quyết latency từ capture → encode → WS → decode. Nguồn lag vẫn là:
  - Server: encode (NVENC ~5-15ms / libx264 ~20-50ms)
  - Transport: WS TCP write buffer + LAN latency
  - Decode: WebCodecs HW ~5-15ms / Broadway phone ~30-80ms
- **Nhễu (banding) không mất hẳn**: WebGL chỉ đổi cách render, không đụng encode. Nhễu từ chroma subsampling 4:2:0 + QP cao vùng flat + temporal-AQ vẫn còn. Muốn hết nhễu cần đụng config encoder (dither, qmin/qmax, multipass) — đã có ở bản L và test gần đây.

### Áp dụng
- Dùng `_wgl.html` khi CPU cao / pin yếu (mobile, laptop).
- Dùng `_new.html` (2D) khi cần tương thích tối đa (browser cũ, không WebGL).
- Broadway fallback luôn dùng 2D (Broadway là software, không upload GPU được).

## 2026-08-09: Keep Screen Bright khi có client (chống màn idle/tắt khi reconnect)

### Vấn đề
- Máy tính idle → màn hình tắt/sleep theo Windows power policy → DXGI capture trả về frame đen.
- Client reconnect sau khi màn đã tắt → server gửi keyframe nhưng client thấy đen vì capture đang lấy frame từ display đã off.
- Trước đây user phải tự di chuột/phím để wake máy trước khi reconnect.

### Nguyên nhân
- Windows không có cơ chế tự wake khi có TCP connection tới.
- Sleep policy (Settings → Power → Screen & sleep) vẫn chạy bình thường kể cả khi server đang listen port 8765/8766.

### Giải pháp sửa đổi (đã thực hiện)
- Thêm `SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED)` khi có client kết nối (gọi trong `ws_handler` và `audio_ws_handler`).
- Khi tất cả client disconnect + audio ngắt → gọi `SetThreadExecutionState(ES_CONTINUOUS)` để trả máy về chế độ idle bình thường.
- Tận dụng lịch check idle có sẵn (`_schedule_idle_exit` → `_monitor`): nếu không còn client + đã qua 5s → gọi `_wake_display_off()`.
- Khi có 1 client mới connect (kể cả là reconnect sau khi màn tắt) → `_wake_display_on()` được gọi → màn sáng trở lại trong ~1-2s → user thấy được nội dung ngay khi client vừa nhận IDR.

### Files thay đổi (áp dụng cho cả O_new/P_new và các bản gốc O/L/K/P)
- release/server/server_H264wss.py (production)
- release/server/server_H264wss_testK.py
- release/server/server_H264wss_testL.py
- release/server/server_H264wss_testO.py
- release/server/server_H264wss_testP.py
- release/server/server_H264wss_testO_new.py
- release/server/server_H264wss_testP_new.py
- Rebuild tất cả exe tương ứng

### Lưu ý
- Chỉ giữ sáng khi CÓ client. Khi không có ai connect → màn sleep bình thường theo policy → không tốn pin.
- Nếu user muốn tắt hẳn máy hoặc sleep thủ công vẫn được (SetThreadExecutionState chỉ yêu cầu, không block shutdown).
- Khi server process exit (idle 5 phút qua wrapper) → OS tự reset execution state về mặc định.

## 2026-08-09: 1 IP = 1 session (mới thay cũ) - chống xung đột WS cũ

### Vấn đề
- Cùng 1 IP (phone/PC) reconnect nhiều lần do mạng yếu → nhiều WS cũ vẫn còn trong connected_clients (chưa kịp finally). Khi WS mới được add → server phải gửi frame cho cả WS cũ (đã chết nhưng chưa close) + WS mới → lãng phí bandwidth, watchdog timeout loop.
- WS cũ bị stuck không gửi được → buffer đầy → skip frame → watchdog keyframe timeout → close → re-add → vòng lặp.

### Giải nhân (đã chọn: đơn giản, chống xung đột)
- Lưu map ip -> ws cho cả video (_ip_to_ws) và audio (_ip_to_audio).
- Khi 1 IP connect mới (kể cả cùng IP khác port client) → trước khi add, gọi _kick_old_session_for_ip(ip, kind) → đóng WS cũ cùng IP với code 1000 'Replaced by new session (same IP)'.
- Map được update theo ws hiện tại trong finally: nếu ws đang đóng là ws cuối cùng của IP → pop khỏi map.
- Kick cả audio lẫn video độc lập (1 client chỉ mở video, client khác chỉ audio thì không ảnh hưởng).

### Files thay đổi (áp dụng đồng thời cho O L K P và production)
- release/server/server_H264wss.py + .exe
- release/server/server_H264wss_testK.py + .exe
- release/server/server_H264wss_testL.py + .exe
- release/server/server_H264wss_testO.py + .exe
- release/server/server_H264wss_testP.py + .exe
- release/server/server_H264wss_testO_new.py + .exe
- release/server/server_H264wss_testP_new.py + .exe

### Lưu ý
- Nếu thật sự cần 2 session cùng IP (vd: 2 tab browser), giải pháp này kick session cũ → tab cũ sẽ phải reconnect. Nếu sau này cần multi-session cùng IP, đổi sang giải pháp 'kèm session token' (client gửi session id, server group theo (ip, sid)).
- Kick code 1000 đóng WS sạch, không để lại zombie trong set.

## 2026-08-09: Luu � b?n build trong 
elease/server/dist/ (cu)

### V?n d?
- Folder 
elease/server/dist/ ch?a 19 file .exe build t? c�c l?n PyInstaller tru?c (bao g?m c? 	estA/B/C/D/F/G/H/I/J d� x�a script nhung qu�n x�a dist).
- C� th? g�y nh?m l?n khi test: ch?y nh?m b?n cu trong dist/ thay v� b?n m?i ? 
elease/server/ ? th?y l?i d� fix t? l�u v?n t�i di?n.

### Ph�n bi?t b?n cu vs m?i
- B?n trong 
elease/server/dist/: build cu hon, KH�NG c� keep-bright + KH�NG c� 1-IP-1-session.
- B?n trong 
elease/server/: build m?i nh?t, �� c� keep-bright + 1-IP-1-session.

### C�ch x�c d?nh nhanh khi test
- M? cmd, g� where server_H264wss_testP_new.exe ? n?u tr? v? 
elease\\server\\ l� b?n m?i, n?u tr? v? 
elease\\server\\dist\\ l� b?n cu.
- Ho?c check timestamp: b?n m?i build sau 12:14 PM 9/8/2026, b?n cu build tru?c th?i di?m d�.

### K? ho?ch d?n
- Sau khi test xong, x�a folder 
elease/server/dist/ v� 
elease/server/build/ (cache t?m).
- C?p nh?t build script d�ng --distpath release/server/ --workpath release/server/build/ d? PyInstaller kh�ng t? dump v�o dist/ n?a.


## 2026-08-09: Fix m�n den khi refresh viewer wgl/new (4 file)

### V?n d?
- M? iewer_H264wss_P_wgl.html (v� tuong t? _O_wgl, _O_new, _P_new) l?n d?u th?y h�nh b�nh thu?ng.
- F5 refresh tab trong khi server dang ch?y ? WS reconnect th�nh c�ng (WS + log, server [FPS] encode=35.5 send=35.5 OK) nhung **m�n h�nh den**, kh�ng hi?n th? frame n�o.
- Bug x?y ra ? c? b?n m?i (d� c� keep-bright + kick IP) v� b?n cu trong 
elease/server/dist/.

### Nguy�n nh�n
1. **ws.onopen KH�NG reset decoder state** � ch? g?i 
equestKeyframe(). Khi reconnect, ideoDecoder, decoderConfigured, decoderReady, cachedSPS, cachedPPS, 	sUs, _nalSlots, _avccOut, glCtx, glProgram c�n s�t t? session tru?c. Server g?i init JSON + frame d?u g?n nhau ? decoder state mismatch ? decode fail ? den.
2. **Race init/frame d?u**: Server g?i init JSON ? initDecoder() ? cleanupDecoder() x�a s?ch canvas. T?o ideoDecoder m?i nhung chua configure. Frame d?u d?n (c� th? l� delta kh�ng ph?i key) ? check if (!decoderMode) return; d� OK, nhung decoderConfigured=true (do session cu) + decoderReady=false (chua nh?n key m?i) ? v?n nh?n delta ? decoder cu reset ? den.
3. **cleanupDecoder() x�a s?ch to�n b? <canvas> trong container** (line container.querySelectorAll('canvas').forEach(c => c.remove())) � x�a lu�n canvas WebGL c?a renderer kh�c, g�y dangling reference, sau d� render m?i c� th? t?o canvas m?i nhung b? browser b? qua v� context cu d� m?t.
4. **Kh�ng c� watchdog frame stall** � N?u v� l� do g� decoder kh�ng nh?n keyframe trong 3s, kh�ng c� co ch? t? y�u c?u l?i keyframe ? den vinh vi?n cho t?i refresh ti?p theo.

### Gi?i ph�p s?a d?i (d� th?c hi?n)
- **Fix 1 � ws.onopen reset to�n b? decoder state**: th�m cleanupDecoder() + reset decoderConfigured, decoderReady, cachedSPS/PPS, 	sUs, decodedCount, decodeCount, _nalSlotCount, _avccOut, _lastRenderTs, glCtx, glProgram, glTexture, glVertexBuf.
- **Fix 2 � Drop guard ch? skip khi chua c� init ho?c d� config nhung chua nh?n key d?u**: th�m if (decoderConfigured && !decoderReady) { scan hasKey; if (!hasKey) return; } ngay sau if (!decoderMode) return;.
- **Fix 3 � Watchdog frame stall (3s kh�ng render ? request keyframe)**: th�m _lastRenderTs du?c set m?i l?n 
enderFrame/
enderFrameGL th�nh c�ng. setInterval 1s check: WS open + decoderReady + Date.now() - _lastRenderTs > 3000 ? g?i 
equestRemoteKeyframe() (c� throttle 1s) + log sendDebug('stall_watchdog', {since_ms}).
- **Fix 4 � cleanupDecoder() ch? x�a canvas c? th?** (luu ref t? l�c t?o), kh�ng querySelectorAll('canvas').forEach(remove) d? tr�nh x�a nh?m canvas c?a renderer kh�c.

### Files thay d?i
- web/viewer_H264wss_O_new.html (Fix 1, 2, 3)
- web/viewer_H264wss_O_wgl.html (Fix 1, 2, 3, 4)
- web/viewer_H264wss_P_new.html (Fix 1, 2, 3)
- web/viewer_H264wss_P_wgl.html (Fix 1, 2, 3, 4)
- Backup: *.bak_preRefresh ? c�ng folder web/.

### Verify
- M? _P_wgl.html ? th?y h�nh ? F5 refresh ? v?n th?y h�nh trong 1-2s.
- Stall test: m? viewer ? t?t server 5s ? b?t l?i ? check console c� log stall_watchdog + t? recover.
- M? 2 viewer _O_wgl.html + _P_wgl.html c�ng l�c ? c? 2 d?u th?y h�nh, refresh 1 c�i kh�ng ?nh hu?ng c�i kia.

### Luu �
- Viewer production iewer_H264wss.html KH�NG thu?c nh�m fix n�y (ch? 2D, kh�ng WebGL). N?u cung g?p den khi refresh ? �p d?ng Fix 1, 2, 3 sau.
- File viewer trong 
elease/server/dist/ l� b?n cu PyInstaller t? dump khi build l?n d?u, d� ch? ra trong changelog 2026-08-09 entry tru?c. Sau khi test xong s? x�a folder d�.


## 2026-08-09: So s�nh 7 file server (K/L/O/P/O_new/P_new/Production)

### B?ng so s�nh NVENC encoder

| | K | L | O | P | O_new | P_new | Production |
|---|---|---|---|---|---|---|---|---|
| **rc mode** | vbr | vbr | vbr | constqp | vbr | constqp | constqp |
| **cq/qp** | cq=14 | cq=14 | cq=16 | qp=16 | cq=16 | qp=16 | qp=22 |
| **aq-strength** | 8 | 8 | 4 | 8 | 4 | 8 | 6 |
| **rc-lookahead** | � | � | � | 0 | � | 0 | 12 |
| **qmin/qmax** | � | 16/28 | 16/28 | 16/28 | 16/28 | 16/28 | 20/40 |
| **preset** | p5 | p5 | p5 | p5 | p5 | p5 | p6 |
| **profile** | main | high444p | main | main | main | main | main |
| **pix_fmt** | yuv420p | yuv444p | yuv420p | yuv420p | yuv420p | yuv420p | yuv420p |
| **KEYINT** | 150 | 150 | 120 | 150 | 120 | 150 | 60 |
| **MAX_FPS** | 45 | 45 | 60 | 60 | 60 | 60 | 60 |
| **DITHER** | 1 | 1 | 0 | 1 | 0 | 1 | 1 |
| **dither impl** | cv2.add | np.clip | np.clip | np.clip | � | np.clip (encode loop) | cv2.add |
| **temporal-aq** | 1 | 0 | 0 | 0 | 0 | 0 | 0 |

### B?ng t�nh nang ki?n tr�c

| T�nh nang | K | L | O | P | O_new | P_new | Production |
|---|---|---|---|---|---|---|---|---|
| **keep-bright** | ? | ? | ? | ? | ? | ? | ? |
| **1-IP-1-session (kick)** | ? | ? | ? | ? | **?** | **?** | ? |
| **encode thread ri�ng** | ? | ? | ? | ? | ? | ? | ? |
| **frame.reformat(yuv420p)** | ? | ? | ? | ? | ? | ? | ? |
| **b? _encode_gop_count** | ? | ? | ? | ? | ? | ? | ? |

### Ph�t hi?n
- **O_new, P_new THI?U _ip_to_ws/_audio + _kick_old_session_for_ip** (1-IP-1-session) � c?n patch d? d?ng b? v?i K/L/O/P/Production.
- **O_new khai b�o treo** _bgr_pool (kh�ng d�ng), ES_AWAYMODE_REQUIRED (kh�ng d�ng).
- **P_new khai b�o treo** ES_AWAYMODE_REQUIRED (kh�ng d�ng).
- **Production** kh�c bi?t encoder so v?i m?i test (p6, qp=22, qmin=20, qmax=40, aq=6, lookahead=12, KEYINT=60) � kh�ng c�ng c?u h�nh v?i b?t k? b?n test n�o.
- **K, L, O, P** d?y d? keep-bright + kick IP, ch? thi?u encode thread ri�ng + reformat so v?i O_new/P_new.

### K? ho?ch
1. Patch O_new + P_new th�m _ip_to_ws/_audio + _kick_old_session_for_ip (rebuild 2 exe).
2. (T�y ch?n) Patch production + K/L/O/P th�m encode thread ri�ng + reformat.


## 2026-08-09: Fix mobile sleep/wake black screen (decoder corrupt)

### Van de
- Dien thoai vao che do nghi/lock man hinh -> browser tab bi suspend
- Sau khi unlock quay lai tab: WS reconnect OK, audio OK, nhung **video den**
- Server log cho thay `[WS] +` thanh cong va `send=55fps` (frame dang gui)
- FPS van cao nhung khong co hinh hien thi

### Gia thuyet (Hypothesis)
- Mobile OS suspend tab khi sleep -> WebCodecs VideoDecoder bi dong bang/corrupt state
- Khi wake up: WS connection van song (TCP keep-alive), server tiep tuc push frame
- Nhung decoder phia client o trang thai "configured" voi config cu, thuc te underlying decoder da corrupt
- Viewer nhan SPS/PPS nhung skip configure (vi `decoderConfigured=true`) -> frame IDR bi drop vi delta-only decoder khong the decode duoc
- Ket qua: server gui frame nhung client khong render -> black screen

### Giai phap sua doi
- Them `cleanupDecoder()` + reset state (`decoderConfigured=false`, `decoderReady=false`, `cachedSPS/PPS=null`) vao `visibilitychange` handler khi `document.hidden=false`
- Reset them `_nalSlotCount`, `_avccOut` (voi `_new files`) de clear buffer reuse
- Delay keyframe request 200ms (thay vi 100ms) de dam bao decoder da cleanup xong truoc khi nhan IDR
- Them `console.log('[VISIBILITY] Tab visible, resetting decoder')` de debug

### Files thay doi
- web/viewer_H264wss_O_wgl.html (visibilitychange handler ~line 1052)
- web/viewer_H264wss_O_new.html (visibilitychange handler ~line 994)
- web/viewer_H264wss_P_wgl.html (ap dung tuong tu)
- web/viewer_H264wss_P_new.html (ap dung tuong tu)

### Verify
- Test: mo `_O_wgl.html` tren mobile -> lock man hinh 10s -> unlock -> tab visible lai -> video phai hien thi trong 1-2s
- Check console log co `[VISIBILITY] Tab visible, resetting decoder` da chay
- Server log phai thay `[WS] +` (reconnect) hoac keyframe request sau khi visible

### Luu y
- Chua ap dung cho `viewer_H264wss.html` (production) � neu can them sau
- Mobile browser caching: trinh duyet co the cache HTML, nen test xong can clear cache de verify ban moi

## 2026-08-09: Fix mobile sleep/wake black screen (decoder corrupt)

### Van de
- Dien thoai vao che do nghi/lock man hinh -> browser tab bi suspend
- Sau khi unlock quay lai tab: WS reconnect OK, audio OK, nhung **video den**
- Server log cho thay `[WS] +` thanh cong va `send=55fps` (frame dang gui)
- FPS van cao nhung khong co hinh hien thi

### Gia thuyet (Hypothesis)
- Mobile OS suspend tab khi sleep -> WebCodecs VideoDecoder bi dong bang/corrupt state
- Khi wake up: WS connection van song (TCP keep-alive), server tiep tuc push frame
- Nhung decoder phia client o trang thai "configured" voi config cu, thuc te underlying decoder da corrupt
- Viewer nhan SPS/PPS nhung skip configure (vi `decoderConfigured=true`) -> frame IDR bi drop vi delta-only decoder khong the decode duoc
- Ket qua: server gui frame nhung client khong render -> black screen

### Giai phap sua doi
- Them `cleanupDecoder()` + reset state (`decoderConfigured=false`, `decoderReady=false`, `cachedSPS/PPS=null`) vao `visibilitychange` handler khi `document.hidden=false`
- Reset them `_nalSlotCount`, `_avccOut` (voi `_new files`) de clear buffer reuse
- Delay keyframe request 200ms (thay vi 100ms) de dam bao decoder da cleanup xong truoc khi nhan IDR
- Them `console.log('[VISIBILITY] Tab visible, resetting decoder')` de debug

### Files thay doi
- web/viewer_H264wss_O_wgl.html (visibilitychange handler ~line 1052)
- web/viewer_H264wss_O_new.html (visibilitychange handler ~line 994)
- web/viewer_H264wss_P_wgl.html (visibilitychange handler ~line 1053)
- web/viewer_H264wss_P_new.html (visibilitychange handler ~line 994)
- Rebuild: server_H264wss_testO_new.exe, server_H264wss_testP_new.exe (6:16-6:20 PM)

### Verify
- Test: mo `_O_wgl.html` tren mobile -> lock man hinh 10s -> unlock -> tab visible lai -> video phai hien thi trong 1-2s
- Check console log co `[VISIBILITY] Tab visible, resetting decoder` da chay
- Server log phai thay keyframe request sau khi visible

### Luu y
- Chua ap dung cho `viewer_H264wss.html` (production) � neu can them sau
- Mobile browser caching: trinh duyet co the cache HTML, nen test xong can clear cache de verify ban moi
- Wrapper exe (server_manager_*.exe) KHONG can rebuild � wrapper chi launch server exe, khong chua HTML

---
## 2026-08-09 (evening): Tong hop trang thai hien tai

### Da hoan thanh
1. **Fix 4 viewer HTML** (black screen khi refresh/ws.onopen): Them cleanupDecoder + watchdog + drop guard
2. **Fix mobile sleep/wake** (visibilitychange decoder corrupt): Them cleanupDecoder trong visibilitychange handler
3. **Build 4 server exe**: O, P, O_new, P_new (co HTML embedded)
4. **Build 7 wrapper exe**: production, K, L, O, P, O_new, P_new

### File trong release/server/ (chinh)
| File | Size | Build |
|------|------|-------|
| server_H264wss.exe | 91.9 MB | (cu, can rebuild) |
| server_H264wss_testK.exe | 91.9 MB | (cu, can rebuild) |
| server_H264wss_testL.exe | 91.9 MB | (cu, can rebuild) |
| server_H264wss_testO.exe | 96.3 MB | 5:01 PM |
| server_H264wss_testP.exe | 96.3 MB | 5:02 PM |
| server_H264wss_testO_new.exe | 96.3 MB | 6:20 PM |
| server_H264wss_testP_new.exe | 96.3 MB | 6:16 PM |
| server_manager.exe | 9.0 MB | 6:24 PM |
| server_manager_K.exe | 9.0 MB | 6:24 PM |
| server_manager_L.exe | 9.0 MB | 6:25 PM |
| server_manager_O.exe | 9.0 MB | 6:25 PM |
| server_manager_P.exe | 9.0 MB | 6:25 PM |
| server_manager_O_new.exe | 9.0 MB | 6:20 PM |
| server_manager_P_new.exe | 9.0 MB | 6:20 PM |

### Luu y
- O/P/O_new/P_new: da co fix black screen + mobile wake
- Production/K/L: chua co fix (dung viewer_H264wss.html cu)
- dist/: chua xoa (19 exe cu, khong dung)

## 2026-08-09 (đêm): Fix đen màn vĩnh viễn khi lock/wake — cleanupDecoder mà không tạo lại decoder

### Vấn đề
- Điện thoại khóa màn hình → vào lại: "Connected" nhưng **màn hình đen vĩnh viễn**, chỉ có âm thanh, F5 cũng đen.
- Xảy ra trên O_new (và cùng cơ chế ở O_wgl/P_new/P_wgl) dù trước đó đã có fix "cleanupDecoder khi visibilitychange".

### Nguyên nhân (phân tích code)
- Fix trước đó trong `visibilitychange` gọi `cleanupDecoder()` — hàm này **set `videoDecoder = null`** (viewer_H264wss_O_new.html ~dòng 500).
- NHƯNG sau đó **KHÔNG gọi `initDecoder()` để tạo decoder mới**.
- Khi lock/wake, WS **vẫn OPEN** (TCP keep-alive sống) → server **KHÔNG gửi init JSON lại** (init JSON chỉ gửi 1 lần khi WS mở) → `initDecoder` (nơi tạo `videoDecoder` mới) không bao giờ được gọi.
- Hệ quả: `videoDecoder = null` mãi → `decodeFrame`: `if (!videoDecoder) return;` → bỏ hết frame. `configureDecoder`: `if (!videoDecoder) return;` → không configure được.
- Audio vẫn chạy (audio WS riêng, không liên quan decoder video) → đúng triệu chứng "chỉ có âm thanh".
- F5 cũng đen: trình duyệt cache trang cũ, hoặc reload nhưng decoder state cũ corrupt.
- Chỉ có WS reconnect (server gửi init JSON mới) mới cứu được — nhưng WS thường không đóng khi lock/wake.

### Giải pháp sửa đổi (đã thực hiện)
- **4 viewer** (`viewer_H264wss_O_new.html`, `viewer_H264wss_O_wgl.html`, `viewer_H264wss_P_new.html`, `viewer_H264wss_P_wgl.html`): trong `visibilitychange`, sau `cleanupDecoder()` → **gọi `initDecoder(screenInfo.width, screenInfo.height)`** ngay (nếu đã có thông tin màn hình) để tạo `videoDecoder` mới, rồi mới `requestRemoteKeyframe` (delay 200ms).
- **Server O_new** (`server_H264wss_testO_new.py`): patch thêm **1-IP-1-session kick** (`_ip_to_ws`/`_ip_to_audio` + `_kick_old_session_for_ip`) cho đồng bộ với O/P — chống xung đột WS cũ khi reconnect cùng IP (tình huống lock/wake reconnect).
- **Rebuild** `server_H264wss_testO_new.exe` (viewer mới 87,331 bytes khớp trong exe).
- **Kill sạch** 2 instance server_manager_O.exe + 2 server_H264wss_testO.exe (bản O cũ đang chạy, không có fix) → khởi động `server_manager_O_new.exe` (giữ 3 port, HTTP 302 OK, viewer serve có fix).

### Files thay đổi
- `web/viewer_H264wss_O_new.html` + `.bak_lockfix` (bản gốc)
- `web/viewer_H264wss_O_wgl.html` + `.bak_lockfix`
- `web/viewer_H264wss_P_new.html` + `.bak_lockfix`
- `web/viewer_H264wss_P_wgl.html` + `.bak_lockfix`
- `release/server/server_H264wss_testO_new.py` + `.bak_lockfix`
- `release/server/server_H264wss_testO_new.exe` (rebuild)

### Lưu ý
- Exe O/P/K/L/production khác chưa rebuild với viewer fix — khi dùng đến cần rebuild (viewer gốc `viewer_H264wss.html` không bị bug này vì không cleanupDecoder trong visibilitychange, nhưng cũng chưa có fix decoder-corrupt đầy đủ).


## 2026-08-10 (rạng sáng): Xác nhận fix lock/wake hoạt động + fix race "frame gửi trước init JSON" (O_new & P_new)

### Vấn đề
1. Trước đây: khóa màn hình → vào lại → đen màn vĩnh viễn, chỉ có âm thanh.
2. Sau khi fix `cleanupDecoder()` → `initDecoder()` ở visibilitychange (entry trước): **vào/ra tab đã hoạt động ổn định** — decode lại màn hình bình thường (xác nhận thực tế từ user).
3. Nhưng **bấm F5 (refresh) thì không hiện hình**: log client có `[WS] onopen fired`, `[DBG-WS] binary type=1 len=... decoderMode=null vd=null` (frame video tới) nhưng **KHÔNG có `[DEC] initDecoder`** (init JSON chưa tới hoặc tới sau) → decoder chưa được tạo → bỏ hết frame. Phải vào/ra tab 2 lần mới hiện.

### Nguyên nhân (phân tích code)
- **Race trong server ws_handler** (cả O_new và P_new): `connected_clients.add(websocket)` xảy ra **TRƯỚC** khi gửi init JSON.
- Sau đó `await run_in_executor(_ensure_streaming)` **blocking 1-3s** (init camera + detect audio + init encoder NVENC).
- Trong lúc đó `stream_loop` đã thấy WS mới trong `connected_clients` → **bắt đầu gửi frame video (type=1) NGAY**, trước cả init JSON.
- Client nhận frame nhưng `decoderMode=null` (chưa nhận init) → bỏ hết frame ở `if (!decoderMode) return;`.
- Nếu `_ensure_streaming` chậm (detect audio device lâu), client nhận frame trước init càng lâu → có thể vượt `client_keyframe_wait_until` (8s) → watchdog đóng WS → reconnect → lặp → đen mãi.
- F5 đặc biệt dễ dính vì tạo WS hoàn toàn mới (server phải `_ensure_streaming` lại nếu stream đã stop); vào/ra tab thường WS vẫn sống + `visibilitychange` gọi `initDecoder` (fix trước) dùng `screenInfo` cũ → hiện ngay không cần init từ server.

### Giải pháp sửa đổi (đã thực hiện)
- **Server O_new + P_new** (`server_H264wss_testO_new.py`, `server_H264wss_testP_new.py`): chuyển `connected_clients.add(websocket)` xuống **SAU khi đã gửi xong init JSON** (+ header SPS/PPS). Giữ `client_needs_keyframe.add`, `_force_keyframe_next=True` từ đầu để encoder ép IDR sẵn. Như vậy `stream_loop` chỉ gửi frame cho WS sau khi client đã nhận init → decoder sẵn sàng.
- **Server P_new**: bổ sung **1-IP-1-session kick** (`_ip_to_ws`/`_ip_to_audio` + `_kick_old_session_for_ip`) cho đồng bộ với O_new/O/P — chống xung đột WS cũ khi reconnect cùng IP.
- **Rebuild** `server_H264wss_testO_new.exe` + `server_H264wss_testP_new.exe`.
- Viewer O_new tạm giữ log debug `[DBG-WS] binary type=...` (30 message đầu) để tiện xác minh lần test tới; sau khi ổn định sẽ gỡ.

### Trạng thái
- **Vào/ra tab: ĐÃ FIX (xác nhận) — dấu mốc quan trọng.**
- F5: đã sửa race server, cần user test lại lần cuối.
- P cũ (testP.exe, viewer `viewer_H264wss.html`) vẫn chưa rebuild với các fix này.

### Files thay đổi
- `release/server/server_H264wss_testO_new.py` + `.bak_lockfix`
- `release/server/server_H264wss_testP_new.py` + `.bak_lockfix`
- `release/server/server_H264wss_testO_new.exe` (rebuild)
- `release/server/server_H264wss_testP_new.exe` (rebuild)


## 2026-08-10 (rạng sáng, tiếp): Fix viewer P_new/P_wgl bị hỏng cú pháp JS — "Unexpected token ')'" / "Unexpected end of input"

### Vấn đề
- Chạy P_new trên điện thoại/PC báo lỗi console: `Uncaught SyntaxError: Unexpected end of input (at viewer_H264wss_P_new.html:2118:1)` và `Failed to get subsystem status ... UNSUPPORTED_OS`.
- P_new (và P_wgl) không bao giờ hiện hình dù server chạy tốt — khác hẳn O_new/O_wgl hoạt động bình thường.

### Nguyên nhân (phân tích)
- Dùng `node --check`/`vm.Script` kiểm tra cú pháp từng viewer:
  - `viewer_H264wss_O_new.html` → OK
  - `viewer_H264wss_O_wgl.html` → OK
  - `viewer_H264wss_P_new.html` → **ERR: Unexpected token ')'** (trước đó là "Unexpected end of input")
  - `viewer_H264wss_P_wgl.html` → **ERR: Unexpected token ')'**
- Kiểm tra backup `.bak_lockfix` (bản trước khi sửa) của P_new cũng lỗi → **lỗi có từ trước**, không phải do các fix lock/wake gần đây.
- Lỗi "Unexpected end of input" = có cấu trúc JS chưa đóng ở giữa file (ngoặc/backtick/template literal) làm parser nuốt tới hết file.
- Các lỗi phụ `GET /db/*.json 404`, `Failed to get subsystem status` là do extension trình duyệt (dịch CN-VN) gọi API không có — vô hại, không liên quan app.

### Giải pháp sửa đổi (đã thực hiện)
- Viewer P_new/P_wgl và O_new/O_wgl về bản chất GIỐNG HỆT nhau (config encoder nằm ở server, không có trong viewer — đã verify `findstr constqp/cq/qp` không match). Vì vậy tái tạo an toàn:
  - `viewer_H264wss_P_new.html` = copy `viewer_H264wss_O_new.html`, đổi tên file trong log `[INIT] viewer_H264wss_P_new.html`.
  - `viewer_H264wss_P_wgl.html` = copy `viewer_H264wss_O_wgl.html`, đổi tên file trong log `[INIT] viewer_H264wss_P_wgl.html`.
- Verify: cả 2 file sau tái tạo pass `vm.Script` (OK), serve từ server cũng OK (len 84,736 / 85,982).
- Rebuild `server_H264wss_testP_new.exe` (viewer mới 87,755 bytes trong exe).
- Lưu ý ghi đè: file release/web/viewer_H264wss_P_new.html lúc đầu ghi không đè được (len giữ nguyên 84,317) do file bị khoá — dùng `fs.writeFileSync(..., {flag:'w'})` + path tuyệt đối mới thành công.

### Trạng thái
- P_new đã build lại và khởi động `server_manager_P_new.exe` (giữ 3 port, serve viewer cú pháp OK). Cần user test F5 lại P_new.
- P_wgl chưa build exe (chỉ sửa viewer file) — build khi cần dùng.

### Files thay đổi
- `release/web/viewer_H264wss_P_new.html` (+ `.bak_lockfix` giữ bản cũ lỗi)
- `release/web/viewer_H264wss_P_wgl.html` (+ `.bak_lockfix`)
- `release/server/server_H264wss_testP_new.exe` (rebuild)


## 2026-08-10 (rạng sáng, tiếp): Fix P_new/P_wgl ReferenceError "_blockRemote is not defined"

### Vấn đề
- Sau khi rebuild P_new (entry trước đã fix SyntaxError "Unexpected token"), chạy P_new trên điện thoại báo console: `Uncaught ReferenceError: _blockRemote is not defined`.
- P_new không hiện hình, dù node --check cú pháp OK (khác hẳn lỗi SyntaxError trước đó).

### Nguyên nhân (phân tích code)
- `_blockRemote` được dùng 12 nơi trong cả 4 viewer (O_new/P_new/O_wgl/P_wgl) nhưng **KHÔNG có khai báo `let/var/const`** — chỉ là implicit global (gán `=` trực tiếp).
- Các biến gesture khác (`twoFingerActive`, `wasTwoFinger`, `scrollMode`, `scrollStarted`, `gestureActive`, `longPressFired`, `doubleTapSelecting`, `oneFingerDrag`) đều có khai báo `let` trong khối Touch events (~line 1379 _new / 1422 _wgl). Riêng `_blockRemote` bị thiếu.
- Lỗi đọc-trước-gán THẬT: trên lần tải trang mới, chạm 1 ngón kích hoạt `touchstart`/`pointerdown` (đọc `_blockRemote` tại line 961/976 _new, 1019/1034 _wgl) TRƯỚC khi bất kỳ phép gán `_blockRemote = false` nào chạy → đọc biến chưa tồn tại → ReferenceError.
- Kiểm tra backup `.bak_lockfix`/`.bak_preRefresh`: `_blockRemote` CHƯA BAO GIỜ được khai báo từ trước — đây là thiếu sót gốc (implicit global), không phải do tái tạo file làm mất khai báo. Lỗi chỉ bộc lộ rõ hơn khi các fix lock/wake tăng số điểm đọc trong nhánh touch.

### Giải pháp sửa đổi (đã thực hiện)
- Thêm `let _blockRemote = false;` vào đầu khối khai báo gesture state (trước `let wasTwoFinger`) cho cả 4 file:
  - web/viewer_H264wss_O_new.html (line 1380)
  - web/viewer_H264wss_P_new.html (line 1380)
  - web/viewer_H264wss_O_wgl.html (line 1423)
  - web/viewer_H264wss_P_wgl.html (line 1423)
- Verify bằng verifier agent: cả 4 file có khai báo `let _blockRemote = false;`, node --check PASS (không phá vỡ cú pháp), lifecycle gán true/false đầy đủ (1 lần =true ở 2-ngón, 7 lần =false ở khởi tạo/visibilitychange/blur/touchend/touchcancel).
- Rebuild: server_H264wss_testO_new.exe (12:24 AM), server_H264wss_testP_new.exe (12:25 AM).

### Trạng thái
- Đã đóng 2 instance server_manager_P_new.exe (đang giữ lock) trước khi build.
- Cần user test lại P_new trên điện thoại: mở `_P_new.html` → connect → không còn ReferenceError, hiện hình.

## 2026-08-10: Fix gesture — ngắt scroll khi giữ mousedown + chỉ tap sạch mới nhả nút

### Vấn đề
- Sau double-tap giữ (mousedown đang giữ, _mouseHeld = true), di chuyển ngón lúc giữ tay **bị ăn vào scroll** thay vì kéo (mouse_move).
- Khi đã vào mousedown, một gesture scroll tiếp theo **làm mousedown bị thoát ra** (gửi mouse_up) dù không phải là tap sạch.
- Yêu cầu: (1) khi giữ mousedown + kéo → drag (mouse_move), không scroll; (2) chỉ **1 tap sạch = 1 click** mới thay cho move-mouse + mouse_up tại vị trí mới; scroll/drag không được làm mousedown thoát ra.

### Nguyên nhân (phân tích code)
- Trong onTouchMove, nhánh lse if (scrollMode) chạy khi doubleTapSelecting đã hết (sau timeout 250ms _dtReleaseTimeout) nhưng _mouseHeld vẫn true → justEnteredScroll = !scrollMode && dist > 2 bật scrollMode = true → di chuyển ngón lúc giữ bị gửi mouse_scroll thay vì mouse_move.
- Trong onTouchEnd, nhánh _mouseHeld và nhánh doubleTapSelecting gửi mouse_up **vô điều kiện** (không kiểm tra isTap) → scroll/drag làm mousedown thoát ra.
- Bug cao (verifier): khi kéo >10px, clearLongPress() xoá _dtReleaseTimeout nhưng KHÔNG đặt doubleTapSelecting = false → doubleTapSelecting còn sống tới onTouchEnd, nhánh đó gửi mouse_up vô điều kiện, bỏ qua cổng isTap.

### Giải pháp sửa đổi (đã thực hiện)
Áp cho cả 4 viewer (O_new/P_new làm trước; O_wgl/P_wgl chưa áp) — logic giống nhau, chỉ khác dòng log tên viewer.

1. onTouchMove:
   - justEnteredScroll = !scrollMode && !_mouseHeld && dist > 2 → khi đang giữ mousedown thì KHÔNG vào scroll mode.
   - Nhánh gửi move đổi if (doubleTapSelecting) → if (doubleTapSelecting || _mouseHeld) → giữ + kéo luôn gửi mouse_move (drag), không scroll.
2. onTouchEnd:
   - Nhánh doubleTapSelecting: **gate trên isTap** — nếu tap sạch (isTap) → mouse_up + mouse_click (double-click) nếu còn trong cửa sổ _dtReleaseTimeout; nếu không (kéo/giữ lâu) → **GIỮ mousedown**, chỉ clear _dtReleaseTimeout + doubleTapSelecting.
   - Nhánh _mouseHeld: chỉ nhả (mouse_move + mouse_up tại vị trí mới, _mouseHeld = false) khi isTap true; nếu scroll/drag → giữ mousedown.

Hành vi sau fix (ma trận):
- Double-tap nhanh + thả nhanh → mouse_up + mouse_click (double-click). ✓
- Double-tap giữ rồi kéo → mouse_move (drag), không scroll. ✓
- Double-tap giữ rồi thả = drag (di chuyển nhiều) → giữ mousedown, không thoát. ✓
- Double-tap giữ rồi thả = tap sạch → mouse_move + mouse_up tại vị trí mới. ✓
- Scroll bình thường (không giữ) → scroll như cũ (isTap gate chỉ chặn khi _mouseHeld). ✓

### Trạng thái
- Đã áp đủ 3 thay đổi cho CẢ 4 viewer (O_new/P_new/O_wgl/P_wgl), node --check SYNTAX OK, verifier PASS (4/4 file nhất quán, không regression). Backup .bak_preTapScroll cho 4 file.
- Đã rebuild lại exe: `server_H264wss_testO_new.exe` (96,319,598 bytes) và `server_H264wss_testP_new.exe` (96,319,302 bytes) — build lúc 1:19 AM 2026-08-10, log xác nhận đã nhúng viewer mới (Building because viewer_...html changed).
- Cần user test lại trên điện thoại: double-tap giữ + kéo = drag (không scroll), thả tay = drag giữ mousedown, tap sạch mới nhả nút.

### Files thay đổi
- web/viewer_H264wss_O_new.html (+ .bak_preTapScroll)
- web/viewer_H264wss_P_new.html (+ .bak_preTapScroll)
- web/viewer_H264wss_O_wgl.html (+ .bak_preTapScroll)
- web/viewer_H264wss_P_wgl.html (+ .bak_preTapScroll)
- release/server/server_H264wss_testO_new.exe (rebuild)
- release/server/server_H264wss_testP_new.exe (rebuild)

## 2026-08-09: So sánh render viewer — Canvas 2D (bản gốc/_new) vs WebGL (bản _wgl)

### Vấn đề
- Cần làm rõ sự khác biệt giữa phía render "kia" và phía WebGL trong viewer.

### Giải thích
- **Bản gốc `viewer_H264wss.html`** và **bản `_new`**: dùng **Canvas 2D + `drawImage`** (CPU path).
  Luồng: WebCodecs `VideoDecoder` decode -> `VideoFrame` -> `ctx.drawImage(frame,0,0)` -> trình duyệt rasterize.
  `canvas.getContext('2d', { desynchronized: true })`. Đơn giản, tương thích cao, nhưng phải copy frame qua CPU.
- **Bản `_wgl`**: dùng **WebGL** (GPU path).
  Thêm `renderFrameGL()` + `_ensureGL()`: `canvas.getContext('webgl2'/'webgl')`, tạo vertex+fragment shader,
  upload `VideoFrame` trực tiếp lên texture bằng `glCtx.texImage2D(..., videoFrame)` (zero-copy nếu driver hỗ trợ),
  vẽ fullscreen quad bằng `TRIANGLE_STRIP`. Nếu WebGL không khả dụng -> rơi về `ctx.drawImage` (2D).

### Bảng so sánh
| | Bản gốc / `_new` | Bản `_wgl` |
|---|---|---|
| API | `CanvasRenderingContext2D` | `WebGLRenderingContext` (webgl2/webgl) |
| Render | `drawImage` (CPU copy) | `texImage2D` + shader (GPU upload) |
| Path | CPU | GPU (zero-copy nếu driver hỗ trợ) |
| Phức tạp | Đơn giản | Thêm shader + buffer |
| Fallback | - | rơi về 2D nếu WebGL không có |

### Ghi chú
- `_wgl` còn có tối ưu decode riêng (pre-alloc NAL slot, `_findStartCode` linear scan, AVCC buffer reuse,
  decode queue soft/hard limit) - không liên quan WebGL.
- Mục đích `_wgl`: giảm copy frame qua CPU khi render nhiều frame / fps cao.

## 2026-08-12: Fix server idle-exit killing active streams + WebSocket stall reconnect

### Vấn đề
Server bị ngắt kết nối khi client tạm thời không nhận dữ liệu (stall), và có thời gian thiếu 1 phút so với watchdog timeout.

### Nguyên nhân
- `IDLE_PROCESS_EXIT` = 300s, khi không có client kết nối WebSocket thì server tự động thoát. Tuy nhiên `_maybe_stop_streaming()` đã được gọi kể cả khi có client đang kết nối nhưng tạm thời không gửi dữ liệu, dẫn đến việc stream bị dừng đột ngột.
- Viewer stall watchdog (8s timeout) chưa có logic force-reconnect, chỉ có reconnect bình thường, dẫn đến thời gian thiếu khoảng 1 phút so với server idle exit (60s).

### Giải pháp sửa đổi
- Giảm `IDLE_PROCESS_EXIT` từ 300s xuống 60s (phù hợp với thời gian chờ của viewer).
- Bọc `_maybe_stop_streaming()` trong cờ `_maybe_stop_idle_exit` để chỉ ngăn việc gọi trùng lặp khi đang trong quá trình dừng stream.
- Viewer: tăng `STALL_RECONNECT_MS` lên 8000 và thêm force-reconnect logic ngay lập tức khi stall được phát hiện.

### Files changed
- Server (all variants): `server_H264wss*.py` — `IDLE_PROCESS_EXIT` 300→60s, guard `_maybe_stop_streaming`
- Viewer: `viewer_H264wss_P_new.html`, `viewer_H264wss_P_wgl.html`, `viewer_H264wss_O_new.html` — `STALL_RECONNECT_MS=8000`, force-reconnect trong stall watchdog

---

## 2026-08-12 (2): Fix send=0.0 — frames never delivered to new clients

### Vấn đề
Server encode ổn (encode=35-40 FPS) nhưng `send=0.0` — khung hình không bao giờ được gửi đến client WebSocket, màn hình viewer đen.

### Nguyên nhân
Trong `send_video_to_clients()`, khi `_buffer_backed_up(ws)` trả về `True` (client chưa kịp nhận dữ liệu), code thực hiện:
```python
client_last_video_id[ws] = vid  # FIX LINE — CẬP NHẬT last_vid TRƯỚC KHI skip
c = _buf_skip_count.get(ws, 0)
...
_buf_skip_count[ws] = c + 1
continue
```
Client **không nhận được frame** nhưng `client_last_video_id` **đã được cập nhật** = `vid`. Frame tiếp theo cùng `vid` (vì stream_loop chưa advance video_id kịp) bị skip qua `if vid == last_vid: continue`. Dẫn đến **mọi frame bị skip** — client mãi không nhận được dữ liệu, buffer kéo dài, server không bao giờ gửi.

### Giải pháp sửa đổi
**Xóa dòng `client_last_video_id[ws] = vid`** ở nhánh buffer-backed-up. Client phải giữ `last_vid` cũ (`-1` cho client mới) để frame tiếp theo được gửi lại khi buffer đã trống.

### Files changed
- All 7 server files (`server_H264wss*.py`) — xóa `client_last_video_id[ws] = vid` ở nhánh skip do buffer full
- Được sửa bởi: opencode/laguna-s-2.1-free

---

## 2026-08-12 (3): Fix send=0.0 — new clients permanently blocked from receiving P-frames

### Vấn đề
Server encode bình thường (encode=30-40 FPS) nhưng `send=0.0` cho client mới kết nối. Client connect WebSocket nhận init JSON + SPS/PPS rồi ngưng nhận mọi frame.

### Nguyên nhân
Trong `send_video_to_clients()`, dòng 1887:
```python
if ws in client_needs_keyframe and not is_key:
    continue
```
Client mới được đánh dấu `client_needs_keyframe` (line 1743), và điều này kéo dài **vô thời gian** vì:
- I-frame chỉ xuất hiện mỗi `keyint=150` frame (~4s ở 37fps)
- Khi I-frame cuối cùng arrives, nếu buffer full → timeout → không discard `client_needs_keyframe`
- Client bị stuck ở trạng thái chờ keyframe mãi mãi → mọi P-frame đều bị skip → `send=0.0`

### Giải pháp sửa đồi
Thay đổi điều kiện skip thành:
```python
if ws in client_needs_keyframe and not is_key and last_vid != -1:
    continue
```
Client **mới** (last_vid == -1, vừa kết nối, đã nhận SPS/PPS) sẽ nhận **ngay cả P-frame đầu tiên** — SPS/PPS đã được gửi ở init phase đủ để khởi tạo decoder. Chỉ client **cũ** (từng nhận dữ liệu rồi) mới bị gián đoạn khi cần keyframe thực sự.

### Files changed
- All 7 server files (`server_H264wss*.py`) — sửa điều kiện skip P-frame cho new client
- Được sửa bởi: opencode/laguna-s-2.1-free
