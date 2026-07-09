"""在 OpenCV 图像上绘制中文文字（使用 PIL）"""

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


def put_chinese_text(img, text, org, font_size=20, color=(0, 255, 255)):
    """在 OpenCV 图像上绘制中文文字（使用 PIL）

    OpenCV 的 putText 不支持中文字符，此函数通过 PIL 渲染中文后
    贴回 OpenCV 图像。

    Args:
        img: OpenCV BGR 图像 (numpy array)，原地修改
        text: 要绘制的文本（支持中文）
        org: 文字左下角坐标 (x, y)
        font_size: 字号
        color: BGR 颜色元组
    """
    # OpenCV BGR → PIL RGB
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(img_rgb)
    draw = ImageDraw.Draw(pil_img)

    # 尝试加载中文字体
    font = None
    font_paths = [
        "C:/Windows/Fonts/msyh.ttc",       # 微软雅黑
        "C:/Windows/Fonts/simsun.ttc",      # 宋体
        "C:/Windows/Fonts/simhei.ttf",      # 黑体
        "C:/Windows/Fonts/msyhbd.ttc",      # 微软雅黑粗体
    ]
    for fp in font_paths:
        if Path(fp).exists():
            try:
                font = ImageFont.truetype(fp, font_size)
                break
            except Exception:
                continue

    # PIL 颜色是 RGB
    pil_color = (color[2], color[1], color[0])

    if font:
        draw.text(org, text, font=font, fill=pil_color)
    else:
        # 回退：无中文字体时用默认字体（可能显示为方框但不会崩溃）
        draw.text(org, text, fill=pil_color)

    # PIL RGB → OpenCV BGR
    img_bgr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    img[:] = img_bgr[:]
