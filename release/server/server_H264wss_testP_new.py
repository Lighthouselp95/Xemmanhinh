#!/usr/bin/env python3
"""
Screen Share Server H264 for Windows v1.0 - Low Latency H.264 Streaming
- Capture: dxcam (Windows Desktop Duplication API)
- Encode: PyAV (libx264 software encoder)
- Input: SendInput (ctypes) - Windows API
- Audio: WASAPI loopback (optional, via ctypes/comtypes)
- Stream: WebSocket binary (prefix: 0x01=video, 0x02=audio, 0x03=init)
- Ports: 8765 (HTTP) + 8766 (WebSocket) + 8767 (Audio WS)
"""

import asyncio
import ctypes
import ctypes.wintypes
import json
import multiprocessing
import os
import ssl
import struct
import subprocess
import sys
import threading
import time
import collections
import gc
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from typing import Set
from fractions import Fraction

import warnings
warnings.filterwarnings("ignore", message="data discontinuity.*")
warnings.filterwarnings("ignore", category=UserWarning, module="soundcard")
import websockets
import av
from av.video.frame import PictureType
import dxcam
import numpy as np

# Patches for dxcam stability during display transitions and hotplug
try:
    import dxcam.core.output
    orig_update_desc = getattr(dxcam.core.output.Output, 'update_desc', None)
    def safe_update_desc(self):
        if getattr(self, 'output', None) is None:
            return
        try:
            self.output.GetDesc(ctypes.byref(self.desc))
        except Exception:
            pass
    dxcam.core.output.Output.update_desc = safe_update_desc
except Exception:
    pass

try:
    import dxcam.dxcam
    def failfast_recover_output(self):
        """Clean fail-fast recovery: stop internal thread gracefully so server can handle hotplug."""
        try:
            self.is_capturing = False
            stop_ev = getattr(self, '_DXCamera__stop_capture', None)
            if stop_ev is not None:
                stop_ev.set()
            frame_ev = getattr(self, '_DXCamera__frame_available', None)
            if frame_ev is not None:
                frame_ev.set()
        except Exception:
            pass
    dxcam.dxcam.DXCamera._recover_output = failfast_recover_output
except Exception:
    pass

try:
    import dxcam.core.stagesurf
    orig_rebuild = dxcam.core.stagesurf.StageSurface.rebuild
    def safe_stagesurf_rebuild(self, output, device, dim=None):
        """Prevent AttributeError when device or device.device is None."""
        if device is None or getattr(device, 'device', None) is None:
            return
        return orig_rebuild(self, output, device, dim=dim)
    dxcam.core.stagesurf.StageSurface.rebuild = safe_stagesurf_rebuild
except Exception:
    pass



# === Windows API constants ===
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008
KEYEVENTF_EXTENDEDKEY = 0x0100
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800

VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_LWIN = 0x5B
VK_RETURN = 0x0D
VK_ESCAPE = 0x1B
VK_TAB = 0x09
VK_BACK = 0x08
VK_DELETE = 0x2E
VK_UP = 0x26
VK_DOWN = 0x28
VK_LEFT = 0x25
VK_RIGHT = 0x27
VK_HOME = 0x24
VK_END = 0x23
VK_PRIOR = 0x21
VK_NEXT = 0x22
VK_INSERT = 0x2D
VK_CAPITAL = 0x14
VK_SNAPSHOT = 0x2C
VK_PAUSE = 0x13
VK_SPACE = 0x20

# Extended keys: (scancode, needs_extended_flag) - must be sent by scancode,
# not wVk, or Windows Terminal/console TUI apps won't generate escape sequences.
_VK_EXT_SCAN = {
    VK_UP: (0x48, True), VK_DOWN: (0x50, True),
    VK_LEFT: (0x4B, True), VK_RIGHT: (0x4D, True),
    VK_HOME: (0x47, True), VK_END: (0x4F, True),
    VK_PRIOR: (0x49, True), VK_NEXT: (0x51, True),
    VK_INSERT: (0x52, True), VK_DELETE: (0x53, True),
}


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", ctypes.c_ulong), ("wParamL", ctypes.c_short),
                ("wParamH", ctypes.c_ushort)]


class INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("union", INPUT_UNION)]


SendInput = ctypes.windll.user32.SendInput
GetSystemMetrics = ctypes.windll.user32.GetSystemMetrics
SM_CXSCREEN = 0
SM_CYSCREEN = 1

# === Config ===
HOST = "0.0.0.0"
HTTP_PORT = 8765
WS_PORT = 8766
WS_AUDIO_PORT = 8767
# Test P_new (2026-08-09): TỐI ƯU LAG - vẫn giữ H264_DITHER=1 (chuẩn testP)
# Thay đổi so với bản P cũ (xem changelog 2026-08-09 mục "Test P_new"):
#   1) Tách capture loop + encode loop (queue mới nhất, max 1 frame pending) → encode chậm không block capture
#   2) Bỏ _encode_gop_count tự đánh I; NVENC với min-keyint=1 đã tôn trọng force-keyframe
#   3) Dither được thực hiện ở encode loop (sau khi lấy frame khỏi queue) để không làm capture thread chậm
#   4) Vẫn giữ rc=constqp / qp=16 / qmin=16 / qmax=28 / aq-strength=8 (chuẩn testP)
MAX_FPS = 60  # Test P_new: 60fps (giữ chuẩn P)
SCALE_PERCENT = 100
H264_BITRATE = 20000000
H264_MAXRATE = 20000000
H264_BUFSIZE = 12000000
H264_PRESET = "medium"
H264_ENCODER = "auto"
H264_TUNE = "zerolatency"
H264_PROFILE = "main"
H264_KEYINT = 150        # Test P_new: giữ keyint 150 (giảm bitrate spike)
H264_DITHER = 1          # P_new: bật dither ±1 (giữ chuẩn testP)

# Audio config
_AUDIO_GAIN = 2.0          # Lower gain to reduce noise amplification
_AUDIO_GATE_THRESHOLD = 200
_AUDIO_SOFT_LIMIT = 0.85
_AUDIO_ADAPTIVE_GATE = False  # OFF: per-sample gate causes harmonic distortion (rat rat)
_AUDIO_GATE_LEARN_TIME = 3.0  # Shorter learn time
_AUDIO_GATE_MULTIPLIER = 2.5  # Less aggressive
_AUDIO_HIGHPASS_HZ = 120      # Higher HPF to remove hum
_AUDIO_SMOOTH_GATE = False    # OFF: gate disabled
_AUDIO_HYSTERESIS = 0.5       # Close threshold = open × 0.5

# Base dir: khi chạy exe (PyInstaller onefile), tài nguyên giải nén ở sys._MEIPASS
if getattr(sys, 'frozen', False):
    _BASE_DIR = sys._MEIPASS
else:
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))

_CERT_DIR = _BASE_DIR
SSL_CERT = os.path.join(_CERT_DIR, "cert.pem")
SSL_KEY = os.path.join(_CERT_DIR, "key.pem")

_cpu_count = max(multiprocessing.cpu_count(), 2)

# === Global State ===
connected_clients: Set = set()
audio_clients: Set = set()
client_last_video_id = {}
client_needs_keyframe: Set = set()
client_keyframe_wait_until = {}

# FPS counter for debug
_encode_frame_count = 0
_encode_fps_start = 0
_send_frame_count = 0
_send_fps_start = 0
_encode_fps = 0.0
_send_fps = 0.0

_cached_sps = None
_cached_pps = None

_latest_video = None
_video_lock = threading.Lock()
_video_id = 0
_latest_video_data = None  # Shared: latest encoded frame (thread-safe via lock)

_latest_audio = None
_audio_lock = threading.Lock()
_audio_id = 0
_audio_queue = collections.deque(maxlen=100)  # ~1s buffer (giảm trễ audio vs video)

_screen_info = {"width": 1920, "height": 1080, "scale": SCALE_PERCENT, "codec": "h264"}
_screen_w, _screen_h = 1920, 1080
_enc_w, _enc_h = 1920, 1080

_streaming_active = False
_stream_lock = threading.Lock()
_stop_timer = None
IDLE_STOP_DELAY = 5.0
IDLE_PROCESS_EXIT = 300.0  # Không có client trong 5 phút → tự thoát process sạch (wrapper restart khi có connect)

_camera = None
_encoder_codec = None
_audio_capture_active = False
_force_keyframe_next = False
_encode_gop_count = 0  # KHÔNG dùng nữa (NVENC min-keyint=1 đã handle), giữ để tương thích nếu bị tham chiếu
_dither_tile = None    # P_new: vẫn dùng int16+clip (chuẩn testP) nhưng sinh ở encode loop

# --- NEW: encode queue (capture -> encode tách thread) ---
_encode_queue = collections.deque(maxlen=1)
_encode_lock = threading.Lock()
_encode_notify = threading.Condition(_encode_lock)
_encode_thread = None
_encode_stop = False

_pressed_buttons = set()
_pressed_keys = {}          # key name -> vk_code đang giữ (track modifier/key_down)
_pressed_keys_lock = threading.Lock()
_last_input_time = [0]
_INPUT_TIMEOUT = 20

# === SSL Helper ===
def _make_ssl_context():
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile=SSL_CERT, keyfile=SSL_KEY)
    return ctx


WEB_DIR = (os.path.join(_BASE_DIR, "web") if getattr(sys, 'frozen', False)
           else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "web"))

# === NEW [P_new]: Giữ màn hình sáng khi có client (chống màn idle/tắt khi reconnect) ===
# SetThreadExecutionState(ES_DISPLAY_REQUIRED | ES_SYSTEM_REQUIRED) = báo Windows rằng
# màn hình + hệ thống đang dùng → không sleep/turn off display trong khi client kết nối.
# Khi tất cả client disconnect → trả về ES_CONTINUOUS (mặc định) để máy idle bình thường.
_SetThreadExecutionState = ctypes.windll.kernel32.SetThreadExecutionState
_SetThreadExecutionState.argtypes = [ctypes.c_uint]
_SetThreadExecutionState.restype = ctypes.c_uint

ES_CONTINUOUS        = 0x80000000
ES_SYSTEM_REQUIRED   = 0x00000001
ES_DISPLAY_REQUIRED  = 0x00000002
ES_AWAYMODE_REQUIRED = 0x00000040

def _wake_display_on():
    """Yêu cầu Windows giữ màn hình sáng. Gọi khi có client mới kết nối."""
    try:
        _SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED)
        print("[WAKE] Display kept ON (client connected)")
    except Exception as e:
        print(f"[WAKE] SetThreadExecutionState failed: {e}", file=sys.stderr)

def _wake_display_off():
    """Trả về chế độ bình thường: máy có thể sleep/turn off display theo power policy.
    Chỉ gọi khi KHÔNG còn client nào (kể cả audio)."""
    try:
        _SetThreadExecutionState(ES_CONTINUOUS)
        print("[WAKE] Display back to default (no clients)")
    except Exception as e:
        print(f"[WAKE] Reset display state failed: {e}", file=sys.stderr)

def _has_any_client():
    return bool(connected_clients) or bool(audio_clients)

# === Input Simulation (SendInput) ===
def _send_input(*inputs):
    n = len(inputs)
    arr = (INPUT * n)(*inputs)
    SendInput(n, arr, ctypes.sizeof(INPUT))


def _mouse_move(x, y):
    sx = GetSystemMetrics(SM_CXSCREEN)
    sy = GetSystemMetrics(SM_CYSCREEN)
    abs_x = int(x * 65535 / max(sx - 1, 1))
    abs_y = int(y * 65535 / max(sy - 1, 1))
    inp = INPUT(type=INPUT_MOUSE,
                union=INPUT_UNION(mi=MOUSEINPUT(dx=abs_x, dy=abs_y,
                                               mouseData=0,
                                               dwFlags=MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE,
                                               time=0, dwExtraInfo=None)))
    _send_input(inp)


def _mouse_button(button, down):
    flags = 0
    if button == 1:
        flags = MOUSEEVENTF_LEFTDOWN if down else MOUSEEVENTF_LEFTUP
    elif button == 2:
        flags = MOUSEEVENTF_MIDDLEDOWN if down else MOUSEEVENTF_MIDDLEUP
    elif button == 3:
        flags = MOUSEEVENTF_RIGHTDOWN if down else MOUSEEVENTF_RIGHTUP
    inp = INPUT(type=INPUT_MOUSE,
                union=INPUT_UNION(mi=MOUSEINPUT(dx=0, dy=0, mouseData=0,
                                               dwFlags=flags, time=0, dwExtraInfo=None)))
    _send_input(inp)
    if down:
        _pressed_buttons.add(button)
    else:
        _pressed_buttons.discard(button)


def _mouse_scroll(dy):
    data = dy * 120
    inp = INPUT(type=INPUT_MOUSE,
                union=INPUT_UNION(mi=MOUSEINPUT(dx=0, dy=0, mouseData=data,
                                               dwFlags=MOUSEEVENTF_WHEEL, time=0, dwExtraInfo=None)))
    _send_input(inp)


def _release_all_buttons():
    if not _pressed_buttons:
        return
    for btn in list(_pressed_buttons):
        _mouse_button(btn, False)


