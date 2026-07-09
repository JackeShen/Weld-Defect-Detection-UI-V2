"""检测记录日志页面 — v3.1 新增"""

from datetime import datetime
import csv

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog,
    QMessageBox,
)
from PyQt5.QtCore import Qt, pyqtSlot, QTimer
from PyQt5.QtGui import QColor


class LogPage(QWidget):
    """检测记录日志页

    实时接收检测事件，以表格形式展示历史记录。
    增量插入 + 定时批量刷新，不卡UI。
    """

    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self._records = []
        self._record_id = 0
        self._pending_inserts = 0

        self._init_ui()

        # 每500ms批量刷新表格
        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(500)
        self._flush_timer.timeout.connect(self._flush_pending)
        self._flush_timer.start()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        # ── 标题 ──
        title_row = QHBoxLayout()
        title = QLabel("检测记录日志")
        title.setObjectName("pageTitle")
        title_row.addWidget(title)

        subtitle = QLabel("摄像头和视频实时检测时自动记录缺陷信息")
        subtitle.setObjectName("pageSubtitle")
        title_row.addWidget(subtitle)
        title_row.addStretch()

        self._count_label = QLabel("共 0 条记录")
        self._count_label.setStyleSheet("color: #8b949e; font-size: 12px; padding: 0 8px; background: transparent;")
        title_row.addWidget(self._count_label)

        btn_export = QPushButton("导出 CSV")
        btn_export.clicked.connect(self._export_csv)
        title_row.addWidget(btn_export)

        btn_clear = QPushButton("清空记录")
        btn_clear.clicked.connect(self._clear_records)
        title_row.addWidget(btn_clear)

        layout.addLayout(title_row)

        # ── 表格 ──
        self._table = QTableWidget()
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels([
            "序号", "时间", "来源", "批次名", "缺陷类别", "置信度", "帧号",
        ])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setAlternatingRowColors(False)
        self._table.verticalHeader().setVisible(False)
        layout.addWidget(self._table, stretch=1)

        # ── 底部状态 ──
        self._status_label = QLabel("等待检测事件...")
        self._status_label.setStyleSheet("color: #484f58; font-size: 11px; padding: 4px 0; background: transparent;")
        layout.addWidget(self._status_label)

    # ═══════════════════════════════════════════════════
    #  公开接口
    # ═══════════════════════════════════════════════════

    @pyqtSlot(object, str, int, str)
    def add_detection_record(self, results, source="摄像头", frame_idx=0, batch_name=""):
        """接收检测结果，提取缺陷信息并记录

        Args:
            results: ultralytics Results 对象
            source: 来源标识（"摄像头" / "视频"）
            frame_idx: 帧号
            batch_name: V5 批次名
        """
        if results is None:
            return

        if isinstance(results, list):
            if len(results) == 0:
                return
            r = results[0]
        else:
            r = results
        boxes = r.boxes
        names = r.names or {}

        if boxes is None or len(boxes) == 0:
            return

        cls_ids = boxes.cls.cpu().numpy().astype(int)
        confs = boxes.conf.cpu().numpy()

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for i in range(len(cls_ids)):
            self._record_id += 1
            cls_name = names.get(int(cls_ids[i]), f"类别{int(cls_ids[i])}")
            conf = float(confs[i])

            record = {
                "id": self._record_id,
                "time": now,
                "source": source,
                "batch_name": batch_name or "—",
                "class_name": cls_name,
                "confidence": conf,
                "frame": frame_idx,
            }
            self._records.append(record)

        # 增量插入新记录（不复建表格），用定时器批量刷新
        self._pending_inserts += len(cls_ids)
        self._update_status(source, len(cls_ids), frame_idx)

    def _flush_pending(self):
        """批量写入待插入的记录到表格（只插新行，不重建）"""
        if self._pending_inserts <= 0:
            return

        # 只取最近未写入的记录
        total = len(self._records)
        new_count = min(self._pending_inserts, total)
        start_idx = total - new_count

        for i in range(start_idx, total):
            rec = self._records[i]
            row = self._table.rowCount()
            self._table.insertRow(row)

            self._table.setItem(row, 0, self._make_item(str(rec["id"])))
            self._table.setItem(row, 1, self._make_item(rec["time"]))

            src_item = self._make_item(rec["source"])
            src_item.setForeground(QColor("#00d4ff" if rec["source"] == "摄像头" else "#58a6ff"))
            self._table.setItem(row, 2, src_item)

            # V5: 批次名列
            batch_item = self._make_item(rec.get("batch_name", "—"))
            self._table.setItem(row, 3, batch_item)

            cls_item = self._make_item(rec["class_name"])
            name_lower = rec["class_name"].lower()
            if any(kw in name_lower for kw in ["bad", "defect", "crack", "porosity", "缺陷", "裂纹"]):
                cls_item.setForeground(QColor("#f85149"))
            else:
                cls_item.setForeground(QColor("#3fb950"))
            self._table.setItem(row, 4, cls_item)

            conf_item = self._make_item(f"{rec['confidence']:.2%}")
            if rec["confidence"] < 0.5:
                conf_item.setForeground(QColor("#d2991d"))
            self._table.setItem(row, 5, conf_item)

            self._table.setItem(row, 6, self._make_item(str(rec["frame"])))

        # 删除超出200的旧行
        while self._table.rowCount() > 200:
            self._table.removeRow(0)

        if self._table.rowCount() > 0:
            self._table.scrollToBottom()

        self._count_label.setText(f"共 {len(self._records)} 条记录")
        self._pending_inserts = 0

    def _make_item(self, text):
        item = QTableWidgetItem(text)
        item.setTextAlignment(Qt.AlignCenter)
        return item

    def _update_status(self, source, count, frame):
        self._status_label.setText(
            f"最新: [{source}] 帧 #{frame} — 检测到 {count} 个缺陷  |  "
            f"累计: {len(self._records)} 条"
        )

    def add_batch_record(self, summary: dict):
        """添加批次汇总记录（V5 新增）

        Args:
            summary: finalize_batch() 返回的汇总字典
        """
        self._record_id += 1
        verdict = "✅ 通过" if summary.get("passed", False) else "🚨 不通过"
        batch_name = summary.get("full_name", summary.get("batch_name", "—"))

        record = {
            "id": self._record_id,
            "time": summary.get("time", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            "source": "批次汇总",
            "batch_name": batch_name,
            "class_name": verdict,
            "confidence": 0.0,
            "frame": summary.get("total_images", 0),
            "_is_batch": True,
        }
        self._records.append(record)
        self._pending_inserts += 1
        self._update_status("批次", summary.get("total_defects", 0), 0)

    def _clear_records(self):
        """清空所有记录"""
        self._records.clear()
        self._record_id = 0
        self._table.setRowCount(0)
        self._count_label.setText("共 0 条记录")
        self._status_label.setText("记录已清空")

    def _export_csv(self):
        """导出为 CSV 文件"""
        if not self._records:
            QMessageBox.information(self, "提示", "暂无记录可导出")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "导出检测记录",
            f"detection_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "CSV 文件 (*.csv)"
        )
        if not path:
            return

        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["序号", "时间", "来源", "批次名", "缺陷类别", "置信度", "帧号"])
            for rec in self._records:
                row = [
                    rec["id"], rec["time"], rec["source"],
                    rec.get("batch_name", "—"),
                    rec["class_name"],
                    f"{rec['confidence']:.4f}" if rec.get("confidence", 0) > 0 else "—",
                    rec["frame"],
                ]
                writer.writerow(row)

        QMessageBox.information(
            self, "导出成功",
            f"已导出 {len(self._records)} 条记录到:\n{path}"
        )
