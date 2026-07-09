"""主窗口 v5 工厂版 — 西安汇丰-京博工业焊缝检测系统（批次管理）"""

import sys, os, threading
from pathlib import Path
from datetime import datetime

import cv2
import numpy as np
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QStackedWidget, QStatusBar, QLabel, QMessageBox, QFileDialog,
    QFrame, QGraphicsOpacityEffect, QShortcut,
)
from PyQt5.QtCore import Qt, pyqtSignal, QSettings, QTimer, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QFont, QKeySequence, QColor

from ultralytics import YOLO
from .weld_width import WeldWidthCalculator

from .sidebar import SidebarWidget
from .pages import ImagePage, CameraPage, VideoPage
from .pages.dashboard_page import DashboardPage
from .pages.log_page import LogPage
from .pages.analysis_page import AnalysisPage
from .utils.width_overlay import draw_width_overlay
from .widgets.status_indicator import StatusIndicator


def _load_stylesheet():
    qss_path = Path(__file__).parent / "resources" / "style.qss"
    if qss_path.exists():
        return qss_path.read_text(encoding="utf-8")
    return ""


class WeldInspectionMainWindow(QMainWindow):
    """主窗口 v5 工厂版 — 批次管理"""

    model_loaded_signal = pyqtSignal(object, dict, list)
    status_message = pyqtSignal(str)
    batch_finalized = pyqtSignal(dict)  # 批次结束时发射，携带批次汇总

    PAGE_DASH = 0
    PAGE_CAMERA = 1
    PAGE_IMAGE = 2
    PAGE_VIDEO = 3
    PAGE_LOG = 4
    PAGE_ANALYSIS = 5

    def __init__(self):
        super().__init__()
        self.setWindowTitle("西安汇丰-京博工业焊缝检测系统 v5")
        self.setMinimumSize(1400, 880)
        self.resize(1500, 920)

        # ── 设置持久化 ──
        self._settings = QSettings("HuifengJingbo", "WeldInspection")
        self._auto_save = self._settings.value("auto_save", True, type=bool)
        self._sound_enabled = self._settings.value("sound_enabled", True, type=bool)
        self._auto_save_dir = self._settings.value("auto_save_dir", str(Path(__file__).parent / "weld_results"))

        # ── 共享状态 ──
        self.model: YOLO | None = None
        self.model_path: str = self._settings.value("last_model", "")
        self.model_info: dict = {}
        self.class_names: list[str] = []
        self.model_task: str = ""
        self.width_calculator: WeldWidthCalculator | None = None

        # ── 统计数据 ──
        self.today_total = 0
        self.today_defects = 0
        self._last_defect_time = None

        # ═══════════════════════════════════════════════════
        #  V5 批次管理
        # ═══════════════════════════════════════════════════
        self.batch_state = {
            "active": False,
            "batch_name": "",
            "full_name": "",
            "part_name": "",
            "total_images": 0,
            "total_defects": 0,
            "defect_details": [],  # [(image_path, cls_name, conf), ...]
        }
        self.batch_history: list[dict] = []  # 已完成批次的汇总记录

        # ── 线程 ──
        self._detection_thread = None
        self._camera_thread = None
        self._video_thread = None

        # ── 动画 ──
        self._transitioning = False

        self._init_ui()
        self._apply_style()
        self._connect_signals()
        self._setup_shortcuts()
        self._start_scan_animation()
        self._restore_settings()

        # 初始状态：模型未加载（红色灯）
        self._header_status.set_error("模型未加载")
        self._status_main.setText("就绪 — 请加载模型")

    # ═══════════════════════════════════════════════════
    #  UI 初始化
    # ═══════════════════════════════════════════════════

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 顶部标题栏 ──
        header = QFrame()
        header.setObjectName("headerBar")
        header.setFixedHeight(80)

        hl = QHBoxLayout(header)
        hl.setContentsMargins(20, 0, 20, 0)
        hl.setSpacing(0)

        # 左侧 Logo
        logo_area = QWidget()
        logo_area.setFixedWidth(220)
        ll = QHBoxLayout(logo_area); ll.setContentsMargins(8, 0, 0, 0)
        logo_icon = QLabel("🔬")
        logo_icon.setStyleSheet("font-size: 28px; background: transparent;")
        ll.addWidget(logo_icon); ll.addSpacing(8)
        cl = QLabel("汇丰·京博")
        cl.setStyleSheet("color: #8b949e; font-size: 12px; font-weight: bold; letter-spacing: 2px; background: transparent;")
        ll.addWidget(cl); ll.addStretch()
        hl.addWidget(logo_area)

        # 中间标题
        ta = QWidget()
        tl = QVBoxLayout(ta); tl.setContentsMargins(0, 10, 0, 8); tl.setSpacing(2)
        self.header_title = QLabel("西安汇丰-京博工业焊缝检测系统")
        self.header_title.setObjectName("headerTitle")
        self.header_title.setAlignment(Qt.AlignCenter)
        self.header_title.setStyleSheet(
            "color: #e6edf3; font-size: 22px; font-weight: bold; letter-spacing: 3px; background: transparent;")
        tl.addWidget(self.header_title)

        self.header_subtitle = QLabel("Xi'an Huifeng-Jingbo  |  Industrial Weld Inspection System")
        self.header_subtitle.setObjectName("headerSubtitle")
        self.header_subtitle.setAlignment(Qt.AlignCenter)
        self.header_subtitle.setStyleSheet(
            "color: #00d4ff; font-size: 10px; letter-spacing: 2px; background: transparent;")
        tl.addWidget(self.header_subtitle)
        hl.addWidget(ta, stretch=1)

        # 右侧状态
        sa = QWidget(); sa.setFixedWidth(260)
        sl = QVBoxLayout(sa); sl.setContentsMargins(0, 12, 8, 0); sl.setSpacing(4)
        sr = QHBoxLayout(); sr.addStretch()
        self._header_status = StatusIndicator("模型未加载")
        self._header_status.setContentsMargins(0, 0, 0, 0)
        sr.addWidget(self._header_status); sl.addLayout(sr)
        self._header_model_info = QLabel("")
        self._header_model_info.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._header_model_info.setStyleSheet("color: #6e7681; font-size: 10px; background: transparent;")
        sl.addWidget(self._header_model_info)
        hl.addWidget(sa)
        root.addWidget(header)

        # ── 青蓝渐变光线 ──
        sep = QFrame()
        sep.setObjectName("headerSep")
        sep.setFixedHeight(2)
        sep.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            "stop:0 #0a0e13, stop:0.3 #00d4ff, stop:0.5 #58a6ff, "
            "stop:0.7 #00d4ff, stop:1 #0a0e13); border: none;")
        root.addWidget(sep)

        # ── 扫描线 ──
        self._scan_line = QFrame(self.centralWidget())
        self._scan_line.setObjectName("scanLine")
        self._scan_line.setFixedHeight(1)
        self._scan_line.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._scan_line.show()

        # ═══════════════════════════════════════════════
        #  主体：侧边栏 + 页面栈
        # ═══════════════════════════════════════════════
        body = QWidget()
        bl = QHBoxLayout(body); bl.setContentsMargins(0, 0, 0, 0); bl.setSpacing(0)

        self.sidebar = SidebarWidget()
        bl.addWidget(self.sidebar)

        content_area = QWidget()
        content_area.setObjectName("contentArea")
        cl2 = QVBoxLayout(content_area); cl2.setContentsMargins(0, 0, 0, 0); cl2.setSpacing(0)

        self.page_stack = QStackedWidget()
        self.dashboard_page = DashboardPage(self)
        self.camera_page = CameraPage(self)
        self.image_page = ImagePage(self)
        self.video_page = VideoPage(self)
        self.log_page = LogPage(self)
        self.analysis_page = AnalysisPage(self)

        self.page_stack.addWidget(self.dashboard_page)
        self.page_stack.addWidget(self.camera_page)
        self.page_stack.addWidget(self.image_page)
        self.page_stack.addWidget(self.video_page)
        self.page_stack.addWidget(self.log_page)
        self.page_stack.addWidget(self.analysis_page)
        self.page_stack.setCurrentIndex(self.PAGE_DASH)
        cl2.addWidget(self.page_stack)
        bl.addWidget(content_area, stretch=1)
        root.addWidget(body, stretch=1)

        # ═══════════════════════════════════════════════
        #  大屏报警条（工厂专用）
        # ═══════════════════════════════════════════════
        self._alarm_bar = QFrame()
        self._alarm_bar.setFixedHeight(6)
        self._alarm_bar.setAutoFillBackground(True)
        palette = self._alarm_bar.palette()
        palette.setColor(self._alarm_bar.backgroundRole(), QColor("#30363d"))
        self._alarm_bar.setPalette(palette)
        root.addWidget(self._alarm_bar)

        # ── 状态栏 ──
        sb = QStatusBar()
        self.setStatusBar(sb)
        self._status_main = QLabel("就绪")
        sb.addWidget(self._status_main)
        sb.addPermanentWidget(QLabel(""))
        self._status_model = QLabel("")
        self._status_model.setStyleSheet("color: #6e7681; padding: 0 12px; background: transparent;")
        sb.addPermanentWidget(self._status_model)
        self._status_fps = QLabel("")
        self._status_fps.setStyleSheet("color: #00d4ff; font-weight: bold; padding: 0 8px; background: transparent;")
        sb.addPermanentWidget(self._status_fps)
        self._status_alarm = QLabel("")
        self._status_alarm.setStyleSheet("padding: 0 12px; background: transparent;")
        sb.addPermanentWidget(self._status_alarm)

    # ═══════════════════════════════════════════════════
    #  键盘快捷键
    # ═══════════════════════════════════════════════════

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("F11"), self, self._toggle_fullscreen)
        QShortcut(QKeySequence("Escape"), self, self._exit_fullscreen)
        QShortcut(QKeySequence("Ctrl+S"), self, self._quick_save)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Space and not event.modifiers():
            # 空格键触发当前页面的检测
            current = self.page_stack.currentIndex()
            if current == self.PAGE_IMAGE:
                self.image_page._run_detection()
            elif current == self.PAGE_CAMERA:
                self.camera_page._start_batch_flow()
            elif current == self.PAGE_VIDEO:
                self.video_page._toggle_play_pause()
        super().keyPressEvent(event)

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _exit_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()

    def _quick_save(self):
        current = self.page_stack.currentIndex()
        if current == self.PAGE_IMAGE:
            self.image_page._save_result_image()

    # ═══════════════════════════════════════════════════
    #  扫描线动画
    # ═══════════════════════════════════════════════════

    def _start_scan_animation(self):
        from PyQt5.QtCore import QTimer
        self._scan_timer = QTimer(self)
        self._scan_timer.setInterval(40)
        self._scan_timer.timeout.connect(self._animate_scan)
        self._scan_offset = 84
        self._scan_direction = 1
        self._scan_timer.start()

    def _animate_scan(self):
        central = self.centralWidget()
        cw = central.width()
        ch = central.height()
        top = 84
        bottom = ch - 40
        if bottom <= top:
            return
        self._scan_offset += self._scan_direction * 3
        if self._scan_offset > bottom:
            self._scan_offset = top
        elif self._scan_offset < top:
            self._scan_offset = top
        self._scan_line.setGeometry(0, self._scan_offset, cw, 1)

    # ═══════════════════════════════════════════════════
    #  页面过渡动画
    # ═══════════════════════════════════════════════════

    def _animate_page_transition(self, target_index):
        if self._transitioning:
            self.page_stack.setCurrentIndex(target_index)
            return
        current = self.page_stack.currentWidget()
        target = self.page_stack.widget(target_index)
        if current is None or target is None or current is target:
            self.page_stack.setCurrentIndex(target_index)
            return
        self._transitioning = True
        fade_out = QGraphicsOpacityEffect(current)
        current.setGraphicsEffect(fade_out)
        anim_out = QPropertyAnimation(fade_out, b"opacity")
        anim_out.setDuration(120)
        anim_out.setStartValue(1.0)
        anim_out.setEndValue(0.2)
        anim_out.setEasingCurve(QEasingCurve.OutCubic)

        def on_fade_done():
            current.setGraphicsEffect(None)
            self.page_stack.setCurrentIndex(target_index)
            fade_in = QGraphicsOpacityEffect(target)
            target.setGraphicsEffect(fade_in)
            fade_in.setOpacity(0.2)
            anim_in = QPropertyAnimation(fade_in, b"opacity")
            anim_in.setDuration(180)
            anim_in.setStartValue(0.2)
            anim_in.setEndValue(1.0)
            anim_in.setEasingCurve(QEasingCurve.InCubic)
            def on_fade_in_done():
                target.setGraphicsEffect(None)
                self._transitioning = False
            anim_in.finished.connect(on_fade_in_done)
            anim_in.start(QPropertyAnimation.DeleteWhenStopped)
        anim_out.finished.connect(on_fade_done)
        anim_out.start(QPropertyAnimation.DeleteWhenStopped)

    # ═══════════════════════════════════════════════════
    #  样式 & 信号
    # ═══════════════════════════════════════════════════

    def _apply_style(self):
        self.setStyleSheet(_load_stylesheet())
        QApplication.instance().setFont(QFont("Microsoft YaHei", 9))

    def _connect_signals(self):
        self.sidebar.page_changed.connect(self._on_sidebar_nav)
        self.dashboard_page.navigate_to.connect(self._on_dashboard_nav)
        self.status_message.connect(self._status_main.setText)

    def _on_sidebar_nav(self, stack_index):
        self._switch_page(stack_index)

    def _on_dashboard_nav(self, stack_index):
        if stack_index >= 1:
            self.sidebar.page_changed.emit(stack_index)
        self._switch_page(stack_index)

    def _switch_page(self, index):
        # 离开旧页面的生命周期
        old_index = self.page_stack.currentIndex()
        if old_index == self.PAGE_CAMERA:
            self.camera_page.on_page_left()
        elif old_index == self.PAGE_VIDEO:
            self.video_page.on_page_left()
        # 清理线程
        if self._camera_thread and self._camera_thread.isRunning():
            self._camera_thread.requestInterruption()
            self._camera_thread.wait(2000)
            self._camera_thread = None
        if self._video_thread and self._video_thread.isRunning():
            self._video_thread.stop()
            self._video_thread.wait(2000)
            self._video_thread = None
        self._status_fps.setText("")
        self._animate_page_transition(index)
        # 进入新页面的生命周期
        if index == self.PAGE_CAMERA:
            self.camera_page.on_page_entered()

    # ═══════════════════════════════════════════════════
    #  设置持久化
    # ═══════════════════════════════════════════════════

    def _restore_settings(self):
        """恢复上次保存的设置"""
        # 恢复相机参数
        fx = self._settings.value("fx", 2500.0, type=float)
        fy = self._settings.value("fy", 2500.0, type=float)
        dist = self._settings.value("distance", 300.0, type=float)
        for page in [self.image_page, self.camera_page, self.video_page]:
            if hasattr(page, 'weld_params'):
                page.weld_params.fx_spin.setValue(fx)
                page.weld_params.fy_spin.setValue(fy)
                page.weld_params.distance_spin.setValue(dist)

        # 恢复模型（如果有的话尝试自动加载）
        if self.model_path and Path(self.model_path).exists():
            try:
                model = YOLO(self.model_path)
                from .widgets.model_panel import get_model_info
                info = get_model_info(model, self.model_path)
                names = model.names
                class_names = list(names.values()) if isinstance(names, dict) else list(names) if isinstance(names, list) else []
                self.handle_model_loaded(model, info, class_names)
                self.status_message.emit("已自动恢复上次模型")
            except Exception:
                pass

    def _save_settings(self):
        """保存当前设置"""
        self._settings.setValue("last_model", self.model_path)
        self._settings.setValue("auto_save", self._auto_save)
        self._settings.setValue("sound_enabled", self._sound_enabled)
        self._settings.setValue("auto_save_dir", self._auto_save_dir)

        # 保存相机参数
        wp = self.image_page.weld_params
        self._settings.setValue("fx", wp.fx_spin.value())
        self._settings.setValue("fy", wp.fy_spin.value())
        self._settings.setValue("distance", wp.distance_spin.value())

    # ═══════════════════════════════════════════════════
    #  模型管理
    # ═══════════════════════════════════════════════════

    def handle_model_loaded(self, model, info, class_names):
        self.model = model
        self.model_info = info
        self.class_names = class_names
        self.model_task = info.get("任务类型", "")
        self.model_path = getattr(model, 'ckpt_path', None) or getattr(self, 'model_path', '')

        model_name = info.get("文件名", "")
        task_type = info.get("任务类型", "")

        self._header_status.set_ready(f"模型已加载 ({task_type})")
        self._header_model_info.setText(f"{model_name}  |  {info.get('类别数', '?')} 类")
        self.sidebar.set_model_loaded(model_name, task_type)

        self.dashboard_page.update_model_info(info, task_type, len(class_names) if class_names else 0)

        for page in [self.camera_page, self.image_page, self.video_page]:
            if hasattr(page, 'detection_params'):
                page.detection_params.set_class_names(class_names)

        # 自动恢复模型时也启用图像页的检测按钮
        if hasattr(self.image_page, 'btn_detect'):
            self.image_page.btn_detect.setEnabled(True)

        if task_type == "segment":
            self.init_width_calculator()
            for page in [self.camera_page, self.image_page, self.video_page]:
                if hasattr(page, 'weld_params'):
                    page.weld_params.setVisible(True)
        else:
            for page in [self.camera_page, self.image_page, self.video_page]:
                if hasattr(page, 'weld_params'):
                    page.weld_params.setVisible(False)

        self._save_settings()
        self.model_loaded_signal.emit(model, info, class_names)
        self.status_message.emit("模型加载完成")

    def handle_model_load_failed(self, error_msg):
        self.sidebar.set_model_error()
        self._header_status.set_error("加载失败")
        self.status_message.emit(f"加载失败: {error_msg}")

    # ═══════════════════════════════════════════════════
    #  工厂报警
    # ═══════════════════════════════════════════════════

    def set_alarm_state(self, state, message=""):
        """设置大屏报警条状态（防重复刷新）

        Args:
            state: "ok" / "defect" / "idle"
            message: 状态栏报警文字
        """
        # 状态未变则跳过，避免每帧重复更新 UI
        if hasattr(self, '_last_alarm_state') and self._last_alarm_state == state:
            return
        self._last_alarm_state = state

        colors = {
            "ok": "#3fb950",
            "defect": "#f85149",
            "idle": "#30363d",
        }
        color = colors.get(state, "#30363d")
        # 用 palette 改背景色，避免 setStyleSheet 触发全局样式重算造成卡顿
        palette = self._alarm_bar.palette()
        palette.setColor(self._alarm_bar.backgroundRole(), QColor(color))
        self._alarm_bar.setPalette(palette)

        if state == "defect":
            # 用 HTML 富文本变色，避免 setStyleSheet 开销
            self._status_alarm.setText(
                f"<span style='color:#f85149; font-weight:bold; font-size:14px;'>⚠ {message}</span>"
            )
            if self._sound_enabled:
                self._play_beep()
        elif state == "ok":
            self._status_alarm.setText(
                f"<span style='color:#3fb950; font-weight:bold; font-size:13px;'>✓ {message}</span>"
            )
        else:
            self._status_alarm.setText("")

        # 更新 Dashboard 统计
        if state == "defect":
            self.today_defects += 1
            self._last_defect_time = datetime.now()
        self.today_total += 1

    def _play_beep(self):
        """播放报警音"""
        try:
            import winsound
            winsound.Beep(800, 200)
        except Exception:
            pass

    # ═══════════════════════════════════════════════════
    #  自动截图保存
    # ═══════════════════════════════════════════════════

    def auto_save_screenshot(self, annotated_image, source="detection"):
        """自动保存检测结果截图（后台线程，不阻塞UI）

        批次进行中时，保存到 批次名/ 子目录下。
        """
        if not self._auto_save or annotated_image is None:
            return

        save_dir = Path(self._auto_save_dir)
        # 批次进行中 → 按批次名创建子目录
        if self.batch_state.get("active") and self.batch_state.get("full_name"):
            batch_name = self.batch_state["full_name"]
            safe_name = batch_name.replace("/", "_").replace("\\", "_").replace(":", "_").replace(" ", "_")
            save_dir = save_dir / safe_name
        save_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:18]
        filename = f"{source}_{timestamp}.jpg"
        filepath = save_dir / filename

        # 后台线程写入，不卡 UI
        img_copy = annotated_image.copy()
        filepath_str = str(filepath)

        def _save():
            success = cv2.imwrite(filepath_str, img_copy)
            if success:
                self.status_message.emit(f"截图已保存: {filename}")
            else:
                self.status_message.emit(f"截图保存失败: {filename}")

        threading.Thread(target=_save, daemon=True).start()

    # ═══════════════════════════════════════════════════
    #  检测日志
    # ═══════════════════════════════════════════════════

    def log_detection(self, results, source="摄像头", frame_idx=0, batch_name=""):
        self.log_page.add_detection_record(results, source, frame_idx, batch_name)

    # ═══════════════════════════════════════════════════
    #  V5 批次管理
    # ═══════════════════════════════════════════════════

    @staticmethod
    def is_defect_class(cls_name: str) -> bool:
        """判断是否为真实缺陷（Good_Weld 不算缺陷，其他都是缺陷）"""
        return cls_name.strip().lower() != "good_weld"

    def start_batch(self, batch_info: dict):
        """开始一个新批次

        Args:
            batch_info: BatchNameDialog.get_result() 返回的字典
        """
        self.batch_state = {
            "active": True,
            "batch_name": batch_info.get("batch_name", ""),
            "full_name": batch_info.get("full_name", ""),
            "part_name": batch_info.get("part_name", ""),
            "total_images": 0,
            "total_defects": 0,
            "defect_details": [],
        }
        self.status_message.emit(f"📦 批次开始: {batch_info.get('full_name', '')}")

    def record_batch_defect(self, image_path, class_ids, confs, names_dict):
        """在批次中记录缺陷（Good_Weld 不计为缺陷）

        Args:
            image_path: 图片路径
            class_ids: 检测到的类别ID列表
            confs: 置信度列表
            names_dict: model.names 字典
        """
        if not self.batch_state["active"]:
            return

        self.batch_state["total_images"] += 1

        # 仅统计非 Good_Weld 的真实缺陷
        if class_ids is not None and len(class_ids) > 0:
            real_defects = 0
            for i in range(len(class_ids)):
                cls_name = names_dict.get(int(class_ids[i]), f"类别{class_ids[i]}")
                if self.is_defect_class(cls_name):
                    real_defects += 1
                    self.batch_state["defect_details"].append(
                        (str(image_path), cls_name, float(confs[i]))
                    )
            self.batch_state["total_defects"] += real_defects

    def finalize_batch(self) -> dict:
        """结束当前批次，生成汇总结果

        Returns:
            dict: 批次汇总，包含 passed (bool), summary 等信息
        """
        state = self.batch_state
        passed = state["total_defects"] == 0

        summary = {
            "batch_name": state["batch_name"],
            "full_name": state["full_name"],
            "part_name": state["part_name"],
            "total_images": state["total_images"],
            "total_defects": state["total_defects"],
            "passed": passed,
            "defect_details": list(state["defect_details"]),
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        # 保存到历史
        self.batch_history.append(summary)

        # 写入日志
        if hasattr(self, 'log_page') and self.log_page is not None:
            self.log_page.add_batch_record(summary)

        # 重置批次状态
        self.batch_state["active"] = False

        # 发射信号
        self.batch_finalized.emit(summary)

        return summary

    # ═══════════════════════════════════════════════════
    #  焊缝宽度
    # ═══════════════════════════════════════════════════

    def init_width_calculator(self):
        current_page = self.page_stack.currentWidget()
        wp = getattr(current_page, 'weld_params', None)
        if wp is None:
            wp = self.image_page.weld_params
        p = wp.get_params()
        if p["fx"] > 0 and p["distance"] > 0:
            self.width_calculator = WeldWidthCalculator(
                model_path=self.model_path or "bestforSEG.pt",
                fx=p["fx"], fy=p["fy"] if p["fy"] > 0 else p["fx"],
                working_distance=p["distance"], model=self.model,
            )
        else:
            self.width_calculator = None

    def compute_width(self, masks_data, orig_shape, method="pca"):
        if self.width_calculator is None:
            return None
        try:
            return self.width_calculator.compute_width_from_masks(masks_data, orig_shape, method=method)
        except Exception as e:
            self.status_message.emit(f"宽度计算失败: {str(e)}")
            return None

    def overlay_width(self, annotated_image, width_results):
        draw_width_overlay(annotated_image, width_results)

    # ═══════════════════════════════════════════════════
    #  状态栏
    # ═══════════════════════════════════════════════════

    def set_status(self, message, timeout=0):
        self._status_main.setText(message)

    def set_fps_display(self, fps=None, inference_time=None):
        if fps is not None and inference_time is not None:
            self._status_fps.setText(f"FPS: {fps:.1f} | {inference_time:.0f}ms")
        elif fps is not None:
            self._status_fps.setText(f"FPS: {fps:.1f}")
        else:
            self._status_fps.setText("")

    # ═══════════════════════════════════════════════════
    #  线程管理
    # ═══════════════════════════════════════════════════

    def set_detection_thread(self, t): self._detection_thread = t
    def set_camera_thread(self, t): self._camera_thread = t
    def set_video_thread(self, t): self._video_thread = t

    def cleanup_threads(self):
        for t in [self._detection_thread, self._camera_thread, self._video_thread]:
            if t and t.isRunning():
                t.requestInterruption()
                t.wait(3000)
        self._detection_thread = None
        self._camera_thread = None
        self._video_thread = None

    def closeEvent(self, event):
        # 检查是否有活动批次且存在未复核项（检查所有有复核面板的页面）
        if self.batch_state.get("active"):
            unjudged = 0
            for page in [self.camera_page, self.image_page]:
                rp = getattr(page, 'review_panel', None)
                if rp is not None:
                    unjudged += rp.get_unjudged_count()
            if unjudged > 0:
                reply = QMessageBox.warning(
                    self, "未完成复核",
                    f"当前批次还有 {unjudged} 个缺陷未完成复核，\n"
                    f"关闭程序将丢失复核数据。\n\n确定要关闭吗？",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No
                )
                if reply == QMessageBox.No:
                    event.ignore()
                    return

        self._scan_timer.stop()
        self._save_settings()
        self.cleanup_threads()
        super().closeEvent(event)


# ═══════════════════════════════════════════════════
#  启动入口
# ═══════════════════════════════════════════════════
def main():
    import sys
    app = QApplication(sys.argv)
    app.setApplicationName("西安汇丰-京博工业焊缝检测系统 v5")
    app.setFont(QFont("Microsoft YaHei", 9))

    window = WeldInspectionMainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
