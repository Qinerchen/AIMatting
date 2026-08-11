# -*- mode: python ; coding: utf-8 -*-
import site
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs

datas = []
binaries = []
hiddenimports = []
tmp_ret = collect_all('onnxruntime')
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]

# 收集 qfluentwidgets（Fluent 界面框架）的 QSS / 图标 / 数据资源，
# 以及它的无边框窗口依赖 qframelesswindow。
for _pkg in ('qfluentwidgets', 'qframelesswindow'):
    _ret = collect_all(_pkg)
    datas += _ret[0]
    binaries += _ret[1]
    hiddenimports += _ret[2]

# 运行时图标与 GPL-3.0 许可证文本
datas.append(('assets', 'assets'))
datas.append(('licenses/GPL-3.0.txt', 'licenses'))

# 收集 pip 安装的 nvidia CUDA/cuDNN 运行库（nvidia/cudnn、nvidia/cu13 等），
# 保证打包版能使用 GPU。collect_dynamic_libs 的 dest 是目录形式，
# 会保持 nvidia/<包名>/bin/... 布局，供 _ensure_nvidia_dll_paths() 定位。
_nvidia_seen: set[str] = set()
_nv_pkgs: list[str] = []
for _nv_base in site.getsitepackages():
    _nv_root = Path(_nv_base) / 'nvidia'
    if _nv_root.is_dir():
        _nv_pkgs = sorted(
            d.name
            for d in _nv_root.glob('*')
            if d.is_dir() and d.name.isidentifier()
        )
        break
for _nv_pkg in _nv_pkgs:
    try:
        for _entry in collect_dynamic_libs(f'nvidia.{_nv_pkg}'):
            if _entry[0] not in _nvidia_seen:
                _nvidia_seen.add(_entry[0])
                binaries.append(_entry)
    except Exception:  # noqa: BLE001
        pass


a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)


# 保险：依赖分析可能把 nvidia DLL 的目标路径写成重复文件名
# （如 ...\cublas64_13.dll\cublas64_13.dll），这里修正为单层文件名。
_separator = '\\'


def _fix_nvidia_dest(entry):
    dest, src = entry[0], entry[1]
    base = Path(src).name
    suffix = _separator + base + _separator + base
    if dest.endswith(suffix):
        return (dest[: -len(base) - 1], *entry[1:])
    return entry


# 过滤掉系统 CUDA 工具包（C:\Program Files\NVIDIA GPU Computing Toolkit）的
# DLL：打包版统一使用 pip 安装的 nvidia 运行库，避免旧版本运行时 DLL
# 在 _internal 根目录遮蔽 nvidia 目录里的版本。
_toolkit_prefix = str(
    Path(r"C:\Program Files\NVIDIA GPU Computing Toolkit")
).lower()
a.binaries = [
    _fix_nvidia_dest(entry)
    for entry in a.binaries
    if not str(entry[1]).lower().startswith(_toolkit_prefix)
]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AIMatting',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/aimatting_icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AIMatting',
)
