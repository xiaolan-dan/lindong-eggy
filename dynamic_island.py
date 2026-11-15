# -*- coding: utf-8 -*-
"""灵动岛 · Windows 硬件状态悬浮条

单文件、纯标准库实现（tkinter + ctypes 直调 Win32 API），无需 pip 安装任何第三方包。
Python 3.9+ / Windows 10 及以上。

一条细长胶囊常驻屏幕顶部中央，CPU / 内存 / GPU / 磁盘 / 电池 五项指标
全部直接显示在条内，每项左侧一个小圆环显示占用比例，不展开、不收起。

两种底色：默认跟随主题渐变，也可以改成轮换播放
`轮换图/` 里的图片（原图居中裁剪铺满，默认每 25 秒一张，
间隔可在设置面板选 10 / 25 / 60 秒，换图时带一段淡入淡出）。

用法：
    python dynamic_island.py

交互：
    位置固定，不能拖动
    右键        -> 设置菜单（主题、刷新频率、图片轮换、开机自启、全屏自动隐藏、
                   下一张图片、收起为图标、退出）
    右侧齿轮    -> 单击同样打开设置菜单（快捷入口）
"""

from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes as wt
import json
import math
import os
import struct
import tempfile
import sys
import threading
import time
import winreg
import zlib

import tkinter as tk
from tkinter import font as tkfont

APP_NAME = "灵动岛 · 硬件状态"
APP_VERSION = "3.0"
SCRIPT_PATH = os.path.abspath(__file__)

# ---------------------------------------------------------------- 主题配色
# 每个主题就是一组颜色名 -> 颜色值。所有自绘函数都在运行时读这些模块级名字，
# 所以 apply_theme() 改写它们之后，重画一遍界面就换主题了。
# 浅色系按《蛋仔派对》的思路做：白色外描边 + 粉彩渐变 + 糖果色圆环。
KEY_COLOR = "#000000"     # 窗口抠色（该颜色的像素完全透明）

THEMES = {
    "dark": {
        "label": "深色",
        "BG_TOP": "#181F2A", "BG_BOTTOM": "#0C1117",
        "BORDER": "#252D3A", "BORDER_DEEP": "#323C4C",
        "TRACK": "#2B3547", "TEXT": "#EDF1F7", "MUTED": "#78849A",
        "DIVIDER": "#222B38", "MENU_BG": "#161B24", "MENU_ACTIVE": "#2A3342",
        "ACC": {"cpu": "#4E9BFF", "mem": "#3FD6C4", "gpu": "#6FE39A",
                "disk": "#FFB25C", "net": "#B98BFF", "bat": "#FF7E9E"},
        "COL_DOT_OK": "#4E9BFF", "COL_DOT_WARN": "#FFB25C", "COL_DOT_HOT": "#FF5D5D",
        "CARD_BG": "#141A24", "CARD_STROKE": "#2A3445",
        "ITEM_BG": "#242D3C", "ITEM_STROKE": "#303B4E",
        "ACTIVE_BG": "#4E9BFF", "PILL_ON_TEXT": "#FFFFFF", "PILL_OFF_TEXT": "#94A2B8",
        "DANGER_BG": "#3A2027", "DANGER_STROKE": "#5A2A33", "DANGER_TEXT": "#FF8A8A",
        "SW_TRACK": "#2B3547", "SW_KNOB": "#8C97AC", "EDGE_W": 1.2,
    },
    "pink": {
        "label": "粉白",
        "BG_TOP": "#FFF7FA", "BG_BOTTOM": "#FBDFE9",
        "BORDER": "#EDB6CC", "BORDER_DEEP": "#FFFFFF",
        "TRACK": "#F3D2DE", "TEXT": "#5B4551", "MUTED": "#A98C9B",
        "DIVIDER": "#F4DCE5", "MENU_BG": "#FFFFFF", "MENU_ACTIVE": "#FCE4EE",
        "ACC": {"cpu": "#F06A93", "mem": "#28B7AC", "gpu": "#5FBF63",
                "disk": "#E39B2A", "net": "#8C6FE3", "bat": "#3F8AE6"},
        "COL_DOT_OK": "#FF8FB1", "COL_DOT_WARN": "#FFC44D", "COL_DOT_HOT": "#F2607A",
        "CARD_BG": "#FFFFFF", "CARD_STROKE": "#F0C8D8",
        "ITEM_BG": "#FDF0F5", "ITEM_STROKE": "#F2D2DF",
        "ACTIVE_BG": "#FF7FA8", "PILL_ON_TEXT": "#FFFFFF", "PILL_OFF_TEXT": "#B98FA0",
        "DANGER_BG": "#FCE7EC", "DANGER_STROKE": "#F2C6D0", "DANGER_TEXT": "#D45C6E",
        "SW_TRACK": "#F1D4DF", "SW_KNOB": "#DB9FB3", "EDGE_W": 1.8,
    },
    "snow": {
        "label": "冷白",
        "BG_TOP": "#FFFFFF", "BG_BOTTOM": "#E8EEF6",
        "BORDER": "#C7D6E6", "BORDER_DEEP": "#FFFFFF",
        "TRACK": "#DDE6F1", "TEXT": "#2E3A4B", "MUTED": "#8A96A8",
        "DIVIDER": "#E6EDF5", "MENU_BG": "#FFFFFF", "MENU_ACTIVE": "#EEF4FB",
        "ACC": {"cpu": "#4E9BFF", "mem": "#2FBFB4", "gpu": "#5EC47A",
                "disk": "#E8A13C", "net": "#8E7BEA", "bat": "#E86A87"},
        "COL_DOT_OK": "#4E9BFF", "COL_DOT_WARN": "#E8A13C", "COL_DOT_HOT": "#E8556B",
        "CARD_BG": "#FFFFFF", "CARD_STROKE": "#D5E1EF",
        "ITEM_BG": "#F3F8FE", "ITEM_STROKE": "#DCE6F2",
        "ACTIVE_BG": "#4E9BFF", "PILL_ON_TEXT": "#FFFFFF", "PILL_OFF_TEXT": "#8090A6",
        "DANGER_BG": "#FCEEF0", "DANGER_STROKE": "#F3CBD2", "DANGER_TEXT": "#C9505F",
        "SW_TRACK": "#DDE7F2", "SW_KNOB": "#9FB0C6", "EDGE_W": 1.8,
    },
    "mint": {
        "label": "薄荷",
        "BG_TOP": "#F3FCF8", "BG_BOTTOM": "#D8F2E7",
        "BORDER": "#A9DCC5", "BORDER_DEEP": "#FFFFFF",
        "TRACK": "#D2EBE0", "TEXT": "#2C4A3E", "MUTED": "#7FA396",
        "DIVIDER": "#E0F1E9", "MENU_BG": "#FFFFFF", "MENU_ACTIVE": "#E6F7EF",
        "ACC": {"cpu": "#DC6280", "mem": "#17AE97", "gpu": "#4FB264",
                "disk": "#DB9526", "net": "#7A6BD6", "bat": "#3285C8"},
        "COL_DOT_OK": "#3FD6C4", "COL_DOT_WARN": "#F2B24F", "COL_DOT_HOT": "#F0605F",
        "CARD_BG": "#FFFFFF", "CARD_STROKE": "#BFE4D3",
        "ITEM_BG": "#EFFBF5", "ITEM_STROKE": "#CFEADD",
        "ACTIVE_BG": "#2FC2A6", "PILL_ON_TEXT": "#FFFFFF", "PILL_OFF_TEXT": "#7FA99A",
        "DANGER_BG": "#FCEBEC", "DANGER_STROKE": "#F2C9CD", "DANGER_TEXT": "#CC5A64",
        "SW_TRACK": "#D8F0E6", "SW_KNOB": "#9CC7B7", "EDGE_W": 1.8,
    },
}

THEME_ORDER = ["dark", "pink", "snow", "mint"]
THEME = "dark"

BG_TOP = "#181F2A"        # 胶囊渐变顶部
BG_BOTTOM = "#0C1117"     # 胶囊渐变底部
BORDER = "#252D3A"        # 胶囊描边
BORDER_DEEP = "#323C4C"   # 外沿亮一档，收边用
TRACK = "#2B3547"         # 圆环轨道
TEXT = "#EDF1F7"          # 主数值
MUTED = "#78849A"
DIVIDER = "#222B38"       # 分隔线
MENU_BG = "#161B24"
MENU_ACTIVE = "#2A3342"
PILL_ON_TEXT = "#FFFFFF"  # 选中胶囊的字
PILL_OFF_TEXT = "#94A2B8" # 未选中胶囊的字
SW_TRACK = "#2B3547"      # 开关轨道
SW_KNOB = "#8C97AC"       # 开关圆钮
EDGE_W = 1.2              # 胶囊描边粗细

ACC = {
    "cpu": "#4E9BFF",
    "mem": "#3FD6C4",
    "gpu": "#6FE39A",
    "disk": "#FFB25C",
    "net": "#B98BFF",
    "bat": "#FF7E9E",
}

COL_DOT_OK = "#4E9BFF"     # 状态球：正常
COL_DOT_WARN = "#FFB25C"   # 状态球：偏忙
COL_DOT_HOT = "#FF5D5D"    # 状态球：高负载


def _cfg_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "LINDONG-EGGY")


def _load_cfg():
    try:
        with open(os.path.join(_cfg_dir(), "config.json"), "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save_cfg(d):
    try:
        os.makedirs(_cfg_dir(), exist_ok=True)
        with open(os.path.join(_cfg_dir(), "config.json"), "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
    except Exception:
        pass


def _cfg_patch(upd):
    """只改几个键，别把别的设置（主题、轮换开关）覆盖掉"""
    d = _load_cfg()
    d.update(upd)
    _save_cfg(d)
    return d


THEME_FIELDS = ("BG_TOP", "BG_BOTTOM", "BORDER", "BORDER_DEEP", "TRACK", "TEXT",
                "MUTED", "DIVIDER", "MENU_BG", "MENU_ACTIVE",
                "COL_DOT_OK", "COL_DOT_WARN", "COL_DOT_HOT",
                "PILL_ON_TEXT", "PILL_OFF_TEXT", "SW_TRACK", "SW_KNOB", "EDGE_W")
PANEL_FIELDS = ("CARD_BG", "CARD_STROKE", "ITEM_BG", "ITEM_STROKE",
                "ACTIVE_BG", "DANGER_BG", "DANGER_STROKE", "DANGER_TEXT")


def apply_theme(name):
    """把某个主题的颜色写进模块级变量 + 设置面板的类属性"""
    global THEME, AVATAR_TINTS
    if name not in THEMES:
        name = THEME_ORDER[0]
    th = THEMES[name]
    THEME = name
    for k in THEME_FIELDS:
        globals()[k] = th[k]
    ACC.clear()
    ACC.update(th["ACC"])
    # 头像色偏跟着当前主题的状态色重建（正常/偏忙/高负载）
    AVATAR_TINTS = {
        COL_DOT_WARN: (1.0, 0.86, 0.62),
        COL_DOT_HOT: (1.0, 0.62, 0.50),
    }
    panel = globals().get("SettingsPanel")
    if panel is not None:
        for k in PANEL_FIELDS:
            setattr(panel, k, th[k])

# ---------------------------------------------------------------- 尺寸（96 DPI 下的逻辑像素）
STRIP_H = 44          # 胶囊高度（不变粗）
PAD_L = 80            # 左侧留白（含蛋仔头像，给左圆头留够空间）
PAD_R = 20
COL_GAP = 10
GEAR_W = 34           # 右侧设置快捷入口的占位宽度
GEAR_D = 22           # 齿轮图标直径
COLUMNS = [
    ("cpu", "CPU", 66),
    ("mem", "内存", 66),
    ("gpu", "GPU", 88),
    ("disk", "磁盘", 66),
    ("bat", "电池", 86),
]
STRIP_W = (PAD_L + sum(c[2] for c in COLUMNS) + COL_GAP * (len(COLUMNS) - 1)
           + COL_GAP + GEAR_W + PAD_R)
TOP_OFFSET = 6

# 图片轮换：胶囊底色换成「轮换图/」里的图，居中裁剪铺满
PHOTO_DIR = "轮换图"
PHOTO_INTERVAL = 25       # 轮换间隔默认值（秒），设置面板里可改，存在配置里
PHOTO_FADE_MS = 320       # 换图时淡入淡出时长
PHOTO_FADE_STEPS = 6      # 淡入淡出分几帧（帧数越多越顺，但每帧要多算一次）
PHOTO_SCRIM_TOP = 0.52    # 顶部压暗强度，保证读数看得清
PHOTO_SCRIM_BOTTOM = 0.66 # 底部再压一点，做出上亮下暗的渐变


# ================================================================ Win32 接口
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


class FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wt.DWORD), ("dwHighDateTime", wt.DWORD)]


class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", wt.DWORD),
        ("dwMemoryLoad", wt.DWORD),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


class SYSTEM_POWER_STATUS(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", wt.BYTE),
        ("BatteryFlag", wt.BYTE),
        ("BatteryLifePercent", wt.BYTE),
        ("SystemStatusFlag", wt.BYTE),
        ("BatteryLifeTime", wt.DWORD),
        ("BatteryFullLifeTime", wt.DWORD),
    ]


kernel32.GetSystemTimes.argtypes = [
    ctypes.POINTER(FILETIME), ctypes.POINTER(FILETIME), ctypes.POINTER(FILETIME)
]
kernel32.GetSystemTimes.restype = wt.BOOL
kernel32.GetTickCount64.restype = ctypes.c_ulonglong
kernel32.GetLogicalDrives.restype = wt.DWORD
kernel32.GetDriveTypeW.argtypes = [wt.LPCWSTR]
kernel32.GetDriveTypeW.restype = wt.UINT
kernel32.GetDiskFreeSpaceExW.argtypes = [
    wt.LPCWSTR,
    ctypes.POINTER(ctypes.c_ulonglong),
    ctypes.POINTER(ctypes.c_ulonglong),
    ctypes.POINTER(ctypes.c_ulonglong),
]
kernel32.GetDiskFreeSpaceExW.restype = wt.BOOL
kernel32.GetSystemPowerStatus.argtypes = [ctypes.POINTER(SYSTEM_POWER_STATUS)]
kernel32.GetSystemPowerStatus.restype = wt.BOOL

def _ft_value(ft: FILETIME) -> int:
    return (ft.dwHighDateTime << 32) | ft.dwLowDateTime


# ================================================================ 数据采集
class CpuProbe:
    """整体 CPU 占用率（GetSystemTimes 差值法）"""

    def __init__(self):
        self._last = self._read()

    def _read(self):
        idle, kern, user = FILETIME(), FILETIME(), FILETIME()
        kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kern), ctypes.byref(user))
        return (_ft_value(idle), _ft_value(kern), _ft_value(user))

    def usage(self) -> float:
        idle, kern, user = self._read()
        d_idle = idle - self._last[0]
        d_total = (kern - self._last[1]) + (user - self._last[2])
        self._last = (idle, kern, user)
        if d_total <= 0:
            return 0.0
        return max(0.0, min(1.0, 1.0 - d_idle / d_total))


def _mem_info():
    ms = MEMORYSTATUSEX()
    ms.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
    return ms.ullTotalPhys, ms.ullTotalPhys - ms.ullAvailPhys


def _disk_info():
    total = free = 0
    mask = kernel32.GetLogicalDrives()
    for i in range(26):
        if not (mask & (1 << i)):
            continue
        root = f"{chr(65 + i)}:\\"
        try:
            if kernel32.GetDriveTypeW(root) != 3:      # DRIVE_FIXED
                continue
        except Exception:
            continue
        fb, tb, _ab = ctypes.c_ulonglong(), ctypes.c_ulonglong(), ctypes.c_ulonglong()
        if kernel32.GetDiskFreeSpaceExW(root, ctypes.byref(fb), ctypes.byref(tb), ctypes.byref(_ab)):
            total += tb.value
            free += fb.value
    return total, free


def _battery_info():
    st = SYSTEM_POWER_STATUS()
    if not kernel32.GetSystemPowerStatus(ctypes.byref(st)):
        return None
    has_battery = not (st.BatteryFlag & 0x80) and st.BatteryLifePercent != 255
    if not has_battery:
        return None
    return int(st.BatteryLifePercent), st.ACLineStatus == 1


def _cpu_info():
    """CPU 名称 / 主频"""
    name, mhz = "", 0
    try:
        key = r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key) as k:
            name = str(winreg.QueryValueEx(k, "ProcessorNameString")[0]).strip()
            mhz = int(winreg.QueryValueEx(k, "~MHz")[0])
    except Exception:
        pass
    return name, mhz


# ---------------------------------------------------------------- GPU
class NVMLUtil(ctypes.Structure):
    _fields_ = [("gpu", wt.UINT), ("memory", wt.UINT)]


