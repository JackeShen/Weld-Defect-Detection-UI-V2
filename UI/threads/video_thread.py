"""视频文件检测线程"""

import time
import cv2
import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal, QMutex, QWaitCondition


class VideoProcessorThread(QThread):
    """视频播放 + 逐帧 YOLO 检测线程

    支持：播放/暂停/跳转/逐帧前进

    Signals:
        frame_processed: 帧处理完成 (frame_index, cv_img, results)
        progress: 播放进度 (current_frame, total_frames)
        playback_finished: 播放结束
        error: 错误信息
    """

    frame_processed = pyqtSignal(int, object, object)  # (idx, cv_img, results)
    progress = pyqtSignal(int, int)                     # (current, total)
    playback_finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, model, video_path, conf=0.25, iou=0.45, imgsz=640, parent=None):
        """
        Args:
            model: 已加载的 YOLO 模型
            video_path: 视频文件路径
            conf: 置信度阈值
            iou: IoU 阈值
            imgsz: 推理尺寸
        """
        super().__init__(parent)
        self._model = model
        self._video_path = video_path
        self._conf = conf
        self._iou = iou
        self._imgsz = imgsz

        # 控制
        self._mutex = QMutex()
        self._pause_condition = QWaitCondition()
        self._paused = False
        self._seek_to = -1
        self._step_forward = False  # 逐帧前进模式

        # 视频信息
        self.total_frames = 0
        self.fps = 0
        self.width = 0
        self.height = 0

    def pause(self):
        """暂停播放"""
        self._mutex.lock()
        self._paused = True
        self._mutex.unlock()

    def resume(self):
        """恢复播放"""
        self._mutex.lock()
        self._paused = False
        self._step_forward = False
        self._pause_condition.wakeAll()
        self._mutex.unlock()

    def seek(self, frame_idx):
        """跳转到指定帧"""
        self._mutex.lock()
        self._seek_to = frame_idx
        self._pause_condition.wakeAll()
        self._mutex.unlock()

    def step_forward(self):
        """逐帧前进一帧"""
        self._mutex.lock()
        self._step_forward = True
        self._paused = False
        self._pause_condition.wakeAll()
        self._mutex.unlock()

    def stop(self):
        """停止播放"""
        self.requestInterruption()
        self._mutex.lock()
        self._paused = False
        self._pause_condition.wakeAll()
        self._mutex.unlock()

    def run(self):
        cap = cv2.VideoCapture(self._video_path)
        if not cap.isOpened():
            self.error.emit(f"无法打开视频文件: {self._video_path}")
            return

        # 提取视频信息
        self.total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.fps = cap.get(cv2.CAP_PROP_FPS)
        self.width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        current_frame = 0

        while not self.isInterruptionRequested():
            # ── 处理暂停 ──
            self._mutex.lock()
            if self._paused and self._seek_to < 0:
                self._pause_condition.wait(self._mutex)
            self._mutex.unlock()

            # ── 处理跳转 ──
            self._mutex.lock()
            seek_target = self._seek_to
            self._seek_to = -1
            self._mutex.unlock()

            if seek_target >= 0:
                current_frame = min(seek_target, self.total_frames - 1)
                cap.set(cv2.CAP_PROP_POS_FRAMES, current_frame)

            # ── 逐帧前进后重新暂停 ──
            was_step = self._step_forward
            if was_step:
                self._step_forward = False

            # ── 读取帧 ──
            if current_frame >= self.total_frames:
                self.playback_finished.emit()
                break

            ret, frame = cap.read()
            if not ret:
                self.playback_finished.emit()
                break

            # ── 执行检测 ──
            try:
                results = self._model.predict(
                    source=frame.copy(),
                    conf=self._conf,
                    iou=self._iou,
                    imgsz=self._imgsz,
                    verbose=False,
                )
                r = results[0] if results else None
                annotated = r.plot(labels=True, conf=True, line_width=2) if r is not None else frame
            except Exception as e:
                self.error.emit(f"检测错误: {str(e)}")
                r = None
                annotated = frame

            # ── 发射结果 ──
            self.frame_processed.emit(current_frame, annotated, r)
            self.progress.emit(current_frame, self.total_frames)

            current_frame += 1

            # 逐帧模式：前进一帧后自动暂停
            if was_step:
                self._mutex.lock()
                self._paused = True
                self._mutex.unlock()

        cap.release()
