"""摄像头实时检测页面 v6 — 双栏布局 + 批次控制 + 摄像头常开"""

import time
from pathlib import Path
from collections import Counter

import cv2
import numpy as np
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame,
    QComboBox, QSpinBox, QSplitter, QMessageBox,
)
from PyQt5.QtCore import Qt, pyqtSignal

from ..widgets.model_panel import ModelPanel
from ..widgets.detection_params import DetectionParams
from ..widgets.weld_params import WeldParams
from ..widgets.result_panel import ResultPanel
from ..widgets.image_viewer import ImageViewer
from ..widgets.review_panel import ReviewPanel
from ..threads.camera_thread import CameraDetectionThread
from ..dialogs.batch_name_dialog import BatchNameDialog
from ..utils.review_store import (
    build_review_record, save_review_record, set_store_path,
    save_misjudgment_samples,
)


class CameraPage(QWidget):
    """摄像头实时检测页面 v6

    新设计：
        - 摄像头始终推流，不受批次启停影响
        - 左侧实时画面 + 右侧缺陷复核面板（水平双栏）
        - 明确的「开始批次」「结束批次」按钮
        - 复核不冻结画面
    """

    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window

        # ── 状态 ──
        self._is_streaming = False
        self._batch_active = False
        self._camera_thread: CameraDetectionThread | None = None
        self._last_frame = None
        self._last_defect_frame = None  # 最近一次有真实缺陷的标注帧

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
        title = QLabel("摄像头实时检测模式")
        title.setObjectName("pageTitle")
        top_bar.addWidget(title)

        subtitle = QLabel("摄像头常开，批次控制检测启停")
        subtitle.setObjectName("pageSubtitle")
        top_bar.addWidget(subtitle)
        top_bar.addStretch()

        layout.addLayout(top_bar)

        # ── 模型面板 ──
        self.model_panel = ModelPanel()
        layout.addWidget(self.model_panel)

        # ═══════════════════════════════════════════════
        #  顶部：批次控制条
        # ═══════════════════════════════════════════════
        batch_bar = QFrame()
        batch_bar.setObjectName("headerBar")
        batch_bar.setFixedHeight(56)
        batch_hl = QHBoxLayout(batch_bar)
        batch_hl.setContentsMargins(12, 6, 12, 6)
        batch_hl.setSpacing(12)

        batch_hl.addWidget(QLabel("📦 批次:"))
        self.batch_name_label = QLabel("未设置")
        self.batch_name_label.setStyleSheet(
            "color: #00d4ff; font-weight: bold; font-size: 14px;"
            "padding: 2px 8px; background: transparent;"
        )
        self.batch_name_label.setMinimumWidth(200)
        batch_hl.addWidget(self.batch_name_label)

        self.batch_status_label = QLabel("")
        self.batch_status_label.setStyleSheet(
            "color: #6e7681; font-size: 11px; padding: 2px 8px; background: transparent;"
        )
        batch_hl.addWidget(self.batch_status_label, stretch=1)

        self.btn_start_batch = QPushButton("▶  开始批次")
        self.btn_start_batch.setObjectName("actionBtn")
        self.btn_start_batch.setMinimumHeight(36)
        self.btn_start_batch.clicked.connect(self._start_batch_flow)
        batch_hl.addWidget(self.btn_start_batch)

        self.btn_end_batch = QPushButton("⏹  结束批次")
        self.btn_end_batch.setObjectName("stopBtn")
        self.btn_end_batch.setMinimumHeight(36)
        self.btn_end_batch.setEnabled(False)
        self.btn_end_batch.clicked.connect(self._end_batch_flow)
        batch_hl.addWidget(self.btn_end_batch)

        layout.addWidget(batch_bar)

        # ═══════════════════════════════════════════════
        #  画面区：摄像头 | 缺陷复核（水平分割，复核占 45%）
        # ═══════════════════════════════════════════════
        body_splitter = QSplitter(Qt.Horizontal)
        body_splitter.setHandleWidth(2)

        self.camera_viewer = ImageViewer()
        self.camera_viewer.setObjectName("cameraFeed")
        body_splitter.addWidget(self.camera_viewer)

        self.review_panel = ReviewPanel(show_complete_button=False)
        self.review_panel.setMinimumWidth(320)
        body_splitter.addWidget(self.review_panel)

        body_splitter.setStretchFactor(0, 11)   # 摄像头 ~55%
        body_splitter.setStretchFactor(1, 9)    # 复核 ~45%

        cam_outer = QWidget()
        cam_outer_layout = QVBoxLayout(cam_outer)
        cam_outer_layout.setContentsMargins(0, 0, 0, 0)
        cam_outer_layout.setSpacing(0)
        cam_outer_layout.addWidget(body_splitter, stretch=1)

        # FPS 信息条 + 摄像头开关
        fps_row = QHBoxLayout()
        self.fps_label = QLabel("FPS: --")
        self.fps_label.setStyleSheet(
            "color: #00d4ff; font-weight: bold; font-size: 13px;"
            "padding: 0 8px; background: transparent;"
        )
        fps_row.addWidget(self.fps_label)
        self.det_count_label = QLabel("检测: --")
        self.det_count_label.setStyleSheet(
            "color: #3fb950; font-size: 12px; background: transparent;"
        )
        fps_row.addWidget(self.det_count_label)
        self.stream_status_label = QLabel("摄像头未开启")
        self.stream_status_label.setStyleSheet(
            "color: #6e7681; font-size: 12px; background: transparent;"
        )
        fps_row.addWidget(self.stream_status_label)
        fps_row.addStretch()

        self.btn_camera_toggle = QPushButton("📷 打开摄像头")
        self.btn_camera_toggle.setObjectName("primaryBtn")
        self.btn_camera_toggle.setMinimumHeight(32)
        self.btn_camera_toggle.setMinimumWidth(130)
        self.btn_camera_toggle.clicked.connect(self._toggle_camera)
        fps_row.addWidget(self.btn_camera_toggle)

        cam_outer_layout.addLayout(fps_row)
        layout.addWidget(cam_outer, stretch=1)

        # ═══════════════════════════════════════════════
        #  底部：参数区（可折叠）
        # ═══════════════════════════════════════════════
        self._params_widget = QWidget()
        params_layout = QHBoxLayout(self._params_widget)
        params_layout.setContentsMargins(0, 4, 0, 0)
        params_layout.setSpacing(12)

        # 检测频率
        cadence_box = QHBoxLayout()
        cadence_box.addWidget(QLabel("每N帧检测:"))
        self.cadence_spin = QSpinBox()
        self.cadence_spin.setRange(1, 30)
        self.cadence_spin.setValue(5)
        self.cadence_spin.setFixedWidth(60)
        cadence_box.addWidget(self.cadence_spin)
        params_layout.addLayout(cadence_box)

        # 摄像头选择
        cam_box = QHBoxLayout()
        cam_box.addWidget(QLabel("摄像头:"))
        self.camera_combo = QComboBox()
        self.camera_combo.setMinimumWidth(120)
        cam_box.addWidget(self.camera_combo)
        btn_refresh_cam = QPushButton("刷新")
        btn_refresh_cam.clicked.connect(self._refresh_cameras)
        cam_box.addWidget(btn_refresh_cam)
        params_layout.addLayout(cam_box)

        params_layout.addStretch()

        # 折叠按钮
        self.btn_toggle_params = QPushButton("▲ 收起参数")
        self.btn_toggle_params.clicked.connect(self._toggle_params)
        params_layout.addWidget(self.btn_toggle_params)

        layout.addWidget(self._params_widget)

        # ── 可折叠的参数详情 ──
        self._detail_widget = QWidget()
        detail_layout = QHBoxLayout(self._detail_widget)
        detail_layout.setContentsMargins(0, 4, 0, 0)
        detail_layout.setSpacing(12)

        self.detection_params = DetectionParams()
        detail_layout.addWidget(self.detection_params)

        self.weld_params = WeldParams()
        self.weld_params.params_changed.connect(self._on_weld_params_changed)
        detail_layout.addWidget(self.weld_params)

        # 实时日志
        log_box = QVBoxLayout()
        log_box.addWidget(QLabel("日志:"))
        self.log_panel = ResultPanel()
        self.log_panel.setMaximumHeight(120)
        log_box.addWidget(self.log_panel)
        detail_layout.addLayout(log_box)

        self._params_expanded = True
        layout.addWidget(self._detail_widget)

    def _connect_signals(self):
        self.model_panel.model_loaded.connect(self._on_model_loaded)
        self.model_panel.model_load_failed.connect(self.mw.handle_model_load_failed)

    # ═══════════════════════════════════════════════════
    #  摄像头枚举
    # ═══════════════════════════════════════════════════

    def _refresh_cameras(self):
        """刷新可用摄像头列表"""
        self.camera_combo.clear()
        cameras = CameraDetectionThread.enumerate_cameras()
        if cameras:
            for cam in cameras:
                self.camera_combo.addItem(cam["name"], cam["index"])
        else:
            self.camera_combo.addItem("未检测到摄像头", -1)

    def _on_model_loaded(self, model, info, class_names):
        """模型加载完成"""
        self.mw.handle_model_loaded(model, info, class_names)
        self._refresh_cameras()
        self.mw.set_status("模型已加载 — 点击「开始批次」启动检测")

    # ═══════════════════════════════════════════════════
    #  摄像头推流（始终运行，与批次解耦）
    # ═══════════════════════════════════════════════════

    def _start_camera_stream(self):
        """启动摄像头推流（不开启检测）"""
        if self._is_streaming:
            return

        cam_index = self.camera_combo.currentData()
        if cam_index is None or cam_index < 0:
            self.stream_status_label.setText("⚠ 无可用摄像头，请点击刷新")
            self.stream_status_label.setStyleSheet(
                "color: #d2991d; font-size: 12px; background: transparent;"
            )
            return

        if self.mw.model is None:
            self.stream_status_label.setText("⚠ 请先加载模型")
            self.stream_status_label.setStyleSheet(
                "color: #d2991d; font-size: 12px; background: transparent;"
            )
            return

        params = self.detection_params.get_params()

        self._camera_thread = CameraDetectionThread(
            model=self.mw.model,
            camera_index=cam_index,
            conf=params["conf"],
            iou=params["iou"],
            imgsz=params["imgsz"],
            detect_every_n=self.cadence_spin.value(),
        )
        self._camera_thread.set_skip_inference(True)

        self._camera_thread.frame_ready.connect(self._on_frame_ready)
        self._camera_thread.detection_done.connect(self._on_detection_for_log)
        self._camera_thread.error.connect(self._on_camera_error)
        self._camera_thread.camera_disconnected.connect(self._on_camera_disconnected)

        self._camera_thread.start()
        self.mw.set_camera_thread(self._camera_thread)

        self._is_streaming = True
        self.stream_status_label.setText("● 摄像头已开启")
        self.stream_status_label.setStyleSheet(
            "color: #3fb950; font-size: 12px; background: transparent;"
        )
        self.btn_camera_toggle.setText("⏹ 关闭摄像头")
        self.btn_camera_toggle.setObjectName("stopBtn")
        self.btn_camera_toggle.style().unpolish(self.btn_camera_toggle)
        self.btn_camera_toggle.style().polish(self.btn_camera_toggle)

        self.log_panel.clear_results()
        self.log_panel.append("摄像头已开启，等待批次开始...")
        self.mw.set_status("摄像头已开启 — 点击「开始批次」启动检测")

    def _stop_camera_stream(self):
        """停止摄像头推流"""
        self._is_streaming = False

        # 如果批次还在进行，先结束
        if self._batch_active:
            self._end_batch_flow()

        if self._camera_thread and self._camera_thread.isRunning():
            self._camera_thread.requestInterruption()
            self._camera_thread.wait(3000)

        self._camera_thread = None
        self._last_frame = None
        self._last_defect_frame = None

        # 画面变黑
        black = np.zeros((480, 640, 3), dtype=np.uint8)
        self.camera_viewer.set_cv_image(black)

        self.fps_label.setText("FPS: --")
        self.det_count_label.setText("检测: --")
        self.stream_status_label.setText("摄像头已关闭")
        self.stream_status_label.setStyleSheet(
            "color: #6e7681; font-size: 12px; background: transparent;"
        )
        self.btn_camera_toggle.setText("📷 打开摄像头")
        self.btn_camera_toggle.setObjectName("primaryBtn")
        self.btn_camera_toggle.style().unpolish(self.btn_camera_toggle)
        self.btn_camera_toggle.style().polish(self.btn_camera_toggle)

        self.mw.set_alarm_state("idle")

    def _toggle_camera(self):
        """打开/关闭摄像头"""
        if self._is_streaming:
            self._stop_camera_stream()
        else:
            self._refresh_cameras()
            self._start_camera_stream()
            # 如果仍未能开启，弹窗提醒
            if not self._is_streaming:
                cam_index = self.camera_combo.currentData()
                if cam_index is None or cam_index < 0:
                    QMessageBox.warning(
                        self, "未检测到摄像头",
                        "未发现可用摄像头设备。\n\n"
                        "请确认摄像头已连接，然后点击「刷新」按钮重试。"
                    )
                elif self.mw.model is None:
                    QMessageBox.warning(
                        self, "模型未加载",
                        "请先在「模型配置」面板中加载 AI 模型，再打开摄像头。"
                    )

    # ═══════════════════════════════════════════════════
    #  批次控制
    # ═══════════════════════════════════════════════════

    def _start_batch_flow(self):
        """开始批次：弹命名框 → 启用检测 → 缺陷累积到右侧面板"""
        if self.mw.model is None:
            QMessageBox.warning(self, "提示", "请先加载模型")
            return

        if not self._is_streaming:
            QMessageBox.warning(
                self, "摄像头未开启",
                "请先点击「打开摄像头」按钮开启摄像头，再开始批次检测。"
            )
            return

        # 弹出批次命名对话框
        dialog = BatchNameDialog(self)
        if dialog.exec_() != BatchNameDialog.Accepted:
            return

        info = dialog.get_result()
        self.mw.start_batch(info)

        # 更新 UI
        self._batch_active = True
        self.batch_name_label.setText(f"📦 {info['full_name']}")
        self.batch_name_label.setStyleSheet(
            "color: #00d4ff; font-weight: bold; font-size: 13px;"
            "padding: 2px 6px; background: transparent;"
        )
        self.batch_status_label.setText("批次进行中 — 检测已开启")

        # 启用检测
        if self._camera_thread:
            self._camera_thread.set_skip_inference(False)

        # 按钮状态
        self.btn_start_batch.setEnabled(False)
        self.btn_end_batch.setEnabled(True)

        # 清空复核面板和上一批次的残留数据
        self.review_panel.reset()
        self._last_defect_frame = None

        self.log_panel.clear_results()
        self.log_panel.append(f"📦 批次开始: {info['full_name']}")
        self.mw.set_status(f"📦 批次检测中: {info['full_name']}")

    def _end_batch_flow(self):
        """结束批次：收集复核结果 → 保存 → 判定 → 停止检测"""
        if not self._batch_active:
            return

        # 检查是否有未复核项
        unjudged = self.review_panel.get_unjudged_count()
        if unjudged > 0:
            QMessageBox.warning(
                self, "未完成复核",
                f"还有 {unjudged} 个缺陷未完成复核，\n请复核完成后再结束批次。"
            )
            return

        # 收集复核结果
        review_results = self.review_panel.get_review_results()

        # 保存复核记录
        if review_results:
            batch_name = self.mw.batch_state.get("full_name", "unknown")
            safe_name = batch_name.replace("/", "_").replace("\\", "_").replace(":", "_").replace(" ", "_")
            set_store_path(Path(self.mw._auto_save_dir) / safe_name / "review_records.json")
            ai_summary = {
                "total": len(review_results),
                "batch_name": self.mw.batch_state.get("full_name", ""),
            }
            record = build_review_record(
                f"camera_batch@{int(time.time())}",
                ai_summary,
                review_results,
            )
            save_review_record(record)
            # 保存误判样本到 Misjudgment 目录（使用最近一次缺陷标注帧）
            if self._last_defect_frame is not None:
                batch_label = self.mw.batch_state.get("full_name", f"cam_{int(time.time())}")
                fp_count = save_misjudgment_samples(review_results, self._last_defect_frame.copy(), batch_label)
                if fp_count > 0:
                    self.log_panel.append(f"📁 已保存 {fp_count} 个误判样本到 Misjudgment/")

        # 结束批次 → 判定
        summary = self.mw.finalize_batch()
        self._show_batch_verdict(summary)

        # 日志记录
        verdict = "✅ 通过" if summary["passed"] else "🚨 不通过"
        self.log_panel.append(
            f"━━ 批次结束: {summary['full_name']} ━━\n"
            f"  判定: {verdict}  |  "
            f"检测帧: {summary['total_images']}  |  "
            f"缺陷: {summary['total_defects']} 处\n"
            f"  时间: {summary['time']}"
        )
        # 同步写入主窗口日志
        self.mw.log_page.add_batch_record(summary)

        # 重置状态
        self._batch_active = False
        self._last_defect_frame = None  # 释放内存
        self.review_panel.reset()

        # 关闭检测（摄像头继续推流）
        if self._camera_thread:
            self._camera_thread.set_skip_inference(True)

        # 恢复按钮
        self.btn_start_batch.setEnabled(True)
        self.btn_end_batch.setEnabled(False)
        self.batch_name_label.setText("未设置")
        self.batch_status_label.setText("")

        self.mw.set_alarm_state("idle")
        self.mw.set_status("批次已结束 — 点击「开始批次」进行下一批")

    def _show_batch_verdict(self, summary):
        """显示批次判定结果对话框"""
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
                f"摄像头实时检测未发现缺陷，产品质量合格。"
            )
        else:
            dlg.setIcon(QMessageBox.Critical)
            dlg.setText("🚨 这批物品检测不通过")
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

    # ═══════════════════════════════════════════════════
    #  帧处理（不冻结画面）
    # ═══════════════════════════════════════════════════

    def _on_frame_ready(self, cv_img, fps, num_det):
        """摄像头帧就绪 — 始终更新画面，不冻结"""
        if not self._is_streaming:
            return

        self._last_frame = cv_img

        # 始终更新实时画面
        self.camera_viewer.set_cv_image(cv_img)
        self.fps_label.setText(f"FPS: {fps:.1f}")
        self.det_count_label.setText(f"检测: {num_det} 个目标" if num_det > 0 else "检测: --")
        self.mw.set_fps_display(fps)

    def _on_detection_for_log(self, results, frame_idx):
        """检测到缺陷 → 写日志 + 报警 + 截图 + 追加到复核面板"""
        batch_name = self.mw.batch_state.get("full_name", "")
        self.mw.log_detection(results, "摄像头", frame_idx, batch_name)

        if isinstance(results, list) and len(results) > 0:
            r = results[0]
        else:
            r = results
        num_det = len(r.boxes) if r.boxes is not None else 0

        if num_det > 0 and self._batch_active:
            names = r.names or {}
            cls_ids = r.boxes.cls.cpu().numpy().astype(int)
            confs = r.boxes.conf.cpu().numpy()
            xyxy = r.boxes.xyxy.cpu().numpy()

            # 计算真实缺陷数量（排除 Good_Weld）
            real_defect_count = sum(
                1 for i in range(len(cls_ids))
                if self.mw.is_defect_class(names.get(int(cls_ids[i]), ""))
            )

            # V5: 记录缺陷到批次
            self.mw.record_batch_defect(
                f"摄像头帧#{frame_idx}", cls_ids, confs, names
            )
            self.batch_status_label.setText(
                f"已检测 {self.mw.batch_state['total_images']} 帧 | "
                f"累计缺陷 {self.mw.batch_state['total_defects']} 处"
            )

            # 生成标注图并保存（直接用 r.plot() 确保标注正确）
            if real_defect_count > 0:
                annotated_frame = r.plot(labels=True, conf=True, line_width=2)
                self._last_defect_frame = annotated_frame  # 保存用于误判
                self.mw.auto_save_screenshot(annotated_frame.copy(), f"cam_f{frame_idx}")
                frame_for_crop = annotated_frame
            else:
                frame_for_crop = None

            # 构建缺陷列表（含截图缩略图，排除 Good_Weld）
            if real_defect_count > 0:
                defects = []
                for i in range(len(cls_ids)):
                    cls_name = names.get(int(cls_ids[i]), f"未知{i}")
                    if not self.mw.is_defect_class(cls_name):
                        continue  # 跳过 Good_Weld

                    thumb = None
                    if frame_for_crop is not None:
                        x1, y1, x2, y2 = xyxy[i].astype(int)
                        h, w = frame_for_crop.shape[:2]
                        # 扩大裁切范围以便看清缺陷
                        pad_w = int((x2 - x1) * 0.3)
                        pad_h = int((y2 - y1) * 0.3)
                        cx1 = max(0, x1 - pad_w)
                        cy1 = max(0, y1 - pad_h)
                        cx2 = min(w, x2 + pad_w)
                        cy2 = min(h, y2 + pad_h)
                        crop = frame_for_crop[cy1:cy2, cx1:cx2]
                        if crop.size > 0:
                            from ..utils.image_conversion import cv_to_qpixmap
                            thumb = cv_to_qpixmap(crop)

                    defects.append({
                        "defect_index": i,
                        "cls_name": cls_name,
                        "cls_id": int(cls_ids[i]),
                        "confidence": float(confs[i]),
                        "bbox": xyxy[i].tolist(),
                        "thumb_pixmap": thumb,
                    })

                # 追加到复核面板（不清除已有缺陷）
                self.review_panel.append_defects(defects)

            if real_defect_count > 0:
                real_cls_names = [
                    names.get(int(c), "?") for c in cls_ids
                    if self.mw.is_defect_class(names.get(int(c), ""))
                ]
                self.mw.set_alarm_state(
                    "defect", f"{real_defect_count}个缺陷: {', '.join(real_cls_names[:3])} — 待复核"
                )
                self.mw.set_status(
                    f"⚠ 帧#{frame_idx}: {real_defect_count} 个缺陷 — 请在右侧面板复核"
                )
                self.log_panel.append(
                    f"🔍 帧#{frame_idx}: {real_defect_count}个缺陷 ({', '.join(real_cls_names[:3])})"
                )
            else:
                self.mw.set_alarm_state("ok", "正常（Good_Weld）")
        elif num_det == 0 and self._batch_active:
            self.mw.set_alarm_state("ok", "正常")

    def _on_camera_error(self, msg):
        """摄像头错误"""
        QMessageBox.critical(self, "摄像头错误", msg)
        self._stop_camera_stream()

    def _on_camera_disconnected(self):
        """摄像头断开"""
        self.log_panel.append("⚠ 摄像头已断开连接")
        self._stop_camera_stream()

    # ═══════════════════════════════════════════════════
    #  页面生命周期
    # ═══════════════════════════════════════════════════

    def on_page_entered(self):
        """页面被切换到当前页时调用 — 不做任何自动操作"""
        self.stream_status_label.setText("摄像头未开启 — 请点击「打开摄像头」")
        self.stream_status_label.setStyleSheet(
            "color: #6e7681; font-size: 12px; background: transparent;"
        )

    def on_page_left(self):
        """页面被切走时调用"""
        self._stop_camera_stream()

    # ═══════════════════════════════════════════════════
    #  其他
    # ═══════════════════════════════════════════════════

    def _on_weld_params_changed(self):
        """焊缝参数变化"""
        if self.mw.model and self.mw.model_task == "segment":
            self.mw.init_width_calculator()

    def _toggle_params(self):
        """展开/收起参数详情"""
        self._params_expanded = not self._params_expanded
        self._detail_widget.setVisible(self._params_expanded)
        if self._params_expanded:
            self.btn_toggle_params.setText("▲ 收起参数")
        else:
            self.btn_toggle_params.setText("▼ 展开参数")

    def update_class_filter(self, class_names):
        """更新类别过滤"""
        self.detection_params.set_class_names(class_names)
