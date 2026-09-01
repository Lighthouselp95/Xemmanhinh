# Phân tích luồng Stream & WebSocket (server P new)

- Ngày: 2026-08-12
- Ký: deepseek-v4-flash api-box
- File chính: `server_H264wss_testP_new.py`, `server_manager.py`, `viewer_H264wss_P_new.html`
- Số dòng tham chiếu theo trạng thái hiện tại.

## A. Luồng khởi động server (`server_H264wss_testP_new.py`)

1. `if __name__ == "__main__":` (L2207) → `main()` (L2196).
2. `main()` (L2196): bọc `_run_server()` trong try/except (KeyboardInterrupt L2200, Exception L2201-2204).
3. `_run_server()` (L2117):
   - `_check_dependencies()` (L2087) kiểm tra dxcam/numpy/websockets/av/cv2; thiếu → `sys.exit(1)` (L2118-2119).
   - `timeBeginPeriod(1)` cho timer 1ms (L2124).
   - reconfigure stdout/stderr UTF-8 (L2129-2132).
   - In banner (L2134-2145).
   - `enc_name = _pick_encoder()` (L2138) — chọn NVENC→QSV→AMF→libx264 (hàm L503).
   - `threading.Thread(target=start_http_server, daemon=True).start()` (L2147) — HTTP server thread riêng.
   - `ssl_ctx_ws = _make_ssl_context()` và `ssl_ctx_audio = _make_ssl_context()` (L2150-2151); `_make_ssl_context()` (L219) load cert.pem/key.pem.
   - Định nghĩa `async def run()` (L2153).
   - Định nghĩa `_loop_exception_handler(loop, context)` (L2174): nếu OSError winerror=64 → `os._exit(1)` để manager respawn (L2176-2181).
   - `loop = asyncio.new_event_loop()` (L2184), `loop.set_exception_handler(...)` (L2185), `asyncio.set_event_loop` (L2186), `loop.run_until_complete(run())` (L2188), finally `loop.close()` (L2191).
4. `run()` (L2153):
   - `websockets.serve(ws_handler, HOST, WS_PORT, max_size=10MB, ping_interval=10, ping_timeout=15, ssl=ssl_ctx_ws)` (L2154-2158) — WS video 8766.
   - `websockets.serve(audio_ws_handler, HOST, WS_AUDIO_PORT, ..., ssl=ssl_ctx_audio)` (L2159-2164) — WS audio 8767.
   - In "[WSS] Video/Control" + "[WSS] Audio" (L2165-2166).
   - `_schedule_idle_exit()` (L2168) — khởi thread idle-exit monitor.
   - `await stream_loop()` (L2169) — vòng lặp gửi chính (xem E).

## B. Manager (`server_manager.py`)

1. `main()` (L261): tự nâng admin nếu chưa (L264-267), `_acquire_single_instance()` (L268), `_kill_stale_servers()` (L270), `evt, released = _hold_ports()` (L272).
2. `_hold_ports()` (L148): tạo `evt = threading.Event()`, `_released_ports = {port: threading.Event() for port in PORTS}` (L152-155). Spawn 3 thread `_port_listener` (L204-208) cho PORTS = (8765, 8766, 8767) (L53).
3. `_port_listener(port)` (L157):
   - Lặp `while not _stop`: nếu `_server_alive() or _spawn_pending` thì sleep 0.3 và bỏ qua (L161-163).
   - `_released_ports[port].clear()` (L164), tạo socket (L165).
   - `srv.setsockopt(SOL_SOCKET, SO_EXCLUSIVEADDRUSE, 1)` (L172) — ngăn double-bind.
   - `srv.bind((HOST, port))`; `srv.listen(8)`; `srv.settimeout(0.5)` (L176-178).
   - Vòng trong `while not _stop and not _server_alive() and not _spawn_pending` (L184): `conn, addr = srv.accept()` (L186), `conn.close()` (L187 — chỉ cần biết có ai muốn nối), `evt.set()` (L188), `_spawn_pending = True` (L191), log connect request (L192), break.
   - `finally:` `srv.close()` nhả port (L199), `_released_ports[port].set()` báo đã release (L200).