_KEY_MAP = {
    'shift': VK_SHIFT, 'control': VK_CONTROL, 'ctrl': VK_CONTROL,
    'alt': VK_MENU, 'super': VK_LWIN, 'meta': VK_LWIN, 'win': VK_LWIN,
    'return': VK_RETURN, 'enter': VK_RETURN, 'kp_enter': VK_RETURN,
    'escape': VK_ESCAPE, 'esc': VK_ESCAPE,
    'tab': VK_TAB, 'space': VK_SPACE,
    'backspace': VK_BACK, 'delete': VK_DELETE, 'del': VK_DELETE,
    'up': VK_UP, 'down': VK_DOWN, 'left': VK_LEFT, 'right': VK_RIGHT,
    'home': VK_HOME, 'end': VK_END,
    'pageup': VK_PRIOR, 'pagedown': VK_NEXT,
    'insert': VK_INSERT, 'capslock': VK_CAPITAL,
    'printscreen': VK_SNAPSHOT, 'pause': VK_PAUSE,
}
for _i in range(1, 25):
    _KEY_MAP[f'f{_i}'] = 0x6E + _i

_CHAR_TO_VK = {}
for c in 'abcdefghijklmnopqrstuvwxyz':
    _CHAR_TO_VK[c] = ord(c.upper())
for c in '0123456789':
    _CHAR_TO_VK[c] = ord(c)
_PUNCT_VK = {
    '-': 0xBD, '=': 0xBB, '[': 0xDB, ']': 0xDD,
    '\\': 0xDC, ';': 0xBA, "'": 0xDE, '`': 0xC0,
    ',': 0xBC, '.': 0xBE, '/': 0xBF,
    ' ': VK_SPACE,
}
_CHAR_TO_VK.update(_PUNCT_VK)


def _vk_key_event(vk_code, down):
    flags = 0
    if not down:
        flags |= KEYEVENTF_KEYUP
    ext = _VK_EXT_SCAN.get(vk_code)
    if ext is not None:
        scan, is_ext = ext
        flags |= KEYEVENTF_SCANCODE
        if is_ext:
            flags |= KEYEVENTF_EXTENDEDKEY
        # REVERT [2026-08-12]: thử gửi wVk=vk_code cho extended key (fix v1.82) KHÔNG giúp
        # opencode TUI nhận phím Up/Down ảo (giới hạn nền tảng: Windows không dịch input
        # injected sang VT escape sequence). Revert về wVk=0 (chuẩn scancode extended).
        inp = INPUT(type=INPUT_KEYBOARD,
                    union=INPUT_UNION(ki=KEYBDINPUT(wVk=0, wScan=scan,
                                                    dwFlags=flags, time=0, dwExtraInfo=None)))
    else:
        inp = INPUT(type=INPUT_KEYBOARD,
                    union=INPUT_UNION(ki=KEYBDINPUT(wVk=vk_code, wScan=0,
                                                    dwFlags=flags, time=0, dwExtraInfo=None)))
    _send_input(inp)


def _send_key(vk_code, down=True):
    _vk_key_event(vk_code, down)


_MODIFIER_SET = {'shift', 'ctrl', 'control', 'alt', 'super', 'meta', 'win'}


def _uinput_key(key):
    n = (key or '').lower()
    vk = _KEY_MAP.get(n)
    if vk is not None:
        _send_key(vk, True)
        time.sleep(0.01)
        _send_key(vk, False)
        return True
    if len(n) == 1:
        code = _CHAR_TO_VK.get(n)
        if code is not None:
            shift = key.isupper() and key.isalpha()
            if shift:
                _send_key(VK_SHIFT, True)
            _vk_key_event(code, True)
            time.sleep(0.005)
            _vk_key_event(code, False)
            if shift:
                _send_key(VK_SHIFT, False)
            return True
    return False


def _uinput_char_held(key):
    # Gõ ký tự KHI modifier (vd Shift/Ctrl) đã được giữ ở server —
    # KHÔNG tự gửi thêm modifier (tránh lặp Shift hoặc thả sớm).
    n = (key or '').lower()
    if len(n) == 1:
        code = _CHAR_TO_VK.get(n)
        if code is not None:
            _vk_key_event(code, True)
            time.sleep(0.005)
            _vk_key_event(code, False)
            return True
    return False


def _uinput_keydown(key):
    n = (key or '').lower()
    vk = _KEY_MAP.get(n)
    if vk is not None:
        _send_key(vk, True)
        with _pressed_keys_lock:
            _pressed_keys[n] = vk
        return True
    return False


def _uinput_keyup(key):
    n = (key or '').lower()
    vk = _KEY_MAP.get(n)
    if vk is not None:
        _send_key(vk, False)
        with _pressed_keys_lock:
            _pressed_keys.pop(n, None)
        return True
    return False


def _release_all_keys():
    """Nhả toàn bộ phím đang giữ (modifier/key_down) — gọi khi client disconnect
    hoặc idle timeout để tránh kẹt Ctrl/Shift ở server."""
    with _pressed_keys_lock:
        held = dict(_pressed_keys)
        _pressed_keys.clear()
    for vk in held.values():
        _send_key(vk, False)


def _uinput_type(text):
    # Gõ bằng PHÍM (không phải UNICODE) để keyboard layout/IME (Unikey) trên PC
    # tự chuyển TELEX (vd gõ "ee" -> "ê"). UNICODE bỏ qua IME nên Unikey không chạy.
    for ch in text:
        if not _uinput_key(ch):
            # Ký tự không map được thành VK (vd dấu tiếng Việt đã thành Unicode) -> gõ unicode dự phòng
            inp_down = INPUT(type=INPUT_KEYBOARD,
                             union=INPUT_UNION(ki=KEYBDINPUT(wVk=0, wScan=ord(ch),
                                                             dwFlags=KEYEVENTF_UNICODE, time=0, dwExtraInfo=None)))
            inp_up = INPUT(type=INPUT_KEYBOARD,
                           union=INPUT_UNION(ki=KEYBDINPUT(wVk=0, wScan=ord(ch),
                                                           dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, time=0, dwExtraInfo=None)))
            _send_input(inp_down, inp_up)
        time.sleep(0.001)
    return True


def execute_command(cmd_type, data):
    try:
        if cmd_type == "mouse_move":
            _mouse_move(int(data["x"]), int(data["y"]))
        elif cmd_type == "mouse_click":
            x, y, button = int(data["x"]), int(data["y"]), data.get("button", 1)
            _mouse_move(x, y)
            time.sleep(0.02)
            _mouse_button(button, True)
            _mouse_button(button, False)
        elif cmd_type == "mouse_dblclick":
            # Double-click thật: 2 lần down/up LIỀN MẠCH trong 1 hàm (không bị gián đoạn
            # bởi network) → Windows luôn nhận đúng double-click, không thành rename file.
            x, y, button = int(data["x"]), int(data["y"]), data.get("button", 1)
            _mouse_move(x, y)
            time.sleep(0.02)
            _mouse_button(button, True)
            time.sleep(0.03)
            _mouse_button(button, False)
            time.sleep(0.03)
            _mouse_button(button, True)
            time.sleep(0.03)
            _mouse_button(button, False)
        elif cmd_type == "mouse_down":
            _mouse_move(int(data["x"]), int(data["y"]))
            _mouse_button(data.get("button", 1), True)
        elif cmd_type == "mouse_up":
            _mouse_move(int(data["x"]), int(data["y"]))
            _mouse_button(data.get("button", 1), False)
        elif cmd_type == "mouse_scroll":
            dy = int(data.get("dy", 0))
            for _ in range(abs(dy)):
                _mouse_scroll(1 if dy > 0 else -1)
        elif cmd_type == "key_press":
            key = data.get("key", "")
            if '+' in key:
                parts = key.split('+')
                has_mod = any(p.lower() in _MODIFIER_SET for p in parts)
                non_mod = [p for p in parts if p.lower() not in _MODIFIER_SET]
                if has_mod:
                    # Giữ modifier (vd shift+ctrl+alt) rồi gõ ký tự/khóa cuối
                    mod_keys = [p for p in parts if p.lower() in _MODIFIER_SET]
                    for m in mod_keys:
                        _uinput_keydown(m)
                    for ch in non_mod:
                        if ch:
                            _uinput_char_held(ch) if not _KEY_MAP.get(ch.lower(), None) else _uinput_key(ch)
                    for m in reversed(mod_keys):
                        _uinput_keyup(m)
                else:
                    for p in parts:
                        _uinput_key(p)
            else:
                _uinput_key(key)
        elif cmd_type == "key_type":
            text = data.get("text", "")
            if text:
                _uinput_type(text)
        elif cmd_type == "key_down":
            key = data.get("key", "")
            _uinput_keydown(key)
        elif cmd_type == "key_up":
            key = data.get("key", "")
            _uinput_keyup(key)
        elif cmd_type == "get_screen_info":
            return _screen_info
    except Exception as e:
        print(f"[CTRL] Error: {cmd_type}: {e}", file=sys.stderr)
    return None

# === Screen Capture (dxcam) ===
def _reset_dxcam():
    """Dọn sạch Singleton và cache camera của dxcam để force re-enumeration tất cả adapter và outputs."""
    try:
        if hasattr(dxcam, '__factory') and dxcam.__factory is not None:
            factory = dxcam.__factory
            # 1. Duyệt qua toàn bộ _camera_instances của factory, gọi cam.stop(), cam.release(), xóa sạch.
            if hasattr(factory, '_camera_instances'):
                for _, cam in list(factory._camera_instances.items()):
                    try:
                        if getattr(cam, 'is_capturing', False):
                            cam.stop()
                        if hasattr(cam, 'release') and not getattr(cam, 'is_released', False):
                            cam.release()
                    except Exception:
                        pass
                factory._camera_instances.clear()
            # 2. Duyệt qua toàn bộ devices của factory nếu có, dọn dẹp các con trỏ COM.
            if hasattr(factory, 'devices'):
                for dev in list(factory.devices):
                    for attr in ('im_context', 'context', 'device', 'adapter'):
                        if hasattr(dev, attr):
                            try:
                                setattr(dev, attr, None)
                            except Exception:
                                pass
                factory.devices.clear()
            if hasattr(factory, 'outputs'):
                factory.outputs.clear()
        # 3. Xóa Singleton._instances, gọi gc.collect() tường minh 2 lần để ép Python thu hồi toàn bộ COM wrapper pointers.
        if hasattr(dxcam, 'Singleton') and hasattr(dxcam.Singleton, '_instances'):
            dxcam.Singleton._instances.clear()
        gc.collect()
        gc.collect()
        # 4. Khởi tạo DXFactory mới tinh và gán vào sys.modules['dxcam'].__factory, dxcam.__dict__['__factory'], dxcam._dxcam__factory.
        new_factory = dxcam.DXFactory()
        dxcam.__factory = new_factory
        dxcam.__dict__['__factory'] = new_factory
        dxcam._dxcam__factory = new_factory
        if 'dxcam' in sys.modules:
            sys.modules['dxcam'].__factory = new_factory
            sys.modules['dxcam'].__dict__['__factory'] = new_factory
            sys.modules['dxcam']._dxcam__factory = new_factory
    except Exception as e:
        pass


def _is_camera_alive(cam):
    """Kiểm tra camera dxcam còn đang sống và thread capture còn hoạt động không (Fast 0ms Detection)."""
    if cam is None or getattr(cam, 'is_released', False):
        return False
    if not getattr(cam, 'is_capturing', False):
        return False
    thread = getattr(cam, '_DXCamera__thread', None)
    if thread is not None and not thread.is_alive():
        return False
    return True


def _attach_input_desktop():
    """Gán luồng hiện tại vào Input Desktop đang active của Windows (tránh lỗi E_ACCESSDENIED 0x80070005 khi rút cáp/đổi desktop)."""
    try:
        user32 = ctypes.windll.user32
        hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
        if hdesk:
            user32.SetThreadDesktop(hdesk)
            user32.CloseDesktop(hdesk)
    except Exception:
        pass


def _create_camera_with_retry(output_idx=0, max_retries=10, delay=0.05):
    """Tạo dxcam với cơ chế thử lại nhiều lần khi Windows đang chuyển đổi màn hình (rút/cắm cáp)."""
    global _current_output_idx
    target_idx = output_idx
    for attempt in range(max_retries):
        try:
            _attach_input_desktop()
            _reset_dxcam()
            # Trước khi tạo, đếm số lượng output thực tế trên device 0 từ factory mới
            factory = getattr(dxcam, '__factory', None)
            total_outputs = 0
            if factory is not None and hasattr(factory, 'outputs') and len(factory.outputs) > 0:
                total_outputs = len(factory.outputs[0])
            # Nếu output_idx >= số lượng output hiện có, tự động hạ output_idx = 0
            if total_outputs > 0 and target_idx >= total_outputs:
                print(f"[CAPTURE] Output index {target_idx} exceeds available outputs ({total_outputs}), falling back to 0")
                target_idx = 0
            cam = dxcam.create(output_idx=target_idx, output_color="BGR")
            # Kiểm tra is_released trước khi trả về camera
            if cam is not None and not getattr(cam, 'is_released', False):
                _current_output_idx = target_idx
                return cam
        except Exception as e:
            pass
        # Cooldown backoff delay
        current_delay = delay * (1.2 ** attempt)
        time.sleep(current_delay)
    return None



