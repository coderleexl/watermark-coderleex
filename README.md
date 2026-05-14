# Coderleex Watermark

自用摄影照片水印工具。支持照片相框、水印文字、PNG 水印素材叠加，并优先从照片 EXIF 中读取真实相机、镜头和拍摄参数。

## 运行

```bash
python3 -m pip install -r requirements.txt
python3 app.py
```

## 当前功能

- 导入 JPG / PNG / TIFF / WebP
- 读取 EXIF：相机、镜头、焦距、光圈、快门、ISO、日期
- 三类模板：
  - Leica 风格白边
  - Hasselblad 风格黑边
  - 英文照片内水印
  - PNG 图片水印叠加
- 自动加载 `/Users/lixinglin/Documents/水印` 中的透明 PNG 水印素材
- 支持位置、大小、透明度、边框比例、底部留白、导出质量

## 说明

相框模板第一版直接用代码生成，不需要下载网站模板。这样文字更清晰，也可以自动替换真实 EXIF 信息。PNG 样式素材可以从本机水印目录直接叠加；整版样例图后续可做半自动裁切提取。
