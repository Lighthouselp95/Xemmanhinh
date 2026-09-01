# Tinh trang & De xuat: WinError 64 tren WS accept (server P new)

- Ngay: 2026-08-12
- Ky: deepseek-v4-flash api-box

## Tinh trang hien tai
- Server: PC Windows stream man hinh -> dien thoai qua HTTPS + WebSocket (H264 + PCM).
- Manager (server_manager.py) song mai, giu 3 port (8765 HTTP / 8766 video / 8767 audio), khi co connect thif spawn server con (server_H264wss_testP_new.py).
- Server con idle 60s -> os._exit(0) -> manager respawn.
- **Da fix (v1.77)**: 
  - Fix a: server co _loop_exception_handler (OSError winerror=64 -> os._exit(1)) de manager respawn.
  - Fix b: manager _port_listener doi SO_REUSEADDR -> SO_EXCLUSIVEADDRUSE.
  - Fix c: HTTP handler bo qua ConnectionResetError/SSLError (<- het spam log 10054).
- **Van de con sot**: WinError 64 VAN xay ra (fix a hoat dong: server tu exit code 1 -> manager respawn, nhung goc chua triet de).

## Log minh chung
`
[FPS] send=37.0 (hoat dong tot)
[FATAL] WS accept failed (WinError 64), exiting for respawn
[MGR] Server exited with code 1
[MGR] Server crashed, respawn in 3s...
`
Fix a (safety-net) hoat dong dung, nhung WinError 64 lap lai -> fix b chua triet de.

## Gi thuyet "scroll terminal gay loi" -> SAI
- Scroll/refresh chi la HTTP request file tinh (thread rieng, port 8765).
- [FATAL] WS accept failed o event loop asyncio (port 8766/8767) - khong lien quan scroll.
- FATAL sau khi scroll chi la trung thoi diem (race port), khong phai quan he nhan qua.

## Root cause con sot (debugger phan tich)
- **Khong phai manager co-bind cung tuple port** (thu ma SO_EXCLUSIVEADDRUSE da chan).
- **La race handoff port giua manager va server con**: manager nha port theo heuristic sleep(0.5) + polling _server_alive(), server con bind theo lich rieng. Khong co co che bao dam ca 3 port thuc su rong truoc khi child bind.
- Listen socket cua child bi teardown khi dang accept -> Windows bao ERROR_NETNAME_DELETED (WinError 64).

### Chi tiet
- _port_listener thread sau khi nha port (inally: srv.close()) + sleep(0.3) -> **RE-BIND lai port** (vi _server_alive() van False trong luc spawn chua xong). vt chi de bao, khong khoa thread khoi re-bind.
- spawn_server dung 	ime.sleep(0.5) heuristic, khong cho du 3 per-port released.
- Port nao khong co connect -> thread giu port toi khi _server_alive()=True (tre toi +0.5s), roi re-bind.
- SO_EXCLUSIVEADDRUSE chi chan co-bind cung tuple, khong giai quyet race timing dong/mo lai socket.

## Cac phuong an de xuat (verifier/duggdebugger)
| # | Giai phap | Trade-off |
|---|-----------|-----------|
| 1 | Manager KHONG bind port chung. Dung ken h wake khac (named-pipe / port dieu khien rieng). Viewer van tro toi port server. | Bo han race, sach nhat. Can sua co che "thuc day". |
| 2 | Truyen socket da bind cho child (pass_fds / ke thua handle tren Windows). Manager giu socket, child dung chinh socket do. | PyInstaller + ke thua socket tren Windows phuc tap. |
| 3 | Sua _port_listener: sau khi vt.set() thi KHONG re-bind cho toi khi server con exit han (them co _spawn_pending); spawn_server cho du 3 per-port eleased event truoc khi Popen (thay sleep(0.5)). | Don gian, giu nguyen kien truc. Can them event dong bo/flag. |
| 4 | Child bind-retry: neu bind fail (10013/10048) thi retry vai giay truoc khi exit. | Giam nhe, khong triet tieu race; co the delay boot. |

## Self-assessment (orchestrator)
- Phuong an 3 la can bang tot nhat: loai bo re-bind-thua + dam bao dong bo nha port truoc spawn, dung nguyen nhan goc. Don gian, giu kien truc hien tai, khong can doi viewer/co che wake.
- Phuong an 1 sach nhat nhung doi co che wake (phuc tap, risk regress ca viewer).
- Phuong an 2 phuc tap tren Windows/PyInstaller.
- Phuong an 4 chi giam nhe.
-> **CHON phuong an 3**.

## Cap nhat (2026-08-12): DA CHON + DA THUC HIEN
- **Chon**: phuong an 3 (manager khong re-bind sau evt.set + spawn_server cho du 3 port released).
- **Da thuc hien**:
  1. server_manager.py: them _spawn_pending flag + per-port eleased event; listener khong re-bind khi pending; spawn_server cho 3 released truoc Popen; main loop reset pending khi server exit.
  2. web/viewer_H264wss_P_new.html: watchdog bo gate decoderReady/_lastRenderTs===0, them _wsConnectTs lam moc khi chua render; reset trong cleanupDecoder → chong den man hinh vinh vien khi F5 spam / khong nhan keyframe dau.
- **Trang thai**: py_compile manager OK, verifier PASS (da sua diem HIGH). CHUA build lai exe. CHUA test thuc te.
- Ky: deepseek-v4-flash api-box