def _get_camera_frame_safe(cam, timeout=0.05):
    """Lấy frame từ dxcam với timeout thực sự (tránh while True vô hạn trong get_latest_frame khi DXGI gặp lỗi 0x887A0026)."""
    if cam is None or getattr(cam, 'is_released', False):
        return None
    try:
        ev = getattr(cam, '_DXCamera__frame_available', None)
        if ev is not None:
            if not ev.wait(timeout=timeout):
                return None
            lock = getattr(cam, '_DXCamera__lock', None)
            runtime = getattr(cam, '_DXCamera__capture_runtime', None)
            if lock and runtime:
                with lock:
                    latest = runtime.peek_latest_with_ticks(copy=True)
                    ev.clear()
                    if latest is not None:
                        return latest[0]
                return None
        return cam.grab()
    except Exception:
        return None


def _stop_and_release_camera():
    """Dừng capture và giải phóng camera dxcam hoàn toàn, dọn sạch singleton."""
    global _camera
    if _camera is not None:
        cam = _camera
        _camera = None
        try:
            stop_ev = getattr(cam, '_DXCamera__stop_capture', None)
            if stop_ev is not None:
                stop_ev.set()
            frame_ev = getattr(cam, '_DXCamera__frame_available', None)
            if frame_ev is not None:
                frame_ev.set()
        except Exception:
            pass
        try:
            if getattr(cam, 'is_capturing', False):
                cam.stop()
        except Exception:
            pass
        try:
            if hasattr(cam, 'release') and not getattr(cam, 'is_released', False):
                cam.release()
        except Exception:
            pass
    _reset_dxcam()


def _start_camera_safe():
    """Bắt đầu continuous capture an toàn, tránh gọi start() khi đang capturing hoặc đã release."""
    global _camera
    if _camera is None or getattr(_camera, 'is_released', False):
        return False
    try:
        if getattr(_camera, 'is_capturing', False):
            return True
        _camera.start(target_fps=MAX_FPS, video_mode=True)
        return True
    except Exception as e:
        print(f"[CAPTURE] Error starting camera: {e}", file=sys.stderr)
        return False


_current_output_idx = 0
_target_output_idx = 0
_display_switch_requested = False

def get_display_list():
    """Get list of active monitors on Windows via DXGI Factory metadata."""
    displays = []
    try:
        _reset_dxcam()
        if hasattr(dxcam, '__factory') and dxcam.__factory is not None:
            factory = dxcam.__factory
            for dev_idx, dev in enumerate(factory.devices):
                if dev_idx < len(factory.outputs):
                    for out_idx, out in enumerate(factory.outputs[dev_idx]):
                        try:
                            w = getattr(out, 'width', None) or _screen_w or 1920
                            h = getattr(out, 'height', None) or _screen_h or 1080
                            displays.append({
                                "id": out_idx,
                                "name": f"Màn hình {out_idx + 1} ({w}x{h})" if w and h else f"Màn hình {out_idx + 1}",
                                "width": w,
                                "height": h,
                                "is_current": (out_idx == _current_output_idx)
                            })
                        except Exception:
                            pass
    except Exception as e:
        print(f"[DISPLAY] Enum error: {e}", file=sys.stderr)
    if not displays:
        displays = [{"id": 0, "name": f"Màn hình 1 ({_screen_w}x{_screen_h})", "width": _screen_w, "height": _screen_h, "is_current": True}]
    return displays


def switch_display(output_idx):
    """Switch active capture display output (delegated safely to capture worker thread)."""
    global _target_output_idx, _display_switch_requested
    try:
        _target_output_idx = int(output_idx)
        _display_switch_requested = True
        print(f"[DISPLAY] Switch requested for output {_target_output_idx}")
        return True
    except Exception as e:
        print(f"[DISPLAY] Switch request error: {e}", file=sys.stderr)
        return False


def _init_capture():
    global _screen_w, _screen_h, _screen_info, _current_output_idx, _enc_w, _enc_h
    _screen_w = GetSystemMetrics(SM_CXSCREEN)
    _screen_h = GetSystemMetrics(SM_CYSCREEN)
    _screen_info = {"width": _screen_w, "height": _screen_h, "scale": SCALE_PERCENT, "codec": "h264"}
    if SCALE_PERCENT < 100:
        import math
        _enc_w = math.ceil(_screen_w * SCALE_PERCENT / 100 / 2) * 2
        _enc_h = math.ceil(_screen_h * SCALE_PERCENT / 100 / 2) * 2
    else:
        _enc_w, _enc_h = _screen_w, _screen_h
    return True


# === H.264 Encoding (PyAV) ===
def _pick_encoder():
    """Chọn encoder H264 tốt nhất có sẵn trên máy: NVENC -> QSV -> AMF -> libx264."""
    if H264_ENCODER != "auto":
        return H264_ENCODER
    for name in ("h264_nvenc", "h264_qsv", "h264_amf", "libx264"):
        if name not in av.codecs_available:
            continue
        try:
            c = av.CodecContext.create(name, 'w')
            c.width = 320; c.height = 240; c.pix_fmt = 'yuv420p'
            c.time_base = Fraction(1, 60); c.bit_rate = 1000000
            c.options = {'g': '30'}
            c.encode(av.VideoFrame.from_ndarray(np.zeros((240, 320, 3), np.uint8), format='bgr24'))
            return name
        except Exception:
            continue
    return "libx264"


def _init_encoder(width, height):
    global _encoder_codec, _enc_w, _enc_h
    _enc_w = width
    _enc_h = height
    enc = _pick_encoder()
    _encoder_codec = av.CodecContext.create(enc, 'w')
    _encoder_codec.width = width
    _encoder_codec.height = height
    _encoder_codec.pix_fmt = 'yuv420p'
    _encoder_codec.time_base = Fraction(1, MAX_FPS)
    _encoder_codec.bit_rate = H264_BITRATE
    if enc == "h264_nvenc":
        _encoder_codec.options = {
            'preset': 'p5',            # p1..p7; p5 nhanh hơn p6, chất lượng tương đương (chuẩn K/O)
            'tune': 'll',              # low latency
            'rc': 'constqp',           # constqp + qp = capped CQ (QP cố định, cap maxrate)
            'qp': '16',                # qp 22->16: giảm ô vuông (macroblocking) đáng kể
            'qmin': '16',              # giữ chất lượng tối đa
            'qmax': '28',              # qmax 40->28: chặn blocky cực độ khi bị cap
            'b': str(H264_BITRATE),
            'maxrate': str(H264_MAXRATE),
            'bufsize': str(H264_BUFSIZE),
            'g': str(H264_KEYINT),
            'min-keyint': '1',         # NEW [P_new]: 1 - đã có, NVENC sẽ tôn trọng force-IDR (lookahead=0)
            'bf': '0',                 # bf 2->0 (B-frame gây artifact khi motion nhanh)
            'rc-lookahead': '0',       # 12->0: NVENC bỏ qua pict_type=I khi lookahead>0
            'multipass': 'fullres',    # 2-pass rate control, phân bổ bit tối ưu cho motion
            'spatial-aq': '1',         # AQ chuẩn NVENC
            'aq-strength': '8',        # aq 6->8: giảm ô vuông vùng phức tạp (chuẩn K)
            'forced-idr': '1',         # IDR kèm SPS/PPS
        }
        _encoder_codec.thread_count = 2
        print(f"[ENCODER] NVENC h264 [P_new]: {width}x{height} @ constqp qp=16 (qmin16/qmax28) cap={H264_MAXRATE // 1000000}M buf={H264_BUFSIZE // 1000000}M | keyint={H264_KEYINT} | preset=p5 tune=ll bf=0 lookahead=0 multipass=fullres aq=8")
    elif enc == "h264_qsv":
        _encoder_codec.options = {
            'preset': 'medium',        # QSV nhanh, CPU nhe
            'rc': 'vbr',
            'maxrate': str(H264_MAXRATE),
            'bufsize': str(H264_BUFSIZE),
            'g': str(H264_KEYINT),
            'bf': '0',
        }
        _encoder_codec.thread_count = 2
        print(f"[ENCODER] Intel QSV h264: {width}x{height} @ {H264_BITRATE // 1000000}Mbps | preset=medium bf=0")
    elif enc == "h264_amf":
        _encoder_codec.options = {
            'usage': 'lowlatency',
            'quality': 'quality',
            'rc': 'vbr_peak',
            'maxrate': str(H264_MAXRATE),
            'bufsize': str(H264_BUFSIZE),
            'g': str(H264_KEYINT),
            'bf': '0',
        }
        _encoder_codec.thread_count = 2
        print(f"[ENCODER] AMD AMF h264: {width}x{height} @ {H264_BITRATE // 1000000}Mbps | usage=lowlatency bf=0")
    else:
        _encoder_codec.options = {
            'preset': H264_PRESET,
            'tune': H264_TUNE,
            'profile': H264_PROFILE,
            'g': str(H264_KEYINT),
            'keyint': str(H264_KEYINT),
            'min-keyint': '1',           # 1: cho phép force IDR ngay khi client mới connect (chặn → đen màn hình khi reconnect)
            'bf': '0',                 # No B-frames -> no reorder -> less ghosting
            'rc-lookahead': '0',       # No look-ahead reorder (low latency)
            'crf': '16',               # CRF constant quality 16 (Test O)
        }
        _encoder_codec.thread_count = _cpu_count # use all available cores for encode
        print(f"[ENCODER] PyAV libx264: {width}x{height} @ CRF 16 | threads={_cpu_count} | bf=0")
    return True


def _stop_encoder():
    global _encoder_codec, _encode_stop
    _encode_stop = True
    with _encode_lock:
        _encode_notify.notify_all()
    if _encoder_codec:
        try:
            del _encoder_codec
        except Exception:
            pass
        _encoder_codec = None
    print("[ENCODER] Stopped")


def _ensure_encode_thread():
    """NEW [P_new]: spawn encode thread khi stream bắt đầu."""
    global _encode_thread, _encode_stop
    if _encode_thread is not None and _encode_thread.is_alive():
        return
    _encode_stop = False
    _encode_thread = threading.Thread(target=_encode_loop, daemon=True, name="encode-loop")
    _encode_thread.start()