class GpuProbe:
    """GPU：名称走注册表，利用率走 PDH 性能计数器（N/A/I 卡通用），温度走 NVML（仅 NVIDIA）"""

    def __init__(self):
        self.name = self._read_name()
        self.short = self._shorten(self.name)
        self.util = None
        self.temp = None
        self._pdh = None
        self._nvml_handle = None
        self._nvml = None
        self._init_pdh()
        self._init_nvml()

    # -- 注册表取显卡名称（取显存最大的那块，通常是独显）
    @staticmethod
    def _read_name() -> str:
        key = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
        best, best_mem = "", -1
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key) as k:
                for i in range(24):
                    try:
                        sub = winreg.EnumKey(k, i)
                    except OSError:
                        break
                    if not sub.isdigit():
                        continue
                    try:
                        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key + "\\" + sub) as sk:
                            desc = str(winreg.QueryValueEx(sk, "DriverDesc")[0]).strip()
                            try:
                                mem = int(winreg.QueryValueEx(sk, "HardwareInformation.qwMemorySize")[0])
                            except OSError:
                                mem = 0
                    except OSError:
                        continue
                    if not desc:
                        continue
                    if mem >= best_mem:
                        best, best_mem = desc, mem
        except Exception:
            pass
        return best

    @staticmethod
    def _shorten(name: str) -> str:
        if not name:
            return "显卡"
        for junk in ("NVIDIA ", "GeForce ", "AMD ", "Radeon ", "Intel(R) ", "Intel ",
                     "(R)", "(TM)", "Graphics", "显卡"):
            name = name.replace(junk, "")
        name = " ".join(name.split())
        return name[:16] if name else "显卡"

    # -- PDH
    def _init_pdh(self):
        try:
            pdh = ctypes.WinDLL("pdh")
            hq = ctypes.c_void_p()
            if pdh.PdhOpenQueryW(None, 0, ctypes.byref(hq)) != 0:
                return
            hc = ctypes.c_void_p()
            path = r"\GPU Engine(*)\Utilization Percentage"
            if pdh.PdhAddEnglishCounterW(hq, path, 0, ctypes.byref(hc)) != 0:
                pdh.PdhCloseQuery(hq)
                return
            pdh.PdhCollectQueryData(hq)
            self._pdh = (pdh, hq, hc)
        except Exception:
            self._pdh = None

    def _pdh_util(self):
        pdh, hq, hc = self._pdh

        class FMT_VALUE(ctypes.Union):
            _fields_ = [("longValue", ctypes.c_long),
                        ("doubleValue", ctypes.c_double),
                        ("largeValue", ctypes.c_longlong),
                        ("longLongValue", ctypes.c_longlong),
                        ("AnsiStringValue", ctypes.c_char_p),
                        ("WideStringValue", ctypes.c_wchar_p)]

        class FMT_ITEM(ctypes.Structure):
            # 必须带上 CStatus：PDH_FMT_COUNTERVALUE 是 {DWORD CStatus; union value}
            _fields_ = [("szName", ctypes.c_wchar_p),
                        ("CStatus", wt.DWORD),
                        ("FmtValue", FMT_VALUE)]

        pdh.PdhCollectQueryData(hq)
        pdh.PdhGetFormattedCounterArrayW.argtypes = [
            ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.DWORD),
            ctypes.POINTER(wt.DWORD), ctypes.POINTER(FMT_ITEM)]
        size, count = wt.DWORD(0), wt.DWORD(0)
        rc = pdh.PdhGetFormattedCounterArrayW(hc, 512, ctypes.byref(size),
                                             ctypes.byref(count), None)
        if rc != 0 and not size.value:
            return None
        buf = (ctypes.c_char * (size.value + 16))()
        items = ctypes.cast(buf, ctypes.POINTER(FMT_ITEM))
        pdh.PdhGetFormattedCounterArrayW(hc, 512, ctypes.byref(size),
                                         ctypes.byref(count), items)
        # 同一块显卡每个进程各占一条计数器：按引擎类型（3D / Copy / VideoDecode…）
        # 跨进程求和，再取各引擎里的最大值，才是任务管理器那种「显卡占用」
        per_engine = {}
        best = 0.0
        for i in range(count.value):
            if items[i].CStatus != 0:             # 0 = PDH_CSTATUS_VALID_DATA
                continue
            try:
                v = items[i].FmtValue.doubleValue
            except Exception:
                continue
            if v is None or v != v:                # 过滤 NaN
                continue
            name = items[i].szName or ""
            tag = ""
            pos = name.find("engtype_")
            if pos >= 0:
                tag = name[pos:]
            per_engine[tag] = per_engine.get(tag, 0.0) + v
            if v > best:
                best = v
        if per_engine:
            best = max(best, max(per_engine.values()))
        return min(1.0, best / 100.0)

    # -- NVML（仅 NVIDIA 提供温度）
    def _init_nvml(self):
        try:
            nvml = ctypes.WinDLL("nvml.dll")
            nvml.nvmlInit_v2()
            handle = ctypes.c_void_p()
            if nvml.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(handle)) != 0:
                return
            self._nvml, self._nvml_handle = nvml, handle
        except Exception:
            self._nvml = None

    def sample(self):
        if self._pdh is not None:
            try:
                self.util = self._pdh_util()
            except Exception:
                self.util = None
        if self._nvml is not None:
            try:
                temp = wt.UINT()
                if self._nvml.nvmlDeviceGetTemperature(self._nvml_handle, 0, ctypes.byref(temp)) == 0:
                    self.temp = int(temp.value)
                u = NVMLUtil()
                if self._nvml.nvmlDeviceGetUtilizationRates(self._nvml_handle, ctypes.byref(u)) == 0:
                    if self.util is None:
                        self.util = u.gpu / 100.0
            except Exception:
                pass


