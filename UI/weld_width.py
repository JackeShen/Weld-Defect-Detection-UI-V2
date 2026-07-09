#!/usr/bin/env python3
"""
焊缝宽度测量脚本 - Weld Seam Width Measurement
==============================================

本脚本使用 YOLO 分割模型检测焊缝区域，通过后处理和相机内参
将像素宽度转换为实际物理宽度（毫米）。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
核心原理
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    width_mm = width_pixels × Z / fx

    其中:
    - Z  : 相机到工件表面的工作距离 (mm)
    - fx : 相机 x 方向焦距 (像素单位)，通过相机标定获得
    - width_pixels : mask 在焊缝法线方向上的像素跨度

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
测量算法 - PCA + 垂直切片法
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    1. 获取分割 mask 的所有前景像素坐标
    2. PCA 分析 → 主方向(焊缝方向) + 法线方向(宽度方向)
    3. 沿主方向切分 mask 为多个切片
    4. 每片内计算法线方向的像素跨度 = 局部宽度
    5. 统计: 均值、最大值、最小值、标准差
    6. 像素 → 毫米换算

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
使用方法
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    # 仅像素级宽度（无需相机参数）
    python weld_width.py --source weld.jpg --model bestforSEG.pt

    # 使用相机参数获取实际宽度(mm)
    python weld_width.py --source weld.jpg --model bestforSEG.pt \\
        --fx 2500 --fy 2500 --distance 300

    # 批量处理 + 可视化
    python weld_width.py --source images/ --model bestforSEG.pt \\
        --fx 2500 --fy 2500 --distance 300 --visualize --output results/

    # JSON 格式输出
    python weld_width.py --source weld.jpg --format json

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
相机参数获取说明
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    方法1: 直接标定（推荐）
        使用 OpenCV 棋盘格标定获取 fx, fy
        → 见 calibrate_camera() 函数

    方法2: 从传感器规格推算
        fx ≈ f_mm / pixel_size_mm
        其中 f_mm 是镜头焦距(mm)，pixel_size_mm 是像元尺寸(mm)

    方法3: 比例法
        放置已知尺寸的参照物，测量其像素尺寸，
        mm_per_pixel = 参照物实际尺寸 / 参照物像素尺寸

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

# ---------- 支持的图片格式 ----------
IMG_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


# ╔══════════════════════════════════════════════════════════════╗
# ║                    相机标定辅助函数                           ║
# ╚══════════════════════════════════════════════════════════════╝

def calibrate_camera(chessboard_dir: str,
                     pattern_size: tuple = (9, 6),
                     square_size_mm: float = 20.0) -> dict | None:
    """
    使用棋盘格图像进行相机标定，获取内参矩阵。

    Args:
        chessboard_dir: 棋盘格图像目录路径
        pattern_size: 棋盘格内角点数量 (列数, 行数)
        square_size_mm: 每格边长 (mm)

    Returns:
        dict: {"fx": ..., "fy": ..., "cx": ..., "cy": ..., "K": ..., "dist": ...}
        或 None（标定失败时）

    Example:
        >>> calib = calibrate_camera("chessboard_images/", (9, 6), 20.0)
        >>> print(f"fx={calib['fx']:.1f}, fy={calib['fy']:.1f}")
    """
    objp = np.zeros((pattern_size[0] * pattern_size[1], 3), np.float32)
    objp[:, :2] = np.mgrid[0:pattern_size[0], 0:pattern_size[1]].T.reshape(-1, 2)
    objp *= square_size_mm

    obj_points, img_points = [], []
    image_dir = Path(chessboard_dir)
    images = sorted([p for p in image_dir.iterdir()
                     if p.suffix.lower() in IMG_EXTENSIONS])

    if not images:
        print(f"✗ 在 {chessboard_dir} 中未找到图片")
        return None

    print(f"正在标定相机，使用 {len(images)} 张棋盘格图像...")

    h, w = 0, 0
    for img_path in images:
        img = cv2.imread(str(img_path))
        if img is None:
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape
        ret, corners = cv2.findChessboardCorners(gray, pattern_size, None)
        if ret:
            corners_sub = cv2.cornerSubPix(
                gray, corners, (11, 11), (-1, -1),
                (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001))
            obj_points.append(objp)
            img_points.append(corners_sub)
            print(f"  ✓ {img_path.name}")

    if len(obj_points) < 3:
        print(f"✗ 有效棋盘格图像不足 (需要 ≥3, 实际 {len(obj_points)})")
        return None

    ret, K, dist, rvecs, tvecs = cv2.calibrateCamera(
        obj_points, img_points, (w, h), None, None)

    if not ret:
        print("✗ 标定失败")
        return None

    fx, fy = K[0, 0], K[1, 1]
    cx, cy = K[0, 2], K[1, 2]

    print(f"\n✓ 标定完成")
    print(f"  焦距:  fx={fx:.2f} px,  fy={fy:.2f} px")
    print(f"  主点:  cx={cx:.2f} px,  cy={cy:.2f} px")
    print(f"  重投影误差: {ret:.4f} px")

    return {"fx": fx, "fy": fy, "cx": cx, "cy": cy,
            "K": K.tolist(), "dist": dist.tolist()}


# ╔══════════════════════════════════════════════════════════════╗
# ║                    焊缝宽度计算器                             ║
# ╚══════════════════════════════════════════════════════════════╝

class WeldWidthCalculator:
    """焊缝宽度计算器

    结合 YOLO 分割模型与相机内参，从图像中测量焊缝的实际物理宽度。

    Attributes:
        model: 加载的 YOLO 分割模型
        fx: x 方向焦距 (像素)
        fy: y 方向焦距 (像素)
        working_distance: 工作距离 (mm)
        mm_per_px_x: x 方向每像素对应物理尺寸 (mm/px)
        mm_per_px_y: y 方向每像素对应物理尺寸 (mm/px)
    """

    def __init__(self,
                 model_path: str = "bestforSEG.pt",
                 fx: float | None = None,
                 fy: float | None = None,
                 working_distance: float | None = None,
                 mm_per_px: float | None = None,
                 sensor_width_mm: float | None = None,
                 image_width_px: int | None = None,
                 focal_length_mm: float | None = None,
                 model=None):
        """
        初始化焊缝宽度计算器。

        支持多种相机参数指定方式（按优先级）:
            1. mm_per_px: 直接指定像素物理尺寸
            2. fx/fy + working_distance: 标定焦距 + 工作距离
            3. sensor_width_mm + image_width_px + focal_length_mm + working_distance:
               从传感器规格推算

        Args:
            model_path: YOLO 分割模型路径（model 参数为 None 时使用）
            fx: x 方向焦距 (像素)
            fy: y 方向焦距 (像素)，默认与 fx 相同
            working_distance: 相机到工件表面距离 (mm)
            mm_per_px: 每个像素对应的物理尺寸 (mm/px)
            sensor_width_mm: 传感器宽度 (mm)
            image_width_px: 图像宽度 (像素)
            focal_length_mm: 镜头焦距 (mm)
            model: 可选，已加载的 YOLO 模型实例（供 UI 等场景复用，避免重复加载）
        """
        # 延迟导入以便在无 ultralytics 环境时也能查看帮助
        from ultralytics import YOLO

        if model is not None:
            self.model = model
        else:
            self.model = YOLO(model_path)
        self.model_path = model_path
        self.fx = fx
        self.fy = fy if fy is not None else fx
        self.working_distance = working_distance
        self.mm_per_px_x: float | None = None
        self.mm_per_px_y: float | None = None

        # ---- 计算像素→毫米转换系数 ----
        if mm_per_px is not None:
            self.mm_per_px_x = mm_per_px
            self.mm_per_px_y = mm_per_px
        elif fx is not None and working_distance is not None:
            self.mm_per_px_x = working_distance / fx
            self.mm_per_px_y = working_distance / (fy if fy is not None else fx)
        elif (sensor_width_mm is not None and image_width_px is not None
              and focal_length_mm is not None and working_distance is not None):
            # fx_px = focal_length_mm / (sensor_width_mm / image_width_px)
            fx_px = focal_length_mm * image_width_px / sensor_width_mm
            self.mm_per_px_x = working_distance / fx_px
            self.mm_per_px_y = self.mm_per_px_x
        else:
            print("⚠ 未提供完整相机参数，将仅输出像素级宽度。")
            print("  使用 --fx/--fy + --distance 或 --pixel-size 获取 mm 结果。")

    # ──────────────────────────────────────────────
    #  内部方法
    # ──────────────────────────────────────────────

    @staticmethod
    def _extract_mask(result) -> np.ndarray | None:
        """从单个 YOLO Results 对象中提取第一个 mask 的二进制数组。

        Args:
            result: ultralytics Results 对象

        Returns:
            (H, W) binary numpy array 或 None
        """
        if result.masks is None or result.masks.data is None:
            return None
        masks = result.masks.data
        if isinstance(masks, np.ndarray):
            pass
        else:
            # torch Tensor
            masks = masks.cpu().numpy()
        if masks.shape[0] == 0:
            return None
        # 取第一个 mask 并二值化
        mask = masks[0]
        mask = (mask > 0.5).astype(np.uint8)
        if mask.sum() < 10:
            return None
        return mask

    @staticmethod
    def _compute_width_pca(mask: np.ndarray,
                           n_bins: int = 50) -> dict | None:
        """
        PCA + 垂直切片法测量焊缝宽度。

        算法步骤:
            1. 提取 mask 所有前景像素坐标
            2. 对坐标做 PCA，得到主方向（焊缝方向）和法线方向（宽度方向）
            3. 沿主方向将像素分为 n_bins 个切片
            4. 每片内计算法线方向投影的极差 = 局部宽度
            5. 使用 IQR 过滤异常值后统计

        Args:
            mask: 二值 mask (H, W)
            n_bins: 沿主方向的切片数量

        Returns:
            dict: {
                "mean_px": float,    # 平均像素宽度
                "min_px": float,     # 最小像素宽度
                "max_px": float,     # 最大像素宽度
                "std_px": float,     # 宽度标准差
                "median_px": float,  # 中位数像素宽度
                "all_widths_px": list[float],  # 所有局部宽度
                "principal_axis": np.ndarray,   # 主方向向量
                "normal_axis": np.ndarray,      # 法线方向向量
                "center": np.ndarray,           # mask 中心
                "angle_deg": float,             # 主方向角度
            }
            或 None（mask 像素不足时）
        """
        ys, xs = np.where(mask > 0)
        n_pixels = len(xs)

        if n_pixels < 20:
            return None

        coords = np.column_stack([xs.astype(np.float64),
                                  ys.astype(np.float64)])
        mean = coords.mean(axis=0)
        centered = coords - mean

        # PCA: 协方差矩阵的特征分解
        cov = np.cov(centered.T)
        eigenvalues, eigenvectors = np.linalg.eigh(cov)

        # 降序排列
        idx = np.argsort(eigenvalues)[::-1]
        eigenvectors = eigenvectors[:, idx]
        eigenvalues = eigenvalues[idx]

        principal_axis = eigenvectors[:, 0]   # 焊缝方向
        normal_axis = eigenvectors[:, 1]       # 宽度方向

        # 主方向角度（相对于水平线）
        angle_rad = np.arctan2(principal_axis[1], principal_axis[0])
        angle_deg = np.degrees(angle_rad)

        # 沿主方向投影
        projections = centered @ principal_axis
        sort_idx = np.argsort(projections)
        sorted_proj = projections[sort_idx]
        sorted_centered = centered[sort_idx]

        # 自适应 bin 数量
        actual_bins = min(n_bins, max(3, n_pixels // 5))
        bin_edges = np.linspace(sorted_proj.min(), sorted_proj.max(),
                                actual_bins + 1)

        widths_px = []
        for i in range(actual_bins):
            in_bin = (sorted_proj >= bin_edges[i]) & (sorted_proj < bin_edges[i + 1])
            if in_bin.sum() < 5:
                continue
            bin_coords = sorted_centered[in_bin]
            # 法线方向的投影值
            norm_proj = bin_coords @ normal_axis
            width = float(norm_proj.max() - norm_proj.min())
            if width > 0:
                widths_px.append(width)

        if len(widths_px) < 3:
            return None

        # IQR 过滤异常值
        widths_arr = np.array(widths_px)
        q1, q3 = np.percentile(widths_arr, [25, 75])
        iqr = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        filtered = widths_arr[(widths_arr >= lower) & (widths_arr <= upper)]

        if len(filtered) < 3:
            filtered = widths_arr

        return {
            "mean_px": float(np.mean(filtered)),
            "min_px": float(np.min(filtered)),
            "max_px": float(np.max(filtered)),
            "std_px": float(np.std(filtered)),
            "median_px": float(np.median(filtered)),
            "all_widths_px": [round(w, 2) for w in widths_px],
            "principal_axis": principal_axis,
            "normal_axis": normal_axis,
            "center": mean,
            "angle_deg": angle_deg,
            "n_bins_used": actual_bins,
            "n_filtered": len(filtered),
            "n_total": len(widths_px),
        }

    @staticmethod
    def _compute_width_dt(mask: np.ndarray) -> dict | None:
        """
        距离变换法测量焊缝宽度。

        对 mask 做距离变换，取骨架上的距离变换值 × 2 作为局部宽度估计。
        适合不规则形状的焊缝。

        Args:
            mask: 二值 mask (H, W)

        Returns:
            dict 或 None
        """
        # 距离变换
        dist = cv2.distanceTransform(mask, cv2.DIST_L2, 5)

        # 骨架化
        from ultralytics.data.converter import merge_multi_segment

        # 使用形态学细化获取骨架
        skeleton = _skeletonize(mask)

        # 取骨架上的距离值
        skeleton_dist = dist[skeleton > 0]
        if len(skeleton_dist) < 5:
            return None

        # 宽度 = 距离 × 2（距离是到最近边界的距离，即半宽）
        widths = skeleton_dist * 2

        # IQR 过滤
        q1, q3 = np.percentile(widths, [25, 75])
        iqr = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        filtered = widths[(widths >= lower) & (widths <= upper)]
        if len(filtered) < 3:
            filtered = widths

        return {
            "mean_px": float(np.mean(filtered)),
            "min_px": float(np.min(filtered)),
            "max_px": float(np.max(filtered)),
            "std_px": float(np.std(filtered)),
            "median_px": float(np.median(filtered)),
            "all_widths_px": [round(float(w), 2) for w in widths],
            "angle_deg": 0.0,  # DT 法不计算方向
        }

    def _pixels_to_mm(self, width_px: float) -> float | None:
        """将像素宽度转换为毫米。

        Args:
            width_px: 像素宽度

        Returns:
            毫米宽度，或 None（无相机参数时）
        """
        if self.mm_per_px_x is not None:
            return width_px * self.mm_per_px_x
        return None

    # ──────────────────────────────────────────────
    #  供外部 UI 调用的便捷方法
    # ──────────────────────────────────────────────

    def compute_width_from_masks(self,
                                 masks_data: "np.ndarray | torch.Tensor",
                                 orig_shape: tuple,
                                 method: str = "pca") -> dict | None:
        """
        从已有的 mask 数据计算焊缝宽度（供 UI 等已推理完毕的场景使用）。

        与 process_image() 的区别：本方法跳过模型推理步骤，直接对传入的
        mask tensor 进行宽度计算。适合 UI 中已有 YOLO Results 的场景。

        **重要：分辨率修正**
        YOLO 推理时会将图像缩放到 imgsz（如 640），mask 也是这个分辨率。
        但 fx 是原始分辨率标定的。本方法自动计算缩放比例进行修正：

            scale = max(orig_h / mask_h, orig_w / mask_w)
            width_original_px = width_mask_px * scale

        Args:
            masks_data: mask 张量，形状 (N, H_mask, W_mask)，已二值化
            orig_shape: 原始图像尺寸 (height, width)
            method: 测量方法 ("pca" | "dt")

        Returns:
            dict 或 None（无有效 mask 时）
        """
        import torch

        # 转为 numpy
        if isinstance(masks_data, torch.Tensor):
            masks_data = masks_data.cpu().numpy()

        if masks_data.ndim == 2:
            masks_data = masks_data[None, :]

        if masks_data.shape[0] == 0:
            return None

        # ── 计算分辨率缩放比例 ──
        mask_h, mask_w = masks_data.shape[1:3]
        orig_h, orig_w = orig_shape[:2]

        # YOLO 使用 LetterBox：保持宽高比，不足边填黑边
        # gain = min(mask_h/orig_h, mask_w/orig_w)，逆变换需要 1/gain
        gain = min(mask_h / orig_h, mask_w / orig_w)
        scale = 1.0 / gain if gain > 0 else 1.0
        # 例如: 1920→640, gain=0.333, scale=3.0 (每个mask像素=原图3像素)

        results = []
        for i in range(masks_data.shape[0]):
            mask = masks_data[i]
            mask_bin = (mask > 0.5).astype(np.uint8)
            if mask_bin.sum() < 10:
                continue

            if method == "dt":
                px_result = self._compute_width_dt(mask_bin)
            else:
                px_result = self._compute_width_pca(mask_bin)

            if px_result is None:
                continue

            # 将 mask 分辨率的像素宽度换算到原始图像分辨率
            scale_rounded = round(scale, 4)

            meas = {
                "weld_index": i + 1,
                "mean_width_px": round(px_result["mean_px"] * scale, 2),
                "min_width_px": round(px_result["min_px"] * scale, 2),
                "max_width_px": round(px_result["max_px"] * scale, 2),
                "std_width_px": round(px_result["std_px"] * scale, 2),
                "median_width_px": round(px_result["median_px"] * scale, 2),
                "angle_deg": round(px_result.get("angle_deg", 0), 1),
                "n_bins": px_result.get("n_bins_used", 0),
                "all_widths_px": [round(w * scale, 2) for w in px_result.get("all_widths_px", [])],
                "_mask": mask_bin,
                "_principal_axis": px_result.get("principal_axis"),
                "_normal_axis": px_result.get("normal_axis"),
                "_center": px_result.get("center"),
                "_scale_factor": scale_rounded,  # mask→原图缩放比
            }

            # 换算 mm（使用缩放到原图分辨率的像素宽度）
            if self.mm_per_px_x is not None:
                meas["mean_width_mm"] = round(self._pixels_to_mm(px_result["mean_px"] * scale), 3)
                meas["min_width_mm"] = round(self._pixels_to_mm(px_result["min_px"] * scale), 3)
                meas["max_width_mm"] = round(self._pixels_to_mm(px_result["max_px"] * scale), 3)
                meas["std_width_mm"] = round(self._pixels_to_mm(px_result["std_px"] * scale), 3)
                meas["median_width_mm"] = round(self._pixels_to_mm(px_result["median_px"] * scale), 3)
                meas["mm_per_px"] = round(self.mm_per_px_x, 6)

            results.append(meas)

        return results if results else None

    # ──────────────────────────────────────────────
    #  主处理方法
    # ──────────────────────────────────────────────

    def process_image(self,
                      image_path: str | Path,
                      conf: float = 0.5,
                      iou: float = 0.45,
                      method: str = "pca") -> dict:
        """
        处理单张图像，测量焊缝宽度。

        Args:
            image_path: 图像路径
            conf: 置信度阈值
            iou: IoU 阈值
            method: 测量方法 ("pca" | "dt")

        Returns:
            dict: {
                "image": str,           # 图像路径
                "image_size": (H, W),   # 图像尺寸
                "num_welds": int,       # 检测到的焊缝数量
                "measurements": list,   # 每个焊缝的测量结果
                "has_mm": bool,         # 是否有 mm 换算
            }
        """
        image_path = Path(image_path)
        img = cv2.imread(str(image_path))
        if img is None:
            return {"image": str(image_path), "error": "无法读取图像",
                    "num_welds": 0, "measurements": [], "has_mm": self.mm_per_px_x is not None}

        h, w = img.shape[:2]

        # YOLO 推理
        results = self.model.predict(
            source=str(image_path),
            conf=conf,
            iou=iou,
            verbose=False,
        )

        measurements = []
        for i, result in enumerate(results):
            mask = self._extract_mask(result)
            if mask is None:
                continue

            # 选择测量方法
            if method == "dt":
                px_result = self._compute_width_dt(mask)
            else:
                px_result = self._compute_width_pca(mask)

            if px_result is None:
                continue

            # 构建测量结果
            meas = {
                "weld_index": i + 1,
                "mean_width_px": round(px_result["mean_px"], 2),
                "min_width_px": round(px_result["min_px"], 2),
                "max_width_px": round(px_result["max_px"], 2),
                "std_width_px": round(px_result["std_px"], 2),
                "median_width_px": round(px_result["median_px"], 2),
                "angle_deg": round(px_result.get("angle_deg", 0), 1),
                "n_bins": px_result.get("n_bins_used", 0),
                "all_widths_px": px_result.get("all_widths_px", []),
            }

            # 换算 mm
            if self.mm_per_px_x is not None:
                meas["mean_width_mm"] = round(self._pixels_to_mm(px_result["mean_px"]), 3)
                meas["min_width_mm"] = round(self._pixels_to_mm(px_result["min_px"]), 3)
                meas["max_width_mm"] = round(self._pixels_to_mm(px_result["max_px"]), 3)
                meas["std_width_mm"] = round(self._pixels_to_mm(px_result["std_px"]), 3)
                meas["median_width_mm"] = round(self._pixels_to_mm(px_result["median_px"]), 3)
                meas["mm_per_px"] = round(self.mm_per_px_x, 6)

            # 附加信息用于可视化
            meas["_mask"] = mask
            meas["_principal_axis"] = px_result.get("principal_axis")
            meas["_normal_axis"] = px_result.get("normal_axis")
            meas["_center"] = px_result.get("center")

            measurements.append(meas)

        return {
            "image": str(image_path),
            "image_size": (h, w),
            "num_welds": len(measurements),
            "measurements": measurements,
            "has_mm": self.mm_per_px_x is not None,
        }

    def process_directory(self,
                          dir_path: str | Path,
                          conf: float = 0.5,
                          iou: float = 0.45,
                          method: str = "pca",
                          visualize: bool = False,
                          output_dir: str | Path | None = None) -> list[dict]:
        """
        批量处理目录中的所有图像。

        Args:
            dir_path: 图像目录路径
            conf: 置信度阈值
            iou: IoU 阈值
            method: 测量方法
            visualize: 是否生成可视化图像
            output_dir: 输出目录（默认与源目录相同）

        Returns:
            list[dict]: 每张图像的测量结果
        """
        dir_path = Path(dir_path)
        images = sorted([
            p for p in dir_path.iterdir()
            if p.suffix.lower() in IMG_EXTENSIONS
        ])

        if not images:
            print(f"✗ 在 {dir_path} 中未找到图片")
            return []

        print(f"找到 {len(images)} 张图片，开始处理...\n")

        all_results = []
        for idx, img_path in enumerate(images, 1):
            print(f"[{idx}/{len(images)}] {img_path.name} ... ", end="", flush=True)
            result = self.process_image(img_path, conf, iou, method)
            all_results.append(result)

            if "error" in result:
                print(f"✗ {result['error']}")
            else:
                n = result["num_welds"]
                print(f"✓ 检测到 {n} 条焊缝")

                if visualize and n > 0:
                    out_dir = Path(output_dir) if output_dir else dir_path
                    out_dir.mkdir(parents=True, exist_ok=True)
                    vis_path = out_dir / f"{img_path.stem}_width{img_path.suffix}"
                    self.visualize(result, str(vis_path))
                    print(f"    可视化保存至: {vis_path}")

        return all_results

    def visualize(self, result: dict, output_path: str) -> bool:
        """
        生成焊缝宽度可视化图像。

        在图像上叠加:
            - mask 半透明覆盖
            - 主方向（焊缝方向）箭头
            - 法线方向（宽度方向）箭头
            - 宽度标注文字

        Args:
            result: process_image() 返回的测量结果
            output_path: 输出图像路径

        Returns:
            bool: 是否成功
        """
        img = cv2.imread(result["image"])
        if img is None:
            return False

        overlay = img.copy()

        for meas in result["measurements"]:
            mask = meas.get("_mask")
            principal_axis = meas.get("_principal_axis")
            normal_axis = meas.get("_normal_axis")
            center = meas.get("_center")

            if mask is None:
                continue

            # ---- mask 半透明覆盖 ----
            colored_mask = np.zeros_like(img)
            colored_mask[mask > 0] = (0, 255, 128)  # 绿色
            overlay = cv2.addWeighted(overlay, 0.65, colored_mask, 0.35, 0)

            # ---- 中心点 ----
            if center is not None:
                cx, cy = int(center[0]), int(center[1])
                cv2.circle(overlay, (cx, cy), 5, (0, 0, 255), -1)

                # ---- 方向箭头 ----
                if principal_axis is not None and normal_axis is not None:
                    arrow_len = 80
                    # 主方向（焊缝方向）-- 蓝色
                    pa = principal_axis / np.linalg.norm(principal_axis)
                    end_principal = (int(cx + pa[0] * arrow_len),
                                     int(cy + pa[1] * arrow_len))
                    cv2.arrowedLine(overlay, (cx, cy), end_principal,
                                    (255, 0, 0), 2, tipLength=0.2)

                    # 法线方向（宽度方向）-- 红色
                    na = normal_axis / np.linalg.norm(normal_axis)
                    end_normal = (int(cx + na[0] * arrow_len),
                                  int(cy + na[1] * arrow_len))
                    cv2.arrowedLine(overlay, (cx, cy), end_normal,
                                    (0, 0, 255), 2, tipLength=0.2)

            # ---- 标注文字 ----
            mm_str = ""
            if "mean_width_mm" in meas:
                mm_str = f" | {meas['mean_width_mm']:.2f} mm"
            text = (f"焊缝 #{meas['weld_index']}: "
                    f"{meas['mean_width_px']:.1f} px{mm_str}")

            y_pos = 30 * meas["weld_index"]
            # 文字背景
            (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX,
                                          0.6, 2)
            cv2.rectangle(overlay, (8, y_pos - th - 8),
                          (8 + tw + 4, y_pos + 4), (0, 0, 0), -1)
            cv2.putText(overlay, text, (10, y_pos),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        (255, 255, 255), 2)

        cv2.imwrite(output_path, overlay)
        return True


# ╔══════════════════════════════════════════════════════════════╗
# ║                    辅助函数                                   ║
# ╚══════════════════════════════════════════════════════════════╝

def _skeletonize(mask: np.ndarray) -> np.ndarray:
    """
    对二值 mask 进行骨架化（形态学细化）。

    使用 Zhang-Suen 算法的 OpenCV 实现。

    Args:
        mask: 二值图像 (H, W)

    Returns:
        二值骨架图像 (H, W)
    """
    # OpenCV 的 ximgproc 模块提供了 thinning 函数
    try:
        skeleton = cv2.ximgproc.thinning(mask, thinningType=cv2.ximgproc.THINNING_ZHANGSUEN)
    except AttributeError:
        # 回退：使用形态学腐蚀的简单骨架化
        skeleton = np.zeros_like(mask)
        element = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
        temp = mask.copy()
        while True:
            eroded = cv2.erode(temp, element)
            dilated = cv2.dilate(eroded, element)
            skeleton = cv2.bitwise_or(skeleton, cv2.bitwise_and(temp, cv2.bitwise_not(dilated)))
            temp = eroded.copy()
            if cv2.countNonZero(temp) == 0:
                break
    return skeleton


def _is_image_file(path: Path) -> bool:
    """检查文件是否为支持的图片格式。"""
    return path.suffix.lower() in IMG_EXTENSIONS


def format_text_output(all_results: list[dict]) -> str:
    """格式化文本输出。"""
    lines = []
    sep = "=" * 60

    for result in all_results:
        lines.append(sep)
        lines.append(f"图片: {result['image']}")

        if "error" in result:
            lines.append(f"✗ 错误: {result['error']}")
            continue

        img_h, img_w = result["image_size"]
        lines.append(f"图像尺寸: {img_w} × {img_h} px")
        lines.append(f"检测到焊缝数量: {result['num_welds']}")
        lines.append("")

        for meas in result["measurements"]:
            idx = meas["weld_index"]
            lines.append(f"  焊缝 #{idx}:")
            lines.append(f"    平均值:  {meas['mean_width_px']:7.2f} px",)
            lines.append(f"    最小值:  {meas['min_width_px']:7.2f} px")
            lines.append(f"    最大值:  {meas['max_width_px']:7.2f} px")
            lines.append(f"    中位数:  {meas['median_width_px']:7.2f} px")
            lines.append(f"    标准差:  {meas['std_width_px']:7.2f} px")
            lines.append(f"    主方向角: {meas['angle_deg']:6.1f}°")

            if "mean_width_mm" in meas:
                lines.append(f"    ──────────────────────────")
                lines.append(f"    平均宽度(毫米): {meas['mean_width_mm']:.3f} mm")
                lines.append(f"    最小宽度(毫米): {meas['min_width_mm']:.3f} mm")
                lines.append(f"    最大宽度(毫米): {meas['max_width_mm']:.3f} mm")
                lines.append(f"    中位数(毫米):   {meas['median_width_mm']:.3f} mm")
                lines.append(f"    标准差(毫米):   {meas['std_width_mm']:.3f} mm")
                lines.append(f"    换算系数: 1 px = {meas['mm_per_px']:.4f} mm")

        lines.append("")

    lines.append(sep)
    lines.append(f"共处理 {len(all_results)} 张图片")
    total_welds = sum(r.get("num_welds", 0) for r in all_results)
    lines.append(f"共检测到 {total_welds} 条焊缝")
    lines.append(sep)

    return "\n".join(lines)


def format_json_output(all_results: list[dict]) -> str:
    """格式化 JSON 输出（去除内部可视化数据）。"""
    clean_results = []
    for result in all_results:
        clean = {
            "image": result["image"],
            "image_size": list(result.get("image_size", [])),
            "num_welds": result.get("num_welds", 0),
            "has_mm": result.get("has_mm", False),
        }
        if "error" in result:
            clean["error"] = result["error"]
        clean["measurements"] = []
        for meas in result.get("measurements", []):
            m = {k: v for k, v in meas.items() if not k.startswith("_")}
            clean["measurements"].append(m)
        clean_results.append(clean)

    return json.dumps(clean_results, ensure_ascii=False, indent=2)


# ╔══════════════════════════════════════════════════════════════╗
# ║                    CLI 入口                                   ║
# ╚══════════════════════════════════════════════════════════════╝

def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        description="焊缝宽度测量 - 基于 YOLO 分割 + 相机标定",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 仅像素宽度
  python weld_width.py --source weld.jpg

  # 使用相机参数获取实际宽度
  python weld_width.py --source weld.jpg --fx 2500 --distance 300

  # 批量处理 + 可视化
  python weld_width.py --source images/ --fx 2500 --distance 300 -v -o results/

  # JSON 输出
  python weld_width.py --source weld.jpg --fx 2500 --distance 300 --format json

  # 相机标定
  python weld_width.py --calibrate chessboard_images/ --pattern 9 6 --square 20
        """)

    # ── 主要参数 ──
    parser.add_argument("--source", "-s",
                        help="输入图像路径或目录")
    parser.add_argument("--model", "-m", default="bestforSEG.pt",
                        help="YOLO 分割模型路径 (默认: bestforSEG.pt)")

    # ── 相机参数 ──
    cam_group = parser.add_argument_group("相机参数")
    cam_group.add_argument("--fx", type=float,
                           help="x 方向焦距 (像素)")
    cam_group.add_argument("--fy", type=float,
                           help="y 方向焦距 (像素)，默认与 fx 相同")
    cam_group.add_argument("--distance", "-d", type=float,
                           help="相机到工件的工作距离 (mm)")
    cam_group.add_argument("--pixel-size", type=float,
                           help="每个像素的物理尺寸 (mm/px)，优先级高于 fx/distance")
    cam_group.add_argument("--sensor-width", type=float,
                           help="传感器宽度 (mm)，配合 --focal-length 和 --image-width 使用")
    cam_group.add_argument("--image-width", type=int,
                           help="图像宽度 (像素)")
    cam_group.add_argument("--focal-length", type=float,
                           help="镜头物理焦距 (mm)")

    # ── 推理参数 ──
    inf_group = parser.add_argument_group("推理参数")
    inf_group.add_argument("--conf", type=float, default=0.5,
                           help="置信度阈值 (默认: 0.5)")
    inf_group.add_argument("--iou", type=float, default=0.45,
                           help="IoU 阈值 (默认: 0.45)")
    inf_group.add_argument("--method", choices=["pca", "dt"], default="pca",
                           help="宽度测量方法: pca=PCA切片法, dt=距离变换法 (默认: pca)")
    inf_group.add_argument("--n-bins", type=int, default=50,
                           help="PCA方法的切片数量 (默认: 50)")

    # ── 输出参数 ──
    out_group = parser.add_argument_group("输出参数")
    out_group.add_argument("--visualize", "-v", action="store_true",
                           help="生成可视化图像")
    out_group.add_argument("--output", "-o", default=None,
                           help="输出目录")
    out_group.add_argument("--format", choices=["text", "json"], default="text",
                           help="输出格式 (默认: text)")
    out_group.add_argument("--save-report", action="store_true",
                           help="保存测量报告到文件")

    # ── 标定模式 ──
    calib_group = parser.add_argument_group("相机标定 (独立模式)")
    calib_group.add_argument("--calibrate",
                             help="棋盘格图像目录，进入相机标定模式")
    calib_group.add_argument("--pattern", type=int, nargs=2, default=[9, 6],
                             metavar=("COLS", "ROWS"),
                             help="棋盘格内角点数量 (默认: 9 6)")
    calib_group.add_argument("--square", type=float, default=20.0,
                             help="棋盘格方格边长 mm (默认: 20.0)")

    return parser.parse_args()


