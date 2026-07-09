"""自适应缩放图像查看器组件 v3 — 带科技风角标"""

from PyQt5.QtWidgets import QScrollArea, QLabel
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QPixmap, QPainter, QPen, QColor

from ..utils.image_conversion import cv_to_qpixmap, scale_pixmap


class ImageViewer(QScrollArea):
    """可自适应缩放的图像查看器 v3

    支持 set_cv_image() 和 set_pixmap()。
    画面区域四角绘制 L 形科技风角标。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("imageViewer")
        self.setWidgetResizable(True)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(400, 300)

        self._label = QLabel()
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setMinimumSize(380, 280)
        self._label.setStyleSheet("""
            QLabel {
                background-color: #040810;
                border: 1px solid #1a2838;
                border-radius: 8px;
                color: #3d5266;
                font-size: 14px;
            }
        """)
        self._label.setText("请加载模型并选择输入源")
        self.setWidget(self._label)

        self._current_pixmap = None
        self._current_cv_image = None
        self._display_mode = "pixmap"

    def set_cv_image(self, cv_img):
        if cv_img is None:
            return
        self._current_cv_image = cv_img
        self._current_pixmap = cv_to_qpixmap(cv_img)
        self._display_mode = "cv"
        self._fit_to_view()

    def set_pixmap(self, pixmap):
        if pixmap is None or pixmap.isNull():
            return
        self._current_pixmap = pixmap
        self._current_cv_image = None
        self._display_mode = "pixmap"
        self._fit_to_view()

    def clear(self):
        self._current_pixmap = None
        self._current_cv_image = None
        self._label.clear()
        self._label.setText("请加载模型并选择输入源")

    def has_image(self):
        return self._current_pixmap is not None

    def _fit_to_view(self):
        if self._current_pixmap is None:
            return
        margin = 20
        target_size = self._label.size() - QSize(margin, margin)
        if target_size.width() <= 0 or target_size.height() <= 0:
            return
        scaled = scale_pixmap(self._current_pixmap, target_size, keep_aspect=True)
        self._label.setPixmap(scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._current_pixmap is not None:
            self._fit_to_view()

    def paintEvent(self, event):
        """绘制四角 L 形科技风角标"""
        super().paintEvent(event)

        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.viewport().width()
        h = self.viewport().height()
        arm = 20   # L 臂长度
        gap = 6    # 离边缘间距
        thickness = 2

        # 青蓝色半透明
        pen = QPen(QColor(0, 212, 255, 120), thickness)
        painter.setPen(pen)

        # 左上角
        painter.drawLine(gap, gap + arm, gap, gap)
        painter.drawLine(gap, gap, gap + arm, gap)

        # 右上角
        painter.drawLine(w - gap - arm, gap, w - gap, gap)
        painter.drawLine(w - gap, gap, w - gap, gap + arm)

        # 左下角
        painter.drawLine(gap, h - gap - arm, gap, h - gap)
        painter.drawLine(gap, h - gap, gap + arm, h - gap)

        # 右下角
        painter.drawLine(w - gap - arm, h - gap, w - gap, h - gap)
        painter.drawLine(w - gap, h - gap - arm, w - gap, h - gap)

        painter.end()
