"""资源路径工具 — 兼容开发环境和 PyInstaller 打包环境

PyInstaller 打包后 sys._MEIPASS 指向临时解压目录，
__file__ 不再指向真实文件系统路径，因此所有资源文件
和输出目录的定位都应通过本模块提供的函数来进行。
"""

import sys
from pathlib import Path


def get_base_path() -> Path:
    """获取应用根目录（UI 包所在目录）

    开发环境：返回 UI/ 目录（本文件的 grandparent）
    PyInstaller 打包：返回 sys._MEIPASS 临时目录
    """
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包环境：所有资源文件在 sys._MEIPASS 下
        return Path(sys._MEIPASS)
    # 开发环境：utils/paths.py → utils/ → UI/
    return Path(__file__).resolve().parent.parent


def get_resource_path(relative_path: str | Path) -> Path:
    """获取打包资源的完整路径

    开发环境：相对于 UI/ 目录解析
    打包环境：相对于 sys._MEIPASS 解析

    Args:
        relative_path: 相对于 UI 包根目录的路径，如 "resources/style.qss"

    Returns:
        Path: 资源的绝对路径（打包环境下指向临时目录）
    """
    return get_base_path() / relative_path


def get_data_dir(dirname: str = "weld_results") -> Path:
    """获取数据输出目录（可写目录）

    开发环境：UI/ 下的子目录
    打包环境：exe 所在目录下的子目录（因为 sys._MEIPASS 只读）

    Args:
        dirname: 目录名，默认 "weld_results"

    Returns:
        Path: 数据目录的绝对路径
    """
    if getattr(sys, 'frozen', False):
        # 打包后 exe 所在目录是可写的
        return Path(sys.executable).parent / dirname
    # 开发环境
    return Path(__file__).resolve().parent.parent / dirname


def ensure_dir(path: Path) -> Path:
    """确保目录存在，不存在则创建

    Args:
        path: 目标路径

    Returns:
        Path: 创建后的目录路径
    """
    path.mkdir(parents=True, exist_ok=True)
    return path