4. `spawn_server()` (L108):
   - `with _server_lock:` (L111); nếu `_server_alive()` return (L112); check `now - _last_spawn < MIN_SPAWN_GAP(2.0)` return (L114-116); `_last_spawn = now` (L117); `_spawn_pending = True` (L118); `_kill_stale_servers()` (L119).
   - `for p in PORTS: _released_ports[p].wait(timeout=3.0)` (L122-123) — chờ CẢ 3 port nhả hẳn.
   - Popen server con: FROZEN → `[SERVER_EXE]` (L128-133); else `[sys.executable, "-u", "-X", "utf8", SERVER_SCRIPT]` (L135-140). Lỗi → `server_proc=None`, `_spawn_pending=False` (L142-145).
5. Main loop của `main()` (L275-293):
   - `if evt.wait(timeout=0.5)` → `evt.clear()` + `spawn_server()` (L276-279).
   - `rc = server_proc.poll()` (L282); nếu `rc is not None`: set `server_proc=None`, `_spawn_pending=False` (L285-288); nếu `rc != 0` → log crash + `time.sleep(3)` + `spawn_server()` (L289-292).
   - `time.sleep(0.2)` (L293).

## C. Luồng client kết nối (`ws_handler` video, L1761)

1. Lấy IP: `client_ip = addr[0]` (L1763-1764).
2. Claim và kick WS cũ (L1770-1774): `_old_ws = _ip_to_ws.get(client_ip)`; `_ip_to_ws[client_ip] = websocket`; nếu có WS cũ khác → `asyncio.create_task(_kick_old_session_for_ip(...))` (L1774) chạy nền. `_kick_old_session_for_ip` (L1735) gọi `old.close(code=1000, reason='Replaced...')` với timeout 1s (L1749).
3. Set trạng thái client mới:
   - `client_needs_keyframe.add(websocket)` (L1780).
   - `client_last_video_id[websocket] = -1` (L1781) — frame đầu luôn được gửi.
   - `client_keyframe_wait_until[websocket] = time.monotonic() + 8.0` (L1782).
   - `_force_keyframe_next = True` (L1783).
   - `_wake_display_on()` (L1787) — SetThreadExecutionState giữ màn sáng (hàm L241).
4. `await run_in_executor(None, _ensure_streaming)` (L1789); `_ensure_streaming()` (L1471) idempotent trong `_stream_lock` (L1473-1478); nếu chưa active: `_init_capture()` (L1481), `_init_encoder()` (L1491), `_find_best_audio_device()` (L1494), `_streaming_active=True` (L1496), `_ensure_encode_thread()` (L1500), start `_capture_loop` + `_audio_capture_loop` threads (L1502-1503).
5. Nếu `_audio_capture_device is None` → `_find_best_audio_device()` thử lại (L1792-1796); tính `audio_rate` (L1797-1799).
6. Gửi init JSON (L1801-1815): `{type:"init", codec:"h264", width/height, scale, enc_width/enc_height, fps, audio_codec, audio_sample_rate, audio_channels}` → `await websocket.send(init_msg)` (L1815).
7. Gửi SPS/PPS: `header_msg = b'\x03' + _cached_sps + _cached_pps` → `await websocket.send(header_msg)` (L1817-1819).
8. `connected_clients.add(websocket)` SAU init (L1825).
9. Đóng cửa sổ TOCTOU: nếu `not _streaming_active` → gọi lại `_ensure_streaming` (L1829-1830).
10. Vòng lặp nhận message `async for message in websocket` (L1834):
    - bỏ frame bytes (L1836-1837).
    - JSON parse (L1838); `get_screen_info` → `screen_info` (L1840-1843); `request_keyframe` → add + reset deadline 8s (L1844-1847); `mouse_*`/`key_*` → `_last_input_time` + `execute_command` (L1848-1850); `ping` → `pong` (L1851-1852).