def _encode_loop():
    """NEW [P_new]: thread encode chạy độc lập với capture.
    - Lấy frame mới nhất từ _encode_queue (size=1, drop nếu đầy → encode chậm không khiến capture treo)
    - Convert BGR->YUV420P 1 lần bằng frame.reformat(format='yuv420p') (sw_scale nội bộ PyAV)
    - Dither thực hiện ở đây (sau khi lấy frame khỏi queue) - không làm capture thread chậm
    - Không còn _encode_gop_count tự đánh I (NVENC min-keyint=1 đã tôn trọng force-IDR)
    - Frame BGR được copy vào queue để capture thread có thể reuse buffer."""
    global _latest_video, _video_id, _latest_video_data, _cached_sps, _cached_pps
    global _encode_frame_count, _encode_fps_start, _encode_fps

    while not _encode_stop:
        bgr_copy = None
        force_kf = False
        with _encode_lock:
            while not _encode_queue and not _encode_stop:
                _encode_notify.wait(timeout=0.005)
            if _encode_stop:
                break
            bgr_copy, force_kf = _encode_queue.popleft()
        if bgr_copy is None:
            continue

        # Scale nếu cần
        if SCALE_PERCENT < 100 and (bgr_copy.shape[1] != _enc_w or bgr_copy.shape[0] != _enc_h):
            import cv2
            bgr_copy = cv2.resize(bgr_copy, (_enc_w, _enc_h), interpolation=cv2.INTER_LINEAR)

        # Dithering trước encode: phá banding (P_new vẫn dùng int16+clip chuẩn testP)
        # FIX [P_new]: gán trực tiếp vào module-global _dither_tile (không dùng nonlocal vì
        # _dither_tile đã là global). Vấn đề cũ: trong _encode_loop, dòng `_dither_tile = ...`
        # khiến Python coi _dither_tile là local của hàm → 'UnboundLocalError' khi đọc ở
        # dòng sau. Thêm 'global _dither_tile' để sửa.
        if H264_DITHER > 0:
            global _dither_tile
            h, w = bgr_copy.shape[:2]
            if _dither_tile is None or _dither_tile.shape[:2] != (h, w):
                tile_w, tile_h = 64, 64
                tile = np.random.randint(-H264_DITHER, H264_DITHER + 1, (tile_h, tile_w, 3), dtype=np.int16)
                _dither_tile = np.tile(tile, (h // tile_h + 1, w // tile_w + 1, 1))[:h, :w]
            bgr_copy = np.clip(bgr_copy.astype(np.int16) + _dither_tile, 0, 255).astype(np.uint8)

        # NEW: from_ndarray bgr24 → frame.reformat(yuv420p): sw_scale nội bộ, nhanh hơn cv2 cvtColor
        frame = av.VideoFrame.from_ndarray(bgr_copy, format='bgr24')
        if _enc_w and _enc_h and (frame.width != _enc_w or frame.height != _enc_h):
            frame = frame.reformat(format='yuv420p', width=_enc_w, height=_enc_h)
        else:
            frame = frame.reformat(format='yuv420p')

        if force_kf:
            frame.pict_type = PictureType.I

        if _encoder_codec is None:
            continue

        try:
            packets = _encoder_codec.encode(frame)
        except Exception as e:
            print(f"[ENCODE] error: {e}", file=sys.stderr)
            continue

        for pkt in packets:
            data = bytes(pkt)
            if len(data) < 4:
                continue
            if _cached_sps is None or _cached_pps is None:
                _extract_sps_pps(data)
            is_key = _has_idr(data)
            with _video_lock:
                _latest_video = data
                _video_id += 1
                _latest_video_data = (_video_id, data, is_key)

        # FPS counter
        _encode_frame_count += 1
        now_enc = time.monotonic()
        if _encode_fps_start == 0:
            _encode_fps_start = now_enc
        elif now_enc - _encode_fps_start >= 5.0:
            _encode_fps = _encode_frame_count / (now_enc - _encode_fps_start)
            _encode_frame_count = 0
            _encode_fps_start = now_enc


def _encode_frame(bgr_frame, force_keyframe=False):
    """NEW [P_new]: chỉ đẩy frame vào queue, encode loop sẽ xử lý.
    - Nếu queue đầy → drop frame (encode chậm hơn capture thì drop frame cũ)
    - Copy frame để capture thread có thể reuse buffer ngay."""
    global _force_keyframe_next
    if _encoder_codec is None or bgr_frame is None:
        return
    if force_keyframe:
        _force_keyframe_next = False
    try:
        bgr_copy = bgr_frame.copy()
    except Exception:
        return
    with _encode_lock:
        had_force_kf = force_keyframe
        if _encode_queue:
            _, prev_kf = _encode_queue.popleft()  # drop frame cũ nếu encode chưa kịp
            had_force_kf = had_force_kf or prev_kf
        _encode_queue.append((bgr_copy, had_force_kf))
        _encode_notify.notify()


def _capture_loop():
    """
    NEW [P_new]: capture thuần túy trong worker thread riêng biệt.
    - Tự động gắn quyền Input Desktop (OpenInputDesktop / SetThreadDesktop) an toàn.
    - Xử lý chuyển đổi màn hình và hotplug ngay trong context của worker thread.
    - Grab frame từ dxcam + đẩy vào _encode_queue qua _encode_frame().
    """
    global _camera, _current_output_idx, _target_output_idx, _display_switch_requested
    global _screen_w, _screen_h, _enc_w, _enc_h, _screen_info, _force_keyframe_next, _streaming_active

    _attach_input_desktop()
    _current_output_idx = _target_output_idx
    _camera = _create_camera_with_retry(_current_output_idx, max_retries=10, delay=0.05)
    if _camera is not None:
        w = getattr(_camera, 'width', None)
        h = getattr(_camera, 'height', None)
        if w and h:
            _screen_w, _screen_h = w, h
            if SCALE_PERCENT < 100:
                import math
                _enc_w = math.ceil(_screen_w * SCALE_PERCENT / 100 / 2) * 2
                _enc_h = math.ceil(_screen_h * SCALE_PERCENT / 100 / 2) * 2
            else:
                _enc_w, _enc_h = _screen_w, _screen_h
            _init_encoder(_enc_w, _enc_h)
            _ensure_encode_thread()
        _start_camera_safe()
        print(f"[CAPTURE] Continuous capture started on output {_current_output_idx}: {_screen_w}x{_screen_h}")
    else:
        print(f"[CAPTURE] Failed to create camera on output {_current_output_idx}", file=sys.stderr)

    last_frame_time = time.monotonic()

    while _streaming_active:
        try:
            if _display_switch_requested:
                _display_switch_requested = False
                print(f"[CAPTURE] Processing display switch to output {_target_output_idx}...")
                _stop_and_release_camera()
                _attach_input_desktop()
                _current_output_idx = _target_output_idx
                _camera = _create_camera_with_retry(_current_output_idx, max_retries=10, delay=0.05)
                if _camera is not None:
                    w = getattr(_camera, 'width', None)
                    h = getattr(_camera, 'height', None)
                    if w and h:
                        _screen_w, _screen_h = w, h
                        if SCALE_PERCENT < 100:
                            import math
                            _enc_w = math.ceil(_screen_w * SCALE_PERCENT / 100 / 2) * 2
                            _enc_h = math.ceil(_screen_h * SCALE_PERCENT / 100 / 2) * 2
                        else:
                            _enc_w, _enc_h = _screen_w, _screen_h
                        _stop_encoder()
                        _init_encoder(_enc_w, _enc_h)
                        _ensure_encode_thread()
                    _start_camera_safe()
                    _force_keyframe_next = True
                    print(f"[CAPTURE] Switched successfully to output {_current_output_idx}: {_screen_w}x{_screen_h}")

            frame = _get_camera_frame_safe(_camera, timeout=0.05)
            if frame is not None:
                force_kf = _force_keyframe_next
                _encode_frame(frame, force_keyframe=force_kf)
                last_frame_time = time.monotonic()
            else:
                elapsed = time.monotonic() - last_frame_time
                is_alive = _is_camera_alive(_camera)
                # Fail-fast: neu camera chet/dung hoac timeout > 0.2s, khoi dong quy trinh phuc hoi ngay lap tuc
                if not is_alive or elapsed > 0.2:
                    print("[CAPTURE] No frames / camera dead, recovering camera (display hotplug)...")
                    _stop_and_release_camera()
                    _reset_dxcam()
                    gc.collect()
                    if not _streaming_active:
                        break
                    _attach_input_desktop()
                    # Recreate camera: 50ms initial delay, tong thoi gian tao camera moi trong khoang 50ms-100ms
                    _camera = _create_camera_with_retry(_current_output_idx, max_retries=10, delay=0.05)
                    if _camera is not None:
                        w = getattr(_camera, 'width', None)
                        h = getattr(_camera, 'height', None)
                        if w and h and (w != _screen_w or h != _screen_h):
                            _screen_w, _screen_h = w, h
                            if SCALE_PERCENT < 100:
                                import math
                                _enc_w = math.ceil(_screen_w * SCALE_PERCENT / 100 / 2) * 2
                                _enc_h = math.ceil(_screen_h * SCALE_PERCENT / 100 / 2) * 2
                            else:
                                _enc_w, _enc_h = _screen_w, _screen_h
                            _stop_encoder()
                            _init_encoder(_enc_w, _enc_h)
                        _start_camera_safe()
                        _ensure_encode_thread()
                        _force_keyframe_next = True
                    last_frame_time = time.monotonic()
                time.sleep(0.001)
        except Exception as e:
            if _streaming_active:
                print(f"[CAPTURE] Hotplug recovery from error: {e}", file=sys.stderr)
            _stop_and_release_camera()
            _reset_dxcam()
            gc.collect()
            time.sleep(0.05)  # Cooldown nhanh 50ms cho Windows DWM ổn định
            if not _streaming_active:
                break
            _attach_input_desktop()
            _camera = _create_camera_with_retry(_current_output_idx, max_retries=10, delay=0.05)
            if _camera is not None:
                w = getattr(_camera, 'width', None)
                h = getattr(_camera, 'height', None)
                if w and h and (w != _screen_w or h != _screen_h):
                    _screen_w, _screen_h = w, h
                    if SCALE_PERCENT < 100:
                        import math
                        _enc_w = math.ceil(_screen_w * SCALE_PERCENT / 100 / 2) * 2
                        _enc_h = math.ceil(_screen_h * SCALE_PERCENT / 100 / 2) * 2
                    else:
                        _enc_w, _enc_h = _screen_w, _screen_h
                    _stop_encoder()
                    _init_encoder(_enc_w, _enc_h)
                _start_camera_safe()
                _ensure_encode_thread()
                _force_keyframe_next = True
            last_frame_time = time.monotonic()


# === NAL Unit Helpers ===
def _find_nal_units(data):
    """Find Annex-B start codes using C-speed bytes.find() (was byte-by-byte loop).
    Byte-by-byte scan cost ~122ms per 500KB packet; bytes.find() costs <1ms."""
    nals = []
    i = 0
    n = len(data)
    while i < n - 3:
        j = data.find(b'\x00\x00\x01', i)
        if j < 0 or j > n - 4:
            break
        if j > 0 and data[j - 1] == 0:
            nals.append((j - 1, 4))
        else:
            nals.append((j, 3))
        i = j + 3
    return nals


def _extract_sps_pps(data):
    global _cached_sps, _cached_pps
    nals = _find_nal_units(data)
    for idx, (pos, sc_len) in enumerate(nals):
        nal_type = data[pos + sc_len] & 0x1F
        # Find end of this NAL (start of next NAL or end of data)
        if idx + 1 < len(nals):
            end = nals[idx + 1][0]
        else:
            end = len(data)
        nal_data = data[pos:end]
        if nal_type == 7 and _cached_sps is None:
            _cached_sps = nal_data
            print(f"[NAL] SPS cached: {len(nal_data)} bytes")
        elif nal_type == 8 and _cached_pps is None:
            _cached_pps = nal_data
            print(f"[NAL] PPS cached: {len(nal_data)} bytes")


def _has_idr(data):
    nals = _find_nal_units(data)
    for pos, sc_len in nals:
        nal_type = data[pos + sc_len] & 0x1F
        if nal_type == 5:
            return True
    return False


def _has_sps_pps(data):
    nals = _find_nal_units(data)
    for pos, sc_len in nals:
        nal_type = data[pos + sc_len] & 0x1F
        if nal_type in (7, 8):
            return True
    return False

# === Audio Capture (Universal Detection) ===
# Global variables for audio capture state
_audio_capture_method = None  # 'wasapi_loopback', 'stereo_mix', 'input_device'
_audio_capture_device = None
_audio_wasapi_client = None
_audio_wasapi_capture = None
_audio_wasapi_fmt = None
_audio_wasapi_pcm16 = None

# WASAPI COM GUIDs
_CLSID_MMDeviceEnumerator = None
_IID_IMMDeviceEnumerator = None
_IID_IAudioClient = None
_IID_IAudioCaptureClient = None


def _init_wasapi_guids():
    """Initialize WASAPI COM GUIDs."""
    global _CLSID_MMDeviceEnumerator, _IID_IMMDeviceEnumerator
    global _IID_IAudioClient, _IID_IAudioCaptureClient
    try:
        from comtypes import GUID as COMGUID
        _CLSID_MMDeviceEnumerator = COMGUID("{BCDE0395-E52F-467C-8E3D-C4579291692E}")
        _IID_IMMDeviceEnumerator = COMGUID("{A95664D2-9614-4F35-A746-DE8DB63617E6}")
        _IID_IAudioClient = COMGUID("{1CB9AD4C-DBFA-4C32-B178-C2F568A703B2}")
        _IID_IAudioCaptureClient = COMGUID("{C8ADBD64-7417-4E63-84C5-6C0C1E6E7DA0}")
        return True
    except ImportError:
        return False


class WAVEFORMATEX(ctypes.Structure):
    _fields_ = [
        ("wFormatTag", ctypes.c_ushort),
        ("nChannels", ctypes.c_ushort),
        ("nSamplesPerSec", ctypes.c_ulong),
        ("nAvgBytesPerSec", ctypes.c_ulong),
        ("nBlockAlign", ctypes.c_ushort),
        ("wBitsPerSample", ctypes.c_ushort),
        ("cbSize", ctypes.c_ushort),
    ]


def _detect_audio_devices():
    """
    Universal audio device detection across all Windows audio APIs.
    Returns list of capture-capable devices with their properties.
    """
    devices = []

    try:
        import sounddevice as sd
    except ImportError:
        return devices

    sd_devices = sd.query_devices()
    hostapis = sd.query_hostapis()

    # Known loopback device name patterns
    loopback_patterns = [
        'stereo mix', 'what u hear', 'wave out', 'mix',
        'loopback', 'monitor', 'waveout', 'synth'
    ]

    for i, dev in enumerate(sd_devices):
        ha = hostapis[dev['hostapi']]
        name_lower = dev['name'].lower()

        # Check if device has input channels
        if dev['max_input_channels'] <= 0:
            continue

        # Determine if this is a loopback device (captures system audio)
        is_loopback = any(pattern in name_lower for pattern in loopback_patterns)

        # WASAPI output devices can be used for loopback via ctypes
        is_wasapi_output = (
            'wasapi' in ha['name'].lower() and
            dev['max_output_channels'] > 0 and
            dev['max_input_channels'] == 0
        )

        devices.append({
            'index': i,
            'name': dev['name'],
            'api': ha['name'],
            'channels': dev['max_input_channels'],
            'sample_rate': int(dev['default_samplerate']),
            'is_loopback': is_loopback,
            'is_wasapi_output': is_wasapi_output,
        })

    return devices


def _try_capture_device(device_info, duration_ms=100):
    """
    Test if a device can capture audio.
    Returns True if successful, False otherwise.
    """
    try:
        import sounddevice as sd
        import numpy as np

        bs = int(device_info['sample_rate'] * 0.02)
        stream = sd.InputStream(
            device=device_info['index'],
            channels=min(2, device_info['channels']),
            samplerate=device_info['sample_rate'],
            dtype='int16',
            blocksize=bs,
        )
        stream.start()
        time.sleep(duration_ms / 1000.0)
        data, overflow = stream.read(bs)
        stream.stop()
        stream.close()

        if data is not None and len(data) > 0:
            return True
        return False
    except Exception:
        return False


def _try_wasapi_loopback_ctypes():
    """
    Try WASAPI loopback capture using ctypes COM calls.
    Works on most modern Windows systems (Windows 10/11).
    """
    global _audio_wasapi_client, _audio_wasapi_capture, _audio_wasapi_fmt, _audio_wasapi_pcm16

    if not _init_wasapi_guids():
        return False

    try:
        from comtypes._post_coinit.misc import _CoCreateInstance
        from comtypes import GUID as COMGUID
        LP_GUID = ctypes.POINTER(COMGUID)

        # Create device enumerator
        enumerator_ptr = ctypes.c_void_p()
        hr = _CoCreateInstance(
            ctypes.byref(_CLSID_MMDeviceEnumerator), None, 0x17,
            ctypes.byref(_IID_IMMDeviceEnumerator), ctypes.byref(enumerator_ptr)
        )
        if hr < 0:
            return False

        # GetDefaultAudioEndpoint (index 4 in vtable)
        vtable_ptr_ptr = ctypes.cast(enumerator_ptr, ctypes.POINTER(ctypes.c_void_p))
        vtable_ptr = vtable_ptr_ptr.contents
        vtable = ctypes.cast(vtable_ptr, ctypes.POINTER(ctypes.c_void_p * 20))
        GetDefaultAudioEndpoint_ptr = vtable.contents[4]
        proto = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p))
        GetDefaultAudioEndpoint = proto(GetDefaultAudioEndpoint_ptr)

        device_ptr = ctypes.c_void_p()
        hr = GetDefaultAudioEndpoint(enumerator_ptr, 0, 1, ctypes.byref(device_ptr))
        if hr < 0:
            return False

        # Activate IAudioClient
        dev_vtable_ptr_ptr = ctypes.cast(device_ptr, ctypes.POINTER(ctypes.c_void_p))
        dev_vtable_ptr = dev_vtable_ptr_ptr.contents
        dev_vtable = ctypes.cast(dev_vtable_ptr, ctypes.POINTER(ctypes.c_void_p * 20))
        Activate_ptr = dev_vtable.contents[3]
        activate_proto = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, LP_GUID, ctypes.c_ulong, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
        Activate = activate_proto(Activate_ptr)

        audio_client_ptr = ctypes.c_void_p()
        hr = Activate(device_ptr, ctypes.byref(_IID_IAudioClient), 0x17, None, ctypes.byref(audio_client_ptr))
        if hr < 0:
            return False

        # Access IAudioClient vtable
        client_vtable_ptr_ptr = ctypes.cast(audio_client_ptr, ctypes.POINTER(ctypes.c_void_p))
        client_vtable_ptr = client_vtable_ptr_ptr.contents
        client_vtable = ctypes.cast(client_vtable_ptr, ctypes.POINTER(ctypes.c_void_p * 20))

        # GetMixFormat
        GetMixFormat_ptr = client_vtable.contents[8]
        getmix_proto = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(ctypes.POINTER(WAVEFORMATEX)))
        GetMixFormat = getmix_proto(GetMixFormat_ptr)

        format_ptr = ctypes.POINTER(WAVEFORMATEX)()
        hr = GetMixFormat(audio_client_ptr, ctypes.byref(format_ptr))
        if hr < 0:
            return False

        fmt = format_ptr.contents
        _audio_wasapi_fmt = fmt

        # Create PCM 16-bit format for capture
        pcm16 = WAVEFORMATEX()
        pcm16.wFormatTag = 1  # PCM
        pcm16.nChannels = fmt.nChannels
        pcm16.nSamplesPerSec = fmt.nSamplesPerSec
        pcm16.wBitsPerSample = 16
        pcm16.nBlockAlign = pcm16.nChannels * 2
        pcm16.nAvgBytesPerSec = pcm16.nSamplesPerSec * pcm16.nBlockAlign
        pcm16.cbSize = 0
        _audio_wasapi_pcm16 = pcm16

        # Initialize with loopback flag
        Initialize_ptr = client_vtable.contents[3]
        init_proto = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_int, ctypes.c_ulong,
                                       ctypes.c_longlong, ctypes.c_longlong, ctypes.POINTER(WAVEFORMATEX), ctypes.POINTER(COMGUID))
        Initialize = init_proto(Initialize_ptr)

        hr = Initialize(audio_client_ptr, 0, 0x00020000, 10000000, 0, ctypes.byref(pcm16), None)
        if hr < 0:
            return False

        # Get capture client
        GetService_ptr = client_vtable.contents[14]
        getsvc_proto = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, LP_GUID, ctypes.POINTER(ctypes.c_void_p))
        GetService = getsvc_proto(GetService_ptr)

        capture_ptr = ctypes.c_void_p()
        hr = GetService(audio_client_ptr, ctypes.byref(_IID_IAudioCaptureClient), ctypes.byref(capture_ptr))
        if hr < 0 or not capture_ptr.value:
            return False

        # Start recording
        Start_ptr = client_vtable.contents[10]
        start_proto = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)
        Start = start_proto(Start_ptr)
        hr = Start(audio_client_ptr)
        if hr < 0:
            return False

        _audio_wasapi_client = audio_client_ptr
        _audio_wasapi_capture = capture_ptr
        return True

    except Exception as e:
        print(f"[AUDIO] WASAPI ctypes error: {e}", file=sys.stderr)
        return False