# ================================================================ 采样线程
class Sampler(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.daemon = True
        self.lock = threading.Lock()
        self.data = {}
        self._stop = threading.Event()
        self.cpu = CpuProbe()
        self.gpu = GpuProbe()
        self._tick = 0
        self.interval = 1.0

    def stop(self):
        self._stop.set()

    def run(self):
        time.sleep(0.2)
        while not self._stop.is_set():
            try:
                self._collect()
            except Exception:
                pass
            self._stop.wait(max(0.5, self.interval))

    def _collect(self):
        d = {}
        d["cpu"] = self.cpu.usage()
        d["mem_total"], d["mem_used"] = _mem_info()
        d["disk_total"], d["disk_free"] = _disk_info()
        d["battery"] = _battery_info()
        d["uptime"] = kernel32.GetTickCount64() / 1000.0
        if self._tick % 3 == 0:
            self.gpu.sample()
        self._tick += 1
        d["gpu_util"] = self.gpu.util
        d["gpu_temp"] = self.gpu.temp
        d["gpu_name"] = self.gpu.short
        with self.lock:
            self.data = d


# ================================================================ 文本格式
def fmt_uptime(sec: float) -> str:
    sec = int(sec)
    days, rem = divmod(sec, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if days:
        return f"已运行 {days} 天 {h:02d}:{m:02d}"
    return f"已运行 {h:02d}:{m:02d}:{rem % 60:02d}"


# 负载 -> 蛋仔头像轻微色偏（亮黄 -> 橙 -> 橙红），保留原来"看颜色判断负载"
# 切主题时 apply_theme() 会按新的状态色重建这张表
AVATAR_TINTS = {
    COL_DOT_WARN: (1.0, 0.86, 0.62),
    COL_DOT_HOT: (1.0, 0.62, 0.50),
}


def load_color(ratio: float) -> str:
    if ratio >= 0.85:
        return COL_DOT_HOT
    if ratio >= 0.65:
        return COL_DOT_WARN
    return COL_DOT_OK


# 设置入口图标：用户提供的蛋仔风齿轮贴纸，已抠掉黑底、缩放到 40x40，
# 存成 RGBA 的 base64（纯标准库即可解码），运行时会按胶囊每一行的渐变色做 alpha 合成。
GEAR_STICKER_B64 = (
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAALOxshLa2tuu7O/u//z//f/2+ff/5efm5OTm5Ze1trVIMTAxBQAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAHl2dwGTkI4om52ZKYqSigEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABzc3UJ4uTjzLK7vP86TFH/KzpA/zNBSP9bZmr/"
    "m6Oj/+fr6v/k5ubGqaytLgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAFVZWAHAw8Jd4efm2u7y8P/t8vD/6+vr08O+wD8AAAAAAAAAAAAAAAAAAAAA"
    "AAAAANrb24HL0NH/Ijk9/2Okrf931Nv/bcHL/1abpf8wYGX/Izg7/5WZnf/s7/D0sbGyOAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACdnZsV2d3dtOHm6P91fYH/"
    "JDk9/yE1PP9/iY7/8fH09dHS00IAAAAAAAAAAAAAAACtra0u8PDx90VWWf9Ykpr/e+nv/4Hl8P+C5fD/g+Tx/4Xk8P9vvsP/"
    "I0pP/4yVmv/p6em+AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAsbGuK+jp6N+yvb7/LT5G/z5veP92y8//d8nP/ytSW/9rc3n/7e/v87KztTcAAAAAtbW0Nuzv7+CTlpj/"
    "LE9Z/4Lj6/+A5ez/f+fw/37n8P9/5+//fufw/37m8f9ywsf/KEFF//Hx8P9APz0OAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAALe6ujzn6un0jpea/yQ3Qf9lq6//h+Tu/4Hm7v995+3/"
    "gNjh/yhMUv+IkZH/8PHx3tTSz37w8fDxiZGV/x8/Qv95xcr/f+bw/4Dm8P9/5vH/f+bx/3/m8f9/5vH/f+bx/4Lc4/8fNDv/"
    "7/Lx/3Fwbi0AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADBwsA3"
    "6+/w8HyGi/8rQ0z/b8vL/4Lj7/+A5u7/gOfu/3/n7f976PD/eMzU/yBBRf+Ej5L/vsTE/1pqbv8mSlL/eMzR/37n7/9+5+3/"
    "gOby/3/m8f9/5vH/f+bx/3/m8f9/5vH/fdfe/yA1PP/09vX/SEdFJgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAvb29H+zr7O5+h4r/KEhR/3vT2/+A5u7/f+bw/3/n8P+A5/D/gOfv/4Dm8/+A5fL/"
    "d8jO/zRdZv8lSFH/SYCG/4Dd4P9+5vH/gOb1/4Hn7v+A5/L/gOby/4Dm8v+A5vL/gOby/4Dm8v92y9P/Kz1F//P09f8AAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADi4+PMnaSo/yVBR/980df/"
    "gObx/3/m8f9/5vH/f+bx/3/m8f9/5vH/f+bx/3/m8f976O//gubu/4To8P995fD/f+bx/3/n8P9/5+z/f+ft/3/n7/9/5vH/"
    "f+bx/3/m8f9/5vH/f+bx/3DDyv81Rk7/6ejr/wAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAsrGyRN7l5P8gOj7/csDH/37n8P+A5vH/f+bx/3/m8f9/5vH/f+bx/3/m8f9/5vH/f+bx/4Hl8f+C5fL/"
    "f+Xx/3/n7P+A5+3/gOfw/3/l8v9+5u//f+bu/3/m8f9/5vH/f+bx/3/m8f9/5vH/dM3S/yc9Q//x8PP/lZuaGwAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADn6OddtcG+/zBUV/+A5+//g+Xy/4Dm8v+A5vL/"
    "gOby/4Dm8v+A5vL/geby/3/n8/9+6O//gObv/3Td7P9WvN//RaXT/0ii0v9PpNX/S6HX/0Wo0v9YwuD/fN/y/4Dm8v995vT/"
    "fufx/4Hm7/+F4uv/JUNN/6Woq//r7e3t2tnbgJaSlzEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAKOiokHj6en/JTs//3O9x/9/5u//f+bw/3/m8f9/5vH/f+bx/3/m8P9/5/D/f+ft/23S5/9HpNT/c7LZ/7/b6//s+f3/"
    "9/7+//r+/P/2/Pv/5/b7/7jT6f9orNX/RqnW/3ja5f+C5e7/fOb1/3zn8P9rur//Hj1C/11qbP+zvL3/7PLy/+rr6uDn5uWX"
    "zszMR2hoaAcAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAOTc4A+Xl58GboqT/J0lT/4Tj7v9/5vH/f+bx/3/m8f9/5vH/"
    "fuXw/37l8f9IsNr/drTa/+fx9//8+v3///z6//79+v/+/vz//v78//7+///9/////f7+//39/P/b6/P/ZqvX/1e71/+C5uv/"
    "hOTw/37n7P9+193/UYqS/yVLUv8hOD3/WWZr/5igpf/e4ub/5OTk38LCwkp9fX0AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "m5mdK+zu7/o5S1H/arvF/4Dm8v+A5vL/f+fz/4Tk6v935O7/SaDS/7nY5v/+/Pr//P78//3/+P////3//v////7////9////"
    "///7/////v///v7//v/8//z+/v/6/P//m8ri/0iq3v995+f/f+Xw/33n7f9/5u//hebv/3fM1f9WmqP/N2Fq/yE0Pf97gYX/"
    "6Ovq/9vY3JXJx8gCAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA2tvb701fZP9frrj/gObx/3/m8f+A5u//eujy/0mi1P/F4u3/"
    "+f7+//7//f////z///////////////////////////////////////////////////////n//f/7+/b/r9Lh/0uu4f9+5+j/"
    "geP6/37n8P9/5vD/fubw/3zo7f+C5u3/ds7U/zdkaf84R0z/09rb/9fa2owAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADl5ubv"
    "RFZb/2W1vv+A5vH/f+bx/3/l8/9Wtdf/rtXp//v9+v///vz////9/////v//////////////////////////////////////"
    "/////////////////v78//39/v/6/vr/lL7e/13G5v+C5uf/fefw/3/m8f+A5vH/gObx/3/m8f9/5vD/guft/06Mkf89Tk//"
    "5+/t+5aamSQAAAAAAAAAAAAAAAAAAAAAoaCgGvX29fUvSUn/ccTO/3/n7/+D5PD/ctzq/2qu0//7/fz//f7+//7++f/+/vv/"
    "+//////+/P/9//3//v////////////////////////////7//v/8//7//f/9//v////8///+///0/Pr/VaLW/4Hh6v9+5/T/"
    "gOby/4Dm8v9+5/L/f+bx/4Dm8P966PH/h+Lo/ypNU/+zvL7/3N3bcQAAAAAAAAAAjo2IGMvLyJrx8/Lzsbm4/yA0PP9619z/"
    "geXz/37o6f9Kqtb/2O3z//7+/P/+//7/+f////v+/f/+/fn//v78//7//f////////////////////////////7+/v/+/fz/"
    "/vz6//3+/v////////////v+/v/A3Ov/ULrf/4Dl8v9/5/D/f+fw/3/n8P9/5/D/gObw/3/n8f9/5u7/SYeL/3iFiP/f4N61"
    "AAAAALq6ukjs7+3pu8TE/0paYP8gQkf/Yqq1/4Hk7/+B5u3/feDy/2epz//9/Pv/+/7+//79/f///vr/6/f7/4y+3v+Uwd7/"
    "8fv9///+/v/////////////////+/v7/8Pf6/4y+3/+UwuD/9Pr7/////////////v79//j9/P9RpdX/gOb0/4Dm8v+A5vL/"
    "gOby/4Dm8v+A5vD/geXw/4Hk8/9epaz/UmZn/+/w7tKuraot7PDv9nKChP8iO0L/V5Wc/4Le6P9/5fD/gObx/4Hk7/9eyeX/"
    "rc7k///+/v/+/////f////79+P93s9j/G4PS/x+Bx/+Sw+H///37/////////////f79//v7/f+Atdn/G4PP/xuD0P+QwuH/"
    "/v7+///////9//7//P79/4y52v9w2fH/f+bt/4Dm8P+A5vH/gOby/4Dm8f+A5vH/f+Tx/2a8wv89T1T/4uTk+uPj4pmcpaj/"
    "KkxY/3zW2/966O//f+bw/3/m8P9/5/D/gObv/0uw2f/a7vj//////////////////P/+/2Wm0f8ahNP/FoXW/3202f/+/v7/"
    "///////////9//r//P77/2Oq2v8ZhdT/G4PQ/3q13v/+/v7///////3//v/8/v3/utjr/1zB4f9+5+z/f+fx/3/n8P9/5/H/"
    "f+fx/3/n8f9/5vD/bcXK/zVFS//p6uv/5OXl21ZlbP9eoar/fuju/4Ll8P+B5fL/gOby/3/m8v9+5+7/S6bX//D7/f//////"
    "///////+/f/+//7/0OLo/0KUzv9Nmcz/2+vx//7+/f/+//////////79+//4/vr/zuLs/0SVzP9Nmcz/3Ozy////////////"
    "/f/+//z+/v/c7fT/UK/X/3/n6v+A5vL/gOby/4Dm8v+A5vL/gObx/4Dm8v9uxcv/NUVL/+rr6//j4+T/OkpQ/2m/xv+A5vH/"
    "gOby/4Dm8v+A5vL/f+by/37l8f9Lp9P//P38/////////////////////////////P////3/////////uNXm/3623v+Ct93/"
    "f7Xb/9bo7//+/v3//f////3////////////////////+//3//P7+/+v2+f9IrNP/geXy/4Dn7v+A5vL/gOby/4Dm8f+B5fD/"
    "gOXw/2y1wf9AUlj/4eHh++vr7P80REn/bsbL/3/n8f9/5/H/f+fx/3/n8f9/5/H/fuXt/0eo0v/5/v3/////////////////"
    "//////////////////////////+21ej/fLTb/3m13/95tN3/1Ofv//7+/v////////////////////////////3//v/9/v3/"
    "5PP6/0et1v+B5fL/gOfu/3/n8f9/5vD/fufx/3zm8f+A5Oz/VZac/2VxdP/l5ePK5OXl/zlKT/9rwcf/gObx/4Dm8f+A5vL/"
    "gOby/4Dm8v9/5ev/RqvV/+z2+v////////////////////////////////////////////z9+v/8/fr//v36//79+v///fj/"
    "/P/+/////////////////////////////P////39/P/Q5vP/T7je/4Hl8v+A5+7/f+by/4Dl8P9/3OX/Y7C3/1CBiv8fOkD/"
    "usC//9LRz4zu7+7dSl1e/2Gvs/9/5u3/gebu/3/m8f+A5vL/f+by/4Hj8f9Rvdz/yd/v////////////////////////////"
    "///////////////////////////////////////////////////////////////////////////+//3//P77/6bL4v9izOP/"
    "f+Xx/3/m8f995u//cL7F/yA9Qv9AUFb/cn2F/8LIy//p6enclpaWGeTl48Vpd3n/U5Sd/4Hm7f+A5u7/gObw/3/n8P9/5/D/"
    "guPz/3DY5f+Hu+D//v7+////////////////////////////////////////////////////////////////////////////"
    "/////////////////////////v/8//j/a6vT/3vj9P9/5vD/f+fw/3/X3P8iPUb/pKes//Dy8fPl5OTH0tDRf4SEhBQAAAAA"
    "4+TilJKanv9Cc37/gObu/4Hm7v9/5+//gObx/4Dm8v+C5u//gebx/1Gjz//5+/3//f/9//7/////////////////////////"
    "/////////////////////////////////////////////////////////v////7//f75/+v0+f9Jp9X/gebx/4Dm8v+A5vH/"
    "R4aL/2pxdf/p6uzprq6uGgAAAAAAAAAAAAAAAAAAAADQ0M9bx8zQ/yRCS/996e7/ieHz/4Dm8P+B5fH/hOTx/4Dm8v9/5u7/"
    "X7/i/6nP5v/8/vv//v/7//////////////////////////////////////////////////////////////////////////7/"
    "///9/////P/8/Pr/irzc/2jR6f+B5fD/f+bx/4Hm8f8vUFz/t8HC/8bIxncAAAAAAAAAAAAAAAAAAAAAAAAAAKelohTu7+76"
    "PUdP/1idof9+5+//f+jx/33n8P976PH/f+fy/3/n7f9+5u//R6HQ/+f29//9/fz/////////////////////////////////"
    "/////////////////////////////////////////f////3/+v7//9Tq9P9Fqtb/guXv/37n7f9/5vD/gOfw/y9RXf+zvb7/"
    "zc/NfwAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAANTT0aXCzM3/ND9I/yZGTv85Zmv/SoCI/3XH0/9+5u//g+T0/4Ll8v9x1uf/"
    "aqbY//X9+P/+/f7////5//7//////////////////////////////////////////v////7//v///vv//v/9//39/f/s9/z/"
    "VKLJ/3ff8f9/5+r/gOXy/4Dm8v9/5vH/TYyT/1tsbf/q6+zqY2NjFgAAAAAAAAAAAAAAAAAAAAAAAAAAlZWVCefl5qXv8PH8"
    "wMfJ/52nqv91e3//HkFG/3zU2f9+5/L/guTx/3vo6v9lyOX/eKzY//H7+//9/f7//v/6////////////////////////////"
    "//////////////7//v/9//n//v/7/v7/7fX4/1Wk0v9v0ur/fuXx/3/n7v9/5vD/f+bx/3/m8f9/3eT/IDxC/8TIzP/Q0NCE"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAKGfnS3Pz8xs0NLPmO3s6u11f4T/NVxg/4Dk6v+A5u//hOPy/4Xj7f9hzeL/"
    "WaTS/9rv8v/+/P3////////////////////////////////////////////+//7/+v38/9Ll7v9Koc//dNPm/4Hm7/9/5vD/"
    "f+by/3/m8f9/5vH/f+bx/33m7/9Ukpr/VWFm/+np6e9CQkIHAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "t7e4RO3t8PtHVVr/UIWQ/37n9P986e//fub0/4Hk9v9z3O7/S6HQ/4u82P/g8fn//f77//3//P/+/vz///77//79/v/+/v7/"
    "+/7+/9nr9f97sdn/R6nX/3/e7/996PH/f+fu/4Dm8f+A5vP/gObz/4Dm8v+A5vL/guXw/3/d5f8dODz/4OTl/7GvsT0AAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA1NTVe9fd3v8lPEL/arrD/3/m8f9/5vH/f+by/3/n7/+A5vP/"
    "ZtLs/0qp0f9bpNT/grjV/5/L4/+ozub/ncjj/3q23f9Uo9j/Sa3V/27Y6v+C5uv/fuXw/3/m8f9/5vH/f+bx/3/m8f9/5vH/"
    "f+bx/3/m8f9/5+7/hOXr/yI/RP/S19n/xMHDTAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "5+rqxXyGif9NiI3/f+bx/3/m8f9/5vL/f+bw/3/n7P+D5fD/gOXy/4Hn8f902e7/Z8zo/2TI5/9nzub/eNzs/4bk8/+E4/P/"
    "f+fs/37m8v9/5vH/f+bx/3/m8f9/5vH/f+bx/3/m8f9/5vH/gObx/33n8P9qtLf/MkRJ/+zu8f2Vk5gVAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADy8vSff4uO/0qIjv+A5vL/gOby/4Dm8v+A5vL/gObx/4Dn8P996O//"
    "f+ft/3/n7f+A5u7/fOjx/33m8v996fL/eenu/33o7f+C5PL/geXz/4Dl8v+A5vD/gOfw/4Dm8v+A5vL/gObx/4Ll7/9/5vH/"
    "fd7j/yZJTP+ip6v/3t7grgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAANPU1MpufoD/"
    "UZKY/3/m8f9/5vH/f+bx/3/m8f9/5vH/f+bx/3/m8f9/5vH/geXx/37o7P92wMj/R3qA/zFZYv8uTlr/NFhj/0V7g/9xxMj/"
    "gOXx/33n8/9+5/D/f+bx/3/m8f+B5u7/f+bu/4Tk6/84aG//YWxw/+rt7vSampopAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA4uPjymR0dv9YmaD/f+bx/3/m8f9/5vH/f+bx/3/m8f9/5vH/f+bx/3/m8f+A5vH/"
    "a7W5/yA5PP97hob/rLW1/7nBwv+stLT/foKH/yM4PP9kpaz/geXx/3/m8v9/5vH/f+bx/3/n7f9/5vH/VoiR/0JPV//p6ur+"
    "ycnKWAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADf4eC8dH+C/1SJkv+C5PH/"
    "fufw/4Dn7/+A5/D/fufw/3/n7/9/5+//f+fw/4Dj6P8nSU//p66w/+/t78vf3t59wMHBfeHe333k5eXTwMbI/yM6Qf9jqK//"
    "geft/3/m7/9/5fH/feft/2qwuP8mO0P/2dvd/87OzogAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAANDQz4DAxcb/HjxD/2i1uP+E5e7/gObz/4Hl8P+D5PD/fuby/33m8/+D5PH/V5Sb/0pYXP/x8fP0"
    "hYSFIwAAAAAAAAAAAAAAAMXFxQfv8O+2vsLE/yU8P/8zY2j/VJCX/1+kq/9WkZj/ITlB/7a6vf/k5OS2g4ODAgAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAApaSiEerr6t6srrP/Kz1A/ydTV/9KiJH/"
    "ZLbA/3XR2P91z9b/abK4/0R4fP8kOkH/zM/Q/8zQz4wAAAAAAAAAAAAAAAAAAAAAAAAAAMjIwwrh4+C25ujp/5mhov9mdXX/"
    "UGJl/1xtcP+/w8T/7e7ry6amphAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAnp2dH93d3rjp7+7/sLW1/3J4fP88SVD/KztA/yY9Qf86T1L/eYKH/9jb3P/m5+e2kJuVBwAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAF5jYgK9v79J4uLhmejo6M7m5ubq5OXl3NTV1JWMj4sTAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAALi6uS/W19aH6+3sxu3v7v/8//3/"
    "+v/9/+jr6v7o6ejCz8/PZnh4eAYAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=="
)

# ================================================================ 抗锯齿位图
# Tk 画布的 oval / arc / 多边形都没有抗锯齿，圆环、圆点、胶囊边缘都会有明显锯齿。
# 这里用 4x 超采样把它们预渲染成位图：外部像素填成抠色（完全透明），视觉上就是平滑圆角。
def _hex_rgb(color: str):
    return (int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16))


def _rgb_hex(rgb) -> str:
    return "#%02X%02X%02X" % (rgb[0], rgb[1], rgb[2])


def _lerp(a, b, t: float):
    return (int(round(a[0] * (1.0 - t) + b[0] * t)),
            int(round(a[1] * (1.0 - t) + b[1] * t)),
            int(round(a[2] * (1.0 - t) + b[2] * t)))


def _mix_hex(bg, fg, cov: float) -> str:
    if cov <= 0.0:
        return _rgb_hex(bg)
    if cov >= 1.0:
        return _rgb_hex(fg)
    return _rgb_hex(_lerp(bg, fg, cov))


GRAD_STEPS = 96          # 渐变分级（同时让 Tk 的取色缓存命中，铺图更快）


def panel_row_color(y: int, h: int, top_rgb, bottom_rgb) -> str:
    t = max(0.0, min(1.0, float(y) / max(1, h - 1)))
    t = round(t * GRAD_STEPS) / GRAD_STEPS
    col = _lerp(top_rgb, bottom_rgb, t)
    gloss = 1.0 - t / 0.45          # 顶部一点淡淡的聚光
    if gloss > 0.0:
        col = _lerp(col, (255, 255, 255), 0.12 * min(1.0, gloss))
    return _rgb_hex(col)


_PPM_SEQ = [0]


def _photo_from_ppm(master, w: int, h: int, body: bytes):
    """把 P6 原始像素写进临时 ppm 再让 Tk 读回来：比逐点 put 颜色名快得多"""
    _PPM_SEQ[0] += 1
    path = os.path.join(tempfile.gettempdir(),
                        "di_panel_%d_%d.ppm" % (os.getpid(), _PPM_SEQ[0]))
    try:
        with open(path, "wb") as fp:
            fp.write(b"P6\n%d %d\n255\n" % (w, h) + body)
        return tk.PhotoImage(master=master, file=path, format="ppm")
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def make_panel_image(master, w: int, h: int):
    """整块胶囊：垂直糖果渐变 + 双层描边 + 4x 超采样抗锯齿边缘

    形状是胶囊（圆角半径 = 半高），一行的左右边界能解析算出来，
    所以只有边缘那几个像素要算超采样，中间整段是同一行的渐变色、按字节重复；
    最后拼成 P6 原始像素一次读进 PhotoImage。输出和旧的逐点版本逐位一致。
    """
    key_rgb = _hex_rgb(KEY_COLOR)
    top_rgb = _hex_rgb(BG_TOP)
    bot_rgb = _hex_rgb(BG_BOTTOM)
    rim_rgb = _hex_rgb(BORDER)
    deep_rgb = _hex_rgb(BORDER_DEEP)
    key_bytes = bytes(key_rgb)

    x0, y0, x1, y1 = 1.5, 1.5, w - 1.5, h - 1.5
    r = (y1 - y0) / 2.0
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    half = max(0.0, (x1 - x0) / 2.0 - r)

    def shade(sd, base_rgb):
        """按到边缘的有符号距离给颜色：|grad| = 1，所以覆盖率就是 0.5 - sd"""
        if sd <= -2.6:                       # 内部：本行渐变色
            return base_rgb
        if sd >= 1.2:                        # 完全在形状外
            return key_rgb
        cov = 0.5 - sd
        if cov <= 0.0:
            return key_rgb
        if cov > 1.0:
            cov = 1.0
        edge = deep_rgb if sd > -1.0 else rim_rgb
        return _lerp(key_rgb, edge, cov)

    body = bytearray()
    sq = math.sqrt
    for y in range(h):
        base_rgb = _hex_rgb(panel_row_color(y, h, top_rgb, bot_rgb))
        dy = y + 0.5 - cy
        ady = abs(dy)
        if ady >= r + 1.2:                       # 这一行整行都在形状外
            body += key_bytes * w
            continue
        # 直段（|x-cx| <= half）在这一行里 sd 恒定 = ady - r，整段同一种颜色
        mid_rgb = shade(ady - r, base_rgb)
        mid_bytes = bytes(mid_rgb)
        m_lo = max(0, int(math.ceil(cx - half - 0.5)))
        m_hi = min(w - 1, int(math.floor(cx + half - 0.5)))
        arc = sq((r + 1.2) ** 2 - dy * dy)       # 圆头这一段还要算的横向范围
        o_lo = max(0, int(math.floor(cx - half - arc - 0.5)))
        o_hi = min(w - 1, int(math.ceil(cx + half + arc - 0.5)))

        if o_lo > 0:
            body += key_bytes * o_lo
        for x in range(o_lo, m_lo):              # 左圆头
            dxq = abs(x + 0.5 - cx) - half
            if dxq < 0.0:
                dxq = 0.0
            body += bytes(shade(sq(dxq * dxq + dy * dy) - r, base_rgb))
        if m_hi >= m_lo:
            body += mid_bytes * (m_hi - m_lo + 1)
        for x in range(m_hi + 1, o_hi + 1):      # 右圆头
            dxq = abs(x + 0.5 - cx) - half
            if dxq < 0.0:
                dxq = 0.0
            body += bytes(shade(sq(dxq * dxq + dy * dy) - r, base_rgb))
        tail = w - (o_hi + 1)
        if tail > 0:
            body += key_bytes * tail

    if len(body) != w * h * 3:
        raise RuntimeError("panel bytes %d != %d" % (len(body), w * h * 3))
    return _photo_from_ppm(master, w, h, bytes(body))


# ---------------------------------------------------------------- PNG：解码 / 写带透明通道的位图
def _png_decode(data: bytes):
    """解 8 位 RGB / RGBA、非隔行的 PNG，返回 (宽, 高, RGB 字节)。图片轮换的素材走这条路径。"""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a png")
    pos, w, h, depth, ctype, inter = 8, 0, 0, 0, 0, 0
    idat = []
    while pos + 8 <= len(data):
        ln = struct.unpack(">I", data[pos:pos + 4])[0]
        tag = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + ln]
        if tag == b"IHDR":
            w, h, depth, ctype, _comp, _filt, inter = struct.unpack(">IIBBBBB", body)
        elif tag == b"IDAT":
            idat.append(body)
        elif tag == b"IEND":
            break
        pos += 12 + ln
    if depth != 8 or ctype not in (2, 6) or inter != 0:
        raise ValueError("unsupported png %d/%d/%d" % (depth, ctype, inter))

    raw = zlib.decompress(b"".join(idat))
    ch = 4 if ctype == 6 else 3
    stride = w * ch
    out = bytearray(h * stride)
    prev = bytearray(stride)
    p = 0
    for y in range(h):
        ft = raw[p]
        p += 1
        line = bytearray(raw[p:p + stride])
        p += stride
        if ft == 1:
            for i in range(ch, stride):
                line[i] = (line[i] + line[i - ch]) & 0xFF
        elif ft == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ft == 3:
            for i in range(stride):
                a = line[i - ch] if i >= ch else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xFF
        elif ft == 4:
            for i in range(stride):
                a = line[i - ch] if i >= ch else 0
                b = prev[i]
                c = prev[i - ch] if i >= ch else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 0xFF
        out[y * stride:(y + 1) * stride] = line
        prev = line

    if ch == 4:
        rgb = bytearray(w * h * 3)
        for i in range(w * h):
            j, k = i * 4, i * 3
            rgb[k:k + 3] = out[j:j + 3]
        return w, h, rgb
    return w, h, out


