"""保存检测结果为 YOLO 训练数据集对话框 — 从 yolo_ui.py 迁移"""

from pathlib import Path

import numpy as np
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QTableWidget, QTableWidgetItem, QHeaderView,
    QCheckBox, QComboBox, QWidget, QFrame, QDialogButtonBox,
    QMessageBox,
)
from PyQt5.QtCore import Qt


class SaveAsDatasetDialog(QDialog):
    """保存检测结果为 YOLO 训练数据集的对话框

    功能:
        - 列出所有检测到的目标，显示类别/置信度
        - 允许用户修正分类错误的类别（下拉框）
        - 允许用户勾选/取消每个目标是否保存
        - 选择保存目录，按 YOLO 格式输出 images/ + labels/
    """

    def __init__(self, results, image_path, parent=None):
        """
        Args:
            results: ultralytics Results 对象 (单张图)
            image_path: 原始图片路径
            parent: 父窗口
        """
        super().__init__(parent)
        self.results = results
        self.image_path = image_path
        self.result = results[0] if isinstance(results, list) else results

        # 提取数据
        self.names = self.result.names or {}
        self._extract_detections()

        self.setWindowTitle("保存检测结果为训练数据")
        self.setMinimumSize(620, 400)
        self.init_ui()

    def _extract_detections(self):
        """从 result 中提取所有检测目标的信息"""
        r = self.result
        boxes = r.boxes

        if boxes is None or len(boxes) == 0:
            self.detections = []
            return

        cls_ids = boxes.cls.cpu().numpy().astype(int)
        confs = boxes.conf.cpu().numpy()
        xywhn = boxes.xywhn.cpu().numpy()  # 归一化 [cx, cy, w, h]

        # 检查是否有分割 mask
        has_masks = r.masks is not None and r.masks.data is not None
        if has_masks:
            mask_xyn = r.masks.xyn  # 归一化多边形顶点列表
        else:
            mask_xyn = [None] * len(cls_ids)

        self.detections = []
        for i in range(len(cls_ids)):
            det = {
                "cls_id": int(cls_ids[i]),
                "cls_name": self.names.get(int(cls_ids[i]), f"类别{int(cls_ids[i])}"),
                "conf": float(confs[i]),
                "xywhn": xywhn[i].tolist(),   # [cx, cy, w, h] 归一化
                "mask_xyn": mask_xyn[i] if has_masks else None,
                "include": True,               # 默认包含
            }
            self.detections.append(det)

        self.has_masks = has_masks

    def init_ui(self):
        """构建对话框 UI"""
        layout = QVBoxLayout(self)

        # ── 保存目录选择 ──
        dir_layout = QHBoxLayout()
        dir_layout.addWidget(QLabel("保存目录:"))
        self.dir_edit = QLabel(str(Path.home() / "Desktop" / "labeled_data"))
        self.dir_edit.setFrameStyle(QFrame.Panel | QFrame.Sunken)
        self.dir_edit.setMinimumWidth(250)
        dir_layout.addWidget(self.dir_edit, stretch=1)

        btn_browse = QPushButton("浏览...")
        btn_browse.clicked.connect(self._browse_dir)
        dir_layout.addWidget(btn_browse)
        layout.addLayout(dir_layout)

        # 子目录结构选项
        subdir_layout = QHBoxLayout()
        self.use_subdirs_check = QCheckBox("创建 images/ 和 labels/ 子目录")
        self.use_subdirs_check.setChecked(True)
        self.use_subdirs_check.setToolTip("勾选后按 YOLO 标准数据集结构组织文件")
        subdir_layout.addWidget(self.use_subdirs_check)

        # 显示标签格式
        self.format_label = QLabel()
        subdir_layout.addStretch()
        subdir_layout.addWidget(self.format_label)
        layout.addLayout(subdir_layout)

        # ── 目标列表表格 ──
        layout.addWidget(QLabel("检测目标列表（可修正类别和勾选是否保存）："))

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["#", "类别", "置信度", "包含", "类型"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.setMinimumHeight(200)
        self._populate_table()
        layout.addWidget(self.table)

        # ── 快捷操作 ──
        quick_layout = QHBoxLayout()
        btn_select_all = QPushButton("全选")
        btn_select_all.clicked.connect(lambda: self._set_all_include(True))
        quick_layout.addWidget(btn_select_all)

        btn_deselect_all = QPushButton("取消全选")
        btn_deselect_all.clicked.connect(lambda: self._set_all_include(False))
        quick_layout.addWidget(btn_deselect_all)

        btn_reset_cls = QPushButton("重置类别")
        btn_reset_cls.setToolTip("恢复所有类别为模型原始预测")
        btn_reset_cls.clicked.connect(self._reset_classes)
        quick_layout.addWidget(btn_reset_cls)

        quick_layout.addStretch()

        # 统计
        self.stats_label = QLabel()
        quick_layout.addWidget(self.stats_label)
        layout.addLayout(quick_layout)

        self._update_stats()

        # ── 确认 / 取消 ──
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.button(QDialogButtonBox.Ok).setText("确认保存")
        btn_box.button(QDialogButtonBox.Ok).clicked.connect(self._save)
        btn_box.button(QDialogButtonBox.Cancel).clicked.connect(self.reject)
        layout.addWidget(btn_box)

    def _populate_table(self):
        """填充目标列表表格"""
        self.table.setRowCount(len(self.detections))

        # 构建类别名列表供下拉框使用
        class_names = list(self.names.values()) if self.names else []
        if not class_names:
            class_names = ["缺陷"]

        for i, det in enumerate(self.detections):
            # 序号
            item = QTableWidgetItem(str(i + 1))
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 0, item)

            # 类别下拉框
            combo = QComboBox()
            combo.addItems(class_names)
            # 选中原始预测类别
            if det["cls_name"] in class_names:
                combo.setCurrentText(det["cls_name"])
            self.table.setCellWidget(i, 1, combo)

            # 置信度
            conf_item = QTableWidgetItem(f"{det['conf']:.3f}")
            conf_item.setFlags(conf_item.flags() & ~Qt.ItemIsEditable)
            if det["conf"] < 0.5:
                conf_item.setForeground(Qt.red)
            self.table.setItem(i, 2, conf_item)

            # 包含勾选框
            check = QCheckBox()
            check.setChecked(det["include"])
            check.stateChanged.connect(
                lambda state, idx=i: self._on_include_changed(idx, state)
            )
            # 居中显示 checkbox
            check_widget = QWidget()
            check_layout = QHBoxLayout(check_widget)
            check_layout.addWidget(check)
            check_layout.setAlignment(Qt.AlignCenter)
            check_layout.setContentsMargins(0, 0, 0, 0)
            self.table.setCellWidget(i, 3, check_widget)

            # 类型
            type_text = "分割" if det["mask_xyn"] is not None else "检测"
            type_item = QTableWidgetItem(type_text)
            type_item.setFlags(type_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 4, type_item)

        # 更新格式提示
        fmt = "分割(多边形)" if self.has_masks else "检测(边界框)"
        self.format_label.setText(f"标注格式: {fmt}")

    def _on_include_changed(self, idx, state):
        """勾选框状态改变"""
        if 0 <= idx < len(self.detections):
            self.detections[idx]["include"] = (state == Qt.Checked)
            self._update_stats()

    def _set_all_include(self, include: bool):
        """全选/取消全选"""
        for det in self.detections:
            det["include"] = include
        # 刷新 checkbox
        for i in range(self.table.rowCount()):
            widget = self.table.cellWidget(i, 3)
            if widget:
                check = widget.findChild(QCheckBox)
                if check:
                    check.setChecked(include)
        self._update_stats()

    def _reset_classes(self):
        """恢复所有类别为原始预测"""
        for i, det in enumerate(self.detections):
            combo = self.table.cellWidget(i, 1)
            if combo and det["cls_name"] in [combo.itemText(j) for j in range(combo.count())]:
                combo.setCurrentText(det["cls_name"])

    def _update_stats(self):
        """更新统计信息"""
        included = sum(1 for d in self.detections if d["include"])
        total = len(self.detections)
        self.stats_label.setText(f"将保存: {included} / {total} 个目标")

    def _browse_dir(self):
        """选择保存目录"""
        folder = QFileDialog.getExistingDirectory(self, "选择保存目录")
        if folder:
            self.dir_edit.setText(folder)

    def _save(self):
        """执行保存"""
        save_dir = Path(self.dir_edit.text())

        # 创建子目录
        if self.use_subdirs_check.isChecked():
            img_dir = save_dir / "images"
            lbl_dir = save_dir / "labels"
        else:
            img_dir = save_dir
            lbl_dir = save_dir

        img_dir.mkdir(parents=True, exist_ok=True)
        lbl_dir.mkdir(parents=True, exist_ok=True)

        # 构建类别名→ID映射（用于用户修正后的类别）
        class_names = list(self.names.values()) if self.names else []
        if not class_names:
            class_names = ["缺陷"]

        # 复制原图
        src_img = Path(self.image_path)
        dst_img = img_dir / src_img.name
        import shutil
        shutil.copy2(str(src_img), str(dst_img))

        # 生成标注文件
        label_name = src_img.stem + ".txt"
        label_path = lbl_dir / label_name

        lines = []
        for i, det in enumerate(self.detections):
            if not det["include"]:
                continue

            # 获取用户修正后的类别
            combo = self.table.cellWidget(i, 1)
            if combo:
                corrected_name = combo.currentText()
                if corrected_name in class_names:
                    cls_id = class_names.index(corrected_name)
                else:
                    cls_id = det["cls_id"]
            else:
                cls_id = det["cls_id"]

            if det["mask_xyn"] is not None:
                # 分割格式: cls_id x1 y1 x2 y2 ...
                points = det["mask_xyn"]
                if isinstance(points, np.ndarray):
                    points = points.tolist()
                pts_str = " ".join(f"{p:.6f}" for pt in points for p in pt)
                lines.append(f"{cls_id} {pts_str}")
            else:
                # 检测格式: cls_id cx cy w h
                cx, cy, w, h = det["xywhn"]
                lines.append(f"{cls_id} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")

        label_path.write_text("\n".join(lines), encoding="utf-8")

        saved_count = len(lines)
        QMessageBox.information(
            self, "保存成功",
            f"已保存到: {save_dir}\n\n"
            f"  图片: {dst_img.name}\n"
            f"  标注: {label_name} ({saved_count} 个目标)\n"
            f"  格式: {'YOLO 分割(多边形)' if self.has_masks else 'YOLO 检测(边界框)'}"
        )
        self.accept()
