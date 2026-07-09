"""状态指示灯组件"""

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel
from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt5.QtGui import QColor, QPainter, QBrush, QPen


class _DotWidget(QWidget):
    """可动画的圆点"""

    def __init__(self, color="#9E9E9E", size=12, parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self._size = size
        self._opacity = 1.0
        self.setFixedSize(size + 4, size + 4)

        # 脉冲动画
        self._anim = QPropertyAnimation(self, b"opacity")
        self._anim.setDuration(1200)
        self._anim.setStartValue(1.0)
        self._anim.setKeyValueAt(0.5, 0.3)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.InOutSine)

    def get_opacity(self):
        return self._opacity

    def set_opacity(self, value):
        self._opacity = value
        self.update()

    opacity = pyqtProperty(float, get_opacity, set_opacity)

    def set_color(self, color):
        self._color = QColor(color)
        self.update()

    def start_pulse(self):
        self._anim.setLoopCount(-1)
        self._anim.start()

    def stop_pulse(self):
        self._anim.stop()
        self._opacity = 1.0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        color = QColor(self._color)
        color.setAlphaF(self._opacity)

        painter.setBrush(QBrush(color))
        painter.setPen(Qt.NoPen)

        r = self._size // 2
        cx = self.width() // 2
        cy = self.height() // 2
        painter.drawEllipse(cx - r, cy - r, self._size, self._size)
        painter.end()


class StatusIndicator(QWidget):
    """带文本标签的状态指示灯

    颜色约定：
        - 灰色 (#9E9E9E): 空闲 / 无模型
        - 绿色 (#4CAF50): 就绪 / 正常
        - 黄色 (#FF9800): 处理中
        - 红色 (#F44336): 错误
    """

    COLOR_IDLE = "#484f58"
    COLOR_READY = "#3fb950"
    COLOR_PROCESSING = "#d2991d"
    COLOR_ERROR = "#f85149"

    def __init__(self, text="", color=None, parent=None):
        super().__init__(parent)
        if color is None:
            color = self.COLOR_IDLE

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._dot = _DotWidget(color)
        layout.addWidget(self._dot)

        self._label = QLabel(text)
        self._label.setStyleSheet("color: #8b949e; font-size: 11px; background: transparent;")
        layout.addWidget(self._label)
        layout.addStretch()

    def set_text(self, text):
        self._label.setText(text)

    def set_color(self, color):
        self._dot.set_color(color)

    def set_idle(self, text=""):
        self._dot.stop_pulse()
        self._dot.set_color(self.COLOR_IDLE)
        if text:
            self._label.setText(text)

    def set_ready(self, text=""):
        self._dot.stop_pulse()
        self._dot.set_color(self.COLOR_READY)
        if text:
            self._label.setText(text)

    def set_processing(self, text=""):
        self._dot.set_color(self.COLOR_PROCESSING)
        self._dot.start_pulse()
        if text:
            self._label.setText(text)

    def set_error(self, text=""):
        self._dot.stop_pulse()
        self._dot.set_color(self.COLOR_ERROR)
        if text:
            self._label.setText(text)
