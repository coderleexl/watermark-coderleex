# 拼图功能设计文档

## 概述

为 Watermark App 添加纯拼图功能，允许用户从照片列表中手动选择多张照片，按可拖拽顺序组合成一张图片，并支持实时预览和导出。

## 需求

- **功能定位**：纯拼图，不叠加相机参数、水印、签名或模板边框
- **布局样式**：均匀网格（2x2、3x3 等）
- **使用场景**：通用场景（社交媒体、作品集、打印等）
- **布局预设**：常用预设（2张、3张、4张、6张、9张等）
- **图片来源**：通过拼图页面 UI 手动选择参与拼图的照片
- **图片适配**：默认填满格子，允许裁切图片边缘
- **排序方式**：支持拖拽调整参与拼图照片的顺序
- **输出尺寸**：支持常用比例、宽高像素和输出长边自定义
- **实时预览**：修改照片选择、排序、布局或参数后自动刷新预览
- **自定义选项**：先实现基础闭环，后续扩展高级布局和样式
- **架构要求**：可扩展，尽量减少对现有水印功能的侵入

## MVP 范围

### 本期实现

- 新增独立“拼图”页面，不改变现有水印页面的主要工作流
- 拼图页包含：照片选择区、拼图预览区、拼图设置区
- 从已导入照片中通过 UI 勾选或选择参与拼图的照片
- 已选照片列表支持拖拽排序，排序即拼图顺序
- 支持布局预设：
  - 2张 横排：1x2
  - 2张 竖排：2x1
  - 3张 横排：1x3
  - 4张：2x2
  - 6张 横排网格：2x3
  - 6张 竖排网格：3x2
  - 9张：3x3
- 支持间距、圆角、背景色
- 支持输出宽度、输出高度、常用比例和输出长边
- 支持预览降采样，导出使用原图
- 支持导出当前拼图为 JPG 或 PNG

### 本期不做

- 拼图后叠加水印
- 每张图单独套水印模板
- 自由布局、瀑布流、胶片条
- 每个格子单独缩放、平移、旋转
- 拼图预设保存/加载
- 混合不同形状格子的模板

## 架构设计

### 页面布局

```text
┌─────────────────────────────────────────────────────────┐
│                    Coderleex Watermark                   │
├──────────┬────────────────────────────┬─────────────────┤
│ 导入照片  │                            │                 │
│ 可选照片  │        拼图预览区域          │    拼图设置面板   │
│          │                            │                 │
│ 已选照片  │                            │  布局 / 尺寸 / 导出 │
│ 拖拽排序  │                            │                 │
└──────────┴────────────────────────────┴─────────────────┘
```

当前项目使用 `FluentWindow.addSubInterface(...)` 注册页面。拼图功能建议新增一个独立导航页面“拼图”，而不是塞进现有“水印”页面内部。这样可以避免水印设置项和拼图设置项相互影响，也更容易保持现有水印功能稳定。

### 目录结构

```text
watermark_app/
├── core/
│   ├── renderer.py        # 水印渲染
│   ├── templates.py       # 水印模板
│   └── collage.py         # 拼图引擎（新增）
├── ui/
│   ├── main_window.py     # 主窗口（修改）
│   ├── photo_list.py      # 照片列表/选择组件（新增，公共或拼图专用）
│   └── collage_panel.py   # 拼图设置面板（新增）
└── app.py
```

说明：现有 `main_window.py` 中水印功能集中度较高。MVP 可以先新增拼图核心和拼图页面，减少对水印页面的大规模重构；公共照片列表组件可以在实现过程中逐步抽取。

## 核心组件

### 1. CollagePhotoSelector（拼图照片选择组件）

```python
class CollagePhotoSelector(QWidget):
    """拼图照片选择和排序组件"""

    photos_changed = Signal(list)
    collage_order_changed = Signal(list)

    def add_files(self, files: list[str]) -> None: ...
    def clear(self) -> None: ...
    def all_photos(self) -> list[Path]: ...
    def selected_photos(self) -> list[Path]: ...
    def set_selected_photos(self, paths: list[Path]) -> None: ...
```

交互规则：

- 上半区显示所有已导入照片，可通过复选框或按钮加入拼图
- 下半区显示参与拼图的照片，支持拖拽排序
- 拼图顺序始终以已选照片列表顺序为准
- 删除已选照片只从拼图中移除，不从已导入照片中删除
- 没有选择照片时，预览区显示空状态

### 2. CollageEngine（拼图引擎）

```python
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from PIL import Image


class CollageFitMode(str, Enum):
    COVER = "cover"  # 默认：填满格子，允许裁切


@dataclass(frozen=True)
class CollageLayout:
    name: str
    rows: int
    cols: int

    @property
    def cell_count(self) -> int:
        return self.rows * self.cols


@dataclass
class CollageOptions:
    gap: int = 8
    corner_radius: int = 0
    background_color: str = "#ffffff"
    output_width: int = 2000
    output_height: int = 2000
    fit_mode: CollageFitMode = CollageFitMode.COVER


class CollageEngine:
    def create_collage(
        self,
        images: list[Image.Image],
        layout: CollageLayout,
        options: CollageOptions,
    ) -> Image.Image: ...

    def create_collage_from_paths(
        self,
        paths: list[Path],
        layout: CollageLayout,
        options: CollageOptions,
        max_source_edge: int | None = None,
    ) -> Image.Image: ...
```

### 3. CollagePanel（拼图设置面板）

