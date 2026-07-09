"""人工复核面板组件

对照技术方案 V1.0 §4.3、§8.2：
- AI 判定 NG 时展示缺陷标注和详情
- 两个大按钮："确认合格" / "确认不合格"
- 追求操作简洁——只需关注两个按钮即可完成复核
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QSizePolicy, QApplication,
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QSize
from PyQt5.QtGui import QColor, QPixmap


# ── 颜色常量（与 V4 深色主题一致）──
COLOR_CONFIRMED = "#f85149"       # 确认缺陷 — 红色（危险）
COLOR_FALSE_POS = "#d2991d"       # AI误判 — 黄色（警告）
COLOR_PENDING = "#484f58"         # 待复核 — 灰色
COLOR_DONE_BG = "#1a2332"         # 已复核行背景
COLOR_ROW_BG = "#0d1117"          # 默认行背景
COLOR_TEXT_PRIMARY = "#c9d1d9"    # 主文字
COLOR_TEXT_SECONDARY = "#6e7681"  # 次要文字
COLOR_BORDER = "#21262d"          # 边框
COLOR_ACCENT = "#00d4ff"          # 强调色
COLOR_SUCCESS = "#3fb950"         # 完成
COLOR_HIGH_CONF = "#3fb950"       # 高置信度
COLOR_MED_CONF = "#d2991d"        # 中置信度
COLOR_LOW_CONF = "#f85149"        # 低置信度


class ReviewItemWidget(QFrame):
    """单条缺陷复核行"""

    judged = pyqtSignal(int, str)  # defect_index, judgment

    def __init__(self, defect_index: int, cls_name: str, confidence: float,
                 bbox: list, thumb_pixmap=None, parent=None):
        super().__init__(parent)
        self.defect_index = defect_index
        self.cls_name = cls_name
        self.confidence = confidence
        self.bbox = bbox
        self._judged = False
        self._judgment = "pending"
        self._thumb_pixmap = thumb_pixmap

        self.setObjectName("reviewItem")
        self.setFrameShape(QFrame.NoFrame)
        self._init_ui()
        self._apply_style()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        # ── 缺陷截图缩略图 ──
        if self._thumb_pixmap is not None and not self._thumb_pixmap.isNull():
            self.thumb_label = QLabel()
            self.thumb_label.setFixedSize(120, 80)
            self.thumb_label.setAlignment(Qt.AlignCenter)
            self.thumb_label.setStyleSheet(
                "background: #060a10; border: 1px solid #21262d; border-radius: 3px;"
            )
            scaled = self._thumb_pixmap.scaled(
                QSize(120, 80), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self.thumb_label.setPixmap(scaled)
            layout.addWidget(self.thumb_label)

        # ── 序号 + 信息区 ──
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        # 序号 + 类别名
        header_row = QHBoxLayout()
        header_row.setSpacing(6)
        self.idx_label = QLabel(f"#{self.defect_index + 1}")
        self.idx_label.setFixedWidth(30)
        self.idx_label.setAlignment(Qt.AlignCenter)
        self.idx_label.setStyleSheet(
            f"color: {COLOR_TEXT_SECONDARY}; font-size: 12px; font-weight: bold; "
            "background: transparent;"
        )
        header_row.addWidget(self.idx_label)

        self.cls_label = QLabel(self.cls_name)
        self.cls_label.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 14px; font-weight: bold; "
            "background: transparent;"
        )
        header_row.addWidget(self.cls_label)

        # 置信度
        conf_pct = f"{self.confidence:.1%}"
        if self.confidence >= 0.7:
            conf_color = COLOR_HIGH_CONF
        elif self.confidence >= 0.4:
            conf_color = COLOR_MED_CONF
        else:
            conf_color = COLOR_LOW_CONF

        self.conf_label = QLabel(conf_pct)
        self.conf_label.setFixedWidth(56)
        self.conf_label.setAlignment(Qt.AlignCenter)
        self.conf_label.setStyleSheet(
            f"color: {conf_color}; font-size: 13px; font-weight: bold; "
            "background: transparent;"
        )
        header_row.addWidget(self.conf_label)
        header_row.addStretch()
        info_layout.addLayout(header_row)

        # 位置信息
        bbox_str = f"位置: ({self.bbox[0]:.0f}, {self.bbox[1]:.0f}, {self.bbox[2]:.0f}, {self.bbox[3]:.0f})"
        self.pos_label = QLabel(bbox_str)
        self.pos_label.setStyleSheet(
            f"color: {COLOR_TEXT_SECONDARY}; font-size: 10px; background: transparent;"
        )
        info_layout.addWidget(self.pos_label)

        layout.addLayout(info_layout, stretch=1)

        # ── 操作按钮 ──
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)

        self.btn_confirm = QPushButton("✓ 确认缺陷")
        self.btn_confirm.setObjectName("reviewConfirmBtn")
        self.btn_confirm.setFixedWidth(90)
        self.btn_confirm.setFixedHeight(30)
        self.btn_confirm.setCursor(Qt.PointingHandCursor)
        self.btn_confirm.clicked.connect(lambda: self._do_judge("confirmed"))
        btn_layout.addWidget(self.btn_confirm)

        self.btn_fp = QPushButton("✗ AI误判")
        self.btn_fp.setObjectName("reviewFPBtn")
        self.btn_fp.setFixedWidth(80)
        self.btn_fp.setFixedHeight(30)
        self.btn_fp.setCursor(Qt.PointingHandCursor)
        self.btn_fp.clicked.connect(lambda: self._do_judge("ai_false_positive"))
        btn_layout.addWidget(self.btn_fp)

        layout.addLayout(btn_layout)

    def _apply_style(self):
        """应用按钮样式"""
        self.btn_confirm.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_CONFIRMED};
                color: #ffffff;
                border: none;
                border-radius: 4px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #ff6b6b;
            }}
            QPushButton:disabled {{
                background-color: #30363d;
                color: #484f58;
            }}
        """)
        self.btn_fp.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_FALSE_POS};
                color: #ffffff;
                border: none;
                border-radius: 4px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #e2b34d;
            }}
            QPushButton:disabled {{
                background-color: #30363d;
                color: #484f58;
            }}
        """)

    def _do_judge(self, judgment: str):
        """执行复核判断"""
        if self._judged:
            return
        self._judged = True
        self._judgment = judgment

        # 禁用按钮
        self.btn_confirm.setEnabled(False)
        self.btn_fp.setEnabled(False)

        # 更新显示
        if judgment == "confirmed":
            self.idx_label.setStyleSheet(
                f"color: {COLOR_CONFIRMED}; font-size: 12px; font-weight: bold; "
                "background: transparent;"
            )
            self.btn_confirm.setText("✓ 已确认")
            self.btn_confirm.setStyleSheet(f"""
                QPushButton {{
                    background-color: #3d1f1f; color: {COLOR_CONFIRMED};
                    border: 1px solid {COLOR_CONFIRMED}; border-radius: 4px;
                    font-size: 12px; font-weight: bold;
                }}
            """)
        else:  # ai_false_positive
            self.idx_label.setStyleSheet(
                f"color: {COLOR_FALSE_POS}; font-size: 12px; font-weight: bold; "
                "background: transparent;"
            )
            self.btn_fp.setText("✗ 已标记")
            self.btn_fp.setStyleSheet(f"""
                QPushButton {{
                    background-color: #2d2410; color: {COLOR_FALSE_POS};
                    border: 1px solid {COLOR_FALSE_POS}; border-radius: 4px;
                    font-size: 12px; font-weight: bold;
                }}
            """)

        # 整行变暗
        self.setStyleSheet(f"#reviewItem {{ background-color: {COLOR_DONE_BG}; "
                           f"border-bottom: 1px solid {COLOR_BORDER}; }}")

        self.judged.emit(self.defect_index, judgment)

    def get_judgment(self) -> str:
        """获取当前判断"""
        return self._judgment

    def is_judged(self) -> bool:
        """是否已复核"""
        return self._judged


class ReviewPanel(QFrame):
    """人工复核面板

    嵌入检测结果面板下方，展示所有检出缺陷供工人逐项复核。

    Signals:
        review_completed(list[dict]): 所有复核完成后发出，携带复核结果列表
        review_item_changed(int, str): 单条复核状态变化时发出
    """

    review_completed = pyqtSignal(list)   # list[dict] 复核结果
    review_item_changed = pyqtSignal(int, str)  # defect_index, judgment

    def __init__(self, show_complete_button=True, parent=None):
        super().__init__(parent)
        self.setObjectName("reviewPanel")
        self.setFrameShape(QFrame.NoFrame)

        self._review_items: list[ReviewItemWidget] = []
        self._defects: list[dict] = []
        self._total = 0
        self._judged_count = 0
        self._completed = False
        self._show_complete_button = show_complete_button

        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 8, 0, 0)
        main_layout.setSpacing(4)

        # ── 标题栏 ──
        header = QHBoxLayout()
        header.setContentsMargins(4, 0, 4, 4)

        self.title_label = QLabel("🔍 人工复核")
        self.title_label.setStyleSheet(
            f"color: {COLOR_ACCENT}; font-size: 15px; font-weight: bold; background: transparent;"
        )
        header.addWidget(self.title_label)

        header.addStretch()

        self.progress_label = QLabel("")
        self.progress_label.setStyleSheet(
            f"color: {COLOR_TEXT_SECONDARY}; font-size: 12px; background: transparent;"
        )
        header.addWidget(self.progress_label)

        main_layout.addLayout(header)

        # ── 分隔线 ──
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color: {COLOR_BORDER};")
        main_layout.addWidget(sep)

        # ── 缺陷列表（可滚动）──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setMinimumHeight(120)
        scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
            "QScrollBar:vertical { width: 6px; background: #0d1117; }"
            "QScrollBar::handle:vertical { background: #30363d; border-radius: 3px; }"
        )

        self.list_widget = QWidget()
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(2)
        self.list_layout.addStretch()

        scroll.setWidget(self.list_widget)
        main_layout.addWidget(scroll)

        # ── 底部操作栏 ──
        footer = QHBoxLayout()
        footer.setContentsMargins(4, 6, 4, 4)
        footer.setSpacing(10)

        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet(
            f"color: {COLOR_TEXT_SECONDARY}; font-size: 12px; background: transparent;"
        )
        footer.addWidget(self.summary_label, stretch=1)

        self.btn_all_confirm = QPushButton("全部确认")
        self.btn_all_confirm.setObjectName("secondaryBtn")
        self.btn_all_confirm.setFixedHeight(32)
        self.btn_all_confirm.setCursor(Qt.PointingHandCursor)
        self.btn_all_confirm.clicked.connect(self._all_confirm)
        footer.addWidget(self.btn_all_confirm)

        self.btn_complete = QPushButton("✓ 完成复核")
        self.btn_complete.setObjectName("primaryBtn")
        self.btn_complete.setFixedHeight(32)
        self.btn_complete.setEnabled(False)
        self.btn_complete.setVisible(self._show_complete_button)
        self.btn_complete.setCursor(Qt.PointingHandCursor)
        self.btn_complete.clicked.connect(self._complete_review)
        footer.addWidget(self.btn_complete)

        main_layout.addLayout(footer)

        # ── 面板默认隐藏 ──
        self.setVisible(False)

    # ═══════════════════════════════════════════════════
    #  公开接口
    # ═══════════════════════════════════════════════════

    def load_defects(self, defects: list[dict]):
        """加载检测到的缺陷列表并显示面板

        Args:
            defects: 缺陷列表，每项包含:
                - defect_index: int
                - cls_name: str
                - confidence: float
                - bbox: [x1, y1, x2, y2]
                - cls_id: int (可选)
        """
        self._clear_list()
        self._defects = defects
        self._total = len(defects)
        self._judged_count = 0
        self._completed = False
        self._review_items = []

        for i, defect in enumerate(defects):
            item = ReviewItemWidget(
                defect_index=i,
                cls_name=defect.get("cls_name", "未知"),
                confidence=defect.get("confidence", 0.0),
                bbox=defect.get("bbox", [0, 0, 0, 0]),
                thumb_pixmap=defect.get("thumb_pixmap"),
                parent=self,
            )
            item.judged.connect(self._on_item_judged)
            # 插入到 stretch 之前
            self.list_layout.insertWidget(self.list_layout.count() - 1, item)
            self._review_items.append(item)

        # 更新进度
        self._update_progress()
        self._update_summary()
        self.btn_all_confirm.setEnabled(True)
        self.btn_complete.setEnabled(False)

        # 显示面板
        self.setVisible(True)

    def append_defects(self, defects: list[dict]):
        """追加缺陷到已有列表（不清空），用于连续检测模式

        Args:
            defects: 新检测到的缺陷列表，格式同 load_defects()
        """
        start_index = len(self._review_items)
        for i, defect in enumerate(defects):
            item = ReviewItemWidget(
                defect_index=start_index + i,
                cls_name=defect.get("cls_name", "未知"),
                confidence=defect.get("confidence", 0.0),
                bbox=defect.get("bbox", [0, 0, 0, 0]),
                thumb_pixmap=defect.get("thumb_pixmap"),
                parent=self,
            )
            item.judged.connect(self._on_item_judged)
            self.list_layout.insertWidget(self.list_layout.count() - 1, item)
            self._review_items.append(item)

        self._defects.extend(defects)
        self._total = len(self._review_items)
        self._update_progress()
        self._update_summary()
        self.btn_all_confirm.setEnabled(True)  # 新缺陷可再次"全部确认"
        self.btn_complete.setEnabled(False)
        self.setVisible(True)

    def reset(self):
        """重置面板（清空并隐藏）"""
        self._clear_list()
        self._defects = []
        self._total = 0
        self._judged_count = 0
        self._completed = False
        self._review_items = []
        self.setVisible(False)

    def is_completed(self) -> bool:
        """是否已完成全部复核"""
        return self._completed

    def get_unjudged_count(self) -> int:
        """返回尚未复核的缺陷数量"""
        return sum(1 for item in self._review_items if not item.is_judged())

    def get_review_results(self) -> list[dict]:
        """获取所有复核结果"""
        results = []
        for item in self._review_items:
            defect = self._defects[item.defect_index] if item.defect_index < len(self._defects) else {}
            results.append({
                "defect_index": item.defect_index,
                "cls_name": item.cls_name,
                "cls_id": defect.get("cls_id", -1),
                "confidence": item.confidence,
                "bbox": item.bbox,
                "human_judgment": item.get_judgment(),
            })
        return results

    # ═══════════════════════════════════════════════════
    #  内部方法
    # ═══════════════════════════════════════════════════

    def _clear_list(self):
        """清空列表（保留末尾的 stretch）"""
        while self.list_layout.count() > 1:
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _on_item_judged(self, defect_index: int, judgment: str):
        """单条复核完成回调"""
        self._judged_count = sum(1 for item in self._review_items if item.is_judged())
        self._update_progress()
        self._update_summary()

        self.review_item_changed.emit(defect_index, judgment)

        # 全部复核完成时启用完成按钮
        if self._judged_count >= self._total:
            self.btn_complete.setEnabled(True)
            self.btn_complete.setStyleSheet(
                "QPushButton { background-color: #3fb950; color: #ffffff; "
                "border: none; border-radius: 4px; font-size: 14px; font-weight: bold; "
                "padding: 6px 20px; }"
                "QPushButton:hover { background-color: #2ea043; }"
            )
            # 闪烁提示
            self._start_pulse()

    def _all_confirm(self):
        """一键全部确认（只能点一次）"""
        self.btn_all_confirm.setEnabled(False)
        for item in self._review_items:
            if not item.is_judged():
                item._do_judge("confirmed")

    def _complete_review(self):
        """完成复核"""
        if self._judged_count < self._total:
            return
        self._completed = True
        self._stop_pulse()

        results = self.get_review_results()
        self.review_completed.emit(results)

        # 更新标题
        confirmed = sum(1 for r in results if r["human_judgment"] == "confirmed")
        fp = sum(1 for r in results if r["human_judgment"] == "ai_false_positive")
        self.title_label.setText("✅ 复核完成")
        self.progress_label.setText(f"确认: {confirmed} | AI误判: {fp}")

        # 禁用完成按钮
        self.btn_complete.setEnabled(False)
        self.btn_complete.setText("✓ 已完成")
        self.btn_all_confirm.setEnabled(False)

    def _update_progress(self):
        """更新进度显示"""
        self.progress_label.setText(f"已复核: {self._judged_count} / {self._total}")

    def _update_summary(self):
        """更新底部统计"""
        confirmed = sum(1 for item in self._review_items if item.get_judgment() == "confirmed")
        fp = sum(1 for item in self._review_items if item.get_judgment() == "ai_false_positive")
        self.summary_label.setText(
            f"确认缺陷: {confirmed}  |  AI误判: {fp}  |  剩余: {self._total - self._judged_count}"
        )

    # ═══════════════════════════════════════════════════
    #  闪烁动画（按钮可用时）
    # ═══════════════════════════════════════════════════

    def _start_pulse(self):
        """完成按钮闪烁提示"""
        if hasattr(self, '_pulse_timer') and self._pulse_timer is not None:
            return
        self._pulse_count = 0
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(400)
        self._pulse_timer.timeout.connect(self._do_pulse)
        self._pulse_timer.start()

    def _do_pulse(self):
        """闪烁动画帧"""
        self._pulse_count += 1
        if self._pulse_count > 6:  # 闪烁3轮后停止
            self._stop_pulse()
            return
        if self._pulse_count % 2 == 0:
            self.btn_complete.setStyleSheet(
                "QPushButton { background-color: #3fb950; color: #ffffff; "
                "border: none; border-radius: 4px; font-size: 14px; font-weight: bold; "
                "padding: 6px 20px; }"
            )
        else:
            self.btn_complete.setStyleSheet(
                "QPushButton { background-color: #238636; color: #e6edf3; "
                "border: 2px solid #3fb950; border-radius: 4px; font-size: 14px; "
                "font-weight: bold; padding: 6px 20px; }"
            )

    def _stop_pulse(self):
        """停止闪烁"""
        if hasattr(self, '_pulse_timer') and self._pulse_timer is not None:
            self._pulse_timer.stop()
            self._pulse_timer = None
        self.btn_complete.setStyleSheet(
            "QPushButton { background-color: #3fb950; color: #ffffff; "
            "border: none; border-radius: 4px; font-size: 14px; font-weight: bold; "
            "padding: 6px 20px; }"
            "QPushButton:hover { background-color: #2ea043; }"
        )