11. `finally` (L1857-1869): discard khỏi `connected_clients`/`client_needs_keyframe`/`client_keyframe_wait_until`; xóa IP khỏi `_ip_to_ws` nếu là ws hiện tại; `_release_all_buttons()`; `_maybe_stop_streaming()`; nếu `not _has_any_client()` → `_wake_display_off()`.

## D. Luồng encode (capture → frame)

1. `_capture_loop()` (L722), thread từ L1502:
   - `_camera.start(target_fps=MAX_FPS, video_mode=True)` (L732).
   - `while _streaming_active` (L737): `frame = _camera.get_latest_frame()` (L739); nếu có → `force_kf = _force_keyframe_next` (L741); `_encode_frame(frame, force_keyframe=force_kf)` (L742); nếu không frame → auto-restart camera khi idle >2s (L745-759).
2. `_encode_frame(bgr_frame, force_keyframe)` (L702):
   - nếu `_encoder_codec is None` return (L707); nếu `force_keyframe` → `_force_keyframe_next = False` (L710).
   - `bgr_copy = bgr_frame.copy()` (L712).
   - `with _encode_lock:` nếu queue đầy `popleft()` drop frame cũ (L716-717); `_encode_queue.append((bgr_copy, force_keyframe))` (L718); `_encode_notify.notify()` (L719).
3. `_ensure_encode_thread()` (L609): spawn thread `_encode_loop` nếu chưa chạy (L612-616).
4. `_encode_loop()` (L619), thread:
   - vòng `while not _encode_stop` (L629): lấy `(bgr_copy, force_kf)` từ `_encode_queue.popleft()` (L637).
   - scale nếu `SCALE_PERCENT<100` (L642-644).
   - Dither ±1 (L651-658): `_dither_tile` sinh/`np.tile`, `np.clip(bgr_copy.astype(int16)+tile, 0, 255)`.
   - `frame = av.VideoFrame.from_ndarray(bgr_copy, format='bgr24')` (L661); `frame.reformat(format='yuv420p')` (L663-665).
   - nếu `force_kf` → `frame.pict_type = PictureType.I` (L667-668).
   - `packets = _encoder_codec.encode(frame)` (L674).
   - với mỗi `pkt`: `data = bytes(pkt)` (L680); lần đầu `_extract_sps_pps(data)` (L683-684); `is_key = _has_idr(data)` (L685); `with _video_lock:` set `_latest_video=data`, `_video_id += 1`, `_latest_video_data = (_video_id, data, is_key)` (L686-689).
   - FPS counter (L692-699).
5. `_force_keyframe_next` được set ở: client mới (L1783), và khi có client cần keyframe trong stream_loop (L2025).

## E. Luồng gửi (`stream_loop`, L1904)

1. Cấu hình: `WRITE_BUFFER_LIMIT = 2MB` (L1908), `_buf_skip_count = {}` (L1909), `max_frames_per_iter = 2` (L1984), `frame_interval = 1.0/MAX_FPS` (L1985/2000), `next_send_time` (L2001), `_audio_batch` (L2002-2003).
2. Hàm lồng:
   - `_buffer_backed_up(ws)` (L1913): `transport.get_write_buffer_size() > WRITE_BUFFER_LIMIT`.
   - `send_video_to_clients(vid, frame, is_key)` (L1922) — chi tiết bước 4.
   - `send_audio_to_clients(audio)` (L1987): gửi `b'\x02'+audio` cho `audio_clients`.
