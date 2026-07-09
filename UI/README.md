# 西安汇丰-京博工业焊缝检测系统 v5.2

基于 PyQt5 + YOLO (Ultralytics) 的工厂产线桌面应用，用于工业焊缝缺陷在线检测。

## 功能特性

- **三种检测模式**
  - 摄像头实时检测：推流与批次解耦，连续检测不冻结画面
  - 图像检测：单张图片检测，支持焊缝宽度测量
  - 视频检测：逐帧播放检测，支持导出标注视频

- **智能缺陷判定**
  - `Good_Weld` 识别为合格焊缝，不计入缺陷
  - 仅非 Good_Weld 类别（裂纹、气孔、夹渣等）判定为缺陷
  - 合格/不合格判定自动同步到批次汇总

- **批次管理**
  - 批次信息对话框（日期/批次号/零件名称，含实时预览）
  - 自动递增批次号（QSettings 持久化）
  - 批次汇总：检测帧数、缺陷数、通过/不通过判定

- **人工复核**
  - 每个缺陷独立复核：确认缺陷 / AI误判
  - 全部确认后方可完成复核（闪烁提示）
  - 结束批次/关闭程序前强制检查未复核项，弹出警告

- **数据留存**
  - 缺陷标注图 → `weld_results/<批次名>/`（带检测框的完整截图）
  - 误判样本图 → `Misjudgment/<批次名>/`（带标注框，用于模型迭代）
  - 复核记录 JSON → `weld_results/<批次名>/review_records.json`
  - 文件名含时间戳+序号，绝不覆盖

- **焊缝宽度测量**：Mask 分割 + 相机参数标定，叠加显示
- **分析报告**：HTML 报告 + 3x3 缺陷图库（递归扫描子目录）
- **检测日志**：表格化记录，含批次列，支持 CSV 导出

## 快速开始

### 环境要求

- Python 3.8+
- Conda 环境 `oldshen`
- 摄像头（可选）

### 依赖

```
PyQt5
opencv-python
ultralytics (YOLO)
Pillow
numpy
```

### 启动

```bash
conda activate oldshen
cd C:\Users\11137\Desktop
python -m UI
```

> 必须从 `Desktop` 目录以 `python -m UI` 方式启动。

## 项目结构

```
UI/
├── __init__.py
├── __main__.py               # 入口
├── main_window.py            # 主窗口：模型/批次/报警/截图/线程
├── sidebar.py                # 侧边栏（6 页面 + 模型状态）
├── weld_width.py             # 焊缝宽度计算

├── pages/
│   ├── dashboard_page.py     # 首页看板
│   ├── camera_page.py        # 摄像头实时检测
│   ├── image_page.py         # 图像检测
│   ├── video_page.py         # 视频检测
│   ├── log_page.py           # 检测日志
│   └── analysis_page.py      # 分析报告 + 缺陷图库

├── widgets/
│   ├── model_panel.py        # 模型选择
│   ├── review_panel.py       # 人工复核面板
│   ├── image_viewer.py       # 图像查看器
│   ├── result_panel.py       # 检测结果面板
│   ├── detection_params.py   # 检测参数
│   ├── weld_params.py        # 焊缝参数
│   └── status_indicator.py   # 状态指示

├── threads/
│   ├── detection_thread.py   # 图像检测线程
│   ├── camera_thread.py      # 摄像头检测线程
│   ├── video_thread.py       # 视频处理线程
│   └── report_thread.py      # 报告生成线程

├── dialogs/
│   ├── batch_name_dialog.py  # 批次命名
│   └── save_dataset_dialog.py # 数据集导出

├── utils/
│   ├── image_conversion.py   # cv2 ↔ QPixmap
│   ├── chinese_text.py       # 中文绘制
│   ├── review_store.py       # 复核记录/误判样本持久化
│   ├── width_overlay.py      # 宽度叠加
│   └── paths.py              # 路径工具

├── resources/
│   └── style.qss             # 暗黑科技风样式

├── weld_results/             # 检测结果（自动创建）
└── Misjudgment/              # 误判样本（自动创建）
```

