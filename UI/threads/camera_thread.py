"""摄像头实时检测线程"""

import os
import time
import cv2
import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal


class CameraDetectionThread(QThread):
    """摄像头连续采集 + YOLO 检测线程

    循环：采集帧 → 每 N 帧执行一次 YOLO 推理 → 发射结果

    Signals:
        frame_ready: 处理后的帧就绪 (cv2 BGR image, fps float, detection_count int)
        stats_updated: 检测统计更新 (dict)
        error: 错误信息
        camera_disconnected: 摄像头断开
    """

    frame_ready = pyqtSignal(object, float, int)   # (cv_img, fps, num_detections)
    detection_done = pyqtSignal(object, int)        # (results, frame_number) — 供日志记录
    stats_updated = pyqtSignal(dict)
    error = pyqtSignal(str)
    camera_disconnected = pyqtSignal()

    def __init__(self, model, camera_index=0, conf=0.25, iou=0.45,
                 imgsz=640, detect_every_n=5, parent=None):
        """
        Args:
            model: 已加载的 YOLO 模型
            camera_index: OpenCV 摄像头索引（0=默认）
            conf: 置信度阈值
            iou: IoU 阈值
            imgsz: 推理尺寸
            detect_every_n: 每 N 帧执行一次检测（降低 CPU 占用）
        """
        super().__init__(parent)
        self._model = model
        self._camera_index = camera_index
        self._conf = conf
        self._iou = iou
        self._imgsz = imgsz
        self._detect_every_n = detect_every_n

        # 运行时状态
        self._last_results = None
        self._last_annotated = None
        self._skip_inference = False

    def set_detect_every_n(self, n):
        self._detect_every_n = max(1, n)

    def set_conf(self, conf):
        self._conf = conf

    def set_iou(self, iou):
        self._iou = iou

    def set_imgsz(self, imgsz):
        self._imgsz = imgsz

    def set_skip_inference(self, skip):
        """设为 True 时跳过 YOLO 推理，只显示原始帧（摄像头常开但批次未开始）"""
        self._skip_inference = skip

    def run(self):
        # 抑制 OpenCV DSHOW 后端错误输出
        os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")
        import sys as _sys
        _stderr = _sys.stderr
        try:
            with open(os.devnull, 'w') as devnull:
                _sys.stderr = devnull
                cap = cv2.VideoCapture(self._camera_index)
                if not cap.isOpened():
                    cap = cv2.VideoCapture(self._camera_index, cv2.CAP_DSHOW)
        finally:
            _sys.stderr = _stderr

        if not cap.isOpened():
            self.error.emit(f"无法打开摄像头 (索引 {self._camera_index})")
            return

        frame_count = 0
        fps = 0.0
        fps_start = time.time()
        fps_frames = 0

        while not self.isInterruptionRequested():
            ret, frame = cap.read()
            if not ret:
                self.camera_disconnected.emit()
                break

            frame_count += 1

            # ── 每 N 帧执行一次检测 ──
            if frame_count % self._detect_every_n == 0:
                if not self._skip_inference:
                    try:
                        results = self._model.predict(
                            source=frame.copy(),
                            conf=self._conf,
                            iou=self._iou,
                            imgsz=self._imgsz,
                            verbose=False,
                        )
                        if results and len(results) > 0:
                            r = results[0]
                            num_det = len(r.boxes) if r.boxes is not None else 0
                            self._last_results = r
                            self._last_annotated = r.plot(
                                labels=True, conf=True, line_width=2
                            )
                            if num_det > 0:
                                self.detection_done.emit(results, frame_count)
                        else:
                            num_det = 0
                            self._last_annotated = frame
                            self._last_results = None
                    except Exception as e:
                        self.error.emit(f"检测错误: {str(e)}")
                        self._last_annotated = frame
                        num_det = 0
                else:
                    # 跳过推理，只显示原始帧
                    self._last_annotated = frame
                    self._last_results = None
                    num_det = 0
            else:
                # 非检测帧：直接显示当前帧
                self._last_annotated = frame
                num_det = len(self._last_results.boxes) if (
                    self._last_results is not None
                    and self._last_results.boxes is not None
                ) else 0

            # ── FPS 计算 ──
            fps_frames += 1
            elapsed = time.time() - fps_start
            if elapsed >= 1.0:
                fps = fps_frames / elapsed
                fps_frames = 0
                fps_start = time.time()

            # 发射帧
            display_frame = self._last_annotated.copy() if self._last_annotated is not None else frame
            self.frame_ready.emit(display_frame, fps, num_det)

            # 短暂休眠以控制帧率
            self.msleep(10)

        cap.release()

    @staticmethod
    def enumerate_cameras(max_index=6):
        """枚举可用摄像头（静默模式，不打印 DSHOW 错误）"""
        import sys as _sys
        _stderr = _sys.stderr
        cameras = []
        try:
            with open(os.devnull, 'w') as devnull:
                _sys.stderr = devnull
                for i in range(max_index):
                    cap = cv2.VideoCapture(i)
                    if cap.isOpened():
                        name = f"摄像头 {i}"
                        try:
                            backend = cap.getBackendName() if hasattr(cap, 'getBackendName') else ""
                            name = f"摄像头 {i} ({backend})" if backend else name
                        except Exception:
                            pass
                        cameras.append({"index": i, "name": name})
                        cap.release()
                    else:
                        cap2 = cv2.VideoCapture(i, cv2.CAP_DSHOW)
                        if cap2.isOpened():
                            cameras.append({"index": i, "name": f"摄像头 {i} (DSHOW)"})
                            cap2.release()
        finally:
            _sys.stderr = _stderr
        return cameras