def _try_soundcard_loopback():
    """
    Try WASAPI loopback via the 'soundcard' library.
    Loopback captures the stream BEFORE the endpoint/device volume is applied,
    so the source is independent of Windows device volume (volume=0 still yields audio).
    """
    global _audio_capture_device
    try:
        import soundcard as sc
        import numpy as np

        mics = sc.all_microphones(include_loopback=True)
        loop = [m for m in mics if 'Loopback' in str(m)]
        if not loop:
            return False

        # Prefer a Realtek loopback speaker (matches default output)
        mic = None
        for m in loop:
            if 'Realtek' in str(m):
                mic = m
                break
        if mic is None:
            mic = loop[0]

        sample_rate = 48000
        channels = 2
        block_len = int(sample_rate * 0.02)
        with mic.recorder(samplerate=sample_rate, channels=channels, blocksize=block_len) as rec:
            data = rec.record(numframes=int(sample_rate * 0.1))  # 100ms test
        if data is not None and len(data) > 0:
            _audio_capture_device = {
                'mic': mic,
                'name': str(mic),
                'sample_rate': sample_rate,
                'channels': channels,
            }
            return True
        return False
    except Exception as e:
        print(f"[AUDIO] soundcard loopback error: {e}", file=sys.stderr)
        return False


def _find_best_audio_device():
    """
    Universal audio device finder.
    Tries multiple methods in order of preference:
    1. soundcard WASAPI loopback (pre-volume, volume-independent source)
    2. WASAPI loopback ctasy (system audio capture)
    3. Stereo Mix / What U Hear devices
    4. Any available input device (microphone)
    """
    global _audio_capture_method, _audio_capture_device

    print("[AUDIO] Detecting audio devices...")

    # Method 0: soundcard WASAPI loopback (best: independent of device volume)
    print("[AUDIO] Trying soundcard WASAPI loopback...")
    if _try_soundcard_loopback():
        _audio_capture_method = 'wasapi_loopback_sd'
        print(f"[AUDIO] soundcard WASAPI loopback initialized: {_audio_capture_device['name']}")
        return True
    print("[AUDIO] soundcard WASAPI loopback not available, falling back...")

    # Get all capture-capable devices
    devices = _detect_audio_devices()
    if not devices:
        print("[AUDIO] No audio input devices found")
        return False

    print(f"[AUDIO] Found {len(devices)} input device(s):")
    for dev in devices:
        loopback_tag = " [LOOPBACK]" if dev['is_loopback'] else ""
        print(f"  [{dev['index']:2d}] {dev['name'][:40]:40s} {dev['api']:15s} {dev['sample_rate']}Hz{loopback_tag}")

    # Method 1: Try WASAPI loopback via ctypes (best quality, system audio)
    print("[AUDIO] Trying WASAPI loopback (ctypes)...")
    if _try_wasapi_loopback_ctypes():
        _audio_capture_method = 'wasapi_loopback'
        _audio_capture_device = 'default_speakers'
        print("[AUDIO] WASAPI loopback initialized successfully!")
        return True
    print("[AUDIO] WASAPI loopback not available")

    # Method 2: Try known loopback devices (Stereo Mix, What U Hear, etc.)
    # Prefer WASAPI loopback devices (better quality, less noise) over MME/DirectSound
    loopback_devices = [d for d in devices if d['is_loopback']]
    # Sort: WASAPI first, then WDM-KS, then DirectSound, then MME
    api_priority = {'Windows WASAPI': 0, 'Windows WDM-KS': 1, 'Windows DirectSound': 2, 'MME': 3}
    loopback_devices.sort(key=lambda d: api_priority.get(d['api'], 99))
    
    for dev in loopback_devices:
        print(f"[AUDIO] Trying loopback device: {dev['name']} ({dev['api']} {dev['sample_rate']}Hz)")
        if _try_capture_device(dev):
            _audio_capture_method = 'stereo_mix'
            _audio_capture_device = dev
            print(f"[AUDIO] Loopback device working: {dev['name']}")
            return True
        print(f"[AUDIO] Device not working: {dev['name']}")

    # Method 3: Try any input device (microphone, line-in)
    for dev in devices:
        if dev['is_loopback']:
            continue
        print(f"[AUDIO] Trying input device: {dev['name']}")
        if _try_capture_device(dev):
            _audio_capture_method = 'input_device'
            _audio_capture_device = dev
            print(f"[AUDIO] Input device working: {dev['name']}")
            return True
        print(f"[AUDIO] Device not working: {dev['name']}")

    print("[AUDIO] No working audio devices found, audio disabled")
    return False


def _audio_capture_loop():
    """Main audio capture loop - adapts to the detected method."""
    global _latest_audio, _audio_id, _audio_queue
    global _audio_wasapi_client, _audio_wasapi_capture, _audio_wasapi_fmt, _audio_wasapi_pcm16

    if _audio_capture_method == 'wasapi_loopback_sd':
        _audio_soundcard_capture_loop()
    elif _audio_capture_method == 'wasapi_loopback':
        _audio_loopback_capture_loop()
    elif _audio_capture_method in ('stereo_mix', 'input_device'):
        _audio_sounddevice_capture_loop()
    else:
        print("[AUDIO] No capture method available")


def _audio_soundcard_capture_loop():
    """Capture audio using soundcard WASAPI loopback (pre-volume, independent of device volume)."""
    global _latest_audio, _audio_id, _audio_queue
    try:
        import numpy as np

        dev = _audio_capture_device
        mic = dev['mic']
        sample_rate = dev['sample_rate']
        channels = dev['channels']
        block_len = int(sample_rate * 0.02)  # 20ms block

        max_int16 = 32767.0
        soft_limit = int(max_int16 * _AUDIO_SOFT_LIMIT)

        # High-pass filter state (1-pole IIR)
        hp_alpha = np.exp(-2.0 * np.pi * _AUDIO_HIGHPASS_HZ / sample_rate) if _AUDIO_HIGHPASS_HZ > 0 else 0
        hp_x_prev = np.zeros(channels, dtype=np.float32)
        hp_y_prev = np.zeros(channels, dtype=np.float32)

        # AGC state: normalize level independent of source/device volume
        agc_gain = 1.0
        agc_target = 0.6           # target peak (normalized -1..1) ~ -4dBFS (stronger/sharp peaks)
        agc_attack = 0.8           # fast: duck quickly on loud system sounds (avoid sudden loudness)
        agc_release = 0.02         # slower: raise gain on quiet signal (avoid pumping)
        agc_min, agc_max = 0.5, 4.0
        silence_peak = 0.002       # below this, treat as silence -> hold gain (don't boost noise)

        with mic.recorder(samplerate=sample_rate, channels=channels, blocksize=block_len) as rec:
            print(f"[AUDIO] Stream started (soundcard loopback): {dev['name']} ({sample_rate}Hz, AGC on)")
            while _streaming_active:
                data = rec.record(numframes=block_len)  # (block, ch) float32 ~ -1..1
                if data is None or len(data) == 0:
                    continue
                arr = data.astype(np.float32)

                # High-pass filter to remove low-frequency hum
                if _AUDIO_HIGHPASS_HZ > 0:
                    for ch in range(channels):
                        x = arr[:, ch]
                        y = hp_alpha * (hp_y_prev[ch] + x - hp_x_prev[ch])
                        hp_x_prev[ch] = x[-1]
                        hp_y_prev[ch] = y[-1]
                        arr[:, ch] = y

                # AGC (envelope-based, not per-sample -> no harmonic distortion)
                peak = float(np.max(np.abs(arr))) if arr.size else 0.0
                if peak > silence_peak:
                    desired = agc_target / peak
                    coef = agc_attack if desired < agc_gain else agc_release
                    agc_gain += coef * (desired - agc_gain)
                    agc_gain = min(max(agc_gain, agc_min), agc_max)
                    arr = arr * agc_gain
                # else: silence -> hold current gain, do not amplify floor noise

                # Convert to int16 interleaved (L,R)
                arr16 = np.clip(arr * max_int16, -max_int16, max_int16).astype(np.int16)
                raw = arr16.ravel().tobytes()
                with _audio_lock:
                    _latest_audio = raw
                    _audio_id += 1
                    _audio_queue.append(raw)
    except Exception as e:
        print(f"[AUDIO] soundcard capture error: {e}", file=sys.stderr)