3. Vòng `while True` (L2006):
   - **Audio**: nếu `audio_clients` → `drain_audio_queue()` (L2012); gom vào `_audio_batch`; nếu đủ ≥2 chunk hoặc đã 20ms → `batched = b''.join(...)` + `asyncio.create_task(send_audio_to_clients(batched))` (L2016-2020).
   - **Video**: nếu `connected_clients and now >= next_send_time` (L2022):
     - nếu `client_needs_keyframe` → `_force_keyframe_next = True` (L2024-2025).
     - `latest = _get_latest_frame()` (L2027) — đọc + clear `_latest_video_data` (hàm L1632).
     - nếu `latest is not None` (L2029): tách `(vid, frame, is_key)` (L2030); nếu `is_key` và có SPS/PPS và frame chưa có SPS/PPS → `send_frame = _cached_sps + _cached_pps + frame` (L2033-2035); `await send_video_to_clients(vid, send_frame, is_key)` (L2036).
     - `next_send_time = now + frame_interval` (L2039).
     - **Watchdog keyframe-timeout**: nếu `client_keyframe_wait_until` (L2044): duyệt `client_needs_keyframe`, nếu `now > dl` (8s) → log + `await ws.close()` (L2049-2050), discard khỏi 2 set (L2053-2054) → client reconnect.
   - Giải phóng nút kẹt sau `_INPUT_TIMEOUT` (L2056-2058).
   - Sleep pacing: `deadline = next_send_time if connected_clients else now+0.05`; `delay = deadline - now - 0.0015`; `await asyncio.sleep(delay)` (L2064-2067); busy-wait `while time.monotonic() < deadline: pass` (L2068-2069).
   - FPS log mỗi 5s (L2072-2083).
4. `send_video_to_clients(vid, frame, is_key)` chi tiết (L1922):
   - `msg = b'\x01' + frame` (L1925).
   - `for ws in list(connected_clients)` (L1926):
     - `last_vid = client_last_video_id.get(ws, -1)` (L1931).
     - `if vid == last_vid: continue` (L1932) — bỏ frame trùng đã gửi.
     - skip P-frame cho client cần keyframe NHƯNG không phải client mới: `if ws in client_needs_keyframe and not is_key and last_vid != -1: continue` (L1934).
     - `if _buffer_backed_up(ws)` (L1936): nếu `is_key and ws in client_needs_keyframe` → ưu tiên gửi keyframe (`wait_for(ws.send, timeout=0.1)`), cập nhật last_vid, discard nhu cầu keyframe (L1939-1949); ngược lại tăng `_buf_skip_count`, yêu cầu keyframe khi count==0, `continue` (L1953-1958).
     - gửi thường: `await asyncio.wait_for(ws.send(msg), timeout=0.05)` (L1960); `client_last_video_id[ws] = vid` (L1961); nếu đang cần keyframe → discard + pop deadline (L1962-1964).
     - `asyncio.TimeoutError` → vẫn cập nhật last_vid, không giữ nhu cầu keyframe vô hạn (L1967-1972).
     - `websockets.ConnectionClosed` → `stale.add(ws)` + cleanup map/set (L1973-1977).
   - nếu `stale` → `connected_clients.difference_update(stale)` (L1980).
   - `_send_frame_count += 1` (L1981).

## F. Luồng client nhận (viewer JS)

1. Khởi động `connect()` (L1139) — gọi lần đầu ở L2155.
   - Nếu WS cũ đang CONNECTING/OPEN/CLOSING (L1142): nếu `_wsClosing` return; set `_wsClosing=true`, `oldWs.close()` + `oldWs.onclose` gọi `connect()` (L1144-1152); rescue 3s nếu onclose không fire (L1155-1162).
   - Tạo `ws = new WebSocket(serverUrl)` (L1169); `ws.binaryType='arraybuffer'` (L1171); `serverUrl` từ `getServerUrl()` (L1087).