def _png_bytes_rgba(w: int, h: int, rows) -> bytes:
    """把逐行 RGBA 字节编成 PNG（图标要压在照片上，必须带透明通道）"""
    return _png_pack(w, h, 6, b"".join(b"\x00" + bytes(r) for r in rows))


def _rgba_photo(master, w: int, h: int, rows, into=None):
    """into 不为空时原地换内容：画布上已经绑着这张图，重建对象会让它消失"""
    data = base64.b64encode(_png_bytes_rgba(w, h, rows)).decode("ascii")
    if into is not None:
        into.configure(data=data)
        return into
    return tk.PhotoImage(master=master, data=data)


def make_photo_panel_image(master, w: int, h: int, src_w: int, src_h: int,
                           src_rows, scrim_top: float, scrim_bot: float):
    """图片版胶囊底：原图居中裁剪铺满，压一层上亮下暗的遮罩，外形与描边同渐变版一致"""
    key_rgb = _hex_rgb(KEY_COLOR)
    key_bytes = bytes(key_rgb)
    top_rgb = _hex_rgb(BG_TOP)
    bot_rgb = _hex_rgb(BG_BOTTOM)
    rim_rgb = _hex_rgb(BORDER)
    deep_rgb = _hex_rgb(BORDER_DEEP)

    # 居中裁剪窗（cover）：按比例裁掉多出来的一边
    if src_w * h > w * src_h:
        cw, chh = src_h * w / float(h), float(src_h)
        x0, y0 = (src_w - cw) / 2.0, 0.0
    else:
        cw, chh = float(src_w), src_w * h / float(w)
        x0, y0 = 0.0, (src_h - chh) / 2.0

    x0p, y0p, x1p, y1p = 1.5, 1.5, w - 1.5, h - 1.5
    r = (y1p - y0p) / 2.0
    cx, cy = (x0p + x1p) / 2.0, (y0p + y1p) / 2.0
    half = max(0.0, (x1p - x0p) / 2.0 - r)
    sq = math.sqrt

    def shade(sd, base_rgb):
        if sd <= -2.6:
            return base_rgb
        if sd >= 1.2:
            return key_rgb
        cov = 0.5 - sd
        if cov <= 0.0:
            return key_rgb
        if cov > 1.0:
            cov = 1.0
        edge = deep_rgb if sd > -1.0 else rim_rgb
        return _lerp(key_rgb, edge, cov)

    def photo_at(x, y):
        fx = x0 + (x + 0.5) * cw / w
        fy = y0 + (y + 0.5) * chh / h
        ix = int(fx)
        iy = int(fy)
        if ix >= src_w - 1:
            ix = src_w - 2
        if iy >= src_h - 1:
            iy = src_h - 2
        tx, ty = fx - ix, fy - iy
        i0 = (iy * src_w + ix) * 3
        i1 = i0 + src_w * 3
        p00 = src_rows[i0:i0 + 3]
        p10 = src_rows[i0 + 3:i0 + 6]
        p01 = src_rows[i1:i1 + 3]
        p11 = src_rows[i1 + 3:i1 + 6]
        w00 = (1.0 - tx) * (1.0 - ty)
        w10 = tx * (1.0 - ty)
        w01 = (1.0 - tx) * ty
        w11 = tx * ty
        rgb = (int(p00[0] * w00 + p10[0] * w10 + p01[0] * w01 + p11[0] * w11 + 0.5),
               int(p00[1] * w00 + p10[1] * w10 + p01[1] * w01 + p11[1] * w11 + 0.5),
               int(p00[2] * w00 + p10[2] * w10 + p01[2] * w01 + p11[2] * w11 + 0.5))
        return rgb

    body = bytearray()
    for y in range(h):
        t = y / float(max(1, h - 1))
        veilt = scrim_top * (1.0 - t) + scrim_bot * t
        veil = _lerp(top_rgb, bot_rgb, t)
        dy = y + 0.5 - cy
        ady = abs(dy)
        if ady >= r + 1.2:
            body += key_bytes * w
            continue
        arc = sq((r + 1.2) ** 2 - dy * dy)
        o_lo = max(0, int(math.floor(cx - half - arc - 0.5)))
        o_hi = min(w - 1, int(math.ceil(cx + half + arc - 0.5)))
        if o_lo > 0:
            body += key_bytes * o_lo
        for x in range(o_lo, o_hi + 1):
            dxq = abs(x + 0.5 - cx) - half
            if dxq < 0.0:
                dxq = 0.0
            sd = sq(dxq * dxq + dy * dy) - r
            px = photo_at(x, y)
            base = _lerp(px, veil, veilt)
            body += bytes(shade(sd, base))
        tail = w - (o_hi + 1)
        if tail > 0:
            body += key_bytes * tail

    if len(body) != w * h * 3:
        raise RuntimeError("photo panel bytes %d != %d" % (len(body), w * h * 3))
    # 顺带把原始像素交出去：淡入淡出要拿它跟下一张混合
    return _photo_from_ppm(master, w, h, bytes(body)), bytes(body)


def _png_bytes_rgb(w: int, h: int, rows) -> bytes:
    """逐行 RGB 字节编成 PNG（淡入淡出的过渡帧用）"""
    body = b"".join(b"\x00" + bytes(r) for r in rows)
    return _png_pack(w, h, 2, body)


def _png_pack(w: int, h: int, color_type: int, body: bytes) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data +
                struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, color_type, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(body, 6)) +
            chunk(b"IEND", b""))


def _blend_rgb(a: bytes, b: bytes, t: float) -> bytes:
    """两张整条底图的线性混合（整数运算，避免每字节浮点乘）"""
    n = len(a)
    ta = max(0, int((1.0 - t) * 1000))
    tb = max(0, int(t * 1000))
    out = bytearray(n)
    for i in range(n):
        out[i] = (a[i] * ta + b[i] * tb) // 1000
    return bytes(out)


def _rgb_photo(master, w: int, h: int, body: bytes):
    """一整帧 RGB 像素 -> PhotoImage（淡入淡出的过渡帧）"""
    rows = [body[i * w * 3:(i + 1) * w * 3] for i in range(h)]
    return tk.PhotoImage(master=master,
                         data=base64.b64encode(_png_bytes_rgb(w, h, rows)).decode("ascii"))


def _scan_photos():
    """扫描脚本旁的 轮换图/ 目录，按文件名排序返回 PNG 路径（Tk 只认 PNG/GIF，用 PNG）"""
    folder = os.path.join(os.path.dirname(SCRIPT_PATH), PHOTO_DIR)
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return []
    return [os.path.join(folder, n) for n in names
            if n.lower().endswith(".png") and os.path.isfile(os.path.join(folder, n))]


AVATAR_B64 = (
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "/tUBDPzQCH7+1RA3AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAP/MAAD80Qla/NEm7/nQEtH/1wklAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAA/dIMB/rSGsL97Zf3+eiK8fnQFM390wI3/9kAAgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAB"
    "DQ0EAePhLA7Y1yc/z8wiQ+jdJhQ7NQMCAAAAAgAAAAEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAP/XBwX41Ap/8N1K8f794f3//fn/+euW8vTWPPL60hS1/dcSJQAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAATgzBwLr3TJC+eosyvjpJvr45iP7++oq1vLsOlRcWxgEAAAAAgAAAAEAAAAAAAAAAAAAAAAAAAAAAAAAAQAAAADJwDcC"
    "m5caD/bnLCXv5x420ckfRM7BJEXr3CY38+YnJqCYDBHBwTYDAAAAAQAAAAEAAAABAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAD/2QoF+NINhfLbQe38+sn6//36///9/////vn//vvM/PrgTPP6zhKYAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAEAAAAC2MswJvvkK+X+3R7//t4f//7gIP/95CL/+e4t8NfULDsAAAAFAAAAAwAAAAEAAAABAAAAAQAAAADEuhwV"
    "7eQnXvHnLKP37i3W/OMk6vfmKfPz7Tj5+vFN+fzwV/T88Vbq+O9O2fTtV6bt6ERitqwjGkM/DAEAAAACAAAAAQAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAP/XBx790Bbf/PGg9f/+8v///f////3////+9f757Iry+tIl0fzTGDAAAAAA"
    "AAAAAAAAAAAAAAABAAAAAgAAAAPt2iSP/t8g//7eIP/+3x///uAf//3jGf/85SD/6uQ3rwQCAAMAAAAGAAAAA1NNEgLj2jIe"
    "6+YiiPrpIuX95Bz8++Av//jkQv/88YH//vjF//396f/7/vD/+//w//7/8v///fD///vr//79zfz495/p7e1zj+Liah9hXA0D"
    "AAAAAgAAAAEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA/9UMBP7WDmf10RbY8dxf7/z3y/r//vv/+u6m9frPE8r/1Aow"
    "+dIEfv7WCkL70xIBAAAAAAAAAAEAAAAEAAAAAuvZG8D83B///tof///bHv//3B7//+Ac//3hI//47TLWMCQFCAAAAAqLhgQL"
    "+O82afnmKeX95Rz/++Ec//feVv/99Kz///zn//7++//+/vz//f/+//z//f/9///////////9/////vz///78//3+/f/+/+b/"
    "9vWy5/X1kHGvtlgOAAAAAwAAAAIAAAABAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAP7lGQ/4zQ9+9to+6/76t/rx3ELu"
    "+9IDUvvSEG352kDx9dMt5fjWC1j/2gcJAAAAAgAAAAUGAAAG5tomqfbcGv/92R3//9od///aHf//3hr//OEe/+3kLNqQhRoW"
    "rawoG/TnJqH75CP7/t0c//jfKv/67X3//v3j//39+//7//3//v/4///+8/////n//v79//z////+/v7////9////+////vf/"
    "/f7y//vvtv/vz3f/+vXE/PX4r7C8w20WAAAABAAAAAOCchED7eYdJenoG0/t6yJM6uIlGyAgEAIAAAACAAAAAfrvIwX73B18"
    "9do56/PYFrz70g1A89Ms1vvyt/j68a/29Ns57PzVCIwAAAACAAAABgEAAA3BuSlM+OYr/PzXHP/+2Bz//tob//7eGf/84R3/"
    "9eAm/uzaK7fw3ya9+eMk/v3gIv/13y//9u+W///+8f/8//v//P/5//7++v/w15j/8NV2//veqv/89Nv//f3p////+P///v7/"
    "/v7+//z73f/x03H/+Lck//LWc//+++z///3w//HzxcSzvGgdJycHB+zsLYb99SLt/vMf+v3yI/r88yLi/PssXDs7CwQAAAAC"
    "AAAAAezgPQX31x1G9NkSG/zUC5r741/0//zc/v/+5v746Fvv99YFoQAAAAIAAAAHAAAADxsSAxXazjKE+OIs9PzeJv/73yb/"
    "+OYt+PnoJ/v83SP//9oY//vdGv/73Rz//tsf//vul////fv///////z////8/////f/9//rkvP/2ynD/8L5E//a3Iv/ttDP/"
    "8uCt///9/f/8/v3/9/PN//C+T//2sSX/7LdK//PqwP///vr//vz6//Dyu8Ps4C18/PIh/PzvFv//7xz///Ae///xHv/99h/0"
    "4t8mQQAAAAUAAAADAAAAAQAAAAAAAAAA/dUOM/zMFcL82VXu/PGR9frPCMP/1QQTAAAAAgAAAAYAAAoOBQAAGhULAB+mmiZQ"
    "wbg7lb61OpuUiCJktagmdPneKvD/1xX//9kZ//vbIf/35mD///3s///+///+/////f////7////+/////v77//vyyP/11nH/"
    "8rgw//bLcP/88Nn//vv9//3+/v/9/fX//fbZ//3zzf/446v/+/bT//3//f/+/v///v3o//bqQ/z47Bv//O4f//7uH///7yD/"
    "//Ag//3xHP/x7y6rTU4OCAAAAAUAAAADAAAAAQAAAAAAAAAA/9QPDPfQEaTx1yLh/NADSgAAAAAAAAABAAAABAAAAwsBAQAV"
    "AQIAIQABACoBAwAsAAEAMwIDADefmyFh+N0u9//XIP//1CD/+tgx//z40P/9//7///7///z////+///////////////++uv/"
    "6MFa/+/NW//677j//v3x//758P/t36///v3q//zty//31qL//v7+//z////8//3//v7+///+/P///uL/+e05//ntG//86yb/"
    "/uwj///uIv//7iL//fAa/+zsK+SLjh8QAAAACgAAAAQAAAACAAAAAAAAAAAAAAAA/tUHC/zVCyn/0QUDAAAAAAAAAAEAAAAD"
    "AAAACAAAAA8AAAAYBQAAIQMAACgABQAxKywIM+bZL9D82iP//9cg//7TIv/75Wn////5//7//f///////v////7////9////"
    "/f////3++//8+ub//v3t///++v///f3///37/+rSgf/ozWP/6MNn//vktP///v7////////+/////v////7+////5v/z7D//"
    "/ewb//7rHv//7R7//+0f///uIP/+7iH/7est7nNyFhkAAAAPAAAABgAAAAIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAQAAAAIAAAAFAAAACQAAAA8BAAYVAgAAHAEBASG7sCJk99wj+/7XIP/92Rj//Nck//70sP///vn////+////////////"
    "/v////7////+/////P/+//3//v/+/vz///78///+/P///f3///7u//fsrv/78Mr///v1///+/////v////7////+/////v//"
    "//72//b1jf/75yL//esf//7tHf//7R7//+0e//7tIv/t6i3ucG0VGwAAABMAAAAIAAAAAwAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAQAAAAIAAAAFAAAACAAACg0AAAESKygEFunWJbP+1Bn//tUb//vaE//52zT//fze///+/v//////"
    "///////////////////////////9//7//v/+/////f////3////8///+/P///v3//v/8//7+/f///f////7////+/////v//"
    "///////////+/////v/n//vva//96ST//+od///rHv//7B///+si/+3oLe5sZRUcAwADFgAAAAoAAAAEAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAQAAAAIAAAAEAAAABgAAAA2voR4f99so6f/TIP//1R7/+9ga//jbPv/+/eL/"
    "//7+/////////////////////v////7///////v//f/+//z/+/7z//784v/9+cD/+/iv//r3xv///O3///v8///9+////v//"
    "/////////////////v////3////8//////3X//znPP//6Bv//+kf///qH//+6yL/7OY53lFKFhoEAAAXAAAADAAAAAQAAAAB"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAQAAAAIAAAAEU0wHCdnCKWz82yn9/9Qh///UIf/91h//"
    "+dw////93/////v////////////////////+/////f////3//v/0//370P/68HL/++Y1//niIv/44h3/9+Qi//TsTf/8+r3/"
    "///0///+/////////v////3////9/////P////z//////uX/++hD///nGv//6B///+kf//7vIP/f2SunDgoFGwAAABYAAAAM"
    "AAAABAAAAAEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABAAAAAsnBJBns2i2Q+toe+f7XHv//1R//"
    "/9Uf//3WH//53ED///3f////+/////////////////////7////9////+f/8853/9+I9//3lI//85x7/++Yk//vnIv/+5Rr/"
    "++Ya//XnTP/++tP///7+//////////////////7////9/////f/////95f/750L//+cc///nIf//5yH++u8o966rIVUDAAEj"
    "AAIAFQAAAAsAAAAEAAAAAQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAS0oAgPt2i44+uIuzP3XI/7+0hn/"
    "/9Qe///UH///1R///NUf//bZNf/++9v///39///+/v/////////9////+v///vb/+/Od//zhJ//94x///+Qf///lHf//5CH/"
    "/uUc//7kGf//4x3//eEj//zuhv////n///7//////v////////////7////8//7//f3T//njOv//5B7//uUf//3wIv3b2TGh"
    "GxkGKwAABiEAAAATAAAACgAAAAMAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAQAAAAKBgRUE+e0kYPvgJ+7+0Rr/"
    "/9Ea///SG///0x3//9Me///UH//80yH/9NQj//3ztv///Pr//v7+//////////3///74//r0tv/04Cv//uQd///kHv//5B7/"
    "/+Qe///kHv//4x7//+Mc///iIP//4h7/+uxr////9v///v/////+///////////////9//7/+P/996r/++Ep//znHP/57SH+"
    "4NwztTEuCzECAwQrAAADHAAAABAAAAAIAAAAAwAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACmY4JBfvrH2v74CD4"
    "/tAk///RHv//0hv//9Ed///SHv//0x7//9Qf///TIf/80h///ORz///++f///////////////v/++9j/9+ZO//zlGP/94h3/"
    "/uIe///hHv//4R7//+Ee///hHv//4hv//+Eg///fGv/66mj////1///+/////v7///7////+/////v7///7w//7reP/+4hz/"
    "8u4h9cvLMZ0WFQUxAgEEMgAABSQAAAAXAAAADAAAAAUAAAACAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACwjAAPu3CFa"
    "/N0e8/7SG///0SP//9Ie///SHP//0h3//9Me///THv//0x7//9If//7SHv/4zzT///rh//3//v/9/////v/2//vsiv/54hv/"
    "/uIc///gHv//4B7//+Ae///gHv//4B7//+Ae///hHf//4CD//90a//zpcf/+//j//v///////v/+/vz//P/+//7+/v//+9H/"
    "+uA7///pHv/CxCCUDQsBNQIBAjQAAgEpAAAAHQAAABEAAAAIAAAABAAAAAEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "1MQlH/jXKuH/0xz//9Md///THv//0x7//9Me///THv//0x7//9Ie//7QHf/90h3//NUX//zVIv/64X7//v/7//7//f/+/dX/"
    "/N85//3dI///3iX//98f///fH///3x///98f///fH///3x///98g///eIP/+3SP//vGZ//3//f/9/////v/+//3//P/6//b/"
    "/v7u//bpdP/85Rf//O4k+6GhJWoFAAI1BgAFLAIABiAAAAAVAAAACwAAAAUAAAACAAAAAQAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAC7shhh/top/v/UHv//0x3//9Me///THv//0x7//9Ig///SIP//0iD//9Ef//7TG//81Bj//dUW//bRHf/47KD/"
    "//31//71pv/73xf//Nkl//3cI///3B///9wf///cH///3B///9wf///cH//83x3//t0c//feOP/9+c3//P/+//z////9//3/"
    "///+//798v/58ov/9uMn//vhHf/x6SzrYWEXQQEAAC0BAAIhAAACFgAAAA0AAAAGAAAAAwAAAAEAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAL+0HlD83S38/tQd//7UHf/+0h3//9Ig//7RH//+0h3//9Qe//7THv/+0SD//tIc//3TGv/80xz/"
    "/c8j//PPNP/78qT/+epo//vcF//93Bv//t0a///bH///2x///9sf///aH///2h///9sf//3eIP/82xn/+Ohn//z97P/9//v/"
    "/f/8//7//////vn/+/Os//bcKv/+4CD//OQk/9/aL7oODQIrAAABJQAAABgAAAAOAAAABwAAAAMAAAABAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAal8TFeXWM5r63ib3/uAn///dJv/+3Sr//dss/vbTKfTpzCfc9NQg+v3RIf//0R3/"
    "/tIc//7SH//+0SL//tEj//zTLP/92i7//dof//7bH///3B7//toe//7aHv//2R7//9ke///ZHv//2R7//9si//XaJv/998T/"
    "/v31////+f////b///7q//vyk//33Tj//9wk///fI//56yj8p6AjagIAACoAAAAeAAAAEQAAAAkAAAAEAAAAAQAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEAAAUIRgEG4VzEzyjkSprp5UrfJWGJnN6bBhfSDoLSDUmBj7i0TvG"
    "/NYc///RHP/+0h3//9Id//7SHv/+0h3//dEd///XIf//2R///tke//7YHf/+2R3//tke///ZHf//2R7//9ge///YHf/72hL/"
    "9el8///88////Pv//f73//z4wP/25l7/+9wi//7gG//+3yX/+eEb/+feOdEcFwItAQAAJQAAABgAAAAMAAAABQAAAAIAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAARIAAAQdAAAAKgABAC8AAwA0AAABOQAAAjwCAAA+"
    "AgABPYh3H1b54R70/tEW///RHP//0Rv//9MZ//7TGv/+0xr//9cd///YHf/+2B3//dcb//7YHf/+2B3//tgd//7YHf/+2B3/"
    "/9cc//3eQf/++83//vrb//vypP/x5GL/8tYp//7aG//+3Br//9sg//3aH//15Sr4oZckWQMCAC0AAQAfAAAAEwAAAAkAAAAD"
    "AAAAAQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACDgAABBYAAAAgAAAAJwABACsAAAIu"
    "AAABLwAAADAAAgAzAgEALcrDJof73hz+/88g///RG///0xP//9Ee///THv//1R7//tYc///XHf//1x3//tgd//7YHf//1x3/"
    "/9cd///XHf/+2Bz//uBF//vbUf/41jH/+dUf//vVG//+1hr//dgb//rdGv/83SD//OQo/c3HL5UOCgMtAAMAKAABABoAAAAP"
    "AAAABgAAAAIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAJAAAADwAAABUAAAAa"
    "AAAAHgAAAB8AAAAgAAAAIQACACUBAAMrJSEHKtjGKqj73SH//dEk///RHP/+0h///9Mg///UH///1h3//9cc///XHf/+1x3/"
    "/tcd///WHf//1h3//9Yc///WHP/81hr//NUZ//3XGf/91xn//tYb///VG//91xz/+t0d//flLP/g1z62MysLMwQAAy4AAAAh"
    "AAAAFAAAAAsAAAAEAAAAAQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAUAAAAI"
    "AAAACwAAAA8AAAARAAAAEgAAABIAAAAUAAAAGAAABh4AAAEpJB0HK9nKKqX82ib8/tAd//7SHv//0yD//9Me///UHP//1Rv/"
    "/tYc//7WHf/+1Rz//9Qc///UHP//1Bv//9Qc//7VHP/91Rr//tcZ//3XGP/+1hv//9Ub//7XHP/54Sb+3thAsyojCjUDAAMz"
    "AQACJgAAABkAAAAPAAAABwAAAAMAAAABAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAgAAAAMAAAAFAAAABgAAAAcAAAAIAAAACAAAAAoAAAAOAAAAFAAAAB0CAAMpIBsKLM28M4n32Sb2+dYa//7SIP//0R7/"
    "/9Mb//7UHP//1B7//tQc///UHP//0xz//9Qc///UG///1Bz//tQd//3UHv/+1h3//tYc//3WH//72R7/+eIu+NHGNZwdFAU0"
    "AwEDNQAAACkAAAAcAAAAEgAAAAkAAAAEAAAAAQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABAAAAAQAAAAIAAAACAAAABAAAAAcAAAAMAAAAFAABAB8AAgIjk24YSsmfFOzpzS7t"
    "/tcp/f7SHP/90xv//dIb///THv/+0xz//tIc//7SHf/+0hz//tMb//7SHP/+0x3//tQe///VHf//1SL/+t0h/+TZLNigmyxp"
    "FwsFNgcAAzUBAAMrAAAAHwAAABQAAAALAAAABQAAAAIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABAAAAAgAAAAYBAAAMXEUJFc2fFnjhrxfu"
    "t5UToE86CjitkSp458ww0vvcJ/j81h/+/tQd//7SHf//0R3//9Ee///RHf//0hv//9Ed///SHf/+0x3//dMb//vgL/q3qhuG"
    "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"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAvrJXN/rFCl3zzAdp888SDAAAAAQAAAAHAAAACgAAAAwAAAAMAAAACwAAAAkAAAAG"
    "AAAABAAAAAIAAAABAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "//9VAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABSYz4C275BAf/VKgAAAAABAAAAAgAAAAMAAAAEAAAABQAAAAUAAAAE"
    "AAAAAwAAAAMAAAABAAAAAQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAD//wAAAAAAAAAAAAAAAAAAAAAAAQAAAAEAAAAB"
    "AAAAAQAAAAEAAAABAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAA=="
)

