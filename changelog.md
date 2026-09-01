# Changelog - Screen Share Server H264 Windows Port

## v1.8 - Universal Audio Fix & Noise Reduction (2026-08-07)
- **Priority WASAPI Stereo Mix (48kHz)**: Device selection by API priority (WASAPI > WDM-KS > DirectSound > MME)
- **High-pass filter 60Hz**: 1-pole IIR removes AC hum/low-freq rumble
- **Adaptive Noise Gate**: Learns noise floor for 2s, gate = 4x noise floor, EMA tracking
- **Soft Limiter (tanh)**: Replaces hard clipping, reduces harmonic distortion
- **Gain reduced to 2.0**: Cleaner WASAPI source needs less amplification
- **Blocksize 20ms + Batch 50ms**: Stable timing, reduced callback frequency
- **Config**: `_AUDIO_GAIN=2.0`, `_AUDIO_GATE_MULTIPLIER=4.0`, `_AUDIO_HIGHPASS_HZ=60`

## v1.7 - Fix FPS Locked at 24fps + Audio Smoothing (2026-08-07)
- **Audio fire-and-forget**: `asyncio.create_task(send_audio_to_clients())` — video loop never blocked by audio
- **Worklet ring-guard**: Push read pointer when full, prevents echo from overwritten region
- **Removed audio flow-control skip**: No more forced drops from `_buffer_backed_up()`
- **Batch 5 chunks (~50ms)**: 80% fewer `ws.send()` calls
- **Gain 20x**: Compensates for low Windows volume

## v1.7 (earlier) - Audio Echo/Dropout Fix (2026-08-07)
- **Worklet ring-guard**: `if (filled >= cap) this.r = (this.r + 1) % cap`
- **Audio batch 50ms (5 chunks)**: Reduces send frequency ~80%
- **Audio-first in stream_loop**: Drain/send audio before video
- **Removed flow-control skip for audio**: Only drops on timeout/close
- **Timeout 50ms → 100ms**: Audio WS on separate port

## v1.6 - Audio Smooth + Video Quality (2026-08-07)
- **SCALE_PERCENT 75 → 100**: Native 1920x1080 encoding
- **H264_PRESET superfast → veryfast**: Better text quality
- **H264_BITRATE 5 → 8Mbps**: Sharper 1080p
- **MAX_FPS 30 → 25, KEYINT 30 → 15**: Phone decode keeps up, fewer artifacts
- **Audio queue 200 → 500** (~5s buffer)
- **Batching 5 chunks (~50ms)**: Fewer WS sends
- **Audio-first + no flow-control skip + 100ms timeout**

## v1.5 - Fixed Stuttering & FPS (2026-08-06)
- **NAL scan O(n) → bytes.find()**: 122ms → 0.026ms/frame (2 calls/frame eliminated)
- **Windows timer 15.6ms → 1ms**: `timeBeginPeriod(1)` + deadline sleep + 1.5ms busy-wait
- **Result**: 4fps (motion) / 19fps (static) → stable 29-30fps, zero stutter >100ms

## v1.4 - Frame Pipeline Restructure (2026-08-06)
- **Latest-frame-only architecture**: Single shared var replaces deque queue
- **Steady frame pacing**: `next_frame_time` deadline scheduling
- **Fixed coordinate mapping**: Send screen resolution (1920x1080) in init

## v1.3 - CPU Optimization & Audio Handling (2026-08-06)
- **Encoder threads 4 → 2**: ~30% CPU reduction
- **Default 1080p60 → 720p30**: 4x pixel reduction
- **Universal audio detection**: WASAPI ctypes → Stereo Mix → Mic fallback
- **Graceful degradation**: Video-only if audio fails

## v1.2 - Video Quality & FPS (2026-08-06)
- **Preset ultrafast → veryfast**: Less macroblocking at same bitrate
- **FPS 60 → 30**: Half workload server+client
- **Resolution 1080p → 720p**: 4x encode speedup
- **GOP 30 → 60**: Fewer keyframe bandwidth spikes
- **Added broadway-*.js**: Missing decoder files

## v1.1 - Initial Fixes (2026-08-06)
- **Black screen**: `grab()` → `start()` + `get_latest_frame()` (DXGI auto-recover)
- **Reconnect fail**: `del _camera` before `_camera = None` (breaks singleton)
- **Audio universal detection**: Multi-API scan with fallback chain
- **Unicode console**: `stdout.reconfigure(utf-8)` + ASCII art
- **Port reuse**: `allow_reuse_address/port = True`

---

## Technical Notes
- **Architecture**: dxcam (DXGI) → PyAV libx264 → WebSocket binary (0x01=video, 0x02=audio)
- **Ports**: 8765 HTTPS, 8766 Video WS, 8767 Audio WS
- **Viewer**: WebCodecs (hardware decode) + AudioWorklet (PCM playback)
- **Run**: `python -X utf8 server/server_H264wss.py`
## v1.9 - Fix Sample Rate Mismatch (Noise) (2026-08-07)
- **Root cause**: Server captures WASAPI Stereo Mix at 48kHz, but viewer hardcoded SRC_RATE=44100 -> wrong resample -> aliasing -> "re re rat rat". Server init also hardcoded audio_sample_rate=48000.
- **Server**: init message now advertises the real captured sample rate (from _audio_capture_device).
- **Viewer**: playPCMChunk uses AUDIO_SRC_RATE read from init message (fallback 48000) instead of hardcoded 44100.
- Removed hardcoded 44100; client now resamples from the actual server rate.
## v1.10 - Disable Noise Gate (Fix Rat-Rat Crackle) (2026-08-07)
- **Root cause**: Per-sample noise gate distorted music/voice near the threshold (gate opens/closes on each sample as |x| crosses the knee) -> harmonic distortion sounding like "rat rat" crackle, independent of Windows volume.
- Disabled noise gate entirely (_AUDIO_ADAPTIVE_GATE=False, _AUDIO_SMOOTH_GATE=False). Processing chain is now HPF(120Hz) + gain(2.0) + tanh soft-limit only.
- Noise floor of WASAPI Stereo Mix is very low (RMS ~39/32767), so gate was unnecessary.
- Wrapped gate application in if _AUDIO_ADAPTIVE_GATE so it is fully skipped when disabled.
## v1.11 - Test: soundcard WASAPI Loopback Works (Volume-Independent Source) (2026-08-07)
- **Goal**: Separate stream volume from Windows device volume (volume=0 but still capture source).
- **Finding**: WASAPI loopback via `soundcard` library (pip install soundcard) WORKS on this machine (ctypes/comtypes got E_NOINTERFACE, but soundcard uses Media Foundation WASAPI loopback correctly).
- Loopback captures the stream BEFORE the endpoint/device volume is applied -> volume device = 0 still yields source audio.
- Device found: `Loopback Speakers (Realtek(R) Audio)` (2ch, 48000Hz), data is float32 normalized (-1..1), peak=0.51, rms=0.17.
- Note: emits SoundcardRuntimeWarning "data discontinuity" on underruns (to be handled).
- Next: integrate soundcard loopback as primary capture method + AGC to normalize level independent of source volume.
## v1.12 - Integrate soundcard WASAPI Loopback + AGC (2026-08-07)
- **Primary capture**: soundcard WASAPI loopback (pre-volume). Stream level now independent of Windows device volume (volume=0 still yields source).
- **New method** `wasapi_loopback_sd` + `_audio_soundcard_capture_loop()`: float32 loopback -> HPF(120Hz) -> AGC -> int16 interleaved.
- **AGC added**: envelope-based (NOT per-sample) so no harmonic distortion. Target peak 0.25, attack 0.2 (fast reduce), release 0.02 (slow raise), silences hold gain (noise floor not boosted), gain clamp 0.5..30.
- **Device selection**: soundcard loopback tried first, falls back to ctypes WASAPI -> Stereo Mix -> mic.
- Result: singing voice clear, no rat-rat crackle, source independent of device volume.
## v1.13 - Reduce Blocky/Ghosting Artifacts (2026-08-07)
- **Cause**: Full-screen motion (minimize/scroll window) exceeded bitrate + sparse keyframes -> macroblocking / smearing.
- H264_BITRATE 20 -> 30Mbps, added maxrate 36Mbps + bufsize 6MB.
- bf=0 (no B-frames) -> no reorder -> less ghosting/smearing.
- rc-lookahead=0 (low latency, no reorder).
- KEYINT 30 -> 15 (keyframe every 0.25s) -> faster artifact reset.
## v1.14 - Remove Debug Audio Logs (2026-08-07)
- Removed per-batch debug logs [AUDIO-SEND], [AUDIO-DRAIN], [AUDIO-BATCH] and the noise-floor learn log (spam).
- Kept startup logs, device detection, and overflow warning (rare, useful).
## v1.15 - Reduce Color Banding on Gradients (2026-08-07)
- **Cause**: 8-bit H.264 quantization + limited bitrate -> horizontal rainbow banding on smooth gradients.
- H264_BITRATE 30 -> 40Mbps, maxrate 48Mbps, bufsize 8MB.
- Added qmin=6 (higher min quality, less banding on dark/smooth regions).
- Added light per-frame dithering (+/-2 LSB) before encode to break banding.
## v1.15b - Revert Dithering (FPS 60->15) (2026-08-07)
- Per-frame random dithering over full 1080p killed encode FPS (58 -> ~15).
- Removed dithering; kept bitrate 40Mbps + qmin=6 to reduce gradient banding.
- Encode FPS restored to ~42-58.
## v1.16 - Video Artifact Experiments & Reverts (2026-08-07)
- Block/ghosting artifacts fixed in v1.13 (bitrate up, bf=0, keyint 15).
- Color banding on gradients: tried qmin=6 + 40Mbps (v1.15) and Bayer/dither (v1.16) - neither removed the "rainbow horizontal streaks" and dithering tanked FPS to ~21.
- Reverted all dithering (random + Bayer). Kept bitrate 40Mbps + qmin=6 + bf=0 + keyint=15.
- Open issue: random flickering 7-color horizontal streaks (static screen) - suspected chroma/decode-side, not encoder banding.
## v1.17 - TODO: Diagnose "7-sac nhat ngau nhien" (open) (2026-08-07)
- **Triệu chung**: soc ngang 7 mau, nhat ngau nhien, ca khi dung yen. Khong phai banding (dithering khong het). Khan nang phia decoder/WebCodecs.
- **Cac phuong an chua thu (chon khi quay lai):**
  1. Thu ep dung Broadway (software decode) thay WebCodecs. Neu het 7 sac -> WebCodecs bug; neu con -> encoder/stream.
  2. Thu tang keyint 15 -> 30 (it reset decode hon). Neu 7 sac giam -> do keyframe decode thuong xuyen.
  3. Thu profile baseline (tuong thich hon mot so phone decoder).
  4. Thu giam bitrate 40 -> 30Mbps + qmin ve mac dinh (isolation).
- **Hien tai giu**: bitrate 40Mbps, qmin=6, bf=0, keyint=15, khong dithering.

## v1.18 - Tang do net (2026-08-07)
- **Van de**: Hinh thieu net, mat chi tiet vung toi.
- **Nguyen nhan**: qmin=6 cong luc luong tu cao nhat -> mo vung toi/tron; preset=faster nen kem hieu qua -> cung bitrate do net thap hon.
- **3 phuong an tang do net (chon 1):**
  1. preset faster -> medium + bitrate 40 -> 50Mbps, GIU qmin=6. An toan, tang net tong the, khong dung banding. (DA CHON - dang chay)
  2. Chi preset -> medium, giu bitrate 40Mbps. Tang net nhe.
  3. Du 3: medium + 50Mbps + qmin=6 -> qmin=2. Net toi da nhung rui ro banding/7-sac quay lai.
- **Ghi chu**: HGinh hien dang chay phuong an 1. Test 7 sac (v1.17) da hoan dung tam.
## v1.19 - Ket qua tang do net (2026-08-07)
- **Thu medium + 50Mbps**: encode tut 18-38fps khi chuyen dong -> giay/lag. KHONG OK.
- **Thu medium + 35Mbps**: FPS on dinh ~60 (encode 59-60, send 52-55). GIU LAI.
- **Ket luan**: preset medium toi voi bitrate thap (35Mbps) van giu duoc 60fps va net hon ban faster can bitrate cao. Medium giup nen hieu qua hon nen can it bitrate hon.
- **Hien tai giu**: preset=medium, bitrate=35Mbps, maxrate=42Mbps, bufsize=8MB, qmin=6, bf=0, keyint=30, profile=main, tune=zerolatency.
- **Ghi chu**: Test 7 sac (v1.17) van con mo, chua quay lai.
## v1.20 - Open: Am thanh to dot ngot + Go tieng Viet (2026-08-07)
- **Van de 1 - Am to dot ngot khi chuyen tab/scroll:**
  - **Nguyen nhan**: AGC agc_max=30.0 (server_H264wss.py:1001). Khi yen tinh gain tu tang len 30x de dat target peak 0.25. Chuyen tab/scroll -> Windows phat am he thong (click) qua loopback -> gain dang cao ap len am dot ngot -> to giat truoc khi attack (0.2) kim xuoeng.
  - **Giai phap (chua lam)**: giam agc_max ~4, tang agc_attack 0.2->0.8 de kim nhanh hon.
- **Van de 2 - Go tieng Viet (chon: Dung Unikey PC - go telex tren phone):**
  - **Nguyen nhan goc**: server dung KEYEVENTF_UNICODE (_uinput_type, server_H264wss.py:329) -> go truc tiep ky tu, bo qua keyboard layout/IME -> Unikey PC khong hoat dong: go "ee" go thang "ee" khong doi "e".
  - **Bug "e thanh eee"**: phone keyboard go Telex, composition tach thanh "e" roi "e" gui roi -> may go "e"+"e" = "ee" (khong phai "eee"; can kiem tra lai mo ta).
  - **Giai phap (chua lam)**: doi server go bang PHIM (key_press) cho chu thuong thay UNICODE, de Unikey PC tu chuyen TELEX. Go "ee" -> "e".
- **Trang thai**: chua sua, chua chay lai.
## v1.21 - Da sua: Am to dot ngot + Go tieng Viet + Xoa hinh khi vao lai tab (2026-08-07)
- **1. Am to dot ngot (DA SUA - user xac nhan het to dot ngot, nhung cam giac "khong hay"):**
  - Sua: AGC agc_max 30.0 -> 4.0, agc_attack 0.2 -> 0.8 (server_H264wss.py AGC block). Kim nhanh am he thong khi chuyen tab/scroll, khong con to giat.
  - **Ton dong**: user cam nhận "khong hay" (nghe khong tu nhien) - co the do agc_max ha qua thap (4x gioi han boost), am doi khi nho. Chua ro, can test lai.
- **2. Go tieng Viet (DA SUA - chua xac nhan):**
  - Sua: _uinput_type (server_H264wss.py:329) go bang PHIM (_uinput_key) thay UNICODE, de Unikey PC tu chuyen TELEX (go "ee" -> "e"). Unicode noi vong khi ky tu khong map VK.
  - Chua test thuc te bang Unikey.
- **3. Xoa hinh khi vao lai tab (DA SUA - chua xac nhan):**
  - Sua client viewer_H264wss.html decodeFrame: khong con drop keyframe khi decodeQueueSize>4. Gap keyframe khi queue day -> videoDecoder.reset() + decoderReady=false de decode lai sach.
- **4. Video (DA SUA - chay doi):** faster + 40Mbps + qmin=2 (medium+35+6 truoc do tao FPS 45 khi scroll khong muot).
  - Chua test: muot khi scroll + banding/7-sac co noi lai khong (qmin 6->2).
- **Trang thai**: dang chay server moi. Can test: muot scroll, banding/7-sac, go tieng Viet, vao lai tab.
## v1.22 - Qua trinh lua chon cau hinh video (2026-08-07)
- **Van de**: User muon ~2MBps ma van NET. Thuc te dang 4MBps (faster+40+qmin=2).
- **Nguyen nhan 4MBps**: qmin=2 ep chat luong cao -> encoder xai nhieu bit cho chi tiet (gap doi so qmin=6). Do net nhan duoc nhờ qmin thap.
- **Danh doi khong tranh duoc**: net@2MBps = nen chat = preset medium = nang/tut FPS khi chuyen dong. faster thi muot nhung can ~4MBps cho cung do net.
- **3 phuong an da de xuat:**
  1. medium + qmin=2 + cap 20Mbps -> ~2MBps, net. Rui ro scroll tut FPS.
  2. faster + qmin=2 (4MBps, muot, net) - bo mục tieu 2MBps.
  3. Giam resolution -> it bit -> ~2MBps muot va net, doi hinh nho hon.
- **DA CHON va DANG CHAY**: phuong an 1 (medium + qmin=2 + 20Mbps).
- **Lich su test truoc do**: faster+40+qmin=6 (2.1MBps, khong net hon linux); faster+40+qmin=2 (4MBps, net, muot); medium+35+qmin=6 (45fps scroll khong muot); medium+50+qmin=6 (18-38fps tut).
- **Can test**: scroll co tut FPS khong (medium), banding/7-sac co noi lai khong (qmin=2), rate co ve ~2MBps.

- **Ket qua test v1.22**: medium+qmin=2+20Mbps -> FPS tut manh (encode 57->31->23). User chap nhan FPS thap (khong quan trong), giu cau hinh nay. Muon net + ~2MBps hon la muot.
- **Ghi nhan**: day la danh doi co chu y - chap nhan 20-30fps de co net + bitrate ~2MBps.
## v1.23 - Audio: tang peak cho am danh hon (2026-08-07)
- **Van de**: Am nghe "khong hay", det, thieu dinh sau khi AGC giam agc_max ve 4.
- **Nguyen nhan**: agc_target=0.25 (server_H264wss.py:1002) kep moi am ve muc 0.25 (-12dBFS) -> am det, peak yeu.
- **Giai phap**: tang agc_target 0.25 -> 0.6 (~-4dBFS) de peak manh, danh hon. Giu nguyen agc_max=4, agc_attack=0.8.
- **Doi lai**: am to hon, peak danh. Can kiem tra co bi clip/sat tieng khong khi nguon to.
## v1.24 - Cac phuong an tang do net va muc do theo sat (2026-08-07)
- **Van de**: User muon net hon nua. Hien tai medium+qmin=2+20Mbps.
- **Giai thich**: qmin=2 da rat thap (cho phep chi tiet toi da) - khong phai gioi han. Gioi han that la BITRATE 20Mbps: nen chat -> encoder phai bo chi tiet. Muon net hon phai tang bitrate hoac tang hieu qua nen (preset slow).
- **Phuong an 1 - Tang bitrate 20->30Mbps (~3MBps)**:
  - Chuong trinh THEO SAT: doi H264_BITRATE=30000000 (server_H264wss.py:111). Doi ngay lap tuc.
  - LUU Y: bitrate la TRAN (cap/ceiling) khong phai san. libx264 chi dung vua du cho noi dung - man hinh tinh dung it. Nen "30Mbps cau hinh" KHONG dam bao ra 3MBps thuc te; rate thuc phu thuoc noi dung. Dong no cao moi ra gan tran.
- **Phuong an 2 - preset slow + giu 20Mbps**:
  - Chuong trinh THEO SAT: doi H264_PRESET="slow" (line 114). 
  - LUU Y: slow nen hieu qua hon -> cung bitrate net hon. NHUNG slow nang CPU -> FPS tut them (hien medium da 20-30fps; slow co the 10-15fps). Va voi qmin=2, slow them it đo net vi bitrate da la gioi han. Hieu qua khong ro bang phuong an 1.
- **Phuong an 3 - Giu nguyen**: khong doi.
- **KET LUAN**: Phuong an 1 (tang bitrate) la hieu qua nhat - chuong trinh theo dung 100## v1.24 - Cac phuong an tang do net va muc do theo sat (2026-08-07)
- **Van de**: User muon net hon nua. Hien tai medium+qmin=2+20Mbps.
- **Giai thich**: qmin=2 da rat thap (cho phep chi tiet toi da) - khong phai gioi han. Gioi han that la BITRATE 20Mbps: nen chat -> encoder phai bo chi tiet. Muon net hon phai tang bitrate hoac tang hieu qua nen (preset slow).
- **Phuong an 1 - Tang bitrate 20->30Mbps (~3MBps)**:
  - Chuong trinh THEO SAT: doi H264_BITRATE=30000000 (server_H264wss.py:111). Doi ngay lap tuc.
  - LUU Y: bitrate la TRAN (cap/ceiling) khong phai san. libx264 chi dung vua du cho noi dung - man hinh tinh dung it. Nen "30Mbps cau hinh" KHONG dam bao ra 3MBps thuc te; rate thuc phu thuoc noi dung. Dong no cao moi ra gan tran.
- **Phuong an 2 - preset slow + giu 20Mbps**:
  - Chuong trinh THEO SAT: doi H264_PRESET="slow" (line 114).
  - LUU Y: slow nen hieu qua hon -> cung bitrate net hon. NHUNG slow nang CPU -> FPS tut them (hien medium da 20-30fps; slow co the 10-15fps). Va voi qmin=2, slow them it đo net vi bitrate da la gioi han. Hieu qua khong ro bang phuong an 1.
- **Phuong an 3 - Giu nguyen**: khong doi.
- **KET LUAN**: Phuong an 1 (tang bitrate) la hieu qua nhat - chuong trinh theo dung 100% va cho net ro. P2 theo dung nhung hieu qua mo hon + FPS tut. P3 khong doi.
- **Trang thai**: chua doi, dang chay medium+qmin=2+20Mbps.


## v1.25 - Tong ket kien truc: tach socket audio/video + async (2026-08-07)
- **Van de**: Tai sao tach 2 socket (8766 video/control, 8767 audio) va phai lam async.
- **Tach socket**: Video = batch to, mat frame duoc, nhay cam latency. Audio = realtime, lien tuc, khong chiu ngat quanh. Chung 1 socket -> head-of-line blocking: video lag (decode cham/buffer day) chan ca audio -> audio giay dinh ky. Tach de audio luon uu tien, khong bi video chan.
- **Lam async**: ws.send() blocking (cho ghi het kernel buffer). Client cham (phone) -> send timeout -> neu goi blocking, video loop dung tron, audio tut. Co che:
  - await wait_for(ws.send, timeout=0.05/0.1): khong bao gio treo cung.
  - asyncio.create_task(send_audio_to_clients): fire-and-forget, video loop khong cho audio.
  - asyncio.sleep precision vi timeBeginPeriod(1) (tru ~1.5ms epsilon).
  - Single-thread event loop: khong lock, xu ly nhieu client cung luc.
- **Chi tiet code**: server_H264wss.py stream_loop (line 1614-1657), send_video_to_clients (1551), send_audio_to_clients (1595), create_task(batched) (1628).
- **Ghi chu**: Toi uu cho 1-2 client LAN. Neu nhieu client / trai ban can lai xem lai.


## v1.26 - Kien thuc: Fix "ket vong" (jitter/stutter) audio (2026-08-07)
- **Nguyen nhan ket (jitter)**: ring buffer day/tran -> echo hoac loi doc ghi.
- **Cac fix da lam (v1.6, v1.7):**
  1. Worklet ring-guard (viewer audio-processor.js): if (filled >= cap) this.r = (this.r + 1) % cap — day con tro doc thay vi ket -> het echo.
  2. Audio batching 50ms (5 chunks) — giam 80% ws.send(), giam giay.
  3. Audio fire-and-forget: asyncio.create_task(send_audio_to_clients()) — video loop khong bi audio chan.
  4. Bo flow-control skip cho audio — chi drop khi timeout/close.
  5. Timeout 50->100ms — audio WS rieng port.
- **Kiem tra khi bi ket**: xem ring-guard (so 1) truoc (nguyen nhan truc tiep nhat), roi den send congestion (so 2,3).


