"""深色侧边栏导航组件 v3 — 首页 + 三种检测模式"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLabel, QFrame,
    QButtonGroup,
)
from PyQt5.QtCore import Qt, pyqtSignal

from .widgets.status_indicator import StatusIndicator


class SidebarWidget(QWidget):
    """深色侧边栏导航 v3

    包含：首页 + 三种检测模式 + 模型状态指示

    Signals:
        page_changed: 页面切换 (stack_index: 0=dash, 1=cam, 2=img, 3=vid)
    """

    page_changed = pyqtSignal(int)

    PAGE_DASH = 0
    PAGE_CAMERA = 1
    PAGE_IMAGE = 2
    PAGE_VIDEO = 3
    PAGE_LOG = 4
    PAGE_ANALYSIS = 5

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(220)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addSpacing(16)

        # ── 导航标签 ──
        nav_label = QLabel("导航菜单")
        nav_label.setObjectName("sectionLabel")
        layout.addWidget(nav_label)
        layout.addSpacing(8)

        # ── 导航按钮组 ──
        self._btn_group = QButtonGroup(self)
        self._btn_group.setExclusive(True)

        nav_buttons = [
            ("🏠  系统首页", self.PAGE_DASH),
            ("📷  摄像头检测", self.PAGE_CAMERA),
            ("🖼  图像检测", self.PAGE_IMAGE),
            ("🎬  视频检测", self.PAGE_VIDEO),
            ("📋  检测记录", self.PAGE_LOG),
            ("📊  分析报告", self.PAGE_ANALYSIS),
        ]

        for text, index in nav_buttons:
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            self._btn_group.addButton(btn, index)
            layout.addWidget(btn)

        self._btn_group.button(self.PAGE_DASH).setChecked(True)
        self._btn_group.buttonClicked.connect(
            lambda btn: self.page_changed.emit(self._btn_group.id(btn))
        )

        # ── 分隔线 ──
        layout.addSpacing(16)
        sep = QFrame()
        sep.setObjectName("separatorLine")
        sep.setFrameShape(QFrame.HLine)
        layout.addWidget(sep)
        layout.addSpacing(12)

        # ── 模型状态 ──
        status_label = QLabel("模型状态")
        status_label.setObjectName("sectionLabel")
        layout.addWidget(status_label)

        self._status_indicator = StatusIndicator("未加载")
        self._status_indicator.setContentsMargins(20, 4, 20, 4)
        layout.addWidget(self._status_indicator)

        self._model_name_label = QLabel("—")
        self._model_name_label.setObjectName("modelNameLabel")
        layout.addWidget(self._model_name_label)

        layout.addSpacing(16)
        layout.addStretch()

        version = QLabel("v4.0 工厂版")
        version.setObjectName("versionLabel")
        version.setAlignment(Qt.AlignCenter)
        layout.addWidget(version)
        layout.addSpacing(12)

    def set_model_loaded(self, model_name, task_type):
        self._status_indicator.set_ready(f"已加载 ({task_type})")
        self._model_name_label.setText(model_name)

    def set_model_unloaded(self):
        self._status_indicator.set_idle("未加载")
        self._model_name_label.setText("—")

    def set_model_error(self):
        self._status_indicator.set_error("加载失败")
        self._model_name_label.setText("—")

    def set_processing(self, text="处理中..."):
        self._status_indicator.set_processing(text)

    def set_ready(self, text="就绪"):
        self._status_indicator.set_ready(text)

    def current_page(self):
        checked = self._btn_group.checkedButton()
        if checked:
            return self._btn_group.id(checked)
        return self.PAGE_DASH
