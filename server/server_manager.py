# -*- coding: utf-8 -*-
"""
Server Manager Wrapper cho Screen Share Server H264 Windows

Thiết kế: wrapper SỐNG MÃI (không bao giờ exit), giữ 3 ports (8765/8766/8767).
Khi có connect request tới bất kỳ port nào -> nhả port, spawn server con (server_H264wss.py)
để xử lý. Khi server con tự thoát (IDLE_PROCESS_EXIT không có client), wrapper lại giữ ports
và chờ connect request tiếp theo.

Lợi ích: server KHÔNG chạy (không tốn CPU encode) khi chưa có client. Wrapper chỉ nhẹ nhàng
giữ port và "thức dậy" server khi có người kết nối.
"""

import os
import subprocess
import sys
import socket
import threading
import time

FROZEN = getattr(sys, 'frozen', False)
if FROZEN:
    # onefile: __file__ ở temp giải nén; BASE_DIR phải là folder thật chứa exe
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Chọn server cần wrap dựa trên tên exe của chính manager ──
# server_manager.exe  -> server_H264wss.exe       (bản production)
# server_manager_K.exe -> server_H264wss_testK.exe
# server_manager_L.exe -> server_H264wss_testL.exe
# server_manager_O.exe -> server_H264wss_testO.exe
# server_manager_P.exe -> server_H264wss_testP.exe
# server_manager_O_new.exe -> server_H264wss_testO_new.exe  (NEW: 2026-08-09)
# server_manager_P_new.exe -> server_H264wss_testP_new.exe  (NEW: 2026-08-09)
def _detect_target():
    self_name = os.path.splitext(os.path.basename(sys.executable if FROZEN else __file__))[0]
    tag = None
    for t in ("_K", "_L", "_O_new", "_P_new", "_O", "_P"):
        if self_name.endswith(t):
            tag = t
            break
    base = "server_H264wss"
    if tag:
        base += f"_test{tag[1:]}"
    return base

_target = _detect_target()
SERVER_SCRIPT = os.path.join(BASE_DIR, _target + ".py")
SERVER_EXE = os.path.join(BASE_DIR, _target + ".exe")

HOST = "0.0.0.0"
PORTS = (8765, 8766, 8767)  # HTTP, Video/Control WSS, Audio WSS

server_proc = None
_server_lock = threading.Lock()
_stop = False
_last_spawn = 0.0
_spawn_pending = False  # FIX [2026-08-12]: đang trong quá trình spawn server con → listener không re-bind port
_released_ports = {}    # FIX [2026-08-12]: per-port event báo listener đã nhả port (đồng bộ trước spawn)
MIN_SPAWN_GAP = 2.0  # tránh spawn spam khi client retry liên tục
# Single-instance lock riêng theo từng wrapper (tránh 2 wrapper cùng wrap 1 server)
PID_LOCK = os.path.join(BASE_DIR, f"server_manager{_target.removeprefix('server_H264wss')}.pid")


def log(msg):
    print(f"[MGR] {msg}", flush=True)


def _server_alive():
    global server_proc
    if server_proc is None:
        return False
    return server_proc.poll() is None


def _get_pids_on_ports():
    """Liệt kê PID đang LISTEN trên các port mục tiêu (Windows)."""
    pids = set()
    try:
        out = subprocess.check_output(
            ["netstat", "-ano"], stderr=subprocess.DEVNULL, text=True
        )
        for line in out.splitlines():
            if any(f":{p}" in line for p in PORTS) and "LISTENING" in line:
                parts = line.split()
                if parts and parts[-1].isdigit():
                    pids.add(int(parts[-1]))
    except Exception:
        pass
    return pids


def _kill_stale_servers():
    """Kill mọi process cũ đang chiếm các port (server rác từ lần chạy trước)."""
    for pid in _get_pids_on_ports():
        if pid == os.getpid():
            continue
        try:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            log(f"Killed stale process on port: PID {pid}")
        except Exception:
            pass
    time.sleep(0.5)


