"""模型加载面板 — 所有检测模式共享"""

from pathlib import Path

from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel,
    QFileDialog, QMessageBox, QGroupBox,
)
from PyQt5.QtCore import Qt, pyqtSignal

from ultralytics import YOLO


def get_model_info(model, model_path):
    """提取模型的详细信息（独立函数，可从任意线程调用）

    Returns:
        dict: 包含 文件名/任务类型/模型名称/类别数/类别名称/默认图片尺寸
    """
    info = {}
    info["文件名"] = Path(model_path).name

    task = getattr(model, 'task', None)
    if task is None and hasattr(model, 'predictor'):
        task = getattr(model.predictor, 'args', {}).get('task', None)
    info["任务类型"] = task or "未知"

    model_name = getattr(model, 'model_name', None)
    if model_name is None and hasattr(model, 'ckpt'):
        model_name = model.ckpt.get('model_name', None)
    info["模型名称"] = model_name or "自动检测"

    names = getattr(model, 'names', None)
    if names is None and hasattr(model, 'model') and hasattr(model.model, 'names'):
        names = model.model.names

    if names and isinstance(names, (dict, list)):
        if isinstance(names, dict):
            info["类别数"] = str(len(names))
            info["类别名称"] = ", ".join(list(names.values())[:10])
            if len(names) > 10:
                info["类别名称"] += f" ... (共{len(names)}类)"
        else:
            info["类别数"] = str(len(names))
            info["类别名称"] = ", ".join(names[:10])

    imgsz = None
    if hasattr(model, 'overrides'):
        imgsz = model.overrides.get('imgsz', None)
    if imgsz is None and hasattr(model, 'model') and hasattr(model.model, 'args'):
        imgsz = model.model.args.get('imgsz', None)
    info["默认图片尺寸"] = str(imgsz) if imgsz else "640"

    return info


class ModelPanel(QGroupBox):
    """模型加载与信息面板

    Signals:
        model_loaded: 模型加载成功，携带 (YOLO model, info_dict, class_names_list)
        model_load_failed: 加载失败，携带 (error_message)
    """

    model_loaded = pyqtSignal(object, dict, list)   # (model, info_dict, class_names)
    model_load_failed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__("模型配置", parent)
        self._model = None
        self._model_path = ""
        self._init_ui()

    @property
    def model(self):
        return self._model

    @property
    def model_path(self):
        return self._model_path

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # ── 模型路径行 ──
        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("模型文件:", self))
        self.path_label = QLabel("未加载")
        self.path_label.setObjectName("infoLabel")
        self.path_label.setStyleSheet("color: #6e7681; padding: 4px 8px; background: transparent;")
        path_layout.addWidget(self.path_label, stretch=1)

        btn_browse = QPushButton("浏览...")
        btn_browse.clicked.connect(self._browse_model)
        path_layout.addWidget(btn_browse)

        self.btn_load = QPushButton("加载模型")
        self.btn_load.setObjectName("primaryBtn")
        self.btn_load.clicked.connect(self._load_model)
        path_layout.addWidget(self.btn_load)

        layout.addLayout(path_layout)

        # ── 模型信息行 ──
        self.info_label = QLabel("")
        self.info_label.setObjectName("infoLabel")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

    def _browse_model(self):
        """浏览 .pt 模型文件"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择模型文件", "",
            "模型文件 (*.pt *.onnx *.engine);;所有文件 (*)"
        )
        if path:
            self.path_label.setText(path)
            self.path_label.setStyleSheet("color: #c9d1d9; padding: 4px 8px; background: transparent;")

    def _load_model(self):
        """加载模型"""
        path = self.path_label.text()
        if not path or path == "未加载":
            QMessageBox.warning(self, "提示", "请先选择模型文件")
            return

        self.btn_load.setEnabled(False)
        self.btn_load.setText("加载中...")

        try:
            model = YOLO(path)
            info = get_model_info(model, path)

            # 提取类别名称列表
            names = getattr(model, 'names', None)
            if names is None and hasattr(model, 'model') and hasattr(model.model, 'names'):
                names = model.model.names
            if isinstance(names, dict):
                class_names = list(names.values())
            elif isinstance(names, list):
                class_names = names
            else:
                class_names = []

            self._model = model
            self._model_path = path
            self.path_label.setText(Path(path).name)
            self.path_label.setStyleSheet("color: #00d4ff; font-weight: bold; padding: 4px 8px; background: transparent;")

            # 显示模型信息
            info_lines = []
            for key in ["任务类型", "模型名称", "类别数", "默认图片尺寸"]:
                if key in info:
                    info_lines.append(f"{key}: {info[key]}")
            self.info_label.setText("  |  ".join(info_lines))
            self.info_label.setStyleSheet("color: #8b949e; font-size: 12px; padding: 4px 0; background: transparent;")

            self.model_loaded.emit(model, info, class_names)

        except Exception as e:
            self.model_load_failed.emit(str(e))
            QMessageBox.critical(self, "加载失败", f"无法加载模型:\n{str(e)}")

        finally:
            self.btn_load.setEnabled(True)
            self.btn_load.setText("加载模型")

    def set_loaded_state(self, model_path, model, info, class_names):
        """从外部设置已加载的模型状态（用于主窗口恢复状态）"""
        self._model = model
        self._model_path = model_path
        self.path_label.setText(Path(model_path).name)
        self.path_label.setStyleSheet("color: #00d4ff; font-weight: bold; padding: 4px 8px; background: transparent;")

        info_lines = []
        for key in ["任务类型", "模型名称", "类别数", "默认图片尺寸"]:
            if key in info:
                info_lines.append(f"{key}: {info[key]}")
        self.info_label.setText("  |  ".join(info_lines))
        self.info_label.setStyleSheet("color: #8b949e; font-size: 12px; padding: 4px 0; background: transparent;")