AVATAR_PX = 96                 # 头像位图边长（与 base64 数据一致）
AVATAR_D = 30                  # 条上显示的逻辑直径
AVATAR_CX = 34                 # 头像圆心的逻辑 x 坐标（胶囊左端加长后右移 16，屏幕上位置不变）

# 收起后显示的小图：用户提供的蛋仔派对横幅，裁到内容 + 圆角遮罩，
# 直接以 PNG base64 内嵌（Tk 8.6+ 原生可读），四周已在生成时压成抠色。
MINI_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAbcAAABwCAYAAACdDT5TAAAAAXNSR0IArs4c6QAAAARnQU1BAACxjwv8YQUAAAAJcEhZcwAA"
    "DsMAAA7DAcdvqGQAAP+lSURBVHhe7P0FgFfV3v2PK13DMN1JDN3dJYp0d8cMEwzd3d1ddly7EWxFQEVUQELEvvcaKHYyrN9a"
    "733OzIDo9T7P8//W/x5c7n32qX0+nzP79Vm7zjX/Wf6z/Gf5z/Kf5f/d5dKlS7iUcwngf1Dox02K+2ncT8FFt+4d/p/lf8ei"
    "L8xkX4oX974k90X9G7Jjc66Qv12n8+Pa72ry9v8j5T/+T89zFeUe490a0/Tw/X675Lb7umy/fGm58h7kq+nK4/LOn+/zMfnr"
    "Ls0/1p0n57Lz5Z43N7/51q9Mv1L+sVfub6H32Wj9d/qjdMo/x2W62v5+Wv7r5I9fLv5P/7n1q16DUrop/2dJXbbNKfdzk66y"
    "XbpsnyuU/zu47Pjf5SVf2hVSYWjx/PvmP8biec9BfuXP22V5+Ve68nqWl3yfuZdm57wizN3nd+Iu+bcrruO8MC//V96Lv35l"
    "mh/Pp9xr5emye7Zs5g//hS47Ni/t8nPmxXMkfz9Pf3XJPY93nJ3Hu0/9PXvF73+W/4nFPljvg86T/0Xkl0v/fZqf7sfz68r9"
    "/f2uXP+jff+FlMff5fN/Xn7Bk1sAmWz18uv/W3nhOezf1bb9ia685pX6V9tNXv7/UH9luxPXvER/258rL4P5DjXlv6aL//k+"
    "V9t+NfnHuPy6+NXktv+1c/4rXT2f/955/fxeqcu3/5Vzun3yH/tX9EfXzL+Pn5an/Pfqy+0nXb5vnq7c58/2d9t+f+4/uqaU"
    "d9zvz5dfV9v+R8f45+P1/p0l33G/l3dugx118eJ/YPfvLJcuer+GLjmouU/V+2D12XvruYsl/oH+ZLna7v9TunK52j6X6cqE"
    "fNEr5Uf8j8GXv1wt7bKE/Dv8qfzIFcn/QrnL1TZK3nK1Tf+W8q3ki16mP13+4s7/YrMt+U+TX/5ytW355S9X25Zf+ZerpedP"
    "y5/uJ1z5zPjKv1xt+7+Sv/xRur9cln6VHfMn+clXpl1NV0u8SpLpz5ar7f9X5C//Ku3P0v9dXW256j5/tPMfLflOYEG+eF6a"
    "BzlPcope8f2f5crFt9P2QeV+aPo0/7P8Z/nP8p/lP8t/d8kPo7+iv7po18uO/Q/o8hza5XXD/ofllPvTgfKjfsQ/xq0rSfu4"
    "/bR4yV6a988/7qr/vH3tXPmO99e9NC15+yvdrfn/9N/lYqrto1Uvnv+Y3Lhb/O22d/64/8/2V4on/s/tlz/04t5efvyyf35a"
    "/m3a3Y5wx7uYdy5GTbZuybnpuXH75+1n6wy9bVosUHp+2R7/ryzujt29+febm2rpbs1Po/g/kxf3l7xt/vnyH28b9J8pX+Ty"
    "eO5+V55Dyb9P/yuy0/7u+CvW9e+KuI6zwE832Yk8+ed1odvf2887R966224L1y2ef3uu8p1Dsn/+7vnSKSVacEW6ky70R9uc"
    "Ltuuf/nPZ+tOSrw8zQ79H1n8a1x2HU+//PwzPvrwQ7xy+DCeePxx3HXXXbj55ptwy803464778Ljjz2GgwdfxnvvncMPP3x/"
    "2bG++D8X5lu85Mvu0cr1/3+EnLvxnFyo/fGS78PKlY5zx17kOb7/6Td88M8LeP3UJzhw9D08/9pZPPPqWTz9ylk8dfgdp0Nn"
    "sF86eBr7qCell532vnwKew9Ip/H4S05PMP7Ey2fwOLc/8fI7pscPvIPHTEynnqD2Sjxe59vHffcxvp/Xe+a1d/HskXzi+nNH"
    "zlIMLa7wLNOZR+b1qcNn8cRLpzydxF7T23jygHQyVzp/bv4PnmH+dX3lxeX5cepJnmv/4Xexn/e//5V3ef538bQ+D13nFX4W"
    "lK1rO/O6j9J96HgXuvt77KUzePTF0wzdZ/LYi6cYpxg++uJJPPrCSTzy/NsM37b0vfyMnjxI8fr7TIzzM1e4j6H7zPlZmd7G"
    "i0dO47Mvv+FzcDH3u/1/Y9F9XMKPP36Pxx65D3upp/c+hOf2P4LnnnoEzz/1KF546jG88PTjTk89zjSFjzGk9j+aqxdMj1AP"
    "cfsd1B7ucxNDar8XWhq1fze1k9dxenbfDjz75HZqG57duw1PPboZ+x/chH33Uw9sNu29fwv23rcZd9y8FTt3UNu3YPu2rdiu"
    "cLvWt2HHjm3YxW27mHbXnk144u6tPMd2Tztw3+3bsMc79vZdd+LePY/i/j2P4/6bnmS49/e6KU8P3vwkHrwln7j+EMOHbtmH"
    "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"
)
# 收起小图的抠色：用户在源图上把背景改成了粉色，这里按粉色洪水填充抠成透明，
# 再用这个源图里不存在的洋红做窗口抠色，避免把图案里的黑描边一起抠掉。
MINI_BG = "#FF00FE"


def make_dot_image(master, diameter: int, color_hex: str, bg_rows):
    """糖果球状态点：抗锯齿圆 + 左上高光"""
    ss = 4
    d = max(6, int(diameter))
    cc = d / 2.0
    fg = _hex_rgb(color_hex)
    white = (255, 255, 255)
    hx, hy = cc - cc * 0.32, cc - cc * 0.36
    hr = cc * 0.30
    rows = []
    for y in range(d):
        bg = _hex_rgb(bg_rows[min(y, len(bg_rows) - 1)])
        row = []
        for x in range(d):
            dist = math.hypot(x + 0.5 - cc, y + 0.5 - cc)
            if dist <= cc - 1.0:
                cov = 1.0
            elif dist >= cc + 0.6:
                cov = 0.0
            else:
                cnt = 0
                for sy in range(ss):
                    for sx in range(ss):
                        if math.hypot(x + (sx + 0.5) / ss - cc, y + (sy + 0.5) / ss - cc) <= cc:
                            cnt += 1
                cov = cnt / float(ss * ss)
            if cov <= 0.0:
                row.append(_rgb_hex(bg))
                continue
            col = _lerp(bg, fg, cov)
            hd = math.hypot(x + 0.5 - hx, y + 0.5 - hy)
            if hd <= hr - 0.8:
                hcov = 1.0
            elif hd <= hr + 0.8:
                cnt = 0
                for sy in range(ss):
                    for sx in range(ss):
                        if math.hypot(x + (sx + 0.5) / ss - hx, y + (sy + 0.5) / ss - hy) <= hr:
                            cnt += 1
                hcov = cnt / float(ss * ss)
            else:
                hcov = 0.0
            if hcov > 0.0:
                col = _lerp(col, white, hcov * 0.9 * cov)
            row.append(_rgb_hex(col))
        rows.append("{" + " ".join(row) + "}")
    img = tk.PhotoImage(master=master, width=d, height=d)
    img.put(" ".join(rows))
    return img


_STICKER_CACHE = {}


def _sticker_data():
    """解码原图贴纸：返回 (RGBA 字节, 边长)"""
    if "raw" not in _STICKER_CACHE:
        raw = base64.b64decode(GEAR_STICKER_B64)
        side = int(round(math.sqrt(len(raw) / 4.0)))
        _STICKER_CACHE["raw"] = raw
        _STICKER_CACHE["side"] = side
    return _STICKER_CACHE["raw"], _STICKER_CACHE["side"]


_AVATAR_CACHE = {}


def _avatar_data():
    """解码蛋仔头像位图：返回 (RGBA 字节, 边长)"""
    if "raw" not in _AVATAR_CACHE:
        raw = base64.b64decode(AVATAR_B64)
        _AVATAR_CACHE["raw"] = raw
        _AVATAR_CACHE["side"] = int(round(math.sqrt(len(raw) / 4.0)))
    return _AVATAR_CACHE["raw"], _AVATAR_CACHE["side"]