def spawn_server():
    """Spawn server con mới. Wrapper nhả port trước khi con bind."""
    global server_proc, _last_spawn, _spawn_pending, _released_ports
    with _server_lock:
        if _server_alive():
            return
        now = time.monotonic()
        if now - _last_spawn < MIN_SPAWN_GAP:
            return  # client đang retry, không spawn spam
        _last_spawn = now
        _spawn_pending = True
        _kill_stale_servers()
        # FIX [2026-08-12]: chờ CẢ 3 port thực sự released (listener nhả hẳn) trước Popen,
        # thay vì sleep(0.5) heuristic → loại bỏ race double-bind port với server con.
        for p in PORTS:
            _released_ports[p].wait(timeout=3.0)
        log(f"Spawning server: {SERVER_EXE if FROZEN else SERVER_SCRIPT}")
        try:
            if FROZEN:
                # Chạy exe server con (đóng gói), cùng folder với manager exe
                server_proc = subprocess.Popen(
                    [SERVER_EXE],
                    cwd=BASE_DIR,
                    stdout=sys.stdout,
                    stderr=sys.stderr,
                )
            else:
                server_proc = subprocess.Popen(
                    [sys.executable, "-u", "-X", "utf8", SERVER_SCRIPT],
                    cwd=BASE_DIR,
                    stdout=sys.stdout,
                    stderr=sys.stderr,
                )
            log(f"Server PID={server_proc.pid}")
        except Exception as e:
            log(f"Failed to spawn server: {e}")
            server_proc = None
            _spawn_pending = False


def _hold_ports():
    """Wrapper giữ 3 ports, chờ connect request. Khi có connect -> báo spawn.
    Chỉ giữ khi server con không chạy."""
    global _spawn_pending, _released_ports
    evt = threading.Event()
    # FIX [2026-08-12]: mỗi port có 1 event "đã release" để spawn_server chờ CẢ 3 port
    # thực sự nhả hẳn trước khi Popen server con (thay vì sleep(0.5) heuristic).
    _released_ports = {port: threading.Event() for port in PORTS}

    def _port_listener(port):
        global _spawn_pending, _released_ports  # FIX [2026-08-12]: gán + đọc biến module
        while not _stop:
            # Nếu server con đang chạy HOẶC đang spawn -> không giữ port (tránh xung đột)
            if _server_alive() or _spawn_pending:
                time.sleep(0.3)
                continue
            _released_ports[port].clear()
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # FIX [2026-08-12]: SO_EXCLUSIVEADDRUSE thay vì SO_REUSEADDR. Trên Windows
            # SO_REUSEADDR cho phép 2 socket bind cùng addr:port → trong cửa sổ manager
            # giữ port + server con lên, listen socket của server con bị teardown →
            # accept ném OSError WinError 64 → proactor đóng listen socket vĩnh viễn →
            # client nhận 1006. SO_EXCLUSIVEADDRUSE ngăn double-bind cùng port.
            try:
                srv.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            except OSError:
                pass
            try:
                srv.bind((HOST, port))
                srv.listen(8)
                srv.settimeout(0.5)
            except OSError:
                srv.close()
                time.sleep(1.0)
                continue
            try:
                while not _stop and not _server_alive() and not _spawn_pending:
                    try:
                        conn, addr = srv.accept()
                        conn.close()  # chỉ cần biết có ai muốn nối
                        evt.set()
                        # FIX [2026-08-12]: đánh dấu đang spawn để 3 listener thoát + nhả port
                        # (không re-bind) cho tới khi server con exit hẳn.
                        _spawn_pending = True
                        log(f"Connect request on port {port} from {addr}")
                        break
                    except socket.timeout:
                        continue
                    except OSError:
                        break
            finally:
                srv.close()  # nhả port để server con bind
                _released_ports[port].set()  # FIX [2026-08-12]: báo port đã release
            time.sleep(0.3)
        return evt, _released_ports

    threads = []
    for port in PORTS:
        t = threading.Thread(target=_port_listener, args=(port,), daemon=True)
        t.start()
        threads.append(t)
    return evt, _released_ports


_single_mutex = None  # giữ handle named mutex suốt vòng đời process