## 操作流程

### 摄像头模式

```
打开摄像头 → 加载模型
    ↓
开始批次（填写批次信息）
    ↓
实时检测（缺陷自动截图 + 追加复核面板）
    ↓
人工复核（确认缺陷 / AI误判）
    ↓
结束批次（判定通过/不通过）
    ↓
摄像头继续推流（可开始下一批次）
    ↓
关闭摄像头（画面变黑）
```

### 图像模式

```
加载模型 → 加载图片
    ↓
设置批次
    ↓
开始检测
    ↓
人工复核 → 完成复核
    ↓
结束批次 → 判定
```

## 核心设计

### 缺陷判定逻辑

```
检测结果
  ├── 无检测 → 合格 ✅
  ├── 仅 Good_Weld → 合格 ✅（不计入缺陷数）
  └── 其他类别 → 不合格 ⚠（计入缺陷数，需复核）
```

`is_defect_class()` 静态方法统一判断：排除 `Good_Weld`，其余皆为缺陷。

### 批次状态

```python
batch_state = {
    "active": bool,           # 批次进行中
    "full_name": str,         # 批次全名（日期_批次号_零件名）
    "total_images": int,      # 检测帧数
    "total_defects": int,     # 真实缺陷数（不含 Good_Weld）
    "defect_details": list,   # [(image_path, cls_name, conf), ...]
}
```

### 信号驱动

| 信号 | 发射者 | 用途 |
|------|--------|------|
| `page_changed` | Sidebar | 页面切换 |
| `model_loaded_signal` | ModelPanel | 模型就绪通知 |
| `batch_finalized` | MainWindow | 批次结束通知 |
| `review_completed` | ReviewPanel | 复核完成 |
| `frame_ready` | CameraThread | 帧画面就绪 |
| `detection_done` | CameraThread | 检测结果就绪 |

### 线程模型

- YOLO 推理均在 QThread 子线程执行
- 标注图通过 `r.plot()` 在主线程（信号槽）重新生成，避免竞态
- `auto_save_screenshot` 使用 `threading.Thread` 后台写盘，不卡 UI
- 所有信号跨线程通信，Qt 事件循环自动序列化

### 数据目录

```
weld_results/
└── 20260709_第12批_焊缝组件/
    ├── cam_f42_20260709_153025_123456.jpg   # 缺陷标注截图
    ├── image_20260709_154030_654321.jpg     # 图像检测标注截图
    └── review_records.json                  # 复核记录

Misjudgment/
└── 20260709_第12批_焊缝组件/
    ├── 20260709_第12批_焊缝组件_crack_20260709_153025_0.jpg
    └── 20260709_第12批_焊缝组件_porosity_20260709_153025_1.jpg
```

- 标注截图：仅保存有真实缺陷的帧（Good_Weld 不保存）
- 误判样本：保存完整标注图，文件名含类别和时间戳
- 所有路径为相对路径（相对于 `UI/` 目录）

## 样式

- 暗黑科技风主题
- 主色 `#00d4ff`（青蓝）
- 文件：`resources/style.qss`
- 避免 `setStyleSheet` 动态改样式，用 `palette` 或 objectName 选择器

## 更新日志

### v5.2
- Good_Weld 不作为缺陷，仅非 Good_Weld 类别计入缺陷
- 结束批次/关闭程序前强制检查未复核项
- 误判样本按批次独立保存，文件名防覆盖
- 缺陷保存完整标注图（`r.plot()` 生成）
- 分析图库支持递归扫描子目录
- 摄像头关闭后画面变黑
- 视频页切换时正确保存批次数据
- 批次对话框紧凑布局
- 多项稳定性修复

### v5.1
- 摄像头推流与批次检测解耦
- 复核面板支持追加模式（连续检测不闪烁）
- 批次管理、日志 CSV 导出
- 分析报告 HTML 生成

### v5.0
- 初始工厂产线版本

## 许可证

私有项目 — 西安汇丰 / 京博工业
