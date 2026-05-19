# Coderleex Watermark

摄影照片水印和拼图工具。支持照片相框、相机 Logo、EXIF 参数、水印文字、PNG 水印素材叠加，以及多照片拼图、拼图组管理和批量导出。

## 开源协议

本项目使用 MIT License 开源，详见 [LICENSE](LICENSE)。

## 运行

```bash
python3 -m pip install -r requirements.txt
python3 app.py
```

## 当前功能

- 导入 JPG / PNG / TIFF / WebP
- 读取 EXIF：相机、镜头、焦距、光圈、快门、ISO、日期
- 模板：
  - Leica 风格白边
  - Hasselblad 底部水印
  - 模糊背景印框
  - 不使用相机参数
- 支持相机品牌 Logo 自动匹配：Sony / Canon / Nikon / Leica / Hasselblad / Fujifilm / DJI 等
- 支持主标题字体选择、标题透明度、位置和偏移
- 支持 EXIF 参数位置、大小、透明度、行间距、第二行缩进和偏移
- 支持 PNG 签名水印和文字签名水印叠加
- 默认加载项目内 `waterTmp/` 水印素材目录，并递归读取子目录 PNG
- 已内置一批本地水印素材和从 GPT 样式图中提取的透明签名水印
- 模板预设系统：
  - 每种模板风格内置 3 个系统预设（经典底部 / 左下简约 / 右下大字 等）
  - 支持保存当前配置为自定义预设，支持删除自定义预设
  - 选择预设后自动应用参数，仍可手动微调
  - 预设按照片尺寸类别独立保存
- 支持参数记忆：模板、文字、字体、位置、滑条、开关、导出质量、水印选择等都会在下次启动恢复
- 预览会降低渲染分辨率以减少模糊模板和大图调整时的卡顿，导出仍使用原图
- 批量导出在后台线程执行，带导出进度窗口和取消按钮
- 支持记住上次导出目录
- 拼图功能：
  - 支持 2 张、3 张、4 张、6 张、9 张常用网格布局
  - 照片按比例分类，点击可查看小预览
  - 已选照片可拖拽排序
  - 支持自定义比例、宽高、长边、间距、圆角和背景色
  - 支持拼图组暂存、更新、重命名、复制、删除和拖拽排序
  - 支持拼图组缩略图、未保存标记和 JPG / PNG 批量导出

## 水印素材

默认水印素材目录是项目根目录下的：

```text
waterTmp/
```

应用会递归读取其中所有 PNG 文件。子目录会显示为相对路径，例如：

```text
提取签名水印/03_signature_script_light_mark.png
```

如果在界面里手动选择其它水印目录，路径会被记忆。旧版本默认的 `/Users/lixinglin/Documents/水印` 会自动迁移到项目内 `waterTmp/`。

## 导出

- `导出当前`：导出当前选中照片
- `批量导出`：导出照片列表里的全部照片
- `导出当前`（拼图页）：导出当前拼图
- `批量导出组`（拼图页）：导出已暂存的全部拼图组
- 导出时会弹出进度窗口
- 渲染和保存运行在后台线程，避免主界面卡死
- 单张和批量导出都会记住上次导出的目录

## Windows EXE

仓库内置 GitHub Actions 自动构建 Windows 版本：

- 手动构建：在 GitHub Actions 页面运行 `Build Windows EXE`
- 自动发布：推送 `v*` 标签后自动构建并发布 Release

发布示例：

```bash
git tag v0.1.0
git push origin v0.1.0
```

构建产物会打包为：

```text
CoderleexWatermark-Windows.zip
```

## 测试

```bash
python3 -m py_compile watermark_app/core/collage.py watermark_app/core/collage_groups.py watermark_app/ui/common.py watermark_app/ui/collage_selector.py watermark_app/ui/collage_panel.py watermark_app/ui/main_window.py app.py scripts/smoke_collage.py tests/test_collage.py tests/test_collage_ui.py
python3 -m unittest tests.test_collage tests.test_collage_ui
python3 scripts/smoke_collage.py
```

## 说明

相框模板直接用代码生成，不依赖外部模板文件。这样文字更清晰，也可以自动替换真实 EXIF 信息。PNG 样式素材统一从 `waterTmp/` 或用户选择的水印目录读取。

项目内相机品牌 Logo 和示例水印素材仅用于应用功能展示及个人摄影工作流，请在公开分发素材或衍生内容前确认相关品牌和素材授权。
