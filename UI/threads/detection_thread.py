"""单张图片检测线程 — 从 yolo_ui.py 迁移"""

from PyQt5.QtCore import QThread, pyqtSignal


class DetectionThread(QThread):
    """推理线程，避免阻塞 UI

    Signals:
        finished: 推理完成，携带 ultralytics Results 对象
        error: 推理失败，携带错误消息字符串
        progress: 进度信息
    """

    finished = pyqtSignal(object)        # ultralytics Results
    error = pyqtSignal(str)              # 错误消息
    progress = pyqtSignal(str)           # 进度信息

    def __init__(self, model, image_path, conf=0.25, iou=0.45, imgsz=640):
        """
        Args:
            model: 已加载的 YOLO 模型实例
            image_path: 图片文件路径
            conf: 置信度阈值
            iou: IoU 阈值
            imgsz: 推理图片尺寸
        """
        super().__init__()
        self._model = model
        self._image_path = image_path
        self._conf = conf
        self._iou = iou
        self._imgsz = imgsz

    def run(self):
        try:
            self.progress.emit("正在进行目标检测...")
            results = self._model.predict(
                source=self._image_path,
                conf=self._conf,
                iou=self._iou,
                imgsz=self._imgsz,
                verbose=False,
            )
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(f"推理失败: {str(e)}")