2. `ws.onopen` (L1173):
   - `_reconnectAttempt = 0` (L1175); `setStatus('connected')` (L1177).
   - Reset decoder: `cleanupDecoder()` (L1179), reset `decoderConfigured/decoderReady/cachedSPS/cachedPPS/tsUs/decodedCount/decodeCount/_nalSlotCount/_avccOut/_lastRenderTs` (L1180-1189).
   - `_wsConnectTs = Date.now()` (L1190) — mốc watchdog chưa render.
   - `connectAudio()` (L1191) — WS audio 8767 (hàm L1110).
   - `requestKeyframe()` (L1194) → gửi `{type:'request_keyframe'}` (hàm L1200-1204).
3. `ws.onmessage` (L1206):
   - `lastDataTime = Date.now()` (L1207).
   - Binary: `type = data[0]` (L1210); nếu `type === 0x01` (L1216): tăng `decodeCount`; nếu `!decoderMode` return (L1219-1221); nếu đã configure nhưng chưa ready, drop nếu không có IDR (L1223-1230); parse NAL (L1231-1240), cache `cachedSPS/cachedPPS`, phát hiện `hasIDR`; webcodecs: nếu chưa configure và có SPS/PPS → `configureDecoder(sps, pps, width, height)` (L1242-1244); broadway: buffer chờ SPS+PPS+IDR (L1245-1256); `decodeFrame(payload)` (L1257).
   - JSON: nếu `msg.type === 'init'` (L1265): set `screenInfo`, `frameIntervalUs = 1e6/msg.fps`, `AUDIO_SRC_RATE` (L1266-1269); `initDecoder(msg.width, msg.height)` (L1270); cập nhật status/codec badge (L1273-1275). Nếu `screen_info` → xử lý thay đổi độ phân giải + request keyframe (L1280-1285).
4. `decodeFrame(data)` (L598): webcodecs → `parseAnnexBNALs` (L602), `annexBToAVCC` (L603), check IDR (L606-609); nếu `decodeQueueSize > DECODE_QUEUE_HARD_LIMIT(4)` và không key → drop (L612-613); nếu key → `videoDecoder.reset()` (L615-616); nếu chưa ready và không key → `requestRemoteKeyframe()` return (L619-622); `videoDecoder.decode(new EncodedVideoChunk({type: isKey?'key':'delta', ...}))` (L624-628); `decoderReady=true` (L629); `tsUs += frameIntervalUs` (L630).
5. Watchdog stall (L1317-1339), setInterval 1s:
   - `anchor = (_lastRenderTs === 0) ? _wsConnectTs : _lastRenderTs` (L1323); `since` (L1324).
   - `since > STALL_TIMEOUT_MS(3000)` → `requestRemoteKeyframe()` (L1325-1329).
   - `since > STALL_RECONNECT_MS(8000)` → `connect()` ép force-reconnect (L1334-1338).
6. `ws.onclose` (L1290): `_reconnectAttempt++` (L1292); `setStatus('disconnected')` (L1294); hide codec badge (L1295); reset modifier (L1298); nếu `!_wsClosing` → `scheduleReconnect()` (L1301); nếu tab ẩn → reset backoff (L1304).
7. `scheduleReconnect(delayMs)` (L1102): clear timer cũ; nếu `document.hidden` return (L1105); tính delay = `min(BASE*2^attempt, MAX)` (L1106); `_connectTimer = setTimeout(connect, delay)` (L1107).
8. Heartbeat/idle watchdog: ping 15s (L2084-2086); WS OPEN nhưng `>180000ms` không nhận data → `ws.close()` (L2088-2093); visibilitychange → ping nhanh + reconnect (L2095-2152).

## G. Luồng idle/stop

1. `_schedule_idle_exit()` (L1571), gọi từ `run()` (L2168) và lần đầu trong `_maybe_stop_streaming` (L1568):
   - `_monitor()` (L1577): `while True`: sleep 2s (L1580); nếu `connected_clients or audio_clients` → `_idle_since=None` (L1581-1583); ngược lại đếm idle; nếu `>= IDLE_PROCESS_EXIT(60.0)` → log + `os._exit(0)` (L1587-1591).
   - `threading.Thread(_monitor, daemon=True).start()` (L1593).
