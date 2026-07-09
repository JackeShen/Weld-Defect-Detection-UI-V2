"""图像检测页面 v5 — 批次管理 + YOLO 检测 + 焊缝宽度测量 + 人工复核"""

from pathlib import Path
from collections import Counter

import cv2
import numpy as np
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QSplitter, QMessageBox, QApplication, QFrame,
)
from PyQt5.QtCore import Qt, pyqtSignal

from ..widgets.model_panel import ModelPanel
from ..widgets.detection_params import DetectionParams
from ..widgets.weld_params import WeldParams
from ..widgets.result_panel import ResultPanel
from ..widgets.image_viewer import ImageViewer
from ..widgets.review_panel import ReviewPanel
from ..threads.detection_thread import DetectionThread
from ..utils.image_conversion import cv_to_qpixmap
from ..utils.review_store import (
    build_review_record, save_review_record, set_store_path,
    save_misjudgment_samples,
)
from ..dialogs.save_dataset_dialog import SaveAsDatasetDialog
from ..dialogs.batch_name_dialog import BatchNameDialog


class ImagePage(QWidget):
    """图像检测页面 v5

    批次管理流程：
        设置批次名 → 开始检测 → 检测完成 → 可换图继续 → 结束检测 → 判定通过/不通过
    """

    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window  # 主窗口引用，访问共享 model / width_calculator

        # 页面状态
        self.current_image: np.ndarray | None = None
        self.annotated_image: np.ndarray | None = None
        self.current_results = None
        self.width_results: list | None = None

        # V5 批次检测状态
        self._batch_just_started = False  # 标记：刚设置批次名，等待第一次检测
        self._review_done = False         # 复核是否完成

        # 线程引用
        self._detection_thread: DetectionThread | None = None

        self._init_ui()
        self._connect_signals()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        # ── 顶部标题栏 ──
        top_bar = QHBoxLayout()
        title = QLabel("图像检测模式")
        title.setObjectName("pageTitle")
        top_bar.addWidget(title)

        subtitle = QLabel("选择单张图片进行焊缝缺陷检测与宽度测量")
        subtitle.setObjectName("pageSubtitle")
        top_bar.addWidget(subtitle)
        top_bar.addStretch()

        btn_clear = QPushButton("清空结果")
        btn_clear.clicked.connect(self._clear_results)
        top_bar.addWidget(btn_clear)

        layout.addLayout(top_bar)

        # ── 模型面板 ──
        self.model_panel = ModelPanel()
        layout.addWidget(self.model_panel)

        # ── 内容分栏 ──
        splitter = QSplitter(Qt.Horizontal)

        # 左侧：图像查看器 + 结果面板（上下分栏）
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        # 图像和结果面板垂直分割
        v_splitter = QSplitter(Qt.Vertical)
        self.image_viewer = ImageViewer()
        v_splitter.addWidget(self.image_viewer)

        self.result_panel = ResultPanel()
        v_splitter.addWidget(self.result_panel)

        # 复核面板（检测到缺陷后显示）
        self.review_panel = ReviewPanel()
        self.review_panel.setMinimumHeight(160)
        v_splitter.addWidget(self.review_panel)
        self._v_splitter = v_splitter
        self._set_splitter_normal()

        left_layout.addWidget(v_splitter)

        # 图像切换按钮行
        btn_row = QHBoxLayout()
        self.btn_show_original = QPushButton("原始图像")
        self.btn_show_original.setCheckable(True)
        self.btn_show_original.setChecked(True)
        self.btn_show_original.clicked.connect(lambda: self._toggle_image("original"))
        btn_row.addWidget(self.btn_show_original)

        self.btn_show_result = QPushButton("检测结果")
        self.btn_show_result.setCheckable(True)
        self.btn_show_result.clicked.connect(lambda: self._toggle_image("result"))
        btn_row.addWidget(self.btn_show_result)

        btn_row.addStretch()

        self.btn_save = QPushButton("保存结果图")
        self.btn_save.setEnabled(False)
        self.btn_save.clicked.connect(self._save_result_image)
        btn_row.addWidget(self.btn_save)

        self.btn_save_dataset = QPushButton("保存为数据集")
        self.btn_save_dataset.setEnabled(False)
        self.btn_save_dataset.clicked.connect(self._save_as_dataset)
        btn_row.addWidget(self.btn_save_dataset)

        left_layout.addLayout(btn_row)
        splitter.addWidget(left_widget)

        # 右侧：控制面板（结果面板已移到左侧，这里只放参数）
        right_widget = QWidget()
        right_widget.setMaximumWidth(380)
        right_widget.setMinimumWidth(280)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_layout.setSpacing(8)

        # ── 图片选择 ──
        img_row = QHBoxLayout()
        img_row.addWidget(QLabel("图片路径:"))
        self.image_path_label = QLabel("未选择")
        self.image_path_label.setStyleSheet(
            "color: #6e7681; padding: 4px 8px; "
            "border: 1px solid #21262d; border-radius: 5px; background: #0d1117;"
        )
        self.image_path_label.setWordWrap(True)
        self.image_path_label.setMinimumWidth(120)
        img_row.addWidget(self.image_path_label, stretch=1)

        btn_browse_img = QPushButton("浏览...")
        btn_browse_img.clicked.connect(self._select_image)
        img_row.addWidget(btn_browse_img)

        right_layout.addLayout(img_row)

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
            "color: #00d4ff; font-weight: bold; font-size: 13px;"
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
            "color: #6e7681; font-size: 11px; padding: 2px 0; background: transparent;"
        )
        batch_layout.addWidget(self.batch_status_label)
        right_layout.addWidget(batch_frame)

        # ── 检测按钮 ──
        self.btn_detect = QPushButton("▶  开始检测")
        self.btn_detect.setObjectName("actionBtn")
        self.btn_detect.setEnabled(False)
        self.btn_detect.setMinimumHeight(40)
        self.btn_detect.clicked.connect(self._run_detection)
        right_layout.addWidget(self.btn_detect)

        # ── 检测参数 ──
        self.detection_params = DetectionParams()
        right_layout.addWidget(self.detection_params)

        # ── 焊缝参数 ──
        self.weld_params = WeldParams()
        self.weld_params.params_changed.connect(self._on_weld_params_changed)
        right_layout.addWidget(self.weld_params)

        right_layout.addStretch()

        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, stretch=1)

    def _connect_signals(self):
        """连接信号"""
        self.model_panel.model_loaded.connect(self._on_model_loaded)
        self.model_panel.model_load_failed.connect(self.mw.handle_model_load_failed)
        self.review_panel.review_completed.connect(self._on_review_done)

    def _set_splitter_review(self):
        self._v_splitter.setStretchFactor(0, 3)
        self._v_splitter.setStretchFactor(1, 1)
        self._v_splitter.setStretchFactor(2, 1)

    def _set_splitter_normal(self):
        self._v_splitter.setStretchFactor(0, 2)
        self._v_splitter.setStretchFactor(1, 1)
        self._v_splitter.setStretchFactor(2, 0)

    # ═══════════════════════════════════════════════════
    #  模型加载
    # ═══════════════════════════════════════════════════

    def _on_model_loaded(self, model, info, class_names):
        """模型加载完成"""
        self.mw.handle_model_loaded(model, info, class_names)
        self.btn_detect.setEnabled(True)
        self.mw.set_status("模型已加载 — 请选择图片")

    # ═══════════════════════════════════════════════════
    #  图片选择
    # ═══════════════════════════════════════════════════

    def _select_image(self):
        """选择待检测图片"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择图片",
            "",
            "图片文件 (*.jpg *.jpeg *.png *.bmp *.tif *.tiff);;所有文件 (*)"
        )
        if not path:
            return

        self.image_path_label.setText(path)
        self.image_path_label.setStyleSheet(
            "color: #c9d1d9; padding: 4px 8px; "
            "border: 1px solid #30363d; border-radius: 5px; background: #0d1117;"
        )

        # 读取并显示
        pixmap = cv_to_qpixmap(cv2.imread(path))
        if pixmap:
            self.current_image = cv2.cvtColor(cv2.imread(path), cv2.COLOR_BGR2RGB)
            self.image_viewer.set_pixmap(pixmap)
            self.btn_show_original.setChecked(True)
            self.btn_show_result.setChecked(False)

    # ═══════════════════════════════════════════════════
    #  V5 批次管理
    # ═══════════════════════════════════════════════════

    def _show_batch_dialog(self):
        """弹出批次命名对话框"""
        dialog = BatchNameDialog(self)
        if dialog.exec_() == BatchNameDialog.Accepted:
            info = dialog.get_result()
            self.mw.start_batch(info)
            self._batch_just_started = True
            self.batch_name_label.setText(f"📦 {info['full_name']}")
            self.batch_name_label.setStyleSheet(
                "color: #00d4ff; font-weight: bold; font-size: 13px;"
                "padding: 2px 6px; background: transparent;"
            )
            self.batch_status_label.setText("批次已就绪，请点击「开始检测」")
            self.btn_detect.setEnabled(self.mw.model is not None)
            self.mw.set_status(f"📦 批次已设定: {info['full_name']} — 请开始检测")

    def _end_batch(self):
        """结束当前批次，显示判定结果"""
        if not self.mw.batch_state["active"]:
            return

        # 检查是否有未复核项
        unjudged = self.review_panel.get_unjudged_count()
        if unjudged > 0:
            QMessageBox.warning(
                self, "未完成复核",
                f"还有 {unjudged} 个缺陷未完成复核，\n请复核完成后再结束批次。"
            )
            return

        # 如果复核已完成但没点"完成复核"，自动保存复核记录
        if not self._review_done and self.review_panel.get_unjudged_count() == 0:
            review_results = self.review_panel.get_review_results()
            if review_results:
                self._on_review_done(review_results)

        summary = self.mw.finalize_batch()

        # ── 弹出判定对话框 ──
        if summary["passed"]:
            self._show_verdict_dialog(True, summary)
        else:
            self._show_verdict_dialog(False, summary)

        # ── 重置 UI ──
        self._reset_batch_ui()

    def _show_verdict_dialog(self, passed, summary):
        """显示批次判定结果对话框"""
        dlg = QMessageBox(self)
        dlg.setWindowTitle("批次检测判定")
        dlg.setMinimumWidth(450)

        if passed:
            dlg.setIcon(QMessageBox.Information)
            dlg.setText("✅ 这批物品检测通过")
            info_text = (
                f"批次: {summary['full_name']}\n"
                f"检测图片: {summary['total_images']} 张\n"
                f"缺陷数量: 0\n\n"
                f"所有检测图片均未发现缺陷，产品质量合格。"
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
                f"检测图片: {summary['total_images']} 张\n"
                f"缺陷总数: {summary['total_defects']} 处\n\n"
                f"缺陷明细:\n{defect_lines}\n\n"
                f"⚠ 该批次存在缺陷，建议隔离处理或人工复检。"
            )

        dlg.setInformativeText(info_text)
        dlg.setStandardButtons(QMessageBox.Ok)
        dlg.exec_()

    def _reset_batch_ui(self):
        """重置批次相关 UI 到初始状态"""
        self.batch_name_label.setText("未设置")
        self.batch_name_label.setStyleSheet(
            "color: #00d4ff; font-weight: bold; font-size: 13px;"
            "padding: 2px 6px; background: transparent;"
        )
        self.batch_status_label.setText("")
        self.btn_detect.setText("▶  开始检测")
        self.btn_detect.setObjectName("actionBtn")
        self.btn_detect.setStyleSheet("")
        self.btn_detect.clicked.disconnect()
        self.btn_detect.clicked.connect(self._run_detection)
        self.btn_detect.setEnabled(self.mw.model is not None)

    # ═══════════════════════════════════════════════════
    #  检测
    # ═══════════════════════════════════════════════════

    def _run_detection(self):
        """启动检测（V5：需要先设置批次）"""
        if self.mw.model is None:
            QMessageBox.warning(self, "提示", "请先加载模型")
            return

        # 如果没有活动批次，提示先设置批次
        if not self.mw.batch_state["active"]:
            reply = QMessageBox.question(
                self, "未设置批次",
                "当前没有活动批次，是否现在设置？\n\n"
                "批次信息用于记录和追溯检测结果。",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if reply == QMessageBox.Yes:
                self._show_batch_dialog()
                if not self.mw.batch_state["active"]:
                    return
            else:
                return

        image_path = self.image_path_label.text()
        if not image_path or image_path == "未选择":
            QMessageBox.warning(self, "提示", "请先选择图片")
            return

        params = self.detection_params.get_params()

        self.btn_detect.setEnabled(False)
        self.btn_detect.setText("检测中...")
        self.mw.set_status("正在进行目标检测...")
        self.mw.sidebar.set_processing("检测中...")

        self._detection_thread = DetectionThread(
            model=self.mw.model,
            image_path=image_path,
            conf=params["conf"],
            iou=params["iou"],
            imgsz=params["imgsz"],
        )
        self._detection_thread.finished.connect(self._on_detection_finished)
        self._detection_thread.error.connect(self._on_detection_error)
        self._detection_thread.start()

        self.mw.set_detection_thread(self._detection_thread)

    def _on_detection_finished(self, results):
        """检测完成回调（V5：OK/NG判定 + 人工复核）"""
        self.current_results = results
        self._review_done = False

        if not results or len(results) == 0:
            self.result_panel.clear()
            self.result_panel.append("未检测到任何物体。")
            self.mw.set_status("检测完成 — 未发现目标")
            self.mw.sidebar.set_ready()
            self._switch_to_end_mode(0, {}, None, None)
            return

        r = results[0]

        # ── 获取带标注的图像 ──
        annotated = r.plot(labels=True, conf=True, line_width=2)
        self.annotated_image = annotated  # BGR

        # ── 类别过滤 ──
        boxes = r.boxes
        names = r.names if r.names else {}
        filter_class = self.detection_params.class_filter_combo.currentText()
        mask_indices = None
        target_cls_id = None

        if filter_class != "全部" and boxes is not None and len(boxes) > 0:
            for cid, cname in names.items():
                if str(cname) == filter_class:
                    target_cls_id = int(cid)
                    break
            if target_cls_id is not None:
                cls_arr = boxes.cls.cpu().numpy().astype(int)
                mask_indices = np.where(cls_arr == target_cls_id)[0]

        box_total = len(boxes) if boxes is not None else 0
        box_cls_ids = boxes.cls.cpu().numpy().astype(int) if boxes is not None and len(boxes) > 0 else []
        box_confs = boxes.conf.cpu().numpy() if boxes is not None and len(boxes) > 0 else []

        # 计算真实缺陷数量（排除 Good_Weld）
        real_defect_count = sum(
            1 for i in range(len(box_cls_ids))
            if self.mw.is_defect_class(names.get(int(box_cls_ids[i]), ""))
        )
        is_ok = real_defect_count == 0

        # ── 显示结果面板 + OK/NG 判定 ──
        self.result_panel.clear_results()
        verdict = "✅ 合格 (OK)" if is_ok else "⚠ 不合格 (NG)"
        self.result_panel.append_header_with_verdict(str(r.path), r.orig_shape, verdict)
        self.result_panel.append_speed(r.speed if hasattr(r, 'speed') else {})

        if boxes is not None and len(boxes) > 0:
            cls_ids = boxes.cls.cpu().numpy().astype(int)
            confs = boxes.conf.cpu().numpy()
            xyxy = boxes.xyxy.cpu().numpy()
            self.result_panel.append_class_stats(names, cls_ids, target_cls_id)
            self.result_panel.append_detection_details(r, names)

        # ═══════════════════════════════════════════════
        #  焊缝宽度计算
        # ═══════════════════════════════════════════════
        self.mw.init_width_calculator()
        self.width_results = None

        if (self.weld_params.is_enabled()
                and r.masks is not None
                and r.masks.data is not None
                and self.mw.width_calculator is not None):

            self.mw.set_status("正在计算焊缝宽度...")
            QApplication.processEvents()

            if mask_indices is not None:
                filtered_masks = r.masks.data[mask_indices]
            else:
                filtered_masks = r.masks.data

            method = self.weld_params.get_method()
            self.width_results = self.mw.compute_width(
                masks_data=filtered_masks,
                orig_shape=r.orig_shape,
                method=method,
            )

            if self.width_results:
                self.result_panel.append_width_results(self.width_results)
                self.mw.overlay_width(self.annotated_image, self.width_results)
            else:
                self.result_panel.append("\n⚠ 焊缝宽度测量失败：未提取到有效 mask 区域")
        elif self.weld_params.is_enabled() and r.masks is not None:
            self.result_panel.append(
                "\n⚠ 相机参数未完整设置，无法进行宽度测量"
            )
            self.result_panel.append(
                "  请在焊缝宽度测量面板中填入 fx、fy 和工作距离后重试"
            )

        # ── 显示结果图像 ──
        self._toggle_image("result")

        # ── V5: 记录缺陷到批次 ──
        image_path = self.image_path_label.text()
        self.mw.record_batch_defect(image_path, box_cls_ids, box_confs, names)

        msg = f"检测完成 — 共发现 {real_defect_count} 个缺陷"
        if self.width_results:
            msg += f"，测量了 {len(self.width_results)} 条焊缝宽度"
        self.mw.set_status(msg)

        # ── 人工复核入口（仅真实缺陷，排除 Good_Weld）──
        if real_defect_count > 0:
            defects = []
            for i in range(len(box_cls_ids)):
                cls_name = names.get(int(box_cls_ids[i]), f"未知{i}")
                if not self.mw.is_defect_class(cls_name):
                    continue  # 跳过 Good_Weld
                defects.append({
                    "defect_index": i,
                    "cls_name": cls_name,
                    "cls_id": int(box_cls_ids[i]),
                    "confidence": float(box_confs[i]),
                    "bbox": boxes.xyxy.cpu().numpy()[i].tolist(),
                })
            batch_name = self.mw.batch_state.get("full_name", "unknown")
            safe_name = batch_name.replace("/", "_").replace("\\", "_").replace(":", "_").replace(" ", "_")
            set_store_path(Path(self.mw._auto_save_dir) / safe_name / "review_records.json")
            self.review_panel.load_defects(defects)
            self._set_splitter_review()
            self.btn_save_dataset.setEnabled(False)  # 复核完才能保存数据集
            self.btn_save.setEnabled(True)
            self.mw.set_status(f"⚠ 检测到 {real_defect_count} 个缺陷 — 请进行人工复核")
            self.mw.set_alarm_state("defect", f"{real_defect_count}个缺陷 — 待复核")

            # 仅在有真实缺陷时保存截图
            self.mw.auto_save_screenshot(self.annotated_image, "image")
        else:
            self.review_panel.reset()
            self._set_splitter_normal()
            self._review_done = True
            self.btn_save.setEnabled(True)
            self.btn_save_dataset.setEnabled(True)
            self.mw.set_alarm_state("ok", "无缺陷")

        # ── V5: 切换到结束检测模式 ──
        self._switch_to_end_mode(real_defect_count, names, box_cls_ids, box_confs)

        self.mw.sidebar.set_ready()

    def _switch_to_end_mode(self, box_total, names, box_cls_ids=None, box_confs=None):
        """切换到「结束检测」按钮模式"""
        self.btn_detect.setEnabled(True)
        self.btn_detect.setText("⏹  结束检测")
        self.btn_detect.setObjectName("stopBtn")
        self.btn_detect.clicked.disconnect()
        self.btn_detect.clicked.connect(self._end_batch)

        # 更新批次状态标签
        bs = self.mw.batch_state
        self.batch_status_label.setText(
            f"已检测 {bs['total_images']} 张图 | "
            f"累计缺陷 {bs['total_defects']} 处 | "
            f"点击「结束检测」完成批次"
        )

    def _on_detection_error(self, msg):
        """检测出错"""
        self.btn_detect.setEnabled(True)
        # 恢复正确的按钮状态
        if self.mw.batch_state["active"]:
            self.btn_detect.setText("⏹  结束检测")
            self.btn_detect.setObjectName("stopBtn")
            self.btn_detect.clicked.disconnect()
            self.btn_detect.clicked.connect(self._end_batch)
        else:
            self.btn_detect.setText("▶  开始检测")
            self.btn_detect.setObjectName("actionBtn")
            self.btn_detect.clicked.disconnect()
            self.btn_detect.clicked.connect(self._run_detection)

        QMessageBox.critical(self, "检测失败", msg)
        self.mw.set_status(f"检测失败: {msg}")
        self.mw.sidebar.set_ready()

    # ═══════════════════════════════════════════════════
    #  图像切换
    # ═══════════════════════════════════════════════════

    def _toggle_image(self, mode):
        """切换原始图片 / 检测结果"""
        if mode == "original":
            self.btn_show_original.setChecked(True)
            self.btn_show_result.setChecked(False)
            if self.current_image is not None:
                self.image_viewer.set_cv_image(
                    cv2.cvtColor(self.current_image, cv2.COLOR_RGB2BGR)
                )
        else:
            self.btn_show_original.setChecked(False)
            self.btn_show_result.setChecked(True)
            if self.annotated_image is not None:
                self.image_viewer.set_cv_image(self.annotated_image)

    # ═══════════════════════════════════════════════════
    #  保存
    # ═══════════════════════════════════════════════════

    def _save_result_image(self):
        """保存检测结果图像"""
        if self.annotated_image is None:
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "保存检测结果图",
            "result.jpg",
            "JPEG (*.jpg *.jpeg);;PNG (*.png);;BMP (*.bmp)"
        )
        if path:
            # annotated_image 是 BGR 格式，直接保存
            cv2.imwrite(path, self.annotated_image)
            QMessageBox.information(self, "保存成功", f"已保存到:\n{path}")

    def _save_as_dataset(self):
        """打开保存为训练数据集对话框"""
        if self.current_results is None:
            QMessageBox.warning(self, "提示", "请先执行检测")
            return

        # 有缺陷未复核时提醒
        r = self.current_results[0]
        bt = len(r.boxes) if r.boxes is not None else 0
        if bt > 0 and not self._review_done:
            reply = QMessageBox.question(self, "提示",
                "检测到缺陷但尚未完成复核。\n建议先复核再保存。\n\n是否继续？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.Yes:
                return

        image_path = self.image_path_label.text()
        if not image_path or image_path == "未选择":
            QMessageBox.warning(self, "提示", "图片路径无效")
            return

        dialog = SaveAsDatasetDialog(self.current_results, image_path, self)
        dialog.exec_()

    # ═══════════════════════════════════════════════════
    #  人工复核
    # ═══════════════════════════════════════════════════

    def _on_review_done(self, review_results):
        """复核完成 → 保存记录 + 标注结果"""
        self._review_done = True

        r = self.current_results[0]
        ai_summary = {
            "total": len(r.boxes) if r.boxes is not None else 0,
            "orig_shape": list(r.orig_shape) if hasattr(r, 'orig_shape') else [],
            "image_path": str(r.path) if hasattr(r, 'path') else "",
        }
        path = self.image_path_label.text()
        if path == "未选择":
            path = ""
        record = build_review_record(path, ai_summary, review_results)
        save_review_record(record)
        # 保存误判样本（使用标注后的图像）
        batch_name = self.mw.batch_state.get("full_name", Path(path).stem)
        fp_count = save_misjudgment_samples(review_results, self.annotated_image, batch_name)
        if fp_count > 0:
            self.mw.set_status(f"📁 已保存 {fp_count} 个误判样本到 Misjudgment/")

        # 标注复核结果到图像
        self._annotate_review(review_results, r.names or {})

        self.btn_save_dataset.setEnabled(True)
        confirmed = sum(1 for rv in review_results if rv["human_judgment"] == "confirmed")
        fp = sum(1 for rv in review_results if rv["human_judgment"] == "ai_false_positive")
        self.mw.set_status(f"✅ 复核完成 — 确认:{confirmed} | AI误判:{fp}")
        self.mw.set_alarm_state("defect" if confirmed > 0 else "ok", f"确认{confirmed}/误判{fp}")
        self._toggle_image("result")

    def _annotate_review(self, review_results, names):
        """在标注图上标记复核结果"""
        if self.annotated_image is None:
            return
        r = self.current_results[0]
        boxes = r.boxes
        if boxes is None:
            return
        xyxy = boxes.xyxy.cpu().numpy()
        overlay = self.annotated_image.copy()
        for rv in review_results:
            idx = rv["defect_index"]
            if idx >= len(xyxy):
                continue
            x1, y1, x2, y2 = xyxy[idx].astype(int)
            if rv["human_judgment"] == "confirmed":
                cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 0, 255), 3)
                label = f"V {rv['cls_name']}"
                color = (0, 0, 255)
            else:
                label = f"X AI误判: {rv['cls_name']}"
                color = (0, 215, 255)
                self._dashed_rect(overlay, (x1, y1), (x2, y2), color, 2)
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
            y = max(th + 8, y1)
            cv2.rectangle(overlay, (x1, y - th - 6), (x1 + tw + 6, y + 4), (30, 30, 30), -1)
            cv2.putText(overlay, label, (x1 + 3, y - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)
        self.annotated_image = overlay

    @staticmethod
    def _dashed_rect(img, p1, p2, color, t=1, dl=8):
        x1, y1 = p1; x2, y2 = p2
        for (a, b) in [((x1,y1),(x2,y1)),((x2,y1),(x2,y2)),((x2,y2),(x1,y2)),((x1,y2),(x1,y1))]:
            d = np.linalg.norm(np.array(b) - np.array(a))
            n = max(1, int(d / (dl * 2)))
            for i in range(n):
                if i % 2 == 0:
                    t1, t2 = i / n, min(1, (i + 1) / n)
                    cv2.line(img, (int(a[0]+(b[0]-a[0])*t1), int(a[1]+(b[1]-a[1])*t1)),
                             (int(a[0]+(b[0]-a[0])*t2), int(a[1]+(b[1]-a[1])*t2)), color, t)

    # ═══════════════════════════════════════════════════
    #  清空
    # ═══════════════════════════════════════════════════

    def _clear_results(self):
        """清空检测结果"""
        self.current_results = None
        self.annotated_image = None
        self.width_results = None
        self._review_done = False
        self.image_viewer.clear()
        self.result_panel.clear_results()
        self.review_panel.reset()
        self._set_splitter_normal()
        self.btn_save.setEnabled(False)
        self.btn_save_dataset.setEnabled(False)
        self.btn_show_original.setChecked(True)
        self.btn_show_result.setChecked(False)
        self.mw.set_status("已清空结果")

    def _on_weld_params_changed(self):
        """焊缝参数变化时通知主窗口重建计算器"""
        if self.mw.model and self.mw.model_task == "segment":
            self.mw.init_width_calculator()

    def update_class_filter(self, class_names):
        """更新类别过滤下拉框"""
        self.detection_params.set_class_names(class_names)
