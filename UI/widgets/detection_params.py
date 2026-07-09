"""检测参数面板 — 所有检测模式共享"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QSlider, QDoubleSpinBox, QComboBox, QGroupBox,
)
from PyQt5.QtCore import Qt, pyqtSignal


class DetectionParams(QGroupBox):
    """检测参数设置面板

    包含：置信度阈值（滑块+数值联动）、IoU 阈值、图片尺寸、类别过滤

    Signals:
        params_changed: 任意参数变化时发射
    """

    params_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("检测参数", parent)
        self._class_names = ["全部"]
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        grid = QGridLayout()
        grid.setSpacing(8)

        # ── 置信度阈值 ──
        grid.addWidget(QLabel("置信度阈值:"), 0, 0)
        self.conf_spin = QDoubleSpinBox()
        self.conf_spin.setRange(0.01, 1.0)
        self.conf_spin.setSingleStep(0.05)
        self.conf_spin.setValue(0.25)
        self.conf_spin.valueChanged.connect(self._on_conf_spin_changed)
        grid.addWidget(self.conf_spin, 0, 1)

        self.conf_slider = QSlider(Qt.Horizontal)
        self.conf_slider.setRange(1, 100)
        self.conf_slider.setValue(25)
        self.conf_slider.valueChanged.connect(self._on_conf_slider_changed)
        grid.addWidget(self.conf_slider, 0, 2)

        # ── IoU 阈值 ──
        grid.addWidget(QLabel("IoU 阈值:"), 1, 0)
        self.iou_spin = QDoubleSpinBox()
        self.iou_spin.setRange(0.1, 1.0)
        self.iou_spin.setSingleStep(0.05)
        self.iou_spin.setValue(0.45)
        self.iou_spin.valueChanged.connect(lambda: self.params_changed.emit())
        grid.addWidget(self.iou_spin, 1, 1)

        # ── 图片尺寸 ──
        grid.addWidget(QLabel("图片尺寸:"), 2, 0)
        self.imgsz_combo = QComboBox()
        self.imgsz_combo.addItems(["320", "640", "800", "1024", "1280"])
        self.imgsz_combo.setCurrentText("640")
        self.imgsz_combo.currentTextChanged.connect(lambda: self.params_changed.emit())
        grid.addWidget(self.imgsz_combo, 2, 1)

        # ── 类别过滤 ──
        grid.addWidget(QLabel("目标类别:"), 3, 0)
        self.class_filter_combo = QComboBox()
        self.class_filter_combo.addItem("全部")
        self.class_filter_combo.currentTextChanged.connect(lambda: self.params_changed.emit())
        grid.addWidget(self.class_filter_combo, 3, 1, 1, 2)

        layout.addLayout(grid)

    def _on_conf_spin_changed(self, value):
        """数值框变化 → 同步滑块"""
        self.conf_slider.blockSignals(True)
        self.conf_slider.setValue(int(value * 100))
        self.conf_slider.blockSignals(False)
        self.params_changed.emit()

    def _on_conf_slider_changed(self, value):
        """滑块变化 → 同步数值框"""
        self.conf_spin.blockSignals(True)
        self.conf_spin.setValue(value / 100.0)
        self.conf_spin.blockSignals(False)
        self.params_changed.emit()

    def set_class_names(self, names):
        """设置类别过滤下拉框的选项列表

        Args:
            names: list[str] 类别名称列表
        """
        self._class_names = ["全部"] + list(names)
        current = self.class_filter_combo.currentText()
        self.class_filter_combo.blockSignals(True)
        self.class_filter_combo.clear()
        self.class_filter_combo.addItems(self._class_names)
        if current in self._class_names:
            self.class_filter_combo.setCurrentText(current)
        self.class_filter_combo.blockSignals(False)

    def get_params(self):
        """获取当前所有检测参数

        Returns:
            dict: conf, iou, imgsz, class_filter
        """
        return {
            "conf": self.conf_spin.value(),
            "iou": self.iou_spin.value(),
            "imgsz": int(self.imgsz_combo.currentText()),
            "class_filter": self.class_filter_combo.currentText(),
        }

    def get_filter_class_id(self, names_dict):
        """获取当前选中的类别 ID（如果选了"全部"返回 None）

        Args:
            names_dict: model.names 字典

        Returns:
            int | None
        """
        filter_class = self.class_filter_combo.currentText()
        if filter_class == "全部":
            return None
        for cls_id, name in names_dict.items():
            if name == filter_class:
                return int(cls_id)
        return None
