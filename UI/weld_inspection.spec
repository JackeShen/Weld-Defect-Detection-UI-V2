# -*- mode: python ; coding: utf-8 -*-
r"""
PyInstaller 打包配置文件 - 西安汇丰-京博工业焊缝检测系统 v5

Usage:
    conda activate oldshen
    cd C:/Users/11137/Desktop
    pyinstaller UI/weld_inspection.spec

Output: dist/西安汇丰-京博工业焊缝检测系统 v5/
"""

import sys
from pathlib import Path

# ── 路径常量 ──
UI_DIR = Path(SPECPATH)  # spec 文件所在目录 = UI/
DESKTOP_DIR = UI_DIR.parent  # Desktop 目录

# ── 隐式导入：PyInstaller 静态分析无法发现的模块 ──
hiddenimports = [
    # ultralytics 内部子模块（大量动态导入）
    'ultralytics.nn.modules',
    'ultralytics.nn.modules.block',
    'ultralytics.nn.modules.conv',
    'ultralytics.nn.modules.head',
    'ultralytics.nn.tasks',
    'ultralytics.utils',
    'ultralytics.utils.callbacks',
    'ultralytics.utils.metrics',
    'ultralytics.utils.torch_utils',
    'ultralytics.utils.ops',
    'ultralytics.utils.plotting',
    'ultralytics.data',
    'ultralytics.data.dataset',
    'ultralytics.data.augment',
    'ultralytics.engine',
    'ultralytics.engine.model',
    'ultralytics.engine.results',
    'ultralytics.engine.predictor',
    'ultralytics.engine.validator',
    'ultralytics.engine.trainer',
    'ultralytics.engine.exporter',

    # PyTorch
    'torch',
    'torch.nn',
    'torch.utils',
    'torchvision',

    # PyQt5 平台插件
    'PyQt5.QtCore',
    'PyQt5.QtGui',
    'PyQt5.QtWidgets',
    'PyQt5.sip',

    # 其他
    'PIL',
    'PIL.Image',
    'PIL.ImageDraw',
    'PIL.ImageFont',
    'numpy',
    'yaml',
]

# ── 数据文件：需要打包进 exe 的非 Python 资源 ──
datas = [
    (str(UI_DIR / 'resources' / 'style.qss'), 'resources'),
]

# ── 排除的模块（减小体积）──
excluded_modules = [
    'matplotlib',
    'scipy',
    'pandas',
    'jupyter',
    'IPython',
    'notebook',
    'tensorflow',
    'tensorboard',
    'wandb',
    'tqdm',
]

a = Analysis(
    [str(DESKTOP_DIR / 'run.py')],
    pathex=[str(DESKTOP_DIR)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excluded_modules,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='西安汇丰-京博工业焊缝检测系统 v5',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,              # 不显示控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(UI_DIR / 'resources' / 'app.ico') if (UI_DIR / 'resources' / 'app.ico').exists() else None,
)