def make_avatar_image(master, size: int, bg_rows, tint=(1.0, 1.0, 1.0)):
    """把蛋仔头像贴到胶囊上：逐行用该行渐变底色做 alpha 合成，tint 做负载色偏"""
    raw, side = _avatar_data()
    size = max(8, int(size))
    tr, tg, tb = tint
    rows = []
    for y in range(size):
        bg = _hex_rgb(bg_rows[min(y, len(bg_rows) - 1)])
        row = []
        sy = min(side - 1, max(0, int((y + 0.5) * side / size)))
        for x in range(size):
            sx = min(side - 1, max(0, int((x + 0.5) * side / size)))
            i = (sy * side + sx) * 4
            a = raw[i + 3] / 255.0
            if a <= 0.0:
                row.append(_rgb_hex(bg))
                continue
            fg = (min(255, int(raw[i] * tr)),
                  min(255, int(raw[i + 1] * tg)),
                  min(255, int(raw[i + 2] * tb)))
            if a >= 1.0:
                row.append("#%02X%02X%02X" % fg)
            else:
                row.append(_rgb_hex(_lerp(bg, fg, a)))
        rows.append("{" + " ".join(row) + "}")
    img = tk.PhotoImage(master=master, width=size, height=size)
    img.put(" ".join(rows))
    return img


def make_sticker_image(master, size: int, bg_rows, boost: float = 1.0):
    """把原图齿轮贴纸贴到胶囊上：逐行用该行的渐变底色做 alpha 合成，边缘自然过渡"""
    raw, side = _sticker_data()
    size = max(8, int(size))
    rows = []
    for y in range(size):
        bg = _hex_rgb(bg_rows[min(y, len(bg_rows) - 1)])
        row = []
        sy = min(side - 1, max(0, int((y + 0.5) * side / size)))
        for x in range(size):
            sx = min(side - 1, max(0, int((x + 0.5) * side / size)))
            i = (sy * side + sx) * 4
            a = raw[i + 3] / 255.0
            if a <= 0.0 and boost <= 1.0:
                row.append(_rgb_hex(bg))
                continue
            if a >= 1.0 and boost <= 1.0:
                row.append("#%02X%02X%02X" % (raw[i], raw[i + 1], raw[i + 2]))
                continue
            fg = (min(255, int(raw[i] * boost)),
                  min(255, int(raw[i + 1] * boost)),
                  min(255, int(raw[i + 2] * boost)))
            row.append(_rgb_hex(_lerp(bg, fg, a)))
        rows.append("{" + " ".join(row) + "}")
    img = tk.PhotoImage(master=master, width=size, height=size)
    img.put(" ".join(rows))
    return img


def make_avatar_alpha(master, size: int, tint=(1.0, 1.0, 1.0)):
    """头像贴纸（保留透明通道）：底色交给下层，渐变色 / 照片都能干净叠住"""
    raw, side = _avatar_data()
    size = max(8, int(size))
    tr, tg, tb = tint
    rows = []
    for y in range(size):
        sy = min(side - 1, max(0, int((y + 0.5) * side / size)))
        row = bytearray()
        for x in range(size):
            sx = min(side - 1, max(0, int((x + 0.5) * side / size)))
            i = (sy * side + sx) * 4
            row += bytes((min(255, int(raw[i] * tr)),
                          min(255, int(raw[i + 1] * tg)),
                          min(255, int(raw[i + 2] * tb)),
                          raw[i + 3]))
        rows.append(row)
    return _rgba_photo(master, size, size, rows)


def make_sticker_alpha(master, size: int, boost: float = 1.0):
    """齿轮贴纸（保留透明通道）"""
    raw, side = _sticker_data()
    size = max(8, int(size))
    rows = []
    for y in range(size):
        sy = min(side - 1, max(0, int((y + 0.5) * side / size)))
        row = bytearray()
        for x in range(size):
            sx = min(side - 1, max(0, int((x + 0.5) * side / size)))
            i = (sy * side + sx) * 4
            row += bytes((min(255, int(raw[i] * boost)),
                          min(255, int(raw[i + 1] * boost)),
                          min(255, int(raw[i + 2] * boost)),
                          raw[i + 3]))
        rows.append(row)
    return _rgba_photo(master, size, size, rows)


class RingGauge:
    """抗锯齿环形进度：底色按胶囊渐变逐行取色，边缘 4x 超采样"""

    SS = 4

    def __init__(self, master, diameter: int, band: float,
                 track_hex: str, accent_hex: str, track_a: int = 255):
        self.master = master
        self.d = max(8, int(diameter))
        self._track = _hex_rgb(track_hex)
        self._track_a = max(0, min(255, int(track_a)))
        self._accent = _hex_rgb(accent_hex)
        self.photo = tk.PhotoImage(master=master, width=self.d, height=self.d)
        self._rows = self._prepare(float(band))
        self._extent = None
        self.render(0.0)

    def _prepare(self, band: float):
        """只算几何：方位角 + 环覆盖率 + 外圈光晕覆盖率，颜色留到 render"""
        d, ss = self.d, self.SS
        cc = d / 2.0
        r_out = cc - 0.6
        r_in = max(1.0, r_out - band)
        edge = 0.9
        pad = 1.3                       # 光晕比环再宽一点，照片上才分得清
        rows = []
        for y in range(d):
            row = []
            for x in range(d):
                px, py = x + 0.5 - cc, y + 0.5 - cc
                dist = math.hypot(px, py)
                if abs(dist - r_in) <= edge or abs(dist - r_out) <= edge:
                    cnt = 0
                    for sy in range(ss):
                        for sx in range(ss):
                            qx = x + (sx + 0.5) / ss - cc
                            qy = y + (sy + 0.5) / ss - cc
                            qd = math.hypot(qx, qy)
                            if r_in <= qd <= r_out:
                                cnt += 1
                    cov = cnt / float(ss * ss)
                else:
                    cov = 1.0 if r_in <= dist <= r_out else 0.0

                if cov > 0.0:
                    halo = 0.0
                else:
                    lo, hi = r_in - pad, r_out + pad
                    if abs(dist - lo) <= edge or abs(dist - hi) <= edge:
                        cnt = 0
                        for sy in range(ss):
                            for sx in range(ss):
                                qx = x + (sx + 0.5) / ss - cc
                                qy = y + (sy + 0.5) / ss - cc
                                qd = math.hypot(qx, qy)
                                if lo <= qd <= hi:
                                    cnt += 1
                        halo = cnt / float(ss * ss)
                    else:
                        halo = 1.0 if lo <= dist <= hi else 0.0

                ang = math.degrees(math.atan2(px, -py)) % 360.0   # 0 = 正上方，顺时针
                row.append((ang, cov, halo))
            rows.append(row)
        return rows

    def render(self, ratio):
        ratio = max(0.0, min(1.0, ratio))
        extent = min(357.0, max(8.0, 360.0 * ratio))
        if self._extent is not None and abs(extent - self._extent) < 1.0:
            return
        self._extent = extent
        rows = []
        for row in self._rows:
            buf = bytearray()
            for ang, cov, halo in row:
                if cov > 0.0:
                    col = self._accent if ang <= extent else self._track
                    alpha = 255 if ang <= extent else self._track_a
                    buf += bytes((col[0], col[1], col[2], int(alpha * cov + 0.5)))
                elif halo > 0.0:
                    buf += bytes((6, 9, 14, int(118.0 * halo + 0.5)))
                else:
                    buf += b"\x00\x00\x00\x00"
            rows.append(buf)
        self.photo = _rgba_photo(self.master, self.d, self.d, rows, into=self.photo)


# ================================================================ 主界面
_ROUND_CACHE = {}
_SWITCH_CACHE = {}


def make_round_image(master, w: int, h: int, radius: float, fill_hex: str,
                     stroke_hex: str, bg_hex: str, stroke_w: float = 1.2):
    """抗锯齿圆角矩形：逐行解出水平跨度，只在边缘带算覆盖率，结果带缓存（开面板不卡）"""
    w, h = max(2, int(w)), max(2, int(h))
    radius = max(0.0, min(float(radius), min(w, h) / 2.0))
    key = (w, h, round(radius, 1), fill_hex, stroke_hex or "-", bg_hex, round(stroke_w, 2))
    hit = _ROUND_CACHE.get(key)
    if hit is not None:
        return hit

    bg = _hex_rgb(bg_hex)
    fill = _hex_rgb(fill_hex)
    stroke = _hex_rgb(stroke_hex) if stroke_hex else fill
    cx, cy = w / 2.0, h / 2.0
    bx, by = max(0.0, cx - radius), max(0.0, cy - radius)

    rows = []
    for y in range(h):
        qy = abs(y + 0.5 - cy) - by
        if qy <= 0.0 or radius <= 0.0:
            half = cx
        else:
            half = bx + math.sqrt(max(0.0, radius * radius - qy * qy))
        row = [bg_hex] * w
        if half > 0.0:
            fx0 = int(math.floor(cx - half + stroke_w + 0.5))
            fx1 = int(math.floor(cx + half - stroke_w + 0.5)) + 1
            if fx1 > fx0:
                a0, a1 = max(0, fx0), min(w, fx1)
                if a1 > a0:
                    row[a0:a1] = [fill_hex] * (a1 - a0)
            lo = max(0, int(math.floor(cx - half)) - 1)
            hi = min(w - 1, int(math.ceil(cx + half)) + 1)
            cut0 = min(max(fx0, lo), hi + 1)
            cut1 = min(max(fx1, lo), hi + 1)
            band = list(range(lo, cut0)) + list(range(cut1, hi + 1))
            for x in band:
                dist = abs(x + 0.5 - cx)
                o = half - dist + 0.5
                if o <= 0.0:
                    continue
                o = 1.0 if o > 1.0 else o
                f = half - stroke_w - dist + 0.5
                f = 0.0 if f <= 0.0 else (1.0 if f > 1.0 else f)
                col = _lerp(bg, stroke, o)
                if f > 0.0:
                    col = _lerp(col, fill, f)
                row[x] = _rgb_hex(col)
        rows.append("{" + " ".join(row) + "}")

    img = tk.PhotoImage(master=master, width=w, height=h)
    img.put(" ".join(rows))
    _ROUND_CACHE[key] = img
    return img


