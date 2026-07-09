"""分析报告生成线程 v5 — 工厂简化版，输出通俗易懂的 HTML 报告"""

from collections import Counter
from datetime import datetime

from PyQt5.QtCore import QThread, pyqtSignal


class ReportThread(QThread):
    """后台统计线程，避免阻塞 UI

    输入 batch_history 的副本（list[dict]），纯计算不碰 UI。
    输出暗色主题 HTML 报告字符串，工厂工人一看就懂。

    Signals:
        finished: 生成完成，携带 HTML 报告字符串
        error: 生成失败，携带错误消息字符串
    """

    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, batch_history: list):
        """
        Args:
            batch_history: list[dict]，每条含:
                batch_name, full_name, part_name, total_images,
                total_defects, passed, defect_details, time
        """
        super().__init__()
        self._batch_history = batch_history

    # ═══════════════════════════════════════════════════
    #  配色
    # ═══════════════════════════════════════════════════

    BG = "#0a0e13"
    CARD_BG = "#0f1520"
    BORDER = "#21262d"
    TEXT = "#c9d1d9"
    TEXT_MUTED = "#8b949e"
    ACCENT = "#00d4ff"
    GREEN = "#3fb950"
    RED = "#f85149"

    def run(self):
        try:
            html = self._build_report()
            self.finished.emit(html)
        except Exception as e:
            self.error.emit(f"报告生成失败: {str(e)}")

    # ═══════════════════════════════════════════════════
    #  统计计算（工厂简化版）
    # ═══════════════════════════════════════════════════

    def _compute_stats(self):
        batches = self._batch_history

        if not batches:
            return None

        total_batches = len(batches)
        passed_batches = sum(1 for b in batches if b.get("passed", False))
        failed_batches = total_batches - passed_batches

        total_images = sum(b.get("total_images", 0) for b in batches)
        total_defects = sum(b.get("total_defects", 0) for b in batches)

        # 缺陷类别汇总（跨所有批次）
        all_defect_counter = Counter()
        for b in batches:
            for _, cls_name, _ in b.get("defect_details", []):
                all_defect_counter[cls_name] += 1

        return {
            "total_batches": total_batches,
            "passed_batches": passed_batches,
            "failed_batches": failed_batches,
            "total_images": total_images,
            "total_defects": total_defects,
            "defect_counter": all_defect_counter,
            "batches": batches,
        }

    # ═══════════════════════════════════════════════════
    #  HTML 构建
    # ═══════════════════════════════════════════════════

    def _build_report(self):
        stats = self._compute_stats()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        css = self._build_css()
        body = self._build_body(stats, now)
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>焊缝检测报告</title>{css}</head>
<body>{body}</body>
</html>"""

    def _build_css(self):
        return f"""