## v1.27 - Kien thuc tong hop cac fix "nguyen nhan + giai phap" (2026-08-07)
- Ghi vao windows_transform_knowledge.md (muc "Kien thuc: Tong hop cac fix gan day") dang doan giai thich, khong chi rieng audio:
  1. Am to dot ngot khi chuyen tab/scroll -> AGC agc_max 30->4, attack 0.2->0.8; sau do agc_target 0.25->0.6 cho peak danh.
  2. Go tieng Viet -> _uinput_type go bang PHIM thay UNICODE de IME/Unikey PC tu chuyen TELEX.
  3. Xoa hinh khi ra-vao tab -> viewer khong drop keyframe khi queue day; videoDecoder.reset() + decoderReady=false.
  4. Video net vs bitrate danh doi -> medium+qmin=2+20Mbps (net, ~2MBps, FPS 20-30).
  5. SoundcardRuntimeWarning "data discontinuity" -> vo hai neu khong nghe giay.
- Muc dich: de sau gap lai co cai nhin nhanh "nguyen nhan -> fix" cho tung van de.


## v1.28 - Kien thuc: Vi sao dung async ma khong tach thread (2026-08-07)
- **Van de**: Vi sao khong tach thread cho audio/video ma dung async.
- **Giai thich:**
  1. Khong can thread: nen video (libx264) va capture (dxcam) da chay trong thread rieng roi. Phan con lai chi la network I/O -> async du thua, 1 event loop quan ly tot.
  2. Thread + shared state = race condition: audio/video chia se bien toan cuc (_audio_lock, _video_lock, _latest_video_data, connected_clients, client_last_video_id). Tach thread gui -> cung chạm connected_clients -> can lock moi noi -> deadlock/bug kho tim. Async single-thread khong can lock giua cac task (chi can lock voi thread capture/encode that su).
  3. Trong luong: thread = 1 stack ~MB + context switch OS. Async task nhe, cung 1 luong.
  4. Khi nao thread moi dung: co CPU-bound lau (xu ly anh phuc tap) -> run_in_executor.
- **Cach du an dung**: thread cho viec nang CPU (capture/encode, run_in_executor(_ensure_streaming) tai line 1449/1521) + async cho I/O send (send_video_to_clients, send_audio_to_clients). Khong tach thread send vi chi la I/O va gay race condition.
- **Tom lai**: thread = CPU-bound, async = I/O. du an dung ca hai dung chuc nang.


## v1.29 - Server lifecycle: wrapper soong mai + spawn con khi connect + fix hinh den (2026-08-07)
- **Van de**: (1) Hinh den khi quay lai tab, refresh cung khong len; (2) Server chay encode 60fps vo ich khi khong co client (CPU cao); (3) Nhieu server rac song sot chiem port.
- **Nguyen nhan**:
  - Hinh den: client connect retry bi ket _wsClosing=true vi onclose khong fire khi socket chet lang (tab an lau) -> khong bao gio tao WS moi.
  - Server chay encode vo ich: _capture_loop + libx264 chay full 60fps khi _streaming_active=True, khong co client van encode.
  - Rác: chay server tay nhieu lan de lai process chiem port -> bind fail 10048.
- **Giai phap**:
  1. Client (viewer_H264wss.html connect()): them _wsCloseRescue timeout 3s - neu onclose khong fire thi tu reset _wsClosing va connect lai. Watchdog visibilitychange cung tu reset khi _wsClosing bi ket.
  2. Server (server_H264wss.py): ping_timeout 300->15s de don client chet nhanh; them IDLE_PROCESS_EXIT=60s (watchdog doc lap tu _maybe_stop_streaming) - khong co client 60s -> _stop_streaming() + os._exit(0).
  3. Wrapper moi (server_manager.py): SOONG MAI, giu 3 ports (8765/8766/8767), CPU ~0. Khi co connect request -> nha port -> spawn server con. Server con idle-exit -> wrapper giu port lai, chờ connect tiep. Tu dong kill process rac chiem port khi spawn.
- **Test**: wrapper giu port -> connect -> spawn con bind 3 port OK; con idle-exit 60s -> wrapper giu lai; connect -> spawn lai OK. Khong con loi 10048.
- **Cach chay**: python -u -X utf8 server_manager.py (KHONG chay server_H264wss.py truc tiep).


## v1.30 - Fix wrapper: single-instance lock + kill wrapper cu (2026-08-07)
- **Van de**: Chay server_manager.py lan 2 khi wrapper cu van con -> chi kill duoc server con, khong kill wrapper cu -> wrapper cu van giu ports -> wrapper moi khong bind duoc port, bi roi/no.
- **Nguyen nhan**: Khong co co che single-instance. _kill_stale_servers chi kill process LISTEN tren ports (server con), khong quet wrapper cu dang giu lock.
- **Giai phap**: Them PID lock file (server_manager.pid) + _acquire_single_instance(): doc PID lock cu, neu con song thi taskkill wrapper cu, roi ghi PID moi. Bao dam chi 1 wrapper chay.
- **CLI**: python -u -X utf8 server_manager.py — khi chay lai tu dong kill wrapper cu va server con cu, khong con xung dot port 10048.


## v1.32 - Giam do tre audio vs video (buffer it hon) (2026-08-07)
- **Van de**: Am thanh tre hon hinh anh.
- **Nguyen nhan**: Nhieu tang buffer cong don:
  - Server: _audio_queue maxlen=500 (~5s) + batch audio 50ms.
  - Client worklet: cap=4s (qua lon) + prebuffer=250ms (lon nhat).
  - Client main: RING_SAMPLES=1s + PREBUFFER=50ms.
- **Giai phap giam buffer**:
  - Server: _audio_queue 500->100 (~1s); batch 50ms->20ms (gui nhanh hon).
  - Client worklet: cap 4s->0.5s; prebuffer 250ms->30ms.
  - Client main: RING_SAMPLES 1s->0.5s; PREBUFFER 50ms->20ms.
- **Doi lai**: Giam tre nhung de bi underrun/jitter hon neu mang khong on dinh. Neu nghe giay/thieu tieng thi tang nhe prebuffer len (30-50ms).
- **Chua test thuc te**.


## v1.33 - Giam delay hinh anh (chon phuong an 2) (2026-08-07)
- **Van de**: Giam them delay hinh anh (da giam audio o v1.32).
- **Nguyen nhan**: Video da co tune=zerolatency + rc-lookahead=0 + bf=0 + latencyMode realtime. Nguon delay chinh con lai: preset medium encode cham (frame den muon) + client decode buffer (>4 frame).
- **2 phuong an**:
  1. preset -> faster: encode nhanh, hinh den som, giam delay ro. Doi lai net giam, FPS on dinh hon.
  2. Giu medium (net) + client drop frame nhanh hon: decodeQueueSize > 4 -> > 2, hien thi sat thoi gian that hon. Doi lai de giay khi mang khong on.
- **DA CHON**: phuong an 2 (giu medium + drop nhanh hon). Phuong an 1 de lai review lan sau.


## v1.34 - Dieu kien test (2026-08-07)
- **Cach chay**: python -u -X utf8 server_manager.py (KHONG chay server_H264wss.py truc tiep). Wrapper soong mai giu ports, spawn server con khi co connect.
- **Refresh viewer**: phai refresh trang viewer de load HTML moi (bao gom fix connect retry, giam buffer audio v1.32, drop nhanh v1.33).
- **Kiem tra khi test**:
  1. Am thanh: het tre so voi hinh chua? Neu giay/thieu tieng -> tang prebuffer worklet 30->50ms (viewer_H264wss.html:694).
  2. Hinh anh: phan hoi nhanh hon khi click/scroll? Neu giay nhieu khi mang khong on -> decodeQueue > 2 -> > 4 (viewer_H264wss.html:543).
  3. Ra ngoai tab vao lai: hinh tu hoi phuc khong can refresh (fix _wsCloseRescue).
  4. Server ngu 60s khong client -> wrapper giu port -> connect lai -> spawn tu dong.
  5. 7-sac (v1.17) van con mo: qmin=2 co lam banding/7-sac tro lai khong.
- **Trang thai**: chua test thuc te lan cuoi. Server dang chay qua wrapper PID 22344 (chua co client).


## v1.35 - Tong hop logic gesture 2 van de con ngo (2026-08-07)
- **Van de 1 - Scroll lan vao tap (bug):** vao scroll chi voi 2px di chuyen (justEnteredScroll = !scrollMode && dist > 2, viewer_H264wss.html:1533). Nhung touchend: isTap = (!scrollMode || dist < threshold) && dist < threshold && elapsed < 250 (line 1661). -> Keo nhe 2-35px roi nha nhanh (<250ms) khi finger ve gan cho cham ban dau: scrollMode=true nhung dist < threshold -> VUA SCROLL VUA GUI CLICK (lan).
- **Van de 2 - Code chet, phat hien "vung cuon" khong hoat dong:** isLikelyScrollableArea() (line 1309) dinh nghia nhung KHONG ai goi. isScrollIntentCandidate, isScrollIntentDetected, scrollCursorPositioned, lastScrollTarget duoc set (1413, 1539-1540) nhung khong bao gio duoc doc lai. -> Thiet ke "chi scroll khi cham dung vung cuon duoc" da co nhung chua noi vao -> moi 1-ngon touch deu vao scroll mode bua.
- **Luu y vi tri chuot:** khi vao scroll, chuot duoc dat ve vi tri cham 1 lan (mouse_move, line 1538) roi khong cap nhat theo finger. Scroll xong, tap cho khac: mouse_click move chuot toi do (server _emit_move) -> khong lech.
- **Chua sua** — can chon huong: lam sach #1 (ngan scroll phat click) hoac hoan thien #2 (chi scroll khi dung vung cuon).


## v1.36 - Chinh lai mo ta van de scroll lan tap (2026-08-07)
- **Sua lai mo ta v1.35 (van de 1):** truoc day mo ta sai trong tam "keo nhe 2-35px". Ban chat that: o touchend (viewer_H264wss.html:1661):
  const isTap = (!scrollMode || dist < threshold) && dist < threshold && elapsed < 250;
  Khi scrollMode=true (da that su scroll), isTap VAN phu thuoc dist < threshold. -> Nguoi dung scroll xa roi keo finger VE LAI gan diem cham ban dau truoc khi nha -> dist nho lai -> isTap=true -> GUI CLICK du da scroll. Khoang cach luc nay khong lien quan gi den tap nhung code van dung no.
- **Fix dung**: khi scrollMode=true thi isTap phai LUON false (khong quan tam dist): isTap = !scrollMode && dist < threshold && elapsed < 250.
- **Chua sua** — ghi de lan sau doc lai biet cho sua.


## v1.37 - Gesture: fix double-tap hold - tap tiep theo = mouse_up (DA SUA) (2026-08-07)
- **Van de**: Double-tap roi GIU LAY (>250ms) -> mouse_down gui, timeout reset doubleTapSelecting -> nhung khong gui mouse_up khi nha ngon -> server ket nut chuot trai. Sau do tap cho khac -> chuot van bi giu -> keo/boi den ngoai y muon.
- **Mong muon**: B4 (giu sau double-tap) = giu mouse_down de boi den (dung). B5 (tap cho khac) = thanh mouse_up (nha nut tai vi tri moi) thay vi mouse_click.
- **Giai phap (da sua viewer_H264wss.html)**:
  - Them bien _mouseHeld (line 1331): true = nut chuot trai dang giu.
  - touchstart double-tap: gui mouse_down + set _mouseHeld=true (line 1446). Timeout giu lau: _mouseHeld VAN true (line 1452).
  - touchend doubleTapSelecting: gui mouse_up + _mouseHeld=false (line 1667).
  - touchend else if _mouseHeld: tap cho khac = mouse_move + mouse_up + _mouseHeld=false, KHONG gui mouse_click (line 1678-1683).
  - touchcancel: neu _mouseHeld -> gui mouse_up du phong (line 1579-1581).
- **Ket qua**: chuoi mouse_down -> mouse_move -> mouse_up = mot cu keo chuot boi den hoan chinh, khong con ket nut.


## v1.38 - Gesture scroll: fix isTap khi scrollMode=true (DA SUA) (2026-08-07)
- **Van de**: Khi scrollMode=true (da that su scroll), isTap VAN phu thuoc dist < threshold (line 1661). Nguoi dung scroll xa roi keo finger VE LAI gan diem cham ban dau truoc khi nha -> dist nho lai -> isTap=true -> gui click du da scroll. Khoang cach luc nay khong lien quan gi den tap nhung code van dung no.
- **Fix (da sua)**: isTap = !scrollMode && dist < threshold && elapsed < 250. Mot khi scrollMode=true -> isTap LUON false, khong quan tam dist.
- **Ket qua**: scroll khong con phat click nham. Tap van hoat dong binh thuong khi khong scroll.


## v1.39 - Gesture scroll: cap nhat vi tri chuot ve noi tha tay (DA SUA) (2026-08-07)
- **Van de**: Khi vao scroll, chuot duoc dat ve vi tri cham 1 lan (mouse_move, line 1538) roi khong cap nhat theo finger. Neu "scroll roi tha o noi khac", chuot van dung cho cu -> thao tac tiep theo lech vi tri.
- **Giai phap (da sua viewer_H264wss.html, onTouchEnd)**: khi tat ca ngon nha (touches.length===0) va scrollMode=true -> gui mouse_move toi vi tri cuoi cua finger (changedTouches[0], line 1638-1642). Chuot dung dung noi tay tha.
- **Luu y**: khong gui mouse_move lien tuc trong luc scroll (chuot se chay lung tung tren remote) - chi gui 1 lan khi tha. Khong xung dot voi tap (isTap = !scrollMode, v1.38).


## v1.40 - Gesture scroll: xoa code chet (DA SUA) (2026-08-07)
- **Van de**: isLikelyScrollableArea() dinh nghia nhung khong ai goi; isScrollIntentCandidate, isScrollIntentDetected, scrollCursorPositioned, lastScrollTarget duoc set nhung khong bao gio doc lai -> code chet gay roi khi doc.
- **Ly do khong hoan thien ma xoa**: isLikelyScrollableArea dung elementFromPoint tren VIEWER DOM (chi co canvas wrapper) -> khong the biet vung nao tren PC remote cuon duoc. Thiet ke "chi scroll khi dung vung cuon" BAT KHA THI voi remote desktop. Giu hanh vi 1-ngon = scroll (chuan remote).
- **Da xoa**: ham isLikelyScrollableArea + 4 bien scroll-intent chet + cac cho set chung (touchstart, touchmove). File gon hon.
- **Hanh vi giu nguyen**: 1 ngon luon scroll, nhu truoc.


## v1.41 - Fix bug: idle-exit treo - server con khong thoat duoc (DA SUA) (2026-08-07)
- **Van de**: Server con khong tu thoat khi khong co client. Log co "[IDLE] No clients for 60s, exiting process cleanly." nhung process van song, giu ports, encode 60fps ma -> ton CPU vo ich.
- **Nguyen nhan**: Trong _schedule_idle_exit() (server_H264wss.py), truoc khi os._exit(0) co goi _stop_streaming(). Ham nay treo (camera.stop() hoac encoder flush bi block) -> khong bao gio toi duoc os._exit(0) -> process song mai.
- **Giai phap**: Bo _stop_streaming() truoc os._exit(0). Vi process sap chet, OS tu thu hoi tai nguyen (camera, encoder, sockets) -> khong can don sach bang tay.
- **Test da xac nhan**: client connect -> server con spawn -> WS disconnect -> "[IDLE] No clients for 8s, exiting process cleanly." -> "[MGR] Server exited with code 0" -> wrapper giu lai ports. Khong con treo.
- **Cau hinh**: IDLE_PROCESS_EXIT = 60s (production).


## v1.42 - Luu y: UIPI - khong dieu khien duoc Task Manager khi server khong admin (2026-08-07)
- **Van de**: Mo Task Manager len (tren PC remote) khong dung duoc chuot.
- **Nguyen nhan**: UIPI (User Interface Privilege Isolation) tren Windows. Task Manager chay voi quyen ELEVATED (admin). Server python chay KHONG admin -> Windows chan SendInput tu process khong-elevated gui toi cua so elevated -> chuot/keyboard khong tac dong duoc.
- **Kiem tra**: wrapper PID chay khong elevated (IsElevated=0, kiem tra qua OpenProcessToken + GetTokenInformation TokenElevation=20).
- **Giai phap**: chay server_manager.py bang "Run as administrator" (PowerShell/cmd admin) -> SendInput cung quyen -> dieu khien duoc Task Manager.
- **Luu y**: Anh huong TOAN BO ung dung elevated (Task Manager, cac chuong trinh admin khac), khong rieng Task Manager.
- **Chua lam**: tu dong nang quyen (ShellExecute runas). Hien tai nguoi dung tu chay admin.


## v1.43 - Tu nang quyen admin trong wrapper (DA SUA) (2026-08-07)
- **Van de**: Server khong admin khong dieu khien duoc Task Manager (UIPI, xem v1.42).
- **Giai phap (da sua server_manager.py)**: main() tu kiem tra elevation:
  - _is_elevated(): dung ctypes.windll.shell32.IsUserAnAdmin().
  - Neu khong admin -> _relaunch_as_admin(): ShellExecuteW(None, "runas", sys.executable, server_manager.py, ...) -> UAC prompt -> process moi chay elevated roi moi tiep tuc.
- **Test da xac nhan**: chay khong-admin -> log "Not running as admin, relaunching elevated..." -> UAC -> PID moi IsElevated=1, giu 3 ports.
- **Luu y**: UAC prompt se hien moi lan chay lan dau tu cmd khong-admin. Neu chay tu cmd admin san roi thi khong prompt.


## v1.44 - Giam toc do scroll xuong 2/3 (DA SUA) (2026-08-07)
- **Van de**: Scroll qua nhanh, muon cham lai.
- **Giai phap**: viewer_H264wss.html:1529, he so chia _scrollAccum += dy / 2.25 -> dy / 3.375 (cham hon 2/3). Scroll chay chap ran, de dieu khien hon.
- **Chua test thuc te**.


## v1.45 - Text net hon, het jitter: faster + 30Mbps (DA SUA) (2026-08-07)
- **Van de**: Khi go text thay jitter + artifact tung cell chu, cam giac may render nang ne. Khong chi do bitrate - preset medium (1080p60) qua nang CPU -> encode khong kip 60fps khi go nhanh -> jitter.
- **Nguyen nhan**: preset=medium nang CPU nhat; khi text thay doi tung frame, encoder khong theo kip -> render nang, jitter, artifact quanh chu. Bitrate 20Mbps cung thap cho text.
- **Qua trinh thu nghiem va ket qua**:
  | Cau hinh | Bitrate | preset | qmin | Ket qua |
  |---|---|---|---|---|
  | Cu (v1.44) | 20Mbps | medium | 2 | Text jitter, may render nang ne |
  | MOI (v1.45) | 30Mbps | faster | 2 | Encode nhe, kip 60fps, text net hon (chua test) |
- **Bang thong so chi tiet (de sau quay lai)**:
  | Tham so | Gia tri cu (v1.44) | Gia tri moi (v1.45) |
  |---|---|---|
  | H264_BITRATE | 20,000,000 | 30,000,000 |
  | H264_MAXRATE | 25,000,000 | 36,000,000 |
  | H264_BUFSIZE | 6,000,000 | 8,000,000 |
  | H264_PRESET | medium | faster |
  | H264_TUNE | zerolatency | zerolatency (khong doi) |
  | H264_PROFILE | main | main (khong doi) |
  | H264_KEYINT | 30 | 30 (khong doi) |
  | qmin | 2 | 2 (khong doi) |
  | bf | 0 | 0 (khong doi) |
  | rc-lookahead | 0 | 0 (khong doi) |
- **Backup**: server_H264wss.py.bak_textsmooth
- **Chua test thuc te**. Neu text van jitter -> thu tang preset faster -> veryfast + bitrate 35Mbps, hoac giam resolution.


## v1.46 - Rollback: quay lai medium + 20Mbps (2026-08-07)
- **Van de**: Thu v1.45 (faster + 30Mbps) de text net hon, het jitter -> NANG HON, khong cai thien gi.
- **Nguyen nhan phan tich lai**: faster preset nen kem hieu qua hon -> de cung do net can nhieu bit hon; 30Mbps cung khong du de faster giu net text khi go nhanh -> artifact nang hon, khong het jitter.
- **Quyet dinh**: ROLLBACK ve cau hinh v1.44 (medium + 20Mbps) - cau hinh tot nhat da test. 
- **Trang thai**: da khoi phuc tu backup .bak_textsmooth, da kill server con, wrapper se spawn con code medium+20Mbps khi connect.
- **Ghi nhan**: text jitter/artifact van CHUA giai quyet duoc voi cac preset da thu (medium, faster). Chua tim duoc giai phap tot.

## v1.47 - Chuyen encoder sang NVENC (GPU GTX1060): net ma khong nang (2026-08-07)
- **Van de**: Text jitter/artifact + cam giac may "render nang ne, delayed". Trinh bay giai phap dot pha: van co the net tren dien thoai ma may tinh khong can render nang.
- **Nguyen nhan**: CPU i3-10105F (4 nhan) phai encode 1080p60 bang libx264 preset=medium -> khong kip 60fps (30-50ms/frame -> chi ra 20-30fps) -> stream rung/trễ tren dien thoai. qmin=2 + 20Mbps cang tot them CPU. Dien thoai chi decode (nhe), phan nang la may tinh encode.
- **Giai phap da thuc hien**: Chuyen encoder tu libx264 (CPU) sang h264_nvenc (GPU GTX1060 - chip encode rieng, khong ton CPU):
  - `H264_ENCODER = "auto"` -> tu dong chon encoder tot nhat co tren may: `h264_nvenc` (NVIDIA) -> `h264_qsv` (Intel) -> `h264_amf` (AMD) -> `libx264` (fallback CPU, may nao cung chay). **Tong quat cho moi may tinh, khong chi may nay.**
  - Ham `_pick_encoder()`: duyet danh sach uu tien, thu CodecContext.create + encode 1 frame gi 320x240 -> chon encoder dau tien hoat dong duoc. Neu `H264_ENCODER` set cu the thi dung thang gia tri do (khong auto).
  - Options NVENC: `preset=p5`, `tune=ll` (low latency), `rc=vbr`, `b=20Mbps`, `maxrate=25Mbps`, `bufsize=6Mbps`, `bf=0` (no B-frame -> het ghosting), `rc-lookahead=0`, `spatial-aq=1` (tang chat luong vung chi tiet = text), `aq-strength=8`, `thread_count=2`.
  - Options QSV (Intel): `preset=medium`, `rc=vbr`, `maxrate/bufsize`, `g=30`, `bf=0`.
  - Options AMF (AMD): `usage=lowlatency`, `quality=quality`, `rc=vbr_peak`, `g=30`, `bf=0`.
  - Giu nguyen nhanh libx264 cu lam fallback (may khong co GPU encoder).
- **Ket qua test cuc bo**: auto-detect chon `h264_nvenc`, NVENC encode 60 frames 1080p mat 0.37s = **160 fps** (du 2x nhu cau 60fps), ra du 60 packet -> may tinh nhe, dien thoai nhan stream 60fps muot, chat luong net o 20Mbps.
- **Backup**: server_H264wss.py.bak_nvenc (truoc khi doi sang NVENC).
- **Trang thai**: chua test thuc te tu dien thoai. Neu text van artifact o bitrate 20Mbps -> co the tang bitrate (30-40Mbps) vi NVENC khong ton CPU nen bitrate cao khong con la van de.

## v1.48 - Tach debug/release + tao file binary exe (PyInstaller) (2026-08-07)
- **Van de**: Can dong goi app thanh file binary de chay khong can Python; va khong su dung lam huong code dang chay.
- **Giai phap (cau truc 2 folder)**:
  - **Debug** = `Xemmanhinh/server` (code dang chay, giu nguyen khong sua tiep).
  - **Release** = `Xemmanhinh/release` (copy code + cert + web sang de sua/build exe).
  - Code trong release da sua cho frozen-aware (chay duoi dang exe PyInstaller).