```python
class CollagePanel(QWidget):
    """拼图设置面板"""

    layout_presets = [
        ("2张 横排", CollageLayout("2张 横排", rows=1, cols=2)),
        ("2张 竖排", CollageLayout("2张 竖排", rows=2, cols=1)),
        ("3张 横排", CollageLayout("3张 横排", rows=1, cols=3)),
        ("4张 2x2", CollageLayout("4张 2x2", rows=2, cols=2)),
        ("6张 2x3", CollageLayout("6张 2x3", rows=2, cols=3)),
        ("6张 3x2", CollageLayout("6张 3x2", rows=3, cols=2)),
        ("9张 3x3", CollageLayout("9张 3x3", rows=3, cols=3)),
    ]

    gap_slider: NumericSlider
    corner_radius_slider: NumericSlider
    background_color_input: QLineEdit
    ratio_combo: QComboBox
    output_width_spin: QSpinBox
    output_height_spin: QSpinBox
    long_edge_spin: QSpinBox
```

尺寸交互：

- 可直接输入输出宽度和输出高度
- 选择常用比例时，根据当前长边自动计算宽高
- 修改长边时，根据当前比例自动计算宽高
- 如果用户直接修改宽高，比例显示为“自定义”
- 预览和导出都以当前宽高为最终画布尺寸

### 4. MainWindow 修改方向

```python
class MainWindow(FluentWindow):
    def __init__(self):
        self.collage_selector = CollagePhotoSelector()
        self.collage_panel = CollagePanel()
        self.collage_preview_label = QLabel()
        self.addSubInterface(self.create_collage_page(), FluentIcon.ALBUM, "拼图")

    def create_collage_page(self) -> QWidget: ...
    def schedule_collage_preview(self) -> None: ...
    def update_collage_preview(self) -> None: ...
    def collect_collage_options(self) -> CollageOptions: ...
    def export_collage(self) -> None: ...
```

## 实现步骤

### 阶段 1：基础设施

1. 创建 `watermark_app/core/collage.py`
2. 定义 `CollageLayout`、`CollageOptions`、`CollageFitMode`
3. 实现从路径加载图片、EXIF 自动旋转、预览降采样

### 阶段 2：拼图引擎

4. 实现均匀网格布局计算
5. 实现 cover 填满裁切
6. 实现间距、圆角、背景色
7. 实现图片不足留空、图片超出忽略

### 阶段 3：拼图 UI

8. 创建 `CollagePhotoSelector`
9. 创建 `CollagePanel`
10. 新增拼图页面三栏布局
11. 实现手动多选和已选照片拖拽排序

### 阶段 4：集成

12. 集成拼图预览
13. 参数变化、照片选择变化、拖拽排序后自动刷新预览
14. 实现拼图导出 JPG/PNG
15. 增加空状态、图片数量不匹配提示和错误提示

### 阶段 5：优化

16. 添加 smoke 测试或核心层测试
17. 优化大图预览性能
18. 视情况抽取现有水印照片列表为公共组件

## 技术细节

### 图片处理

- 使用 PIL/Pillow 进行图片处理
- 支持 EXIF 自动旋转
- 预览支持 `max_source_edge` 降采样
- 导出使用原图
- 默认使用 cover 模式：图片填满单元格，超出部分居中裁切

### 布局算法

```python
def calculate_layout(rows: int, cols: int, output_width: int, output_height: int, gap: int):
    """计算每个格子的位置和尺寸"""
    cell_width = (output_width - gap * (cols + 1)) / cols
    cell_height = (output_height - gap * (rows + 1)) / rows

    for i in range(rows * cols):
        row = i // cols
        col = i % cols
        x = gap + col * (cell_width + gap)
        y = gap + row * (cell_height + gap)
        yield (round(x), round(y), round(cell_width), round(cell_height))
```

```python
def cover_crop(image: Image.Image, target_width: int, target_height: int) -> Image.Image:
    """等比缩放并居中裁切，确保填满目标格子"""
    scale = max(target_width / image.width, target_height / image.height)
    resized = image.resize(
        (round(image.width * scale), round(image.height * scale)),
        Image.Resampling.LANCZOS,
    )
    left = (resized.width - target_width) // 2
    top = (resized.height - target_height) // 2
    return resized.crop((left, top, left + target_width, top + target_height))
```

### 图片数量处理

当图片数量与布局不匹配时：

- **图片不足**：留空单元格，显示背景色
- **图片超出**：只渲染前 `rows * cols` 张，并在 UI 显示提示
- **没有选择图片**：预览区显示“请选择参与拼图的照片”

### 拖拽排序

- 已选照片列表使用支持内部移动的 `QListWidget` 或 `QTreeWidget`
- 设置 `InternalMove` 拖拽模式
- 每次顺序变化后发出 `collage_order_changed`
- 渲染顺序以控件当前顺序为准，不依赖导入顺序

### 导出格式

- JPEG（默认，可调质量）
- PNG（支持透明背景）
- 导出文件默认名：`collage.jpg`

### 预览性能

- 预览渲染使用定时器 debounce，避免滑条拖动时频繁渲染
- 预览图片加载传 `max_source_edge`
- 预览缩放到预览控件尺寸
- 导出不传 `max_source_edge`，保证使用原图质量

## 测试建议

- 2 张横排输出尺寸正确
- 4 张 2x2 输出尺寸正确
- 9 张 3x3 输出尺寸正确
- 图片不足时空格为背景色
- 图片超出时只使用前 N 张
- 横图、竖图、方图都能 cover 填满格子
- 圆角、间距、背景色生效
- JPG/PNG 导出成功
- 拖拽排序后预览顺序变化

## 未来扩展

- 自由拼图布局
- 瀑布流布局
- 胶片条布局
- 自定义模板
- 拼图后统一叠加水印
- 每张图先套水印再拼图
- 边框样式
- 每个格子独立缩放和平移
- 拼图预设保存/加载

## 依赖

- PySide6
- Pillow
- qfluentwidgets