<style>
    body {{ background: {self.BG}; color: {self.TEXT};
           font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
           margin: 0; padding: 24px 36px; line-height: 1.5; }}
    h1 {{ color: {self.ACCENT}; font-size: 22px;
          border-bottom: 2px solid {self.BORDER}; padding-bottom: 10px; }}
    h2 {{ color: #e6edf3; font-size: 16px; margin-top: 24px; }}
    .time {{ color: {self.TEXT_MUTED}; font-size: 12px; margin-bottom: 20px; }}
    .big-box {{ display: flex; gap: 16px; flex-wrap: wrap; margin: 16px 0; }}
    .big-item {{ background: {self.CARD_BG}; border: 2px solid {self.BORDER};
                 border-radius: 12px; padding: 20px 28px; min-width: 110px; text-align: center; }}
    .big-num {{ font-size: 42px; font-weight: bold; }}
    .big-label {{ font-size: 13px; color: {self.TEXT_MUTED}; margin-top: 4px; }}
    .pass {{ color: {self.GREEN}; }}
    .fail {{ color: {self.RED}; }}
    table {{ width: 100%; border-collapse: collapse; margin: 12px 0 20px 0; }}
    th {{ background: {self.CARD_BG}; color: {self.ACCENT}; padding: 10px 12px;
          text-align: center; border-bottom: 2px solid {self.ACCENT}; font-size: 13px; }}
    td {{ padding: 8px 12px; border-bottom: 1px solid {self.BORDER};
          text-align: center; font-size: 13px; }}
    tr:hover {{ background: {self.CARD_BG}; }}
    .badge-pass {{ color: {self.GREEN}; font-weight: bold; font-size: 16px; }}
    .badge-fail {{ color: {self.RED}; font-weight: bold; font-size: 16px; }}
    .empty {{ color: {self.TEXT_MUTED}; text-align: center; padding: 40px; }}
    .verdict-box {{ border-radius: 10px; padding: 16px 24px; margin: 16px 0; text-align: center; }}
    .verdict-pass {{ background: #0a2a10; border: 2px solid #1a5a20; }}
    .verdict-fail {{ background: #2a0a0a; border: 2px solid #5a1a1a; }}
</style>"""

    def _build_body(self, stats, now):
        if stats is None:
            return """
<div class="empty">
    <p style="font-size:48px;">📭</p>
    <p>暂无检测记录。</p>
    <p style="font-size:12px;">请先在图像检测页完成批次检测后再生成报告。</p>
</div>"""

        sections = [
            self._header(now),
            self._overview(stats),
            self._verdict(stats),
            self._defect_summary(stats),
            self._batch_table(stats),
        ]
        return "\n".join(sections)

    def _header(self, now):
        return f"""
<h1>📊 焊缝检测报告</h1>
<p class="time">报告生成时间: {now}</p>"""

    def _overview(self, stats):
        items = [
            ("总检测批次", stats["total_batches"], "#00d4ff"),
            ("✅ 通过", stats["passed_batches"], "#3fb950"),
            ("🚨 不通过", stats["failed_batches"],
             "#f85149" if stats["failed_batches"] > 0 else "#8b949e"),
            ("总检测图片", stats["total_images"], "#00d4ff"),
            ("总缺陷数", stats["total_defects"],
             "#f85149" if stats["total_defects"] > 0 else "#3fb950"),
        ]
        boxes = "\n".join(
            f'<div class="big-item"><div class="big-num" style="color:{color}">{v}</div>'
            f'<div class="big-label">{k}</div></div>'
            for k, v, color in items
        )
        return f"<h2>📋 检测概览</h2><div class=\"big-box\">{boxes}</div>"

    def _verdict(self, stats):
        """总体判定"""
        if stats["failed_batches"] == 0:
            return (
                '<div class="verdict-box verdict-pass">'
                '<p style="font-size:20px; color:#3fb950; font-weight:bold; margin:0;">'
                '✅ 所有批次检测通过</p>'
                '<p style="color:#8b949e; margin:4px 0 0 0;">产品质量合格，可正常流转</p>'
                '</div>'
            )
        else:
            return (
                f'<div class="verdict-box verdict-fail">'
                f'<p style="font-size:20px; color:#f85149; font-weight:bold; margin:0;">'
                f'🚨 {stats["failed_batches"]} 个批次检测不通过</p>'
                f'<p style="color:#d2991d; margin:4px 0 0 0;">'
                f'请对不通过批次进行隔离或人工复检</p>'
                f'</div>'
            )

    def _defect_summary(self, stats):
        """缺陷类别汇总"""
        if not stats["defect_counter"]:
            return ""

        rows = []
        total = stats["total_defects"]
        for cls_name, cnt in stats["defect_counter"].most_common():
            pct = cnt / total * 100 if total > 0 else 0
            rows.append(
                f"<tr><td>{cls_name}</td><td>{cnt} 处</td>"
                f"<td>{pct:.0f}%</td></tr>"
            )

        table = (
            "<table><tr><th>缺陷类型</th><th>数量</th><th>占比</th></tr>"
            + "\n".join(rows)
            + "</table>"
        )
        return f"<h2>🔍 缺陷类型统计</h2>{table}"

    def _batch_table(self, stats):
        """批次明细表"""
        rows = []
        for i, b in enumerate(stats["batches"], 1):
            passed = b.get("passed", False)
            badge = (
                '<span class="badge-pass">✅ 通过</span>' if passed
                else '<span class="badge-fail">🚨 不通过</span>'
            )
            rows.append(
                f"<tr>"
                f"<td>{i}</td>"
                f"<td>{b.get('full_name', b.get('batch_name', '-'))}</td>"
                f"<td>{b.get('total_images', 0)}</td>"
                f"<td>{b.get('total_defects', 0)}</td>"
                f"<td>{badge}</td>"
                f"</tr>"
            )

        table = (
            "<table><tr><th>序号</th><th>批次名</th><th>检测图片</th>"
            "<th>缺陷数</th><th>判定</th></tr>"
            + "\n".join(rows)
            + "</table>"
        )
        return f"<h2>📦 批次明细</h2>{table}"