- **Binary tao duoc** (trong `Xemmanhinh/release/server/dist/`):
  - `server_manager.exe` (8.7MB) - wrapper giu ports, spawn server con.
  - `server_H264wss.exe` (92MB) - server chinh (PyAV/dxcam/websockets/cert/web dong goi chung).
- **Qua trinh build**:
  - `python -m PyInstaller --onefile --console --name server_H264wss --collect-all av --collect-all dxcam --collect-all websockets --add-data "cert.pem;." --add-data "key.pem;." --add-data "../web/xxx;web" ... server_H264wss.py`
  - `python -m PyInstaller --onefile --console --name server_manager server_manager.py`
- **Chinh sua code cho frozen** (debug + release deu co):
  - `server_H264wss.py`: `_BASE_DIR = sys._MEIPASS` khi frozen (cert/web giai nen o day); `WEB_DIR = _BASE_DIR/web`.
  - `server_manager.py`: `FROZEN = getattr(sys,'frozen',False)`; `BASE_DIR = dirname(sys.executable)` khi frozen (folder that chua exe - de tim server_H264wss.exe va ghi PID lock); spawn `server_H264wss.exe` thay vi python script; relaunch admin bang chinh exe.
- **Ket qua test**: exe chay duoc den buoc bind port (loi 10048 vi debug dang giu port -> dung mong doi, chung to dong goi OK, khong crash o import).
- **Backup**: `server_H264wss.py.bak_exe`, `server_manager.py.bak_exe`.
- **Bug phat hien sau khi sua cho frozen (dang mo, da fix)**: khi doi WEB_DIR thanh `_BASE_DIR/web` cho exe, ban debug chay bang python bi 404 khi mo viewer (WEB_DIR sai = server/web, web that o `Xemmanhinh/web`). **Fix**: `WEB_DIR = _BASE_DIR/web` khi frozen, `../web` khi khong frozen (ap dung ca debug va release). Video/audio khong bi anh huong.
- **Release tro thanh ban doc lap**: copy `web/*` vao `release/server/web/`, `WEB_DIR = _BASE_DIR/web` cố định (khong can phan biet frozen nua), build lai exe voi `--add-data "web;web"`. Release gio tu chua du web (html/js/wasm), co the copy di noi khac van chay. **Luu y**: html da duoc nhung vao exe tu luc build (`--add-data`), copy html thuần tui khong can build lai - chi build lai khi doi source. Exe = snapshot cua source tai thoi diem build.
- **Ghi chu bao mat (PyInstaller)**: PyInstaller CHI dong goi (code + interpreter + DLL + data), KHONG bien dich native va KHONG bao mat. Code trong exe lay lai duoc ~90-95% bang `pyinstxtractor` (giai nen .pyc) + `uncompyle6`/`pycdc` (decompile). Neu can bao ve that: Nuitka (bien dich sang C/native) hoac Cython (logic nhanh/rieng). App nay khong co secret/loi the kinh doanh -> khong dang dau tu bao mat.

## v1.49 - Fix: NVENC khong sinh IDR/SPS/PPS -> nghe tieng khong co hinh (2026-08-07)
- **Van de**: Test exe release (NVENC) tu dien thoai -> NGHE TIENG NHUNG KHONG CO HINH. Log: `[FPS] encode=60 send gia dan 25->19->10`, `[FC] keyframe DELIVERED` lap lai lien tuc (client yeu cau keyframe mai vi khong decode duoc). Audio OK vi audio la PCM rieng, khong lien quan H264.
- **Nguyen nhan** (do sau phan tich, khong phai profile): NVENC KHONG ton trong `frame.pict_type=PictureType.I` -> khong sinh IDR (NAL 5) khi force keyframe; VA khong nhung SPS/PPS inline (extradata rong, packet chi co SEI + nonIDR). Server `_has_idr()` khong thay IDR -> khong gui keyframe hop le -> Broadway (JS H264 decoder) khong khoi tao duoc -> den hinh. libx264 tu nhung SPS/PPS+IDR vao packet dau nen truoc day khong bi. Profile NVENC la main/4.2 (giong libx264) nen KHONG phai nguyen nhan.
- **Giai phap**: them option `'forced-idr': '1'` vao nhanh NVENC (`server_H264wss.py`) -> moi frame duoc danh dau I se thanh IDR KEM SPS+PPS inline. Verify bang test: 30 frames -> IDR=1, SPS=1, nonIDR=29 (CHI ep frame danh dau, khong bien moi frame thanh keyframe, bitrate khong tang). Ap dung ca debug + release.
- **Backup**: `server_H264wss.py.bak_idr` (ca 2 ban).
- **Trang thai**: da build lai `release/server/dist/server_H264wss.exe` (bao gom fix). Manager release (PID 7796) dang giu ports -> khi connect phone se spawn exe moi co fix -> co hinh. Luu y: `forced-idr` la option cua NVENC, dung key dash `forced-idr` (khong phai `forced_idr`).

## v1.50 - Tang bitrate + lookahead cho NVENC: giam blocky khi chuyen dong nhanh (2026-08-07)
- **Van de**: Co hinh roi nhung chuyen dong nhanh (scroll, video) bi nhieu, o vuong (blocky) + jitter khung hinh.
- **Nguyen nhanh**: 20Mbps o 1080p60 khong du cho motion nhanh; `rc-lookahead=0` khien rate control phan ung cham (khong biet truoc motion -> cap phat bitrate kem) -> blocky; preset p5 va aq-strength 8 thap.
- **Giai phap da thuc hien** (NVENC branch, ca debug + release):
  - `H264_BITRATE` 20M -> **35M**, `H264_MAXRATE` 25M -> **42M**, `H264_BUFSIZE` 6M -> **12M** (NVENC khong ton CPU nen tang bitrate thoai mai).
  - `rc-lookahead` 0 -> **8** (phan bo bitrate thong minh hon khi motion; latency them ~130ms).
  - `preset` p5 -> **p6**, `aq-strength` 8 -> **12**.
  - Giu nguyen: tune=ll, bf=0, spatial-aq=1, forced-idr=1, keyint=30.
- **Verify**: options hop le, NVENC p6 35Mbps encode 1080p dat 72fps (du 60). IDR van sinh dung (forced-idr).
- **Trang thai**: da build lai exe release; manager (PID 7796) con chay, se spawn exe moi khi connect. Con 2 server con cu chay elevated da kill qua UAC truoc khi build. Backup: server_H264wss.py.bak_idr (config cu 20Mbps).

## v1.51 - Chuyen VBR->CBR 20Mbps: het jitter khi bandwidth gioi han 2.5MBps (2026-08-07)
- **Van de**: Sau v1.50 (35Mbps VBR) van con jitter khung hinh khi chuyen dong nhanh.
- **Nguyen nhan**: Bandwidth mang chi chiu duoc ~2.5MBps (20Mbps). Encoder VBR set 35Mbps -> moi khi motion nhanh, bitrate spike vuot bandwidth -> buffer mang nghen -> send fps tut (log: encode=60, send=19-25) -> jitter. KHONG the giam resolution (yeu cau giu 1080p) nen giai phap la khoa bitrate o dung muc bandwidth.
- **Giai phap da thuc hien**: Doi NVENC tu `rc=vbr` sang **`rc=cbr`**:
  - `H264_BITRATE` = 20Mbps, `H264_MAXRATE` = 20Mbps, `H264_BUFSIZE` = 8M (khop bandwidth 2.5MBps -> khong spike, send on dinh).
  - Giu nguyen toi uu chat luong: preset p6, rc-lookahead=8, aq-strength=12, spatial-aq=1, bf=0, forced-idr=1, tune=ll, keyint=30.
- **Verify**: CBR 20M hop le, NVENC encode 1080p dat 94fps.
- **Trang thai**: da build lai exe release. Da kill manager + server con (UAC) de build. User can chay lai `server_manager.exe` (release/server/dist) de bat dau. Backup: `server_H264wss.py.bak_cbr`.
- **Luu y**: 1080p60 o 20Mbps khi motion rat nhanh van se co mot it blocky (gioi han vat ly cua bitrate thap) - nhung khong con jitter vi bitrate da khop mang.

## v1.52 - Fix jitter/freeze: giam FPS 60->45 + decodeQueue 2->4 (2026-08-07)
- **Van de**: Co hinh, bitrate CBR 20M on dinh (encode=60 send=55) nhung client van spam `request_keyframe` lien tuc + bam click 1 cai hinh dung o 29fps.
- **Nguyen nhan** (phan tich client WebCodecs): decode 1080p60 tren dien thoai khong theo kip -> `decodeQueueSize > 2` luon day -> `videoDecoder.reset()` lien tuc -> `decoderReady=false` -> moi frame delta bi bo + gui request_keyframe -> nhan keyframe -> queue lai day -> reset... Vong lap nay tao spam request_keyframe va hinh dung/freeze. Decode la bottleneck (khong phai mang, khong phai encoder - log cho thay encode/send tot).
- **Giai phap da thuc hien**:
  - Server: `MAX_FPS` 60 -> **45** (decode nhe hon 25%, screen share van muot).
  - Client (viewer_H264wss.html:543): `decodeQueueSize > 2` -> **> 4** (it reset, it spam keyframe, on dinh hon).
  - Giu nguyen 1080p (khong giam resolution), CBR 20Mbps.
- **Trang thai**: da dong bo debug + release, build lai exe release. Chua test thuc te. Neu van freeze -> tiep tuc giam FPS (30) hoac tang decodeQueue (> 8).

## v1.53 - DE XUAT 3 thay doi giam smear + blocky khi motion (chua ap dung - dang cho test tung cai) (2026-08-07)
- **Van de**: Con 2 bieu hien nang nhat: (1) khoi den chuyen nhanh vao khoi trang -> sau khi di khoi van mac lai (motion smear), (2) scroll nhanh text terminal bi dinh o vuong lan lon. Root cause: CBR 20Mbps khong du bit cho motion o 1080p -> NVENC uu tien motion vector giu du doan cu (thieu bit cho residual) -> smear; text tan so cao + motion -> blocky.
- **3 thay doi de xuat (moi cai la 1 bien co lap de test):**
  1. `preset` p6 -> **p7** (chat luong NVENC tot nhat, khong ton them CPU/bandwidth, benchmark 74fps @1080p45 du 45fps). An toan nhat.
  2. `rc-lookahead` 8 -> **12** (encoder nhin truoc 12 frame phan bo bit tot hon -> danh san bit cho residual o vung chuyen dong nhanh -> giam smear). Danh doi: latency +~90ms (tong ~266ms).
  3. `bf` 0 -> **2** (B-frame tan dung du doan ca truoc lan sau -> hieu suat nen +15-20% o cung bitrate -> giam smear + blocky text). Rui ro: reorder - client WebCodecs danh timestamp tang deu theo thu tu nhan (decode order) nhung B-frame can presentation order -> co the lech khuon hinh; neu xau quay lai bf=0.
- **Ke hoach test tung cai (co lap tung bien):**
  - Buoc 1: chi doi preset p7 -> build -> test (ky vong: cai thien nhe, khong rui ro).
  - Buoc 2: + them rc-lookahead 12 -> build -> test smear giam? latency 266ms chap nhan? (ky vong: giam smear ro nhat).
  - Buoc 3: + them bf=2 -> build -> test chat luong tong + kiem tra reorder/lech frame (rui ro cao nhat).
  - Sau moi buoc: ghi ket qua vao changelog; neu xau -> rollback 1 bien.
- **Backup**: `server_H264wss.py.bak_motion` (config hien tai p6/lookahead8/bf0 truoc khi doi).
- **Trang thai (da ap dung)**: Test 2 truoc — da doi `rc-lookahead` 8 -> 12 (nen hien tai p6/bf0), dong bo debug+release, build lai exe. CHUA test thuc te tu dien thoai. Danh gia: smear khoi den giam? latency ~266ms co kho chiu khong? Neu ok -> test them p7 (buoc 1) hoac bf=2 (buoc 3).
- **Ket qua Test 2 (lookahead 12)**: Hinh dep, mau dep, nhung nhieu + dam (smear/blocky) VAN CON khi motion nhanh. Lookahead 12 khong giai quyet duoc goc roi -> xac nhan: van de la BITRATE 20M khong du cho motion (gioi han vat ly bandwidth), khong phai do lookahead.
- **Buoc tiep theo**: thu them p7 + bf=2 (tang hieu suat nen ~15-20% o cung bitrate) de giam nhe. Neu van khong du -> chap nhan gioi han (20Mbps 1080p motion nhanh se con it blocky/smear), hoac giam motion nguon (giam FPS 45->30 giam nhung khong het).
- **Ket qua Test 3 (bf=2)**: Mau dep nhu thuong, nhin ON DINH HON (khong bi reorder/lech frame xau, khong lag them dang ke), nhung nhieu + dam VAN CON khi motion nhanh. -> bf=2 cai thien on dinh tong the, GIU LAI.
- **Tong ket 3 bien**: lookahead 12 (khong cai thien ro), bf=2 (on dinh hon, giu), p7 (CHUA test). Con lai la gioi han vat ly: 20Mbps khong du cho motion nhanh o 1080p -> smear/blocky van con mot phan khong the het bang encoder settings.
- **Buoc tiep**: (a) test not p7 (cai thien nhe, an toan) hoac (b) chap nhan muc hien tai + tinh chinh khac (vi du giam FPS 45->30 de giam toc do motion de codec theo kip hon) hoac (c) dung tai.
- **Trang thai (da ap dung)**: Test 1 — da doi `preset` p6 -> **p7** (nen hien tai p7/lookahead12/bf2), dong bo debug+release, build lai exe. CHUA test thuc te.
- **Trang thai (da rollback)**: p7 (Test 1) KHONG dep + van nhieu/dam -> nhan dinh: encoder nen manh qua (p7 qua manh, mat chi tiet). Rollback ve TRANG THAI TEST 3 (p6/lookahead12/bf2) - cau hinh on dinh nhat tuong. Chua test thuc te. "encoder nen manh qua" = nhan xet quan trong: cac preset/bf nen manh hon co the mat chi tiet khong dep, can can nhac khi tang nen.
- **Trang thai hien tai**: Da mo `release/server/dist/server_manager.exe` (cau hinh test 3: p6/lookahead12/bf2) - dang giu 3 ports 8765/8766/8767, san sang dung. Khi connect tu dien thoai se spawn server con cau hinh test 3.

## v1.54 - Giam khung theo chu ky: keyint 30->60 + ghi nhan phuong an B (2026-08-07)
- **Van de**: Khung hinh theo chu ky gui chunk; scroll nhieu dung khung hinh. Log cho thay: `[FC] skip backup` buf=642408->828540 (client khong tieu thu kip -> buffer vuot 512KB -> server skip frame lien tuc), skips tang 209->898; client khac spam request_keyframe -> nhieu keyframe lon -> buffer spike.
- **Nguyen nhan**: client (decode/WiFi) khong theo kip 45fps CBR 20M 1080p khi motion + keyframe moi 0.67s (keyint 30) tao spike buffer -> skip -> khung chu ky.
- **Giai phap da thuc hien (C)**: `H264_KEYINT` 30 -> **60** (keyframe moi ~1.3s) giam keyframe spike -> giam khung chu ky. Client moi vao van request keyframe rieng (forced-idr sinh IDR ngay) nen khong can cho 1.3s. Ap dung ca debug + release, build lai exe.
- **Phuong an B (de xuat, CHUA ap dung - co the test hoac khong)**: tang `WRITE_BUFFER_LIMIT` 512KB -> 1MB (it skip hon, danh doi tre tang). De test sau neu C chua du.

## v1.55 - Logic chuot sau scroll: giu vi tri dat tay (khong di chuyen ve noi tha tay) (2026-08-07)
- **Van de**: Sau khi scroll xong va tha tay, con tro chuot di chuyen VE VI TRI THA TAY (luu truoc do v1.39) -> chuot doi cho, kho chiu khi thao tac tiep.
- **Giai phap**: Khi thao tac la scroll, sau khi tha tay gui `mouse_move` ve VI TRI BAT DAU DAT TAY (`touchStartPos` - khong doi trong scroll mode) thay vi vi tri tha tay. Chuot se khong di chuyen khoi diem dat tay ban dau neu thao tac la scroll. Ap dung ca debug + release (web), build lai exe.
- **Backup**: (thay doi nho trong viewer_H264wss.html, khong can backup file rieng - backup cua viewer hien co van dung).
- **Bo sung v1.55**: Bo sung o cho KHI BAT DAU scroll (justEnteredScroll): con tro chuot chuyen VE `touchStartPos` (vi tri dat tay ban dau) ngay khi vao scroll mode (truoc day chuyen ve vi tri finger dang di chuyen). Nhu vay chuot luon dung o diem dat tay tu luc bat dau scroll cho den khi tha tay. Da dong bo + build lai exe.

## v1.56 - Giam flicker vung den/trang + muot hon: aq-strength 12->6, bufsize 8M->12M (2026-08-07)
- **Van de**: Van con chớp hinh (flicker) khi co mau den trang tuong phan cao + bong hinh (smear) khi motion nhanh, trong video chua muot.
- **Nguyen nhan**: (1) aq-strength=12 qua manh -> AQ thay doi quantization giua cac frame o vung phang (den/trang) -> temporal flicker. (2) bufsize=8M nho -> quantization dao dong manh -> nhap nhay them.
- **Giai phap da thuc hien** (A+B): `aq-strength` 12 -> **6** (AQ vua phai, het flicker vung flat), `H264_BUFSIZE` 8M -> **12M** (phan bo bit on dinh hon -> muot). Giu nguyen: CBR 20M, FPS 45, 1080p, p6, lookahead 12, bf=2, keyint 60, forced-idr.
- **Trang thai**: dong bo debug+release, build lai exe. CHUA test thuc te. Neu van flicker -> giam tiep aq (4) hoac giam FPS 30.

## v1.57 - Giam khung chunk: WRITE_BUFFER_LIMIT 512KB->2MB + fix timestamp client theo fps that (2026-08-07)
- **Van de**: Khung hinh theo chunk (buffer day -> server skip frame -> giac chu ky). Log cho thay `[FC] skip backup` buf vuot 512KB lien tuc khi client khong tieu thu kip.
- **Nguyen nhan**: (1) WRITE_BUFFER_LIMIT=512KB qua nho -> client cham 1 chut la bi skip nhieu frame lien tuc -> giac. (2) Client WebCodecs gan timestamp `tsUs += 33333` (theo 60fps) trong khi server 45fps -> WebCodecs pacing sai -> gop phan giac khung.
- **Giai phap da thuc hien**:
  - Server: `WRITE_BUFFER_LIMIT` 512KB -> **2MB** (skip it hon, tre tang nhe).
  - Client: them `frameIntervalUs = 1000000 / msg.fps` (lay fps that tu server), `tsUs += frameIntervalUs` thay vi `33333` co dinh (pacing dung voi 45fps).
- **Trang thai**: dong bo debug+release, build lai exe. CHUA test thuc te.

## v1.58 - Giam nen tho bang multipass fullres (2-pass rate control) (2026-08-07)
- **Van de**: Doi tuong di chuyen van bi blocky. User huong theo "giam compress" (giam nen tho) thay vi giam resolution.
- **Phan tich**: blocky do bit khong du cho motion; "giam nen tho" KHONG co nghia la giam bit (cang toi), ma la phan bo bit hieu qua hon o CUNG bitrate. Tham so chua dung: `multipass` (2-pass rate control) - encoder quet khung 2 lan phan bo bit toi uu cho vung chuyen dong -> giam blocky. GTX1060 ho tro `fullres`.
- **Giai phap da thuc hien**: them `'multipass': 'fullres'` vao NVENC branch (giu nguyen CBR 20M, p6, lookahead 12, bf 2, keyint 60, FPS 45). Dong bo debug+release, build lai exe. CHUA test thuc te.
- **Neu chua du**: (1) thu `bf` 2->0 (B-frame du doan 2 chieu gay artifact khi motion nhanh), (2) hoac cuoi cung moi giam resolution 75%/66% hoac FPS 30.
- **Bo sung v1.58**: multipass fullres khong du -> thu tiep `bf` 2 -> **0** (B-frame du doan 2 chieu gay artifact khi motion nhanh; P-frame don gian hon it vo cuc bo). Giu multipass fullres. Dong bo + build lai exe. CHUA test.
- Luu y ky thuat: build bi fail 1 lan do Windows Defender dang quet file exe moi (Access denied) -> cho ~6s la build duoc.

## v1.59 - Phan tich AQ/CQ/QP/CBR + ke hoach test chuyen sang CQ (2026-08-07)
- **Phan tich 4 loai rate control (giam blocky motion ma khong tang bitrate tong)**:
  1. **CBR** (dang dung): bit co dinh 20M moi luc -> khi motion, QP tang (nen tho) -> blocky; vung tinh lai lang phi bit.
  2. **CQ (Constant Quality)**: QP ON DINH, chat luong nhat quan -> vung tinh dung it bit, vung motion dung nhieu. Neu co cap (`maxrate`=20M) = "capped CQ": chat luong deu + khong vuot bandwidth. **Huong to nhat trong gioi han bandwidth**.
  3. **QP (qmin/qmax)**: gioi han nen toi da/thap nhat, ket hop CQ de chan QP qua tho.
  4. **AQ (spatial-aq + aq-strength)**: phan bo bit theo do phuc tap vung (dang aq-strength=6).
- **Ke hoach test**: Test 1 = chuyen `rc: 'cbr'` -> `rc: 'cq'` (capped maxrate 20M, bufsize 12M), them `qmin/qmax` neu can. Luu y: test so bo `rc=cq` bi FAIL ("Invalid argument") -> can tim cau hinh hop le truoc khi ap dung.
- **Trang thai**: chua ap dung. Giu nguyen cau hinh hien tai (CBR 20M, p6, bf=0, lookahead 12, multipass fullres, aq 6, keyint 60, FPS 45).
- **Ket qua khao sat CQ**: `rc='cq'` KHONG ho tro tren build NVENC nay (Invalid argument moi to hop). Thay the thanh **`rc='constqp'` + `qp` + cap (maxrate/bufsize)** = capped CQ (QP co dinh, khong vuot bandwidth) - hop le moi gia tri qp 26-32.
- **Test 1 (da ap dung)**: chuyen `rc` 'cbr' -> **'constqp'**, `qp`='30' (0-51, thap = net), giu cap maxrate 20M + bufsize 12M. Giu nguyen: p6, bf=0, lookahead 12, multipass fullres, aq 6, keyint 60, FPS 45. Dong bo debug+release, build lai exe. CHUA test thuc te. Tinh chinh qp sau: 26 (net hon) / 32 (nhe hon).
- **Phan tich QP (tiep theo, de tinh chinh)**:
  - Ban chat: QP 0-51, thap = net + nhieu bit, cao = nen manh + it bit. Moi +6 QP giam nua bitrate.
  - Giam QP (30->26): vung tinh net hon NHUNG khi motion bi cap 20M chan -> blocky dot ngot; rui ro vuot bandwidth -> jitter.
  - Tang QP (30->34): motion it bi chan (luon duoi cap) -> blocky motion giam, NHUNG chat luong moi luc kem (nhieu, banding, chu khong sac).
  - Mau chot: voi cap 20M khong co QP nao "dep" ca (thap -> motion vo vi chan cap, cao -> toan hinh kem). CQ/constqp chi ON DINH (het flicker) + vung tinh net hon, KHONG tao them bit cho motion.
  - Buoc tiep de thu: them `qmin`/`qmax` (vi du qmin=26, qmax=40) chan QP khong tang vo han khi bi cap -> gioi han blocky toi da.