def _audio_loopback_capture_loop():
    """Capture audio using WASAPI loopback (ctypes)."""
    global _latest_audio, _audio_id, _audio_queue
    global _audio_wasapi_client, _audio_wasapi_capture, _audio_wasapi_fmt, _audio_wasapi_pcm16

    try:
        from comtypes import GUID as COMGUID
        LP_GUID = ctypes.POINTER(COMGUID)

        # Access capture client vtable
        capture_ptr = _audio_wasapi_capture
        cap_vtable_ptr_ptr = ctypes.cast(capture_ptr, ctypes.POINTER(ctypes.c_void_p))
        cap_vtable_ptr = cap_vtable_ptr_ptr.contents
        cap_vtable = ctypes.cast(cap_vtable_ptr, ctypes.POINTER(ctypes.c_void_p * 10))

        GetNextPacketSize_ptr = cap_vtable.contents[5]
        gnp_proto = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32))
        GetNextPacketSize = gnp_proto(GetNextPacketSize_ptr)

        GetBuffer_ptr = cap_vtable.contents[3]
        getbufcap_proto = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p,
                                            ctypes.POINTER(ctypes.POINTER(ctypes.c_byte)),
                                            ctypes.POINTER(ctypes.c_uint32),
                                            ctypes.POINTER(ctypes.c_uint32),
                                            ctypes.POINTER(ctypes.c_uint64),
                                            ctypes.POINTER(ctypes.c_uint64))
        GetBuffer = getbufcap_proto(GetBuffer_ptr)

        ReleaseBuffer_ptr = cap_vtable.contents[4]
        rel_proto = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_uint32)
        ReleaseBuffer = rel_proto(ReleaseBuffer_ptr)

        pcm16 = _audio_wasapi_pcm16

        while _streaming_active:
            try:
                pkt_size = ctypes.c_uint32()
                GetNextPacketSize(capture_ptr, ctypes.byref(pkt_size))
                if pkt_size.value > 0:
                    data_buf = ctypes.POINTER(ctypes.c_byte)()
                    frames_available = ctypes.c_uint32()
                    flags = ctypes.c_uint32()
                    dev_pos = ctypes.c_uint64()
                    qpc_pos = ctypes.c_uint64()
                    GetBuffer(capture_ptr, ctypes.byref(data_buf), ctypes.byref(frames_available),
                             ctypes.byref(flags), ctypes.byref(dev_pos), ctypes.byref(qpc_pos))
                    byte_count = frames_available.value * pcm16.nBlockAlign
                    audio_data = ctypes.string_at(data_buf, byte_count)
                    with _audio_lock:
                        _latest_audio = audio_data
                        _audio_id += 1
                        _audio_queue.append(audio_data)
                    ReleaseBuffer(capture_ptr, frames_available.value)
                else:
                    time.sleep(0.001)
            except Exception as e:
                if _streaming_active:
                    print(f"[AUDIO] Capture error: {e}", file=sys.stderr)
                time.sleep(0.01)

        # Stop
        client_ptr = _audio_wasapi_client
        client_vtable_ptr_ptr = ctypes.cast(client_ptr, ctypes.POINTER(ctypes.c_void_p))
        client_vtable_ptr = client_vtable_ptr_ptr.contents
        client_vtable = ctypes.cast(client_vtable_ptr, ctypes.POINTER(ctypes.c_void_p * 20))
        Stop_ptr = client_vtable.contents[11]
        stop_proto = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)
        Stop = stop_proto(Stop_ptr)
        Stop(client_ptr)

    except Exception as e:
        print(f"[AUDIO] Loopback loop error: {e}", file=sys.stderr)


def _audio_sounddevice_capture_loop():
    """Capture audio using sounddevice (Stereo Mix, microphone, etc.)."""
    global _latest_audio, _audio_id, _audio_queue, _audio_stream

    try:
        import sounddevice as sd
        import numpy as np

        dev = _audio_capture_device
        if dev is None:
            return

        channels = min(2, dev['channels'])
        sample_rate = dev['sample_rate']
        blocksize = int(sample_rate * 0.02)  # 20ms block

        stream = sd.InputStream(
            device=dev['index'],
            channels=channels,
            samplerate=sample_rate,
            dtype='int16',
            blocksize=blocksize,
            latency='low',
        )
        stream.start()
        print(f"[AUDIO] Stream started: {dev['name']} (gain={_AUDIO_GAIN}x, adaptive_gate={_AUDIO_ADAPTIVE_GATE}, hp={_AUDIO_HIGHPASS_HZ}Hz, blocksize={blocksize}, {sample_rate}Hz)")

        max_int16 = 32767.0
        soft_limit = int(max_int16 * _AUDIO_SOFT_LIMIT)
        gate_thresh = _AUDIO_GATE_THRESHOLD

        # Adaptive noise gate state
        noise_floor = 0.0
        learning = _AUDIO_ADAPTIVE_GATE
        learn_frames = 0
        learn_total = int(_AUDIO_GATE_LEARN_TIME * sample_rate / blocksize) if _AUDIO_ADAPTIVE_GATE else 0
        ema_alpha = 0.01

        # High-pass filter state (1-pole IIR)
        hp_alpha = np.exp(-2.0 * np.pi * _AUDIO_HIGHPASS_HZ / sample_rate) if _AUDIO_HIGHPASS_HZ > 0 else 0
        hp_x_prev = np.zeros(channels, dtype=np.float32)
        hp_y_prev = np.zeros(channels, dtype=np.float32)

        while _streaming_active:
            try:
                data, overflow = stream.read(blocksize)
                if overflow:
                    print(f"[AUDIO] Overflow detected", file=sys.stderr)
                if data is not None and len(data) > 0 and not overflow:
                    arr = np.frombuffer(data, dtype=np.int16).copy().astype(np.float32)

                    # High-pass filter to remove low-frequency hum
                    if _AUDIO_HIGHPASS_HZ > 0 and channels > 0:
                        arr_f = arr.reshape(-1, channels)
                        for ch in range(channels):
                            x = arr_f[:, ch]
                            y = hp_alpha * (hp_y_prev[ch] + x - hp_x_prev[ch])
                            hp_x_prev[ch] = x[-1]
                            hp_y_prev[ch] = y[-1]
                            arr_f[:, ch] = y
                        arr = arr_f.flatten()

                    # Adaptive noise gate: learn noise floor during initial silence
                    if learning:
                        rms = np.sqrt(np.mean(arr ** 2))
                        noise_floor = (noise_floor * learn_frames + rms) / (learn_frames + 1)
                        learn_frames += 1
                        if learn_frames >= learn_total:
                            gate_thresh = max(noise_floor * _AUDIO_GATE_MULTIPLIER, _AUDIO_GATE_THRESHOLD)
                            # Cap maximum gate to avoid cutting legitimate quiet audio
                            gate_thresh = min(gate_thresh, 800)
                            learning = False
                            print(f"[AUDIO] Gate ready (noise floor {noise_floor:.1f})", file=sys.stderr)
                    elif _AUDIO_ADAPTIVE_GATE:
                        # Slow EMA tracking for changing noise conditions
                        rms = np.sqrt(np.mean(arr ** 2))
                        noise_floor = noise_floor * (1 - ema_alpha) + rms * ema_alpha
                        gate_thresh = max(noise_floor * _AUDIO_GATE_MULTIPLIER, _AUDIO_GATE_THRESHOLD)
                        gate_thresh = min(gate_thresh, 800)  # Cap max gate

                    # Noise gate (only when adaptive gate enabled; OFF by default to
                    # avoid per-sample harmonic distortion / "rat rat" crackle)
                    if _AUDIO_ADAPTIVE_GATE:
                        gate_open = float(gate_thresh)
                        gate_close = gate_open * _AUDIO_HYSTERESIS
                        abs_arr = np.abs(arr)

                        if _AUDIO_SMOOTH_GATE:
                            # Smooth expander: signal below close thresh → 0
                            # Between close and open → linear fade
                            fade = np.ones_like(arr)
                            below_close = abs_arr < gate_close
                            in_knee = (abs_arr >= gate_close) & (abs_arr < gate_open)
                            if np.any(below_close):
                                fade[below_close] = 0.0
                            if np.any(in_knee):
                                fade[in_knee] = (abs_arr[in_knee] - gate_close) / (gate_open - gate_close + 1e-10)
                            arr = arr * fade
                        else:
                            mask = abs_arr < int(gate_thresh)
                            if np.any(mask):
                                arr[mask] = 0

                    # Apply gain with soft limiting
                    if _AUDIO_GAIN != 1.0:
                        arr = arr * _AUDIO_GAIN
                        arr = np.tanh(arr / soft_limit) * soft_limit
                        arr = np.clip(arr, -max_int16, max_int16)

                    raw = arr.astype(np.int16).tobytes()
                    with _audio_lock:
                        _latest_audio = raw
                        _audio_id += 1
                        _audio_queue.append(raw)
            except Exception as e:
                if _streaming_active:
                    print(f"[AUDIO] Read error: {e}", file=sys.stderr)
                time.sleep(0.01)

        stream.stop()
        stream.close()
        print("[AUDIO] Stream closed")

    except Exception as e:
        print(f"[AUDIO] Sounddevice error: {e}", file=sys.stderr)

# === Streaming Manager ===
def _ensure_streaming():
    global _streaming_active, _stop_timer, _camera
    with _stream_lock:
        if _stop_timer is not None:
            _stop_timer.cancel()
            _stop_timer = None
        if _streaming_active:
            return

        if _camera is None:
            _init_capture()

        if _encoder_codec is None:
            # Calculate scaled resolution
            if SCALE_PERCENT < 100:
                import math
                enc_w = math.ceil(_screen_w * SCALE_PERCENT / 100 / 2) * 2
                enc_h = math.ceil(_screen_h * SCALE_PERCENT / 100 / 2) * 2
            else:
                enc_w, enc_h = _screen_w, _screen_h
            _init_encoder(enc_w, enc_h)

        # Detect best audio device (universal method)
        _find_best_audio_device()

        _streaming_active = True
        print("[STREAM] Started")

        # NEW [P_new]: spawn encode thread riêng trước khi start capture
        _ensure_encode_thread()

        threading.Thread(target=_capture_loop, daemon=True).start()
        threading.Thread(target=_audio_capture_loop, daemon=True).start()


def _stop_streaming_locked():
    """Thân hàm stop, GIẢ ĐỊNH caller đã giữ _stream_lock. Không self-lock."""
    global _streaming_active, _camera, _encode_stop
    _streaming_active = False
    _encode_stop = True
    with _encode_lock:
        _encode_notify.notify_all()
    _stop_encoder()
    _stop_and_release_camera()
    print("[STREAM] Stopped")


def _stop_streaming():
    global _streaming_active, _camera, _encode_stop
    with _stream_lock:
        _stop_streaming_locked()


def _do_stop_streaming():
    global _streaming_active, _stop_timer
    # FIX [2026-08-12]: Giữ _stream_lock để vừa check clients vừa stop (đóng cửa sổ TOCTOU),
    # gọi _stop_streaming_locked (không self-lock) → HẾT deadlock (trước đây with _stream_lock
    # + _stop_streaming() self-lock → khóa non-reentrant giữ 2 lần → thread timer giữ lock vĩnh
    # viễn → mọi _ensure_streaming() block mãi → video không add → send=0.0, đen màn hình
    # khi reconnect sau khi stream đã stop).
    with _stream_lock:
        _stop_timer = None
        if not _streaming_active:
            return
        if connected_clients or audio_clients:
            return
        _stop_streaming_locked()


_idle_exit_started = False

def _maybe_stop_streaming():
    global _stop_timer, _idle_exit_started
    with _stream_lock:
        if connected_clients or audio_clients:
            return
        if _stop_timer is not None:
            return
        _stop_timer = threading.Timer(IDLE_STOP_DELAY, _do_stop_streaming)
        _stop_timer.daemon = True
        _stop_timer.start()
        # NEW [2026-08-12]: Chỉ khởi động idle exit monitor ở lần đầu (server startup).
        # Trước đây _schedule_idle_exit() được gọi ở mỗi lần client disconnect →
        # tạo hàng chục thread monitor rác, và trong thời gian kick old session
        # (reconnect cùng IP), monitor mới có thể đếm idle sai → os._exit phá hỏng stream.
        if not _idle_exit_started:
            _idle_exit_started = True
            _schedule_idle_exit()


def _schedule_idle_exit():
    """Watchdog định kỳ: không có client nào trong IDLE_PROCESS_EXIT giây → thoát process sạch.
    Wrapper ngoài (server_manager.py) sẽ restart khi nhận connect request mới.
    Chạy độc lập từ khi server start (không phụ thuộc _maybe_stop_streaming)."""
    _idle_since = None

    def _monitor():
        nonlocal _idle_since
        while True:
            time.sleep(2.0)
            if connected_clients or audio_clients:
                _idle_since = None
                continue
            now = time.monotonic()
            if _idle_since is None:
                _idle_since = now
            elif now - _idle_since >= IDLE_PROCESS_EXIT:
                print(f"[IDLE] No clients for {IDLE_PROCESS_EXIT}s, exiting process cleanly.", file=sys.stderr)
                # KHÔNG gọi _stop_streaming() — nó có thể treo (camera.stop/encoder flush),
                # làm os._exit không bao giờ chạy → process sống mãi. os._exit tự thu hồi tài nguyên.
                os._exit(0)

    t = threading.Thread(target=_monitor, daemon=True)
    t.start()


