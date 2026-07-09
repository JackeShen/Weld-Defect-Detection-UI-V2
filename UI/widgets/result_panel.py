"""检测结果显示面板"""

from collections import Counter

from PyQt5.QtWidgets import QTextEdit, QWidget, QVBoxLayout
from PyQt5.QtCore import Qt


class ResultPanel(QTextEdit):
    """结构化检测结果文本面板"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("resultPanel")
        self.setReadOnly(True)
        self.setMinimumWidth(280)
        self.setPlaceholderText("检测结果将在此显示...")

    def clear_results(self):
        """清空所有结果"""
        self.clear()

    def append_header(self, image_path, image_shape):
        """显示检测头部信息"""
        self.clear()
        self.append("═" * 50)
        self.append("  检 测 完 成！")
        self.append("═" * 50)
        self.append(f"  图片: {image_path}")
        self.append(f"  尺寸: {image_shape[1]} × {image_shape[0]}")
        self.append("")

    def append_header_with_verdict(self, image_path, image_shape, verdict_text):
        """显示检测头部信息 + OK/NG 判定"""
        self.clear()
        self.append("═" * 50)
        self.append(f"  检 测 完 成  —  {verdict_text}")
        self.append("═" * 50)
        self.append(f"  图片: {image_path}")
        self.append(f"  尺寸: {image_shape[1]} × {image_shape[0]}")
        self.append("")

    def append_speed(self, speed_dict):
        """显示推理速度"""
        if speed_dict:
            pre = speed_dict.get("preprocess", 0)
            inf = speed_dict.get("inference", 0)
            post = speed_dict.get("postprocess", 0)
            self.append(f"  推理速度: 预处理 {pre:.1f}ms | "
                        f"推理 {inf:.1f}ms | 后处理 {post:.1f}ms")
            self.append("")

    def append_class_stats(self, names_dict, class_ids, highlight_cls_id=None):
        """显示类别统计

        Args:
            names_dict: model.names 字典
            class_ids: 检测到的所有类别 ID 列表
            highlight_cls_id: 高亮标记的类别 ID（用于宽度测量目标）
        """
        if class_ids is None or len(class_ids) == 0:
            self.append("  未检测到任何目标")
            return

        counter = Counter(class_ids)
        self.append(f"  检测目标数: {len(class_ids)}")
        self.append("  类别统计:")
        for cls_id, count in counter.most_common():
            name = names_dict.get(int(cls_id), f"类别{int(cls_id)}")
            line = f"    - {name}: {count} 个"
            if highlight_cls_id is not None and int(cls_id) == highlight_cls_id:
                line += " ← 宽度测量"
            self.append(line)
        self.append("")

    def append_detection_details(self, result, names_dict):
        """显示每个检测目标的详细信息

        Args:
            result: ultralytics Results 对象
            names_dict: model.names 字典
        """
        boxes = result.boxes
        if boxes is None or len(boxes) == 0:
            return

        cls_ids = boxes.cls.cpu().numpy().astype(int)
        confs = boxes.conf.cpu().numpy()
        xyxy = boxes.xyxy.cpu().numpy()

        self.append("─" * 50)
        self.append("  目 标 详 情")
        self.append("─" * 50)

        for i in range(len(cls_ids)):
            name = names_dict.get(int(cls_ids[i]), f"类别{int(cls_ids[i])}")
            conf = confs[i]
            x1, y1, x2, y2 = xyxy[i]
            self.append(
                f"  [{i + 1}] {name} | "
                f"置信度: {conf:.2%} | "
                f"坐标: ({x1:.0f}, {y1:.0f}, {x2:.0f}, {y2:.0f})"
            )
        self.append("")

    def append_width_results(self, width_results):
        """显示焊缝宽度测量结果

        Args:
            width_results: WeldWidthCalculator 返回的测量列表
        """
        if not width_results:
            return

        self.append("═" * 50)
        self.append("  焊 缝 宽 度 测 量")
        self.append("═" * 50)

        for meas in width_results:
            idx = meas.get("weld_index", "?")
            self.append(f"  焊缝 #{idx}:")

            # 像素宽度
            self.append(f"    平均宽度: {meas.get('mean_width_px', 0):.1f} px")
            self.append(f"    最小/最大: {meas.get('min_width_px', 0):.1f} / "
                        f"{meas.get('max_width_px', 0):.1f} px")
            self.append(f"    标准差:   {meas.get('std_width_px', 0):.1f} px")
            self.append(f"    中位数:   {meas.get('median_width_px', 0):.1f} px")

            # 毫米宽度（如果可用）
            if "mean_width_mm" in meas:
                self.append(f"    ---")
                self.append(f"    平均宽度: {meas['mean_width_mm']:.3f} mm")
                self.append(f"    最小/最大: {meas['min_width_mm']:.3f} / "
                            f"{meas['max_width_mm']:.3f} mm")

            # 焊缝角度
            if "angle_deg" in meas:
                self.append(f"    焊缝角度: {meas['angle_deg']:.1f}°")

            self.append("")