2. Khi client disconnect, `finally` của `ws_handler` gọi `_maybe_stop_streaming()` (L1866) và nếu không còn client `_wake_display_off()` (L1868-1869). Audio handler tương tự (L1898-1901).
3. `_maybe_stop_streaming()` (L1552): `with _stream_lock:` nếu còn client return (L1555); nếu đã có `_stop_timer` return (L1557); tạo `_stop_timer = threading.Timer(IDLE_STOP_DELAY(5.0), _do_stop_streaming)` (L1559-1561); nếu chưa khởi động idle-exit → `_schedule_idle_exit()` (L1566-1568).
4. `_do_stop_streaming()` (L1534), chạy trên thread timer: `with _stream_lock:` `_stop_timer=None` (L1542); nếu `not _streaming_active` return (L1543); nếu còn client return (L1545); `_stop_streaming_locked()` (L1547).
5. `_stop_streaming_locked()` (L1506): `_streaming_active=False` (L1509); `_encode_stop=True` + `_encode_notify.notify_all()` (L1510-1512); `_stop_encoder()` (L1513); `_camera.stop()` + `del _camera`, `_camera=None` (L1514-1524); log "[STREAM] Stopped" (L1525).
6. `_stop_encoder()` (L595): `_encode_stop=True` + notify (L597-599); `del _encoder_codec`, `_encoder_codec=None` (L600-605).
7. `_ensure_streaming()` khi có client mới (L1789/L1830) sẽ khởi động lại toàn bộ chain (camera + encoder + stream timer) một cách idempotent.

---
- Ký: deepseek-v4-flash api-box
---

## PHỤ LỤC: Parent/Child Process trong Windows (tổng quát)

### Lý thuyết
- Một process (parent) tạo process khác (child) bằng API như CreateProcess. Child có không gian bộ nhớ, handle, thread riêng biệt.
- Có 2 loại với hiệu năng khác nhau:
  1. **Child làm việc song song thật** (vd: server spawn worker, thread pool): cả 2 cùng chạy → mới có chi phí hiệu suất (tốn CPU/RAM, có thể lock/đồng bộ).
  2. **Child chỉ "khởi động + chờ"** (vd: PyInstaller onefile bootloader, wrapper): parent nằm im chờ → KHÔNG giảm hiệu suất thời gian thực, parent không dùng CPU, không chen vào luồng xử lý chính.

### Nguyên tắc chung
- Việc tạo process (CreateProcess) có chi phí 1 lần lúc khởi động, không phải mỗi lần chạy.
- Hiệu suất phụ thuộc vào việc 2 process có tranh chấp tài nguyên (CPU/RAM/lock) trong lúc chạy hay không, chứ không phải có parent/child hay không.
- Parent/child chỉ là mô hình tổ chức (ai tạo ra ai, ai quản lý ai). Chậm hay không là do công việc thực thi, không do mối quan hệ parent/child.

### Áp dụng cho app này (PyInstaller onefile)
- server_H264wss_testP_new.exe chạy 2 process: parent (bootloader, giải nén + spawn child rồi chờ) và child (chạy code server thật).
- Parent không tham gia luồng capture/encode/send WS → không ảnh hưởng fps/độ trễ.
- Exe lớn (~96MB) chỉ ảnh hưởng thời gian load/giải nén lúc khởi động, không ảnh hưởng hiệu suất stream.

### Kết luận
- Parent/child không tự nó gây chậm. Chậm chỉ khi cả 2 cùng tranh CPU/RAM/lock để làm việc song song. Nếu một bên chỉ chờ thì không ảnh hưởng hiệu suất.

- Ký: deepseek-v4-flash api-box