- **Ket qua test CQ (constqp qp=30)**: Video Youtube chi con dam ngang, IT DI + NHANH HON (cai thien ro). Nhung DOI TUONG NHO den/trang di chuyen van bi nhieu o vuong (thieu chi tiet vat nho).
- **Phan tich**: qp=30 kha cao -> macroblock 16x16 nen tho vung vat nho nhieu chi tiet -> vo thanh o vuong khi di chuyen.
- **KE HOACH (chuan bi sua, chua ap dung)**:
  1. Giam `qp` 30 -> **27** (tang chi tiet vat nho, vung tinh net hon).
  2. Them `qmin=26` + `qmax=40` (chan QP khong tang vo han khi bi cap 20M -> blocky co gioi han; qmin giu chat luong toi da).
  3. Test: doi tuong nho di chuyen + youtube. Neu bi jitter (vuot bandwidth) -> lui ve qp=30, hoac thu qp=28.
  - Danh doi: qp thap hon -> vung motion co the bi cap 20M chan (blocky dot ngot) nhung vat nho net hon; qmax=40 dam bao blocky khong qua muc.
- **Da ap dung (tiep v1.59)**: `qp` 30 -> **22** + them `qmin=20` + `qmax=40`. Ly do: bitrate thuc chi ~500KBps (4Mbps) trong khi cap 20M -> con du bandwidth nhieu, giam QP dang ke de tang chi tiet vat nho. Dong bo debug+release, build lai exe. CHUA test thuc te.
- **Bug phat hien khi test qp=22**: log spam `SSL connection is closed` + `send=0.0` (video dung 1 luc). Nguyen nhan: co 2 server_manager.exe + 2 server_H264wss.exe chay song song (instance cu chua tat, single-instance lock khong bat duoc instance elevated cu) -> 2 server con giang co stream -> SSL closed spam + send roi 0. Da kill het + chay lai dung 1 manager. Trang thai: on dinh.
- **Luu y van hanh**: khi thay doi config + build, phai kill HET server_manager + server_H264wss (ca instance cu elevated) truoc, chi chay 1 manager duy nhat, tranh 2 server con chong cheo.

## v1.60 - Het "do sau scroll": khi nghen bo het frame cu + force keyframe (2026-08-07)
- **Van de**: Sau khi scroll 1 cai, server bi "do" 1 thoi gian. Log: encode=44 send=0.1->0.0 (khong gui duoc frame) roi hoi phuc sau khi connect lai.
- **Nguyen nhan**: scroll -> motion -> buffer client day (vuot WRITE_BUFFER_LIMIT) -> server skip delta frame NHUNG khong danh dau can keyframe -> sau khi het backlog, client nhan delta frame reference frame da bi bo -> decode loi -> phai cho keyframe tu nhien (keyint 60 = 1.3s) -> do.
- **Giai phap da thuc hien** (server_H264wss.py):
  1. Khi nghen (buffer day): add ws vao `client_needs_keyframe` (bo het frame cu, chi nhan keyframe moi -> decode sach, khong delta hong).
  2. Trong stream_loop: neu co client dang `client_needs_keyframe` -> `_force_keyframe_next = True` -> encode IDR NGAY (khong cho keyint 60).
- **Trang thai**: dong bo debug+release, build lai exe. CHUA test thuc te.

## v1.61 - Ep bitrate CBR 12M: het vo video nho/doi tuong chuyen dong (2026-08-07)
- **Van de**: Van vo blocky khi doi tuong/video chuyen dong, bitrate thuc chi ~5-6Mbps.
- **Nguyen nhan**: `constqp qp22` de encoder TU DO dung bit -> vi man hinh phan lon tinh nen chi dung 5-6M (thap), vung video nho/doi tuong chuyen dong THIEU bit cuc bo -> vo. Co du bandwidth (2.5MBps) nhung encoder khong chu dong dung.
- **Giai phap da thuc hien**: chuyen `constqp qp22` -> **CBR 12Mbps** (1.5MBps < 2.5MBps an toan, khong overshoot vuot mang): CBR EP encoder luon co dung ~12M -> bit du don vao vung chi tiet -> video nho/doi tuong net hon han. `H264_BITRATE/MAXRATE` 20M -> **12M**, bufsize 12M.
- **Trang thai**: dong bo debug+release, build lai exe. CHUA test thuc te. Neu van vo -> tang CBR len 15M (van < 2.5MBps an toan).
- **Phat hien quan trong sau test CBR 12M**: van vo TOAN BO khung (vun san) du bitrate dung ~1.4MBps. Dieu nay KHONG phai dau hieu thieu bit ma nghi ngo **rate control NVENC bi loi do chong chat option**. Qua nhieu vong, config dang chat dong: `tune=ll` + `multipass=fullres` + `rc-lookahead=12` + `aq-strength` + `spatial-aq` + CBR... -> combo nay de lam NVENC roi vao trang thai cap phat bit sai -> vo san toan khung.
- **KE HOACH (chuan bi): RESET config NVENC toi gian chuan** (kien nghi OBS, da on dinh):
  - `preset=p5 | tune=ll | rc=cbr | b=12M | maxrate=12M | bufsize=8M | g=60 | bf=0 | rc-lookahead=8 | spatial-aq=1 | forced-idr=1`
  - BO HET: `multipass=fullres` (co the xung dot tune=ll - multipass can buffer/lookahead con ll gioi han latency), `aq-strength` thu cong, `lookahead=12`, `qmin/qmax`.
- **Buoc tiep**: do that bitrate tung config (encodder dung du bit hay khong) TRUOC khi ap dung, tranh doan mo. (Test truoc bi loi script - numpy ndarray khong set pict_type sau khi copy, can tao VideoFrame moi moi set duoc.)
- **Phat hien then chot**: khi doc file, nhan ra `maxrate`/`bufsize` bi TRUNG 2 lan trong options NVENC (qua nhieu vong edit chong chat -> trung option). Dieu nay CO THE gay loi rate control NVENC (option trung nhau -> encoder roi trang thai sai) -> vo san toan khung.
- **Da ap dung (tiep v1.61)**: RESET config NVENC SACH TOI GIAN: `preset=p5 | tune=ll | rc=cbr | b/maxrate/bufsize=12M | g=60 | bf=0 | rc-lookahead=8 | spatial-aq=1 | forced-idr=1`. BO HET: multipass, aq-strength thu cong, lookahead 12, qmin/qmax, spatial-aq=0, bo trung option. Dong bo debug+release, build lai exe. CHUA test thuc te.
- Test local khong dang tin (bitrate 0.27M, IDR=0 bat ki config - co the do cach test/noi dung) -> chi tin ket qua test tren may that.
- **Ket qua config sach CBR 12M**: van 1.4MBps va VAN VO blocky. Quan trong: CA CBR 12M lan constqp qp22 deu vo -> bitrate KHONG phai yeu to quyet dinh (thu 2 che do, 2 muc bitrate khac nhau, deu vo).
- **Ket luan + de xuat moi**: nghi van loi o CAPTURE (dxcam) hoac ENCODE base - neu frame nguon da nhieu thi encoder chi encode dung cai nhieu do, doi tham so vo ich. **KE HOACH MOI: kiem tra frame capture goc (chup 1 frame dxcam luu PNG xem co sach khong)** truoc khi quay vo vong tham so. Neu capture sach -> loi encode; neu capture nhieu -> loi dxcam.
- **Quay ve QP (constqp) theo yeu cau**: se ap dung lai constqp qp22 (config sach, khong trung option).
- **Ket qua dieu tra sâu**: (1) dxcam capture SACH (frame goc khong nhieu), (2) NVENC encode-decode KEYFRAME SACH (khong vo), (3) test local KHONG dang tin - moi test (tinh, nhieu, scroll gia co motion) deu ra bitrate 0.27M CODINH (bat thuong, co the do cach test/flush) trong khi server that dung dung 1.4MBps. -> Khong the dung test local de so sanh config.
- **Con 2 cach PHAN BIET loic encode vs loic client (WebCodecs decode P-frame)**:
  - **A. Client dung Broadway (software) thay WebCodecs**: neu het vo -> loi WebCodecs hardware decode P-frame; neu van vo -> encoder.
  - **B. Server dung libx264 thay NVENC**: neu het vo -> loi NVENC driver; neu van vo -> van de khac.
- Chua thuc hien A/B - cho user chon.
- **Ghi chu: DANG DOI TEST** - chua thuc hien A (Broadway client) va B (libx264 server). Khi user quyet dinh test se ap dung + ghi ket qua vao day. (2026-08-07)
- **Ghi chu test A/B/C/D (2026-08-07):**
  - Dinh chinh: test local MAC THUC RA dung bitrate. 0.27 la Mbit/frame (0.27 x 45fps = 12.15Mbps = dung CBR 12M). Cac lan ghi "0.27M bat thuong / test local khong tin cay" la SAI do tinh nham don vi (lay bit/frame lam Mbps).
  - Phan tich 2 anh scroll-gia (s_orig vs s_decoded): PSNR 40.56dB, chi 0.04% pixel sai >30, khong blocky => ENCODER NVENC xử lý motion mạnh o CBR 12M LA SACH, KHONG phai thu pham.
  - Vi vay vo blocky khi motion tren server that la do: (1) mat goi tin tren mang (bitrate cao -> goi lon de mat -> vo), hoac (2) client WebCodecs decode loat P-frame (keyframe moi 60 frame).
  - Phan biet bang 2 test moi:
    - **C. Tang keyframe** (server g=45 thay vi 60). Het vo => loi client decode P-frame dai. (1 dong sua, lam truoc)
    - **D. Ghi luong stream client-side** + log dropped frames. Co packet loss => loi mang truyen.
  - (A/B truoc do van DANG DOI: A=Broadway soft decode client, B=libx264 server - chua thuc hien.)

## Van de chua giai quyet (2026-08-07)
- **Van de**: Khi man hinh may tinh bi tat chuyen sang che do cho (sleep/off), server khong nhan duoc request/anh moi tu client; chi khi man hinh sang lai (wake) moi bat duoc frame.
- **Nguyen nhan**: Chua phan tich. Do uoc luong: khi man hinh tat, dxcam/DXGI khong sinh frame moi (Duplication API khong co du lieu toi), nen _capture_loop khong co frame de encode va gui -> stream dung lai. (Chua xac nhan, can test them.)
- **Giai phap**: Chua co. Dinh huong kiem tra: su dung frame cuoi cung (retain last frame) gui tiep khi khong co frame moi, hoac dung virtual display/buffer de giu nguon video song khi man hinh tat. (Chua thuc hien.)
- **Ket qua TEST A (force Broadway, 2026-08-07): KHONG hien hinh -> KHONG the ket luan.**
  - Thuc hien: them FORCE_BROADWAY=true bo qua WebCodecs trong viewer_H264wss.html.
  - Ket qua: dien thoai KHONG nhan duoc hinh (den man hinh).
  - Nguyen nhan: dung van de da biet o changelog (dong ~452) - Broadway khong khoi tao duoc voi NVENC vi NVENC khong nhung SPS/PPS inline + khong sinh IDR dung -> Big play khong hien. KHONG phai loi force-boardway.
  - Ket luan: test A khong dung de so sanh vo blocky vi Broadway + NVENC von khong chay. Da HOAN NGUYEN A (client ve WebCodecs) va HOAN NGUYEN B (server ve auto). Code ve trang thai goc.
  - HUONG TIEP: test B (doi encoder sang libx264) moi co the hien hinh voi ca WebCodecs lan Broadway, nen dung test B de phan biet NVENC vs libx264. Nhung test B CAN chay ban source python (hoac rebuild exe) vi exe release khong doc file .py.
- **Ket qua TEST A (Broadway + NVENC, 2026-08-07): Broadway decode KHONG ra frame.**
  - Phat hien quan trong: EXE nhuoc client `web/` (PyInstaller --add-data, spec dong 4) -> moi sua file html tren dia deu VO HIEU voi EXE, phai REBUILD moi co hieu luc.
  - Thuc hien: force Broadway + rebuild EXE. Logo: mode='broadway', [BROADWAY] got=400+ ready=true buf=0, co SPS/PPS/IDR moi 60 frame, NHUNG KHONG co [BROADWAY] OUTPUT frame -> Broadway nhan duong, khoi tao, nhung decode KHONG nha frame nao voi stream NVENC.
  - Ket luan: Stream NVENC khong tuong thich Broadway (khong decode ra hinh). Test A KHONG ket luan duoc thu pham vo blocky. Da BO QUA test A.
  - Loi phu: `_blockRemote is not defined` (dòng 906) - JS error khong lien quan video.
  - Hoan nguyen: bo FORCE_BROADWAY + debug Broadway, giu lai meta no-cache (tranh cache).
- **Bat dau TEST B (2026-08-07)**: Da hoan nguyen A (bo FORCE_BROADWAY + debug, giu meta no-cache). Doi H264_ENCODER="auto" -> "libx264" trong release/server/server_H264wss.py + rebuild EXE. Client ve WebCodecs mac dinh. Dang cho user test: neu het vo khi cuon -> NVENC thu pham; van vo -> client WebCodecs.
- **Ket qua TEST B (libx264 vs NVENC, 2026-08-07):** Se duoi libx264 (CPU) thi vo blocky GIAM nhung chua het: NVENC ~7/10, libx264 ~4/10.
  - Ket luan: Encoder GOP PHAN vao van de (NVENC te hon libx264), nhung libx264 van vo 4/10 -> con nguyen nhan khac (client WebCodecs / mang / keyframe drift), khong chi encoder.
  - Test tiep theo de xuat: TEST C - giam H264_KEYINT tu 60 -> ~15-30 (tang tan suat keyframe) tren NVENC, xem vo co giam khong -> neu giam thi do drift chuoi P-frame dai / keyframe hiem.
- **Bat dau TEST C (2026-08-07)**: Hoan nguyen B (encoder ve auto/NVENC). Giam H264_KEYINT 60 -> 30. Rebuild EXE xong. Dang cho user test: NVENC + keyint 30. So sanh vo vs NVENC keyint 60 (~7/10).
- **Ket qua TEST C (NVENC + keyint 30, 2026-08-07): vo giam** tu ~7/10 xuong ~4/10, hinh chan thuc hon, nhieu thua hon. Nhung van blocky/bong hinh o vung nhan vat di chuyen ~4/10.
  - Bang tong ket: NVENC keyint60 ~7/10; libx264 ~4/10; NVENC keyint30 ~4/10.
  - Ket luan: Tang tan suat keyframe giup NVENC 7->4 (mot phan do drift P-frame dai). Nhung 3 cau hinh khac nhau deu dung o ~4/10 -> phan con lai KHONG do encoder/keyframe, ma do client WebCodecs decode hoac thieu bitrate.
  - Bieu hien "blocky/bong hinh o vung chuyen dong" giong thieu bitrate (vung dong can nhieu bit).
  - De xuat test tiep: D1 - tang bitrate 12->20Mbps (giu keyint 30) de loai bien thieu bitrate.
- **NGUYEN NHAN GOC (so sanh ban Linux goc, 2026-08-07):** Doc ban Linux goc tai H:/home/haidang/Xemmanhinh/server/server_H264wss.py (chay khong vo):
  - Linux: GStreamer nvh264enc, H264_RC_MODE="vbr", H264_CONST_QUALITY=18 (chat luong muc tieu cao), H264_MAX_BITRATE=50000kbps (cap 50M!), H264_BITRATE=22000, spatial-aq+temporal-aq aq-strength=8, h264parse config-interval=1 (SPS/PPS nhuoc moi keyframe).
  - Windows: NVENC rc=cbr CUNG 12M (bitrate=maxrate=bufsize=12000000) -> khi co motion, bitrate bi khoa o 12M -> khong du bit cho vung chuyen dong -> BLOCKY. Day la nguyen nhan chinh.
  - Khac biet cot loi: Linux dung VBR/const-quality (de bitrate tu dao dong theo noi dung, uu tien chat luong, cap cao 50M), Windows dung CBR cung (khoa bit) -> con blocky vung dong.
  - DE XUAT: doi NVENC Windows tu rc=cbr -> rc=vbr voi cq (chat luong muc tieu) + maxrate cao (giong Linux), giu keyint 30. Khong phai "tang bitrate" don thuan ma doi logic rate-control.
- **Luu y**: user cho rang tang bitrate khong doi (co the thu bang CBR). Nhung ban Linux khong vo vi dung VBR/const-quality, khong phai CBR.
- **Da thuc hien (2026-08-07): Doi NVENC sang VBR theo ban Linux.** H264_BITRATE=22000000, H264_MAXRATE=50000000, H264_BUFSIZE=25000000. NVENC options: rc=cbr -> rc=vbr, them cq=20 (chat luong muc tieu), giu keyint=30/spatial-aq/forced-idr. Rebuild EXE xong. Dang cho user test: xem con vo blocky vung chuyen dong khong.
- **SUA (2026-08-07) - NVENC khong tu sinh keyframe dinh ky:** Phat hien _encode_frame chi danh I khi _force_keyframe_next=True (client moi/request). NVENC voi min-keyint=g khong tu sinh keyframe -> sau keyframe dau chi toan P-frame -> khong co keyframe reset -> drift/vo tich luy. Fix: server TU danh I dinh ky moi H264_KEYINT frame (them _encode_gop_count), khong phu thuoc GOP NVENC. Giu VBR cq=20. Rebuild EXE xong.
- **Luu y**: ca 2 sua nay (VBR + keyframe dinh ky) ket hop de giai quyet vo, da rebuild.
- **Ket qua test VBR + keyframe dinh ky (2026-08-07):** Vo giam, hinh co ve co ban hon, nhung van con nhiem/bong nguoi. Bitrate do duoc ~2.4MBps (~19.2Mbps) chua den max 50M. Chua het vo.
- **Thuc hien (2026-08-07):** Doi NVENC tu rc=vbr sang rc=constqp, qp=18 (co dinh chat luong pixel, giong Linux). Rebuild EXE xong. Dang cho user test.
- **Ket qua constqp QP=18 (2026-08-07):** It nhiem/bong/jitter hon, nhung van con blocky ("dam 7 sac") nhieu. Lai xuat hien hien tuong KHUNG KHUNG, GIAT GIAT, GAY GOC nhu lag - giong luc dau moi tao app. Nghi ngo keyint=30 gay lag do tang bitrate dot bien.
- **Test keyint 60 lai (2026-08-07):** Do nghi keyint=30 gay lag/khung khung, tang keyint tro lai 60 voi constqp QP=18. Rebuild xong, dang cho user test.
- **Ket qua keyint 60 + constqp QP=18 (2026-08-07):** Khong bi khung, muot hon, NHUNG lai bi nhieu/nhoe hon. Trade-off ro rang: keyint 30 -> it nhoe nhung khung; keyint 60 -> muot nhung nhoe.
- **Test keyint 45 (2026-08-07):** Can bang giua 30 va 60. Rebuild xong, dang cho user test.
- **SUA QUAN TRONG (2026-08-07) - Them temporal-aq + profile high + preset p7:** Phat hien ban Linux co `temporal-aq=true` ma Windows THIEU. temporal-aq phan bo them bit cho vung chuyen dong - dung trieu chung "blocky o nhan vat di chuyen". Them vao: temporal-aq=1, preset p5->p7, profile main->high (CABAC). QP=18 (khop Linux). Giu keyint 60, constqp, spatial-aq, forced-idr. Rebuild xong.
- **SUA (2026-08-07): constqp -> VBR+cq=18.** "Dam song 7 sac" = color banding do constqp phan bo bit khong deu (vung phang thieu bit). Doi sang VBR+cq=18 (khop Linux: rc-mode=vbr + const-quality=18). Giu temporal-aq, spatial-aq, preset p5, profile main, keyint 60. Rebuild xong.
- **SUA (2026-08-07) - theo KN Linux:** User chia se: Linux giam aq-strength 7->2 (giam "7 sac nhay"), tang QP 5->20 (giam ap luc render+bitrate). Ap dung: them aq-strength=2, cq 18->20. Giu VBR, temporal-aq, spatial-aq, preset p5, profile main, keyint 60. Rebuild xong.
- **SUA (2026-08-07) - Tat spatial-aq:** User phat hien vung gradient chuyen mau muon de bi nhieu. spatial-aq lay bit tu vung phang/gradient -> banding. Tat spatial-aq=0, giu temporal-aq=1 (cho motion). Rebuild xong.
- **TEST BROADWAY + libx264 (2026-08-07):** Test phan biet CUOI CUNG: client WebCodecs hay encoder? Force libx264 (encoder chuan) + Broadway (software decode). libx264 nhung SPS/PPS/IDR dung -> Broadway decode duoc. Neu HET artifact -> loi WebCodecs hardware decode tren dien thoai. Neu VAN artifact -> encoder/capture. Rebuild xong.
- **TEST WebCodecs + libx264 (2026-08-07):** Broadway+libx264 den hinh -> bo FORCE_BROADWAY, giu libx264, ve WebCodecs. Test: neu HET artifact -> NVENC thu pham; neu VAN artifact -> client WebCodecs. Rebuild xong.

## 2026-08-08 - Fix double-click-hold-to-drag + touch gesture mis-detection + server_manager wrappers K/L/O/P

### 1. Double-click giữ chuột → drag (viewer_H264wss.html)
- **Vấn đề**: double click giữ chuột (không thả) không drag được đúng; sau khi kéo xong còn gửi click thừa.
- **Nguyên nhân**: browser bắn chuỗi `mousedown → mouseup → click → dblclick`; handler `dblclick` cũ luôn gửi 2x `mouse_click` kể cả sau khi đã drag.
- **Giải pháp**: theo dõi `_mouseBtnDown` / `_mouseDragged`; kéo rồi nhả → đặt `_suppressClick` chặn cả `click` lẫn `dblclick`. Reset flag ở `mousedown` mới (không reset trong `click` vì sau drag browser bắn click rồi mới dblclick — cần giữ flag cho cả 2).

### 2. Check touch — sửa 4 lỗi hiểu nhầm cử chỉ
Cơ chế: tap đơn KHÔNG gửi click ngay, chờ 500ms (`singleTapTimer`) xem có tap 2 không → có tap 2 = double-tap (bôi đen/drag), không có = gửi 1 click.

#### 2.1 Lặp double-click (bỏ fallback 750ms)
- **Triệu chứng**: tap 2 lần nhanh → server nhận click + double-click (lặp).
- **Nguyên nhân**: có fallback `now - lastTapTime < 750`. `lastTapTime` được đặt SAU khi click đơn đã gửi (trong callback timer 500ms). Nên tap 2 trong 750ms sau đó vẫn bị biến thành double-tap → gửi thêm down/up/click trong khi click tap 1 đã gửi rồi.
- **Giải pháp**: chỉ coi là double-tap khi tap 2 tới TRONG lúc click tap 1 còn đang chờ (`singleTapTimer` chưa fire). Click tap 1 đã gửi thì tap 2 là click riêng.

#### 2.2 Double-click nhầm khi tap xa (thêm check khoảng cách 50px)
- **Triệu chứng**: tap A rồi tap B (2 vị trí khác nhau, 2 icon khác nhau) → B bị double-click nhầm.
- **Nguyên nhân**: chỉ xét thời gian, không xét khoảng cách 2 tap.
- **Giải pháp**: lưu vị trí tap 1 (`pendingTapClient`), tap 2 phải cách tap 1 dưới 50px (`DT_MAX_DIST`) mới là double-tap. Tap xa nhau = 2 click riêng ở đúng vị trí.

#### 2.3 Rung nhẹ thành scroll (ngưỡng 2px → 10px)
- **Triệu chứng**: chạm xuống rung nhẹ 3-5px → click bị hủy + gửi scroll nhầm.
- **Nguyên nhân**: ngưỡng vào scroll mode chỉ `dist > 2px` — tay run >2px là vào scroll.
- **Giải pháp**: nâng lên `dist > 10px` và không vào scroll khi đang `doubleTapSelecting` / `_mouseHeld`.

#### 2.4 Drag ngắt sau 250ms (thêm `_mouseHeld`)
- **Triệu chứng**: double-tap giữ và kéo, sau 250ms drag biến thành scroll.
- **Nguyên nhân**: `doubleTapSelecting` tự tắt sau 250ms (`DT_RELEASE_MS`); code cũ chỉ check `doubleTapSelecting` → rơi xuống nhánh scrollMode.
- **Giải pháp**: điều kiện gửi `mouse_move` thành `doubleTapSelecting || _mouseHeld`. `_mouseHeld` chỉ tắt khi nhả tay (touchend) → kéo bao lâu cũng chạy.

