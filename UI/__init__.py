# weld_ui_v5 - 西安汇丰-京博工业焊缝检测系统 UI 包
# 启动: python -m weld_ui_v5.main_window
#
# 注意: 不做 eager import main_window，否则 -m weld_ui_v5.main_window
#       会触发 "found in sys.modules" RuntimeWarning。
__all__ = ["WeldInspectionMainWindow"]


def _get_main_window():
    from .main_window import WeldInspectionMainWindow
    return WeldInspectionMainWindow
