"""分析报告 & 缺陷图库页面 v5 — 3×3 网格图库 + 工厂化简易报告"""

import re
from datetime import datetime
from pathlib import Path

import cv2
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QSplitter, QComboBox, QTextEdit, QDialog,
    QVBoxLayout as QDV, QFileDialog, QMessageBox, QGroupBox,
    QGridLayout, QFrame, QScrollArea, QApplication,
)
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QPixmap, QIcon

from ..threads.report_thread import ReportThread
from ..widgets.image_viewer import ImageViewer
from ..widgets.status_indicator import StatusIndicator
from ..utils.image_conversion import cv_to_qpixmap

# 文件名解析正则
_FILENAME_RE = re.compile(
    r"^(.+)_(\d{8}_\d{6}_\d{4})\.(jpg|jpeg|png|bmp)$", re.IGNORECASE
)

SOURCE_LABELS = {"cam": "摄像头", "video": "视频", "image": "图像"}


def _parse_filename(filename: str):
    """从截图文件名中提取来源和可读时间"""
    m = _FILENAME_RE.match(filename)
    if not m:
        return None, None
    source_raw = m.group(1)
    ts_str = m.group(2)
    source_label = "未知"
    for prefix, label in SOURCE_LABELS.items():
        if source_raw.startswith(prefix):
            source_label = label
            break
    try:
        dt = datetime.strptime(ts_str, "%Y%m%d_%H%M%S_%f")
        display_time = dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        display_time = ts_str
    return source_label, display_time


