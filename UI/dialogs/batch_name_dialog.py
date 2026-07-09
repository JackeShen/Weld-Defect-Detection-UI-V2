"""批次命名对话框 — 每次检测开始前让工人填写批次信息"""

from datetime import datetime

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QDialogButtonBox,
    QGroupBox,
)
from PyQt5.QtCore import Qt, QSettings


class BatchNameDialog(QDialog):
    """批次命名对话框

    工厂工人在检测前填写：
        - 日期（自动填今天）
        - 批次号（自动递增）
        - 零件/产品名称
        - 实时预览完整批次名

    返回 dict:
        {"batch_name": "20260702_第3批", "part_name": "焊缝组件",
         "full_name": "20260702_第3批_焊缝组件"}
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置批次信息")
        self.setMinimumWidth(420)
        self.setFixedHeight(330)

        # 读取上次批次号
        self._settings = QSettings("HuifengJingbo", "WeldInspection")
        self._last_batch_num = self._settings.value("last_batch_num", 0, type=int)

        self._init_ui()
        self._update_preview()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(12, 8, 12, 8)

        # ── 表单 ──
        form = QGroupBox("批次信息")
        form_layout = QGridLayout(form)
        form_layout.setSpacing(8)
        form_layout.setContentsMargins(12, 16, 12, 12)

        # 日期
        form_layout.addWidget(QLabel("日期:"), 0, 0)
        self.date_edit = QLineEdit(datetime.now().strftime("%Y%m%d"))
        self.date_edit.setToolTip("检测日期，格式如 20260702")
        self.date_edit.setMaximumHeight(32)
        self.date_edit.textChanged.connect(self._update_preview)
        form_layout.addWidget(self.date_edit, 0, 1)

        # 批次号
        form_layout.addWidget(QLabel("批次号:"), 1, 0)
        batch_layout = QHBoxLayout()
        self.batch_edit = QLineEdit(f"第{self._last_batch_num + 1}批")
        self.batch_edit.setToolTip("自动递增，也可手动修改")
        self.batch_edit.setMaximumHeight(32)
        self.batch_edit.textChanged.connect(self._update_preview)
        batch_layout.addWidget(self.batch_edit)

        batch_hint = QLabel(f"(上次: 第{self._last_batch_num}批)")
        batch_hint.setStyleSheet("color: #6e7681; font-size: 11px;")
        batch_layout.addWidget(batch_hint)
        form_layout.addLayout(batch_layout, 1, 1)

        # 零件名称
        form_layout.addWidget(QLabel("零件名称:"), 2, 0)
        self.part_edit = QLineEdit()
        self.part_edit.setPlaceholderText("例如：焊缝组件、管道接头...")
        self.part_edit.setMaximumHeight(32)
        self.part_edit.textChanged.connect(self._update_preview)
        form_layout.addWidget(self.part_edit, 2, 1)

        layout.addWidget(form)

        # ── 预览（紧凑标签） ──
        self.preview_label = QLabel()
        self.preview_label.setStyleSheet(
            "font-size: 13px; font-weight: bold; color: #00d4ff;"
            "padding: 4px 8px;"
        )
        self.preview_label.setWordWrap(True)
        layout.addWidget(self.preview_label)

        # ── 按钮 ──
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.button(QDialogButtonBox.Ok).setText("确认")
        btn_box.button(QDialogButtonBox.Ok).setMinimumHeight(30)
        btn_box.button(QDialogButtonBox.Ok).setStyleSheet(
            "QPushButton { font-weight: bold; font-size: 13px; "
            "background-color: #238636; color: #fff; border: 1px solid #2ea043; "
            "border-radius: 4px; padding: 4px 18px; }"
            "QPushButton:hover { background-color: #2ea043; }"
        )
        btn_box.button(QDialogButtonBox.Cancel).setText("取消")
        btn_box.accepted.connect(self._on_accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _update_preview(self):
        """更新预览文本"""
        date = self.date_edit.text().strip()
        batch = self.batch_edit.text().strip()
        part = self.part_edit.text().strip()

        parts = [p for p in [date, batch, part] if p]
        full = "_".join(parts) if parts else "（请填写上方信息）"

        self.preview_label.setText(full)

    def _on_accept(self):
        """确认：保存批次号并接受"""
        # 解析批次号数字用于递增
        import re
        match = re.search(r'(\d+)', self.batch_edit.text())
        if match:
            self._settings.setValue("last_batch_num", int(match.group(1)))

        self.accept()

    def get_result(self):
        """获取填写的批次信息

        Returns:
            dict: batch_name, part_name, full_name
        """
        date = self.date_edit.text().strip()
        batch = self.batch_edit.text().strip()
        part = self.part_edit.text().strip()

        if not date:
            date = datetime.now().strftime("%Y%m%d")
        if not batch:
            batch = f"第{self._last_batch_num + 1}批"

        parts = [p for p in [date, batch, part] if p]
        full_name = "_".join(parts)
        batch_name = f"{date}_{batch}" if date and batch else full_name

        return {
            "batch_name": batch_name,
            "part_name": part,
            "full_name": full_name,
        }
