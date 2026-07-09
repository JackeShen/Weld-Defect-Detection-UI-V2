# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## 项目概述

西安汇丰-京博工业焊缝检测系统 v5 — 基于 PyQt5 + YOLO (Ultralytics) 的工厂产线桌面应用。支持摄像头实时检测、图像检测、视频检测三种模式，含批次管理、人工复核、焊缝宽度测量、分析报告生成。

## 启动命令

```bash
conda activate oldshen && cd C:\Users\11137\Desktop && python -m UI
```

必须从 `Desktop` 目录（UI 包的父目录）以 `python -m UI` 方式启动。

## 架构

```
main_window.py          — 主窗口：模型管理、批次状态、报警、截图、线程管理
├── sidebar.py          — 侧边栏导航（6个页面入口 + 模型状态指示）
├── pages/
│   ├── dashboard_page.py   — 首页看板（数据卡片 + 模式入口）
│   ├── camera_page.py      — 摄像头实时检测（推流 + 批次启停 + 复核）
│   ├── image_page.py       — 图像检测（单张图 + YOLO + 复核 + 宽度测量）
│   ├── video_page.py       — 视频检测（逐帧播放 + 导出标注视频）
│   ├── log_page.py         — 检测记录日志（表格 + CSV导出 + 批次汇总）
│   └── analysis_page.py    — 分析报告 + 缺陷图库（3×3网格 + HTML报告）
├── widgets/            — 可复用组件（ModelPanel、ReviewPanel、ImageViewer等）
├── threads/            — QThread 子线程（DetectionThread、CameraDetectionThread、VideoProcessorThread）
├── dialogs/            — 对话框（BatchNameDialog、SaveAsDatasetDialog）
└── utils/              — 工具（图像转换、中文绘制、复核存储、焊缝宽度叠加）
```

### 核心设计模式

- **共享状态集中管理**：所有 Page 通过 `self.mw` 引用主窗口，模型、批次状态、宽度计算器等由 `WeldInspectionMainWindow` 统一持有
- **信号驱动**：`page_changed`、`model_loaded_signal`、`batch_finalized` 等 `pyqtSignal` 解耦组件通信
- **批次状态**（`main_window.py`）：`batch_state` dict 含 `active`、`full_name`、`total_images`、`total_defects`、`defect_details`；方法 `start_batch()` / `record_batch_defect()` / `finalize_batch()`
- **线程安全**：所有 YOLO 推理在 QThread 中，通过信号跨线程通信；`CameraDetectionThread` 支持 `set_skip_inference()` 切换检测开关

### 摄像头页面（v6）设计

- 摄像头始终可推流（`_is_streaming`），与批次检测（`_batch_active`）解耦
- 操作流程：打开摄像头 → 开始批次（填名 → 启用检测 → 缺陷累积）→ 复核 → 结束批次（判定）
- 布局：批次控制条（顶部）+ 摄像头 | 复核面板（水平分割器 55:45）+ 参数区（底部可折叠）
- 复核不冻结画面

### 复核面板（ReviewPanel）

- `show_complete_button` 参数控制是否显示"完成复核"按钮（摄像头页隐藏，图像页显示）
- `load_defects()` 清空并加载；`append_defects()` 追加不清空（摄像头连续检测用）
- "全部确认"仅可点一次，新缺陷追加后重新启用
- 支持 `thumb_pixmap` 缩略图显示

## 数据目录

```
UI/
├── weld_results/              ← 检测结果（按批次分子目录）
│   └── 批次名/                ← 截图 + review_records.json
├── Misjudgment/               ← 误判样本（按批次分子目录，只存原图）
│   └── 批次名/                ← 批次名.jpg
```

## 样式

- 暗黑科技风 QSS：`resources/style.qss`
- 主题色 `#00d4ff`（青蓝），按钮/导航状态与之一致
- 避免用 `setStyleSheet` 动态改样式（触发全局重算），用 `palette` 改背景色或使用 objectName 选择器

## 依赖

- `oldshen` conda 环境：PyQt5、OpenCV、Ultralytics YOLO、Pillow、NumPy
- `weld_width` 模块在 `UI/` 内，通过相对导入 `from .weld_width import ...` 引用