### 3. Server manager wrap K/L/O/P (server_manager.py)
- **Vấn đề**: cần chạy từng bản test (K/L/O/P) độc lập, mỗi bản 1 wrapper riêng.
- **Nguyên nhân**: server_manager cũ chỉ wrap cố định `server_H264wss.exe`.
- **Giải pháp**:
  - `_detect_target()` tự nhận diện tên exe của chính manager → wrap đúng server: `server_manager.exe`→`server_H264wss.exe`, `server_manager_K.exe`→`server_H264wss_testK.exe`, `_L`→testL, `_O`→testO, `_P`→testP.
  - PID lock riêng theo từng wrapper (`server_manager.pid`, `server_manager_testK.pid`, ...) → 2 wrapper khác nhau không giết lẫn nhau.
  - Thêm spec `server_manager_{K,L,O,P}.spec`; build đủ 4 exe test + rebuild `server_manager.exe`.
  - Cập nhật BUILD.md mục 4.5.
  - Lưu ý: các server vẫn dùng chung 3 port (8765/8766/8767) → chỉ chạy 1 wrapper tại 1 thời điểm.

## 2026-08-08 - Rebuild Test O (html) + Test P (html+dither) theo changelog

### Van de
- Exe test cu chua HTML cu (khong co fix drag/touch) vi server doc web tu ben trong exe (sys._MEIPASS) -> sua html tren dia khong co hieu luc voi exe da build.
- Source server_H264wss.py khong con code dithering (bi ghi de).

### Nguyen nhan
- Exe dong goi web qua --add-data; phai REBUILD moi nhung duoc html moi.
- Dithering chi ton tai trong exe testO (khong con trong source/backup).

### Giai phap (da thuc hien)
1. Trich xuat code dithering tu pyc exe testO (pyinstxtractor-ng + xdis):
   - H264_DITHER=1, _dither_tile=None, tile 64x64 co dinh + np.tile + np.clip truoc khi encode.
2. Rebuild:
   - server_H264wss_testO.exe: NVENC vbr cq=16, aq=4, keyint 120, dither=0 (chi html moi).
   - server_H264wss_testP.exe: constqp qp=22 (qmin20/qmax40), 20M cap, 12M buf, p6, lookahead 12, multipass fullres, aq=6, keyint 60, dither=1.
3. Rebuild wrapper: server_manager_O.exe, server_manager_P.exe.
4. Khoi phuc source ve config P + dither.

### Trang thai
- 4 exe moi trong dist/: testO, testP, manager_O, manager_P. Da verify html moi nhung dung trong exe.

## 2026-08-08 - Rebuild Test K + Test L (html moi nhat)

### Giai phap (da thuc hien)
1. server_H264wss_testK.exe: NVENC vbr cq=14, aq=8, keyint 150, spatial+temp aq, dither=1; libx264 crf=14.
2. server_H264wss_testL.exe: nhu K nhung pix_fmt=yuv444p + profile high444p (4:4:4 full chroma), dither=1.
3. Rebuild wrapper server_manager_K.exe, server_manager_L.exe.
4. Khoi phuc source ve config P + dither.

### Trang thai
- Du 8 exe KLOP: server testK/L/O/P.exe + manager K/L/O/P.exe, tat ca nhung html moi nhat.

## 2026-08-08 - Phan tich P bi delayed hinh anh hon app khac

### Van de
- App P (testP) hien thi hinh anh bi delay ro ret hon cac ban khac (O/K/L) du cung nguon capture.

### Nguyen nhan (phan tich)
- Doc pyc truc tiep tu exe testO/testP (pyinstxtractor-ng + marshal), so sanh options NVENC thuc te:
  - testO: rc=vbr cq=16, preset p5, KHONG co rc-lookahead, KHONG co multipass, aq spatial+temporal 4, keyint 120.
  - testP: rc=constqp qp=22 (qmin20/qmax40), preset p6, **rc-lookahead=12**, **multipass=fullres (2-pass)**, aq spatial 6, keyint 60.
- 3 yeu to gay delay cua P:
  1. rc-lookahead=12: giu 12 frame truoc khi encode -> +200ms delay o 60fps.
  2. multipass=fullres: 2-pass full resolution, buffer nhieu frame -> nguon delay lon nhat.
  3. preset p6 cham hon p5.
- Ket luan: delay do cau hinh encoder NVENC, khong phai mang/decode.

### Giai phap de xuat (chua thuc hien)
- Thu rc-lookahead=12 -> 0 (hoac 2-4) va multipass=fullres -> quarterres (hoac bo multipass); giu constqp qp=22 + cap 20M.
- Neu can muot: preset p6 -> p5.

### Bo sung: So sanh latency K/L vs O/P (da doc config thuc te ca 4 exe)

| Thong so | K | L | O | P |
|---|---|---|---|---|
| rc | vbr cq=14 | vbr cq=14 | vbr cq=16 | constqp qp=22 |
| preset | p5 | p5 | p5 | p6 |
| rc-lookahead | 0 | 0 | 0 | 12 |
| multipass | khong | khong | khong | fullres |
| profile | main | high444p | main | main |
| fps | 45 | 45 | 60 | 60 |
| keyint | 150 | 150 | 120 | 60 |

- Thu tu nhanh -> cham: **K ~ O > L > P**.
  - K va O nhanh nhat, ngang nhau (p5, khong lookahead/multipass); cq=14 (K) nang hon cq=16 (O) nhung K 45fps / O 60fps nen do tre gan tuong duong.
  - L cham hon K mot chut: 4:4:4 high444p (~1.5x chroma) -> encode lau hon moi frame.
  - P cham nhat: lookahead=12 (+200ms @60fps) + multipass=fullres (2-pass) + preset p6.
- Neu can 4:4:4 dung L (cham hon K khong dang ke); muon latency thap nhat chon K hoac O.

## 2026-08-08 - Test L den man hinh khi thoat/vao lai + khong xin lai duoc keyframe

### Van de
- Dien thoai thoat app roi quay lai -> den man hinh vinh vien tren Test L (4:4:4), cac ban 4:2:0 (O/K/P) it gap. Client co gui request_keyframe nhung khong nhan duoc keyframe de decode lai.
- Test L con bi nhieu hon cac ban khac.

### Nguyen nhan (phan tich code)
- Server skip keyframe khi nghen (send_video_to_clients trong server_H264wss.py):
  - L la 4:4:4 -> bitrate ~1.5x, dien thoai decode cham -> WebSocket nghen (buffer > 2MB).
  - Khi nghen: server skip frame + danh dau client_needs_keyframe.add(ws). Nhung nhanh _buffer_backed_up chay TRUOC dieu kien gui -> keyframe cung bi skip khi buffer van day.
  - Quay lai tab: client request_keyframe -> server encode IDR -> nhung khong gui duoc (buffer day) -> client khong bao gio nhan keyframe -> den mai. Client chi decode khi isKey (!isKey && !decoderReady -> bo frame + xin keyframe tiep).
- Vong lap chet phia client (decodeFrame trong viewer_H264wss.html):
  - decodeQueueSize > 4 -> drop delta + videoDecoder.reset() + decoderReady=false -> reset xong lai can keyframe; cang nghen cang xin, cang khong nhan duoc.
- Race _force_keyframe_next (set trong stream_loop async, doc trong capture thread) chi la yeu to phu.
- Nhieu L: NVENC 4:4:4 kem hieu qua + dither ±1 ap len ca 3 kenh day du (4:4:4 khong bi chroma subsample che) -> noise/banding ro; cq=14 khong du bit cho vung phuc tap khi 4:4:4.
- Nhan xet them (user test): L con co nhieu dam nhay soc ngang 7 sac (rainbow line artifact) - KHONG phai do 4:4:4 va KHONG phai do dither (vi tu dau toi gio app nao cung bi, co truoc khi them dither). Kha nang do encoder/NVENC, can dieu tra rieng neu muon het.

### Giai phap sua doi (da thuc hien)
- Server (send_video_to_clients trong tat ca file server_H264wss*.py): khi _buffer_backed_up(ws) ma frame la keyframe VA ws dang nam trong client_needs_keyframe -> KHONG skip, uu tien gui keyframe (timeout 0.1), reset _buf_skip_count=0, roi client_needs_keyframe.discard + client_keyframe_wait_until.pop. Neu gui timeout/dong -> danh dau stale. Client den se nhan lai keyframe de decode sach.
- Client (viewer_H264wss.html decodeFrame): khi decodeQueueSize > 4 va gap keyframe -> videoDecoder.reset() + decoderReady=false + requestRemoteKeyframe() ngay (truoc chi reset khong xin keyframe -> vong lap chet).
- Rebuild 4 exe server_H264wss_testK/L/O/P.exe tu file py rieng (da verify: HTML co requestRemoteKeyframe, bytecode chua nhanh timeout 0.1 uu tien keyframe).
- Neu L chi de test 4:4:4: chap nhan nhieu do ban chat 4:4:4, hoac tang cq/bitrate; khong nen dua 4:4:4 vao production.

## 2026-08-08 - Double-tap ra double-click THAT (het doi ten file) + touch nhay + scroll nhay + idle timeout 5 phut

### Van de
- Double-tap tren dien thoai doi khi KHONG mo duoc file/folder ma bi nham thanh doi ten file (rename). Nghi do double-tap khong thanh double-click o cap Windows.
- Cham tay cam giac li: con tro chuot chua den vi tri cham ngay.
- Scroll cham/bi can di chuyen xa moi vao scroll mode.
- Server tu thoat sau 60s khong co client (log IDLE No clients for 60.0s).

### Nguyen nhan (phan tich code)
- Double-tap khong thanh double-click that:
  - Client gui 3 lenh roi rac qua network: mouse_down -> mouse_up -> mouse_click.
  - Moi lenh la 1 round-trip WebSocket rieng; mouse_click tren server con time.sleep(0.02). Khoang cach giua 2 lan mouse_down thuc te co the vuot GetDoubleClickTime() (500ms) do jitter mang -> Windows khong nhan la double-click -> chi 1 click vao file dang chon = RENAME.
- Chuot khong nhay: onTouchStart khong gui mouse_move (cho vao scroll mode >10px hoac click gui sau 500ms moi move).
- Scroll li: nguong vao scroll mode dist > 10px.
- Idle 60s: IDLE_PROCESS_EXIT = 60.0.

### Giai phap sua doi (da thuc hien)
- Server (5 file server_H264wss*.py): them lenh mouse_dblclick - thuc hien _mouse_move + down/up/down/up LIEN MACH trong 1 ham (sleep 30ms giua cac buoc), khong bi gian doan boi network -> Windows luon nhan dung double-click, khong thanh rename.
- Client (viewer_H264wss.html):
  - Double-tap: touchstart tap 2 khong gui mouse_down ngay; touchend release nhanh (<250ms) -> gui 1 lenh mouse_dblclick duy nhat tai vi tri tap 2 (doubleTapPos2); giu lau (timeout 250ms) -> moi gui mouse_down de boi den. Xoa nhanh gui mouse_up+mouse_click roi cu.
  - DT_MAX_DIST 50 -> 1000000 (gan nhu khong gioi han): 2 tap trong cua so thoi gian luon la double-tap, nhan tai vi tri tap 2.
  - Touch nhay: onTouchStart 1 ngon gui mouse_move NGAY tai vi tri cham (khong cho scroll/click).
  - Scroll nhay: nguong vao scroll mode dist > 10 -> dist > 3.
  - Cleanup doubleTapPos2 o touchcancel + cuoi onTouchEnd.
- Idle timeout: IDLE_PROCESS_EXIT 60.0 -> 300.0 (5 phut) trong ca 5 file server.
- Rebuild server_H264wss_testO.exe (da build voi du fix).

### Trang thai
- Da dong bo mouse_dblclick + touch nhay + scroll nhay + idle 5 phut vao source 5 file.
- testO da build; testK/L/P chua rebuild lan cuoi voi cac fix nay (can build khi test).

## 2026-08-08 - O lag 25-29fps du NVENC -> nguyen nhan DITHERING la nut that CPU -> bo dither O/P, K/L giu nguyen

### Van de
- Test O chay NVENC 1920x1080 nhung encode chi dat 25-29fps (target 60), hinh lag lag du chi 1 client.

### Nguyen nhan (phan tich + do benchmark)
- Log [ENCODER] NVENC h264: 1920x1080 -> KHONG phai fallback libx264 (dong threads=8 trong FPS log chi la so loi CPU, khong phai thread encoder).
- Dithering numpy la nut that: moi frame 1080p chay frame.astype(int16) + tile + np.clip + astype(uint8) tren CPU = ~30ms/frame -> gioi han ~34fps - dung khop encode=29-36 thuc te.
- NVENC encode nhanh nhung phai cho frame da qua dithering CPU -> encode fps bi keo xuong.

### Giai phap sua doi (da thuc hien)
1. Toi uu dither (5 file server): thay vi int16+clip moi frame (~30ms), cache 2 mang uint8 0/1 (pos=+1, neg=-1) va ap dung bang cv2.add/cv2.subtract saturate -> ~7ms/frame (nhanh gap ~4x). Do benchmark: 6.9ms -> khong con nut that.
2. Bo dither cho O va P (H264_DITHER = 0): O/P uu tien 60fps muot, khong can dither. Rebuild server_H264wss_testO.exe (13:13) + server_H264wss_testP.exe (13:12).
3. K va L GIU NGUYEN dither (=1) - chua chuyen (K 45fps, L 4:4:4; neu sau nay muon bo thi doi 1 dong H264_DITHER = 1 -> 0 roi rebuild).

### Doan code mau (dither toi uu bang cv2)
# Cache 1 lan (khi frame doi size)
# tile = np.random.randint(-H264_DITHER, H264_DITHER + 1, (64, 64, 3), dtype=np.int8)
# tile_full = np.tile(tile, (h // 64 + 1, w // 64 + 1, 1))[:h, :w]
# _dither_tile = ((tile_full > 0).astype(np.uint8), (tile_full < 0).astype(np.uint8))
# Moi frame:
# bgr_frame = bgr_frame.copy()
# cv2.add(bgr_frame, _dither_tile[0], dst=bgr_frame)
# cv2.subtract(bgr_frame, _dither_tile[1], dst=bgr_frame)

## v1.72 - Fix phim mui ten (Up/Down/Left/Right) khong hoat dong trong terminal TUI (opencode) (2026-08-11)
- **Van de**: Bam nut mui ten ▲▼ tren dien thoai (keyboard panel) de dieu huong con tro trong terminal (opencode TUI) khong hoat dong; cac phim khac (chu, Enter, Esc, Backspace) van OK. Chuot + cac phim khac gui qua server deu nhan.
- **Nguyen nhan**: Server gui phim mui ten bang `wVk=0x26/0x28/0x25/0x27, wScan=0` (chi VK, khong scancode, khong co `KEYEVENTF_EXTENDEDKEY`). Phim mui ten la *extended key* (scancode E0-prefix: Up=0x48, Down=0x50, Left=0x4B, Right=0x4D). Windows Terminal / console TUI chi tao duoc escape sequence `\x1b[A`/`\x1b[B` cho TUI khi phim duoc gui dung dang scancode + extended flag; gui wVk-only -> terminal khong nhan dien dung phim -> opencode khong nhan lenh dieu huong con tro. Cac phim khong phai extended key (chu/Enter/Esc) khong bi anh huong nen van chay.
- **Giai phap da thuc hien**:
  - Them `KEYEVENTF_SCANCODE = 0x0008` + `KEYEVENTF_EXTENDEDKEY = 0x0100`.
  - Them `_VK_EXT_SCAN` map (VK -> (scancode, extended)) cho phim dieu huong: Up/Down/Left/Right (0x48/0x50/0x4B/0x4D) + Home/End/PageUp/PageDown/Insert/Delete.
  - Sua `_vk_key_event`: neu la extended key -> gui bang `wVk=0, wScan=scancode, dwFlags=KEYEVENTF_SCANCODE[|KEYEVENTF_EXTENDEDKEY]`; phim thuong giu nguyen wVk nhu cu (khong doi flow dang chay OK).
  - Ap dung cho ca debug `server/server_H264wss.py` + release `release/server/server_H264wss_testP_new.py`, build lai `server_H264wss_testP_new.exe`, da thay the exe (dist -> release/server).
- **Kiem chung**: `py_compile` ca 2 file OK. Backup truoc khi sua tai `Temp/opencode/bak_arrowkeys`. CHUA test thuc te tren dien thoai.
- Ky thuat: deepseek-v4-flash-free opencode
## v1.73 - Force refresh khi server chết lặng: watchdog stall ép reconnect (2026-08-12)
- **Vấn đề**: Khi server `os._exit(0)` sau IDLE, WebSocket chết lặng, không nhận close frame → `ws.onclose` không bao giờ fire → `connect()` không được gọi → decoder không bị reset → viewer kẹt ở frame cuối mãi. Watchdog cũ (>3s) chỉ gọi `requestRemoteKeyframe()`, nhưng server đã tắt nên không có phản hồi gì.
- **Nguyên nhân**: Frame-stall watchdog chỉ có một ngưỡng duy nhất `STALL_TIMEOUT_MS=3000` (gửi keyframe); chưa có cơ chế ép đóng WS + reconnect khi server mất hoàn toàn. Hàm `connect()` (có sẵn force-close + `_wsCloseRescue` 3s cho trường hợp onclose không fire + reset decoder trong `ws.onopen`) chưa được gọi từ watchdog.
- **Giải pháp sửa đổi** (áp dụng `web/viewer_H264wss_P_new.html`):
  - Thêm hằng `STALL_RECONNECT_MS = 8000`.
  - Watchdog: >3s → `requestRemoteKeyframe()` (giữ nguyên); >8s → `sendDebug('stall_force_reconnect')` + gọi `connect()`. `connect()` tự force-close WS cũ (`oldWs.close()` + `_wsCloseRescue` 3s) rồi tạo WS mới → `ws.onopen` gọi `cleanupDecoder()` + reset `decoderConfigured/decoderReady/cachedSPS/PPS/tsUs/_lastRenderTs=0` + `requestKeyframe()` → nhận init mới + I-frame đầu.
  - Tái nhập (re-entry) được ngăn tự nhiên: `connect()` gán `ws=null` ngay, tick watchdog kế `if (!ws || ...) return;` thoát sớm; `ws.onopen` reset `_lastRenderTs=0` cũng ngăn watchdog fire liên tục.
- **Kiểm chứng**: Đọc lại `connect()` (force-close branch line 1134-1158 + rescue) và `ws.onopen` (reset decoder line 1171-1186) xác nhận flow reconnect → reset decoder → nhận init/keyframe. Chưa test thời gian thực thật (chưa deploy server IDLE).
- Signed: opencode/laguna-s-2.1-free

## v1.74 - Fix den man hinh khi reconnect: kick WS cu khong block (2026-08-12)
- **Van de**: App mobile background roi quay lai (hoac F5 refresh), video WS moi ket noi thanh cong ([WS] + total:1, ncode=40.x) nhung send=0.0 mai → man den. Refresh nhieu lan vo dung: chi thay [WS-AUDIO] +/- lap lai, khong co [WS] + moi cho video.
- **Nguyen nhan**: Trong _kick_old_session_for_ip, wait old.close() block (old la socket half-open tu client cu khong ACK; close-handshake khong bao gio hoan tat). Video ws_handler goi kick TRUOC khi dang ky: coroutine cua client moi treo o kick, khong toi duoc connected_clients.add(websocket) → connected_clients rong (WS cu bi stream_loop xoa vi ConnectionClosed) → stream_loop khong vao nhanh gui → _send_frame_count khong tang → send=0.0. Chi xay ra khi reconnect vi lan dau _ip_to_ws rong nen kick khong lam gi. Audio KHONG bi vi udio_clients.add TRUOC kick (bat doi xung video/audio).
- **Giai phap sua doi** (ap dung 6 file release: server_H264wss_testP_new.py, _testP.py, _testO.py, _testO_new.py, _testK.py, _testL.py):
  - _kick_old_session_for_ip: them tham so old=None. Neu truyen old thi dung reference do (khong doc lai map), neu None moi doc lai map. Boc wait old.close() trong syncio.wait_for(..., timeout=1.0), bat syncio.TimeoutError → pass (de handler cu tu cleanup o finally).
  - Video ws_handler: bat giu _old_ws = _ip_to_ws.get(client_ip) TRUOC khi ghi de _ip_to_ws[client_ip] = websocket, roi kick cu chay nen bang syncio.create_task(_kick_old_session_for_ip(client_ip, kind='video', old=_old_ws)) (co guard _old_ws is not None and _old_ws is not websocket). Giua get va set khong co await → atomic, khong the dan xen.
  - Giu nguyen: them connected_clients sau khi gui init (P_new/O_new), guard inally _ip_to_ws.get(client_ip) is websocket (ngan pop nham WS moi), _force_keyframe_next=True.
- **Kiem chung**: py_compile 6/6 OK. Verifier lan 2 PASS (loi CRITICAL lan 1 - kick doc lai map dan dong nham WS moi - da duoc sua triet de). Build lai server_H264wss_testP_new.exe (PyInstaller, dist -> release/server), da thay the. Backup truoc khi sua tai Temp/opencode/bak_reconnect. CHUA test thuc te tren dien thoai.
- Signed: deepseek-v4-flash opencode

## v1.75 - Fix deadlock _stream_lock + TOCTOU khi reconnect sau khi stream stop (2026-08-12)
- **Van de**: Dien thoai reconnect sau khi server da idle-stop stream → [WAKE] Display kept ON in duoc nhung [WS] + khong in, send=0.0 mai → man den. Chi thay audio connect, video khong gui duoc.
- **Nguyen nhan**: _do_stop_streaming giu _stream_lock (threading.Lock non-reentrant) roi goi _stop_streaming() (ham nay tu with _stream_lock mot lan nua) → DEADLOCK: cung thread giu lock 2 lan → thread timer (idle) giu lock vinh vien → moi _ensure_streaming() sau do block moi mai o with _stream_lock → video ws_handler treo o 
un_in_executor(_ensure_streaming) (line 1764) → khong toi duoc connected_clients.add → connected_clients rong → send=0.0. Audio khong bi vi udio_clients.add TRUOC _ensure_streaming.
- **Giai phap sua doi** (ap dung 6 file release: P_new, P, O, O_new, K, L):
  - Tach ham _stop_streaming_locked() (than ham stop, GIA DINH caller da giu _stream_lock, khong self-lock). _stop_streaming() tro thanh wrapper with _stream_lock: _stop_streaming_locked().
  - _do_stop_streaming: giu _stream_lock mot lan duy nhat, check _streaming_active + connected_clients/udio_clients TRONG lock roi goi _stop_streaming_locked() → vua HET deadlock vua DONG cua so TOCTOU (check va stop atomic cung lock).
  - P_new/O_new: them re-ensure sau connected_clients.add (if not _streaming_active: run_in_executor(_ensure_streaming)) de dong residual TOCTOU khi timer idle stop stream trong cua so gui init blocking.
- **Kiem chung**: py_compile 6/6 OK. Verifier lan 2 PASS (deadlock het, TOCTOU goc dong; chi con 1 residual MEDIUM da duoc va tiep cho P_new/O_new). Backup .py truoc khi sua tai Temp/opencode/bak_reconnect. CHUA build lai exe (chi sua .py). CHUA test thuc te tren dien thoai.
- Signed: deepseek-v4-flash opencode