def make_switch_image(master, w: int, h: int, on: bool, bg_hex: str,
                      track_off: str = "#2B3547", track_on: str = "#4E9BFF",
                      knob_off: str = "#8C97AC", knob_on: str = "#FFFFFF"):
    """开关：跑道形轨道 + 圆钮，4x 超采样，带缓存"""
    w, h = max(8, int(w)), max(8, int(h))
    key = (w, h, bool(on), bg_hex, track_off, track_on, knob_off, knob_on)
    hit = _SWITCH_CACHE.get(key)
    if hit is not None:
        return hit

    ss = 4
    bg = _hex_rgb(bg_hex)
    track = _hex_rgb(track_on if on else track_off)
    knob = _hex_rgb(knob_on if on else knob_off)
    r = h / 2.0
    kd = h - 4.0
    kx = (2.0 + kd / 2.0) if not on else (w - 2.0 - kd / 2.0)
    ky = h / 2.0

    def in_track(px, py):
        qx = min(max(px, r), w - r)
        return math.hypot(px - qx, py - h / 2.0) <= r

    def in_knob(px, py):
        return math.hypot(px - kx, py - ky) <= kd / 2.0

    rows = []
    for y in range(h):
        row = []
        for x in range(w):
            rs = gs = bs = 0
            for j in range(ss):
                for i in range(ss):
                    px = x + (i + 0.5) / ss
                    py = y + (j + 0.5) / ss
                    if in_knob(px, py):
                        col = knob
                    elif in_track(px, py):
                        col = track
                    else:
                        col = bg
                    rs += col[0]
                    gs += col[1]
                    bs += col[2]
            n = ss * ss
            row.append(_rgb_hex((rs // n, gs // n, bs // n)))
        rows.append("{" + " ".join(row) + "}")

    img = tk.PhotoImage(master=master, width=w, height=h)
    img.put(" ".join(rows))
    _SWITCH_CACHE[key] = img
    return img


class SettingsPanel:
    """设置面板：从右端齿轮点开。控件全部画布自绘，点击由自己做命中测试，
    不走 canvas tag 绑定（底图会盖住控件导致点不动）。"""

    CARD_BG = "#141A24"
    CARD_STROKE = "#2A3445"
    ITEM_BG = "#242D3C"
    ITEM_STROKE = "#303B4E"
    ACTIVE_BG = "#4E9BFF"
    DANGER_BG = "#3A2027"
    DANGER_STROKE = "#5A2A33"
    DANGER_TEXT = "#FF8A8A"
    # 上面这些由 apply_theme() 按主题改写；面板逻辑尺寸放这里，预热位图时也用同一份
    W_LOG = 300
    H_LOG = 502

    def __init__(self, app):
        self.app = app
        S = app.S
        self.w = S(self.W_LOG)
        self.h = S(self.H_LOG)
        self.top = tk.Toplevel(app.root)
        self.top.overrideredirect(True)
        self.top.configure(bg=KEY_COLOR)
        try:
            self.top.wm_attributes("-transparentcolor", KEY_COLOR)
        except tk.TclError:
            pass
        self.top.wm_attributes("-topmost", True)

        x = app.anchor_cx - self.w // 2
        x = max(S(8), min(x, app.root.winfo_screenwidth() - self.w - S(8)))
        y = app.anchor_y + app.h + S(10)
        self.top.geometry(f"{self.w}x{self.h}+{x}+{y}")

        fam = app.f_label.cget("family")
        self.f_title = tkfont.Font(family=fam, size=11, weight="bold")
        self.f_row = tkfont.Font(family=fam, size=8)
        self.f_small = tkfont.Font(family=fam, size=7)

        self.canvas = tk.Canvas(self.top, bg=KEY_COLOR, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self._imgs = []
        self._hits = []
        self._cursor = ""
        self._build()
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<Motion>", self._on_motion)
        self.top.bind("<Escape>", lambda _e: self.close())
        self.top.lift()

    # ------------------------------------------------------------ 绘制
    def _keep(self, img):
        self._imgs.append(img)
        return img

    def _pill(self, bw, bh, fill, stroke=""):
        return self._keep(make_round_image(self.app.root, bw, bh, bh / 2.0, fill,
                                           stroke, self.CARD_BG, stroke_w=EDGE_W))

    def _hit(self, x0, y0, x1, y1, kind, payload=None):
        self._hits.append((x0, y0, x1, y1, kind, payload))

    def _build(self):
        c = self.canvas
        c.delete("all")
        self._imgs = []
        self._hits = []
        S = self.app.S
        w, h, pad = self.w, self.h, S(18)

        c.create_image(0, 0, anchor="nw", image=self._keep(
            make_round_image(self.app.root, w, h, S(16), self.CARD_BG,
                             self.CARD_STROKE, KEY_COLOR, stroke_w=EDGE_W)))

        c.create_text(pad, S(24), text="设置", anchor="w", font=self.f_title, fill=TEXT)

        cxx = w - pad - S(11)
        c.create_image(cxx, S(24), image=self._keep(
            make_round_image(self.app.root, S(22), S(22), S(11), self.ITEM_BG, "", self.CARD_BG)))
        c.create_text(cxx, S(23), text="×", font=self.f_title, fill=MUTED)
        self._hit(cxx - S(13), S(11), cxx + S(13), S(37), "close")

        # 主题：四枚糖果胶囊
        c.create_text(pad, S(58), text="主题", anchor="w", font=self.f_row, fill=MUTED)
        self._seg_row(S(94), [(k, THEMES[k]["label"]) for k in THEME_ORDER],
                      self.app.theme, "theme")

        # 刷新频率
        c.create_text(pad, S(130), text="刷新频率", anchor="w", font=self.f_row, fill=MUTED)
        cur = int(round(self.app.refresh_interval))
        self._seg_row(S(166), [(1, "1 秒"), (2, "2 秒"), (5, "5 秒")], cur, "rate")

        # 开关行
        self._switch_row(S(204), "图片轮换", self.app._photo_on, "photo")

        # 轮换间隔：三档，选了立刻生效（默认 25 秒）
        c.create_text(pad, S(248), text="轮换间隔", anchor="w", font=self.f_row, fill=MUTED)
        self._seg_row(S(284), [(10, "10 秒"), (25, "25 秒"), (60, "60 秒")],
                      int(self.app._photo_interval), "photo_gap")

        self._switch_row(S(330), "开机自启动", self.app._autostart_enabled(), "auto")
        self._switch_row(S(368), "全屏时自动隐藏", self.app._fs_hide, "fs")

        # 动作按钮
        self._action(S(410), "收起为图标", "collapse")
        self._action(S(452), "退出灵动岛", "quit", danger=True)

        with self.app.sampler.lock:
            up = self.app.sampler.data.get("uptime")
        if up:
            c.create_text(w // 2, S(486), text=fmt_uptime(up), font=self.f_small, fill=MUTED)

    def _seg_row(self, y, items, current, kind):
        """一排等宽胶囊分段：既是主题选择也是刷新频率选择"""
        c = self.canvas
        S = self.app.S
        pad = S(18)
        gap = S(8)
        n = max(1, len(items))
        seg_w = (self.w - pad * 2 - gap * (n - 1)) // n
        seg_h = S(30)
        for i, (val, label) in enumerate(items):
            bx = pad + i * (seg_w + gap) + seg_w // 2
            on = (val == current)
            img = self._pill(seg_w, seg_h, self.ACTIVE_BG if on else self.ITEM_BG,
                             "" if on else self.ITEM_STROKE)
            c.create_image(bx, y, image=img)
            c.create_text(bx, y, text=label, font=self.f_row,
                          fill=PILL_ON_TEXT if on else PILL_OFF_TEXT)
            self._hit(bx - seg_w // 2, y - seg_h // 2,
                      bx + seg_w // 2, y + seg_h // 2, kind, val)

    def _switch_row(self, y, label, on, kind):
        c = self.canvas
        S = self.app.S
        c.create_text(S(18), y, text=label, anchor="w", font=self.f_row, fill=TEXT)
        sw_w, sw_h = S(46), S(26)
        sw_x = self.w - S(18) - sw_w // 2
        c.create_image(sw_x, y, image=self._keep(
            make_switch_image(self.app.root, sw_w, sw_h, on, self.CARD_BG,
                              track_off=SW_TRACK, track_on=self.ACTIVE_BG,
                              knob_off=SW_KNOB, knob_on="#FFFFFF")))
        self._hit(sw_x - sw_w // 2, y - sw_h // 2, sw_x + sw_w // 2, y + sw_h // 2,
                  kind)

    def _action(self, y, label, kind, danger=False):
        c = self.canvas
        S = self.app.S
        bw = self.w - S(36)
        bh = S(34)
        c.create_image(self.w // 2, y, image=self._pill(
            bw, bh, self.DANGER_BG if danger else self.ITEM_BG,
            self.DANGER_STROKE if danger else self.ITEM_STROKE))
        c.create_text(self.w // 2, y, text=label, font=self.f_row,
                      fill=self.DANGER_TEXT if danger else TEXT)
        self._hit(self.w // 2 - bw // 2, y - bh // 2,
                  self.w // 2 + bw // 2, y + bh // 2, kind)

    # ------------------------------------------------------------ 交互
    def _pick(self, x, y):
        for (x0, y0, x1, y1, kind, payload) in self._hits:
            if x0 <= x <= x1 and y0 <= y <= y1:
                return kind, payload
        return None, None

    def _set_cursor(self, name):
        if name != self._cursor:
            self._cursor = name
            try:
                self.canvas.configure(cursor=name)
            except tk.TclError:
                pass

    def _on_motion(self, e):
        kind, _ = self._pick(e.x, e.y)
        self._set_cursor("hand2" if kind else "")

    def _on_click(self, e):
        kind, payload = self._pick(e.x, e.y)
        if kind == "close":
            self.close()
        elif kind == "theme":
            self.set_theme(payload)
            return
        elif kind == "rate":
            self.set_rate(payload)
        elif kind == "photo":
            self.toggle_photo()
        elif kind == "photo_gap":
            self.set_photo_gap(payload)
        elif kind == "auto":
            self.toggle_autostart()
        elif kind == "fs":
            self.toggle_fullscreen()
        elif kind == "collapse":
            self.close()
            self.app._collapse()
        elif kind == "quit":
            self.quit_app()

    def set_rate(self, val):
        self.app.set_rate_value(val)
        self._build()

    def set_theme(self, name):
        # 换主题要整块重建（面板底色、位图缓存都变了），app.set_theme 会把本面板换成新的
        self.app.set_theme(name)

    def toggle_autostart(self):
        self.app._auto_var = tk.BooleanVar(value=self.app._autostart_enabled())
        self.app._toggle_autostart()
        self._build()

    def toggle_fullscreen(self):
        self.app._fs_hide = not self.app._fs_hide
        if not self.app._fs_hide and self.app._hidden_for_fullscreen:
            self.app._show_island()
        self._build()

    def toggle_photo(self):
        self.app.set_photo_mode(not self.app._photo_on)
        self._build()

    def set_photo_gap(self, sec):
        self.app.set_photo_interval(sec)
        self._build()

    def quit_app(self):
        self.close()
        self.app._quit()

    def close(self):
        try:
            self.top.destroy()
        except Exception:
            pass
        self.app._settings = None


class IslandApp:
    def __init__(self):
        self.dpi = self._init_dpi()
        self.scale = self.dpi / 96.0
        self._scene_cache = {}        # {主题: 位图组}
        self._panel_cache = {}        # {主题: 渐变底图}
        self._photo_src = {}          # {路径: (宽, 高, RGB)}
        self._photo_panel_cache = {}  # {(路径, 宽, 高, 主题): 底图}
        self._photo_idx = 0           # 当前轮到第几张
        self._photo_job = None        # 轮换定时器
        self._photo_interval = PHOTO_INTERVAL
        self._panel_raw = None        # 当前底图的原始 RGB（算过渡帧要用）
        self._fade_frames = []        # 下一张图的过渡位图（提前算好的）
        self._fade_ready_for = None   # 这些过渡帧对应的图片路径
        self._fade_target = None
        self._fade_next_raw = None
        self._fade_step = 0
        self._fade_anim = 0
        self._fade_job = None
        self._prep_job = None

        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.configure(bg=KEY_COLOR)
        self.root.overrideredirect(True)
        try:
            self.root.wm_attributes("-transparentcolor", KEY_COLOR)
        except tk.TclError:
            pass
        self.root.wm_attributes("-topmost", True)
        try:
            self.root.tk.call("tk", "scaling", self.dpi / 72.0)
        except Exception:
            pass

        self._pick_fonts()
        self.w = self.S(STRIP_W)
        self.h = self.S(STRIP_H)
        self.anchor_cx = self.root.winfo_screenwidth() // 2
        self.anchor_y = self.S(TOP_OFFSET)

        self.canvas = tk.Canvas(self.root, bg=KEY_COLOR, highlightthickness=0,
                                borderwidth=0, bd=0)
        self.canvas.pack(fill="both", expand=True)

        self._cols = {}
        self._settings = None
        self._collapsed = False
        self._mini = None
        self._drag_off = None
        self._hidden_for_fullscreen = False
        self._fs_hide = False
        self.refresh_interval = 1.0
        self._cpu_name, self._mhz = _cpu_info()

        self.sampler = Sampler()
        self.sampler.start()

        cfg = _load_cfg()
        self.theme = cfg.get("theme") if cfg.get("theme") in THEMES else THEME_ORDER[0]
        apply_theme(self.theme)

        self._photos = _scan_photos()
        self._photo_on = bool(cfg.get("photos", True)) and bool(self._photos)
        try:
            self._photo_interval = max(2, min(600, int(cfg.get("photo_interval",
                                                                  PHOTO_INTERVAL))))
        except (TypeError, ValueError):
            self._photo_interval = PHOTO_INTERVAL

        self._bind()
        self._apply_geometry()
        self._build()
        self._update()

        self.root.after(500, self._ui_tick)
        self.root.after(2000, self._fullscreen_tick)
        self._photo_start()

    # ------------------------------------------------------------ 初始化
    @staticmethod
    def _init_dpi() -> int:
        try:
            ctypes.WinDLL("shcore").SetProcessDpiAwareness(2)
        except Exception:
            try:
                user32.SetProcessDPIAware()
            except Exception:
                pass
        try:
            return int(user32.GetDpiForSystem())
        except Exception:
            return 96

    def S(self, v):
        return int(round(v * self.scale))

    def _pick_fonts(self):
        fams = set(tkfont.families(self.root))
        ui = next((f for f in ("Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI")
                   if f in fams), "TkDefaultFont")
        num = next((f for f in ("Bahnschrift", "DIN Alternate", "Segoe UI")
                    if f in fams), ui)
        self._num_family, self._ui_family = num, ui
        self.f_val = tkfont.Font(family=num, size=11, weight="bold")   # 主数值
        self.f_label = tkfont.Font(family=ui, size=7)                  # 指标名
        self.f_menu = tkfont.Font(family=ui, size=9)

    def _bind(self):
        # 位置固定：左键拖动已禁用，只保留右键菜单
        self.root.bind("<Button-3>", self._on_menu)

    # ------------------------------------------------------------ 窗口几何
    def _apply_geometry(self):
        x = self.anchor_cx - self.w // 2
        self.root.geometry(f"{self.w}x{self.h}+{x}+{self.anchor_y}")

    def _panel_row(self, y):
        return panel_row_color(y, self.h, _hex_rgb(BG_TOP), _hex_rgb(BG_BOTTOM))

    # ------------------------------------------------------------ 底图：渐变 / 轮换图片
    def _panel_image(self):
        """当前该用的胶囊底图：开了图片轮换就取轮到的那张，否则用主题渐变"""
        if self._photo_on and self._photos:
            img, self._panel_raw = self._photo_panel(
                self._photos[self._photo_idx % len(self._photos)])
            return img
        self._panel_raw = None
        img = self._panel_cache.get(self.theme)
        if img is None:
            img = make_panel_image(self.root, self.w, self.h)
            self._panel_cache[self.theme] = img
        return img

    def _photo_panel(self, path):
        """返回 (位图, 原始 RGB 像素)；后者留着做淡入淡出的两端"""
        key = (path, self.w, self.h, self.theme)
        item = self._photo_panel_cache.get(key)
        if item is not None:
            return item
        sw, sh, rows = self._photo_source(path)
        img, raw = make_photo_panel_image(self.root, self.w, self.h, sw, sh, rows,
                                          PHOTO_SCRIM_TOP, PHOTO_SCRIM_BOTTOM)
        item = (img, raw)
        self._photo_panel_cache[key] = item
        while len(self._photo_panel_cache) > 6:       # 只留最近几张，别把内存吃满
            self._photo_panel_cache.pop(next(iter(self._photo_panel_cache)))
        return item

    def _photo_source(self, path):
        src = self._photo_src.get(path)
        if src is None:
            with open(path, "rb") as fp:
                src = _png_decode(fp.read())
            self._photo_src[path] = src
        return src

    def _apply_panel(self):
        """只换底图，不重建整条胶囊（轮换时用它，几乎不闪）"""
        if getattr(self, "_panel_item", None) is None:
            return
        self._panel = self._panel_image()
        self._invalidate_fade()          # 底图变了，之前算的过渡帧就作废
        try:
            self.canvas.itemconfigure(self._panel_item, image=self._panel)
        except tk.TclError:
            pass

    def _invalidate_fade(self):
        self._fade_frames = []
        self._fade_ready_for = None
        self._fade_target = None
        self._fade_next_raw = None

    def set_photo_mode(self, on):
        """开关图片轮换：底图和图标配色都要换，所以整条重画"""
        self._photo_on = bool(on) and bool(self._photos)
        _cfg_patch({"photos": self._photo_on})
        if getattr(self, "_panel_item", None) is None:
            return
        self._fade_abort()
        self.canvas.delete("all")
        self._cols = {}
        self._build()
        self._update()
        self._photo_start()

    def set_photo_interval(self, sec):
        """改轮换间隔：存进配置，并把定时器按新间隔重排"""
        try:
            sec = int(sec)
        except (TypeError, ValueError):
            return
        self._photo_interval = max(2, min(600, sec))
        _cfg_patch({"photo_interval": self._photo_interval})
        self._photo_start()

    def advance_photo(self, step=1):
        """切到下一张：过渡帧要是提前算好了，就走一段淡入淡出，否则直接换"""
        if not self._photos:
            return
        new_idx = (self._photo_idx + step) % len(self._photos)
        self._fade_abort()
        self._photo_idx = new_idx
        if (self._photo_on and self._fade_frames
                and self._fade_ready_for == self._photos[new_idx]
                and getattr(self, "_panel_item", None) is not None):
            self._fade_anim = 0
            self._fade_anim_tick()
            return
        self._apply_panel()
        self._prepare_next()

    def _fade_anim_tick(self):
        """每帧只是把算好的位图换上，不做任何像素运算，所以不会卡"""
        frames = self._fade_frames
        i = self._fade_anim
        if i >= len(frames):
            self._fade_job = None
            self._apply_panel()          # 收尾换回清晰的原图
            self._prepare_next()
            return
        try:
            self.canvas.itemconfigure(self._panel_item, image=frames[i])
        except tk.TclError:
            self._fade_job = None
            return
        self._fade_anim += 1
        self._fade_job = self.root.after(max(12, PHOTO_FADE_MS // (len(frames) + 1)),
                                         self._fade_anim_tick)

    def _prepare_next(self):
        """趁两次轮换之间的空档，把下一张的过渡帧一帧一帧先算好"""
        self._prepare_abort()
        if not (self._photo_on and self._photos and self._panel_raw is not None):
            return
        if self._fade_job is not None:       # 动画还在放，等它放完再算
            self._prep_job = self.root.after(200, self._prepare_next)
            return
        self._prep_job = self.root.after(400, self._prepare_panel)

    def _prepare_panel(self):
        """第一步：把下一张的底图渲出来（没缓存过的话这是最贵的一步）"""
        self._prep_job = None
        if not (self._photo_on and self._photos and self._panel_raw is not None):
            return
        path = self._photos[(self._photo_idx + 1) % len(self._photos)]
        if self._fade_ready_for == path and self._fade_frames:
            return
        try:
            _img, raw = self._photo_panel(path)
        except Exception:
            return
        self._fade_frames = []
        self._fade_target = path
        self._fade_next_raw = raw
        self._fade_step = 1
        self._prep_job = self.root.after(60, self._prepare_frame)

    def _prepare_frame(self):
        """第二步：一帧算一张过渡位图，算完就排下一帧，不占用连续时间"""
        self._prep_job = None
        if self._fade_next_raw is None or self._panel_raw is None:
            return
        i = self._fade_step
        if i >= PHOTO_FADE_STEPS:
            self._fade_ready_for = self._fade_target
            self._fade_next_raw = None
            return
        t = i / float(PHOTO_FADE_STEPS)
        try:
            body = _blend_rgb(self._panel_raw, self._fade_next_raw, t)
            img = _rgb_photo(self.root, self.w, self.h, body)
        except Exception:
            self._fade_next_raw = None
            return
        self._fade_frames.append(img)
        self._fade_step += 1
        self._prep_job = self.root.after(60, self._prepare_frame)

    def _prepare_abort(self):
        if self._prep_job is not None:
            try:
                self.root.after_cancel(self._prep_job)
            except Exception:
                pass
            self._prep_job = None

    def _fade_abort(self):
        if self._fade_job is not None:
            try:
                self.root.after_cancel(self._fade_job)
            except Exception:
                pass
            self._fade_job = None
        self._fade_anim = 0

    def _photo_start(self):
        self._photo_stop()
        if self._photo_on and self._photos:
            self._photo_job = self.root.after(self._photo_interval * 1000, self._photo_tick)
            self._prepare_next()

    def _photo_stop(self):
        if self._photo_job is not None:
            try:
                self.root.after_cancel(self._photo_job)
            except Exception:
                pass
            self._photo_job = None

    def _photo_tick(self):
        self._photo_job = None
        if not self._collapsed:
            self.advance_photo()
        self._photo_start()

    # ------------------------------------------------------------ 绘制
    def _build(self):
        c = self.canvas
        c.delete("all")
        self.w = self.S(STRIP_W)
        self.h = self.S(STRIP_H)
        w, h = self.w, self.h
        sc = self._scene()
        self._avatar_imgs = sc["avatars"]
        self._gear_imgs = sc["gears"]

        # 胶囊本体：默认渐变底，开了图片轮换就用当前那张图
        self._fade_abort()
        self._prepare_abort()
        self._invalidate_fade()
        self._panel = self._panel_image()
        self._panel_item = c.create_image(0, 0, image=self._panel, anchor="nw")

        # 左侧蛋仔头像（原图，按负载轻度变色）
        self._avatar = c.create_image(self.S(AVATAR_CX), h // 2,
                                      image=self._avatar_imgs[COL_DOT_OK], anchor="center")

        # 五列：左侧小圆环 + 右侧名称 / 数值
        # 图片模式下底色是照片：文字转白、分隔线用半透明白，才压得住画面
        txt_col = "#FFFFFF" if self._photo_on else TEXT
        div_col = "#FFFFFF" if self._photo_on else DIVIDER
        div_stipple = "gray50" if self._photo_on else ""
        self._cols = {}
        x = self.S(PAD_L)
        for idx, (key, label, cw) in enumerate(COLUMNS):
            cw_px = self.S(cw)
            if idx:
                gx = x - self.S(COL_GAP) // 2
                c.create_line(gx, self.S(11), gx, h - self.S(11), fill=div_col,
                              width=self.S(1), stipple=div_stipple)
            ring = sc["rings"][key]
            c.create_image(x + self.S(9), h // 2, image=ring.photo, anchor="center")
            tx = x + self.S(23)
            lab = c.create_text(tx, self.S(13), text=label, anchor="w",
                                font=self.f_label, fill=ACC[key])
            val = c.create_text(tx, self.S(28), text="--", anchor="w",
                                font=self.f_val, fill=txt_col)
            self._cols[key] = {"lab": lab, "val": val, "ring": ring}
            x += cw_px + self.S(COL_GAP)

        # 右侧齿轮：单击直接打开设置面板（位置固定，只响应单击）
        gear_cx = w - self.S(PAD_R) - self.S(GEAR_W) // 2
        gx = gear_cx - self.S(GEAR_W) // 2 - self.S(COL_GAP) // 2
        c.create_line(gx, self.S(11), gx, h - self.S(11), fill=div_col,
                      width=self.S(1), stipple=div_stipple)
        self._gear = c.create_image(gear_cx, h // 2, image=self._gear_imgs[False],
                                    anchor="center")
        c.tag_bind(self._gear, "<Enter>", self._gear_hover_on)
        c.tag_bind(self._gear, "<Leave>", self._gear_hover_off)
        c.tag_bind(self._gear, "<Button-1>", self._on_gear_click)

    def _scene(self):
        """生成 / 复用整条胶囊的位图组（图标都是带透明通道的，底色交给下层）"""
        cache_key = (self.theme, self._photo_on)
        sc = self._scene_cache.get(cache_key)
        if sc is not None:
            return sc

        old = (self.w, self.h)
        try:
            self.w = self.S(STRIP_W)
            self.h = self.S(STRIP_H)

            av_d = self.S(AVATAR_D)
            avatars = {col: make_avatar_alpha(self.root, av_d,
                                              AVATAR_TINTS.get(col, (1.0, 1.0, 1.0)))
                       for col in (COL_DOT_OK, COL_DOT_WARN, COL_DOT_HOT)}

            gear_d = self.S(GEAR_D)
            gears = {False: make_sticker_alpha(self.root, gear_d),
                     True: make_sticker_alpha(self.root, gear_d, boost=1.12)}

            rd = self.S(16)
            if self._photo_on:      # 照片上：轨道用半透明白，才不会糊成一团
                rings = {key: RingGauge(self.root, rd, self.S(2), "#FFFFFF", ACC[key],
                                        track_a=96)
                         for key, _label, _cw in COLUMNS}
            else:
                rings = {key: RingGauge(self.root, rd, self.S(2), TRACK, ACC[key])
                         for key, _label, _cw in COLUMNS}

            sc = {"avatars": avatars, "gears": gears, "rings": rings}
        finally:
            self.w, self.h = old

        self._scene_cache[cache_key] = sc
        return sc

    def _prewarm_images(self):
        """预热设置面板用到的位图，第一次点齿轮就不卡了"""
        try:
            S, R, P = self.S, self.root, SettingsPanel
            make_round_image(R, S(P.W_LOG), S(P.H_LOG), S(16), P.CARD_BG,
                             P.CARD_STROKE, KEY_COLOR, stroke_w=EDGE_W)
            make_round_image(R, S(22), S(22), S(11), P.ITEM_BG, "", P.CARD_BG)
            make_round_image(R, S(P.W_LOG) - S(36), S(34), S(34) / 2.0,
                             P.ITEM_BG, P.ITEM_STROKE, P.CARD_BG, stroke_w=EDGE_W)
            make_round_image(R, S(P.W_LOG) - S(36), S(34), S(34) / 2.0,
                             P.DANGER_BG, P.DANGER_STROKE, P.CARD_BG, stroke_w=EDGE_W)
            for n in (3, 4):
                seg_w = (S(P.W_LOG) - S(18) * 2 - S(8) * (n - 1)) // n
                make_round_image(R, seg_w, S(30), S(30) / 2.0, P.ACTIVE_BG, "",
                                 P.CARD_BG, stroke_w=EDGE_W)
                make_round_image(R, seg_w, S(30), S(30) / 2.0, P.ITEM_BG,
                                 P.ITEM_STROKE, P.CARD_BG, stroke_w=EDGE_W)
            for on in (True, False):
                make_switch_image(R, S(46), S(26), on, P.CARD_BG,
                                  track_off=SW_TRACK, track_on=P.ACTIVE_BG,
                                  knob_off=SW_KNOB, knob_on="#FFFFFF")
        except Exception:
            pass

    def _gear_hover_on(self, _e=None):
        self.canvas.itemconfigure(self._gear, image=self._gear_imgs[True])
        self.canvas.configure(cursor="hand2")

    def _gear_hover_off(self, _e=None):
        self.canvas.itemconfigure(self._gear, image=self._gear_imgs[False])
        self.canvas.configure(cursor="")

    def _on_gear_click(self, e):
        self._toggle_settings()

    def _toggle_settings(self):
        """齿轮 = 打开 / 收起设置面板"""
        if self._settings is not None:
            self._settings.close()
            return
        self._settings = SettingsPanel(self)

    # ------------------------------------------------------------ 收起 / 展开
    def _collapse(self):
        """收起：长条缩成一枚可以随便拖的小图，右键恢复"""
        if self._collapsed:
            return
        if self._settings is not None:
            self._settings.close()

        img = tk.PhotoImage(master=self.root, data=MINI_B64)
        mw, mh = img.width(), img.height()
        mini = tk.Toplevel(self.root)
        mini.overrideredirect(True)
        mini.configure(bg=MINI_BG)
        try:
            mini.wm_attributes("-transparentcolor", MINI_BG)
        except tk.TclError:
            pass
        mini.wm_attributes("-topmost", True)
        cv = tk.Canvas(mini, width=mw, height=mh, bg=MINI_BG,
                       highlightthickness=0, bd=0)
        cv.pack()
        cv.create_image(0, 0, image=img, anchor="nw")
        self._mini_img = img
        mini.geometry(f"{mw}x{mh}+{self.anchor_cx - mw // 2}+{self.anchor_y}")
        cv.bind("<Button-1>", self._mini_press)
        cv.bind("<B1-Motion>", self._mini_drag)
        cv.bind("<Button-3>", lambda _e: self._expand())
        self._mini = mini
        mini.deiconify()
        mini.lift()
        self._collapsed = True
        self.root.update_idletasks()
        self.root.withdraw()

    def _mini_press(self, e):
        if self._mini is None:
            return
        self._drag_off = (e.x_root - self._mini.winfo_rootx(),
                          e.y_root - self._mini.winfo_rooty())

    def _mini_drag(self, e):
        if self._drag_off is None or self._mini is None:
            return
        self._mini.geometry("+%d+%d" % (e.x_root - self._drag_off[0],
                                        e.y_root - self._drag_off[1]))

    def _expand(self):
        """右键小图标：恢复成原来的长条，并回到屏幕顶部中央原位"""
        if not self._collapsed:
            return
        self._collapsed = False
        if self._mini is not None:
            try:
                self._mini.destroy()
            except Exception:
                pass
            self._mini = None
        self._drag_off = None
        self.anchor_cx = self.root.winfo_screenwidth() // 2
        self.anchor_y = self.S(TOP_OFFSET)
        self.root.deiconify()
        self._apply_geometry()
        try:
            self.root.wm_attributes("-topmost", True)
            self.root.lift()
        except tk.TclError:
            pass
        self._update()

    def _set_ring(self, key, ratio):
        """占用比例画成环形进度（圆圈），而不是横条"""
        col = self._cols.get(key)
        if col:
            col["ring"].render(ratio)

    # ------------------------------------------------------------ 数值刷新
    def _update(self):
        if self._collapsed:
            return
        with self.sampler.lock:
            d = dict(self.sampler.data)
        if not d or not self._cols:
            return
        c = self.canvas
        cpu = d.get("cpu", 0.0)
        mem_total = d.get("mem_total", 0) or 1
        mem_used = d.get("mem_used", 0)
        mem_ratio = mem_used / mem_total
        disk_total = d.get("disk_total", 0) or 1
        disk_free = d.get("disk_free", 0)
        disk_used = 1.0 - disk_free / disk_total
        gpu_util = d.get("gpu_util")
        gpu_temp = d.get("gpu_temp")
        battery = d.get("battery")

        cols = self._cols

        c.itemconfigure(cols["cpu"]["val"], text=f"{cpu * 100:.0f}%")
        self._set_ring("cpu", cpu)

        c.itemconfigure(cols["mem"]["val"], text=f"{mem_ratio * 100:.0f}%")
        self._set_ring("mem", mem_ratio)

        if gpu_util is None:
            c.itemconfigure(cols["gpu"]["val"], text="—")
        else:
            pct = gpu_util * 100.0
            c.itemconfigure(cols["gpu"]["val"],
                            text=(f"{pct:.1f}%" if pct < 9.95 else f"{pct:.0f}%"))
            self._set_ring("gpu", gpu_util)
        if gpu_temp:
            c.itemconfigure(cols["gpu"]["lab"], text=f"GPU {gpu_temp}°")

        c.itemconfigure(cols["disk"]["val"], text=f"{disk_used * 100:.0f}%")
        self._set_ring("disk", disk_used)

        if battery is None:
            c.itemconfigure(cols["bat"]["lab"], text="电池")
            c.itemconfigure(cols["bat"]["val"], text="AC")
            self._set_ring("bat", 0.0)
        else:
            pct, plugged = battery
            c.itemconfigure(cols["bat"]["lab"], text="电池·充" if plugged else "电池")
            c.itemconfigure(cols["bat"]["val"], text=f"{pct}%")
            self._set_ring("bat", pct / 100.0)

        imgs = self._avatar_imgs
        want = imgs[load_color(cpu)]
        if c.itemcget(self._avatar, "image") != str(want):
            c.itemconfigure(self._avatar, image=want)

    # ------------------------------------------------------------ 定时刷新
    def _ui_tick(self):
        try:
            if not self._hidden_for_fullscreen and not self._collapsed:
                self._update()
        finally:
            self.root.after(int(self.refresh_interval * 1000) // 2 or 500, self._ui_tick)

    # ------------------------------------------------------------ 右键菜单
    def _on_menu(self, e):
        self._open_menu(e.x_root, e.y_root)

    def _open_menu(self, x_root, y_root):
        m = tk.Menu(self.root, tearoff=0, bg=MENU_BG, fg=TEXT,
                    activebackground=MENU_ACTIVE, activeforeground=TEXT,
                    bd=0, font=self.f_menu)
        with self.sampler.lock:
            up = self.sampler.data.get("uptime")
        if up:
            m.add_command(label=fmt_uptime(up), state="disabled")
            m.add_separator()

        sub = tk.Menu(m, tearoff=0, bg=MENU_BG, fg=TEXT,
                      activebackground=MENU_ACTIVE, activeforeground=TEXT, bd=0,
                      font=self.f_menu)
        self._rate_var = tk.IntVar(value=int(self.refresh_interval))
        for txt, val in (("1 秒（流畅）", 1), ("2 秒（省电）", 2), ("5 秒（极省电）", 5)):
            sub.add_radiobutton(label=txt, variable=self._rate_var, value=val,
                                command=self._set_rate)
        m.add_cascade(label="刷新频率", menu=sub)

        tsub = tk.Menu(m, tearoff=0, bg=MENU_BG, fg=TEXT,
                       activebackground=MENU_ACTIVE, activeforeground=TEXT, bd=0,
                       font=self.f_menu)
        self._theme_var = tk.StringVar(value=self.theme)
        for key in THEME_ORDER:
            tsub.add_radiobutton(label=THEMES[key]["label"], variable=self._theme_var,
                                 value=key,
                                 command=lambda k=key: self.set_theme(k))
        m.add_cascade(label="主题", menu=tsub)

        self._auto_var = tk.BooleanVar(value=self._autostart_enabled())
        m.add_checkbutton(label="开机自启动", variable=self._auto_var,
                          command=self._toggle_autostart)
        self._fs_var = tk.BooleanVar(value=self._fs_hide)
        m.add_checkbutton(label="全屏时自动隐藏", variable=self._fs_var,
                          command=self._set_fs_hide)

        self._photo_var = tk.BooleanVar(value=self._photo_on)
        m.add_separator()
        m.add_checkbutton(label="图片轮换", variable=self._photo_var,
                          command=lambda: self.set_photo_mode(self._photo_var.get()))
        m.add_command(label="下一张图片", state=("normal" if self._photos else "disabled"),
                      command=lambda: self.advance_photo())

        m.add_separator()
        m.add_command(label="收起为图标", command=self._collapse)
        m.add_command(label="退出", command=self._quit)
        try:
            m.tk_popup(x_root, y_root)
        finally:
            m.grab_release()

    def set_rate_value(self, val):
        self.sampler.interval = float(val)
        self.refresh_interval = float(val)

    def set_theme(self, name):
        """切主题：换配色 -> 存配置 -> 长条和面板一起重画"""
        if name not in THEMES:
            return
        apply_theme(name)
        self.theme = name
        _cfg_patch({"theme": name})
        self._scene_cache.clear()
        self.canvas.delete("all")
        self._cols = {}
        self._build()
        self._update()
        if self._settings is not None:
            try:
                self._settings.close()
            except Exception:
                pass
            self._settings = SettingsPanel(self)

    def _set_rate(self):
        self.set_rate_value(self._rate_var.get())

    def _quit(self):
        if self._settings is not None:
            try:
                self._settings.top.destroy()
            except Exception:
                pass
            self._settings = None
        try:
            self.sampler.stop()
        finally:
            self.root.destroy()

    # ------------------------------------------------------------ 开机自启
    @staticmethod
    def _startup_dir():
        return os.path.join(os.environ.get("APPDATA", ""),
                            r"Microsoft\Windows\Start Menu\Programs\Startup")

    def _autostart_path(self):
        return os.path.join(self._startup_dir(), "动态岛硬件状态.vbs")

    def _autostart_enabled(self):
        try:
            return os.path.exists(self._autostart_path())
        except Exception:
            return False

    def _toggle_autostart(self):
        path = self._autostart_path()
        try:
            if self._autostart_enabled():
                os.remove(path)
            else:
                pyw = sys.executable.replace("python.exe", "pythonw.exe")
                if not os.path.exists(pyw):
                    pyw = sys.executable
                content = (
                    'Set sh = CreateObject("WScript.Shell")\r\n'
                    f'sh.Run Chr(34) & "{pyw}" & Chr(34) & " " & Chr(34) & '
                    f'"{SCRIPT_PATH}" & Chr(34), 0, False\r\n'
                )
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
        except Exception:
            pass

    # ------------------------------------------------------------ 全屏自动隐藏
    def _set_fs_hide(self):
        self._fs_hide = bool(self._fs_var.get())
        if not self._fs_hide and self._hidden_for_fullscreen:
            self._show_island()

    def _fullscreen_tick(self):
        try:
            if self._fs_hide:
                if self._is_fullscreen_foreground():
                    if not self._hidden_for_fullscreen:
                        self._hidden_for_fullscreen = True
                        self.root.withdraw()
                elif self._hidden_for_fullscreen:
                    self._show_island()
        finally:
            self.root.after(1500, self._fullscreen_tick)

    def _show_island(self):
        self._hidden_for_fullscreen = False
        try:
            self.root.deiconify()
            self.root.wm_attributes("-topmost", True)
            self._apply_geometry()
        except Exception:
            pass

    def _is_fullscreen_foreground(self):
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return False
        own = self.root.winfo_id()
        if hwnd == own or hwnd == user32.GetParent(own):
            return False
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, buf, 256)
        if buf.value in ("Progman", "WorkerW", "Shell_TrayWnd", "MultitaskingViewFrame"):
            return False
        rect = wt.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return False
        sw = user32.GetSystemMetrics(0)
        sh = user32.GetSystemMetrics(1)
        return rect.left <= 1 and rect.top <= 1 and rect.right >= sw - 1 and rect.bottom >= sh - 1

    # ------------------------------------------------------------ 启动
    def run(self):
        self.root.mainloop()


def main():
    try:
        IslandApp().run()
    except Exception as exc:                     # GUI 程序没有控制台，弹窗告知
        try:
            ctypes.windll.user32.MessageBoxW(0, f"启动失败：\n{exc}", APP_NAME, 0x10)
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