def _acquire_single_instance():
    """Đảm bảo chỉ 1 wrapper chạy. Dùng named mutex (atomic, cross-process) để chống
    2 instance cùng lúc khởi động; instance mới kill instance cũ (qua PID file) rồi chiếm quyền."""
    global _single_mutex
    import ctypes
    MUTEX_NAME = f"Global\\ScreenShareMgr_{_target}"

    def _try_create():
        h = ctypes.windll.kernel32.CreateMutexW(None, True, MUTEX_NAME)
        err = ctypes.windll.kernel32.GetLastError()
        return h, err

    # Thử tạo mutex (True = initial owner).
    # Nếu h == 0 hoặc err in (183, 5) (183: ERROR_ALREADY_EXISTS, 5: ERROR_ACCESS_DENIED) -> có instance khác.
    handle, err = _try_create()
    if not handle or err in (183, 5):
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            handle = None

        # Có manager cũ đang chạy -> kill qua PID file (cơ chế "mới thay cũ")
        try:
            if os.path.exists(PID_LOCK):
                with open(PID_LOCK) as f:
                    old_pid = int(f.read().strip())
                if old_pid not in (0, os.getpid()):
                    try:
                        subprocess.run(["taskkill", "/F", "/PID", str(old_pid)],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        log(f"Killed old manager PID {old_pid}")
                    except Exception:
                        pass
        except Exception:
            pass

        # Đợi instance cũ nhả mutex rồi thử lại
        for _ in range(10):
            time.sleep(0.5)
            handle, err = _try_create()
            if handle and err not in (183, 5):
                break
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                handle = None

        if not handle or err in (183, 5):
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                handle = None
            log("Another manager still running; cannot acquire lock.")
            sys.exit(1)
    _single_mutex = handle  # giữ handle để mutex không bị GC giải phóng
    try:
        with open(PID_LOCK, "w") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass
    log(f"Single-instance lock acquired (PID {os.getpid()})")


def _is_elevated():
    """Kiểm tra xem tiến trình hiện tại có quyền admin (elevated) không."""
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _relaunch_as_admin():
    """Tự nâng quyền admin qua UAC prompt (ShellExecute runas)."""
    import ctypes
    try:
        if FROZEN:
            # Chạy lại chính exe manager (đã đóng gói)
            res = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, None, BASE_DIR, 1)  # 1 = SW_SHOWNORMAL
        else:
            res = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable,
                f'"{os.path.join(BASE_DIR, "server_manager.py")}"',
                BASE_DIR, 1)  # 1 = SW_SHOWNORMAL
        if int(res) > 32:
            log("Relaunching as admin (UAC prompt accepted)...")
            return True
        else:
            log(f"Elevation cancelled or failed (ShellExecute code {res})")
            return False
    except Exception as e:
        log(f"Elevation failed: {e}")
        return False


def main():
    global server_proc, _stop, _spawn_pending
    # Tự nâng quyền admin nếu chưa có (để SendInput điều khiển được ứng dụng elevated như Task Manager)
    if not _is_elevated():
        log("Not running as admin, attempting elevation...")
        if _relaunch_as_admin():
            return
        log("Elevation failed or cancelled, continuing in non-admin mode...")
    _acquire_single_instance()
    log("Server Manager started (holding ports, waiting for connect)")
    _kill_stale_servers()

    evt, released = _hold_ports()

    try:
        while True:
            if evt.wait(timeout=0.5):
                evt.clear()
                # FIX [2026-08-12]: spawn_server tự chờ cả 3 port released (không cần sleep ở đây)
                spawn_server()

            if server_proc is not None:
                rc = server_proc.poll()
                if rc is not None:
                    log(f"Server exited with code {rc}")
                    with _server_lock:
                        server_proc = None
                        # FIX [2026-08-12]: server đã thoát → cho phép listener giữ port lại
                        _spawn_pending = False
                    if rc != 0:
                        log("Server crashed, respawn in 3s...")
                        time.sleep(3)
                        spawn_server()
            time.sleep(0.2)
    except KeyboardInterrupt:
        log("Shutting down manager...")
        _stop = True
        if server_proc is not None:
            try:
                server_proc.terminate()
            except Exception:
                pass


if __name__ == "__main__":
    main()