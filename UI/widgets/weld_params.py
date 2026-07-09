"""焊缝宽度测量参数面板"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QDoubleSpinBox, QComboBox, QCheckBox, QGroupBox,
)
from PyQt5.QtCore import pyqtSignal


class WeldParams(QGroupBox):
    """焊缝宽度测量参数面板

    仅在模型任务类型为 "segment" 时显示。

    Signals:
        params_changed: 任意参数变化时发射
    """

    params_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("焊缝宽度测量", parent)
        self._init_ui()
        self.setVisible(False)  # 默认隐藏，加载分割模型后显示

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # ── 启用开关 ──
        top_row = QHBoxLayout()
        self.enable_check = QCheckBox("启用焊缝宽度测量")
        self.enable_check.setChecked(False)
        self.enable_check.stateChanged.connect(lambda: self.params_changed.emit())
        top_row.addWidget(self.enable_check)

        self.method_combo = QComboBox()
        self.method_combo.addItems(["PCA切片法", "距离变换法"])
        self.method_combo.currentTextChanged.connect(lambda: self.params_changed.emit())
        top_row.addWidget(QLabel("测量方法:"))
        top_row.addWidget(self.method_combo)
        top_row.addStretch()
        layout.addLayout(top_row)

        # ── 相机参数 ──
        grid = QGridLayout()
        grid.setSpacing(8)

        grid.addWidget(QLabel("fx (像素):"), 0, 0)
        self.fx_spin = QDoubleSpinBox()
        self.fx_spin.setRange(0, 50000)
        self.fx_spin.setDecimals(1)
        self.fx_spin.setValue(2500)
        self.fx_spin.setToolTip("相机内参焦距 fx，通过棋盘格标定获得")
        self.fx_spin.valueChanged.connect(lambda: self.params_changed.emit())
        grid.addWidget(self.fx_spin, 0, 1)

        grid.addWidget(QLabel("fy (像素):"), 0, 2)
        self.fy_spin = QDoubleSpinBox()
        self.fy_spin.setRange(0, 50000)
        self.fy_spin.setDecimals(1)
        self.fy_spin.setValue(2500)
        self.fy_spin.setToolTip("相机内参焦距 fy，通常与 fx 相同")
        self.fy_spin.valueChanged.connect(lambda: self.params_changed.emit())
        grid.addWidget(self.fy_spin, 0, 3)

        grid.addWidget(QLabel("工作距离 (mm):"), 1, 0)
        self.distance_spin = QDoubleSpinBox()
        self.distance_spin.setRange(0, 5000)
        self.distance_spin.setDecimals(1)
        self.distance_spin.setValue(300)
        self.distance_spin.setToolTip("相机镜头到焊缝表面的距离")
        self.distance_spin.valueChanged.connect(lambda: self.params_changed.emit())
        grid.addWidget(self.distance_spin, 1, 1)

        layout.addLayout(grid)

    def is_enabled(self):
        return self.enable_check.isChecked()

    def get_method(self):
        """获取测量方法字符串

        Returns:
            "pca" 或 "dt"
        """
        text = self.method_combo.currentText()
        return "pca" if "PCA" in text else "dt"

    def get_params(self):
        """获取当前所有相机参数

        Returns:
            dict: fx, fy, distance, method, enabled
        """
        return {
            "fx": self.fx_spin.value(),
            "fy": self.fy_spin.value(),
            "distance": self.distance_spin.value(),
            "method": self.get_method(),
            "enabled": self.is_enabled(),
        }
