"""在检测结果图上叠加焊缝宽度可视化标注"""

import cv2
import numpy as np

from .chinese_text import put_chinese_text


def draw_width_overlay(annotated_image, width_results):
    """在检测结果图上叠加焊缝宽度可视化标注（原地修改）

    内容包括：绿色半透明掩码覆盖、黄色中心点、红色法线方向双箭头、
    蓝色主方向箭头、中文宽度标签。

    Args:
        annotated_image: OpenCV BGR 格式标注图 (numpy array)，原地修改
        width_results: WeldWidthCalculator.compute_width_from_masks() 返回的列表
    """
    if annotated_image is None or width_results is None:
        return

    overlay = annotated_image.copy()

    for meas in width_results:
        mask = meas.get("_mask")
        principal_axis = meas.get("_principal_axis")
        normal_axis = meas.get("_normal_axis")
        center = meas.get("_center")

        if mask is None:
            continue

        # ── 将 mask 缩放到与标注图相同尺寸 ──
        ov_h, ov_w = overlay.shape[:2]
        mask_h, mask_w = mask.shape[:2]
        sx = ov_w / mask_w if mask_w > 0 else 1.0
        sy = ov_h / mask_h if mask_h > 0 else 1.0
        if abs(sx - 1.0) > 0.001 or abs(sy - 1.0) > 0.001:
            mask_vis = cv2.resize(mask, (ov_w, ov_h), interpolation=cv2.INTER_NEAREST)
        else:
            mask_vis = mask

        # ── 绿色半透明 mask 覆盖 ──
        colored_mask = np.zeros_like(overlay, dtype=np.uint8)
        colored_mask[mask_vis > 0] = (0, 255, 128)
        overlay = cv2.addWeighted(overlay, 0.7, colored_mask, 0.3, 0)

        # ── 中心点（从 mask 坐标缩放到 overlay 坐标）──
        if center is not None:
            cx = int(center[0] * sx)
            cy = int(center[1] * sy)
            cv2.circle(overlay, (cx, cy), 6, (0, 255, 255), -1)
            cv2.circle(overlay, (cx, cy), 8, (0, 0, 0), 2)

            # ── 法线方向（宽度方向）红色双箭头 ──
            if normal_axis is not None:
                na = normal_axis / (np.linalg.norm(normal_axis) + 1e-8)
                arrow_len = min(120, max(40, meas.get("mean_width_px", 80) * 1.5 * sx))
                end1 = (int(cx + na[0] * arrow_len),
                        int(cy + na[1] * arrow_len))
                end2 = (int(cx - na[0] * arrow_len),
                        int(cy - na[1] * arrow_len))
                cv2.arrowedLine(overlay, (cx, cy), end1,
                                (0, 0, 255), 2, tipLength=0.15)
                cv2.arrowedLine(overlay, (cx, cy), end2,
                                (0, 0, 255), 2, tipLength=0.15)

            # ── 主方向（焊缝方向）蓝色箭头 ──
            if principal_axis is not None:
                pa = principal_axis / (np.linalg.norm(principal_axis) + 1e-8)
                arrow_len = 100 * min(sx, sy)
                end_pa = (int(cx + pa[0] * arrow_len),
                          int(cy + pa[1] * arrow_len))
                cv2.arrowedLine(overlay, (cx, cy), end_pa,
                                (255, 128, 0), 3, tipLength=0.2)

        # ── 宽度标注文字（使用 PIL 支持中文）──
        idx = meas["weld_index"]
        if "mean_width_mm" in meas:
            label = (f"焊缝#{idx}: {meas['mean_width_px']:.1f}px "
                     f"| {meas['mean_width_mm']:.2f}mm")
        else:
            label = f"焊缝#{idx}: {meas['mean_width_px']:.1f}px"

        y_pos = 30 + 35 * (idx - 1)
        font_size = 18
        # 画背景矩形
        est_w = len(label) * font_size * 0.6
        est_h = font_size + 8
        cv2.rectangle(overlay, (6, y_pos - int(est_h)),
                      (6 + int(est_w) + 8, y_pos + 6), (0, 0, 0), -1)
        put_chinese_text(overlay, label, (10, y_pos - int(est_h) + 4),
                         font_size=font_size, color=(0, 255, 255))

    # 原地更新
    annotated_image[:] = overlay[:]
