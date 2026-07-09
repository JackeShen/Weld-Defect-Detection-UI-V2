"""复核记录持久化存储

对照技术方案 V1.0 §4.3 人工复核与模型矫正机制：
- AI判NG → 工人确认"不合格" → 正样本归档
- AI判NG → 工人确认"合格"   → 标记"AI误判"，用于模型优化
- 平台端定期汇总误判样本和低置信度样本（<75%）用于模型再训练
"""

import json
import cv2
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Optional


# ── 默认存储路径 ──
def _default_store_path() -> Path:
    return Path(__file__).parent.parent / "weld_results" / "review_records.json"


# ── 全局缓存 ──
_store_path: Optional[Path] = None


def set_store_path(path):
    """设置复核记录文件路径"""
    global _store_path
    _store_path = Path(path)


def get_store_path() -> Path:
    """获取当前存储路径"""
    global _store_path
    if _store_path is None:
        _store_path = _default_store_path()
    _store_path.parent.mkdir(parents=True, exist_ok=True)
    return _store_path


# ═══════════════════════════════════════════════════
#  读写操作
# ═══════════════════════════════════════════════════

def load_review_records() -> list[dict]:
    """加载所有复核记录

    Returns:
        复核记录列表，文件不存在时返回空列表
    """
    path = get_store_path()
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        return []
    except (json.JSONDecodeError, OSError):
        return []


def save_review_record(record: dict) -> bool:
    """追加一条复核记录到 JSON 文件

    Args:
        record: 复核记录字典，必须包含 timestamp、image_path、reviews、summary

    Returns:
        是否保存成功
    """
    records = load_review_records()
    records.append(record)

    path = get_store_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
        return True
    except OSError:
        return False


def get_record_count() -> int:
    """获取复核记录总数"""
    return len(load_review_records())


# ═══════════════════════════════════════════════════
#  模型优化相关查询
# ═══════════════════════════════════════════════════

def get_false_positive_samples() -> list[dict]:
    """提取所有 AI 误判样本（AI判NG但人工确认合格）

    这些样本是模型迭代优化的关键数据来源（方案 §4.3、§7.2）。

    Returns:
        AI 误判的复核记录列表，每条记录含图片路径、缺陷信息、置信度
    """
    records = load_review_records()
    fp_samples = []

    for record in records:
        for review in record.get("reviews", []):
            if review.get("human_judgment") == "ai_false_positive":
                fp_samples.append({
                    "timestamp": record.get("timestamp", ""),
                    "image_path": record.get("image_path", ""),
                    "cls_name": review.get("cls_name", ""),
                    "cls_id": review.get("cls_id", -1),
                    "confidence": review.get("confidence", 0.0),
                    "bbox": review.get("bbox", []),
                })

    return fp_samples


def get_low_confidence_samples(threshold: float = 0.75) -> list[dict]:
    """提取低置信度样本（置信度低于阈值）

    方案 §4.3 要求定期汇总置信度低于 75% 的样本用于模型再训练。

    Args:
        threshold: 置信度阈值，默认 0.75

    Returns:
        低置信度样本列表
    """
    records = load_review_records()
    low_conf = []

    for record in records:
        for review in record.get("reviews", []):
            conf = review.get("confidence", 1.0)
            if conf < threshold:
                low_conf.append({
                    "timestamp": record.get("timestamp", ""),
                    "image_path": record.get("image_path", ""),
                    "cls_name": review.get("cls_name", ""),
                    "cls_id": review.get("cls_id", -1),
                    "confidence": conf,
                    "bbox": review.get("bbox", []),
                    "human_judgment": review.get("human_judgment", "pending"),
                })

    return low_conf


def get_review_statistics() -> dict:
    """获取复核统计摘要

    Returns:
        {
            "total_records": 总复核记录数,
            "total_defects_reviewed": 总复核缺陷数,
            "confirmed_count": 确认缺陷数,
            "false_positive_count": AI误判数,
            "false_positive_rate": AI误判率,
        }
    """
    records = load_review_records()
    total_defects = 0
    confirmed = 0
    false_positives = 0

    for record in records:
        for review in record.get("reviews", []):
            total_defects += 1
            judgment = review.get("human_judgment", "pending")
            if judgment == "confirmed":
                confirmed += 1
            elif judgment == "ai_false_positive":
                false_positives += 1

    fp_rate = false_positives / total_defects if total_defects > 0 else 0.0

    return {
        "total_records": len(records),
        "total_defects_reviewed": total_defects,
        "confirmed_count": confirmed,
        "false_positive_count": false_positives,
        "false_positive_rate": round(fp_rate, 4),
    }


# ═══════════════════════════════════════════════════
#  构造辅助
# ═══════════════════════════════════════════════════

def build_review_record(
    image_path: str,
    ai_results_summary: dict,
    reviews: list[dict],
) -> dict:
    """构造一条完整的复核记录

    Args:
        image_path: 被检测的图片路径
        ai_results_summary: AI 检测结果概要 {"total": N, "class_stats": {...}, "orig_shape": (h, w)}
        reviews: 复核项列表，每项为 review_item 格式

    Returns:
        完整的复核记录字典
    """
    confirmed = sum(1 for r in reviews if r.get("human_judgment") == "confirmed")
    fp = sum(1 for r in reviews if r.get("human_judgment") == "ai_false_positive")
    pending = sum(1 for r in reviews if r.get("human_judgment") == "pending")

    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "image_path": image_path,
        "ai_summary": ai_results_summary,
        "reviews": reviews,
        "summary": {
            "total": len(reviews),
            "confirmed": confirmed,
            "false_positive": fp,
            "pending": pending,
        },
    }


# ═══════════════════════════════════════════════════
#  误判样本保存（用于模型迭代优化）
# ═══════════════════════════════════════════════════

def _misjudgment_dir() -> Path:
    """误判样本存储目录"""
    d = Path(__file__).parent.parent / "Misjudgment"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_misjudgment_samples(
    review_results: list[dict],
    source_image,
    source_label: str = "",
) -> int:
    """将误判样本的截图保存到 Misjudgment 目录

    保存完整的标注检测结果图，文件名含时间戳防止覆盖。

    Args:
        review_results: 复核结果列表，每项含 bbox / cls_name / human_judgment
        source_image: 标注后的检测结果图像（cv2 BGR numpy array 或 图片路径字符串）
        source_label: 来源标签（如批次名、帧号等），用于生成子目录和文件名

    Returns:
        保存的误判样本数量
    """
    fp_items = [r for r in review_results if r.get("human_judgment") == "ai_false_positive"]
    if not fp_items:
        return 0

    # 加载图像
    if isinstance(source_image, (str, Path)):
        img = cv2.imread(str(source_image))
        if img is None:
            return 0
    elif isinstance(source_image, np.ndarray):
        img = source_image
    else:
        return 0

    safe_label = source_label.replace("/", "_").replace("\\", "_").replace(":", "_").replace(" ", "_")[:60]

    # 每个批次单独一个文件夹
    batch_dir = _misjudgment_dir() / safe_label
    batch_dir.mkdir(parents=True, exist_ok=True)

    # 保存完整标注图，每个误判项一张
    saved = 0
    base_ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:18]
    for idx, item in enumerate(fp_items):
        cls_name = item.get("cls_name", "unknown").replace("/", "_").replace("\\", "_")
        # 加序号防覆盖（datetime 精度在 Windows 上可能不够）
        img_filename = f"{safe_label}_{cls_name}_{base_ts}_{idx}.jpg"
        cv2.imwrite(str(batch_dir / img_filename), img)
        saved += 1

    return saved