def get_latest_video():
    with _video_lock:
        return _latest_video


def get_video_id():
    with _video_lock:
        return _video_id


def get_latest_audio():
    with _audio_lock:
        return _latest_audio


def drain_audio_queue():
    with _audio_lock:
        if not _audio_queue:
            return []
        pkts = list(_audio_queue)
        _audio_queue.clear()
        return pkts


def drain_video_queue():
    """Get and clear the latest video frame (thread-safe)."""
    global _latest_video_data
    with _video_lock:
        data = _latest_video_data
        _latest_video_data = None
        if data is None:
            return []
        return [data]


def _get_latest_frame():
    """Get and clear the latest frame (thread-safe, for stream loop)."""
    global _latest_video_data
    with _video_lock:
        data = _latest_video_data
        _latest_video_data = None
        return data

# === HTTP Server ===
class ViewerHandler(SimpleHTTPRequestHandler):
    # NEW [P_new]: serve viewer_H264wss_P_new.html
    VIEWER_FILE = '/viewer_H264wss_P_new.html'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def do_GET(self):
        print(f"[HTTP] GET {self.path} from {self.client_address}")
        if self.path == '/':
            self.send_response(302)
            self.send_header('Location', self.VIEWER_FILE)
            self.end_headers()
            return
        allowed_files = (
            self.VIEWER_FILE,
            '/viewer_H264wss_P_wgl.html',  # P_wgl cho test GPU path (cùng server P)
            '/viewer_H264wss.html',        # fallback bản gốc
            '/audio-processor.js', '/favicon.ico',
            '/broadway-decoder.js', '/broadway-yuv.js', '/broadway-player.js',
            '/broadway-avc.wasm', '/avc.wasm', '/viewer.html',
        )
        if self.path in allowed_files:
            full = os.path.join(WEB_DIR, self.path.lstrip('/'))
            if not os.path.isfile(full):
                self.send_response(404)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                self.wfile.write(b'Not Found')
                return
            self.send_response(200)
            self.send_header('Cross-Origin-Embedder-Policy', 'require-corp')
            self.send_header('Cross-Origin-Opener-Policy', 'same-origin')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Content-Type', self.guess_type(self.path))
            self.end_headers()
            with open(full, 'rb') as f:
                self.wfile.write(f.read())
        else:
            self.send_response(404)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Not Found')

    def log_message(self, format, *args):
        pass


class ReusableHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    allow_reuse_port = True
    daemon_threads = True
    ssl_ctx = None

    def handle_error(self, request, client_address):
        exc = sys.exc_info()[1]
        # FIX [2026-08-12]: Bỏ qua các lỗi network I/O thông thường (client ngắt đột ngột,
        # reset connection) — không phải lỗi server, tránh spam traceback trong log.
        if isinstance(exc, (ssl.SSLError, ConnectionResetError, ConnectionAbortedError, BrokenPipeError)):
            return
        super().handle_error(request, client_address)

    def get_request(self):
        sock, addr = self.socket.accept()
        if self.ssl_ctx is not None:
            # FIX [2026-08-12]: bọc wrap_socket để không để exception lan ra handle_error
            # khi client ngắt giữa lúc handshake → tránh spam log 10054.
            try:
                sock = self.ssl_ctx.wrap_socket(sock, server_side=True, do_handshake_on_connect=False)
            except Exception:
                try:
                    sock.close()
                except Exception:
                    pass
                raise
        return sock, addr


def start_http_server():
    try:
        server = ReusableHTTPServer((HOST, HTTP_PORT), ViewerHandler)
        server.ssl_ctx = _make_ssl_context()
        print(f"[HTTPS] https://{HOST}:{HTTP_PORT}")
        server.serve_forever()
    except Exception as e:
        print(f"[HTTP] ERROR: {e}")


# === NEW [2026-08-09]: 1 IP = 1 session (mới thay cũ) ===
# Khi 1 IP tạo kết nối mới, đóng các WS cũ cùng IP để tránh xung đột.
# Lưu map ip -> websocket cho cả video + audio.
_ip_to_ws = {}    # ip -> video websocket
_ip_to_audio = {} # ip -> audio websocket

async def _kick_old_session_for_ip(ip, kind='video', old=None):
    """Đóng WS cũ cùng IP (nếu có) trước khi thêm WS mới. Trả về ws cũ nếu có.
    Nếu truyền sẵn `old` (reference đã bắt giữ) thì dùng luôn, không đọc lại map
    (tránh đóng nhầm WS mới khi map đã bị ghi đè)."""
    if old is None:
        if kind == 'video':
            m = _ip_to_ws
        else:
            m = _ip_to_audio
        old = m.get(ip)
    if old is not None and old.state.name != 'CLOSED':
        try:
            # FIX [2026-08-12]: bọc timeout 1s để không treo coroutine khi old là socket
            # half-open (client cũ không ACK) → tránh block việc đăng ký WS mới (gây send=0, đen màn hình khi reconnect)
            await asyncio.wait_for(old.close(code=1000, reason='Replaced by new session (same IP)'), timeout=1.0)
            print(f"[KICK] {kind} {ip} closed (replaced by new session)")
        except asyncio.TimeoutError:
            # old là socket half-open không trả lời close-handshake → bỏ qua, để coroutine
            # handler cũ tự cleanup ở finally (stream_loop sẽ xóa khỏi connected_clients vì ConnectionClosed/ping timeout)
            pass
        except Exception:
            pass
        return old
    return None

# === WebSocket Handlers ===
async def ws_handler(websocket):
    global _force_keyframe_next
    addr = websocket.remote_address
    client_ip = addr[0] if addr else None

    # NEW [2026-08-09]: 1 IP = 1 session — claim IP ngay trước khi kick WS cũ chạy nền.
    # FIX [2026-08-12]: kick cũ qua asyncio.create_task để không chặn việc đăng ký WS mới.
    # Trước đây await _kick_old_session_for_ip block ở old.close() (socket half-open) khiến
    # client mới không bao giờ được add vào connected_clients → send=0.0 → đen màn hình khi reconnect.
    if client_ip:
        _old_ws = _ip_to_ws.get(client_ip)
        _ip_to_ws[client_ip] = websocket
        if _old_ws is not None and _old_ws is not websocket:
            asyncio.create_task(_kick_old_session_for_ip(client_ip, kind='video', old=_old_ws))

    # LƯU Ý [FIX 2026-08-09]: KHÔNG add vào connected_clients ở đây (trước init) —
    # vì _ensure_streaming blocking (1-3s) khiến stream_loop gửi frame video TRƯỚC
    # init JSON → client nhận frame nhưng decoderMode=null (chưa init) → bỏ hết frame,
    # watchdog đóng WS → vòng lặp đen. Chỉ add SAU khi đã gửi xong init JSON.
    client_needs_keyframe.add(websocket)
    client_last_video_id[websocket] = -1   # -1: frame đầu (kể cả đang treo) luôn được gửi
    client_keyframe_wait_until[websocket] = time.monotonic() + 8.0
    _force_keyframe_next = True  # Force keyframe for new client

    # NEW [P_new]: Khi có client (kể cả reconnect), giữ màn sáng để user thấy frame ngay
    # khi client vừa nhận được keyframe IDR. Tránh tình trạng màn idle tắt → client thấy đen.
    _wake_display_on()

    await asyncio.get_event_loop().run_in_executor(None, _ensure_streaming)

    # Ensure audio device is known so we advertise the real capture sample rate
    if _audio_capture_device is None:
        try:
            _find_best_audio_device()
        except Exception:
            pass
    audio_rate = 48000
    if isinstance(_audio_capture_device, dict):
        audio_rate = int(_audio_capture_device.get('sample_rate', 48000))

    init_msg = json.dumps({
        "type": "init",
        "codec": "h264",
        "width": _screen_w,
        "height": _screen_h,
        "scale": SCALE_PERCENT,
        "enc_width": _enc_w,
        "enc_height": _enc_h,
        "fps": MAX_FPS,
        "audio_codec": "pcm",
        "audio_sample_rate": audio_rate,
        "audio_channels": 2,
    })
    try:
        await websocket.send(init_msg)
        # Send cached SPS/PPS immediately so decoder can initialize
        if _cached_sps and _cached_pps:
            header_msg = b'\x03' + _cached_sps + _cached_pps
            await websocket.send(header_msg)
    except websockets.ConnectionClosed:
        pass

    # FIX [2026-08-09]: add vào connected_clients SAU khi init đã gửi → stream_loop
    # chỉ gửi frame cho WS sau khi client đã nhận init + decoderMode sẵn sàng.
    connected_clients.add(websocket)
    # FIX [2026-08-12]: đóng cửa sổ TOCTOU — nếu timer idle đã stop stream trong khoảng
    # thời gian gửi init (blocking I/O) trước khi add, gọi lại _ensure_streaming (idempotent:
    # nếu đã active thì return ngay) để restart nếu stream bị tắt.
    if not _streaming_active:
        await asyncio.get_event_loop().run_in_executor(None, _ensure_streaming)
    print(f"[WS] + {addr} (total: {len(connected_clients)})")

    try:
        async for message in websocket:
            try:
                if isinstance(message, bytes):
                    continue
                data = json.loads(message)
                cmd_type = data.get("type", "")
                if cmd_type == "get_screen_info":
                    info = execute_command("get_screen_info", {})
                    if info:
                        await websocket.send(json.dumps({"type": "screen_info", **info}))
                elif cmd_type == "get_displays":
                    displays = get_display_list()
                    await websocket.send(json.dumps({
                        "type": "display_list",
                        "displays": displays,
                        "current": _current_output_idx
                    }))
                elif cmd_type == "switch_display":
                    out_idx = data.get("output_idx", 0)
                    success = switch_display(out_idx)
                    if success:
                        new_init_msg = json.dumps({
                            "type": "init",
                            "codec": "h264",
                            "width": _screen_w,
                            "height": _screen_h,
                            "scale": SCALE_PERCENT,
                            "enc_width": _enc_w,
                            "enc_height": _enc_h,
                            "fps": MAX_FPS,
                            "audio_codec": "pcm",
                            "audio_sample_rate": audio_rate,
                            "audio_channels": 2,
                            "current_display": _current_output_idx
                        })
                        for ws in list(connected_clients):
                            try:
                                await ws.send(new_init_msg)
                                client_needs_keyframe.add(ws)
                                client_keyframe_wait_until[ws] = time.monotonic() + 8.0
                            except Exception:
                                pass
                elif cmd_type == "request_keyframe":
                    _force_keyframe_next = True
                    client_needs_keyframe.add(websocket)
                    # Deadline để watchdog phát hiện keyframe không tới được client
                    client_keyframe_wait_until[websocket] = time.monotonic() + 8.0
                elif cmd_type.startswith("mouse_") or cmd_type.startswith("key_"):
                    _last_input_time[0] = time.time()
                    execute_command(cmd_type, data)
                elif cmd_type == "ping":
                    await websocket.send(json.dumps({"type": "pong"}))
            except json.JSONDecodeError:
                pass
    except websockets.ConnectionClosed:
        pass
    finally:
        connected_clients.discard(websocket)
        client_needs_keyframe.discard(websocket)
        client_keyframe_wait_until.pop(websocket, None)
        # 1-IP-1-session: nếu ws đang đóng là ws hiện tại của IP → xóa khỏi map
        if client_ip and _ip_to_ws.get(client_ip) is websocket:
            _ip_to_ws.pop(client_ip, None)
        print(f"[WS] - {addr} (total: {len(connected_clients)})")
        _release_all_buttons()
        _release_all_keys()
        _maybe_stop_streaming()
        # NEW [P_new]: Sau khi release client, kiểm tra còn ai không; nếu không → trả sleep về bình thường
        if not _has_any_client():
            _wake_display_off()


async def audio_ws_handler(websocket):
    audio_clients.add(websocket)
    addr = websocket.remote_address
    client_ip = addr[0] if addr else None

    # NEW [2026-08-09]: 1 IP = 1 session — đóng audio WS cũ cùng IP nếu có
    if client_ip:
        await _kick_old_session_for_ip(client_ip, kind='audio')
    if client_ip:
        _ip_to_audio[client_ip] = websocket

    print(f"[WS-AUDIO] + {addr} (total: {len(audio_clients)})")
    # NEW [P_new]: Audio client cũng giữ màn sáng
    _wake_display_on()
    await asyncio.get_event_loop().run_in_executor(None, _ensure_streaming)
    try:
        async for msg in websocket:
            pass
    except websockets.ConnectionClosed:
        pass
    finally:
        audio_clients.discard(websocket)
        # 1-IP-1-session: nếu ws đang đóng là ws hiện tại của IP → xóa khỏi map
        if client_ip and _ip_to_audio.get(client_ip) is websocket:
            _ip_to_audio.pop(client_ip, None)
        print(f"[WS-AUDIO] - {addr} (total: {len(audio_clients)})")
        _maybe_stop_streaming()
        # NEW [P_new]: Trả về idle nếu không còn client nào
        if not _has_any_client():
            _wake_display_off()