class _ThumbnailCard(QFrame):
    """单张缩略图卡片，用于 3×3 网格"""

    clicked = None  # 由外部设置回调

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dashCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumSize(160, 140)
        self.setMaximumSize(220, 180)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumSize(150, 100)
        self.image_label.setStyleSheet(
            "background: #060a10; border: 1px solid #21262d; border-radius: 4px;"
        )
        layout.addWidget(self.image_label)

        self.info_label = QLabel("")
        self.info_label.setAlignment(Qt.AlignCenter)
        self.info_label.setWordWrap(True)
        self.info_label.setStyleSheet(
            "color: #8b949e; font-size: 10px; background: transparent; padding: 2px;"
        )
        layout.addWidget(self.info_label)

        self._filepath = ""

    def set_image(self, filepath: str, pixmap, info_text: str):
        """设置缩略图内容"""
        self._filepath = filepath
        scaled = pixmap.scaled(QSize(150, 100), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.image_label.setPixmap(scaled)
        self.info_label.setText(info_text)

    def mousePressEvent(self, event):
        if self._filepath and self.clicked:
            self.clicked(self._filepath)
        super().mousePressEvent(event)


class _ImagePreviewDialog(QDialog):
    """大图预览弹窗"""

    def __init__(self, cv_img, title, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(800, 600)
        self.resize(1000, 750)
        self.setStyleSheet("background-color: #0a0e13;")

        layout = QDV(self)
        layout.setContentsMargins(8, 8, 8, 8)

        viewer = ImageViewer()
        viewer.set_cv_image(cv_img)
        layout.addWidget(viewer)

        close_btn = QPushButton("关闭 (Esc)")
        close_btn.clicked.connect(self.close)
        close_btn.setMinimumHeight(36)
        layout.addWidget(close_btn)


class AnalysisPage(QWidget):
    """分析报告 & 缺陷图库页面 v5

    改进：
        - 图库：3×3 网格 + 翻页，每页最多 9 张
        - 报告：基于批次历史生成，通俗易懂
    """

    GRID_ROWS = 3
    GRID_COLS = 3
    PER_PAGE = GRID_ROWS * GRID_COLS  # 9

    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window

        # 图库状态
        self._gallery_dir = ""
        self._all_paths: list[Path] = []
        self._filtered_paths: list[Path] = []
        self._current_page = 0
        self._total_pages = 0

        # 报告
        self._report_html = ""
        self._report_thread = None

        self._init_ui()
        self._connect_signals()

    # ═══════════════════════════════════════════════════
    #  UI 构建
    # ═══════════════════════════════════════════════════

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        # ── 顶部标题栏 ──
        top_bar = QHBoxLayout()
        title = QLabel("分析报告 & 缺陷图库")
        title.setObjectName("pageTitle")
        top_bar.addWidget(title)

        subtitle = QLabel("浏览缺陷截图，查看批次检测报告")
        subtitle.setObjectName("pageSubtitle")
        top_bar.addWidget(subtitle)
        top_bar.addStretch()

        self.btn_refresh = QPushButton("🔄 刷新图库")
        self.btn_refresh.clicked.connect(self._refresh_gallery)
        top_bar.addWidget(self.btn_refresh)

        layout.addLayout(top_bar)

        # ── 主体分栏 ──
        splitter = QSplitter(Qt.Horizontal)

        # ═══ 左侧：图库 + 报告（上下分屏） ═══
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        v_splitter = QSplitter(Qt.Vertical)

        # ── 上图库：3×3 网格 ──
        gallery_wrapper = QWidget()
        gallery_wrapper_layout = QVBoxLayout(gallery_wrapper)
        gallery_wrapper_layout.setContentsMargins(0, 0, 0, 0)
        gallery_wrapper_layout.setSpacing(8)

        # 3×3 缩略图网格
        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setSpacing(6)
        self.grid_layout.setContentsMargins(4, 4, 4, 4)

        # 创建 9 个缩略图卡片
        self._cards: list[_ThumbnailCard] = []
        for row in range(self.GRID_ROWS):
            for col in range(self.GRID_COLS):
                card = _ThumbnailCard()
                card.clicked = self._on_thumbnail_clicked
                self.grid_layout.addWidget(card, row, col)
                self._cards.append(card)

        gallery_wrapper_layout.addWidget(self.grid_widget)

        # 翻页控件
        page_row = QHBoxLayout()
        page_row.addStretch()

        self.btn_prev_page = QPushButton("◀ 上一页")
        self.btn_prev_page.clicked.connect(self._prev_page)
        self.btn_prev_page.setFixedWidth(100)
        page_row.addWidget(self.btn_prev_page)

        self.page_label = QLabel("第 1/1 页")
        self.page_label.setAlignment(Qt.AlignCenter)
        self.page_label.setStyleSheet(
            "color: #c9d1d9; font-size: 13px; padding: 0 16px; background: transparent;"
        )
        self.page_label.setFixedWidth(120)
        page_row.addWidget(self.page_label)

        self.btn_next_page = QPushButton("下一页 ▶")
        self.btn_next_page.clicked.connect(self._next_page)
        self.btn_next_page.setFixedWidth(100)
        page_row.addWidget(self.btn_next_page)

        page_row.addStretch()
        gallery_wrapper_layout.addLayout(page_row)

        v_splitter.addWidget(gallery_wrapper)

        # ── 下报告视图 ──
        self.report_view = QTextEdit()
        self.report_view.setReadOnly(True)
        self.report_view.setObjectName("resultPanel")
        self.report_view.setHtml(
            '<p style="color:#8b949e; text-align:center; padding:40px;">'
            '点击右侧 <b>"生成报告"</b> 查看批次检测汇总...</p>'
        )
        v_splitter.addWidget(self.report_view)

        v_splitter.setStretchFactor(0, 3)
        v_splitter.setStretchFactor(1, 2)
        left_layout.addWidget(v_splitter)
        splitter.addWidget(left_widget)

        # ═══ 右侧：控制面板 ═══
        right_widget = QWidget()
        right_widget.setMaximumWidth(340)
        right_widget.setMinimumWidth(260)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_layout.setSpacing(10)

        # ── 图库筛选 ──
        gallery_group = QGroupBox("图库筛选")
        gallery_group_layout = QVBoxLayout(gallery_group)
        gallery_group_layout.setSpacing(6)

        gallery_group_layout.addWidget(QLabel("图片来源:"))

        self.source_filter_combo = QComboBox()
        self.source_filter_combo.addItems(["全部", "摄像头", "视频", "图像"])
        gallery_group_layout.addWidget(self.source_filter_combo)

        self.gallery_count_label = QLabel("共 0 张截图")
        self.gallery_count_label.setStyleSheet("color: #8b949e; background: transparent;")
        gallery_group_layout.addWidget(self.gallery_count_label)

        self.btn_open_dir = QPushButton("📂 打开截图目录")
        self.btn_open_dir.clicked.connect(self._open_gallery_dir)
        gallery_group_layout.addWidget(self.btn_open_dir)

        right_layout.addWidget(gallery_group)

        # ── 报告操作 ──
        report_group = QGroupBox("批次检测报告")
        report_group_layout = QVBoxLayout(report_group)
        report_group_layout.setSpacing(8)

        self.btn_generate = QPushButton("📊 生成检测报告")
        self.btn_generate.setObjectName("actionBtn")
        self.btn_generate.setMinimumHeight(40)
        self.btn_generate.clicked.connect(self._generate_report)
        report_group_layout.addWidget(self.btn_generate)

        self.btn_export = QPushButton("💾 导出 HTML 报告")
        self.btn_export.setEnabled(False)
        self.btn_export.clicked.connect(self._export_html)
        report_group_layout.addWidget(self.btn_export)

        self._report_status = StatusIndicator("等待生成")
        self._report_status.setContentsMargins(0, 4, 0, 0)
        report_group_layout.addWidget(self._report_status)

        right_layout.addWidget(report_group)
        right_layout.addStretch()

        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, stretch=1)

    def _connect_signals(self):
        self.source_filter_combo.currentTextChanged.connect(self._apply_filter)

    # ═══════════════════════════════════════════════════
    #  图库：3×3 网格 + 翻页
    # ═══════════════════════════════════════════════════

    def _refresh_gallery(self):
        """扫描截图目录，更新时间倒序列表"""
        gallery_dir = self.mw._auto_save_dir if hasattr(self.mw, '_auto_save_dir') else ""
        if not gallery_dir:
            self._show_empty_grid("保存目录未设置")
            return

        dir_path = Path(gallery_dir)
        if not dir_path.exists():
            self._show_empty_grid(f"目录不存在:\n{dir_path}")
            return

        self._gallery_dir = str(dir_path)

        self._all_paths = sorted(
            [p for p in dir_path.rglob('*')
             if p.is_file() and p.suffix.lower() in ('.jpg', '.jpeg', '.png', '.bmp')],
            key=lambda p: p.stat().st_mtime, reverse=True,
        )

        if not self._all_paths:
            self._show_empty_grid("目录中没有截图文件")
            self.gallery_count_label.setText("共 0 张截图")
            return

        self._apply_filter(self.source_filter_combo.currentText())

    def _apply_filter(self, source_type):
        """按来源筛选，重新分页"""
        if source_type == "全部":
            self._filtered_paths = list(self._all_paths)
        else:
            self._filtered_paths = [
                p for p in self._all_paths
                if _parse_filename(p.name)[0] == source_type
            ]

        self._total_pages = max(1, (len(self._filtered_paths) + self.PER_PAGE - 1) // self.PER_PAGE)
        self._current_page = 0
        self._render_page()

        self.gallery_count_label.setText(
            f"共 {len(self._filtered_paths)} 张截图（总计 {len(self._all_paths)} 张）"
        )

    def _render_page(self):
        """渲染当前页的 3×3 网格"""
        start = self._current_page * self.PER_PAGE
        end = min(start + self.PER_PAGE, len(self._filtered_paths))

        for i, card in enumerate(self._cards):
            idx = start + i
            if idx < end:
                filepath = self._filtered_paths[idx]
                pixmap = self._make_thumbnail(str(filepath))
                source_label, display_time = _parse_filename(filepath.name)
                info = f"{source_label or '?'}\n{display_time or filepath.stem}"

                if pixmap:
                    card.set_image(str(filepath), pixmap, info)
                else:
                    card.image_label.setText("⚠ 无法加载")
                    card.info_label.setText(info)
                    card._filepath = str(filepath)
                card.setVisible(True)
            else:
                card.setVisible(False)

        # 更新翻页控件
        self.page_label.setText(f"第 {self._current_page + 1}/{self._total_pages} 页")
        self.btn_prev_page.setEnabled(self._current_page > 0)
        self.btn_next_page.setEnabled(self._current_page < self._total_pages - 1)

    def _prev_page(self):
        if self._current_page > 0:
            self._current_page -= 1
            self._render_page()

    def _next_page(self):
        if self._current_page < self._total_pages - 1:
            self._current_page += 1
            self._render_page()

    def _make_thumbnail(self, path, thumb_w=150, thumb_h=100):
        """生成缩略图 QPixmap"""
        try:
            img = cv2.imread(path)
            if img is None:
                return None
            h, w = img.shape[:2]
            scale = min(thumb_w / w, thumb_h / h)
            new_w, new_h = int(w * scale), int(h * scale)
            if new_w < 1 or new_h < 1:
                return None
            thumb_cv = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
            return cv_to_qpixmap(thumb_cv)
        except Exception:
            return None

    def _show_empty_grid(self, message):
        """清空网格并显示提示"""
        for card in self._cards:
            card.image_label.clear()
            card.image_label.setText(message)
            card.info_label.setText("")
            card._filepath = ""
            card.setVisible(True)
        self.page_label.setText("第 1/1 页")
        self.btn_prev_page.setEnabled(False)
        self.btn_next_page.setEnabled(False)

    def _on_thumbnail_clicked(self, filepath):
        """点击缩略图 → 大图预览"""
        try:
            img = cv2.imread(filepath)
            if img is None:
                QMessageBox.warning(self, "错误", f"无法读取图片:\n{filepath}")
                return
        except Exception as e:
            QMessageBox.warning(self, "错误", f"读取图片失败:\n{str(e)}")
            return

        dialog = _ImagePreviewDialog(img, Path(filepath).name, self)
        dialog.exec_()

    def _open_gallery_dir(self):
        """用系统文件管理器打开截图目录"""
        if not self._gallery_dir:
            QMessageBox.information(self, "提示", "请先刷新图库")
            return
        import subprocess
        subprocess.Popen(["explorer", self._gallery_dir])

    # ═══════════════════════════════════════════════════
    #  报告生成 & 导出（V5：基于批次历史）
    # ═══════════════════════════════════════════════════

    def _generate_report(self):
        """从批次历史生成工厂化检测报告"""
        batch_history = getattr(self.mw, 'batch_history', [])

        if not batch_history:
            QMessageBox.information(
                self, "暂无检测记录",
                "当前没有批次检测记录。\n"
                "请先在「图像检测」页面完成批次检测后再生成报告。"
            )
            return

        self.btn_generate.setEnabled(False)
        self.btn_generate.setText("⏳ 生成中...")
        self._report_status.set_processing("正在分析...")

        self._report_thread = ReportThread(list(batch_history))
        self._report_thread.finished.connect(self._on_report_done)
        self._report_thread.error.connect(self._on_report_error)
        self._report_thread.start()

    def _on_report_done(self, html):
        """报告生成完成"""
        self._report_html = html
        self.report_view.setHtml(html)

        self.btn_generate.setEnabled(True)
        self.btn_generate.setText("📊 生成检测报告")
        self.btn_export.setEnabled(True)
        self._report_status.set_ready("报告已生成")

        self.report_view.verticalScrollBar().setValue(0)

    def _on_report_error(self, msg):
        """报告生成失败"""
        self.btn_generate.setEnabled(True)
        self.btn_generate.setText("📊 生成检测报告")
        self._report_status.set_error(f"生成失败: {msg}")
        QMessageBox.critical(self, "报告生成失败", msg)

    def _export_html(self):
        """导出 HTML 报告到文件"""
        if not self._report_html:
            QMessageBox.warning(self, "提示", "请先生成报告")
            return

        default_name = f"焊缝检测报告_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 HTML 报告", default_name,
            "HTML 文件 (*.html *.htm);;所有文件 (*)"
        )
        if not path:
            return

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._report_html)
            QMessageBox.information(self, "导出成功", f"报告已保存到:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"写入文件失败:\n{str(e)}")
