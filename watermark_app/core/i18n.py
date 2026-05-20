from __future__ import annotations


LANGUAGE_ZH = "zh"
LANGUAGE_EN = "en"
CURRENT_LANGUAGE = LANGUAGE_ZH


TRANSLATIONS = {
    "app.culling": {"zh": "选片", "en": "Culling"},
    "app.watermark": {"zh": "水印", "en": "Watermark"},
    "app.collage": {"zh": "拼图", "en": "Collage"},
    "app.collage_tools": {"zh": "拼图工具箱", "en": "Collage Toolkit"},
    "app.contact_sheet": {"zh": "样片墙", "en": "Contact Sheet"},
    "app.social_export": {"zh": "社交导出", "en": "Social Export"},
    "app.batch_rename": {"zh": "批量重命名", "en": "Batch Rename"},
    "common.import_photos": {"zh": "导入照片", "en": "Import Photos"},
    "common.clear": {"zh": "清空", "en": "Clear"},
    "common.export": {"zh": "导出", "en": "Export"},
    "common.no_photos": {"zh": "没有照片", "en": "No Photos"},
    "common.choose_first": {"zh": "请先导入照片。", "en": "Please import photos first."},
    "common.done": {"zh": "完成", "en": "Done"},
    "common.export_done": {"zh": "导出完成。", "en": "Export completed."},
    "culling.title": {"zh": "选片", "en": "Culling"},
    "culling.empty": {"zh": "导入照片开始选片", "en": "Import photos to start culling"},
    "culling.rating": {"zh": "评分", "en": "Rating"},
    "culling.color": {"zh": "颜色标签", "en": "Color Label"},
    "culling.status": {"zh": "状态", "en": "Status"},
    "culling.min_rating": {"zh": "最低星级", "en": "Min Rating"},
    "culling.copy_selected": {"zh": "复制精选", "en": "Copy Picks"},
    "culling.no_picks": {"zh": "没有精选照片", "en": "No Picks"},
    "culling.set_rating_or_keep": {"zh": "请先设置星级或标记保留。", "en": "Set a rating or mark photos as kept first."},
    "culling.copy_done": {"zh": "复制完成", "en": "Copy Complete"},
    "culling.copied_count": {"zh": "已复制 {count} 张精选照片。", "en": "Copied {count} picked photos."},
    "contact.title": {"zh": "样片墙", "en": "Contact Sheet"},
    "contact.empty": {"zh": "导入照片生成样片墙", "en": "Import photos to create a contact sheet"},
    "contact.render": {"zh": "生成样片墙", "en": "Render Sheet"},
    "contact.columns": {"zh": "列数", "en": "Columns"},
    "contact.thumb_width": {"zh": "缩略图宽", "en": "Thumb Width"},
    "contact.thumb_height": {"zh": "缩略图高", "en": "Thumb Height"},
    "contact.background": {"zh": "背景色", "en": "Background"},
    "contact.export_title": {"zh": "导出样片墙", "en": "Export Contact Sheet"},
    "contact.export_done": {"zh": "样片墙导出完成。", "en": "Contact sheet exported."},
    "social.title": {"zh": "社交尺寸导出", "en": "Social Export"},
    "social.export_all": {"zh": "批量导出", "en": "Batch Export"},
    "social.contain": {"zh": "完整显示", "en": "Contain"},
    "social.cover": {"zh": "裁切填满", "en": "Cover"},
    "social.choose_dir": {"zh": "选择导出目录", "en": "Choose Export Folder"},
    "social.done_count": {"zh": "已导出 {count} 张照片。", "en": "Exported {count} photos."},
    "rename.title": {"zh": "批量重命名", "en": "Batch Rename"},
    "rename.preview": {"zh": "预览命名", "en": "Preview Names"},
    "rename.apply": {"zh": "执行重命名", "en": "Rename"},
    "rename.confirm": {"zh": "确认重命名", "en": "Confirm Rename"},
    "rename.confirm_text": {"zh": "确定重命名 {count} 张照片吗？", "en": "Rename {count} photos?"},
    "rename.done": {"zh": "批量重命名完成。", "en": "Batch rename completed."},
    "settings.language": {"zh": "语言", "en": "Language"},
    "settings.language_restart": {"zh": "导航名称将在下次启动时完全刷新。", "en": "Navigation labels fully refresh after restart."},
}


def set_language(language: str) -> None:
    global CURRENT_LANGUAGE
    CURRENT_LANGUAGE = language if language in {LANGUAGE_ZH, LANGUAGE_EN} else LANGUAGE_ZH


def current_language() -> str:
    return CURRENT_LANGUAGE


def tr(key: str, **kwargs) -> str:
    value = TRANSLATIONS.get(key, {}).get(CURRENT_LANGUAGE)
    if value is None:
        value = TRANSLATIONS.get(key, {}).get(LANGUAGE_ZH, key)
    return value.format(**kwargs) if kwargs else value