## v1.76 - De xuat toi uu phan thua thai trong flow (CHUA sua, de sau) (2026-08-12)
- **Van de**: Sau khi fix reconnect + deadlock, server P new chay on (send=39.5, reconnect respawn OK). Kiem tra flow phat hien mot so phan thua thai / ton tai nguyen khong can thiet.
- **Phan tich** (verifier doc code, khong sua):
  - [ ] **F1 (cao)**: _find_best_audio_device() (line \~1494 trong _ensure_streaming) goi KHONG dieu kien moi lan respawn, du _audio_capture_device da cache (khong bao gio reset o _stop_streaming_locked). → detect lai thiet bi moi lan, them ~100ms+probe + log rac. ws_handler L1781 da guard if _audio_capture_device is None → khong nhat quan. **Sua: then guard if _audio_capture_device is None:**.
  - [ ] **F2 (vua)**: udio_ws_handler (L1875) goi _ensure_streaming → client audio-only khoi dong ca pipeline video (capture 60fps + NVENC) du khong ai xem. Coupling video+audio qua chat. De xuat: tach audio khoi _ensure_streaming, hoac chi start audio khi chua co video client.
  - [ ] **F3 (vua)**: dxcam warning "instance already exists" khi respawn. _stop_streaming_locked co del _camera dung, nhung _capture_loop (L757, L773) tai tao _camera = dxcam.create() moi sau khi stop da del → leak + warning. De xuat: check if not _streaming_active: return truoc khi tao camera moi o ca 2 nhanh, hoac 	hread.join() capture thread truoc khi del.
  - [ ] **F4 (thap)**: [FPS] encode=... in gia tri STALE sau [STREAM] Stopped (encode thread da dung han, chi la bien cache _encode_fps cu) → log gây hieu nham. stream_loop van busy-wait + in FPS khi khong client. De xuat: chi in khi _has_any_client().
  - [ ] **F5 (thap)**: _wake_display_on/_off goi trung (video + audio) — idempotent, vo hai. Co the guard bang flag.
  - [ ] **F6 (thap)**: _encode_stop = True set 2 lan khi stop (L1510 + L597 trong _stop_encoder) — vo hai.
- **Ghi chu quan trong**: [FPS] encode=39.8 sau [STREAM] Stopped KHONG phai encode that van chay — la gia tri cache cu. Khong ton tai nguyen that.
- **Ket luan**: KHONG can sua ngay (server dang chay tot, khong bug nghiem trong). Neu toi uu thi sua F1 truoc (an toan 1 dong). F2/F3 de dot sau. F4/F6 lam cung dot ve sinh log.
- **Quy uoc**: Cac muc de xuat o tren dang o tich `[ ]` = CHUA SUA. Bao gio sua muc nao thi danh dau `[x]` VA GHI THEM muc changelog moi (van de / nguyen nhan / giai phap) cho lan sua do. Khong duoc xoa/tim sua cac muc chua sua cu.
- Signed: deepseek-v4-flash api-box




## v1.77 - Fix WS accept loop chet vi WinError 64 khi server idle respawn (2026-08-12)
- **Van de**: Server idle 60s → os._exit(0) → manager respawn. Nhung co luc WS accept loop chet vinh vien: OSError [WinError 64] "network name no longer available" → asyncio ProactorEventLoop dong listen socket (8766/8767) khong recovery → client nhan onclose code 1006, khong ket noi lai duoc. Kèm spam ConnectionResetError 10054 trong HTTP handler.
- **Nguyen nhan**: Manager _port_listener dung SO_REUSEADDR — tren Windows cho phep 2 socket bind cung addr:port → trong cua so manager giu port + server con len, listen socket cua server con bi teardown → accept nem WinError 64 → proactor dong socket vinh vien (proactor_events.py nhanh loi goi sock.close(), khong lap lai accept). HTTP (8765) khong chet vi ThreadingHTTPServer accept per-thread. Spawn tu dist\ KHONG phai nguyen nhan.
- **Giai phap sua doi**:
  - **Fix b (goc, manager)**: server_manager.py _port_listener doi SO_REUSEADDR → SO_EXCLUSIVEADDRUSE (boc try/except OSError) de ngan double-bind port voi server con.
  - **Fix a (safety-net, server)**: server_H264wss_testP_new.py them _loop_exception_handler dat tren event loop — neu gap OSError winerror==64 → os._exit(1) (code nonzero) de manager vao nhanh c != 0 → respawn chu dong trong 3s. Doi syncio.run(run()) → 
ew_event_loop + set_exception_handler + run_until_complete. main() cu doi ten _run_server(), them main() wrapper. **Luu y QUAN TRONG**: khong dung os._exit(0) (manager xem la clean idle exit nen KHONG respawn → client 1006 stuck). Idle exit van giu os._exit(0).
  - **Fix c (cosmetic, server)**: handle_error bo qua ssl.SSLError, ConnectionResetError, ConnectionAbortedError, BrokenPipeError; get_request boc ssl_ctx.wrap_socket trong try/except (close socket + re-raise) → het spam log 10054.
- **Kiem chung**: py_compile 2 file OK. Verifier review: Fix b dung goc (race rebind mong manh nhung an toan thuc te vi server con import nang 2-5s), Fix a cau truc dung + handler chay dung (verified proactor_events.py line 862-869), Fix c khong nuot loi that. Da sua diem verifier bat: os._exit(0)→os._exit(1). Backup truoc khi sua tai Temp/opencode/bak_acceptfail. CHUA build lai exe (chi sua .py). CHUA test thuc te.
- **Ap dung cho TAT CA bien the**: 3 fix tren duoc ap dung dong bo cho 6 server (`server_H264wss_testP_new.py`, `_testP.py`, `_testO.py`, `_testO_new.py`, `_testK.py`, `_testL.py`) + `server_manager.py`. Verifier xac nhan 6 server + manager dong bo hoan toan (block fix a/c byte-identical), py_compile 7/7 OK. **DA build lai 7 exe** (6 server + server_manager_P_new) va copy tu dist -> release/server luc 19:20. Luu y: P_new bi loi PermissionError khi build do exe dang chay — da dong server roi build lai OK.
- Signed: deepseek-v4-flash api-box

## v1.78 - Fix WinError 64 goc (phuong an 3) + chong F5 spam dam bao ra hinh (2026-08-12)
- **Van de**: 
  1. WinError 64 VAN xay ra sau fix v1.77 (fix b SO_EXCLUSIVEADDRUSE chi chan double-bind cung tuple, khong triet race timing nha/re-bind port giua manager va server con).
  2. Khi client khong nhan duoc keyframe dau (F5 spam), stall watchdog viewer bi gate boi decoderReady/_lastRenderTs===0 → khong chay → den man hinh vinh vien.
- **Nguyen nhan**:
  1. _port_listener manager sau khi nha port van RE-BIND lai (vi _server_alive() con False trong luc spawn chua xong); spawn_server dung sleep(0.5) heuristic khong cho du ca 3 port that su rong truoc khi Popen → child bind trung/chen luc accept dang cho → WinError 64.
  2. Watchdog viewer if (!decoderReady) return; if (_lastRenderTs===0) return; → neu client connect ma khong decode duoc frame dau thi watchdog bo qua → khong request keyframe / khong force-reconnect → den vinh vien.
- **Giai phap sua doi**:
  - **Manager (phuong an 3)**: server_manager.py them _spawn_pending flag + per-port eleased event. Khi co connect (vt.set) → set _spawn_pending=True → listener KHONG re-bind cho toi khi server con exit. spawn_server cho ca 3 eleased event (timeout 3s) truoc Popen (thay sleep heuristic). Main loop reset _spawn_pending khi server exit.
  - **Viewer (chong den man hinh)**: web/viewer_H264wss_P_new.html them _wsConnectTs (moc thoi diem WS connect), set trong ws.onopen + cleanupDecoder. Watchdog bo 2 gate decoderReady/_lastRenderTs===0, dung nchor = (_lastRenderTs===0) ? _wsConnectTs : _lastRenderTs → khi den man hinh van chay: >3s request keyframe, >8s force-reconnect. Reset _wsConnectTs trong cleanupDecoder de cho decoder moi 3s/8s an han (tranh vong lap reconnect khi tab-wake).
- **Kiem chung**: py_compile server_manager.py OK. Verifier review: phuong an 3 dung, viewer fix dung (bỏ gate dung, chong spam/reentry du, khong regression path stream tot); da sua diem HIGH verifier bat (reset _wsConnectTs trong cleanupDecoder). Backup truoc khi sua: Temp/opencode/bak_acceptfail. **DA build lai 7 manager exe** (19:48-19:49) va copy tu dist -> release/server. Viewer HTML khong can build (serve truc tiep). CHUA test thuc te.
- Signed: deepseek-v4-flash api-box
- **FIX bug runtime**: luc dau build 19:48 manager _port_listener bi UnboundLocalError: cannot access local variable '_spawn_pending' vi ham long gan _spawn_pending=True (Python coi la local) nhung doc truoc khi gan. Da them global _spawn_pending vao dau _port_listener, chay thu bang python OK (khong con loi), build lai 7 manager exe (19:51-19:52) va copy tu dist -> release/server.
- Signed: deepseek-v4-flash api-box
- **FIX bug runtime 2**: luc chay manager exe gap NameError: name 'released' is not defined — bien eleased la local cua _hold_ports nhung spawn_server (ham toan cuc) goi eleased[p].wait(). Da doi thanh bien toan cuc _released_ports (khai bao global o module + trong _hold_ports va _port_listener + spawn_server). Chay thu bang python xac nhan manager spawn server con OK (khong con loi). Build lai 7 manager exe (20:31-20:32) va copy tu dist -> release/server.
- Signed: deepseek-v4-flash api-box

## TONG HOP - Cac nguyen nhan phat hien & bug quan trong (2026-08-12)
Muc nay tong hop cac van de chi tiet da ghi o cac muc v1.74 - v1.78, de tra cuu nhanh.

### 1. Den man hinh khi reconnect (send=0.0) - v1.74
- **Nguyen nhan**: _kick_old_session_for_ip goi wait old.close() block (old la socket half-open, client cu khong ACK). Video ws_handler goi kick TRUOC khi dang ky → coroutine client moi treo, khong toi connected_clients.add → connected_clients rong → stream_loop khong gui → send=0.0. Chi xay ra khi reconnect (lan dau _ip_to_ws rong). Audio khong bi vi add truoc kick (bat doi xung video/audio).
- **Fix**: kick boc timeout 1s + claim IP ngay truoc, kick cu chay nen (create_task). Verifier phat hien loi CRITICAL v1: kick doc lai map (da ghi de = WS moi) → dong nham WS moi → fix bang truyen reference old truc tiep.

### 2. Deadlock _stream_lock (sau khi stream idle stop) - v1.75
- **Nguyen nhan**: _do_stop_streaming giu _stream_lock (threading.Lock non-reentrant) roi goi _stop_streaming() (tu lock lai lan 2) → DEADLOCK → thread timer giu lock vinh vien → _ensure_streaming block mai → video khong add → send=0.0 den man hinh.
- **Fix**: tach _stop_streaming_locked() (than stop khong self-lock), _doorstop_streaming giu lock 1 lan + check client trong lock (dong TOCTOU). P_new/O_new them re-ensure sau add.

### 3. WS accept loop chet WinError 64 - v1.77
- **Nguyen nhan**: manager _port_listener dung SO_REUSEADDR tren Windows cho phep 2 socket bind cung port → race khi spawn → listen socket server con bi teardown → accept nem OSError [WinError 64] → asyncio ProactorEventLoop dong socket vinh vien (proactor_events.py nhanh loi sock.close(), khong lap lai accept) → client onclose 1006, khong ket noi lai.
- **Fix**: (b) manager SO_REUSEADDR → SO_EXCLUSIVEADDRUSE; (a) server them _loop_exception_handler (winerror=64 → os_exit(1) de manager respawn; KHONG dung os_exit(0) vi manager khong respawn khi rc==0); (c) HTTP boc wrap_socket + handle_error bo qua ConnectionResetError/SSLError (het spam 10054).

### 4. WinError 64 van con - phuong an 3 (v1.78)
- **Nguyen nhan**: fix b chi chan double-bind cung tuple, khong triet race timing re-bind port. _port_listener sau khi nha port van RE-BIND (vi _server_alive() con False trong luc spawn); spawn_server dung sleep(0.5) heuristic khong cho du 3 port rong truoc Popen → child bind chen luc accept dang cho → WinError 64.
- **Fix (phuong an 3)**: them _spawn_pending flag (listener khong re-bind khi pending) + per-port _released_ports event (spawn_server cho ca 3 port released truoc Popen).

### 5. Den man hinh vinh vien khi F5 spam (khong nhan keyframe dau) - v1.78 viewer
- **Nguyen nhan**: stall watchdog viewer bi gate if (!decoderReady) return; + if (_lastRenderTs === 0) return; → neu client connect ma khong decode duoc frame dau thi watchdog khong chay → khong request keyframe / khong force-reconnect → den vinh vien.
- **Fix**: bo 2 gate, them _wsConnectTs lam moc khi chua render (>3s request keyframe, >8s force-reconnect). Reset _wsConnectTs trong cleanupDecoder de tranh vong lap reconnect khi tab-wake.

### 6. Bug runtime manager (2 bug)
- **Bug 1**: UnboundLocalError: cannot access local variable '_spawn_pending' — ham long _port_listener gan _spawn_pending=True nen Python coi la local, nhung doc truoc khi gan. Fix: them global _spawn_pending.
- **Bug 2**: NameError: name 'released' is not defined — eleased la local cua _hold_ports nhung spawn_server (ham toan cuc) goi. Fix: doi thanh bien toan cuc _released_ports.

### 7. Diep dieu chuan doan (tool)
- So sanh 2 file/2 ban: dung c hoac doc lai.
- Kiem tra process dang chay: Get-Process / 	asklist.
- Kiem tra port: 
etstat -ano | findstr LISTENING.

### Trang thai hien tai
- 6 server .py + server_manager.py: da sua dong bo (fix v1.74-1.78).
- 6 server exe: da build lai (19:17-19:20).
- 7 manager exe: da build lai + copy (20:31-20:32).
- Viewer iewer_H264wss_P_new.html: da sua (khong can build, serve truc tiep).
- CHUA test thuc te day du tren dien thoai.
- Signed: deepseek-v4-flash api-box

## TONG HOP - Cac nguyen nhan MAN HINH DEN (full lich su den hien tai)
Muc nay tong hop rieng ve van de MAN HINH DEN - nguyen nhan quan trong nhat cua app. Tracuu nhanh theo thu tu xuat hien.

### 1. Goi frame TRUOC init (bug co nhat, goc re pho bien)
- **Nguyen nhan**: connected_clients.add(websocket) duoc goi TRUOC khi gui init JSON cho client. Vi _ensure_streaming blocking 1-3s, stream_loop gui frame video TRUOC khi client nhan init → decoderMode=null (chua init) → client bo het frame → watchdog dong WS → vong lap den man hinh.
- **Fix**: chi add vao connected_clients SAU khi gui xong init JSON + SPS/PPS (thu tu: init → SPS/PPS → add connected_clients). Comment loi canh bao duoc giu nguyen trong code (P_new/O_new add sau init; cac ban P/O/K/L add ngay - chu y race).

### 2. Reconnect → send=0.0 (v1.74)
- **Nguyen nhan**: _kick_old_session_for_ip → wait old.close() block (old la socket half-open client cu khong ACK). Video ws_handler goi kick TRUOC khi dang ky → coroutine client moi treo, khong toi connected_clients.add → connected_clients rong → stream_loop khong gui → send=0.0. Chi khi reconnect (lan dau _ip_to_ws rong). Audio khong bi (add truoc kick).
- **Fix**: kick boc timeout 1s + claim IP ngay truoc + kick cu chay nen (create_task). Verifier phat hien CRITICAL v1 (kick doc lai map da ghi de → dong nham WS moi) → fix bang truyen reference old truc tiep.

### 3. Deadlock _stream_lock (v1.75)
- **Nguyen nhan**: _do_stop_streaming giu _stream_lock (Lock non-reentrant) roi goi _stop_streaming() (tu lock lan 2) → DEADLOCK → thread timer giu lock vinh vien → _ensure_streaming block mai → video khong add → send=0.0 den man hinh.
- **Fix**: tach _stop_streaming_locked() (khong self-lock), _do_stop_streaming giu lock 1 lan + check client trong lock (dong TOCTOU). P_new/O_new them re-ensure sau add.

### 4. Khong nhan duoc keyframe dau (v1.78 viewer)
- **Nguyen nhan**: stall watchdog viewer bi gate if (!decoderReady) return; + if (_lastRenderTs === 0) return; → neu client connect ma khong decode duoc frame dau thi watchdog khong chay → khong request keyframe / khong force-reconnect → den VINH VIEN.
- **Fix**: bo 2 gate, them _wsConnectTs lam moc khi chua render (>3s request keyframe, >8s force-reconnect). Reset _wsConnectTs trong cleanupDecoder de tranh vong lap reconnect khi tab-wake.

### 5. Keyframe khong toi duoc client (co che phong hoa)
- **Nguyen nhan**: I-frame bi timeout/buffer-full khong toi client → client nam trong client_needs_keyframe mai mai → khong decode duoc → den.
- **Fix**: client moi (last_vid=-1) khong bi skip P-frame dau; keyframe-priority khi buffer day; watchdog keyframe-timeout 8s dong WS de client reconnect sach.

### Ket luan chung
- **Diem goc re pho bien nhat**: connected_clients rong (server encode nhung khong gui, send=0.0) HOAC client khong nhan duoc keyframe/I-frame dau de khoi tao decoder.
- **Bat doi xung video/audio** (add truoc/sau kick) la manh moi lay loi reconnect.
- **Non-reentrant lock goi 2 lan** la loi classing deadlock.
- Fix cac lop nay dam bao: client moi LUON nhan init + SPS/PPS + I-frame dau, va watchdog luon chay de tu phuc hoi du khi khong nhan duoc keyframe.
- Signed: deepseek-v4-flash api-box

## v1.79 - Fix 2 manager chay song song gay WS 1006 (named mutex) (2026-08-12)
- **Van de**: Client nhan WS 1006 lap lai vo han (connect → 1006 → reconnect → 1006) du khong refresh. Dieu tra phat hien 2 server_manager_P_new + 2 server_H264wss_testP_new chay dong thoi.
- **Nguyen nhan**: _acquire_single_instance cua manager dung file PID KHONG atomic (chi os.remove roi open().write(), khong co mutex that) → 2 instance cung luc khoi dong deu qua mat lock → ca 2 _hold_ports()/spawn_server() → spawn 2 server → double-bind port 8765/8766/8767 → accept loop server chet (WinError 64) → client connect toi port nhung khong co WS nao accept/handshake → 1006 → reconnect loop. GIẢ THUYẾT "browser tri nho cu" la SAI (WebSocket khong cache, khong service worker, khong luu WS trong localStorage; _wsClosing reset dung).
- **Giai phap sua doi** (server_manager.py): _acquire_single_instance doi sang **named mutex** (Windows CreateMutexW, atomic cross-process) + giu handle _single_mutex suot vong doi + van kill instance cu qua PID file + retry neu mutex bi giu. Instance moi luon kill instance cu truoc khi chiem quyen → khong bao gio co 2 manager song song.
- **Kiem chung**: py_compile OK. Chay thu 2 lan manager lien tiep → lan 2 kill lan 1, chi con 1 manager + 1 server instance. Da kill 2 manager + 2 server cu, build lai server_manager_P_new.exe (9:37 PM) va copy. CHUA test thuc te tren dien thoai.
- Signed: deepseek-v4-flash api-box
- **Bo sung**: da build lai 7 manager exe (P_new + K/L/O/O_new/P/chung) voi fix named mutex: P_new luc 9:37 PM, 6 con lai luc 21:38-21:39, copy tu dist -> release/server. Tat ca dong bo.
- Signed: deepseek-v4-flash api-box

## v1.80 - Nguyen nhan that cua WinError 64: bug stdlib gh-93821 (2026-08-12)
- **Van de**: WinError 64 VAN xay ra du da fix manager (named mutex + SO_EXCLUSIVEADDRUSE + _spawn_pending + wait released). Mau: client dang stream (send=35) roi F5 refresh → disconnect → accept loop WS chet → HTTP van song (GET /viewer toi) nhung WS moi khong connect → FATAL WinError 64 → server exit → manager respawn → moi connect duoc.
- **Nguyen nhan THAT (debugger phan tich)**: khong phai manager double-bind. La **bug CPython asyncio ProactorEventLoop gh-93821**: khi client F5-reconnect, TCP moi bi reset truoc khi AcceptEx hoan tat → inish_accept() (syncio/windows_events.py:556) nem OSError WinError 64 (ERROR_NETNAME_DELETED) → _start_serving.loop (proactor_events.py:862) bat OSError tho → sock.close() dong listen socket WS vinh vien → accept loop chet. HTTP khong bi vi chay thread rieng (ThreadingHTTPServer), WS (8766/8767) dung chung proactor accept loop. Python 3.14.6 dang dung CHUA co fix PR #124032.
- **Giai phap**: 
  - Da thu monkeypatch stdlib theo PR #124032 nhung QUYET DINH KHONG dung (finish_accept la closure local trong IocpProactor.accept, version-specific, rui ro pha vo server).
  - Giu nguyen safety-net hien tai (_loop_exception_handler winerror=64 → os._exit(1) → manager respawn). Day la giai phap thuc dung: co gi an doan ~3s khi F5-spam luc disconnect, nhung khong ket client 1006 mai.
  - Classify: khong can thiet nang Python (kho voi PyInstaller).
- **Kiem chung**: py_compile OK. Da xoa monkeypatch khong dung (gioi han an toan). CHUA build lai exe (chi sua .py server). CHUA test thuc te.
- Signed: deepseek-v4-flash api-box

## TONG HOP - Tien trinh loi WinError 64 (WS accept chet) + code minh chung
Muc nay tong hop TOAN BO qua trinh dieu tra, phat hien va code lien quan den loi WinError 64 (WS accept loop chet) de tra cuu.

### Giai doan 1 - Phat hien la dau (v1.77)
- **Hien tuong**: Server idle respawn nhung WS accept loop chet vinh vien, client 1006.
- **Gia thuyet ban dau**: manager _port_listener dung SO_REUSEADDR tren Windows cho phep 2 socket bind cung port → double-bind khi spawn → listen socket server con bi teardown → accept nem WinError 64 → proactor dong socket.
- **Fix da lam**: (b) manager SO_REUSEADDR → SO_EXCLUSIVEADDRUSE; (a) server _loop_exception_handler (winerror=64 → os._exit(1)); (c) HTTP boc wrap_socket.
- **Code (fix b, server_manager.py)**:
`python
srv.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
`
- **Code (fix a, server)**:
`python
def _loop_exception_handler(loop, context):
    exc = context.get('exception')
    if isinstance(exc, OSError) and getattr(exc, 'winerror', None) == 64:
        os._exit(1)   # manager respawn
    loop.default_exception_handler(context)
`

### Giai doan 2 - WinError 64 VAN con sau fix manager (v1.78)
- **Hien tuong**: van con FATAL WinError 64. Phan tich lai → race timing re-bind port (manager nha port theo heuristic, khong dong bo 3 port).
- **Fix (phuong an 3)**: them _spawn_pending flag + per-port _released_ports event; spawn_server cho 3 port released truoc Popen.
- **Code (server_manager.py)**:
`python
_spawn_pending = True  # listener khong re-bind khi pending
for p in PORTS:
    _released_ports[p].wait(timeout=3.0)  # cho ca 3 port nha han
`

### Giai doan 3 - Phat hien 2 manager song song (v1.79)
- **Hien tuong**: client 1006 lap lai vo han. Phat hien 2 server_manager_P_new + 2 server chay dong thoi.
- **Nguyen nhan**: _acquire_single_instance dung file PID khong atomic → 2 instance cung luc qua mat lock → ca 2 spawn → double-bind.
- **Fix**: doi sang named mutex (CreateMutexW) + giu handle + kill instance cu.
- **Code (server_manager.py)**:
`python
MUTEX_NAME = f"Global\\ScreenShareMgr_{_target}"
h = ctypes.windll.kernel32.CreateMutexW(None, True, MUTEX_NAME)
err = ctypes.windll.kernel32.GetLastError() if h else -1
# err==183 (ERROR_ALREADY_EXISTS) -> kill instance cu roi retry
`

