# 西安汇丰-京博工业焊缝检测系统 v5

基于 PyQt5 + YOLO (Ultralytics) 的工厂产线桌面应用，用于工业焊缝缺陷检测。

## 功能特性

- **三种检测模式**
  - 摄像头实时检测：支持实时推流、批次管理、连续检测
  - 图像检测：单张图片检测，支持焊缝宽度测量
  - 视频检测：逐帧播放检测，支持导出标注视频

- **批次管理**：创建批次、记录缺陷、批次汇总判定
- **人工复核**：检测结果人工确认，支持误判标记
- **焊缝宽度测量**：自动测量焊缝宽度并叠加显示
- **分析报告**：生成 HTML 格式的分析报告，含缺陷图库（3x3 网格）
- **检测日志**：表格化记录，支持 CSV 导出

## 快速开始

### 环境要求

- Python 3.8+
- Conda 环境 `oldshen`

### 依赖包

```
PyQt5
opencv-python
ultralytics (YOLO)
Pillow
numpy
```

### 启动命令

```bash
conda activate oldshen
cd C:\Users\11137\Desktop
python -m UI
```

> **注意**：必须从 `Desktop` 目录（UI 包的父目录）以 `python -m UI` 方式启动。

## 项目结构

```
UI/
├── __init__.py              # 包初始化
├── __main__.py              # 入口文件
├── main_window.py           # 主窗口：模型管理、批次状态、报警、截图、线程管理
├── sidebar.py               # 侧边栏导航（6个页面入口 + 模型状态指示）
├── weld_width.py            # 焊缝宽度计算模块
│
├── pages/                   # 页面组件
│   ├── dashboard_page.py    # 首页看板（数据卡片 + 模式入口）
│   ├── camera_page.py       # 摄像头实时检测
│   ├── image_page.py        # 图像检测
│   ├── video_page.py        # 视频检测
│   ├── log_page.py          # 检测记录日志
│   └── analysis_page.py     # 分析报告 + 缺陷图库
│
├── widgets/                 # 可复用组件
│   ├── model_panel.py       # 模型选择面板
│   ├── review_panel.py      # 复核面板
│   ├── image_viewer.py      # 图像查看器
│   ├── result_panel.py      # 结果面板
│   ├── detection_params.py  # 检测参数设置
│   ├── weld_params.py       # 焊缝参数设置
│   └── status_indicator.py  # 状态指示器
│
├── threads/                 # QThread 子线程
│   ├── detection_thread.py  # 通用检测线程
│   ├── camera_thread.py     # 摄像头检测线程
│   ├── video_thread.py      # 视频处理线程
│   └── report_thread.py     # 报告生成线程
│
├── dialogs/                 # 对话框
│   ├── batch_name_dialog.py # 批次命名对话框
│   └── save_dataset_dialog.py # 保存数据集对话框
│
├── utils/                   # 工具函数
│   ├── image_conversion.py  # 图像格式转换
│   ├── chinese_text.py      # 中文文字绘制
│   ├── review_store.py      # 复核记录存储
│   └── width_overlay.py     # 焊缝宽度叠加显示
│
├── resources/               # 资源文件
│   └── style.qss            # QSS 样式表
│
├── weld_results/            # 检测结果（按批次存储）
└── Misjudgment/             # 误判样本（按批次存储）
```

## 核心设计

### 共享状态管理

所有页面通过 `self.mw` 引用主窗口，模型、批次状态、宽度计算器等由 `WeldInspectionMainWindow` 统一持有。

### 信号驱动通信

使用 PyQt5 信号槽机制解耦组件：
- `page_changed`：页面切换信号
- `model_loaded_signal`：模型加载完成信号
- `batch_finalized`：批次结束信号

### 批次状态

```python
batch_state = {
    "active": bool,           # 是否激活
    "full_name": str,         # 批次全名
    "total_images": int,      # 总图片数
    "total_defects": int,     # 总缺陷数
    "defect_details": dict    # 缺陷详情
}
```

### 线程安全

所有 YOLO 推理在 QThread 中执行，通过信号跨线程通信。`CameraDetectionThread` 支持 `set_skip_inference()` 切换检测开关。

## 数据目录

```
weld_results/
└── 批次名/
    ├── screenshots/          # 检测截图
    └── review_records.json   # 复核记录

Misjudgment/
└── 批次名/
    └── *.jpg                 # 误判样本原图
```

## 样式主题

- 暗黑科技风 QSS 样式
- 主题色：`#00d4ff`（青蓝）
- 样式文件：`resources/style.qss`

## 许可证

私有项目 - 西安汇丰 / 京博工业