async def stream_loop():
    # Flow control: skip a client whose write buffer is backed up instead of
    # dropping it. Slow clients (e.g. phone decoding with Broadway) stay connected
    # and keep receiving frames at a rate they can handle.
    WRITE_BUFFER_LIMIT = 2 * 1024 * 1024  # 2MB: client không tiêu thụ kịp -> skip ít hơn, giảm khựng chunk (đánh đổi trễ tăng)
    _buf_skip_count = {}
    global _send_frame_count, _send_fps_start, _send_fps, _encode_fps, _encode_frame_count
    iteration = 0

    def _buffer_backed_up(ws):
        try:
            transport = ws.transport
            if transport is not None and transport.get_write_buffer_size() > WRITE_BUFFER_LIMIT:
                return True
        except Exception:
            pass
        return False

    async def send_video_to_clients(vid, frame, is_key):
        global _send_frame_count
        stale = set()
        msg = b'\x01' + frame
        for ws in list(connected_clients):
            # FIX [2026-08-12]: Chỉ skip P-frame cho client cũ (từng nhận dữ liệu rồi) đang cần keyframe.
            # Client MỚI (client_last_video_id=-1, vừa kết nối) đã nhận SPS/PPS ở init → 
            # được nhận ngay cả P-frame đầu tiên. Tránh trường hợp client bị stuck ở trạng thái
            # client_needs_keyframe mãi mãi vì I-frame bị timeout/buffer-full.
            last_vid = client_last_video_id.get(ws, -1)
            if vid == last_vid:
                continue
            if ws in client_needs_keyframe and not is_key and last_vid != -1:
                continue
            if _buffer_backed_up(ws):
                # Nghẽn: client đang cần keyframe để phục hồi (đen màn hình) → ưu tiên gửi keyframe
                # dù buffer đầy, nếu không client sẽ đen mãi (không bao giờ nhận được keyframe).
                if is_key and ws in client_needs_keyframe:
                    _buf_skip_count[ws] = 0
                    try:
                        await asyncio.wait_for(ws.send(msg), timeout=0.1)
                        client_last_video_id[ws] = vid
                        client_needs_keyframe.discard(ws)
                        client_keyframe_wait_until.pop(ws, None)
                        continue
                    except (asyncio.TimeoutError, websockets.ConnectionClosed):
                        stale.add(ws)
                        continue
                   # FIX [2026-08-12]: KHÔNG update client_last_video_id khi frame bị skip do buffer full.
                # Nếu update, frame tiếp theo cùng vid sẽ bị skip qua đừờng 'if vid == last_vid: continue'.
                # Client phải giữ last_vid=cũ để frame kế tiếp (vid mới) được gửi lại.
                c = _buf_skip_count.get(ws, 0)
                if c == 0:
                    # Nghẽn: bỏ hết frame cũ, yêu cầu keyframe để decode sạch (tránh delta hỏng -> đơ)
                    client_needs_keyframe.add(ws)
                _buf_skip_count[ws] = c + 1
                continue
            try:
                await asyncio.wait_for(ws.send(msg), timeout=0.05)
                client_last_video_id[ws] = vid
                if ws in client_needs_keyframe:
                    client_needs_keyframe.discard(ws)
                    client_keyframe_wait_until.pop(ws, None)
                if is_key:
                    pass
            except asyncio.TimeoutError:
                client_last_video_id[ws] = vid
                # FIX [2026-08-12]: Timeout không đồng nghĩa với client disconnect.
                # Client vẫn còn sống nhưng đang nghẽn → tiếp tục gửi frame kế tiếp
                # (không giữ client_needs_keyframe vô thời gian, tránh client bị stuck
                # ở trạng thái chờ keyframe mãi mãi khiến send=0).
            except websockets.ConnectionClosed:
                stale.add(ws)
                client_last_video_id.pop(ws, None)
                client_needs_keyframe.discard(ws)
                client_keyframe_wait_until.pop(ws, None)
        # Áp dụng mọi ws bị timeout/đóng (kể cả nhánh keyframe-priority) → không rò rỉ trong connected_clients
        if stale:
            connected_clients.difference_update(stale)
        _send_frame_count += 1

    # Frame pacing: limit sends per iteration to avoid network congestion
    max_frames_per_iter = 2  # Prevent flooding the network
    frame_interval = 1.0 / MAX_FPS

    async def send_audio_to_clients(audio):
         stale_a = set()
         msg = b'\x02' + audio
         for ws in list(audio_clients):
             try:
                 await asyncio.wait_for(ws.send(msg), timeout=0.1)
             except asyncio.TimeoutError:
                 continue
             except websockets.ConnectionClosed:
                 stale_a.add(ws)
         audio_clients.difference_update(stale_a)

    # Frame pacing: send at steady rate
    frame_interval = 1.0 / MAX_FPS
    next_send_time = time.monotonic()
    _audio_batch = []  # accumulate chunks to send in ~50ms batches
    _audio_batch_last_send = time.monotonic()
    iteration = 0

    while True:
        iteration += 1
        now = time.monotonic()

        # Accumulate audio into batches (~20ms = 1 block) to giảm trễ nhưng vẫn gom bớt send
        if audio_clients:
            drained = drain_audio_queue()
            for audio in drained:
                _audio_batch.append(audio)
            now_audio = time.monotonic()
            if _audio_batch and (now_audio - _audio_batch_last_send >= 0.02 or len(_audio_batch) >= 2):
                batched = b''.join(_audio_batch)
                _audio_batch = []
                _audio_batch_last_send = now_audio
                asyncio.create_task(send_audio_to_clients(batched))

        if connected_clients and now >= next_send_time:
            # Có client đang nghẽn cần keyframe -> ép encode IDR ngay (không chờ keyint)
            if client_needs_keyframe:
                _force_keyframe_next = True
            # Get latest frame (non-peek: read and clear)
            latest = _get_latest_frame()

            if latest is not None:
                vid, frame, is_key = latest
                send_frame = frame
                # Prepend SPS/PPS to keyframes for decoder initialization
                if is_key and _cached_sps and _cached_pps:
                    if not _has_sps_pps(frame):
                        send_frame = _cached_sps + _cached_pps + frame
                await send_video_to_clients(vid, send_frame, is_key)

            # Schedule next send time (maintain steady rate)
            next_send_time = now + frame_interval

            # Watchdog: client cần keyframe nhưng quá hạn (3s) vẫn chưa nhận được
            # → khả năng nghẽn cứng / ws chết thầm → đóng để client reconnect sạch
            # (tránh đen màn hình vĩnh viễn do keyframe không bao giờ tới).
            if client_keyframe_wait_until:
                for ws in list(client_needs_keyframe):
                    dl = client_keyframe_wait_until.get(ws)
                    if dl is not None and now > dl:
                        print(f"[WS] Keyframe timeout for {ws.remote_address}, force reconnect", file=sys.stderr)
                        try:
                            await ws.close()
                        except Exception:
                            pass
                        client_needs_keyframe.discard(ws)
                        client_keyframe_wait_until.pop(ws, None)

        if _pressed_buttons and _last_input_time[0] > 0:
            if time.time() - _last_input_time[0] > _INPUT_TIMEOUT:
                _release_all_buttons()
        if _pressed_keys and _last_input_time[0] > 0:
            if time.time() - _last_input_time[0] > _INPUT_TIMEOUT:
                _release_all_keys()

        # Sleep until next send deadline (precise with timeBeginPeriod(1)).
        # Polling with a fixed 1ms sleep is inaccurate on Windows (~16ms resolution)
        # and threw frame pacing off to ~21fps. asyncio.sleep rounds up ~1ms,
        # so subtract a small epsilon to keep the send cadence at exactly MAX_FPS.
        deadline = next_send_time if connected_clients else time.monotonic() + 0.05
        delay = deadline - time.monotonic() - 0.0015
        if delay > 0:
            await asyncio.sleep(delay)
        while time.monotonic() < deadline:
            pass

        # Periodic FPS log (every 5s)
        now_report = time.monotonic()
        if _send_fps_start == 0:
            _send_fps_start = now_report
        if now_report - _send_fps_start >= 5.0:
            _send_fps = _send_frame_count / (now_report - _send_fps_start)
            _send_frame_count = 0
            _send_fps_start = now_report
            total_skip = sum(_buf_skip_count.values())
            if total_skip > 0:
                print(f"[FPS] encode={_encode_fps:.1f} send={_send_fps:.1f} keyint={H264_KEYINT} threads={_cpu_count} skips={total_skip}", file=sys.stderr)
            else:
                print(f"[FPS] encode={_encode_fps:.1f} send={_send_fps:.1f} keyint={H264_KEYINT} threads={_cpu_count}", file=sys.stderr)


# === Main ===
def _check_dependencies():
    missing = []
    try:
        import dxcam
    except ImportError:
        missing.append("dxcam")
    try:
        import numpy
    except ImportError:
        missing.append("numpy")
    try:
        import websockets
    except ImportError:
        missing.append("websockets")
    try:
        import av
    except ImportError:
        missing.append("av")
    try:
        import cv2
    except ImportError:
        missing.append("opencv-python")

    if missing:
        print(f"[INIT] Missing packages: {', '.join(missing)}")
        print(f"[INIT] Install with: pip install {' '.join(missing)}")
        return False
    return True


def _run_server():
    if not _check_dependencies():
        sys.exit(1)

    # Set high-resolution Windows timer (1ms) so asyncio.sleep is accurate.
    # Default Windows timer resolution ~15.6ms breaks frame pacing (30fps -> ~21fps).
    try:
        ctypes.windll.winmm.timeBeginPeriod(1)
    except Exception:
        pass

    # Force UTF-8 output for box drawing characters
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')

    print("+" + "=" * 48 + "+")
    print("|    Screen Share Server H264 Windows v1.0        |")
    print("+" + "-" * 48 + "+")
    print("|  Capture : dxcam (Desktop Duplication API)      |")
    enc_name = _pick_encoder()
    print(f"|  Encode  : PyAV {enc_name.ljust(30)}|")
    print("|  Input   : SendInput (Windows API)              |")
    print("|  Audio   : WASAPI loopback (ctypes/comtypes)    |")
    print("|  Stream  : WebSocket binary (H.264 + PCM)       |")
    print("+" + "-" * 48 + "+")
    print(f"|  Open: https://localhost:{HTTP_PORT}                 |")
    print("+" + "=" * 48 + "+")

    threading.Thread(target=start_http_server, daemon=True).start()
    print("[MAIN] HTTP server thread started")

    ssl_ctx_ws = _make_ssl_context()
    ssl_ctx_audio = _make_ssl_context()

    async def run():
        async with websockets.serve(
            ws_handler, HOST, WS_PORT,
            max_size=10 * 1024 * 1024,
            ping_interval=10, ping_timeout=300,
            ssl=ssl_ctx_ws,
        ), websockets.serve(
            audio_ws_handler, HOST, WS_AUDIO_PORT,
            max_size=10 * 1024 * 1024,
            ping_interval=10, ping_timeout=300,
            ssl=ssl_ctx_audio,
        ):
            print(f"[WSS]  Video/Control: wss://{HOST}:{WS_PORT}")
            print(f"[WSS]  Audio        : wss://{HOST}:{WS_AUDIO_PORT}")
            print("[*] Ready! Waiting for clients...")
            _schedule_idle_exit()
            await stream_loop()

    # FIX [2026-08-12]: safety-net — nếu accept loop của WS bị chết (OSError WinError 64
    # do gh-93821: client F5-reconnect làm TCP mới reset trước khi AcceptEx hoàn tất → stdlib
    # ProactorEventLoop đóng listen socket vĩnh viễn), server tự exit để manager respawn sạch
    # thay vì kẹt client 1006 mãi. (Không monkeypatch stdlib — quá rủi ro khi nhắm closure local.)
    def _loop_exception_handler(loop, context):
        exc = context.get('exception')
        if isinstance(exc, OSError) and getattr(exc, 'winerror', None) == 64:
            # FIX [2026-08-12]: use os._exit(1) (code nonzero) để manager nhánh `rc != 0`
            # respawn chủ động. Nếu dùng os._exit(0) manager xem như "clean idle exit" nên
            # KHÔNG respawn → client 1006 stuck. Idle exit (chờ connect) vẫn giữ os._exit(0).
            print("[FATAL] WS accept failed (WinError 64), exiting for respawn", file=sys.stderr, flush=True)
            os._exit(1)
        loop.default_exception_handler(context)

    # FIX [2026-08-12 gh-93821]: dùng SelectorEventLoop thay vì ProactorEventLoop (mặc định Windows).
    # Proactor dùng AcceptEx → khi client F5-reconnect làm TCP mới reset trước khi AcceptEx hoàn tất,
    # finish_accept() ném OSError WinError 64 → stdlib đóng listen socket WS vĩnh viễn → client 1006.
    # SelectorEventLoop dùng select() → accept fail chỉ được log/ignore, listen socket KHÔNG bị đóng,
    # tự phục hồi sau mỗi lần reset (đã test thực tế 200 connection RST flood → server không chết).
    # Hạn chế: không support asyncio.subprocess (app không dùng), select() ~512 fd (OK với vài client).
    loop = asyncio.SelectorEventLoop()
    loop.set_exception_handler(_loop_exception_handler)
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run())
    finally:
        try:
            loop.close()
        except Exception:
            pass


def main():
    try:
        _run_server()
    except KeyboardInterrupt:
        print("\n[*] Server stopped.")
    except Exception as e:
        print(f"[FATAL] {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