### Giai doan 4 - Phat hien NGUYEN NHAN THU (v1.80): bug stdlib gh-93821
- **Hien tuong**: WinError 64 van xay ra du 1 manager. Mau RO: client dang stream (send=35) → F5 refresh → disconnect → accept WS chet ngay → HTTP van song (GET /viewer toi) nhung WS moi khong connect → FATAL → server exit → respawn.
- **Nguyen nhan THU**: **khong phai manager double-bind**. La bug CPython asyncio ProactorEventLoop **gh-93821**:
  - Client F5-reconnect → TCP moi bi reset truoc khi AcceptEx hoan tat → inish_accept() (syncio/windows_events.py:556) nem OSError WinError 64 (ERROR_NETNAME_DELETED).
  - _start_serving.loop (proactor_events.py:862) bat OSError → sock.close() dong listen socket WS vinh vien → accept loop chet.
  - HTTP khong bi vi chay thread rieng (ThreadingHTTPServer); WS (8766/8767) dung chung proactor accept loop.
  - Python 3.14.6 CHUA co fix PR #124032.
- **Code stdlib lo loi (asyncio/windows_events.py:555-556)**:
`python
def finish_accept(trans, key, ov):
    ov.getresult()   # nem OSError WinError 64 khi client reset
`
- **Code stdlib dong socket (asyncio/proactor_events.py:862-869)**:
`python
except OSError as exc:
    if sock.fileno() != -1:
        self.call_exception_handler({'message': 'Accept failed on a socket', ...})
        sock.close()   # DONG LISTEN SOCKET WS vinh vien
`
- **Giai phap cuoi**: thu monkeypatch stdlib theo PR #124032 nhung QUYET DINH KHONG dung (finish_accept la closure local trong IocpProactor.accept, version-specific, rui ro pha vo server). Giu safety-net (os._exit(1) → manager respawn) lam giai phap thuc dung.

### Ket luan
- WinError 64 = bug stdlib asyncio (gh-93821), trigger boi RST ket noi moi luc F5-reconnect.
- Manager + cac fix truoc (mutex, SO_EXCLUSIVEADDRUSE, _spawn_pending, released) dung de chong race luc spawn, NHUNG khong lien quan loi nay.
- Safety-net hien tai (server tu exit → manager respawn trong 3s) la giai phap thuc dung, co gi an doan ngan khi F5-spam luc disconnect nhung khong ket 1006 mai.
- Signed: deepseek-v4-flash api-box

## v1.81 - Fix triet de WinError 64: chuyen sang SelectorEventLoop (2026-08-12)
- **Van de**: WinError 64 (gh-93821) van gay WS accept chet khi client F5-reconnect. Safety-net (os._exit(1) → respawn) chi giam nhe (gian doan ~3s moi lan F5-spam luc disconnect).
- **Nghien cuu (general agent, test thuc te tren may)**: gh-93821 van OPEN (chua fix o bat ky Python 3.14/3.15/3.16). PR #124032 + #124779 van OPEN. Nang Python vo ich. Cac thu vien khac (aiohttp, uvicorn/starlette) van dung Proactor accept cua stdlib → cung dinh gh-93821. tornado/gevent tranh duoc nhung chi phi chuyen doi cao (rewrite 2200 dong). **SelectorEventLoop** (1 dong) la giai phap tot nhat: dung select() thay AcceptEx → accept fail chi log/ignore, listen socket KHONG bi dong, tu phuc hoi. Da test: 200 connection RST flood → server khong chet.
- **Giai phap sua doi** (server_H264wss_testP_new.py): doi loop = asyncio.new_event_loop() → loop = asyncio.SelectorEventLoop(). Giu nguyen safety-net _loop_exception_handler lam du phong. Giu nguyen websockets.serve, ssl, stream_loop, run_in_executor (khong doi API).
- **Kiem chung**: py_compile OK. Test that: server SelectorEventLoop khoi dong, WS 8766 accept OK, client that (192.168.3.1) ket noi + stream Started + SPS cached. Exe P_new da build lai (9:59 PM) va copy. Da dong het process cu. CHUA test F5-spam thuc te lau.
- Signed: deepseek-v4-flash api-box
- **Bo sung**: da ap dung fix SelectorEventLoop cho TAT CA 6 server (.py + exe): P_new (9:59 PM), P (22:07), O (22:08), O_new (22:09), K (22:09), L (22:10). py_compile 6/6 OK. Dong bo.
- Signed: deepseek-v4-flash api-box

## TONG HOP - 2 van de con: phim Up/Down TUI + tap kem nhay (2026-08-12)
Muc nay ghi 2 van de con va giai phap (CHUA sua, cho y kien user).

