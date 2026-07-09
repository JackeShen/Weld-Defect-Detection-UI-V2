"""视频文件检测页面 v5 — 批次管理"""

import cv2
import numpy as np
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame,
    QSlider, QSplitter, QFileDialog, QMessageBox, QApplication,
)
from PyQt5.QtCore import Qt

from ..widgets.model_panel import ModelPanel
from ..widgets.detection_params import DetectionParams
from ..widgets.weld_params import WeldParams
from ..widgets.result_panel import ResultPanel
from ..widgets.image_viewer import ImageViewer
from ..threads.video_thread import VideoProcessorThread
from ..dialogs.batch_name_dialog import BatchNameDialog


class VideoPage(QWidget):
    """视频检测页面

    功能：选择视频文件 → 播放/暂停/跳转 → 逐帧检测 → 导出结果视频
    """

    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window

        # 状态
        self._video_path = ""
        self._is_playing = False
        self._is_paused = False
        self._video_thread: VideoProcessorThread | None = None
        self._total_frames = 0
        self._current_frame_idx = 0
        self._annotated_frames = {}  # 缓存已处理的帧 {idx: cv_img}
        self._current_results = None

        self._init_ui()
        self._connect_signals()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        # ── 顶部标题栏 ──
        top_bar = QHBoxLayout()
        title = QLabel("视频检测模式")
        title.setObjectName("pageTitle")
        top_bar.addWidget(title)

        subtitle = QLabel("选择视频文件进行逐帧焊缝缺陷检测")
        subtitle.setObjectName("pageSubtitle")
        top_bar.addWidget(subtitle)
        top_bar.addStretch()

        layout.addLayout(top_bar)

        # ── 模型面板 ──
        self.model_panel = ModelPanel()
        layout.addWidget(self.model_panel)

        # ── 视频选择行 ──
        video_row = QHBoxLayout()
        video_row.addWidget(QLabel("视频文件:"))

        self.video_path_label = QLabel("未选择")
        self.video_path_label.setStyleSheet(
            "color: #6e7681; padding: 4px 8px; "
            "border: 1px solid #21262d; border-radius: 5px; background: #0d1117;"
        )
        video_row.addWidget(self.video_path_label, stretch=1)

        btn_browse_video = QPushButton("浏览...")
        btn_browse_video.clicked.connect(self._select_video)
        video_row.addWidget(btn_browse_video)

        layout.addLayout(video_row)

        # ── 内容分栏 ──
        splitter = QSplitter(Qt.Horizontal)

        # 左侧：视频画面
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.video_viewer = ImageViewer()
        self.video_viewer.setObjectName("cameraFeed")
        left_layout.addWidget(self.video_viewer)

        # ── 播放控制 ──
        ctrl_row = QHBoxLayout()

        self.btn_prev_frame = QPushButton("⏮ 上一帧")
        self.btn_prev_frame.clicked.connect(self._prev_frame)
        self.btn_prev_frame.setEnabled(False)
        ctrl_row.addWidget(self.btn_prev_frame)

        self.btn_play_pause = QPushButton("▶ 播放")
        self.btn_play_pause.setObjectName("actionBtn")
        self.btn_play_pause.setMinimumHeight(36)
        self.btn_play_pause.clicked.connect(self._toggle_play_pause)
        self.btn_play_pause.setEnabled(False)
        ctrl_row.addWidget(self.btn_play_pause)

        self.btn_next_frame = QPushButton("⏭ 下一帧")
        self.btn_next_frame.clicked.connect(self._next_frame)
        self.btn_next_frame.setEnabled(False)
        ctrl_row.addWidget(self.btn_next_frame)

        ctrl_row.addStretch()

        self.frame_label = QLabel("帧: -- / --")
        self.frame_label.setStyleSheet(
            "color: #00d4ff; font-size: 13px; font-weight: bold; padding: 0 12px; background: transparent;"
        )
        ctrl_row.addWidget(self.frame_label)

        left_layout.addLayout(ctrl_row)

        # ── 时间线滑块 ──
        slider_row = QHBoxLayout()
        self.timeline_slider = QSlider(Qt.Horizontal)
        self.timeline_slider.setRange(0, 100)
        self.timeline_slider.setValue(0)
        self.timeline_slider.sliderMoved.connect(self._on_slider_moved)
        self.timeline_slider.setEnabled(False)
        slider_row.addWidget(self.timeline_slider, stretch=1)
        left_layout.addLayout(slider_row)

        splitter.addWidget(left_widget)

        # 右侧：控制面板
        right_widget = QWidget()
        right_widget.setMaximumWidth(360)
        right_widget.setMinimumWidth(280)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_layout.setSpacing(8)

        # ── V5 批次名设置 ──
        batch_frame = QFrame()
        batch_frame.setStyleSheet(
            "QFrame { background: #0f1520; border: 1px solid #21262d; "
            "border-radius: 6px; padding: 8px; }"
        )
        batch_layout = QVBoxLayout(batch_frame)
        batch_layout.setContentsMargins(8, 6, 8, 6)
        batch_layout.setSpacing(4)

        batch_header = QHBoxLayout()
        batch_header.addWidget(QLabel("📦 当前批次:"))
        self.batch_name_label = QLabel("未设置")
        self.batch_name_label.setStyleSheet(
            "color: #00d4ff; font-weight: bold; font-size: 14px;"
            "padding: 2px 6px; background: transparent;"
        )
        batch_header.addWidget(self.batch_name_label, stretch=1)

        self.btn_set_batch = QPushButton("设置批次")
        self.btn_set_batch.setToolTip("点击设置本次检测的批次名称")
        self.btn_set_batch.clicked.connect(self._show_batch_dialog)
        batch_header.addWidget(self.btn_set_batch)
        batch_layout.addLayout(batch_header)

        self.batch_status_label = QLabel("")
        self.batch_status_label.setStyleSheet(
            "color: #6e7681; font-size: 12px; padding: 2px 0; background: transparent;"
        )
        batch_layout.addWidget(self.batch_status_label)
        right_layout.addWidget(batch_frame)

        # ── 检测参数 ──
        self.detection_params = DetectionParams()
        right_layout.addWidget(self.detection_params)

        # ── 焊缝参数 ──
        self.weld_params = WeldParams()
        self.weld_params.params_changed.connect(self._on_weld_params_changed)
        right_layout.addWidget(self.weld_params)

        # ── 导出按钮 ──
        self.btn_export = QPushButton("📹 导出检测视频")
        self.btn_export.setObjectName("primaryBtn")
        self.btn_export.setEnabled(False)
        self.btn_export.clicked.connect(self._export_video)
        right_layout.addWidget(self.btn_export)

        # ── 结果面板 ──
        self.result_panel = ResultPanel()
        right_layout.addWidget(self.result_panel, stretch=1)

        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, stretch=1)

    def _connect_signals(self):
        self.model_panel.model_loaded.connect(self._on_model_loaded)
        self.model_panel.model_load_failed.connect(self.mw.handle_model_load_failed)

    # ═══════════════════════════════════════════════════
    #  视频选择
    # ═══════════════════════════════════════════════════

    def _select_video(self):
        """选择视频文件"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择视频文件", "",
            "视频文件 (*.mp4 *.avi *.mov *.mkv *.wmv *.flv);;所有文件 (*)"
        )
        if not path:
            return

        # 用 OpenCV 读取元数据
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            QMessageBox.warning(self, "错误", f"无法打开视频文件:\n{path}")
            return

        self._total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()

        self._video_path = path
        self.video_path_label.setText(path)
        self.video_path_label.setStyleSheet(
            "color: #c9d1d9; padding: 4px 8px; "
            "border: 1px solid #30363d; border-radius: 5px; background: #0d1117;"
        )

        # 设置滑块范围
        self.timeline_slider.setRange(0, self._total_frames - 1)
        self.timeline_slider.setValue(0)
        self.timeline_slider.setEnabled(True)

        # 显示视频信息
        self.frame_label.setText(f"总帧数: {self._total_frames} | FPS: {fps:.1f}")
        self.result_panel.clear_results()
        self.result_panel.append(f"视频已加载")
        self.result_panel.append(f"分辨率: {width}×{height}")
        self.result_panel.append(f"总帧数: {self._total_frames}")
        self.result_panel.append(f"帧率: {fps:.2f} FPS")

        # 启用按钮
        self.btn_play_pause.setEnabled(True)
        self.btn_prev_frame.setEnabled(True)
        self.btn_next_frame.setEnabled(True)

        self.mw.set_status(f"视频已加载 — {self._total_frames} 帧, {fps:.1f} FPS")

    # ═══════════════════════════════════════════════════
    #  V5 批次管理
    # ═══════════════════════════════════════════════════

    def _show_batch_dialog(self):
        """弹出批次命名对话框"""
        dialog = BatchNameDialog(self)
        if dialog.exec_() == BatchNameDialog.Accepted:
            info = dialog.get_result()
            self.mw.start_batch(info)
            self.batch_name_label.setText(f"📦 {info['full_name']}")
            self.batch_name_label.setStyleSheet(
                "color: #00d4ff; font-weight: bold; font-size: 14px;"
                "padding: 2px 6px; background: transparent;"
            )
            self.batch_status_label.setText("批次已就绪 — 请点击「播放」开始检测")

    # ═══════════════════════════════════════════════════
    #  播放控制
    # ═══════════════════════════════════════════════════

    def _toggle_play_pause(self):
        """切换播放/暂停"""
        if not self._is_playing:
            self._start_playback()
        elif self._is_paused:
            self._resume_playback()
        else:
            self._pause_playback()

    def _start_playback(self):
        """开始播放（V5：自动检查批次）"""
        if self.mw.model is None:
            QMessageBox.warning(self, "提示", "请先加载模型")
            return
        if not self._video_path:
            QMessageBox.warning(self, "提示", "请先选择视频文件")
            return

        # V5: 检查是否有活动批次
        if not self.mw.batch_state["active"]:
            reply = QMessageBox.question(
                self, "未设置批次",
                "当前没有活动批次，是否现在设置？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if reply == QMessageBox.Yes:
                self._show_batch_dialog()
                if not self.mw.batch_state["active"]:
                    return
            else:
                return

        params = self.detection_params.get_params()

        self._video_thread = VideoProcessorThread(
            model=self.mw.model,
            video_path=self._video_path,
            conf=params["conf"],
            iou=params["iou"],
            imgsz=params["imgsz"],
        )

        self._video_thread.frame_processed.connect(self._on_frame_processed)
        self._video_thread.progress.connect(self._on_progress)
        self._video_thread.playback_finished.connect(self._on_playback_finished)
        self._video_thread.error.connect(self._on_video_error)

        # 如果需要从当前帧开始
        current_pos = self.timeline_slider.value()
        if current_pos > 0:
            self._video_thread.seek(current_pos)

        self._video_thread.start()
        self.mw.set_video_thread(self._video_thread)

        self._is_playing = True
        self._is_paused = False
        self.btn_play_pause.setText("⏸ 暂停")
        self.btn_play_pause.setObjectName("primaryBtn")
        self.btn_play_pause.style().unpolish(self.btn_play_pause)
        self.btn_play_pause.style().polish(self.btn_play_pause)

        self.result_panel.clear_results()
        self.result_panel.append("视频检测开始...")

        self.mw.sidebar.set_processing("视频检测中...")
        self.mw.set_status("视频检测运行中...")

    def _pause_playback(self):
        """暂停播放"""
        if self._video_thread:
            self._video_thread.pause()
        self._is_paused = True
        self.btn_play_pause.setText("▶ 继续")
        self.btn_play_pause.setObjectName("actionBtn")
        self.btn_play_pause.style().unpolish(self.btn_play_pause)
        self.btn_play_pause.style().polish(self.btn_play_pause)
        self.mw.sidebar.set_ready("已暂停")
        self.mw.set_status("视频已暂停")

    def _resume_playback(self):
        """继续播放"""
        if self._video_thread:
            self._video_thread.resume()
        self._is_paused = False
        self.btn_play_pause.setText("⏸ 暂停")
        self.btn_play_pause.setObjectName("primaryBtn")
        self.btn_play_pause.style().unpolish(self.btn_play_pause)
        self.btn_play_pause.style().polish(self.btn_play_pause)
        self.mw.sidebar.set_processing("视频检测中...")
        self.mw.set_status("视频检测运行中...")

    def _stop_playback(self):
        """停止播放（V5：结束时判定批次）"""
        self._is_playing = False
        self._is_paused = False

        if self._video_thread and self._video_thread.isRunning():
            self._video_thread.stop()
            self._video_thread.wait(3000)

        self._video_thread = None

        self.btn_play_pause.setText("▶ 播放")
        self.btn_play_pause.setObjectName("actionBtn")
        self.btn_play_pause.style().unpolish(self.btn_play_pause)
        self.btn_play_pause.style().polish(self.btn_play_pause)

        # V5: 批次判定
        if self.mw.batch_state["active"]:
            self._finalize_video_batch()

        self.mw.sidebar.set_ready()
        self.mw.set_status("视频检测已停止")

    def _finalize_video_batch(self):
        """结束视频检测批次并显示判定"""
        summary = self.mw.finalize_batch()

        dlg = QMessageBox(self)
        dlg.setWindowTitle("批次检测判定")
        dlg.setMinimumWidth(450)

        if summary["passed"]:
            dlg.setIcon(QMessageBox.Information)
            dlg.setText("✅ 这批物品检测通过")
            info_text = (
                f"批次: {summary['full_name']}\n"
                f"检测帧数: {summary['total_images']}\n"
                f"缺陷数量: 0\n\n"
                f"视频检测未发现缺陷，产品质量合格。"
            )
        else:
            dlg.setIcon(QMessageBox.Critical)
            dlg.setText("🚨 这批物品检测不通过")
            from collections import Counter
            defect_counter = Counter()
            for _, cls_name, _ in summary["defect_details"]:
                defect_counter[cls_name] += 1
            defect_lines = "\n".join(
                f"  · {name}: {cnt} 处" for name, cnt in defect_counter.most_common()
            )
            info_text = (
                f"批次: {summary['full_name']}\n"
                f"检测帧数: {summary['total_images']}\n"
                f"缺陷总数: {summary['total_defects']} 处\n\n"
                f"缺陷明细:\n{defect_lines}\n\n"
                f"⚠ 该批次存在缺陷，建议隔离处理或人工复检。"
            )

        dlg.setInformativeText(info_text)
        dlg.setStandardButtons(QMessageBox.Ok)
        dlg.exec_()

        # 重置批次UI
        self.batch_name_label.setText("未设置")
        self.batch_status_label.setText("")

    def on_page_left(self):
        """页面离开时：停止播放并保存批次数据"""
        if self._is_playing:
            self._stop_playback()

    def _prev_frame(self):
        """上一帧"""
        if self._video_thread and self._is_playing:
            target = max(0, self._current_frame_idx - 2)
            self._video_thread.seek(target)
        else:
            target = max(0, self.timeline_slider.value() - 1)
            self.timeline_slider.setValue(target)
            # 单帧处理
            self._process_single_frame(target)

    def _next_frame(self):
        """下一帧"""
        if self._video_thread and self._is_playing:
            self._video_thread.step_forward()
        else:
            target = min(self._total_frames - 1, self.timeline_slider.value() + 1)
            self.timeline_slider.setValue(target)
            self._process_single_frame(target)

    def _on_slider_moved(self, position):
        """拖动时间线滑块"""
        self._current_frame_idx = position
        self.frame_label.setText(f"帧: {position} / {self._total_frames}")

        if self._video_thread and self._is_playing:
            self._video_thread.seek(position)

    def _process_single_frame(self, frame_idx):
        """处理单帧（非播放模式下的逐帧查看）"""
        if self.mw.model is None or not self._video_path:
            return

        # 检查缓存
        if frame_idx in self._annotated_frames:
            self.video_viewer.set_cv_image(self._annotated_frames[frame_idx])
            return

        cap = cv2.VideoCapture(self._video_path)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        cap.release()

        if not ret:
            return

        params = self.detection_params.get_params()
        try:
            results = self.mw.model.predict(
                source=frame.copy(),
                conf=params["conf"],
                iou=params["iou"],
                imgsz=params["imgsz"],
                verbose=False,
            )
            r = results[0] if results else None
            annotated = r.plot(labels=True, conf=True, line_width=2) if r is not None else frame
        except Exception as e:
            annotated = frame

        self._annotated_frames[frame_idx] = annotated
        self.video_viewer.set_cv_image(annotated)
        self.frame_label.setText(f"帧: {frame_idx} / {self._total_frames}")

    # ═══════════════════════════════════════════════════
    #  帧处理回调
    # ═══════════════════════════════════════════════════

    def _on_frame_processed(self, frame_idx, cv_img, results):
        """播放模式下的帧处理完成"""
        self._current_frame_idx = frame_idx
        self._annotated_frames[frame_idx] = cv_img
        self.video_viewer.set_cv_image(cv_img)

        # 提取第一个 result 对象
        if isinstance(results, list):
            r = results[0] if len(results) > 0 else None
        else:
            r = results

        # 记录到日志 + 报警 + 截图 + V5批次
        if r is not None and r.boxes is not None and len(r.boxes) > 0:
            batch_name = self.mw.batch_state.get("full_name", "")
            self.mw.log_detection(results, "视频", frame_idx, batch_name)

            num_det = len(r.boxes)
            names = r.names or {}
            cls_ids = r.boxes.cls.cpu().numpy().astype(int)
            confs = r.boxes.conf.cpu().numpy()
            cls_names = [names.get(int(c), "?") for c in cls_ids]

            # 计算真实缺陷数量（排除 Good_Weld）
            real_defect_count = sum(
                1 for i in range(len(cls_ids))
                if self.mw.is_defect_class(names.get(int(cls_ids[i]), ""))
            )

            # V5: 记录缺陷到批次（始终调用以跟踪 total_images）
            self.mw.record_batch_defect(f"视频帧#{frame_idx}", cls_ids, confs, names)
            self.batch_status_label.setText(
                f"已检测 {self.mw.batch_state['total_images']} 帧 | "
                f"累计缺陷 {self.mw.batch_state['total_defects']} 处"
            )

            if real_defect_count > 0:
                real_cls_names = [
                    n for n in cls_names
                    if self.mw.is_defect_class(n)
                ]
                self.mw.set_alarm_state("defect", f"视频帧#{frame_idx}: {real_defect_count}个缺陷: {', '.join(real_cls_names[:3])}")

                # 仅在有真实缺陷时截图
                self.mw.auto_save_screenshot(cv_img.copy(), f"video_f{frame_idx}")
            else:
                # 仅检测到 Good_Weld，不记录为缺陷
                self.mw.set_alarm_state("ok", "正常（Good_Weld）")
        elif frame_idx % 5 == 0:
            self.mw.set_alarm_state("ok", "正常")

        # 更新结果面板（每10帧）
        if r is not None and frame_idx % 10 == 0:
            num_det = len(r.boxes) if r.boxes is not None else 0
            self.result_panel.clear_results()
            self.result_panel.append(f"帧 {frame_idx} / {self._total_frames}")
            self.result_panel.append(f"检测目标: {num_det} 个")

    def _on_progress(self, current, total):
        """播放进度更新"""
        self.timeline_slider.blockSignals(True)
        self.timeline_slider.setValue(current)
        self.timeline_slider.blockSignals(False)
        self.frame_label.setText(f"帧: {current} / {total}")

    def _on_playback_finished(self):
        """播放结束"""
        self._stop_playback()
        # V5: 批次判定已在 _stop_playback 中处理
        self.result_panel.append("\n视频检测完成！")
        self.btn_export.setEnabled(True)
        self.mw.set_status("视频检测完成")

    def _on_video_error(self, msg):
        """视频处理错误"""
        QMessageBox.critical(self, "视频错误", msg)
        self._stop_playback()

    # ═══════════════════════════════════════════════════
    #  导出
    # ═══════════════════════════════════════════════════

    def _export_video(self):
        """导出带检测标注的视频"""
        if not self._annotated_frames:
            QMessageBox.warning(self, "提示", "没有可导出的帧数据")
            return

        save_path, _ = QFileDialog.getSaveFileName(
            self, "导出检测视频",
            "output_detected.mp4",
            "MP4 (*.mp4);;AVI (*.avi)"
        )
        if not save_path:
            return

        # 获取原视频的 FPS 和尺寸
        cap = cv2.VideoCapture(self._video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps <= 0:
            fps = 30
        cap.release()

        # 使用第一帧的尺寸
        first_frame = next(iter(self._annotated_frames.values()))
        h, w = first_frame.shape[:2]

        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        writer = cv2.VideoWriter(save_path, fourcc, fps, (w, h))

        for i in range(self._total_frames):
            if i in self._annotated_frames:
                writer.write(self._annotated_frames[i])
            else:
                # 未处理的帧写黑帧
                writer.write(np.zeros((h, w, 3), dtype=np.uint8))

        writer.release()
        QMessageBox.information(
            self, "导出成功",
            f"检测视频已导出到:\n{save_path}\n\n"
            f"总帧数: {len(self._annotated_frames)} / {self._total_frames}"
        )

    # ═══════════════════════════════════════════════════
    #  其他
    # ═══════════════════════════════════════════════════

    def _on_model_loaded(self, model, info, class_names):
        """模型加载完成"""
        self.mw.handle_model_loaded(model, info, class_names)
        if self._video_path:
            self.btn_play_pause.setEnabled(True)
            self.btn_prev_frame.setEnabled(True)
            self.btn_next_frame.setEnabled(True)
        self.mw.set_status("模型已加载 — 请选择视频文件")

    def _on_weld_params_changed(self):
        """焊缝参数变化"""
        if self.mw.model and self.mw.model_task == "segment":
            self.mw.init_width_calculator()

    def update_class_filter(self, class_names):
        """更新类别过滤"""
        self.detection_params.set_class_names(class_names)
