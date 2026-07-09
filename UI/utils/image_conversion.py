"""OpenCV 图像 与 QPixmap 互转工具"""

import cv2
import numpy as np
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtCore import Qt, QSize


def cv_to_qpixmap(cv_img):
    """将 OpenCV 图像 (BGR numpy array) 转为 QPixmap

    Args:
        cv_img: OpenCV BGR 或灰度图像

    Returns:
        QPixmap 或 None（如果输入无效）
    """
    if cv_img is None:
        return None

    h, w = cv_img.shape[:2]
    ch = cv_img.shape[2] if cv_img.ndim == 3 else 1

    if ch == 3:
        rgb = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        bytes_per_line = 3 * w
        qt_img = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
    elif ch == 4:
        rgb = cv2.cvtColor(cv_img, cv2.COLOR_BGRA2RGBA)
        bytes_per_line = 4 * w
        qt_img = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGBA8888)
    else:
        bytes_per_line = w
        qt_img = QImage(cv_img.data, w, h, bytes_per_line, QImage.Format_Grayscale8)

    # .copy() 防止 data 被回收后 pixmap 变成野指针
    return QPixmap.fromImage(qt_img.copy())


def pixmap_to_cv(pixmap):
    """将 QPixmap 转为 OpenCV BGR 图像

    Args:
        pixmap: QPixmap

    Returns:
        numpy array (BGR) 或 None
    """
    if pixmap.isNull():
        return None

    q_img = pixmap.toImage()
    q_img = q_img.convertToFormat(QImage.Format_RGB888)

    w = q_img.width()
    h = q_img.height()
    ptr = q_img.bits()
    ptr.setsize(h * w * 3)
    arr = np.array(ptr).reshape((h, w, 3))
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def scale_pixmap(pixmap, target_size, keep_aspect=True):
    """缩放 QPixmap 到目标尺寸

    Args:
        pixmap: 原始 QPixmap
        target_size: QSize 目标尺寸
        keep_aspect: 是否保持宽高比

    Returns:
        缩放后的 QPixmap
    """
    if pixmap.isNull():
        return pixmap

    aspect_mode = Qt.KeepAspectRatio if keep_aspect else Qt.IgnoreAspectRatio
    return pixmap.scaled(target_size, aspect_mode, Qt.SmoothTransformation)