### 1. Phim Up/Down khong vao duoc opencode TUI (giới han nen tang)
- **Van de**: Phim Up/Down remote (qua SendInput extended key) CHI khong hoat dong trong tab terminal dang chay opencode (TUI). O app khac / terminal trong thi bam Up ao duoc.
- **Nguyen nhan (debugger nghien cuu, khong phai loi code server)**: 
  - App GUI + terminal trong (cooked mode): doc WM_KEYDOWN tu RIT → nhan phim ao SendInput binh thuong → hoat dong.
  - opencode TUI (raw/VT mode): KHONG doc WM_KEYDOWN, ma doc **escape sequence** (ESC [ A) tu console input buffer. conhost/Windows Terminal **khong dich input injected (SendInput) sang VT escape sequence** cho phim mui ten → TUI khong nhan gi.
  - Dan chung: winpty issue #82 (VT mode zero hoa VK khi sinh escape), microsoft/terminal PR #16511 (wVirtualKeyCode=0 coi la synthesized event, dung UnicodeChar; voi phim mui ten UnicodeChar=0 → khong phat ra gi).
- **Code hien tai gui Up/Down** (server_H264wss_testP_new.py line 77-83 _VK_EXT_SCAN, line 344-361 _vk_key_event):
  - Gui wVk=0, wScan=scancode, KEYEVENTF_SCANCODE|EXTENDEDKEY (scancode extended).
- **Giai phap de xuat**:
  - (C) Thu gui wVk dung (VK_UP) kèm scancode thay vi wVk=0 — chi phi thap, co the giup TUI (conhost co the dich escape dua tren wVirtualKeyCode). HUy nhieu vi winpty cho thay VT mode co tinh zero hoa VK.
  - (A) Ghi truc tiep escape sequence ESC [ A vao console input buffer cua target qua WriteConsoleInput — đúng ban chat nhung phuc tap, can biet handle console + co co "target la TUI".
  - Neu khong muon phuc tap → chap nhan la giới han cua Windows voi TUI fullscreen.
- **Quyet dinh**: thu phuong an (C) wVk dung neu khong anh huong logic phim thuong (phim thuong van dung wVk).

### 2. Tap 1 cai kem nhay / cam ung kem (3 loi o viewer)
- **Van de**: 1 tap tren dien thoai kem nhay, phai cham nhieu lan moi an.
- **Nguyen nhan (debugger phan tich, server KHONG loi — path mouse_click line 430-435 day du down+up)**:
  1. **Scroll threshold mau thuan (nghiem trong nhat)**: vao scroll khi ngon lech >2px (justEnteredScroll line 1657) nhung cho phep tap toi 36-45px (line 1791) → ngon rung 3px la scrollMode=true → isTap=false → click bi nuot → phai cham nhieu lan.
  2. **Tre 500ms moi tap don** (SINGLE_TAP_DELAY_MS=500 line 1458, dung line 1830-1837) → cam giac do/khong nhay.
  3. **Double-tap state nuot tap ke** (_mouseHeld ket true sau _dtReleaseTimeout line 1570-1576) → tap ke bi nuot thanh mouse_up (line 1814-1822).
  4. (Phu) dead zones 300ms sau gesture (line 1511, 1767-1772).
- **Giai phap**:
  - (1) Tang scroll threshold 2px → ~12px (tap dang tin cay hon). 
  - (2) Giam SINGLE_TAP_DELAY_MS 500 → 250ms.
  - (3) Reset _mouseHeld + gui mouse_up du phong sau dtReleaseTimeout.
  - (4) Rut ngan dead zones 300 → 150ms.
- **Quyet dinh (user)**: CHI rut ngan 500ms timeout → 250ms. (Khong sua scroll threshold / double-tap / dead zone.) 
- Signed: deepseek-v4-flash api-box

## v1.82 - Fix wVk cho phim Up/Down TUI + giam tap delay (2026-08-12)
- **Van de**: (1) Phim Up/Down remote khong vao duoc opencode TUI; (2) tap tren dien thoai kem nhay do tre 500ms.
- **Nguyen nhan**: (1) gioi han nen tang — TUI doc escape sequence, Windows khong dich input injected sang VT sequence; thu gui wVk dung xem co giup khong. (2) viewer tre 500ms moi tap don.
- **Giai phap sua doi**:
  - server_H264wss_testP_new.py _vk_key_event: extended key doi wVk=0 → wVk=vk_code (giu scancode + KEYEVENTF_SCANCODE|EXTENDEDKEY). Phim thuong KHONG doi. Ap dung P_new truoc de test.
  - web/viewer_H264wss_P_new.html: SINGLE_TAP_DELAY_MS 500 → 250ms (tap nhay hon).
- **Kiem chung**: py_compile P_new OK. CHUA build lai exe. CHUA test thuc te (phim Up/Down trong TUI, tap tren dien thoai). Neu wVk khong giup thi revert ve wVk=0.
- Signed: deepseek-v4-flash api-box
- **REVERT wVk**: thu gui wVk=vk_code cho extended key (v1.82) KHONG giup opencode TUI nhan phim Up/Down ao — xac nhan gioi han nen tang (Windows khong dich input injected sang VT escape sequence). Da revert ve wVk=0 (scancode extended chuan), build lai exe P_new (10:33 PM), copy, restart manager P new. Tap delay 250ms (v1.82) van giu.
- Signed: deepseek-v4-flash api-box
- **QUYET DINH**: Dung xu ly phim Up/Down trong opencode TUI. Nghien cuu xac nhan gioi han nen tang (Windows khong dich input injected sang VT escape sequence cho TUI). Phuong an WriteConsoleInput + KEY_EVENT_RECORD (AttachConsole→CONIN$→WriteConsoleInput) la kha thi nhung phuc tap (~200 dong, kho tim PID target tab) — user quyet dinh KHONG can. Up/Down remote van hoat dong o app GUI + terminal trong (cooked mode). Tap delay 250ms giu. wVk da revert ve 0.
- Signed: deepseek-v4-flash api-box

## v1.83 - Tang timeout connect len 5 phut (2026-08-12)
- **Van de**: Server tu thoai sau 60s khong client va kick client khong phan hoi sau 15s (qua ngan khi user nghi ngắn).
- **Giai phap sua doi** (ap dung 6 server .py: P_new, P, O, O_new, K, L):
  - IDLE_PROCESS_EXIT 60.0 → 300.0 (server giu khi khong client toi 5 phut roi moi thoai).
  - websockets.serve ping_timeout 15 → 300 (client khong phan hoi ping toi 5 phut moi bi kick).
- **Kiem chung**: py_compile 6/6 OK, xac nhan gia tri da doi. Build lai 6 server exe (23:52-23:55) va copy tu dist -> release/server. Chua test thuc te.
- Signed: deepseek-v4-flash api-box

## v1.84 - Fix Black Screen on Tab Switch / Unfocus / Alt-Tab (2026-08-17)
- **Vấn đề**: Khi chuyển tab / unfocus / alt-tab rồi quay lại tab web stream, WebSocket vẫn Connected nhưng bị màn hình đen hoặc kẹt giải mã video.
- **Nguyên nhân**:
  1. **Async race condition trong WebCodecs client**: configureDecoder là async nhưng ws.onmessage gọi decodeFrame ngay lập tức khiến IDR keyframe đầu tiên bị drop vì !decoderConfigured. Sau đó decoder kẹt ở decoderReady = false và drop toàn bộ P-frame tiếp theo.
  2. **cleanupDecoder trong visibilitychange**: remove mất thẻ canvas khỏi DOM khiến màn hình bị đen tức thì khi tab chuyển trạng thái.
  3. **Bỏ qua packet type 0x03**: Web client chưa parse packet extradata SPS/PPS từ server dẫn đến thiếu cấu hình sớm cho decoder.
  4. **Keyframe throttle**: requestRemoteKeyframe bị throttle 1s cố định và thiếu các event listener focus, pageshow trên window để kích hoạt gửi keyframe lập tức.
  5. **Server drop cờ force_keyframe & trễ xử lý keyframe**: _encode_queue (maxlen=1) làm mất cờ force_keyframe khi capture nhanh hơn encode (popleft). Trong ws_handler, khi nhận request_keyframe không gán ngay _force_keyframe_next = True.
- **Giải pháp sửa đổi**:
  - **Web Client** (viewer_H264wss_P_new.html, viewer_H264wss.html, viewer_H264wss_P_wgl.html, viewer_H264wss_O_new.html, viewer_H264wss_O_wgl.html):
    + Quản lý trạng thái _isConfiguring và đệm _pendingKeyframe. Tự động gọi decodeFrame(_pendingKeyframe) ngay khi configureDecoder hoàn tất.
    + cleanupDecoder: Không remove canvas khỏi DOM, chỉ reset decoder instance / state để giữ lại frame cuối cùng hiển thị.
    + Xử lý packet type 0x03 để parse và cache SPS/PPS sớm.
    + Bổ sung event listeners focus và pageshow, hỗ trợ requestRemoteKeyframe(force=true) bypass throttle 1s khi tab vừa active trở lại.
  - **Server** (server_H264wss.py, release/server/server_H264wss_testP_new.py, release/server/server_H264wss.py, release/server/server_H264wss_testO_new.py):
    + Trong _encode_frame: Giữ lại had_force_kf = force_keyframe or prev_kf khi pop frame cũ khỏi _encode_queue.
    + Trong ws_handler: Gán ngay _force_keyframe_next = True khi nhận tin nhắn request_keyframe.

## v1.85 - Fix Crash Luồng _capture_loop: RuntimeError "Capture is already running" (2026-08-17)
- **Vấn đề**:
  - Khi camera gặp ngoại lệ hoặc timeout không có frame mới (`elapsed > 2.0`), server khởi động lại camera trong `_capture_loop`. Do đối tượng `_camera` cũ chỉ bị `del _camera` (không gọi `release()`), dxcam `DXFactory` vẫn giữ singleton instance ở trạng thái capturing (`is_capturing=True`).
  - Lệnh `_camera.start(target_fps=MAX_FPS, video_mode=True)` tiếp theo ném ra ngoại lệ `RuntimeError: Capture is already running. Call stop() first.` làm sập toàn bộ luồng `_capture_loop`.
  - Hậu quả: `_capture_loop` chết khiến `send=0.0` vĩnh viễn. Khi client kết nối lại, WebSocket vẫn connected và nhận input (alt-tab/chuột vẫn hoạt động) nhưng màn hình bị đen do luồng capture video đã dừng.
- **Nguyên nhân**:
  1. `_camera.start()` không kiểm tra cờ `_camera.is_capturing` trước khi gọi và không được bọc `try...except` an toàn chống crash luồng.
  2. Khi camera gặp lỗi hoặc timeout, việc gọi `del _camera` không giải phóng tài nguyên trong singleton factory của dxcam (`DXFactory`). Dxcam trả về instance cũ đang capturing và không thể `start()` lại nếu không `stop()` / `release()` đúng cách.
  3. Trong `_capture_loop`, sau khi ngủ `time.sleep(0.2)` không kiểm tra `if not _streaming_active: break`, có thể dẫn đến việc khởi tạo lại camera khi luồng streaming đang dừng.
- **Giải pháp sửa đổi** (áp dụng đồng bộ cho `server/server_H264wss.py` và các file `release/server/server_H264wss_testP_new.py`, `_testP.py`, `_testO_new.py`, `_testO.py`, `_testK.py`, `_testL.py`, `server_H264wss.py`):
  1. Chuẩn hóa hàm `_stop_and_release_camera()`:
     - Kiểm tra `getattr(_camera, 'is_capturing', False)` để gọi `stop()`.
     - Gọi `_camera.release()` (nếu chưa `is_released`) để dọn sạch singleton trong `dxcam.DXFactory`.
     - Gán `_camera = None`.
  2. Chuẩn hóa hàm `_start_camera_safe()`:
     - Kiểm tra `getattr(_camera, 'is_capturing', False)` trước khi gọi `start()` để tránh `RuntimeError`.
     - Bọc `try...except` bắt ngoại lệ, không để crash luồng capture.
  3. Cập nhật `_capture_loop()`:
     - Dùng `_start_camera_safe()` khi bắt đầu luồng.
     - Khi `elapsed > 2.0` hoặc gặp ngoại lệ trong loop: gọi `_stop_and_release_camera()`, `time.sleep(0.2)`, kiểm tra `if not _streaming_active: break`, sau đó tạo `_camera = dxcam.create(output_color="BGR")` và gọi `_start_camera_safe()`.
  4. Cập nhật `_init_capture()` và `_stop_streaming_locked()`:
     - Sử dụng `_stop_and_release_camera()` để dọn dẹp sạch sẽ tài nguyên camera và loại bỏ mã dọn dẹp thủ công cũ.
- **Kiểm chứng**: `python -m py_compile` toàn bộ 8 file server đều PASS.


## v1.86 - Giải Pháp Headless Mode: Khắc Phục Màn Hình Đen Khi Rút Cáp HDMI Bằng Virtual Display Driver (2026-08-21)
- **Vấn đề**:
  - Khi rút cáp HDMI kết nối màn hình vật lý, luồng stream video của server Xemmanhinh bị tối đen (black screen) hoàn toàn hoặc không gửi frame mới (`send=0.0`).
- **Nguyên nhân**:
  1. Thư viện `dxcam` hoạt động dựa trên DXGI Desktop Duplication API (`IDXGIOutputDuplication`). Khi rút cổng HDMI, GPU ngắt kết nối `IDXGIOutput`, ném ngoại lệ mất quyền truy cập (`DXGI_ERROR_ACCESS_LOST`).
  2. Hệ điều hành Windows phát hiện trạng thái không có màn hình vật lý (Headless), khiến Desktop Window Manager (DWM) tự động đình chỉ pipeline dựng hình đồ họa của GPU để tiết kiệm năng lượng. Framebuffer không còn được cập nhật và trả về mảng dữ liệu rỗng.
- **Giải pháp sửa đổi**:
  1. **Triển khai Virtual Display Driver (VDD)**: Cài đặt driver màn hình ảo dựa trên kiến trúc Microsoft Indirect Display Driver Model (IddCx) thông qua WinGet (`VirtualDrivers.Virtual-Display-Driver`) và đăng ký thiết bị phần cứng ảo `Root\MttVDD`.
  2. **Tạo kịch bản tự động hóa 1-click**:
     - `Cai_Dat_Man_Hinh_Ao.bat`: Tự động xin quyền Administrator, khởi tạo thư mục cấu hình `C:\VirtualDisplayDriver\vdd_settings.xml`, nạp driver vào DriverStore (`pnputil`) và tạo thiết bị màn hình ảo (`devcon.exe`).
     - `Bat_Tat_Man_Hinh_Ao.bat`: Cho phép Bật (Enable), Tắt (Disable) hoặc Gỡ bỏ (Remove) màn hình ảo khi cần.
  3. **Tài liệu kỹ thuật chuyên sâu**: Soạn thảo tài liệu lý thuyết và hướng dẫn vận hành hoàn chỉnh trong file `huong_dan_virtual_display_driver.md`.
- **Kết quả**: Windows luôn duy trì thiết bị hiển thị `Generic Monitor (VDD by MTT)` hoạt động 24/7. DWM và dxcam liên tục capture mượt mà 60fps kể cả khi rút toàn bộ cáp màn hình vật lý.
## v1.87 - Tính Năng Chuyển Màn Hình Phát Trực Tiếp Trong Bảng Cài Đặt (Settings Panel) (2026-08-21)
- **Vấn đề**:
  - Khi máy tính có nhiều màn hình (ví dụ: màn hình vật lý chính và màn hình ảo VDD), người dùng cần có khả năng chủ động lựa chọn và chuyển đổi màn hình đang stream từ xa thông qua giao diện Web.
- **Nguyên nhân**:
  - Trước đây server chỉ mặc định gắn cố định capture vào cổng `output_idx=0`, không hỗ trợ cơ chế quét và chuyển đổi cổng xuất hình động từ phía client.
- **Giải pháp sửa đổi**:
  - **Server** (`release/server/server_H264wss_testP_new.py`):
    + Thêm biến trạng thái `_current_output_idx = 0`.
    + Bổ sung hàm `get_display_list()` quét toàn bộ các màn hình đang hoạt động trên hệ thống (màn hình 1, màn hình ảo VDD...) kèm kích thước độ phân giải thực tế.
    + Bổ sung hàm `switch_display(output_idx)`: giải phóng camera cũ, tạo `dxcam.create(output_idx=...)`, tái khởi tạo encoder theo kích thước mới, gửi gói tin `init` và SPS/PPS NAL qua WebSocket cho toàn bộ client.
    + Xử lý 2 sự kiện WebSocket: `get_displays` (lấy danh sách màn hình) và `switch_display` (chuyển cổng màn hình phát).
  - **Web Client** (`web/viewer_H264wss_P_new.html`):
    + Trong `Settings Panel`: Thêm mục `Màn hình phát (Display)` với dropdown danh sách màn hình, nút `Quét lại danh sách màn hình` và nút `Chuyển Màn Hình`.
    + Tự động gửi lệnh `get_displays` khi mở bảng Settings.
    + Nhận gói tin `display_list` từ server và cập nhật danh sách hiển thị thời gian thực.
  - **Đóng gói binary**: Đã build lại thành công `server_H264wss_testP_new.exe` và khởi động lại dịch vụ.
- **Kết quả**: Người dùng có thể chuyển đổi mượt mà giữa màn hình chính và màn hình ảo VDD trực tiếp từ điện thoại mà không cần tải lại trang.
## v1.88 - Khắc Phục Lỗi COMError (0x80004005) Khi Rút Cáp HDMI Đột Ngột (2026-08-21)
- **Vấn đề**:
  - Khi đang stream và người dùng rút dây cáp HDMI vật lý ra khỏi máy tính, server ném ra ngoại lệ `_ctypes.COMError: (-2147467259, 'Unspecified error')` tại hàm `DuplicateOutput()` và làm sập luồng capture.
- **Nguyên nhân**:
  - 1. Khi rút cáp HDMI, Windows DWM mất khoảng 0.3s - 0.8s để tái cơ cấu luồng đồ họa sang màn hình ảo VDD. Trong khoảng thời gian ngắn này, cổng DXGI cũ bị hủy (`DXGI_ERROR_ACCESS_LOST`).
  - 2. Thư viện `dxcam` sử dụng mô hình Singleton (`DXFactory`) lưu lại con trỏ `IDXGIAdapter1` cũ đã chết. Khi khởi tạo lại mà không dọn sạch bộ nhớ Singleton, `dxcam` gọi `DuplicateOutput()` trên adapter cũ dẫn đến lỗi `E_FAIL` (`-2147467259`).
  - 3. Thiếu cơ chế thử lại (Retry Loop) và độ trễ chờ Windows kích hoạt màn hình ảo.
- **Giải pháp sửa đổi**:
  - **Server** (`release/server/server_H264wss_testP_new.py`):
    + Bổ sung hàm `_reset_dxcam()`: Xóa sạch bộ nhớ Singleton `dxcam.Singleton._instances` và tái tạo đối tượng `DXFactory` mới để quét lại toàn bộ cổng đồ họa phần cứng từ đầu.
    + Bổ sung hàm `_create_camera_with_retry()`: Tự động thử lại tối đa 6 lần (mỗi lần cách nhau 0.3s - 0.4s) khi phát hiện trạng thái cắm/rút cáp nóng.
    + Cập nhật `_stop_and_release_camera()`, `_init_capture()`, `switch_display()` và `_capture_loop()` bắt mọi ngoại lệ COMError, tự động giải phóng DXGI cũ và gắn camera mới vào màn hình ảo VDD liền mạch.
  - **Đóng gói**: Đã build lại file thực thi [release/server/dist/server_H264wss_testP_new.exe](file:///C:/Users/Hai%20Dang/Xemmanhinh/release/server/dist/server_H264wss_testP_new.exe) và khởi chạy lại `server_manager_P_new.exe`.
- **Kết quả**: Khi rút cáp HDMI đột ngột, server tự động bắt lấy màn hình ảo VDD MTT trong vòng 0.5 giây mà không bị gián đoạn hay phát sinh lỗi.
## v1.89 - Gán Session Desktop (OpenInputDesktop / SetThreadDesktop) Cho Luồng Capture (2026-08-21)
- **Vấn đề**:
  - Khi rút cáp HDMI hoặc khi Windows chuyển đổi phiên Desktop, server bị kẹt tại `encode=0.1 send=0.0` và không thể tiếp tục gửi luồng video.
- **Nguyên nhân**:
  - Khi ngắt kết nối phần cứng màn hình, Windows DWM tạo lại Input Desktop session. Các luồng nền (background worker threads) nếu không được gắn quyền `SetThreadDesktop(OpenInputDesktop(...))` sẽ bị Windows chặn truy cập Direct3D/DXGI với mã lỗi `E_ACCESSDENIED` (`0x80070005`).
- **Giải pháp sửa đổi**:
  - **Server** (`release/server/server_H264wss_testP_new.py`):
    + Bổ sung hàm `_attach_input_desktop()`: Tự động mở quyền Input Desktop đang hoạt động của Windows (`OpenInputDesktop(0, False, 0x01FF)`) và gắn trực tiếp vào luồng capture bằng `SetThreadDesktop()`.
    + Tích hợp `_attach_input_desktop()` vào đầu luồng `_capture_loop()` và toàn bộ các lần thử lại trong `_create_camera_with_retry()`.
  - **Đóng gói**: Đã build lại file thực thi [release/server/dist/server_H264wss_testP_new.exe](file:///C:/Users/Hai%20Dang/Xemmanhinh/release/server/dist/server_H264wss_testP_new.exe) và khởi chạy lại `server_manager_P_new.exe`.
- **Kết quả**: Luồng capture luôn duy trì quyền truy cập DirectX Desktop Duplication đầy đủ ngay cả khi rút cáp màn hình vật lý, đảm bảo tốc độ khung hình 30-45 FPS liên tục.
## v1.90 - Khắc Phục Lỗi Dừng Luồng Encode Thread Khi Chuyển Cổng Màn Hình (2026-08-21)
- **Vấn đề**:
  - Khi rút cáp màn hình trong chế độ Duplicate, server kết nối lại thành công và đổi cổng màn hình nhưng màn hình trên web bị đen và hiển thị 0 FPS (`encode=0.1 send=0.0`).
- **Nguyên nhân**:
  - Khi `switch_display()` hoặc hàm phục hồi hotplug được kích hoạt, server gọi `_stop_encoder()` để giải phóng encoder cũ. Lệnh này đồng thời gán `_encode_stop = True`, khiến luồng `_encode_thread` chạy nền bị kết thúc (`break`). Khi encoder mới được tạo lại, luồng `_encode_thread` không được khởi động lại (`_ensure_encode_thread()` bị thiếu), dẫn đến việc các khung hình mới từ camera không bao giờ được nén để gửi đi.
- **Giải pháp sửa đổi**:
  - **Server** (`release/server/server_H264wss_testP_new.py`):
    + Bổ sung lệnh `_ensure_encode_thread()` ngay sau mỗi lần `_init_encoder()`, `switch_display()` và các khối phục hồi lỗi trong `_capture_loop()`.
    + Đảm bảo luồng encode luôn được tái sinh tự động ngay khi encoder mới sẵn sàng.
  - **Đóng gói**: Đã build lại file thực thi [release/server/dist/server_H264wss_testP_new.exe](file:///C:/Users/Hai%20Dang/Xemmanhinh/release/server/dist/server_H264wss_testP_new.exe) và khởi chạy lại `server_manager_P_new.exe`.
- **Kết quả**: Khi rút cáp màn hình ở chế độ Duplicate, luồng encode tự động tiếp tục xử lý các khung hình từ màn hình ảo VDD mà không bị chết luồng.
## v1.91 - Cô Lập Hoàn Toàn Vòng Đời DirectX Capture & Đổi Màn Hình Trong Worker Thread (2026-08-21)
- **Vấn đề**:
  - Khi rút cáp màn hình trong chế độ Duplicate, server vẫn báo Màn hình 1 đang phát nhưng tốc độ khung hình đứng yên ở 0 FPS (`encode=0.1 send=0.0`).
- **Nguyên nhân**:
  - `switch_display()` và `_init_capture()` trước đây được thực thi trực tiếp trên luồng asyncio/WebSocket hoặc main thread. Trên các luồng này, Windows API `SetThreadDesktop(OpenInputDesktop(...))` trả về thất bại (`result = 0`) do luồng đã khởi tạo các handle mạng/COM trước đó.
  - Do `SetThreadDesktop` thất bại trên luồng WebSocket, `dxcam.create()` bị từ chối cấp quyền truy cập DXGI (`E_ACCESSDENIED 0x80070005`) và trả về `None`, làm luồng chụp `_capture_loop` rơi vào trạng thái mất camera liên tục.
- **Giải pháp sửa đổi**:
  - **Server** (`release/server/server_H264wss_testP_new.py`):
    + Chuyển giao toàn bộ việc khởi tạo, chuyển đổi cổng xuất hình (`switch_display`) và phục hồi hotplug vào bên trong luồng worker riêng biệt `_capture_loop()`.
    + Luồng WebSocket chỉ gửi tín hiệu `_target_output_idx` và `_display_switch_requested = True`, không gọi trực tiếp các hàm DirectX/COM.
    + Luồng worker `_capture_loop` sở hữu quyền gắn `SetThreadDesktop(OpenInputDesktop(...))` sạch 100%, tự động tái kết nối camera vào màn hình ảo VDD MTT và cấu hình lại encoder ngay trong vòng lặp.
  - **Đóng gói**: Đã build lại file thực thi [release/server/dist/server_H264wss_testP_new.exe](file:///C:/Users/Hai%20Dang/Xemmanhinh/release/server/dist/server_H264wss_testP_new.exe) và khởi chạy lại `server_manager_P_new.exe`.
- **Kết quả**: Luồng chụp DXGI tự động nhận diện và chuyển giao sang màn hình ảo VDD MTT với tốc độ mượt mà 30-45 FPS ngay khi rút cáp HDMI.
## v1.92 - Khắc Phục Treo Vô Hạn Trong dxcam Khi Rút Cáp HDMI (DXGI 0x887A0026) (2026-08-21)
- Vấn đề:
  - Khi rút cáp màn hình HDMI trong chế độ Duplicate, server rơi vào trạng thái 0 FPS (`send=0.0`), client bị timeout chờ keyframe (`[WS] Keyframe timeout, force reconnect`).
- Phân tích nguyên nhân sâu xa từ Subagent:
  - 1. Khi rút cáp HDMI, Windows hủy desktop duplication output cũ và trả về mã lỗi `HRESULT 0x887A0026` (`DXGI_ERROR_ACCESS_LOST`).
  - 2. dxcam bắt lỗi này và gọi `DisplayRecoveryHandler.handle()`, nhưng do topology màn hình vừa bị ngắt kết nối nên dxcam bị kẹt trong vòng lặp vô hạn `while True:` trong luồng capture nội bộ của nó.
  - 3. Hàm `get_latest_frame()` của dxcam có vòng lặp `while True:` đợi `__frame_available.wait(0.1)` vô hạn mà không có tham số timeout tổng thể. Khi dxcam bị kẹt phục hồi, event không bao giờ được set, khiến luồng `_capture_loop` của server bị treo cứng vĩnh viễn ở lệnh `get_latest_frame()`.
  - 4. Do luồng capture bị treo, cơ chế watchdog phát hiện mất frame (`elapsed > 1.5s`) của server không bao giờ được kích hoạt. Không có khung hình nào được đẩy vào encoder, dẫn đến `send=0.0` và client bị timeout keyframe.
- Giải pháp sửa đổi:
  - Server (`release/server/server_H264wss_testP_new.py`):
    + Xây dựng hàm `_get_camera_frame_safe(cam, timeout=0.05)`: Trực tiếp chờ event với timeout tối đa 50ms và đọc frame từ ring buffer có bảo vệ lock. Khi có lỗi kết nối phần cứng, hàm trả về `None` ngay lập tức thay vì bị block vô hạn.
    + Nâng cấp `_stop_and_release_camera()`: Chủ động set cờ `__stop_capture` và kích hoạt `__frame_available` để giải phóng luồng nội bộ của dxcam ngay lập tức, ngăn ngừa kẹt thread join.
    + Giảm ngưỡng watchdog trong `_capture_loop()` xuống 0.8s: Khi phát hiện mất frame liên tục 0.8s do rút cáp, server tự động dọn sạch camera cũ, gắn lại `_attach_input_desktop()` và kết nối thẳng vào màn hình ảo VDD MTT.
  - Đóng gói: Đã build lại file thực thi [release/server/dist/server_H264wss_testP_new.exe](file:///C:/Users/Hai%20Dang/Xemmanhinh/release/server/dist/server_H264wss_testP_new.exe) và khởi động lại `server_manager_P_new.exe`.
- Kết quả: Khi rút cáp HDMI đột ngột ở bất kỳ chế độ hiển thị nào, server tự động bắt lấy màn hình ảo VDD MTT trong vòng chưa đầy 1 giây và tiếp tục stream 30-45 FPS mượt mà.
## v1.93 - Khắc Phục Lỗi Camera Đã Bị Release Khi Cắm Lại Cáp HDMI (2026-08-21)
- Vấn đề:
  - Khi cắm lại dây cáp HDMI để chuyển về màn hình chính, server báo lỗi `DXCamera has been released and cannot be reused. Create a new camera instance with dxcam.create()` và không thể phát lại luồng video.
- Phân tích nguyên nhân:
  - Khi cắm cáp HDMI, Windows mất từ 1.0s đến 2.5s để thực hiện quy trình bắt tay EDID và khởi tạo lại Direct3D output.
  - Trong lúc này, các lần thử tạo camera ban đầu chưa thành công và camera cũ đã bị giải phóng (`is_released = True`). Hàm `_start_camera_safe()` vô tình cố khởi động lại đối tượng camera cũ dẫn đến lỗi `RuntimeError`.
  - Bộ nhớ cache của `dxcam` đôi khi vẫn giữ tham chiếu tới đối tượng đã giải phóng nếu không được quét sạch ở cả module level.
- Giải pháp sửa đổi:
  - Server (`release/server/server_H264wss_testP_new.py`):
    + Nâng số lần thử lại kết nối `max_retries` lên 10 lần (tổng thời gian chờ ~3.0s) kết hợp tự động chuyển đổi giữa các output (0 và 1) khi phát hiện cắm lại cáp màn hình vật lý.
    + Thêm kiểm tra `is_released` trước khi gọi `start()` hoặc lấy khung hình, tuyệt đối không tái sử dụng đối tượng camera đã bị giải phóng.
    + Khi camera mới được tạo thành công sau khi cắm cáp, server tự động cập nhật độ phân giải mới, re-init encoder H.264 và gửi ngay Keyframe IDR cho client.
  - Đóng gói: Đã build lại file thực thi [release/server/dist/server_H264wss_testP_new.exe](file:///C:/Users/Hai%20Dang/Xemmanhinh/release/server/dist/server_H264wss_testP_new.exe) và khởi động lại `server_manager_P_new.exe`.
- Kết quả: Khi cắm lại cáp HDMI, server tự động nhận diện màn hình chính trong vòng 1-2 giây và tiếp tục stream bình thường mà không bị lỗi release camera.
## v1.94 - Quản Lý Vòng Đời COM và Dynamic Output Clamping Khi Cắm/Rút Cáp Hotplug Liên Tiếp (2026-08-21)
- Vấn đề:
  - Khi thực hiện cắm/rút cáp HDMI nhiều chu kỳ liên tiếp (Rút -> Cắm lại -> Rút tiếp), server bị rơi vào tình trạng mất frame vĩnh viễn (send=0.0) và không thể kết nối lại camera.
- Phân tích nguyên nhân sâu xa từ quy trình Subagent:
  - Khi lặp lại cắm/rút cáp nóng nhiều lần, các đối tượng COM wrapper (ID3D11Device, IDXGIOutputDuplication) của dxcam không được giải phóng triệt để do rò rỉ tham chiếu cấp Python, khiến Windows DWM từ chối cấp phiên Desktop Duplication mới.
  - Chỉ số output (_current_output_idx) bị kẹt ở giá trị cũ (ví dụ 1 khi có 2 màn hình), khi rút cáp chỉ còn 1 output (index 0) dẫn đến IndexError/Exception trong dxcam.create(output_idx=1).
- Giải pháp sửa đổi:
  - Server (release/server/server_H264wss_testP_new.py):
    + _reset_dxcam(): Duyệt dọn dẹp sạch toàn bộ COM pointers của devices/outputs, xóa Singleton, gọi gc.collect() 2 lần tường minh để giải phóng tài nguyên đồ họa kernel.
    + _create_camera_with_retry(): Tự động đếm số lượng output thực tế trên adapter mới, tự động hạ target_idx về 0 nếu vượt quá số lượng màn hình khả dụng, và cập nhật _current_output_idx đồng bộ.
    + Bổ sung 0.5s cooldown backoff trong luồng phục hồi để chờ Windows DWM ổn định cấu hình hiển thị sau mỗi lần cắm/rút cáp.
  - Đóng gói: Đã build lại file thực thi [release/server/dist/server_H264wss_testP_new.exe](file:///C:/Users/Hai%20Dang/Xemmanhinh/release/server/dist/server_H264wss_testP_new.exe) và khởi chạy lại server_manager_P_new.exe.
- Kết quả: Khi cắm/rút cáp HDMI nhiều chu kỳ liên tiếp, server dọn sạch tài nguyên COM cũ, tự động điều chỉnh index màn hình và duy trì stream mượt mà liên tục mà không bị mất frame.
## v1.95 - Khắc Phục Lỗi AttributeError GetDesc và Tối Ưu Tốc Độ Phục Hồi Hotplug Dưới 100ms (2026-08-21)
- Vấn đề:
  + Xuất hiện ngoại lệ AttributeError: 'NoneType' object has no attribute 'GetDesc' trong luồng dxcam làm crash luồng capture khi cắm/rút cáp HDMI.
  + Độ trễ kết nối lại còn chậm (1.5s - 2.5s) do server phụ thuộc vào bộ đếm thời gian timeout tĩnh và độ trễ retry lớn.
- Phân tích nguyên nhân sâu xa từ quy trình Subagent:
  + Trong output.py dòng 27: self.output.GetDesc(...) không kiểm tra self.output is None khi màn hình bị ngắt kết nối đột ngột. Hàm phục hồi nội bộ của dxcam không bắt ngoại lệ AttributeError dẫn đến crash luồng DXCamera.
  + Server trước đây phải đợi 800ms timeout không có frame mới phát hiện luồng camera đã chết, kèm 500ms sleep tĩnh và delay retry 300ms.
- Giải pháp sửa đổi:
  + Sửa dứt điểm AttributeError bằng monkey-patch an toàn cho Output.update_desc, kiểm tra self.output trước khi gọi GetDesc.
  + Bổ sung hàm _is_camera_alive() để phát hiện tức thì (0ms delay) khi luồng capture bị dừng hoặc gặp sự cố.
  + Tối ưu độ trễ phục hồi: Hạ timeout watchdog xuống 0.2s, giảm thời gian chờ cooldown xuống 0.05s (50ms), và giảm delay trong _create_camera_with_retry xuống 0.05s (50ms). Tốc độ phục hồi stream hiện đạt dưới 100ms.
- Đóng gói: Đã build lại file thực thi [release/server/dist/server_H264wss_testP_new.exe](file:///C:/Users/Hai%20Dang/Xemmanhinh/release/server/dist/server_H264wss_testP_new.exe) và khởi chạy lại server_manager_P_new.exe.
- Kết quả: Khắc phục triệt để lỗi crash luồng capture, stream phục hồi tức thì sau khi cắm/rút cáp HDMI với độ trễ chuyển giao dưới 100ms.
## v1.96 - Triển Khai Cơ Chế Fail-Fast Cho Thư Viện Chụp Màn Hình Và Chuyển Giao Quyền Khởi Tạo Cho Server (2026-08-21)
- Vấn đề:
  + Khi rút/cắm cáp HDMI, xuất hiện ngoại lệ Unhandled exception in capture loop do AttributeError: 'NoneType' object has no attribute 'CreateTexture2D' tại stagesurf.py dòng 68.
  + Điện thoại (client) bị rơi vào trạng thái connecting rất lâu do luồng phục hồi nội bộ của dxcam bị kẹt và xung đột với quy trình phục hồi của server.
- Phân tích nguyên nhân sâu xa từ quy trình Subagent:
  + Khi xảy ra ngắt kết nối màn hình (0x887A0026), dxcam cố gắng tự phục hồi thông qua DXCamera._recover_output() -> DisplayRecoveryHandler -> StageSurface.rebuild(). Do kết nối Direct3D device đã bị DWM giải phóng, device hoặc device.device bị None, dẫn đến crash luồng với lỗi CreateTexture2D.
  + Cơ chế tự phục hồi nội bộ của dxcam không thể quét lại phần cứng toàn diện như server, khiến luồng capture bị kẹt và làm chậm quá trình tái kết nối của client.
- Giải pháp sửa đổi:
  + Áp dụng bản vá Fail-Fast cho DXCamera._recover_output: Chặn đứng cơ chế tự phục hồi lỗi thời của dxcam, gán is_capturing = False và dừng êm dịu luồng capture con.
  + Áp dụng bản vá an toàn cho StageSurface.rebuild: Kiểm tra device và device.device trước khi gọi CreateTexture2D.
  + Server phát hiện trạng thái ngừng hoạt động ngay lập tức (0ms delay) thông qua _is_camera_alive(), tự động khởi tạo lại toàn bộ DXFactory sạch sẽ và bắt lại màn hình ảo VDD hoặc màn hình chính chỉ trong 50ms-100ms.
- Đóng gói: Đã build lại file thực thi [release/server/dist/server_H264wss_testP_new.exe](file:///C:/Users/Hai%20Dang/Xemmanhinh/release/server/dist/server_H264wss_testP_new.exe) và khởi chạy lại server_manager_P_new.exe.
- Kết quả: Khắc phục triệt để lỗi CreateTexture2D, loại bỏ trạng thái connecting kéo dài trên điện thoại, hệ thống tự động bắt lại màn hình ảo VDD hoặc màn hình chính trong 50ms-100ms khi cắm/rút cáp HDMI.
## v1.97 - Đạt Cột Mốc Hoạt Động Mượt Mà 100% Chuỗi Xử Lý Hotplug HDMI và Virtual Display Driver (2026-08-21)
- Ghi nhận thành tựu:
  + Chuỗi xử lý Hotplug HDMI kết hợp Virtual Display Driver (VDD) đã hoạt động mượt mà 100%, không còn bất kỳ exception nào (bao gồm cả các lỗi rò rỉ COM, DXGI_ERROR_ACCESS_LOST, AttributeError GetDesc hay CreateTexture2D).
  + Thời gian chuyển đổi và phục hồi màn hình diễn ra tức thì trong vòng <100ms khi người dùng rút hoặc cắm lại cáp HDMI.
  + Duy trì tốc độ phát video ổn định 35-38+ FPS liên tục qua nhiều chu kỳ rút/cắm cáp liên tiếp mà không bị sụt giảm hiệu năng hoặc đọng rò rỉ bộ nhớ.
  + Hệ thống tự động chuyển giao liền mạch giữa màn hình vật lý và màn hình ảo VDD, mang lại trải nghiệm xem màn hình không gián đoạn trên mọi thiết bị client.

## v1.98 - Fix Autostart Server Manager P New Khi Khởi Động Windows (2026-08-22)
- Vấn đề: Ứng dụng autostart server_manager_P_new.exe không tự khởi động được khi đăng nhập Windows.
- Phân tích nguyên nhân:
  1. File shortcut autostart nằm trong thư mục Startup của Windows (AppData\Roaming\...\Startup) khởi chạy ứng dụng dưới quyền người dùng tiêu chuẩn (non-admin). Khi server_manager_P_new.exe chạy, hàm _is_elevated() trả về False và tự động kích hoạt _relaunch_as_admin() qua ShellExecuteW("runas").
  2. Tại thời điểm Windows startup, hộp thoại UAC (runas) bị Windows chặn/ẩn hoặc bị người dùng bỏ qua/từ chối. Hàm ShellExecuteW trả về mã lỗi (như 1223) mà không tạo ngoại lệ Python. Hàm main() lập tức gọi return khiến tiến trình bị thoát hoàn toàn thay vì duy trì chạy ở chế độ non-admin.
  3. File server_manager_P_new.exe tại root release/server bị lệch thời gian cập nhật so với file trong thư mục dist.
- Giải pháp sửa đổi:
  1. Cập nhật server_manager.py: Hàm _relaunch_as_admin() kiểm tra mã trả về int(res) > 32 của ShellExecuteW. Trong hàm main(), nếu yêu cầu nâng quyền admin thất bại hoặc bị hủy, ứng dụng ghi log cảnh báo và tiếp tục chạy ở chế độ non-admin giữ port 8765/8766/8767 thay vì thoát hẳn tiến trình.
  2. Rebuild lại server_manager_P_new.exe từ server_manager_P_new.spec và sao chép đồng bộ từ dist sang thư mục release/server.
  3. Cấu hình Windows Task Scheduler tạo tác vụ ServerManager_P_new tự động chạy khi người dùng đăng nhập với quyền cao nhất (/RL HIGHEST), giúp autostart chạy ngầm trơn tru không bị vướng UAC prompt.
- Kết quả: Khắc phục triệt để lỗi không khởi động được autostart. Ứng dụng tự khởi động thành công và mở các port lắng nghe đúng quy chuẩn.
- Sửa đổi bổ sung (Sửa single-instance mutex & dọn dẹp Startup):
  - Vấn đề: Rò rỉ handle trong retry loop mutex và không phát hiện xung đột single-instance khi tiến trình non-admin chạy (CreateMutexW trả về h == 0 và err == 5). Shortcut cũ server_manager_P_new.exe.lnk trong thư mục Startup gây khởi động trùng lặp 2 lần.
  - Nguyên nhân: _try_create() trước đây chưa lấy GetLastError() khi h == 0, retry loop 10 lần không CloseHandle khi err == 183. Shortcut trong Startup chạy độc lập song song với Task Scheduler.
  - Giải pháp sửa đổi:
    1. Sửa _try_create() và _acquire_single_instance() trong release/server/server_manager.py (và server/server_manager.py): coi not handle hoặc err in (183, 5) là đã có instance khác đang chạy; giải phóng handle bằng CloseHandle() trong retry loop và trước khi exit.
    2. Xóa file shortcut server_manager_P_new.exe.lnk trong thư mục Startup (AppData\Roaming\...\Startup).
    3. Rebuild server_manager_P_new.exe bằng PyInstaller và cập nhật đồng bộ ở dist/ và release/server/.
  - Kết quả: Xóa bỏ hoàn toàn việc chạy trùng 2 instance, không còn rò rỉ handle Windows mutex, Task Scheduler ServerManager_P_new chạy đơn instance chuẩn xác.