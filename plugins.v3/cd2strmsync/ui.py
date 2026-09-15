"""插件页面的 Vuetify JSON 构建：配置表单与详情页。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .rules import (
    DEFAULT_LINK_EXTS,
    DEFAULT_METADATA_EXTS,
    DEFAULT_STRM_TEMPLATE,
    MAX_GLOBAL_EXCLUDES,
    MirrorRule,
    OrganizeRule,
    SyncRule,
    has_nested_target,
    mirror_key,
    organize_key,
    rule_key,
)

# 下拉选项
METADATA_MODES = [
    {"title": "本地模式（从挂载盘复制）", "value": "local"},
    {"title": "云端模式（经 API 下载）", "value": "cloud"},
]
LINK_MODES = [
    {"title": "strm", "value": "strm"},
    {"title": "symlink", "value": "symlink"},
]
STRM_MODES = [
    {"title": "cloud（云端直链）", "value": "cloud"},
    {"title": "local（挂载路径）", "value": "local"},
]
PROCESS_MODES = [
    {"title": "精确（按通知处理，推荐）", "value": "precise"},
    {"title": "目录扫描（整目录比对）", "value": "scan"},
]
MOUNT_TYPES = [
    {"title": "cd2", "value": "cd2"},
    {"title": "alist", "value": "alist"},
    {"title": "local", "value": "local"},
]


def _text_node(
    value: str, css: str = "text-body-2", style: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """构造一个纯文本节点。"""
    props: Dict[str, Any] = {"class": css}
    if style:
        props["style"] = style
    return {"component": "span", "props": props, "text": value}


# 注入到插件页面的受控样式（B 紧凑日志表）：所有选择器都限定在 .cd2strm-page 内，避免影响其它页面。
PAGE_CSS = """
.cd2strm-page{font-size:13px}
.cd2strm-page .cd2strm-panel,details.cd2strm-group{border:1px solid rgba(var(--v-theme-on-surface,0,0,0),.14);
border-radius:8px;margin-bottom:10px;overflow:hidden}
.cd2strm-page .cd2strm-phead{display:flex;align-items:center;flex-wrap:wrap;gap:4px 8px;padding:8px 14px 8px 12px;font-size:13px;font-weight:600;
background:rgba(var(--v-theme-on-surface,0,0,0),.03);border-bottom:1px solid rgba(var(--v-theme-on-surface,0,0,0),.10)}
details.cd2strm-group>summary.cd2strm-phead{cursor:pointer;list-style:none}
details.cd2strm-group>summary.cd2strm-phead::-webkit-details-marker{display:none}
details.cd2strm-group>summary.cd2strm-phead::before{content:"\\25BE";font-size:10px;opacity:.5}
details.cd2strm-group:not([open])>summary.cd2strm-phead::before{content:"\\25B8"}
.cd2strm-page .cd2strm-stripe{width:4px;align-self:stretch;border-radius:2px;margin:-8px 2px -8px -12px;
background:rgb(var(--v-theme-success,46,125,50))}
.cd2strm-page .cd2strm-stripe.warn{background:rgb(var(--v-theme-warning,237,108,2))}
.cd2strm-page .cd2strm-stripe.bad{background:rgb(var(--v-theme-error,198,40,40))}
.cd2strm-page .cd2strm-sp{flex:1 1 auto;min-width:0}
.cd2strm-page .cd2strm-idx{font-size:11px;font-weight:700;letter-spacing:.04em;opacity:.65}
.cd2strm-page .cd2strm-meta{font-size:11.5px;font-weight:400;opacity:.6;font-family:ui-monospace,Menlo,Consolas,monospace;
min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cd2strm-page .cd2strm-pbody{padding:10px 12px}
.cd2strm-page .cd2strm-sub{padding:0;margin-top:6px}
.cd2strm-page details.cd2strm-group>.cd2strm-sub{padding:10px 12px;margin-top:0}
.cd2strm-page .cd2strm-paths{display:grid;grid-template-columns:1fr;gap:2px;margin:0 0 8px}
.cd2strm-page .cd2strm-path{display:grid;grid-template-columns:58px minmax(0,1fr);gap:6px;align-items:baseline}
.cd2strm-page .cd2strm-path .l{font-size:10.5px;opacity:.6}
.cd2strm-page .cd2strm-path .v{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12px;
white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cd2strm-page .cd2strm-kpis{display:grid;grid-template-columns:repeat(8,minmax(0,1fr));margin:10px 0;
border:1px solid rgba(var(--v-theme-on-surface,0,0,0),.12);border-radius:6px;overflow:hidden}
.cd2strm-page .cd2strm-kpis.k4{grid-template-columns:repeat(4,minmax(0,1fr))}
.cd2strm-page .cd2strm-kpi{padding:6px 9px;border-right:1px solid rgba(var(--v-theme-on-surface,0,0,0),.12)}
.cd2strm-page .cd2strm-kpi:last-child{border-right:none}
.cd2strm-page .cd2strm-kpi .n{font-size:15px;font-weight:600;line-height:1.25}
.cd2strm-page .cd2strm-kpi .l{font-size:10.5px;opacity:.6;white-space:nowrap;margin-top:1px}
.cd2strm-page .cd2strm-kpi.muted .n{opacity:.6}
.cd2strm-page .cd2strm-kpi.bad .n{color:rgb(var(--v-theme-error,198,40,40))}
.cd2strm-page .cd2strm-kpi.ok .n{color:rgb(var(--v-theme-success,46,125,50))}
.cd2strm-page .cd2strm-progress{margin:8px 0 2px}
.cd2strm-page .cd2strm-hint{font-size:11.5px;opacity:.65;margin-top:6px}
.cd2strm-page .cd2strm-alert{display:flex;gap:8px;align-items:center;font-size:12px;margin-top:10px;
padding:6px 9px;border-radius:6px;border:1px solid rgba(var(--v-theme-warning,237,108,2),.4);
background:rgba(var(--v-theme-warning,237,108,2),.10)}
.cd2strm-page .cd2strm-alert.bad{border-color:rgba(var(--v-theme-error,198,40,40),.4);
background:rgba(var(--v-theme-error,198,40,40),.10)}
.cd2strm-page .cd2strm-btns{display:flex;gap:6px;justify-content:flex-end;flex-wrap:wrap;margin-top:10px}
details.cd2strm-fold{border-top:1px solid rgba(var(--v-theme-on-surface,0,0,0),.10);margin-top:10px;padding-top:8px}
details.cd2strm-fold>summary{list-style:none;cursor:pointer;display:flex;align-items:center;gap:6px;
font-size:12.5px;font-weight:600;opacity:.85}
details.cd2strm-fold>summary::-webkit-details-marker{display:none}
details.cd2strm-fold>summary::before{content:"\\25B8";font-size:9px;opacity:.55}
details.cd2strm-fold[open]>summary::before{content:"\\25BE"}
details.cd2strm-fold.cd2strm-group>summary{flex-wrap:wrap;row-gap:4px;padding:8px 12px}
.cd2strm-page .cd2strm-tr{display:grid;align-items:center;gap:8px;padding:4px 0;font-size:12px;
border-bottom:1px solid rgba(var(--v-theme-on-surface,0,0,0),.08)}
.cd2strm-page .cd2strm-tr:last-child{border-bottom:none}
.cd2strm-page .cd2strm-tr.th{border-bottom:1px solid rgba(var(--v-theme-on-surface,0,0,0),.14)}
.cd2strm-page .cd2strm-tr.th .h{font-size:10.5px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;opacity:.5}
.cd2strm-page .cd2strm-tr.ev{grid-template-columns:max-content max-content minmax(0,1fr) max-content}
.cd2strm-page .cd2strm-tr.rec{grid-template-columns:max-content max-content minmax(0,1fr) minmax(0,1.2fr);
align-items:start}
.cd2strm-page .cd2strm-tr.org{grid-template-columns:max-content max-content max-content minmax(0,1.7fr) minmax(0,0.9fr);
align-items:center}
.cd2strm-page .cd2strm-tr.ign{grid-template-columns:max-content max-content minmax(0,1fr) minmax(0,1fr) max-content}
.cd2strm-page .cd2strm-menu{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px}
/* 「消息与日志」区：全页共用的操作区（文字按钮，不做悬停说明，避免遮挡与横向溢出） */
.cd2strm-page .cd2strm-msglog{display:flex;align-items:center;flex-wrap:wrap;gap:8px;
padding:8px 12px;margin-bottom:10px;border:1px solid rgba(var(--v-theme-on-surface,0,0,0),.14);
border-radius:8px;background:rgba(var(--v-theme-on-surface,0,0,0),.03)}
.cd2strm-page .cd2strm-msglog .cd2strm-mtitle{font-size:13px;font-weight:600}
.cd2strm-page .cd2strm-msglog .cd2strm-stripe{width:4px;height:14px;border-radius:2px;margin:0;
align-self:center;background:rgb(var(--v-theme-primary,103,80,164))}
.cd2strm-page .cd2strm-t{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:11.5px;opacity:.65;white-space:nowrap}
.cd2strm-page .cd2strm-pth{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:11.5px;
white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cd2strm-page .cd2strm-r{display:flex;align-items:center;gap:4px;justify-content:flex-end}
.cd2strm-page .cd2strm-s{font-size:12px;overflow:hidden;text-overflow:ellipsis}
.cd2strm-page .cd2strm-fl{display:flex;flex-direction:column;gap:1px;min-width:0}
.cd2strm-page .cd2strm-ok{color:rgb(var(--v-theme-success,46,125,50))}
.cd2strm-page .cd2strm-st{font-size:11px;font-weight:600;white-space:nowrap}
.cd2strm-page .cd2strm-st.ok{color:rgb(var(--v-theme-success,46,125,50))}
.cd2strm-page .cd2strm-st.skip{opacity:.6}
.cd2strm-page .cd2strm-st.bad{color:rgb(var(--v-theme-error,198,40,40))}
.cd2strm-page .cd2strm-res{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:11.5px;opacity:.8;
max-width:300px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cd2strm-page .cd2strm-bad{color:rgb(var(--v-theme-error,198,40,40))}
.cd2strm-page .cd2strm-skip{color:rgba(var(--v-theme-on-surface,0,0,0),.55)}
.cd2strm-page .cd2strm-chip{display:inline-block;border-radius:999px;padding:0 8px;font-size:11px;line-height:18px;
vertical-align:middle;white-space:nowrap;background:rgba(var(--v-theme-on-surface,0,0,0),.07);opacity:.75}
.cd2strm-page .cd2strm-chip.primary{background:rgba(var(--v-theme-primary,103,80,164),.14);
color:rgb(var(--v-theme-primary,103,80,164));opacity:1}
.cd2strm-page .cd2strm-chip.info{background:rgba(var(--v-theme-info,2,119,189),.14);
color:rgb(var(--v-theme-info,2,119,189));opacity:1}
.cd2strm-page .cd2strm-chip.success{background:rgba(var(--v-theme-success,46,125,50),.14);
color:rgb(var(--v-theme-success,46,125,50));opacity:1}
.cd2strm-page .cd2strm-chip.error,.cd2strm-page .cd2strm-chip.bad{background:rgba(var(--v-theme-error,198,40,40),.14);
color:rgb(var(--v-theme-error,198,40,40));opacity:1}
.cd2strm-page .cd2strm-chip.warn{background:rgba(var(--v-theme-warning,237,108,2),.16);
color:rgb(var(--v-theme-warning,237,108,2));opacity:1}
.cd2strm-page .cd2strm-chip.grey{background:rgba(var(--v-theme-on-surface,0,0,0),.07);opacity:.7}
.cd2strm-page .cd2strm-count{font-size:11px;opacity:.6}
.cd2strm-page .cd2strm-pager{display:flex;align-items:center;justify-content:flex-end;gap:6px;flex-wrap:wrap;
margin-top:12px;font-size:12px}
.cd2strm-page .cd2strm-pager .lab{opacity:.6}
.cd2strm-page .cd2strm-pager .size{padding:1px 7px;border-radius:6px;cursor:pointer;opacity:.7}
.cd2strm-page .cd2strm-pager .size.on{background:rgba(var(--v-theme-primary,103,80,164),.14);
color:rgb(var(--v-theme-primary,103,80,164));font-weight:600;opacity:1}
.cd2strm-page .cd2strm-pager .nav{border:1px solid rgba(var(--v-theme-on-surface,0,0,0),.16);
border-radius:6px;padding:0 8px;cursor:pointer}
.cd2strm-page .cd2strm-pager .pos{opacity:.6}
.cd2strm-page .cd2strm-enable-head{display:inline-flex;align-items:center;flex:0 0 auto;margin-left:8px}
.cd2strm-page .cd2strm-enable-head .v-switch{margin:0}
.cd2strm-page .cd2strm-enable-head .v-selection-control--density-compact{--v-selection-control-size:22px}
.cd2strm-page .cd2strm-tr.mir{grid-template-columns:max-content max-content max-content minmax(0,1.7fr) minmax(0,0.9fr)}
@media (max-width:900px){
.cd2strm-page .cd2strm-kpis{grid-template-columns:repeat(4,minmax(0,1fr))}
.cd2strm-page .cd2strm-tr.ev{grid-template-columns:max-content max-content minmax(0,1fr) max-content}
.cd2strm-page .cd2strm-tr.rec{grid-template-columns:max-content max-content minmax(0,1fr)}
.cd2strm-page .cd2strm-tr.org{grid-template-columns:max-content max-content max-content minmax(0,1.7fr) minmax(0,0.9fr)}
.cd2strm-page .cd2strm-tr.ign{grid-template-columns:max-content max-content minmax(0,1fr) minmax(0,1fr) max-content}
.cd2strm-page .cd2strm-tr.mir{grid-template-columns:max-content max-content max-content minmax(0,1fr) minmax(0,0.9fr)}
}
"""


def _style_block() -> Dict[str, Any]:
    """注入本插件页面的受控样式（PageRender 会用 innerHTML 渲染该 style 节点）。"""
    return {"component": "style", "html": PAGE_CSS}


# 字段说明文案：键名同时是浮层类名（cd2strm-tip-<键>），见 _field_tip_css()。
# 图标紧贴字段标题、悬停 0 延迟显示；文案只在配置页使用。
FIELD_TIPS: Dict[str, str] = {
    # 全局卡片
    "g-onlyonce": "保存配置后立刻对所有目录组做一次扫描，执行完自动复位为关闭",
    "g-global_schedule_enabled": "按间隔自动全量扫描所有开启「本组定时扫描」的目录组",
    "g-global_schedule_hours": "自动扫描的间隔小时数（1～168）",
    "g-notify": "是否推送通知到 MoviePilot 已配置的消息渠道",
    "g-notify_only_matched": "开启后详情页隐藏「未匹配」通知卡片与相关计数",
    # STRM 同步：目录
    "r-media_dir": "CD2 通知里落在这个目录（含子目录）的变更才会被本组处理；填容器内路径，例如 /mnt/cd2-mount/115/media/电视剧/国产剧",
    "r-local_dir": "strm / 软链接生成到这里，目录结构按源目录的相对路径镜像；建议放在挂载之外的盘上",
    "r-exclude_dirs": "每行一条绝对路径；命中的变更不生成链接、也不同步元数据",
    # STRM 同步：扫描方式
    "r-process_mode": "精确＝只处理通知里那一个文件（推荐）；目录扫描＝收到通知后整目录比对，慢但能补齐漏网文件",
    "r-update_link": "目标已存在时是否按源文件重新生成 / 刷新（关闭后已存在的链接不再改动）",
    "r-update_metadata": "是否把与视频同名的元数据（nfo / 字幕 / 图片）一起同步到目的目录",
    "r-schedule_enabled": "勾选后本组参与全局定时扫描（由「启用定时扫描」与「扫描间隔」驱动）",
    # STRM 同步：元数据
    "r-metadata_mode": "本地＝从挂载盘复制（快）；云端＝经 CD2 API 下载（慢，但不受挂载可见性影响）",
    "r-metadata_overwrite": "仅在未勾选「跳过已存在元数据」时生效：勾选后比较内容，有变化才重写",
    "r-metadata_skip": "优先级最高：勾选后，目的目录里已存在的同名元数据永不重写",
    "r-metadata_exts": "逗号分隔，例如 .nfo,.srt,.ass；决定哪些文件被当作元数据一起同步",
    # STRM 同步：链接与后缀
    "r-link_mode": "strm＝生成 .strm 文本文件（播放器按内容寻址）；symlink＝生成真实软链接",
    "r-strm_mode": "云端直链＝strm 内容写成可直链播放的 URL；挂载路径＝写容器内挂载路径（仅本机播放器可用）",
    "r-strm_template": "可用变量：{host} strm 播放主机、{path} URL 编码后的云盘路径、{raw} 未编码云盘路径、{local} 挂载路径；模板非法会自动回退默认",
    "r-link_exts": "逗号分隔的视频后缀白名单，例如 .mkv,.mp4；只有这些后缀才会生成链接",
    "r-link_min_size": "0＝不限制；小于该体积的视频只计入「跳过」，不生成链接",
    # STRM 同步：挂载与高级
    "r-mount_type": "通知路径换算成容器内路径时使用的根：cd2 用 CD2 根目录、alist 用 alist 根目录、local 表示源路径本身就是容器内路径",
    "r-cloud_host": "仅「strm 内容＝云端直链」时使用；填 CD2 的播放主机，例如 192.168.3.111:19798",
    "r-cd2_root": "把 CD2 通知里的内部路径换算成容器路径的挂载前缀，例如 /mnt/cd2-mount",
    "r-alist_root": "挂载类型为 alist 时使用的挂载前缀",
    # STRM 同步：清理与联动
    "r-clean_invalid_dir": "全量扫描时，删除目的目录里已无对应源目录的空目录",
    "r-clean_invalid_link": "全量扫描时，删除源文件已不存在的链接文件",
    "r-clean_invalid_metadata": "全量扫描时，删除源文件已不存在的元数据文件",
    "r-on_delete_remove_link": "源端删除事件发生时，是否联动删除目的端对应的链接",
    "r-on_delete_remove_metadata": "源端删除事件发生时，是否联动删除目的端对应的元数据",
    # 媒体整理
    "o-src": "CD2 通知里落在这个目录（含子目录）的变更才会交给整理链",
    "o-dst": "必须与 MoviePilot「目录配置」里的 library_path 完全一致，否则会走另一套行为（强制重命名、不发入库通知、同名不覆盖）",
    "o-cd2_root": "把 CD2 通知里的内部路径换算成容器路径的挂载前缀，例如 /mnt/cd2-mount",
    "o-exclude_dirs": "每行一条绝对路径；命中的变更不交给整理链",
    "o-notify": "整理完成后推送结果通知（含媒体名、文件名与失败原因）",
    # 镜像移动
    "d-path1": "监听目录：它里面发生删除时，触发一次镜像移动",
    "d-path2": "镜像目录：监听目录里删了什么，就把这里的对应对象移到回收站",
    "d-path3": "回收站：从镜像目录移过来的文件 / 目录放这里，同名会加时间戳",
    "d-cd2_root": "把 CD2 通知里的内部路径换算成容器路径的挂载前缀，例如 /mnt/cd2-mount",
    "d-media_exts": "仅用于把监听目录里的 .strm 换算成镜像目录中的视频文件，不参与保护判定",
    "d-protect": "四种写法，每行一条：文件夹名（如 花絮）、无后缀文件名（如 README）、.后缀（如 .nfo）、文件名+后缀（如 poster.jpg）；命中者留在镜像目录不移动",
    "d-notify": "镜像移动完成后推送结果通知",
}


def _field_tip_css() -> str:
    """按字段说明生成浮层内容规则：每个字段一条 ::after 的 content。"""
    rules: List[str] = []
    for key, text in FIELD_TIPS.items():
        safe = str(text).replace('"', "'")
        rules.append(f'.cd2strm-form .cd2strm-tip-{key}::after{{content:"{safe}"}}')
    return "\n".join(rules)


# 配置页专用样式（C 紧凑表格式）。注入的 CSS 在本次 SPA 会话中常驻，
# 因此所有选择器都限定在 .cd2strm-form 内，避免影响宿主其它页面。
_FORM_CSS_BASE = """
/* 卡片与分区一律不做 overflow 裁剪：字段说明浮层挂在分区内部，裁剪会把靠底部的浮层切掉 */
.cd2strm-form .cd2strm-card{border:1px solid rgba(var(--v-theme-on-surface,0,0,0),.14);border-radius:8px;
margin-bottom:10px}
.cd2strm-form .cd2strm-chead{display:flex;align-items:center;gap:8px;padding:7px 12px;font-size:13px;
font-weight:600;border-bottom:1px solid rgba(var(--v-theme-on-surface,0,0,0),.10);
border-radius:7px 7px 0 0;
background:rgba(var(--v-theme-on-surface,0,0,0),.03)}
.cd2strm-form .cd2strm-stripe{width:4px;height:14px;border-radius:2px;
background:rgb(var(--v-theme-primary,103,80,164));opacity:1}
.cd2strm-form .cd2strm-cbody{padding:6px 8px 8px}
.cd2strm-form .cd2strm-sec{margin-top:6px;border:1px solid rgba(var(--v-theme-on-surface,0,0,0),.14);
border-radius:8px}
.cd2strm-form .cd2strm-sec:first-child{margin-top:0}
.cd2strm-form .cd2strm-fsec{display:flex;align-items:center;gap:8px;padding:6px 10px;font-size:12.5px;
font-weight:600;letter-spacing:0;text-transform:none;border-bottom:1px solid rgba(var(--v-theme-on-surface,0,0,0),.10);
border-radius:7px 7px 0 0;
background:rgba(var(--v-theme-on-surface,0,0,0),.03)}
.cd2strm-form .cd2strm-fsec .v-switch{--v-input-control-height:auto;min-height:22px}
.cd2strm-form .cd2strm-fsec .v-selection-control--density-compact{--v-selection-control-size:22px}
/* 分区色条改用真实元素 span.cd2strm-stripe（见 _form_section），避免伪元素在无 CSS 环境下丢失 */
/* 配置页视图切换标签（class 由表达式驱动高亮） */
.cd2strm-form .cd2strm-view-tab{display:inline-block;font-size:12.5px;line-height:26px;padding:0 14px;
border-radius:999px;cursor:pointer;border:1px solid rgba(var(--v-theme-on-surface,0,0,0),.14);
color:rgba(var(--v-theme-on-surface,0,0,0),.75)}
.cd2strm-form .cd2strm-view-tab-on{background:rgba(var(--v-theme-primary,103,80,164),.14);
color:rgb(var(--v-theme-primary,103,80,164));border-color:transparent;font-weight:600}
/* 分区可折叠：去掉原生三角，右侧自绘箭头；收起时去掉标题栏底边线 */
.cd2strm-form details.cd2strm-sec>summary.cd2strm-fsec{list-style:none;cursor:pointer}
.cd2strm-form details.cd2strm-sec>summary.cd2strm-fsec::-webkit-details-marker{display:none}
.cd2strm-form details.cd2strm-sec>summary.cd2strm-fsec::after{content:"\\25BE";margin-left:auto;
font-size:10px;opacity:.5}
.cd2strm-form details.cd2strm-sec:not([open])>summary.cd2strm-fsec{border-bottom:none}
.cd2strm-form details.cd2strm-sec:not([open])>summary.cd2strm-fsec::after{content:"\\25B8"}
.cd2strm-form .cd2strm-sec-body{border:none;border-radius:0}
/* 不裁剪之后由行自身补圆角，保证分区底角仍是圆角 */
.cd2strm-form .cd2strm-sec-body>:last-child{border-radius:0 0 7px 7px}
/* 字段说明：图标紧贴字段标题，鼠标悬停 0 延迟显示（纯 CSS，不用原生 title） */
.cd2strm-form .cd2strm-flab{display:flex;align-items:center;gap:5px;min-width:0}
.cd2strm-form .cd2strm-fi{display:inline-block;width:13px;height:13px;flex:0 0 auto;
background-repeat:no-repeat;background-position:center;background-size:contain;opacity:.45}
.cd2strm-form .cd2strm-tip:hover .cd2strm-fi{opacity:.9}
.cd2strm-form .cd2strm-tip{position:relative}
.cd2strm-form .cd2strm-tip::after{content:"";position:absolute;left:0;bottom:calc(100% + 7px);z-index:30;
width:26rem;max-width:58vw;white-space:normal;padding:7px 10px;border-radius:6px;
font-size:12px;font-weight:400;line-height:1.55;letter-spacing:0;
background:rgba(32,36,42,.96);color:#fff;box-shadow:0 4px 14px rgba(0,0,0,.28);
opacity:0;visibility:hidden;pointer-events:none;transition:none}
.cd2strm-form .cd2strm-tip:hover::after{opacity:1;visibility:visible}
.cd2strm-form .cd2strm-frow{display:grid;grid-template-columns:160px minmax(0,1fr);gap:10px;
align-items:center;padding:2px 10px;border-bottom:1px solid rgba(var(--v-theme-on-surface,0,0,0),.07)}
.cd2strm-form .cd2strm-frow:nth-child(even){background:rgba(var(--v-theme-on-surface,0,0,0),.02)}
.cd2strm-form .cd2strm-frow:last-child{border-bottom:none}
.cd2strm-form .cd2strm-flab{font-size:12.5px;line-height:1.45}
.cd2strm-form .cd2strm-fctl{min-width:0}
.cd2strm-form .cd2strm-fctl .v-input,.cd2strm-form .cd2strm-fctl .v-field{font-size:12.5px}
/* 紧凑化：compact 密度下的文本控件高度由 Vuetify 默认的 40px 压到 32px（开关不受影响），
   并把无标签字段的上下内距清零以保持文字垂直居中 */
.cd2strm-form .v-input--density-compact:not(.v-switch){--v-input-control-height:32px;--v-input-padding-top:6px}
.cd2strm-form .v-field--no-label{--v-field-padding-top:0px;--v-field-padding-bottom:0px}
.cd2strm-form .cd2strm-mono input,.cd2strm-form .cd2strm-mono textarea,
.cd2strm-form .cd2strm-mono .v-field__input{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12px}
.cd2strm-form details.cd2strm-rule-fold{border:1px solid rgba(var(--v-theme-on-surface,0,0,0),.14);
border-radius:10px;margin-bottom:10px}
.cd2strm-form details.cd2strm-rule-fold>summary{list-style:none;cursor:pointer;display:flex;
align-items:center;gap:8px;padding:7px 12px;background:rgba(var(--v-theme-on-surface,0,0,0),.03);
border-radius:9px}
.cd2strm-form details.cd2strm-rule-fold[open]>summary{border-radius:9px 9px 0 0}
.cd2strm-form details.cd2strm-rule-fold>summary::-webkit-details-marker{display:none}
.cd2strm-form details.cd2strm-rule-fold>summary::before{content:"\\25B8";font-size:10px;opacity:.55}
.cd2strm-form details.cd2strm-rule-fold[open]>summary::before{content:"\\25BE"}
.cd2strm-form .cd2strm-rmeta{display:flex;flex-direction:column;gap:2px;min-width:0;flex:1}
.cd2strm-form .cd2strm-rname{font-size:14px;font-weight:600;display:flex;align-items:center;gap:6px;
flex-wrap:wrap}
.cd2strm-form .cd2strm-rpath{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:11.5px;
white-space:nowrap;overflow:hidden;text-overflow:ellipsis;opacity:.65}
.cd2strm-form .cd2strm-rbody{padding:6px 10px 8px}
.cd2strm-form .cd2strm-chip{display:inline-block;border-radius:999px;padding:0 8px;font-size:11px;
line-height:18px;vertical-align:middle;white-space:nowrap;font-weight:400;
background:rgba(var(--v-theme-on-surface,0,0,0),.07);opacity:.8}
.cd2strm-form .cd2strm-chip.primary{background:rgba(var(--v-theme-primary,103,80,164),.14);
color:rgb(var(--v-theme-primary,103,80,164));opacity:1}
@media (max-width:900px){
.cd2strm-form .cd2strm-frow{grid-template-columns:108px minmax(0,1fr);gap:8px}
}
""" + _field_tip_css()

# 配置页样式（基础规则 + 每个字段的说明浮层）
FORM_CSS = _FORM_CSS_BASE


def _form_style_block() -> Dict[str, Any]:
    """把配置页样式注入配置表单。

    用 text 而不是 html：FormRender 处理 html 时会在外层 style 里再套一个 style，
    嵌套 style 在部分浏览器/WebView 下不生效；用 text 只生成单个 style 元素，全平台通用。
    关键视觉另有内联样式兜底（见 _apply_inline_styles），这里的 CSS 只做增强。
    """
    return {"component": "style", "text": FORM_CSS}


# 字段说明图标（information-outline 的 SVG 内联 data URI：不依赖宿主的 mdi 图标集与字体）
_TIP_ICON = (
    "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'>"
    "<path d='M11 9h2V7h-2m1 13c-4.41 0-8-3.59-8-8s3.59-8 8-8s8 3.59 8 8s-3.59 8-8 8"
    "m0-18A10 10 0 0 0 2 12a10 10 0 0 0 10 10a10 10 0 0 0 10-10A10 10 0 0 0 12 2"
    "m-1 15h2v-6h-2z' fill='%233a3f45'/></svg>"
)

# 关键视觉的内联样式（不依赖注入的 CSS，任何环境都能看到边框 / 底色 / 色条）
_BORDER = "1px solid rgba(var(--v-theme-on-surface,0,0,0),.14)"
_LINE = "1px solid rgba(var(--v-theme-on-surface,0,0,0),.10)"
_ROW_LINE = "1px solid rgba(var(--v-theme-on-surface,0,0,0),.07)"
_TINT = "rgba(var(--v-theme-on-surface,0,0,0),.03)"
_PRIMARY = "rgb(var(--v-theme-primary,103,80,164))"

INLINE_STYLES: Dict[str, Dict[str, Any]] = {
    "cd2strm-card": {
        "border": _BORDER,
        "border-radius": "8px",
        "margin-bottom": "10px",
    },
    "cd2strm-chead": {
        "display": "flex",
        "align-items": "center",
        "gap": "8px",
        "padding": "7px 12px",
        "font-size": "13px",
        "font-weight": "600",
        "border-bottom": _LINE,
        "border-radius": "7px 7px 0 0",
        "background": _TINT,
    },
    "cd2strm-stripe": {
        "flex": "none",
        "display": "inline-block",
        "width": "4px",
        "height": "14px",
        "border-radius": "2px",
        "background": _PRIMARY,
    },
    "cd2strm-cbody": {"padding": "6px 8px 8px"},
    "cd2strm-sec": {
        "margin-top": "6px",
        "border": _BORDER,
        "border-radius": "8px",
    },
    "cd2strm-fsec": {
        "display": "flex",
        "align-items": "center",
        "gap": "8px",
        "padding": "6px 10px",
        "font-size": "12.5px",
        "font-weight": "600",
        "letter-spacing": "0",
        "text-transform": "none",
        "border-bottom": _LINE,
        "border-radius": "7px 7px 0 0",
        "background": _TINT,
        "cursor": "pointer",
        "list-style": "none",
    },
    "cd2strm-sec-body": {"border": "none", "border-radius": "0"},
    "cd2strm-frow": {
        "display": "grid",
        "grid-template-columns": "160px minmax(0,1fr)",
        "gap": "10px",
        "align-items": "center",
        "padding": "2px 10px",
        "border-bottom": _ROW_LINE,
    },
    "cd2strm-flab": {
        "display": "flex",
        "align-items": "center",
        "gap": "5px",
        "min-width": "0",
        "font-size": "12.5px",
        "line-height": "1.45",
    },
    "cd2strm-tip": {"position": "relative"},
    "cd2strm-fi": {
        "flex": "0 0 auto",
        "display": "inline-block",
        "width": "13px",
        "height": "13px",
        "opacity": ".45",
        "background-repeat": "no-repeat",
        "background-position": "center",
        "background-size": "contain",
        "background-image": f'url("{_TIP_ICON}")',
    },
    "cd2strm-fctl": {"min-width": "0"},
    "cd2strm-view-tab": {
        "display": "inline-block",
        "font-size": "12.5px",
        "line-height": "26px",
        "padding": "0 14px",
        "border-radius": "999px",
        "cursor": "pointer",
        "border": _BORDER,
        "color": "rgba(var(--v-theme-on-surface,0,0,0),.75)",
    },
    "cd2strm-view-tab-on": {
        "background": "rgba(var(--v-theme-primary,103,80,164),.14)",
        "color": _PRIMARY,
        "border-color": "transparent",
        "font-weight": "600",
    },
    "cd2strm-mono": {"font-family": "ui-monospace,Menlo,Consolas,monospace"},
    "cd2strm-rbody": {"padding": "6px 10px 8px"},
    "cd2strm-rmeta": {
        "display": "flex",
        "flex-direction": "column",
        "gap": "2px",
        "min-width": "0",
        "flex": "1",
    },
    "cd2strm-rname": {
        "font-size": "14px",
        "font-weight": "600",
        "display": "flex",
        "align-items": "center",
        "gap": "6px",
        "flex-wrap": "wrap",
    },
    "cd2strm-rpath": {
        "font-family": "ui-monospace,Menlo,Consolas,monospace",
        "font-size": "11.5px",
        "white-space": "nowrap",
        "overflow": "hidden",
        "text-overflow": "ellipsis",
        "opacity": ".65",
    },
    "cd2strm-chip": {
        "display": "inline-block",
        "border-radius": "999px",
        "padding": "0 8px",
        "font-size": "11px",
        "line-height": "18px",
        "vertical-align": "middle",
        "white-space": "nowrap",
        "background": "rgba(var(--v-theme-on-surface,0,0,0),.07)",
    },
    "cd2strm-rule-fold": {
        "border": _BORDER,
        "border-radius": "8px",
        "margin-bottom": "10px",
    },
}

# 控件紧凑化：compact 密度下把 Vuetify 默认的 40px 控制高度压到 32px
CONTROL_STYLE: Dict[str, Any] = {
    "--v-input-control-height": "32px",
    "--v-input-padding-top": "6px",
    "font-size": "12.5px",
}


def _apply_inline_styles(node: Any) -> Any:
    """递归给表单节点补内联样式，保证宿主不应用注入 CSS 时仍有边框 / 底色 / 紧凑高度。"""
    if isinstance(node, list):
        for item in node:
            _apply_inline_styles(item)
        return node
    if not isinstance(node, dict):
        return node
    props = node.get("props")
    if isinstance(props, dict):
        class_names = str(props.get("class") or "").split()
        merged: Dict[str, Any] = {}
        for name in class_names:
            merged.update(INLINE_STYLES.get(name, {}))
        # 视图切换标签的 class 是 {{表达式}}（高亮态运行期才确定），基础样式按关键字兜底
        if "cd2strm-view-tab" in str(props.get("class") or ""):
            merged.update(INLINE_STYLES.get("cd2strm-view-tab", {}))
        if "cd2strm-chip" in class_names and "primary" in class_names:
            merged.update(
                {"background": "rgba(var(--v-theme-primary,103,80,164),.14)", "color": _PRIMARY}
            )
        if node.get("component") in ("VTextField", "VSelect", "VTextarea"):
            merged.update(CONTROL_STYLE)
        existing = props.get("style")
        if isinstance(existing, dict):
            merged.update(existing)
        if merged:
            props["style"] = merged
    content = node.get("content")
    if isinstance(content, list):
        _apply_inline_styles(content)
        if str((props or {}).get("class") or "") == "cd2strm-sec-body" and content:
            last = content[-1]
            last_style = (last.get("props") or {}).get("style") if isinstance(last, dict) else None
            if isinstance(last_style, dict):
                last_style.pop("border-bottom", None)
    return node


def _chip(text: str, color: str = "primary") -> Dict[str, Any]:
    """构造小徽章（自绘样式，行高可控）。"""
    return {
        "component": "span",
        "props": {"class": f"cd2strm-chip {color}"},
        "text": text,
    }


# CD2 变更类型的中文名与配色（页面展示用）
CHANGE_LABELS = {"create": "新增", "delete": "删除", "rename": "改名"}
CHANGE_TONES = {"create": "primary", "delete": "error", "rename": "info"}


def _change_chip(change_type: str) -> Dict[str, Any]:
    """把 CD2 变更类型渲染成中文徽章。"""
    key = str(change_type or "")
    return _chip(CHANGE_LABELS.get(key, key or "变更"), CHANGE_TONES.get(key, "grey"))


def _kpi(value: str, label: str, tone: str = "", icon: str = "") -> Dict[str, Any]:
    """构造一个 KPI 小格（数字大、标签小）。"""
    cell_class = "cd2strm-kpi"
    if tone:
        cell_class = f"{cell_class} {tone}"
    if icon:
        head: Dict[str, Any] = {
            "component": "span",
            "props": {"class": "n"},
            "text": icon,
        }
    else:
        head = {"component": "div", "props": {"class": "n"}, "text": value}
    return {
        "component": "div",
        "props": {"class": cell_class},
        "content": [
            head,
            {"component": "div", "props": {"class": "l"}, "text": label},
        ],
    }


def _path_cell(label: str, value: str) -> Dict[str, Any]:
    """构造路径显示单元（等宽、单行省略、悬停显示完整路径）。"""
    return {
        "component": "div",
        "props": {"class": "cd2strm-path"},
        "content": [
            {"component": "div", "props": {"class": "l"}, "text": label},
            {
                "component": "div",
                "props": {"class": "v", "title": value},
                "text": value,
            },
        ],
    }


def _field_label(label: str, tip: str = "") -> Dict[str, Any]:
    """字段标签：有说明时在文字后紧跟一个说明图标（鼠标悬停 0 延迟显示说明文本）。"""
    if not tip:
        return {"component": "div", "props": {"class": "cd2strm-flab"}, "text": label}
    return {
        "component": "div",
        "props": {"class": f"cd2strm-flab cd2strm-tip cd2strm-tip-{tip}"},
        "content": [
            {"component": "span", "text": label},
            {"component": "span", "props": {"class": "cd2strm-fi"}},
        ],
    }


def _form_row(
    label: str, control: Dict[str, Any], mono: bool = False, tip: str = ""
) -> Dict[str, Any]:
    """配置页的一行：左侧字段标签 + 右侧控件（tip 非空时标签后带说明图标）。"""
    control_class = "cd2strm-fctl cd2strm-mono" if mono else "cd2strm-fctl"
    return {
        "component": "div",
        "props": {"class": "cd2strm-frow"},
        "content": [
            _field_label(label, tip),
            {"component": "div", "props": {"class": control_class}, "content": [control]},
        ],
    }


def _form_row_actions(
    label: str, control: Dict[str, Any], actions: List[Dict[str, Any]], tip: str = ""
) -> Dict[str, Any]:
    """配置页的一行：左侧标签 + 右侧控件 + 控件右侧的动作按钮（例如「＋」「－」）。"""
    return {
        "component": "div",
        "props": {"class": "cd2strm-frow"},
        "content": [
            _field_label(label, tip),
            {
                "component": "div",
                "props": {
                    "class": "cd2strm-fctl",
                    "style": {"display": "flex", "align-items": "center"},
                },
                "content": [control, *actions],
            },
        ],
    }


def _exclude_button(text: str, title: str, script: str) -> Dict[str, Any]:
    """排除目录行右侧的小按钮：原生 span + onClick 字符串改表单模型。"""
    return {
        "component": "span",
        "props": {
            "class": "cd2strm-ex-btn",
            "title": title,
            "onClick": script,
            "style": {
                "display": "inline-flex",
                "align-items": "center",
                "justify-content": "center",
                "width": "24px",
                "height": "24px",
                "margin-left": "6px",
                "border-radius": "6px",
                "border": "1px solid rgba(var(--v-theme-on-surface,0,0,0),.16)",
                "cursor": "pointer",
                "font-size": "14px",
                "line-height": "1",
                "flex": "0 0 auto",
            },
        },
        "text": text,
    }


def _exclude_row(index: int) -> Dict[str, Any]:
    """全局排除目录的一行：输入框 + 「＋」（第 2 行起另有「－」）。

    行显隐 = 「计数器 >= 行号」**或**「上一行已填内容」：前者由「＋」驱动，
    后者只依赖文本框的模型绑定（与整张表单同一条响应式路径，必然生效），
    因此即使「＋」被拦住/失效，往下填一行也会自动带出下一行。
    表达式带 typeof 守护，避免字段缺失时 FormRender 整页渲染失败。
    """
    count_expr = "(typeof exclude_row_count === 'undefined' ? 1 : exclude_row_count)"
    control = {
        "component": "VTextField",
        "props": {
            "model": f"gx_{index}",
            "density": "compact",
            "variant": "outlined",
            "hide-details": True,
            "placeholder": "/mnt/cd2-mount/115/media/不想生成 strm 的目录",
            # flex-basis 用 0% 并把宽度交回 flex，避免 Vuetify 的 100% 宽度盖住右侧按钮
            "style": {"flex": "1 1 0%", "min-width": "0", "width": "auto"},
        },
    }
    actions = [
        _exclude_button(
            "＋",
            "再加一行排除目录",
            "(event) => { var c = %s; exclude_row_count = (c >= %d ? %d : c + 1); }"
            % (count_expr, MAX_GLOBAL_EXCLUDES, MAX_GLOBAL_EXCLUDES),
        )
    ]
    if index >= 2:
        actions.append(
            _exclude_button(
                "－",
                "收起本行（清空该行内容）",
                "(event) => { gx_%d = ''; var c = %s; if (c <= %d) { exclude_row_count = (c <= 1 ? 1 : c - 1); } }"
                % (index, count_expr, index),
            )
        )
    row = _form_row_actions(f"排除目录 {index}", control, actions)
    if index >= 2:
        # 关键：style 必须排在 show 之前。宿主的 props 编译是按插入顺序遍历的，
        # show 分支写的是 n.style.display；若 style 排在 show 之后，会把 display 覆盖掉，
        # 于是所有行都会显示出来（2026-09-14 实机踩坑）。
        row["props"]["style"] = {"display": "grid"}
        prev_expr = f"(typeof gx_{index - 1} !== 'undefined' && gx_{index - 1} !== '')"
        row["props"]["show"] = "{{ %s >= %d || %s }}" % (count_expr, index, prev_expr)
    return row


def _global_exclude_card() -> Dict[str, Any]:
    """配置页最上方的「全局排除目录」卡片：命中的路径不生成 strm（对所有目录组生效）。"""
    return _form_card(
        "全局排除目录",
        [
            _form_section(
                "对所有目录组生效（命中的路径不生成 strm）",
                [_exclude_row(index) for index in range(1, MAX_GLOBAL_EXCLUDES + 1)],
            )
        ],
    )


def _form_section(
    title: str,
    rows: List[Dict[str, Any]],
    header_extra: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """配置页的一个分区：可折叠的原生 details（标题栏 + 分区内的字段行）。

    header_extra 用于在标题右侧紧跟放置控件（例如 CloudDrive 地址的启用开关）。
    默认展开（open=True）；折叠状态不持久化，重新打开配置页即回到默认展开。
    色条用真实元素而不用伪元素，这样在没有 CSS 的环境下也能显示。
    """
    stripe = {"component": "span", "props": {"class": "cd2strm-stripe"}}
    if header_extra:
        head: Dict[str, Any] = {
            "component": "summary",
            "props": {"class": "cd2strm-fsec"},
            "content": [stripe, {"component": "span", "text": title}, *header_extra],
        }
    else:
        head = {
            "component": "summary",
            "props": {"class": "cd2strm-fsec"},
            "content": [stripe, {"component": "span", "text": title}],
        }
    return {
        "component": "details",
        "props": {"class": "cd2strm-sec", "open": True},
        "content": [
            head,
            {"component": "div", "props": {"class": "cd2strm-sec-body"}, "content": rows},
        ],
    }


def _header_switch(model: str) -> Dict[str, Any]:
    """构造分区标题右侧的小开关（用于 CloudDrive 地址的启用开关）。"""
    return {
        "component": "VSwitch",
        "props": {
            "model": model,
            "density": "compact",
            "hide-details": True,
            "style": {"flex": "none", "margin-left": "2px"},
        },
    }


def _form_card(title: str, content: List[Dict[str, Any]]) -> Dict[str, Any]:
    """配置页的一张卡片：标题栏（色条 + 标题）与卡片内容。"""
    return {
        "component": "div",
        "props": {"class": "cd2strm-card"},
        "content": [
            {
                "component": "div",
                "props": {"class": "cd2strm-chead"},
                "content": [
                    {"component": "span", "props": {"class": "cd2strm-stripe"}},
                    {"component": "span", "text": title},
                ],
            },
            {"component": "div", "props": {"class": "cd2strm-cbody"}, "content": content},
        ],
    }


# 折叠头徽章用的简称
CHIP_LABELS: Dict[str, Dict[str, str]] = {
    "process_mode": {"precise": "精确", "scan": "目录扫描"},
    "link_mode": {"strm": "strm 文件", "symlink": "软链接"},
    "strm_mode": {"cloud": "云端", "local": "本地"},
}


def _chip_label(field: str, value: Any) -> str:
    """取折叠头徽章用的简要名称（找不到时回退为原值）。"""
    return CHIP_LABELS.get(field, {}).get(str(value or ""), str(value or "未设置"))


def _switch(model: str, label: str, tip: str = "") -> Dict[str, Any]:
    """构造开关行（字段名只在左侧显示，开关本身不带文字）。"""
    control = {
        "component": "VSwitch",
        "props": {"model": model, "density": "compact", "hide-details": True},
    }
    return _form_row(label, control, tip=tip)


def _enable_row(
    plugin_id: str, api_token: str, scope: str, index: int, enabled: bool
) -> Dict[str, Any]:
    """详情页每个路径组折叠头右侧的启用开关（点击后写配置并整页重载）。"""
    return {
        "component": "div",
        "props": {"class": "cd2strm-enable-head"},
        "content": [
            {
                "component": "VSwitch",
                "props": {
                    "model-value": bool(enabled),
                    "color": "primary",
                    "density": "compact",
                    "hide-details": True,
                },
                "events": {
                    "change": {
                        "api": f"plugin/{plugin_id}/toggle?apikey={api_token}",
                        "method": "post",
                        "params": {"scope": scope, "index": index, "enabled": not enabled},
                    }
                },
            }
        ],
    }


def _text(
    model: str,
    label: str,
    hint: str = "",
    password: bool = False,
    mono: bool = False,
    tip: str = "",
) -> Dict[str, Any]:
    """构造单行输入（mono 为真时用等宽字体，适合路径与后缀）。"""
    props: Dict[str, Any] = {
        "model": model,
        "density": "compact",
        "variant": "outlined",
        "hide-details": True,
        "placeholder": hint,
    }
    if password:
        props["type"] = "password"
        props["prepend-inner-icon"] = "mdi-key"
    control = {"component": "VTextField", "props": props}
    return _form_row(label, control, mono=mono, tip=tip)


def _number(
    model: str, label: str, min_value: int = 0, max_value: int = 9999, tip: str = ""
) -> Dict[str, Any]:
    """构造数字输入。"""
    control = {
        "component": "VTextField",
        "props": {
            "model": model,
            "type": "number",
            "min": min_value,
            "max": max_value,
            "density": "compact",
            "variant": "outlined",
            "hide-details": True,
        },
    }
    return _form_row(label, control, tip=tip)


def _select(
    model: str, label: str, items: List[Dict[str, str]], tip: str = ""
) -> Dict[str, Any]:
    """构造下拉选择。"""
    control = {
        "component": "VSelect",
        "props": {
            "model": model,
            "items": items,
            "density": "compact",
            "variant": "outlined",
            "hide-details": True,
        },
    }
    return _form_row(label, control, tip=tip)


def _textarea(model: str, label: str, hint: str = "", tip: str = "") -> Dict[str, Any]:
    """构造多行输入。"""
    control = {
        "component": "VTextarea",
        "props": {
            "model": model,
            "rows": 2,
            "density": "compact",
            "variant": "outlined",
            "hide-details": True,
            "placeholder": hint,
        },
    }
    return _form_row(label, control, tip=tip)





def build_form(
    config: Dict[str, Any],
    rules: List[SyncRule],
    organize_rules: Optional[List[OrganizeRule]] = None,
    mirror_rules: Optional[List[MirrorRule]] = None,
) -> Dict[str, Any]:
    """构建插件配置表单。

    顶部是视图菜单（STRM 同步配置 / 媒体整理配置 / 镜像移动配置），各组内容用 show 表达式切换：
    配置页（FormRender）不支持 events，用表单字段 config_view 驱动显示是最稳妥的切法。
    """
    organize_rules = organize_rules or []
    mirror_rules = mirror_rules or []
    sync_content: List[Dict[str, Any]] = [
        _global_exclude_card(),
        _enabled_card(),
        _connection_card(config),
        _schedule_card(),
        _run_card(),
    ]
    for index, rule in enumerate(rules):
        sync_content.append(_rule_fold(index, rule))
    organize_content: List[Dict[str, Any]] = [_organize_card()]
    for index, rule in enumerate(organize_rules):
        organize_content.append(_organize_group_fold(index, rule))
    mirror_content: List[Dict[str, Any]] = [_mirror_card()]
    for index, rule in enumerate(mirror_rules):
        mirror_content.append(_mirror_group_fold(index, rule))
    content: List[Dict[str, Any]] = [
        _form_style_block(),
        _config_view_toggle(),
        _view_wrap("sync", sync_content),
        _view_wrap("organize", organize_content),
        _view_wrap("mirror", mirror_content),
    ]
    form = {"component": "VForm", "props": {"class": "cd2strm-form"}, "content": content}
    return _apply_inline_styles(form)


def _enabled_card() -> Dict[str, Any]:
    """启用插件卡片（含「保存后立即执行一次」）。"""
    return _form_card(
        "启用插件",
        [
            _switch("enabled", "启用插件"),
            _switch("onlyonce", "保存后立即扫描一次", "g-onlyonce"),
        ],
    )


def _connection_card(config: Dict[str, Any]) -> Dict[str, Any]:
    """连接与地址卡片（CloudDrive1 / CloudDrive2，两个地址共用同一套目录规则）。"""
    del config
    return _form_card(
        "连接与地址",
        [
            _form_section(
                "CloudDrive1",
                [
                    _text("cd2_host", "地址", "http://172.17.0.1:19798"),
                    _text("cd2_token", "令牌", "粘贴 API 令牌", password=True),
                ],
                header_extra=[_header_switch("cd2_enabled")],
            ),
            _form_section(
                "CloudDrive2",
                [
                    _text("cd2_host2", "地址", "http://192.168.3.111:19798"),
                    _text("cd2_token2", "令牌", "粘贴 API 令牌", password=True),
                ],
                header_extra=[_header_switch("cd2_enabled2")],
            ),
        ],
    )


def _run_card() -> Dict[str, Any]:
    """通知卡片（只保留通知开关）。"""
    return _form_card(
        "通知",
        [
            _form_section(
                "通知",
                [
                    _switch("notify", "发送通知", "g-notify"),
                    _switch("notify_only_matched", "详情页只显示命中通知", "g-notify_only_matched"),
                ],
            )
        ],
    )


def _schedule_card() -> Dict[str, Any]:
    """全局定时扫描卡片。"""
    return _form_card(
        "定时扫描",
        [
            _form_section(
                "全局",
                [
                    _switch(
                        "global_schedule_enabled", "启用定时扫描", "g-global_schedule_enabled"
                    ),
                    _number(
                        "global_schedule_hours",
                        "扫描间隔（小时）",
                        1,
                        168,
                        "g-global_schedule_hours",
                    ),
                ],
            )
        ],
    )


def _rule_fold(index: int, rule: SyncRule) -> Dict[str, Any]:
    """把单个目录组包成可独立折叠的区块：默认全部折叠，点开才显示设置项。"""
    return {
        "component": "details",
        "props": {"class": "cd2strm-rule-fold"},
        "content": [
            _rule_summary(index, rule),
            _rule_card(index),
        ],
    }


def _rule_summary(index: int, rule: SyncRule) -> Dict[str, Any]:
    """目录组的折叠头：序号、备注名、当前设置徽章与「源目录 → 目的目录」。

    这里取保存后的配置值（不做表单模型绑定），保证渲染一定成功；
    修改并保存后重新打开配置页，折叠头即显示新值。
    """
    title = f"目录组 {index + 1}"
    if rule.name:
        title = f"{title}：{rule.name}"
    paths = f"{rule.media_dir or '未配置源目录'} → {rule.local_dir or '未配置目的目录'}"
    chips = [
        _chip(_chip_label("process_mode", rule.process_mode), "primary"),
        _chip(_chip_label("link_mode", rule.link_mode)),
        _chip(_chip_label("strm_mode", rule.strm_mode)),
        _chip(f"定时扫描{'开' if rule.schedule_enabled else '关'}"),
    ]
    return {
        "component": "summary",
        "props": {"class": "cd2strm-rule-summary"},
        "content": [
            {
                "component": "div",
                "props": {"class": "cd2strm-rmeta"},
                "content": [
                    {
                        "component": "div",
                        "props": {"class": "cd2strm-rname"},
                        "content": [{"component": "span", "text": title}, *chips],
                    },
                    {
                        "component": "div",
                        "props": {"class": "cd2strm-rpath"},
                        "text": paths,
                    },
                ],
            },
        ],
    }


def _rule_card(index: int) -> Dict[str, Any]:
    """单个目录组的设置卡片（6 个分区：目录 / 处理方式 / 元数据 / 链接与后缀 / 挂载与高级 / 清理与联动）。"""
    return {
        "component": "div",
        "props": {"class": "cd2strm-rbody"},
        "content": [
            _form_section(
                "目录",
                [
                    _text(rule_key(index, "name"), "备注名称", "例如：115 电影"),
                    _text(
                        rule_key(index, "media_dir"),
                        "源目录",
                        "/mnt/cd2-mount/115/media",
                        mono=True,
                        tip="r-media_dir",
                    ),
                    _text(
                        rule_key(index, "local_dir"),
                        "目的目录",
                        "/media_auto_symlink/cd2/115/media",
                        mono=True,
                        tip="r-local_dir",
                    ),
                    _textarea(
                        rule_key(index, "exclude_dirs"),
                        "排除目录",
                        "/mnt/cd2-mount/115/media/tg/整理前",
                        tip="r-exclude_dirs",
                    ),
                ],
            ),
            _form_section(
                "扫描方式",
                [
                    _select(
                        rule_key(index, "process_mode"),
                        "扫描方式",
                        PROCESS_MODES,
                        "r-process_mode",
                    ),
                    _switch(rule_key(index, "update_link"), "更新已有链接", "r-update_link"),
                    _switch(
                        rule_key(index, "update_metadata"),
                        "更新已有元数据",
                        "r-update_metadata",
                    ),
                    _switch(
                        rule_key(index, "schedule_enabled"),
                        "本组定时扫描",
                        "r-schedule_enabled",
                    ),
                ],
            ),
            _form_section(
                "元数据",
                [
                    _select(
                        rule_key(index, "metadata_mode"),
                        "元数据来源",
                        METADATA_MODES,
                        "r-metadata_mode",
                    ),
                    _switch(
                        rule_key(index, "metadata_overwrite"),
                        "覆盖已有元数据",
                        "r-metadata_overwrite",
                    ),
                    _switch(
                        rule_key(index, "metadata_skip"),
                        "跳过已存在元数据",
                        "r-metadata_skip",
                    ),
                    _text(
                        rule_key(index, "metadata_exts"),
                        "元数据后缀",
                        DEFAULT_METADATA_EXTS,
                        tip="r-metadata_exts",
                    ),
                ],
            ),
            _form_section(
                "链接与后缀",
                [
                    _select(rule_key(index, "link_mode"), "链接方式", LINK_MODES, "r-link_mode"),
                    _select(rule_key(index, "strm_mode"), "strm 内容", STRM_MODES, "r-strm_mode"),
                    _text(
                        rule_key(index, "strm_template"),
                        "strm 模板",
                        DEFAULT_STRM_TEMPLATE,
                        mono=True,
                        tip="r-strm_template",
                    ),
                    _text(
                        rule_key(index, "link_exts"),
                        "视频后缀",
                        DEFAULT_LINK_EXTS,
                        tip="r-link_exts",
                    ),
                    _number(
                        rule_key(index, "link_min_size"),
                        "生成链接的最小体积（MB）",
                        0,
                        102400,
                        "r-link_min_size",
                    ),
                ],
            ),
            _form_section(
                "挂载与高级",
                [
                    _select(
                        rule_key(index, "mount_type"),
                        "路径映射方式",
                        MOUNT_TYPES,
                        "r-mount_type",
                    ),
                    _text(
                        rule_key(index, "cloud_host"),
                        "strm 播放主机",
                        "192.168.3.111:19798",
                        tip="r-cloud_host",
                    ),
                    _text(
                        rule_key(index, "cd2_root"),
                        "cd2 根目录",
                        "/mnt/cd2-mount",
                        mono=True,
                        tip="r-cd2_root",
                    ),
                    _text(rule_key(index, "alist_root"), "alist 根目录", "", tip="r-alist_root"),
                ],
            ),
            _form_section(
                "清理与联动",
                [
                    _switch(
                        rule_key(index, "clean_invalid_dir"),
                        "清理无效目录",
                        "r-clean_invalid_dir",
                    ),
                    _switch(
                        rule_key(index, "clean_invalid_link"),
                        "清理无效链接",
                        "r-clean_invalid_link",
                    ),
                    _switch(
                        rule_key(index, "clean_invalid_metadata"),
                        "清理无效元数据",
                        "r-clean_invalid_metadata",
                    ),
                    _switch(
                        rule_key(index, "on_delete_remove_link"),
                        "删除时移除链接",
                        "r-on_delete_remove_link",
                    ),
                    _switch(
                        rule_key(index, "on_delete_remove_metadata"),
                        "删除时移除元数据",
                        "r-on_delete_remove_metadata",
                    ),
                ],
            ),
        ],
    }


def _config_view_toggle() -> Dict[str, Any]:
    """配置页顶部的视图菜单：STRM 同步配置 / 媒体整理配置。

    用原生 span + onClick 字符串改表单模型：FormRender 会把 props 里以 on 开头、值为字符串的
    键编译成处理函数（`with(model){ (expr)(event) }`），因此不依赖任何 Vuetify 组件的注册情况
    （实测 VBtnToggle 不支持 items、VTabs 在实机上也没渲染出来）。高亮状态通过 class 表达式驱动。
    """
    def tab(title: str, value: str) -> Dict[str, Any]:
        return {
            "component": "span",
            "props": {
                "class": "{{config_view == '%s' ? 'cd2strm-view-tab cd2strm-view-tab-on' : 'cd2strm-view-tab'}}"
                % value,
                "style": {"margin-right": "6px"},
                "onClick": "(event) => { config_view = '%s'; }" % value,
            },
            "text": title,
        }

    return {
        "component": "div",
        "props": {
            "class": "cd2strm-view-toggle",
            "style": {"margin-bottom": "10px"},
        },
        "content": [
            tab("STRM 同步配置", "sync"),
            tab("媒体整理配置", "organize"),
            tab("镜像移动配置", "mirror"),
        ],
    }


def _view_wrap(view: str, content: List[Dict[str, Any]]) -> Dict[str, Any]:
    """把一个视图的内容包起来，按 config_view 显示/隐藏。"""
    return {
        "component": "div",
        "props": {
            "class": "cd2strm-view",
            "show": "{{config_view == '%s'}}" % view,
        },
        "content": content,
    }


def _organize_card() -> Dict[str, Any]:
    """媒体整理的全局卡片（与 STRM 同步完全隔离）。"""
    return _form_card(
        "媒体整理",
        [
            _form_section(
                "总开关",
                [
                    _switch("organize_enabled", "启用媒体整理"),
                    _switch("organize_notify", "完成后通知"),
                ],
            )
        ],
    )


def _organize_summary(index: int, rule: OrganizeRule) -> Dict[str, Any]:
    """整理组的折叠头：名称、当前设置徽章与「整理源目录 → 整理目的目录」。"""
    title = f"整理组 {index + 1}"
    if rule.name.strip():
        title = f"{title}：{rule.name.strip()}"
    src = rule.src.strip() or "未配置源目录"
    dst = rule.dst.strip() or "未配置目的目录"
    chips = [
        _chip("通知开" if rule.notify else "通知关", "primary" if rule.notify else "grey"),
    ]
    return {
        "component": "summary",
        "props": {"class": "cd2strm-rule-summary"},
        "content": [
            {
                "component": "div",
                "props": {"class": "cd2strm-rmeta"},
                "content": [
                    {
                        "component": "div",
                        "props": {"class": "cd2strm-rname"},
                        "content": [{"component": "span", "text": title}, *chips],
                    },
                    {
                        "component": "div",
                        "props": {"class": "cd2strm-rpath"},
                        "text": f"{src} → {dst}",
                    },
                ],
            }
        ],
    }


def _organize_body(index: int) -> Dict[str, Any]:
    """整理组的设置区：目录 / 整理方式 / 整理行为。"""
    return {
        "component": "div",
        "props": {"class": "cd2strm-rbody"},
        "content": [
            _form_section(
                "目录",
                [
                    _text(organize_key(index, "name"), "备注名称", "例如：115 电影整理"),
                    _text(organize_key(index, "src"), "源目录", "", mono=True, tip="o-src"),
                    _text(organize_key(index, "dst"), "目的目录", "", mono=True, tip="o-dst"),
                    _text(
                        organize_key(index, "cd2_root"),
                        "CD2 根目录",
                        "/mnt/cd2-mount",
                        mono=True,
                        tip="o-cd2_root",
                    ),
                    _textarea(
                        organize_key(index, "exclude_dirs"),
                        "排除目录",
                        "",
                        tip="o-exclude_dirs",
                    ),
                ],
            ),
            _form_section(
                "插件自身行为",
                [
                    _switch(organize_key(index, "notify"), "完成后通知", "o-notify"),
                    _form_row(
                        "整理规则来源",
                        _text_node(
                            "整理模式 / 刮削 / 类型目录 / 分类目录 / 重命名 / 同名覆盖"
                            "由 MoviePilot「目录配置」决定",
                            "text-caption",
                        ),
                    ),
                ],
            ),
        ],
    }


def _organize_group_fold(index: int, rule: OrganizeRule) -> Dict[str, Any]:
    """一个整理组的可折叠区块（默认折叠，与 STRM 目录组一致）。"""
    return {
        "component": "details",
        "props": {"class": "cd2strm-rule-fold"},
        "content": [_organize_summary(index, rule), _organize_body(index)],
    }


def _mirror_card() -> Dict[str, Any]:
    """镜像移动的全局卡片（与 STRM 同步、媒体整理完全隔离）。"""
    return _form_card(
        "镜像移动",
        [
            _form_section(
                "总开关",
                [
                    _switch("mirror_enabled", "启用镜像移动"),
                    _switch("mirror_dry_run", "预演模式（只记录，不移动）"),
                    _switch("mirror_notify", "完成后通知"),
                ],
            )
        ],
    )


def _mirror_summary(index: int, rule: MirrorRule) -> Dict[str, Any]:
    """镜像组的折叠头：名称、徽章与「监听目录 → 镜像目录 → 回收站」。"""
    title = f"镜像组 {index + 1}"
    if rule.name.strip():
        title = f"{title}：{rule.name.strip()}"
    paths = " → ".join(
        [
            rule.path1.strip() or "未配置监听目录",
            rule.path2.strip() or "未配置镜像目录",
            rule.path3.strip() or "未配置回收站",
        ]
    )
    chips = [
        _chip("已启用" if rule.enabled else "未启用", "success" if rule.enabled else "grey"),
        _chip(f"保护 {len(rule.protect_list)} 项", "primary" if rule.protect_list else "grey"),
    ]
    return {
        "component": "summary",
        "props": {"class": "cd2strm-rule-summary"},
        "content": [
            {
                "component": "div",
                "props": {"class": "cd2strm-rmeta"},
                "content": [
                    {
                        "component": "div",
                        "props": {"class": "cd2strm-rname"},
                        "content": [{"component": "span", "text": title}, *chips],
                    },
                    {"component": "div", "props": {"class": "cd2strm-rpath"}, "text": paths},
                ],
            }
        ],
    }


def _mirror_body(index: int) -> Dict[str, Any]:
    """镜像组的设置区：目录（三项路径）/ 保护白名单 / 通知。"""
    return {
        "component": "div",
        "props": {"class": "cd2strm-rbody"},
        "content": [
            _form_section(
                "目录",
                [
                    _text(mirror_key(index, "name"), "备注名称", "例如：115 国产剧镜像"),
                    _text(
                        mirror_key(index, "path1"),
                        "监听目录",
                        "/mnt/cd2-mount/i52t/ptssd2/115/media/电视剧/国产剧",
                        mono=True,
                        tip="d-path1",
                    ),
                    _text(
                        mirror_key(index, "path2"),
                        "镜像目录",
                        "/mnt/cd2-mount/115/media/电视剧/国产剧",
                        mono=True,
                        tip="d-path2",
                    ),
                    _text(
                        mirror_key(index, "path3"),
                        "回收站",
                        "/mnt/cd2-mount/i52t/ptssd2/回收",
                        mono=True,
                        tip="d-path3",
                    ),
                    _text(
                        mirror_key(index, "cd2_root"),
                        "CD2 根目录",
                        "/mnt/cd2-mount",
                        mono=True,
                        tip="d-cd2_root",
                    ),
                    _text(
                        mirror_key(index, "media_exts"),
                        "媒体后缀（strm 换算）",
                        DEFAULT_LINK_EXTS,
                        tip="d-media_exts",
                    ),
                ],
            ),
            _form_section(
                "保护白名单",
                [
                    _textarea(
                        mirror_key(index, "protect"),
                        "保护条目",
                        "文件夹名 / 无后缀文件名 / .后缀 / 文件名+后缀，例如：花絮 或 README 或 .jpg 或 poster.jpg",
                        tip="d-protect",
                    ),
                ],
            ),
            _form_section(
                "通知",
                [
                    _switch(mirror_key(index, "notify"), "完成后通知", "d-notify"),
                ],
            ),
        ],
    }


def _mirror_group_fold(index: int, rule: MirrorRule) -> Dict[str, Any]:
    """一个镜像组的可折叠区块（默认折叠，与其它路径组一致）。"""
    return {
        "component": "details",
        "props": {"class": "cd2strm-rule-fold"},
        "content": [_mirror_summary(index, rule), _mirror_body(index)],
    }


def build_page(
    plugin_id: str,
    api_token: str,
    status: Dict[str, Any],
    rules: List[SyncRule],
    rule_stats: Dict[str, Dict[str, Any]],
    events: List[Dict[str, Any]],
    actions: List[Dict[str, Any]],
    display: Dict[str, Any],
    others: Optional[List[Dict[str, Any]]] = None,
    ignored_count: int = 0,
    excluded_count: int = 0,
    progress: Optional[Dict[str, Dict[str, Any]]] = None,
    view: str = "sync",
    organize_rules: Optional[List[OrganizeRule]] = None,
    organize_status: Optional[Dict[str, Any]] = None,
    organize_records: Optional[List[Dict[str, Any]]] = None,
    mirror_rules: Optional[List[MirrorRule]] = None,
    mirror_status: Optional[Dict[str, Any]] = None,
    mirror_records: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """构建插件详情页。

    顶部是视图菜单（STRM 同步 / 媒体整理 / 镜像移动），各视图渲染自己的状态与分组，
    数据互不影响；切换通过插件接口写入当前视图后整页重载。
    """
    organize_rules = organize_rules or []
    organize_records = organize_records or []
    mirror_rules = mirror_rules or []
    mirror_records = mirror_records or []
    if view == "mirror":
        mirror_page: List[Dict[str, Any]] = [
            _page_menu(plugin_id, api_token, "mirror"),
            _mirror_status_card(plugin_id, api_token, mirror_status or {}, len(mirror_rules)),
        ]
        for index, rule in enumerate(mirror_rules):
            mirror_page.append(
                _mirror_group_card(
                    plugin_id,
                    api_token,
                    index,
                    rule,
                    (mirror_status or {}).get("stats", {}).get(str(index), {}),
                    mirror_records,
                    [
                        item
                        for item in ((mirror_status or {}).get("events") or [])
                        if item.get("rule_index") == index
                    ],
                )
            )
        mirror_page.append(_style_block())
        mirror_page.append(_mirror_ignored_card((mirror_status or {}).get("ignored") or []))
        return [{"component": "div", "props": {"class": "cd2strm-page"}, "content": mirror_page}]
    if view == "organize":
        page: List[Dict[str, Any]] = [
            _page_menu(plugin_id, api_token, "organize"),
            _organize_status_card(plugin_id, api_token, organize_status or {}, len(organize_rules)),
        ]
        for index, rule in enumerate(organize_rules):
            page.append(
                _organize_group_card(
                    plugin_id,
                    api_token,
                    index,
                    rule,
                    (organize_status or {}).get("stats", {}).get(str(index), {}),
                    organize_records,
                    [
                        item
                        for item in ((organize_status or {}).get("events") or [])
                        if item.get("rule_index") == index
                    ],
                )
            )
        page.append(_organize_ignored_card((organize_status or {}).get("ignored") or []))
        page.append(_style_block())
        return [{"component": "div", "props": {"class": "cd2strm-page"}, "content": page}]
    page_size = max(5, int(display.get("page_size") or 5))
    pages = display.get("pages") or {}
    progress = progress or {}
    page: List[Dict[str, Any]] = [
        _page_menu(plugin_id, api_token, "sync"),
        _status_card(plugin_id, api_token, status),
    ]
    for index, rule in enumerate(rules):
        key = str(index)
        rule_name = rule.display_name(index)
        group_events = [item for item in events if item.get("rule_index") == index]
        group_actions = [
            item
            for item in actions
            if item.get("rule_index") == index
            or (item.get("rule_index") is None and item.get("rule") == rule_name)
        ]
        page.append(
            _rule_group_card(
                plugin_id,
                api_token,
                index,
                rule,
                rule_stats.get(key, {}),
                group_events,
                group_actions,
                int(pages.get(key) or 1),
                page_size,
                progress.get(key),
            )
        )
    if others:
        page.append(
            _unmatched_card(
                plugin_id,
                api_token,
                others,
                int(pages.get("other") or 1),
                page_size,
                ignored_count,
                excluded_count,
            )
        )
    # 整页包在前缀容器内，并注入受控样式
    page.append(_style_block())
    return [{"component": "div", "props": {"class": "cd2strm-page"}, "content": page}]


def _button(
    api: str,
    payload: Dict[str, Any],
    text: str,
    icon: str,
    color: str,
    css: str = "",
    variant: str = "",
) -> Dict[str, Any]:
    """构造一个会调用插件接口的按钮（variant 缺省时按颜色推断）。"""
    props: Dict[str, Any] = {
        "color": color,
        "variant": variant or ("flat" if color == "primary" else "tonal"),
        "size": "small",
        "prepend-icon": icon,
    }
    if css:
        props["class"] = css
    return {
        "component": "VBtn",
        "props": props,
        "text": text,
        "events": {"click": {"api": api, "method": "post", "params": payload}},
    }


def _page_menu(plugin_id: str, api_token: str, view: str) -> Dict[str, Any]:
    """详情页顶部固定区：视图菜单 + 「消息与日志」区（三个视图完全一致）。

    视图按钮点击后插件记录当前视图、页面自动重载。「消息与日志」区放全页共用的文字按钮
    （刷新 / 清除计数 / 清空通知与记录 / 清空日志），不再使用图标 + 悬停说明。
    其中「清除计数」只清当前显示的那个功能的统计数值；「清空通知与记录」清空三个功能的
    通知列表并连带清空操作记录。
    """
    api = f"plugin/{plugin_id}/view?apikey={api_token}"
    menu = {
        "component": "div",
        "props": {"class": "cd2strm-menu"},
        "content": [
            _button(api, {"view": "sync"}, "STRM 同步", "mdi-sync", "primary" if view == "sync" else "grey"),
            _button(
                api,
                {"view": "organize"},
                "媒体整理",
                "mdi-folder-move",
                "primary" if view == "organize" else "grey",
            ),
            _button(
                api,
                {"view": "mirror"},
                "镜像移动",
                "mdi-swap-horizontal",
                "primary" if view == "mirror" else "grey",
            ),
        ],
    }
    msglog = {
        "component": "div",
        "props": {"class": "cd2strm-msglog"},
        "content": [
            {"component": "span", "props": {"class": "cd2strm-stripe"}},
            {"component": "span", "props": {"class": "cd2strm-mtitle"}, "text": "消息与日志"},
            {"component": "span", "props": {"class": "cd2strm-sp"}},
            _button(
                f"plugin/{plugin_id}/refresh?apikey={api_token}",
                {},
                "刷新",
                "mdi-refresh",
                "primary",
            ),
            _button(
                f"plugin/{plugin_id}/clear-count?apikey={api_token}",
                {"scope": view},
                "清除计数",
                "mdi-counter",
                "grey",
            ),
            _button(
                f"plugin/{plugin_id}/clear-notify?apikey={api_token}",
                {"scope": "all", "target": "all"},
                "清空通知与记录",
                "mdi-delete-outline",
                "warning",
            ),
            _button(
                f"plugin/{plugin_id}/clear-log?apikey={api_token}",
                {},
                "清空日志",
                "mdi-delete-outline",
                "error",
                "",
                "flat",
            ),
        ],
    }
    return {"component": "div", "props": {"class": "cd2strm-top"}, "content": [menu, msglog]}


def _organize_status_card(
    plugin_id: str,
    api_token: str,
    status: Dict[str, Any],
    group_count: int,
) -> Dict[str, Any]:
    """媒体整理的运行状态面板（与 STRM 同步的状态面板同构）。"""
    enabled = bool(status.get("organize_enabled"))
    tone = "" if enabled else "warn"
    state_text = "已启用" if enabled else "未启用"
    state_tone = "ok" if enabled else "muted"
    body: List[Dict[str, Any]] = [
        {
            "component": "div",
            "props": {"class": "cd2strm-kpis k4"},
            "content": [
                _kpi(state_text, "整理状态", tone=state_tone),
                _kpi(str(status.get("accepted", 0)), "累计通知"),
                _kpi(str(status.get("pending", 0)), "待整理", tone="muted"),
                _kpi(str(status.get("running", 0)), "正在整理", tone="muted"),
            ],
        },
        {
            "component": "div",
            "props": {"class": "cd2strm-hint"},
            "text": "　｜　".join(
                [
                    f"整理组：{group_count} 组",
                    "通知来源：与 STRM 同步共用",
                    "整理链：MoviePilot TransferChain",
                    f"整理记录：{int(status.get('record_count') or 0)} 条",
                ]
            ),
        },
    ]
    if not enabled:
        body.append(
            {
                "component": "div",
                "props": {"class": "cd2strm-alert"},
                "content": [
                    {"component": "span", "text": "媒体整理当前未启用：到配置页「媒体整理配置」里开启并填写整理组。"}
                ],
            }
        )
    if status.get("last_error"):
        body.append(
            {
                "component": "div",
                "props": {"class": "cd2strm-alert bad"},
                "content": [
                    {"component": "span", "props": {"class": "cd2strm-bad"}, "text": "最近错误"},
                    {"component": "span", "text": str(status["last_error"])},
                ],
            }
        )
    return {
        "component": "div",
        "props": {"class": "cd2strm-panel"},
        "content": [
            {
                "component": "div",
                "props": {"class": "cd2strm-phead"},
                "content": [
                    {"component": "span", "props": {"class": f"cd2strm-stripe {tone}".strip()}},
                    {"component": "span", "text": "运行状态"},
                    {"component": "span", "props": {"class": "cd2strm-sp"}},
                    # 刷新 / 清除计数 / 清空通知与记录 / 清空日志 已统一到顶部「消息与日志」区
                ],
            },
            {"component": "div", "props": {"class": "cd2strm-sub"}, "content": body},
        ],
    }


def _organize_ignored_card(ignored: List[Dict[str, Any]]) -> Dict[str, Any]:
    """未匹配的整理通知卡片（默认折叠）：时间 / 变更 / 路径 / 新路径 / 原因。"""
    head = {
        "component": "div",
        "props": {"class": "cd2strm-tr th ign"},
        "content": [
            {"component": "div", "props": {"class": "h"}, "text": "时间"},
            {"component": "div", "props": {"class": "h"}, "text": "变更"},
            {"component": "div", "props": {"class": "h"}, "text": "路径"},
            {"component": "div", "props": {"class": "h"}, "text": "新路径"},
            {"component": "div", "props": {"class": "h"}, "text": "原因"},
        ],
    }
    rows: List[Dict[str, Any]] = []
    if not ignored:
        rows.append({"component": "div", "props": {"class": "cd2strm-count"}, "text": "暂无未匹配通知"})
    for item in ignored:
        rows.append(
            {
                "component": "div",
                "props": {"class": "cd2strm-tr ign"},
                "content": [
                    {"component": "div", "props": {"class": "cd2strm-t"}, "text": str(item.get("time") or "")},
                    {
                        "component": "div",
                        "content": [
                            _chip(
                                CHANGE_LABELS.get(str(item.get("change_type") or ""), "变更"),
                                CHANGE_TONES.get(str(item.get("change_type") or ""), "grey"),
                            )
                        ],
                    },
                    {"component": "div", "props": {"class": "cd2strm-pth"}, "text": str(item.get("path") or "")},
                    {
                        "component": "div",
                        "props": {"class": "cd2strm-pth"},
                        "text": str(item.get("new_path") or "—"),
                    },
                    {"component": "div", "props": {"class": "cd2strm-s"}, "text": str(item.get("reason") or "")},
                ],
            }
        )
    return {
        "component": "div",
        "props": {"class": "cd2strm-panel"},
        "content": [
            {
                "component": "div",
                "props": {"class": "cd2strm-phead"},
                "content": [
                    {"component": "span", "props": {"class": "cd2strm-stripe"}},
                    {"component": "span", "text": f"未匹配的整理通知 · {len(ignored)} 条"},
                    {"component": "span", "props": {"class": "cd2strm-sp"}},
                    {
                        "component": "span",
                        "props": {"class": "cd2strm-hint"},
                        "text": "收到通知但没被整理受理的记录（原因见右侧）",
                    },
                ],
            },
            {
                "component": "div",
                "props": {"class": "cd2strm-sub"},
                "content": [
                    {
                        "component": "details",
                        "props": {"class": "cd2strm-fold"},
                        "content": [
                            {"component": "summary", "text": "展开查看明细"},
                            {"component": "div", "content": [head, *rows]},
                        ],
                    }
                ],
            },
        ],
    }


def _organize_records(
    records: List[Dict[str, Any]], page: int = 1, page_size: int = 5
) -> Dict[str, Any]:
    """整理记录表（默认展开）：时间 / 触发 / 结果 / 媒体 / 文件。"""
    head = {
        "component": "div",
        "props": {"class": "cd2strm-tr th org"},
        "content": [
            {"component": "div", "props": {"class": "h"}, "text": "时间"},
            {"component": "div", "props": {"class": "h"}, "text": "触发"},
            {"component": "div", "props": {"class": "h"}, "text": "结果"},
            {"component": "div", "props": {"class": "h"}, "text": "文件"},
            {"component": "div", "props": {"class": "h"}, "text": "媒体"},
        ],
    }
    rows: List[Dict[str, Any]] = []
    if not records:
        rows.append({"component": "div", "props": {"class": "cd2strm-count"}, "text": "暂无整理记录"})
    for item in records:
        # 结果三态：成功 / 跳过 / 失败（跳过是正常结果，不能渲染成失败）
        result = str(item.get("result") or "")
        if result == "success":
            result_class, result_text = "cd2strm-ok", "成功"
        elif result == "skipped":
            result_class, result_text = "cd2strm-skip", "跳过"
        else:
            result_class, result_text = "cd2strm-bad", "失败"
        reason_text = str(item.get("message") or "")
        rows.append(
            {
                "component": "div",
                "props": {"class": "cd2strm-tr org"},
                "content": [
                    {"component": "div", "props": {"class": "cd2strm-t"}, "text": str(item.get("time") or "")},
                    {
                        "component": "div",
                        "content": [
                            _chip("事件" if item.get("trigger") == "event" else "手动",
                                  "info" if item.get("trigger") == "event" else "")
                        ],
                    },
                    {
                        "component": "div",
                        "props": {"class": result_class, "title": reason_text},
                        "text": result_text,
                    },
                    {
                        "component": "div",
                        "props": {"class": "cd2strm-pth", "title": str(item.get("file") or "")},
                        "text": str(item.get("file") or ""),
                    },
                    {
                        "component": "div",
                        "props": {"class": "cd2strm-s", "title": str(item.get("media") or reason_text)},
                        "text": str(item.get("media") or "—"),
                    },
                ],
            }
        )
    return {
        "component": "details",
        "props": {"class": "cd2strm-fold", "open": True},
        "content": [
            {"component": "summary", "text": f"整理记录 · {len(records)} 条"},
            {"component": "div", "content": [head, *rows]},
        ],
    }


def _organize_group_card(
    plugin_id: str,
    api_token: str,
    index: int,
    rule: OrganizeRule,
    stats: Dict[str, Any],
    records: List[Dict[str, Any]],
    hit_events: Optional[List[Dict[str, Any]]] = None,
    page_size: int = 5,
) -> Dict[str, Any]:
    """整理组面板：路径、KPI、操作按钮与整理记录（第一组默认展开）。"""
    name = rule.display_name(index)
    head: List[Dict[str, Any]] = [
        {"component": "span", "props": {"class": "cd2strm-stripe"}},
        {"component": "span", "props": {"class": "cd2strm-idx"}, "text": f"{index + 1} ·"},
        {"component": "span", "text": name},
        _chip("通知开" if rule.notify else "通知关", "primary" if rule.notify else "grey"),
        {"component": "span", "props": {"class": "cd2strm-sp"}},
        {
            "component": "span",
            "props": {"class": "cd2strm-meta"},
            "text": f"上次整理 {stats.get('time') or '—'}",
        },
        _enable_row(plugin_id, api_token, "organize", index, rule.enabled),
    ]
    sub: List[Dict[str, Any]] = [
        {
            "component": "div",
            "props": {"class": "cd2strm-paths"},
            "content": [
                _path_cell("源目录", rule.src.strip() or "未配置"),
                _path_cell("目的目录", rule.dst.strip() or "未配置"),
            ],
        },
        {
            "component": "div",
            "props": {"class": "cd2strm-kpis"},
            "content": [
                _kpi(str(stats.get("accepted", 0)), "收到通知"),
                _kpi(str(stats.get("organized", 0)), "已整理", tone="ok"),
                _kpi(str(stats.get("skipped", 0)), "跳过", tone="muted"),
                _kpi(str(stats.get("failed", 0)), "失败", tone="bad"),
                _kpi(str(stats.get("metadata", 0)), "元数据"),
                _kpi(str(stats.get("cleaned", 0)), "清理", tone="muted"),
            ],
        },
        {
            "component": "div",
            "props": {"class": "cd2strm-btns"},
            "content": [
                _button(
                    f"plugin/{plugin_id}/organize-clear?apikey={api_token}",
                    {"index": index},
                    "清空数值",
                    "mdi-counter",
                    "grey",
                ),
                _button(
                    f"plugin/{plugin_id}/organize?apikey={api_token}",
                    {"operation": "copy", "index": index},
                    "复制这一组",
                    "mdi-content-copy",
                    "grey",
                ),
                _button(
                    f"plugin/{plugin_id}/organize?apikey={api_token}",
                    {"operation": "delete", "index": index},
                    "删除这一组",
                    "mdi-delete",
                    "error",
                ),
                _button(
                    f"plugin/{plugin_id}/organize-scan?apikey={api_token}",
                    {"index": index},
                    "立即整理",
                    "mdi-folder-move",
                    "primary",
                ),
            ],
        },
        _notifications_card(
            f"organize{index}",
            1,
            page_size,
            hit_events or [],
            "暂无命中通知：只有命中本整理组规则的通知才会出现在这里。",
        ),
        _organize_records(records, 1, page_size),
    ]
    props: Dict[str, Any] = {"class": "cd2strm-group"}
    return {
        "component": "details",
        "props": props,
        "content": [
            {"component": "summary", "props": {"class": "cd2strm-phead"}, "content": head},
            {"component": "div", "props": {"class": "cd2strm-sub"}, "content": sub},
        ],
    }


def _mirror_status_card(
    plugin_id: str, api_token: str, status: Dict[str, Any], group_count: int
) -> Dict[str, Any]:
    """镜像移动视图的状态面板：状态、预演徽章、KPI 与右上角按钮。"""
    enabled = bool(status.get("enabled"))
    dry_run = bool(status.get("dry_run", True))
    head: List[Dict[str, Any]] = [
        {"component": "span", "props": {"class": "cd2strm-stripe"}},
        {"component": "span", "text": "镜像移动"},
        _chip("已启用" if enabled else "已停用", "success" if enabled else "grey"),
        _chip(
            "预演模式（不移动文件）" if dry_run else "正式执行（会移动文件）",
            "warn" if dry_run else "error",
        ),
        {"component": "span", "props": {"class": "cd2strm-sp"}},
        {"component": "span", "props": {"class": "cd2strm-meta"}, "text": f"共 {group_count} 组"},
        # 刷新 / 清除计数 / 清空通知与记录 / 清空日志 已统一到顶部「消息与日志」区
    ]
    body: List[Dict[str, Any]] = [
        {
            "component": "div",
            "props": {"class": "cd2strm-kpis k4"},
            "content": [
                _kpi(str(status.get("accepted", 0)), "受理通知"),
                _kpi(str(status.get("moved_files", 0)), "移动文件", tone="ok"),
                _kpi(str(status.get("moved_dirs", 0)), "移动目录", tone="ok"),
                _kpi(str(status.get("failed", 0)), "失败", tone="bad"),
            ],
        },
        {
            "component": "div",
            "props": {"class": "cd2strm-hint"},
            "text": "监听目录里删除什么，就把镜像目录里对应的对象移到回收站；保护白名单命中的对象不移动。"
            "预演模式开启时只记录「将要移动什么」，不会真正移动文件。",
        },
    ]
    return {
        "component": "div",
        "props": {"class": "cd2strm-panel"},
        "content": [
            {"component": "div", "props": {"class": "cd2strm-phead"}, "content": head},
            {"component": "div", "props": {"class": "cd2strm-pbody"}, "content": body},
        ],
    }


def _mirror_records(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """镜像记录表格（默认折叠，一行一条）。"""
    rows: List[Dict[str, Any]] = [
        {
            "component": "div",
            "props": {"class": "cd2strm-tr th mir"},
            "content": [
                {"component": "div", "props": {"class": "h"}, "text": "时间"},
                {"component": "div", "props": {"class": "h"}, "text": "触发"},
                {"component": "div", "props": {"class": "h"}, "text": "结果"},
                {"component": "div", "props": {"class": "h"}, "text": "监听目录对象"},
                {"component": "div", "props": {"class": "h"}, "text": "移动项"},
            ],
        }
    ]
    for item in records[-10:]:
        rows.append(
            {
                "component": "div",
                "props": {"class": "cd2strm-tr mir"},
                "content": [
                    {
                        "component": "div",
                        "props": {"class": "cd2strm-s"},
                        "text": str(item.get("time") or ""),
                    },
                    {
                        "component": "div",
                        "props": {"class": "cd2strm-s"},
                        "text": str(item.get("trigger") or ""),
                    },
                    {
                        "component": "div",
                        "props": {"class": "cd2strm-s"},
                        "text": str(item.get("result") or ""),
                    },
                    {
                        "component": "div",
                        "props": {
                            "class": "cd2strm-pth",
                            "title": str(item.get("path") or ""),
                        },
                        "text": str(item.get("path") or ""),
                    },
                    {
                        "component": "div",
                        "props": {
                            "class": "cd2strm-s",
                            "title": str(item.get("target") or ""),
                        },
                        "text": str(item.get("target") or ""),
                    },
                ],
            }
        )
    return {
        "component": "details",
        "props": {"class": "cd2strm-fold"},
        "content": [
            {"component": "summary", "text": f"镜像记录 · {len(records)} 条"},
            {"component": "div", "content": rows},
        ],
    }


def _mirror_ignored_card(ignored: List[Dict[str, Any]]) -> Dict[str, Any]:
    """未匹配的镜像通知（默认折叠，便于自查为什么没处理）。"""
    rows: List[Dict[str, Any]] = [
        {
            "component": "div",
            "props": {"class": "cd2strm-tr th ign"},
            "content": [
                {"component": "div", "props": {"class": "h"}, "text": "时间"},
                {"component": "div", "props": {"class": "h"}, "text": "变更"},
                {"component": "div", "props": {"class": "h"}, "text": "路径"},
                {"component": "div", "props": {"class": "h"}, "text": "原因"},
                {"component": "div", "props": {"class": "h"}, "text": "来源"},
            ],
        }
    ]
    for item in ignored[-20:]:
        rows.append(
            {
                "component": "div",
                "props": {"class": "cd2strm-tr ign"},
                "content": [
                    {
                        "component": "div",
                        "props": {"class": "cd2strm-s"},
                        "text": str(item.get("time") or ""),
                    },
                    {
                        "component": "div",
                        "props": {"class": "cd2strm-s"},
                        "text": str(item.get("change_type") or ""),
                    },
                    {
                        "component": "div",
                        "props": {
                            "class": "cd2strm-pth",
                            "title": str(item.get("path") or ""),
                        },
                        "text": str(item.get("path") or ""),
                    },
                    {
                        "component": "div",
                        "props": {"class": "cd2strm-s"},
                        "text": str(item.get("reason") or ""),
                    },
                    {
                        "component": "div",
                        "props": {"class": "cd2strm-s"},
                        "text": str(item.get("source") or ""),
                    },
                ],
            }
        )
    return {
        "component": "details",
        "props": {"class": "cd2strm-fold"},
        "content": [
            {"component": "summary", "text": f"未匹配的镜像通知 · {len(ignored)} 条"},
            {"component": "div", "content": rows},
        ],
    }


def _mirror_group_card(
    plugin_id: str,
    api_token: str,
    index: int,
    rule: MirrorRule,
    stats: Dict[str, Any],
    records: List[Dict[str, Any]],
    hit_events: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """镜像组面板：三项路径、KPI、镜像记录与折叠头右侧的启用开关（默认折叠）。"""
    head: List[Dict[str, Any]] = [
        {"component": "span", "props": {"class": "cd2strm-stripe"}},
        {"component": "span", "props": {"class": "cd2strm-idx"}, "text": f"{index + 1} ·"},
        {"component": "span", "text": rule.display_name(index)},
        _chip(f"保护 {len(rule.protect_list)} 项", "primary" if rule.protect_list else "grey"),
        {"component": "span", "props": {"class": "cd2strm-sp"}},
        {
            "component": "span",
            "props": {"class": "cd2strm-meta"},
            "text": f"上次 {stats.get('time') or '—'}",
        },
        _enable_row(plugin_id, api_token, "mirror", index, rule.enabled),
    ]
    body: List[Dict[str, Any]] = [
        {
            "component": "div",
            "props": {"class": "cd2strm-paths"},
            "content": [
                _path_cell("监听目录", rule.path1.strip() or "未配置"),
                _path_cell("镜像目录", rule.path2.strip() or "未配置"),
                _path_cell("回收站", rule.path3.strip() or "未配置"),
            ],
        },
        {
            "component": "div",
            "props": {"class": "cd2strm-kpis"},
            "content": [
                _kpi(str(stats.get("accepted", 0)), "受理通知"),
                _kpi(str(stats.get("moved_files", 0)), "移动文件", tone="ok"),
                _kpi(str(stats.get("moved_dirs", 0)), "移动目录", tone="ok"),
                _kpi(str(stats.get("protected", 0)), "保护跳过", tone="muted"),
                _kpi(str(stats.get("skipped", 0)), "跳过", tone="muted"),
                _kpi(str(stats.get("failed", 0)), "失败", tone="bad"),
            ],
        },
        {
            "component": "div",
            "props": {"class": "cd2strm-btns"},
            "content": [
                _button(
                    f"plugin/{plugin_id}/mirror-clear?apikey={api_token}",
                    {"index": index},
                    "清空数值",
                    "mdi-counter",
                    "grey",
                ),
                _button(
                    f"plugin/{plugin_id}/mirror?apikey={api_token}",
                    {"index": index, "operation": "copy"},
                    "复制这一组",
                    "mdi-content-copy",
                    "grey",
                ),
                _button(
                    f"plugin/{plugin_id}/mirror?apikey={api_token}",
                    {"index": index, "operation": "delete"},
                    "删除这一组",
                    "mdi-delete-outline",
                    "error",
                ),
            ],
        },
        _notifications_card(
            f"mirror{index}",
            1,
            5,
            hit_events or [],
            "暂无命中通知：只有监听目录里的删除通知才会命中本镜像组。",
        ),
        _mirror_records(records),
    ]
    return _collapsible(summary=head, body=body, css="cd2strm-group")


def _status_card(plugin_id: str, api_token: str, status: Dict[str, Any]) -> Dict[str, Any]:
    """构建运行状态面板：状态色条、关键数字、连接明细与刷新/清空按钮。"""
    connections = status.get("connections") or []
    if not status.get("enabled"):
        tone, state_text, state_tone = "bad", "未启用", "bad"
    elif not connections:
        tone, state_text, state_tone = "warn", "未配置地址", "muted"
    elif status.get("connected"):
        tone, state_text, state_tone = "", "订阅已连接", "ok"
    else:
        tone, state_text, state_tone = "bad", "订阅未连接", "bad"
    scanning = _safe_count(status, "scanning")
    body: List[Dict[str, Any]] = [
        {
            "component": "div",
            "props": {"class": "cd2strm-kpis k4"},
            "content": [
                _kpi(state_text, "总状态", tone=state_tone),
                _kpi(str(status.get("message_count", 0)), "累计通知"),
                _kpi(str(status.get("pending", 0)), "待处理目录", tone="muted"),
                _kpi(str(scanning), "正在扫描", tone="muted"),
            ],
        },
        {
            "component": "div",
            "props": {"class": "cd2strm-hint"},
            "text": "　｜　".join(
                f"{item.get('label')}：{'已连接' if item.get('connected') else '未连接'}"
                f"（{item.get('message_count', 0)}）"
                for item in connections
            )
            or "尚未配置 CloudDrive2 地址",
        },
        {
            "component": "div",
            "props": {"class": "cd2strm-hint"},
            "text": (
                f"最后通知：{status.get('last_message_at') or '无'}"
                f"　｜　定时扫描：{status.get('schedule_text') or '已关闭'}"
            ),
        },
    ]
    if status.get("last_error"):
        body.append(
            {
                "component": "div",
                "props": {"class": "cd2strm-alert bad"},
                "content": [
                    {"component": "span", "props": {"class": "cd2strm-bad"}, "text": "最近错误"},
                    {"component": "span", "text": str(status["last_error"])},
                ],
            }
        )
    head: List[Dict[str, Any]] = [
        {"component": "span", "props": {"class": f"cd2strm-stripe {tone}".strip()}},
        {"component": "span", "text": "运行状态"},
    ]
    if scanning:
        head.append(_chip("正在扫描", "warn"))
    head.extend(
        [
            {"component": "span", "props": {"class": "cd2strm-sp"}},
            # 刷新 / 清除计数 / 清空通知与记录 / 清空日志 已统一到顶部「消息与日志」区
        ]
    )
    return {
        "component": "div",
        "props": {"class": "cd2strm-panel"},
        "content": [
            {"component": "div", "props": {"class": "cd2strm-phead"}, "content": head},
            {"component": "div", "props": {"class": "cd2strm-pbody"}, "content": body},
        ],
    }


def _safe_count(stats: Dict[str, Any], key: str) -> int:
    """从统计字典里安全取整数。"""
    try:
        return int(stats.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _rule_group_card(
    plugin_id: str,
    api_token: str,
    index: int,
    rule: SyncRule,
    stats: Dict[str, Any],
    events: List[Dict[str, Any]],
    actions: List[Dict[str, Any]],
    page: int,
    page_size: int,
    progress: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """构建单个目录组卡片：标题徽章、路径、KPI、操作按钮与该组的通知、操作记录。"""
    base = f"plugin/{plugin_id}"
    suffix = f"?apikey={api_token}"
    key = str(index)
    precise = (rule.process_mode or "precise") == "precise"
    failures = _safe_count(stats, "links_failed") + _safe_count(stats, "metadata_failed")
    cleaned = (
        _safe_count(stats, "removed_links")
        + _safe_count(stats, "removed_metadata")
        + _safe_count(stats, "removed_dirs")
    )
    body: List[Dict[str, Any]] = [
        {
            "component": "div",
            "props": {"class": "cd2strm-paths"},
            "content": [
                _path_cell("源目录", rule.media_dir or "未设置"),
                _path_cell("目的目录", rule.local_dir or "未设置"),
            ],
        },
        {
            "component": "div",
            "props": {"class": "cd2strm-kpis"},
            "content": [
                _kpi(str(_safe_count(stats, "scanned_files")), "扫描媒体", tone="muted"),
                _kpi(str(_safe_count(stats, "links_created")), "新增"),
                _kpi(str(_safe_count(stats, "links_updated")), "更新", tone="muted"),
                _kpi(str(_safe_count(stats, "links_skipped")), "跳过", tone="muted"),
                _kpi(str(failures), "失败", tone="bad" if failures else ""),
                _kpi(str(_safe_count(stats, "metadata_copied")), "元数据复制"),
                _kpi(str(_safe_count(stats, "metadata_skipped")), "元数据跳过", tone="muted"),
                _kpi(str(cleaned), "清理", tone="muted"),
            ],
        },
    ]
    if progress:
        body.insert(
            2,
            {
                "component": "div",
                "props": {"class": "cd2strm-progress"},
                "content": [
                    {
                        "component": "VProgressLinear",
                        "props": {"indeterminate": True, "height": 4, "rounded": True},
                    },
                    {
                        "component": "div",
                        "props": {"class": "cd2strm-hint"},
                        "text": (
                            f"扫描中：已处理 {progress.get('scanned', 0)} 个"
                            f" · 用时 {progress.get('elapsed', 0)}s"
                            f" · 阶段：{progress.get('stage') or '准备'}"
                        ),
                    },
                ],
            },
        )
    if stats.get("error"):
        body.append(
            {
                "component": "div",
                "props": {"class": "cd2strm-alert bad"},
                "content": [
                    {
                        "component": "span",
                        "props": {"class": "cd2strm-bad"},
                        "text": "最近错误",
                    },
                    {"component": "span", "text": str(stats["error"])},
                ],
            }
        )
    body.append(
        {
            "component": "div",
            "props": {"class": "cd2strm-btns"},
            "content": [
                {
                    "component": "VBtn",
                    "props": {
                        "color": "grey",
                        "variant": "text",
                        "size": "small",
                        "prepend-icon": "mdi-counter",
                        "title": "只清空上方显示的统计数值，不影响操作记录与已生成的文件",
                    },
                    "text": "清空数值",
                    "events": {
                        "click": {
                            "api": f"{base}/clear{suffix}",
                            "method": "post",
                            "params": {"index": index},
                        }
                    },
                },
                _button(
                    f"{base}/rule{suffix}",
                    {"index": index, "operation": "copy"},
                    "复制这一组",
                    "mdi-content-copy",
                    "secondary",
                ),
                _button(
                    f"{base}/rule{suffix}",
                    {"index": index, "operation": "delete"},
                    "删除这一组",
                    "mdi-delete",
                    "error",
                ),
                _button(
                    f"{base}/scan{suffix}",
                    {"index": index},
                    "立即扫描",
                    "mdi-magnify-scan",
                    "primary",
                ),
            ],
        }
    )
    body.append(_notifications_card(key, page, page_size, events))
    body.append(_actions_card(page, page_size, actions))
    body.append(
        _pager(plugin_id, api_token, key, page, page_size, max(len(events), len(actions)))
    )
    # 头部：状态色条 + 序号 + 组名 + 徽章 + 上次处理时间；第一组默认展开，其余默认折叠
    if progress:
        tone = "warn"
    elif failures:
        tone = "bad"
    else:
        tone = ""
    head: List[Dict[str, Any]] = [
        {"component": "span", "props": {"class": f"cd2strm-stripe {tone}".strip()}}
    ]
    if rule.name:
        head.append(
            {"component": "span", "props": {"class": "cd2strm-idx"}, "text": f"{index + 1} ·"}
        )
    head.append(
        _text_node(rule.name or f"目录组 {index + 1}", "text-body-1", {"font-weight": "600"})
    )
    head.append(_chip("精确" if precise else "目录扫描", "primary"))
    head.append(
        _chip(
            "定时扫描：开" if rule.schedule_enabled else "定时扫描：关",
            "success" if rule.schedule_enabled else "grey",
        )
    )
    if progress:
        head.append(_chip("正在扫描", "warn"))
    if has_nested_target(rule):
        head.append(_chip("目的目录在源目录内（已自动排除）", "error"))
    head.append({"component": "span", "props": {"class": "cd2strm-sp"}})
    head.append(
        {
            "component": "span",
            "props": {
                "class": "cd2strm-meta",
                "title": "该组最近一次处理（事件 / 手动 / 定时）的时间",
            },
            "text": f"上次 {stats.get('time') or '无'}",
        }
    )
    head.append(_enable_row(plugin_id, api_token, "sync", index, rule.enabled))
    return _collapsible(summary=head, body=body, css="cd2strm-group")


def _collapsible(
    summary: List[Dict[str, Any]],
    body: List[Dict[str, Any]],
    opened: bool = False,
    css: str = "",
) -> Dict[str, Any]:
    """构造原生可折叠块：details + summary，opened 决定默认是否展开。"""
    classes = "cd2strm-fold"
    if css:
        classes = f"{classes} {css}"
    props: Dict[str, Any] = {"class": classes}
    if opened:
        props["open"] = True
    return {
        "component": "details",
        "props": props,
        "content": [
            {"component": "summary", "content": summary},
            {"component": "div", "props": {"class": "cd2strm-sub"}, "content": body},
        ],
    }


def _clamp_page(page: int, page_size: int, total: int) -> int:
    """把页码限制在有效范围内。"""
    if page_size <= 0:
        return 1
    max_page = max(1, (total + page_size - 1) // page_size)
    return max(1, min(page, max_page))


def _page_window(items: List[Dict[str, Any]], page: int, page_size: int) -> List[Dict[str, Any]]:
    """按页码与每页条数截取一段数据。"""
    start = max(0, (page - 1) * page_size)
    return items[start : start + page_size]


def _pager(
    plugin_id: str,
    api_token: str,
    key: str,
    page: int,
    page_size: int,
    total: int,
) -> Dict[str, Any]:
    """构造消息显示范围控制条：每页条数 + 上一页 / 下一页。"""
    api = f"plugin/{plugin_id}/display?apikey={api_token}"
    sizes: List[Dict[str, Any]] = []
    for size in (5, 10, 20, 30, 50, 100):
        sizes.append(
            {
                "component": "span",
                "props": {"class": "size on" if size == page_size else "size"},
                "text": str(size),
                "events": {
                    "click": {
                        "api": api,
                        "method": "post",
                        "params": {"index": key, "page_size": size},
                    }
                },
            }
        )
    max_page = max(1, (total + page_size - 1) // page_size) if page_size else 1
    return {
        "component": "div",
        "props": {"class": "cd2strm-pager"},
        "content": [
            {"component": "span", "props": {"class": "lab"}, "text": "显示消息范围：每页"},
            *sizes,
            {
                "component": "span",
                "props": {"class": "nav", "title": "上一页"},
                "text": "‹",
                "events": {
                    "click": {
                        "api": api,
                        "method": "post",
                        "params": {"index": key, "page": page - 1},
                    }
                },
            },
            {
                "component": "span",
                "props": {"class": "pos"},
                "text": f"第 {page} / {max_page} 页（共 {total} 条）",
            },
            {
                "component": "span",
                "props": {"class": "nav", "title": "下一页"},
                "text": "›",
                "events": {
                    "click": {
                        "api": api,
                        "method": "post",
                        "params": {"index": key, "page": page + 1},
                    }
                },
            },
        ],
    }


def _event_line(event: Dict[str, Any]) -> Dict[str, Any]:
    """把一条 CD2 通知渲染成表格行：时间 / 变更 / 内容 / 结果。"""
    path = str(event.get("path") or "")
    result = str(event.get("result") or "")
    if not event.get("done"):
        state_class, state_text = "", "处理中"
    elif result.startswith("失败"):
        state_class, state_text = "bad", "失败"
    elif result.startswith("跳过"):
        state_class, state_text = "skip", "跳过"
    else:
        state_class, state_text = "ok", "完成"
    if not result and not event.get("done"):
        result = "等待处理"
    tail: List[Dict[str, Any]] = [
        {
            "component": "span",
            "props": {"class": f"cd2strm-st {state_class}".strip()},
            "text": state_text,
        },
        {
            "component": "span",
            "props": {"class": "cd2strm-res", "title": result or "—"},
            "text": result or "—",
        },
    ]
    if event.get("internal"):
        tail.append(_chip("自身生成", "grey"))
    if event.get("source"):
        tail.append(_chip(str(event["source"]), "grey"))
    return {
        "component": "div",
        "props": {"class": "cd2strm-tr ev"},
        "content": [
            {
                "component": "span",
                "props": {"class": "cd2strm-t"},
                "text": str(event.get("time") or ""),
            },
            _change_chip(str(event.get("change_type") or "")),
            {"component": "span", "props": {"class": "cd2strm-pth", "title": path}, "text": path},
            {"component": "span", "props": {"class": "cd2strm-r"}, "content": tail},
        ],
    }


def _notifications_card(
    key: str,
    page: int,
    page_size: int,
    events: List[Dict[str, Any]],
    empty_hint: str = "",
) -> Dict[str, Any]:
    """构建某个目录组的 CD2 通知区：表头 + 按处理结果分组，整体默认展开。"""
    del key
    total = len(events)
    page = _clamp_page(page, page_size, total)
    window = _page_window(events, page, page_size)
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for event in window:
        grouped.setdefault(str(event.get("outcome") or "其它"), []).append(event)
    ordered = sorted(grouped.items(), key=lambda item: (item[0] != "已受理", item[0]))
    rows: List[Dict[str, Any]] = [
        {
            "component": "div",
            "props": {"class": "cd2strm-tr th ev"},
            "content": [
                {"component": "span", "props": {"class": "h"}, "text": "时间"},
                {"component": "span", "props": {"class": "h"}, "text": "变更"},
                {"component": "span", "props": {"class": "h"}, "text": "内容"},
                {
                    "component": "span",
                    "props": {"class": "h", "style": {"text-align": "right"}},
                    "text": "结果",
                },
            ],
        }
    ]
    for position, (outcome, items) in enumerate(ordered):
        color = {"已受理": "info", "已忽略": "grey"}.get(outcome, "primary")
        rows.append(
            _collapsible(
                summary=[
                    _chip(outcome, color),
                    {
                        "component": "span",
                        "props": {"class": "cd2strm-count"},
                        "text": f"{len(items)} 条",
                    },
                ],
                body=[_event_line(event) for event in items],
                opened=position == 0,
                css="cd2strm-nested",
            )
        )
    if not ordered:
        rows.append(
            {
                "component": "div",
                "props": {"class": "cd2strm-hint"},
                "text": empty_hint or "暂无通知：CloudDrive2 只在变更经由它自身发生时推送。",
            }
        )
    shown = min(total, page * page_size) if total else 0
    return _collapsible(
        summary=[
            {"component": "span", "text": "CD2 通知"},
            _chip(f"共 {total} 条", "grey"),
            {
                "component": "span",
                "props": {"class": "cd2strm-count"},
                "text": f"已显示最新 {shown} 条",
            },
        ],
        body=rows,
        opened=True,
    )


def _actions_card(page: int, page_size: int, actions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """构建某个目录组的操作记录区：表格行（时间 / 触发 / 统计 / 处理文件），默认折叠。"""
    total = len(actions)
    page = _clamp_page(page, page_size, total)
    window = _page_window(actions, page, page_size)
    lines: List[Dict[str, Any]] = [
        {
            "component": "div",
            "props": {"class": "cd2strm-tr th rec"},
            "content": [
                {"component": "span", "props": {"class": "h"}, "text": "时间"},
                {"component": "span", "props": {"class": "h"}, "text": "触发"},
                {"component": "span", "props": {"class": "h"}, "text": "统计"},
                {"component": "span", "props": {"class": "h"}, "text": "生成 / 处理文件"},
            ],
        }
    ]
    for action in window:
        text = str(action.get("summary") or "")
        if action.get("error"):
            text = f"{text}｜错误：{action['error']}" if text else f"错误：{action['error']}"
        files = list(action.get("files") or [])
        file_nodes: List[Dict[str, Any]] = []
        for item in files[:5]:
            file_nodes.append(
                {
                    "component": "div",
                    "props": {"class": "cd2strm-pth", "title": item},
                    "text": item,
                }
            )
        if len(files) > 5:
            file_nodes.append(
                {
                    "component": "div",
                    "props": {"class": "cd2strm-count"},
                    "text": f"其余 {len(files) - 5} 个已省略",
                }
            )
        if not file_nodes:
            file_nodes.append(
                {"component": "div", "props": {"class": "cd2strm-count"}, "text": "—"}
            )
        lines.append(
            {
                "component": "div",
                "props": {"class": "cd2strm-tr rec"},
                "content": [
                    {
                        "component": "span",
                        "props": {"class": "cd2strm-t"},
                        "text": str(action.get("time") or ""),
                    },
                    _chip(str(action.get("trigger") or "事件"), "grey"),
                    {
                        "component": "span",
                        "props": {"class": "cd2strm-s", "title": text},
                        "text": text or "无变化",
                    },
                    {
                        "component": "span",
                        "props": {"class": "cd2strm-fl"},
                        "content": file_nodes,
                    },
                ],
            }
        )
    if len(lines) == 1:
        lines.append(
            {"component": "div", "props": {"class": "cd2strm-hint"}, "text": "暂无操作记录"}
        )
    return _collapsible(
        summary=[
            {"component": "span", "text": "操作记录"},
            _chip(f"{total} 条", "grey"),
        ],
        body=lines,
        opened=False,
    )


def _unmatched_card(
    plugin_id: str,
    api_token: str,
    events: List[Dict[str, Any]],
    page: int,
    page_size: int,
    ignored_count: int = 0,
    excluded_count: int = 0,
) -> Dict[str, Any]:
    """构建未匹配任何目录组的通知卡片：按来源分组，整体可折叠、默认折叠。"""
    labels = (
        ("whitelist_miss", "后缀未匹配"),
        ("internal", "自身生成（插件回声）"),
        ("rule_miss", "不在目录组内"),
    )
    total = len(events)
    page = _clamp_page(page, page_size, total)
    window = _page_window(events, page, page_size)
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for event in window:
        category = str(
            event.get("category") or ("internal" if event.get("internal") else "rule_miss")
        )
        grouped.setdefault(category, []).append(event)
    body: List[Dict[str, Any]] = []
    for position, (category, title) in enumerate(labels):
        items = grouped.get(category) or []
        if not items:
            continue
        body.append(
            _collapsible(
                summary=[
                    _chip(title, "grey"),
                    {
                        "component": "span",
                        "props": {"class": "cd2strm-count"},
                        "text": f"{len(items)} 条",
                    },
                ],
                body=[_event_line(event) for event in items],
                opened=position == 0 and category != "internal",
                css="cd2strm-nested",
            )
        )
    if not body:
        body = [{"component": "div", "props": {"class": "cd2strm-count"}, "text": "暂无未匹配通知"}]
    summary: List[Dict[str, Any]] = [
        {"component": "span", "text": "未匹配的strm通知"},
        _chip(f"{total} 条", "grey"),
    ]
    if ignored_count:
        summary.append(_chip(f"累计 {ignored_count} 条", "grey"))
    if excluded_count:
        summary.append(_chip(f"排除目录 {excluded_count} 条", "grey"))
    summary.insert(0, {"component": "span", "props": {"class": "cd2strm-stripe"}})
    return _collapsible(
        summary=summary,
        body=[
            *body,
            _pager(plugin_id, api_token, "other", page, page_size, total),
        ],
        opened=False,
        css="cd2strm-group",
    )
