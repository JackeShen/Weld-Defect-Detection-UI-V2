"""Dashboard 首页 — v3 新增"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QGridLayout, QSizePolicy,
)
from PyQt5.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QFont


class _ModeCard(QFrame):
    """模式入口卡片"""
    clicked = pyqtSignal()

    def __init__(self, icon, title, desc, parent=None):
        super().__init__(parent)
        self.setObjectName("modeCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumSize(240, 200)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(8)

        icon_label = QLabel(icon)
        icon_label.setObjectName("modeCardIcon")
        icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_label)

        title_label = QLabel(title)
        title_label.setObjectName("modeCardTitle")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        desc_label = QLabel(desc)
        desc_label.setObjectName("modeCardDesc")
        desc_label.setAlignment(Qt.AlignCenter)
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)


class _DashCard(QFrame):
    """数据指标卡片"""

    def __init__(self, title, value="—", sub="", accent=False, parent=None):
        super().__init__(parent)
        self.setObjectName("dashCard")
        self.setMinimumSize(160, 110)

        layout = QVBoxLayout(self)
        layout.setSpacing(4)

        title_lbl = QLabel(title)
        title_lbl.setObjectName("dashCardTitle")
        layout.addWidget(title_lbl)

        self.value_lbl = QLabel(str(value))
        self.value_lbl.setObjectName("dashCardValueAccent" if accent else "dashCardValue")
        layout.addWidget(self.value_lbl)

        self.sub_lbl = QLabel(sub)
        self.sub_lbl.setObjectName("dashCardSub")
        layout.addWidget(self.sub_lbl)

    def set_value(self, value, sub=""):
        self.value_lbl.setText(str(value))
        if sub:
            self.sub_lbl.setText(sub)


class DashboardPage(QWidget):
    """首页 Dashboard

    功能：系统信息总览 + 三个检测模式入口 + 实时数据卡片
    """

    # 信号：请求切换到某页面
    navigate_to = pyqtSignal(int)  # 0=camera, 1=image, 2=video

    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(20)

        # ═══════════════════════════════════════════════
        #  欢迎区
        # ═══════════════════════════════════════════════
        welcome = QLabel("工业焊缝智能检测平台")
        welcome.setAlignment(Qt.AlignCenter)
        welcome.setStyleSheet(
            "color: #e6edf3; font-size: 26px; font-weight: bold; "
            "letter-spacing: 3px; padding: 20px 0 0 0; background: transparent;"
        )
        layout.addWidget(welcome)

        welcome_sub = QLabel(
            "选择检测模式，加载 AI 模型，自动识别焊缝缺陷并测量焊缝宽度"
        )
        welcome_sub.setAlignment(Qt.AlignCenter)
        welcome_sub.setStyleSheet(
            "color: #6e7681; font-size: 13px; padding: 0 0 10px 0; background: transparent;"
        )
        layout.addWidget(welcome_sub)

        # ── 分隔装饰 ──
        sep = QFrame()
        sep.setFixedHeight(2)
        sep.setMaximumWidth(400)
        sep.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            "stop:0 rgba(0,0,0,0), stop:0.2 #00d4ff, stop:0.5 #58a6ff, "
            "stop:0.8 #00d4ff, stop:1 rgba(0,0,0,0)); border: none;"
        )
        sep_layout = QHBoxLayout()
        sep_layout.addStretch()
        sep_layout.addWidget(sep)
        sep_layout.addStretch()
        layout.addLayout(sep_layout)

        layout.addSpacing(10)

        # ═══════════════════════════════════════════════
        #  模式入口卡片
        # ═══════════════════════════════════════════════
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(24)
        cards_layout.addStretch()

        camera_card = _ModeCard(
            "📷", "摄像头实时检测",
            "连接工业相机或USB摄像头\n实时画面检测，支持录像保存"
        )
        camera_card.clicked.connect(lambda: self.navigate_to.emit(0))
        cards_layout.addWidget(camera_card)

        image_card = _ModeCard(
            "🖼", "图像检测",
            "单张图片检测\nYOLO 目标检测 & 分割\n焊缝宽度自动测量"
        )
        image_card.clicked.connect(lambda: self.navigate_to.emit(1))
        cards_layout.addWidget(image_card)

        video_card = _ModeCard(
            "🎬", "视频检测",
            "视频文件逐帧检测\n播放控制 & 跳转\n导出标注视频"
        )
        video_card.clicked.connect(lambda: self.navigate_to.emit(2))
        cards_layout.addWidget(video_card)

        cards_layout.addStretch()
        layout.addLayout(cards_layout)

        layout.addSpacing(10)

        # ═══════════════════════════════════════════════
        #  实时数据卡片行
        # ═══════════════════════════════════════════════
        grid = QGridLayout()
        grid.setSpacing(16)

        self.card_model = _DashCard("🧠 模型状态", "未加载", "请先加载 AI 模型")
        grid.addWidget(self.card_model, 0, 0)

        self.card_task = _DashCard("🎯 检测任务", "—", "")
        grid.addWidget(self.card_task, 0, 1)

        self.card_classes = _DashCard("🏷 缺陷类别", "—", "")
        grid.addWidget(self.card_classes, 0, 2)

        self.card_width = _DashCard("📏 焊缝测量", "—", "", accent=True)
        grid.addWidget(self.card_width, 0, 3)

        layout.addLayout(grid)

        layout.addStretch()

        # ── 底部提示 ──
        hint = QLabel("💡 提示：先在任意页面加载模型，再选择检测模式")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("color: #484f58; font-size: 12px; padding: 12px; background: transparent;")
        layout.addWidget(hint)

    def update_model_info(self, model_info, task_type, class_count):
        """模型加载后更新卡片数据"""
        model_name = model_info.get("文件名", "—")
        self.card_model.set_value("已加载", model_name)
        self.card_task.set_value(
            "分割" if task_type == "segment" else "检测",
            "支持焊缝宽度测量" if task_type == "segment" else "目标检测模式"
        )
        self.card_classes.set_value(f"{class_count} 类", model_info.get("类别名称", "")[:40])

    def update_width_result(self, count, mean_mm=None):
        """更新焊缝宽度卡片"""
        if count > 0:
            val = f"{count} 条"
            sub = f"平均 {mean_mm:.2f}mm" if mean_mm else ""
            self.card_width.set_value(val, sub)
        else:
            self.card_width.set_value("—", "")