def main():
    args = parse_args()

    # ── 标定模式 ──
    if args.calibrate:
        calib = calibrate_camera(
            chessboard_dir=args.calibrate,
            pattern_size=tuple(args.pattern),
            square_size_mm=args.square,
        )
        if calib:
            print(f"\n在 weld_width.py 中使用以下参数:")
            print(f"  --fx {calib['fx']:.2f} --fy {calib['fy']:.2f}")
        return

    # ── 检查 source ──
    if not args.source:
        print("✗ 请指定 --source（图像路径或目录）")
        print("  使用 --help 查看更多信息")
        sys.exit(1)

    source = Path(args.source)

    # ── 初始化计算器 ──
    calculator = WeldWidthCalculator(
        model_path=args.model,
        fx=args.fx,
        fy=args.fy,
        working_distance=args.distance,
        mm_per_px=args.pixel_size,
        sensor_width_mm=args.sensor_width,
        image_width_px=args.image_width,
        focal_length_mm=args.focal_length,
    )

    # ── 处理 ──
    if source.is_file():
        all_results = [calculator.process_image(
            source, conf=args.conf, iou=args.iou, method=args.method)]
    elif source.is_dir():
        all_results = calculator.process_directory(
            source, conf=args.conf, iou=args.iou,
            method=args.method, visualize=args.visualize,
            output_dir=args.output)
    else:
        print(f"✗ 路径不存在: {source}")
        sys.exit(1)

    # ── 单张图片可视化 ──
    if args.visualize and source.is_file() and all_results:
        result = all_results[0]
        if result.get("num_welds", 0) > 0:
            out_dir = Path(args.output) if args.output else source.parent
            out_dir.mkdir(parents=True, exist_ok=True)
            vis_path = out_dir / f"{source.stem}_width{source.suffix}"
            calculator.visualize(result, str(vis_path))
            print(f"✓ 可视化保存至: {vis_path}")

    # ── 输出 ──
    if args.format == "json":
        output_str = format_json_output(all_results)
    else:
        output_str = format_text_output(all_results)

    print(output_str)

    # ── 保存报告 ──
    if args.save_report:
        out_dir = Path(args.output) if args.output else Path.cwd()
        out_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext = "json" if args.format == "json" else "txt"
        report_path = out_dir / f"weld_width_report_{timestamp}.{ext}"
        report_path.write_text(output_str, encoding="utf-8")
        print(f"\n✓ 报告已保存至: {report_path}")


if __name__ == "__main__":
    main()
