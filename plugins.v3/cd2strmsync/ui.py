"""插件页面的 Vuetify JSON 构建：配置表单与详情页。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .rules import (
    DEFAULT_LINK_EXTS,
    MAX_MIRROR_RULES,
    MAX_ORGANIZE_RULES,
    DEFAULT_METADATA_EXTS,
    DEFAULT_STRM_TEMPLATE,
    MAX_GLOBAL_EXCLUDES,
    MAX_RULES,
    MirrorRule,
    OrganizeRule,
    SyncRule,
    has_nested_target,
    mirror_field_names,
    mirror_key,
    organize_field_names,
    organize_key,
    rule_field_names,
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

# 「连接状态」一行式：跟在「消息与日志」下面，不再占右侧一栏（内联样式为主）
CONN_LINE_STYLE: Dict[str, Any] = {
    "display": "flex",
    "align-items": "center",
    "flex-wrap": "wrap",
    "gap": "6px 12px",
    "padding": "8px 12px",
    "margin-bottom": "10px",
    "border": "1px solid rgba(var(--v-theme-on-surface,0,0,0),.14)",
    "border-radius": "10px",
    "background": "rgba(var(--v-theme-on-surface,0,0,0),.03)",
    "font-size": "12px",
}
CONN_DOT_STYLE: Dict[str, Any] = {"width": "8px", "height": "8px", "border-radius": "50%", "flex": "0 0 auto"}
CONN_SEP_STYLE: Dict[str, Any] = {
    "width": "1px",
    "height": "14px",
    "background": "rgba(var(--v-theme-on-surface,0,0,0),.16)",
}

def _tint(color: str, alpha: float) -> str:
    """把 #rrggbb 转成 rgba()，用于组头整行的淡色底（明暗主题都能用）。"""
    value = str(color or "").lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    try:
        red, green, blue = (int(value[index : index + 2], 16) for index in (0, 2, 4))
    except (ValueError, IndexError):
        return color
    return f"rgba({red},{green},{blue},{alpha:g})"


# 目录组的标识色：每一组一个颜色（左色条 + 序号徽章），方便一眼区分是哪一组；
# 这组色在明暗主题下都够醒目，且不占用 green/红/橙 的"状态语义"（状态仍由徽章表达）
GROUP_COLORS = ("#3b82f6", "#8b5cf6", "#06b6d4", "#f59e0b", "#ec4899", "#10b981", "#6366f1", "#14b8a6")

# 通知合并：整组最大跨度（秒），避免把同一目录里隔了很久的操作也并成一组
MERGE_SPAN_LIMIT = 300
# 通知与操作记录配对时允许的时间错位（秒）：批处理里两边往往交错发生
PAIR_SLACK = 60

# 通知 / 操作记录容器：固定高度 + 垂直滚动。
# 用内联样式而不是只靠注入 CSS —— 宿主对注入样式表的支持并不可靠（配置页一直是内联兜底），
# 内联样式不会被任何样式表规则覆盖，滚动条一定能出来。
FEED_BOX_STYLE: Dict[str, Any] = {
    "max-height": "420px",
    "overflow-y": "auto",
    # 不要写 overscroll-behavior:contain —— 那会拦住滚动接力：
    # 光标停在框里、框滚到底后整页就再也滚不动（用户实测"鼠标在左侧无法滚动窗口"）
    "padding": "4px 8px",
    "border": "1px solid rgba(var(--v-theme-on-surface,0,0,0),.10)",
    "border-radius": "8px",
}

# 合并时间窗的可选值（与 rules.NOTIFY_MERGE_WINDOWS 保持一致）
MERGE_WINDOW_ITEMS = [
    {"title": "10 秒", "value": "10"},
    {"title": "30 秒（默认）", "value": "30"},
    {"title": "60 秒", "value": "60"},
    {"title": "300 秒", "value": "300"},
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
/* ===== C 布局（活动流 + 常驻侧栏）：只新增类名，不改动配置页与整理/镜像视图既有类 ===== */
.cd2strm-page .cd2strm-dot{width:8px;height:8px;border-radius:50%;flex:0 0 auto;
background:rgba(var(--v-theme-on-surface,0,0,0),.30)}
.cd2strm-page .cd2strm-dot.ok{background:rgb(var(--v-theme-success,46,125,50))}
.cd2strm-page .cd2strm-dot.bad{background:rgb(var(--v-theme-error,198,40,40))}
.cd2strm-page .cd2strm-scard code{font-family:ui-monospace,Menlo,Consolas,monospace;
font-size:11px;padding:1px 6px;border-radius:6px;background:rgba(var(--v-theme-on-surface,0,0,0),.07)}
.cd2strm-page .cd2strm-main{min-width:0}
.cd2strm-page .cd2strm-adr{display:inline-flex;align-items:center;gap:6px}
/* 活动流：时间线行（时间 / 轴 / 内容） */
.cd2strm-page .cd2strm-fsec{border-top:1px solid rgba(var(--v-theme-on-surface,0,0,0),.10);margin-top:10px;padding-top:7px}
.cd2strm-page .cd2strm-fhead{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:2px}
.cd2strm-page .cd2strm-fh{font-size:12.5px;font-weight:600;opacity:.85}
.cd2strm-page .cd2strm-feed{padding-top:2px}
.cd2strm-page .cd2strm-fi{display:grid;grid-template-columns:82px 12px minmax(0,1fr);gap:8px;padding:5px 0}
.cd2strm-page .cd2strm-fi .tm{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:11px;opacity:.55;
padding-top:2px;white-space:nowrap}
.cd2strm-page .cd2strm-fi .rail{position:relative;display:flex;justify-content:center}
.cd2strm-page .cd2strm-fi .rail .dot{width:8px;height:8px;border-radius:50%;margin-top:5px;
background:rgb(var(--v-theme-primary,103,80,164))}
.cd2strm-page .cd2strm-fi .rail::before{content:"";position:absolute;top:14px;bottom:-7px;width:1px;
background:rgba(var(--v-theme-on-surface,0,0,0),.13)}
.cd2strm-page .cd2strm-fi:last-child .rail::before{display:none}
.cd2strm-page .cd2strm-fi.ok .rail .dot{background:rgb(var(--v-theme-success,46,125,50))}
.cd2strm-page .cd2strm-fi.bad .rail .dot{background:rgb(var(--v-theme-error,198,40,40))}
.cd2strm-page .cd2strm-fi.skip .rail .dot{background:rgba(var(--v-theme-on-surface,0,0,0),.30)}
.cd2strm-page .cd2strm-fi.run .rail .dot{background:rgb(var(--v-theme-warning,237,108,2))}
.cd2strm-page .cd2strm-fi .bd{min-width:0}
.cd2strm-page .cd2strm-fi .top{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.cd2strm-page .cd2strm-fi .nm{font-size:13px;font-weight:600;min-width:0;max-width:100%;
overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cd2strm-page .cd2strm-fi .dr{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:11px;opacity:.5;
margin-top:1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cd2strm-page .cd2strm-fi .mt{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-top:2px;font-size:11.5px}
.cd2strm-page .cd2strm-fi .files{margin-top:1px}
@media (max-width:1000px){
.cd2strm-page .cd2strm-fi{grid-template-columns:66px 12px minmax(0,1fr)}
}
/* ===== 通知合并（方案 A）：同目录 + 同类型的相邻通知折叠成一条聚合行 ===== */
.cd2strm-page details.cd2strm-gwrap{margin:2px 0}
.cd2strm-page details.cd2strm-gwrap>summary{list-style:none;cursor:pointer;display:grid;
grid-template-columns:82px 12px minmax(0,1fr);gap:8px;padding:5px 0}
.cd2strm-page details.cd2strm-gwrap>summary::-webkit-details-marker{display:none}
.cd2strm-page details.cd2strm-gwrap>summary .tm{font-family:ui-monospace,Menlo,Consolas,monospace;
font-size:11px;opacity:.55;padding-top:2px;white-space:nowrap}
.cd2strm-page details.cd2strm-gwrap>summary .rail{position:relative;display:flex;justify-content:center}
.cd2strm-page details.cd2strm-gwrap>summary .rail .dot{width:9px;height:9px;border-radius:3px;
margin-top:5px;background:rgb(var(--v-theme-warning,237,108,2))}
.cd2strm-page details.cd2strm-gwrap>summary .rail::before{content:"";position:absolute;top:14px;bottom:-7px;
width:1px;background:rgba(var(--v-theme-on-surface,0,0,0),.13)}
.cd2strm-page details.cd2strm-gwrap:last-child>summary .rail::before{display:none}
.cd2strm-page .cd2strm-gsum{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.cd2strm-page .cd2strm-gsum .nm{font-size:13px;font-weight:600;min-width:0;
overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cd2strm-page .cd2strm-gsum .cnt{font-size:12px;opacity:.75;white-space:nowrap}
/* 展开/收起提示挂在 .mt 里（不是 .cd2strm-gsum）：按 details[open] 切换，只显示一个 */
.cd2strm-page details.cd2strm-gwrap>summary .chev{margin-left:auto;font-size:10.5px;opacity:.55;
white-space:nowrap}
.cd2strm-page details.cd2strm-gwrap>summary .cd2strm-gopen{display:none}
.cd2strm-page details.cd2strm-gwrap[open]>summary .cd2strm-gopen{display:inline}
.cd2strm-page details.cd2strm-gwrap[open]>summary .cd2strm-gclosed{display:none}
.cd2strm-page details.cd2strm-gwrap .cd2strm-gdet{margin:2px 0 6px 102px;padding-left:10px;
border-left:1px dashed rgba(var(--v-theme-on-surface,0,0,0),.16)}
.cd2strm-page details.cd2strm-gwrap .cd2strm-gdet .cd2strm-fi{padding:4px 0}
/* 通知与操作记录：固定高度 + 垂直滚动条（内联样式为主，这里是增强）*/
.cd2strm-page .cd2strm-fsec .cd2strm-feed{max-height:420px;overflow-y:auto;
padding-right:4px;scrollbar-width:thin}
.cd2strm-page .cd2strm-fsec .cd2strm-feed::-webkit-scrollbar{width:8px}
.cd2strm-page .cd2strm-fsec .cd2strm-feed::-webkit-scrollbar-thumb{
background:rgba(var(--v-theme-on-surface,0,0,0),.22);border-radius:4px}
.cd2strm-page .cd2strm-fsec .cd2strm-feed::-webkit-scrollbar-track{
background:rgba(var(--v-theme-on-surface,0,0,0),.05);border-radius:4px}
/* 通知 ↔ 操作记录 的对应提示 */
.cd2strm-page .cd2strm-link{font-size:11.5px;color:rgb(var(--v-theme-primary,103,80,164));opacity:.9;
font-family:ui-monospace,Menlo,Consolas,monospace;white-space:nowrap}
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
    "g-notify_merge": "详情页把「同一目录 + 同类型」且在时间窗内的连续通知折叠成一条可展开的聚合行，只影响显示，数据仍逐条保存",
    "g-notify_merge_seconds": "相邻两条通知间隔超过这个秒数就不再合并；整组跨度最多 300 秒，含失败或待回填的组默认展开",
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
/* 目录组下方的「复制这一组」与新建槽位 */
.cd2strm-form .cd2strm-copy-row{display:flex;align-items:center;gap:8px;padding:6px 10px 8px;
border-top:1px dashed rgba(var(--v-theme-on-surface,0,0,0),.12)}
.cd2strm-form .cd2strm-copy-hint{font-size:11.5px;opacity:.6;min-width:0}
.cd2strm-form .cd2strm-copy-btn{display:inline-flex;align-items:center;flex:0 0 auto;font-size:12.5px;
line-height:24px;padding:0 12px;border-radius:999px;cursor:pointer;
border:1px solid rgba(var(--v-theme-primary,103,80,164),.35);
color:rgb(var(--v-theme-primary,103,80,164));background:rgba(var(--v-theme-primary,103,80,164),.08)}
.cd2strm-form .cd2strm-new-fold{border-style:dashed}
.cd2strm-form .cd2strm-new-head{display:flex;align-items:center;gap:8px;flex-wrap:wrap;
padding:7px 12px;background:rgba(var(--v-theme-on-surface,0,0,0),.03);border-radius:9px 9px 0 0}
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
    """配置页的一张卡片：标题栏（色条 + 标题）与卡片内容；外框与色条按卡片主题取色。"""
    accent = FORM_CARD_COLORS.get(title, "#3b82f6")
    return {
        "component": "div",
        "props": {"class": "cd2strm-card", "style": _accent_border(accent, "1.5px", 0.6)},
        "content": [
            {
                "component": "div",
                "props": {"class": "cd2strm-chead"},
                "content": [
                    {"component": "span", "props": {"class": "cd2strm-stripe", "style": {"background": accent}}},
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
        copy_target = len(rules) if len(rules) < MAX_RULES else None
        if index:
            # 展开后组与组之间用上一组的颜色画一条横线
            sync_content.append(_group_divider(index - 1))
        sync_content.append(_rule_fold(index, rule, copy_target))
    if len(rules) < MAX_RULES:
        sync_content.append(_new_rule_fold(len(rules)))
    organize_content: List[Dict[str, Any]] = [_organize_card()]
    for index, rule in enumerate(organize_rules):
        if index:
            organize_content.append(_group_divider(index - 1))
        copy_target = len(organize_rules) if len(organize_rules) < MAX_ORGANIZE_RULES else None
        organize_content.append(_organize_group_fold(index, rule, copy_target))
    if len(organize_rules) < MAX_ORGANIZE_RULES:
        organize_content.append(_new_organize_fold(len(organize_rules)))
    mirror_content: List[Dict[str, Any]] = [_mirror_card()]
    for index, rule in enumerate(mirror_rules):
        if index:
            mirror_content.append(_group_divider(index - 1))
        copy_target = len(mirror_rules) if len(mirror_rules) < MAX_MIRROR_RULES else None
        mirror_content.append(_mirror_group_fold(index, rule, copy_target))
    if len(mirror_rules) < MAX_MIRROR_RULES:
        mirror_content.append(_new_mirror_fold(len(mirror_rules)))
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
    """通知卡片（通知开关 + 详情页通知合并显示）。"""
    return _form_card(
        "通知",
        [
            _form_section(
                "通知",
                [
                    _switch("notify", "发送通知", "g-notify"),
                    _switch("notify_only_matched", "详情页只显示命中通知", "g-notify_only_matched"),
                ],
            ),
            _form_section(
                "详情页通知显示",
                [
                    _switch("notify_merge", "合并相邻通知", "g-notify_merge"),
                    _select(
                        "notify_merge_seconds",
                        "合并时间窗",
                        MERGE_WINDOW_ITEMS,
                        "g-notify_merge_seconds",
                    ),
                ],
            ),
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


def _copy_button(
    prefix: str, fields: List[str], source_index: int, target_index: int, slot_flag: str
) -> Dict[str, Any]:
    """通用的「复制这一组」按钮：把本组全部字段写进下方的新建槽位。

    纯前端赋值（与全局排除目录的「＋」同一套机制）：不调用接口、不改已保存的配置，
    用户检查完再按保存，才会真正多出一组。prefix 是键前缀（r / o / d）。
    """
    assignments = "; ".join(
        f"{prefix}{target_index}_{name} = {prefix}{source_index}_{name}" for name in fields
    )
    show_slot = (
        f"{slot_flag} = Math.max("
        f"(typeof {slot_flag} === 'undefined' ? 0 : {slot_flag}), 1)"
    )
    return {
        "component": "span",
        "props": {
            "class": "cd2strm-copy-btn",
            "title": "把这一组的全部设置复制到下方「新建目录组」，保存后生效",
            "onClick": f"(event) => {{ {assignments}; {show_slot}; }}",
        },
        "text": "复制这一组",
    }


def _rule_copy_button(source_index: int, target_index: int) -> Dict[str, Any]:
    """STRM 目录组的「复制这一组」（键前缀 r）。"""
    return _copy_button("r", rule_field_names(), source_index, target_index, "new_rule_slots")


def _organize_copy_row(index: int, target_index: int) -> Dict[str, Any]:
    """整理组的「复制这一组」（键前缀 o）。"""
    return _group_copy_row("o", organize_field_names(), index, target_index, "new_organize_slots")


def _mirror_copy_row(index: int, target_index: int) -> Dict[str, Any]:
    """镜像组的「复制这一组」（键前缀 d）。"""
    return _group_copy_row("d", mirror_field_names(), index, target_index, "new_mirror_slots")


def _group_copy_row(
    prefix: str,
    fields: List[str],
    source_index: int,
    target_index: int,
    slot_flag: str,
    hint: str = "要再建一组同样的？",
) -> Dict[str, Any]:
    """组卡片下方的复制入口（配置页专用）。"""
    return {
        "component": "div",
        "props": {"class": "cd2strm-copy-row"},
        "content": [
            {"component": "span", "props": {"class": "cd2strm-copy-hint"}, "text": hint},
            _copy_button(prefix, fields, source_index, target_index, slot_flag),
        ],
    }


def _new_group_fold(
    *,
    title: str,
    index: int,
    prefix: str,
    fields: List[str],
    slot_flag: str,
    body: Dict[str, Any],
    hint: str,
) -> Dict[str, Any]:
    """通用的「新建槽位」：默认隐藏，点任意一组的「复制这一组」后才出现。"""
    guard = f"(typeof {slot_flag} === 'undefined' ? 0 : {slot_flag})"
    clear = "; ".join(f"{prefix}{index}_{name} = ''" for name in fields) + f"; {slot_flag} = 0"
    return {
        "component": "div",
        "props": {"class": "cd2strm-rule-fold cd2strm-new-fold", "show": f"{guard} >= 1"},
        "content": [
            {
                "component": "div",
                "props": {"class": "cd2strm-new-head"},
                "content": [
                    {"component": "span", "props": {"class": "cd2strm-rname"}, "text": title},
                    _chip("保存后生效", "primary"),
                    {"component": "span", "props": {"class": "cd2strm-copy-hint"}, "text": hint},
                    {"component": "span", "props": {"class": "cd2strm-sp"}},
                    {
                        "component": "span",
                        "props": {
                            "class": "cd2strm-copy-btn",
                            "title": "清空这个槽位（不保存就不会创建）",
                            "onClick": f"(event) => {{ {clear}; }}",
                        },
                        "text": "清空槽位",
                    },
                ],
            },
            body,
        ],
    }


def _new_organize_fold(index: int) -> Dict[str, Any]:
    """整理页的新建槽位。"""
    return _new_group_fold(
        title="新建整理组",
        index=index,
        prefix="o",
        fields=organize_field_names(),
        slot_flag="new_organize_slots",
        body=_organize_body(index),
        hint="上面任意一组点「复制这一组」会把内容填到这里；留空则不会被创建",
    )


def _new_mirror_fold(index: int) -> Dict[str, Any]:
    """镜像页的新建槽位。"""
    return _new_group_fold(
        title="新建镜像组",
        index=index,
        prefix="d",
        fields=mirror_field_names(),
        slot_flag="new_mirror_slots",
        body=_mirror_body(index),
        hint="上面任意一组点「复制这一组」会把内容填到这里；留空则不会被创建",
    )


def _rule_copy_row(index: int, target_index: int) -> Dict[str, Any]:
    """目录组下方的复制入口（配置页专用）。"""
    return {
        "component": "div",
        "props": {"class": "cd2strm-copy-row"},
        "content": [
            {
                "component": "span",
                "props": {"class": "cd2strm-copy-hint"},
                "text": "要再建一组同样的？",
            },
            _rule_copy_button(index, target_index),
        ],
    }


def _new_rule_fold(index: int) -> Dict[str, Any]:
    """配置页的新建槽位：默认隐藏，点任意一组的「复制这一组」后才出现。"""
    guard = "(typeof new_rule_slots === 'undefined' ? 0 : new_rule_slots)"
    clear = (
        "; ".join(f"r{index}_{name} = ''" for name in rule_field_names())
        + "; new_rule_slots = 0"
    )
    return {
        "component": "div",
        "props": {"class": "cd2strm-rule-fold cd2strm-new-fold", "show": f"{guard} >= 1"},
        "content": [
            {
                "component": "div",
                "props": {"class": "cd2strm-new-head"},
                "content": [
                    {"component": "span", "props": {"class": "cd2strm-rname"}, "text": "新建目录组"},
                    _chip("保存后生效", "primary"),
                    {
                        "component": "span",
                        "props": {"class": "cd2strm-copy-hint"},
                        "text": "上面任意一组点「复制这一组」会把内容填到这里；留空则不会被创建",
                    },
                    {"component": "span", "props": {"class": "cd2strm-sp"}},
                    {
                        "component": "span",
                        "props": {
                            "class": "cd2strm-copy-btn",
                            "title": "清空这个槽位（不保存就不会创建）",
                            "onClick": f"(event) => {{ {clear}; }}",
                        },
                        "text": "清空槽位",
                    },
                ],
            },
            _rule_card(index),
        ],
    }


def _rule_fold(index: int, rule: SyncRule, copy_target: Optional[int] = None) -> Dict[str, Any]:
    """把单个目录组包成可独立折叠的区块：默认全部折叠，点开才显示设置项。"""
    body: List[Dict[str, Any]] = [_rule_card(index)]
    if copy_target is not None:
        body.append(_rule_copy_row(index, copy_target))
    return {
        "component": "details",
        "props": {
            "class": "cd2strm-rule-fold",
            "style": _accent_border(_group_accent(index), "1.5px", 0.6),
        },
        "content": [
            _rule_summary(index, rule),
            *body,
        ],
    }


# 各区块外框的配色：不同区块不同颜色（目录组用组标识色）。rgba 直接算好写死，
# 避免在模块顶部调用后面才定义的 _tint()。
BLOCK_BORDERS: Dict[str, Dict[str, Any]] = {
    "conn": {"border": "1px solid rgba(14,165,233,.55)"},    # 连接状态 / 状态行（青）
    "others": {"border": "1px solid rgba(139,92,246,.55)"},  # 未匹配卡片（紫）
    # 说明：记录区 / CD2 通知区这两个「组内框」按用户要求不再着色（2026-09-20），
    # 它们仍各自有中性色的内层滚动框做分区。
}
# 配置页各卡片的配色（按调用顺序取用）
FORM_CARD_COLORS: Dict[str, str] = {
    "启用插件": "#10b981",
    "连接与地址": "#0ea5e9",
    "通知": "#f59e0b",
    "定时扫描": "#06b6d4",
    "全局排除目录": "#8b5cf6",
    "媒体整理": "#3b82f6",
    "镜像移动": "#ec4899",
}


def _accent_border(color: str, width: str = "1px", alpha: float = 0.55) -> Dict[str, Any]:
    """按标识色给区块外框上色（内联样式，宿主一定生效）。"""
    return {"border": f"{width} solid {_tint(color, alpha)}"}


def _group_accent(index: int) -> str:
    """目录组的标识色（与详情页同一套调色板）。"""
    return GROUP_COLORS[index % len(GROUP_COLORS)]


def _group_summary_style(index: int) -> Dict[str, Any]:
    """折叠头的整行淡底（标识色 18%）。"""
    return {"background": _tint(_group_accent(index), 0.18)}


def _group_divider(index: int) -> Dict[str, Any]:
    """组与组之间的彩色横线（用上一组的标识色），展开后一眼看出分界。"""
    return {
        "component": "div",
        "props": {
            "class": "cd2strm-rule-divider",
            "style": {
                "height": "3px",
                "border-radius": "2px",
                "background": _group_accent(index),
                "opacity": "0.55",
                "margin": "12px 0 4px",
            },
        },
        # 带一个隐藏子节点：某些渲染器会跳过没有 content 的节点，这里做个保险
        "content": [{"component": "span", "props": {"style": {"display": "none"}}}],
    }


def _stripe_node(index: int) -> Dict[str, Any]:
    """折叠头左侧的标识色竖条。"""
    return {
        "component": "span",
        "props": {"class": "cd2strm-stripe", "style": {"background": _group_accent(index), "width": "5px"}},
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
        "props": {"class": "cd2strm-rule-summary", "style": _group_summary_style(index)},
        "content": [
            _stripe_node(index),
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
        "props": {"class": "cd2strm-rule-summary", "style": _group_summary_style(index)},
        "content": [
            _stripe_node(index),
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


def _organize_group_fold(
    index: int, rule: OrganizeRule, copy_target: Optional[int] = None
) -> Dict[str, Any]:
    """一个整理组的可折叠区块（默认折叠）；copy_target 有值时在下方给出复制入口。"""
    body: List[Dict[str, Any]] = [_organize_body(index)]
    if copy_target is not None:
        body.append(_organize_copy_row(index, copy_target))
    return {
        "component": "details",
        "props": {"class": "cd2strm-rule-fold", "style": _accent_border(_group_accent(index), "1.5px", 0.6)},
        "content": [_organize_summary(index, rule), *body],
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
        "props": {"class": "cd2strm-rule-summary", "style": _group_summary_style(index)},
        "content": [
            _stripe_node(index),
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


def _mirror_group_fold(
    index: int, rule: MirrorRule, copy_target: Optional[int] = None
) -> Dict[str, Any]:
    """一个镜像组的可折叠区块（默认折叠）；copy_target 有值时在下方给出复制入口。"""
    body: List[Dict[str, Any]] = [_mirror_body(index)]
    if copy_target is not None:
        body.append(_mirror_copy_row(index, copy_target))
    return {
        "component": "details",
        "props": {"class": "cd2strm-rule-fold", "style": _accent_border(_group_accent(index), "1.5px", 0.6)},
        "content": [_mirror_summary(index, rule), *body],
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
    # 三个视图共用：每页条数（合并后按组翻页）与合并窗口（display 由 get_page 写入）
    page_size = max(5, int(display.get("page_size") or 5))
    merge_seconds = max(0, int(display.get("merge_seconds") or 0))
    organize_rules = organize_rules or []
    organize_records = organize_records or []
    mirror_rules = mirror_rules or []
    mirror_records = mirror_records or []
    if view == "mirror":
        mirror_page: List[Dict[str, Any]] = [
            _page_menu(plugin_id, api_token, "mirror"),
            _mirror_status_line(mirror_status or {}, len(mirror_rules)),
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

                    merge_seconds,
                )
            )
        mirror_page.append(_style_block())
        mirror_page.append(_mirror_ignored_card((mirror_status or {}).get("ignored") or []))
        return [{"component": "div", "props": {"class": "cd2strm-page"}, "content": mirror_page}]
    if view == "organize":
        page: List[Dict[str, Any]] = [
            _page_menu(plugin_id, api_token, "organize"),
            _organize_status_line(organize_status or {}, len(organize_rules)),
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

                    merge_seconds,
                )
            )
        page.append(_organize_ignored_card((organize_status or {}).get("ignored") or []))
        page.append(_style_block())
        return [{"component": "div", "props": {"class": "cd2strm-page"}, "content": page}]
    pages = display.get("pages") or {}
    progress = progress or {}
    # 左栏：各目录组的活动流（通知 + 操作记录）；右栏：常驻的运行状态与目录组导览
    blocks: List[Dict[str, Any]] = []
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
        blocks.append(
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
                merge_seconds,
            )
        )
    if others:
        blocks.append(
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
    page: List[Dict[str, Any]] = [
        _page_menu(plugin_id, api_token, "sync"),
        _connection_line(status),
        {"component": "div", "props": {"class": "cd2strm-main"}, "content": blocks},
    ]
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
        "props": {"class": "cd2strm-panel", "style": {**BLOCK_BORDERS["others"]}},
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
                        "props": {"class": "cd2strm-fold", "style": {**BLOCK_BORDERS["others"]}},
                        "content": [
                            {"component": "summary", "text": "展开查看明细"},
                            {"component": "div", "props": {"class": "cd2strm-feed", "style": dict(FEED_BOX_STYLE)}, "content": [head, *rows]},
                        ],
                    }
                ],
            },
        ],
    }


def _record_entries(records: List[Dict[str, Any]], kind: str) -> List[Dict[str, Any]]:
    """把整理 / 镜像记录整理成「可合并条目」：时间 + 触发 + 结果 + 目录 + 明细行。

    明细行沿用两个视图原有的表格行，保证逐条内容不丢；聚合与展示交给下面几个构件。
    """
    entries: List[Dict[str, Any]] = []
    for item in records:
        if kind == "organize":
            path = str(item.get("file") or "")
            extra = str(item.get("media") or "")
            node = _organize_record_node(item)
        else:
            path = str(item.get("path") or "")
            extra = ""
            node = _mirror_record_node(item)
        directory, name = _split_path(path)
        entries.append(
            {
                "time": str(item.get("time") or ""),
                "trigger": str(item.get("trigger") or ""),
                "result": str(item.get("result") or ""),
                "dir": directory,
                "name": name,
                "extra": extra,
                "node": node,
            }
        )
    return entries


def _merge_entries(entries: List[Dict[str, Any]], seconds: int) -> List[List[Dict[str, Any]]]:
    """相邻的「同触发方式 + 同目录」记录合并成组（与操作记录同一套规则）。"""
    if seconds <= 0:
        return [[entry] for entry in entries]
    groups: List[Dict[str, Any]] = []
    for entry in entries:
        stamp = _time_seconds(entry["time"])
        key = (entry["trigger"], entry["dir"])
        if groups:
            current = groups[-1]
            if (
                current["key"] == key
                and stamp is not None
                and current["last"] is not None
                and abs(current["last"] - stamp) <= seconds
                and abs(current["first"] - stamp) <= MERGE_SPAN_LIMIT
            ):
                current["rows"].append(entry)
                current["last"] = stamp
                continue
        groups.append({"key": key, "rows": [entry], "first": stamp, "last": stamp})
    return [item["rows"] for item in groups]


def _record_entry_group(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """把多条记录渲染成一条聚合行（标签 + 计数 + 可展开明细），与操作记录聚合并行同款。"""
    first = rows[0]
    directory = first["dir"]
    total = len(rows)
    ok = sum(1 for item in rows if item["result"] == "success")
    skipped = sum(1 for item in rows if item["result"] == "skipped")
    failed = total - ok - skipped
    tail = "/".join([part for part in directory.split("/") if part][-2:]) or directory
    head: List[Dict[str, Any]] = [
        _chip(
            "事件" if first["trigger"] == "event" else "手动",
            "info" if first["trigger"] == "event" else "grey",
        ),
        {"component": "span", "props": {"class": "nm", "title": directory}, "text": tail or "（无目录）"},
        {"component": "span", "props": {"class": "cnt"}, "text": f"{total} 次"},
    ]
    meta: List[Dict[str, Any]] = [
        {"component": "span", "props": {"class": "cd2strm-st ok"}, "text": f"成功 {ok}"}
    ]
    if skipped:
        meta.append({"component": "span", "props": {"class": "cd2strm-st skip"}, "text": f"跳过 {skipped}"})
    if failed:
        meta.append({"component": "span", "props": {"class": "cd2strm-st bad"}, "text": f"失败 {failed}"})
    if first.get("extra"):
        meta.append(_chip(str(first["extra"]), "grey"))
    if total > 1:
        span = abs(
            (_time_seconds(rows[0]["time"]) or 0) - (_time_seconds(rows[-1]["time"]) or 0)
        )
        meta.append({"component": "span", "props": {"class": "cd2strm-res"}, "text": f"历时 {span}s"})
    meta.append(
        {
            "component": "span",
            "props": {"class": "chev"},
            "content": [
                {"component": "span", "props": {"class": "cd2strm-gclosed"}, "text": f"展开 {total} 条 ▾"},
                {"component": "span", "props": {"class": "cd2strm-gopen"}, "text": f"收起 {total} 条 ▴"},
            ],
        }
    )
    times = [str(item["time"]) for item in rows]
    range_text = times[0] if len(times) == 1 else f'{times[-1].split(" ")[-1]}–{times[0].split(" ")[-1]}'
    props: Dict[str, Any] = {"class": "cd2strm-gwrap"}
    if failed:
        props["open"] = True
    return {
        "component": "details",
        "props": props,
        "content": [
            {
                "component": "summary",
                "content": [
                    {"component": "span", "props": {"class": "tm"}, "text": range_text},
                    {
                        "component": "span",
                        "props": {"class": "rail"},
                        "content": [{"component": "span", "props": {"class": "dot"}}],
                    },
                    {
                        "component": "div",
                        "content": [
                            {"component": "div", "props": {"class": "cd2strm-gsum"}, "content": head},
                            {"component": "div", "props": {"class": "dr", "title": directory}, "text": directory},
                            {"component": "div", "props": {"class": "mt"}, "content": meta},
                        ],
                    },
                ],
            },
            {
                "component": "div",
                "props": {"class": "cd2strm-gdet"},
                "content": [item["node"] for item in rows],
            },
        ],
    }


def _records_feed(
    title: str, entries: List[Dict[str, Any]], seconds: int, table_head: Dict[str, Any]
) -> Dict[str, Any]:
    """记录区（与 STRM 页的操作记录同款）：合并聚合行 + 固定高度滚动框 + 计数徽章。"""
    groups = _merge_entries(entries, seconds)
    total = len(entries)
    items: List[Dict[str, Any]] = [
        group[0]["node"] if len(group) == 1 else _record_entry_group(group) for group in groups
    ]
    if not items:
        items = [{"component": "div", "props": {"class": "cd2strm-count"}, "text": f"暂无{title}"}]
    head_content: List[Dict[str, Any]] = [
        {"component": "span", "props": {"class": "cd2strm-fh"}, "text": title},
        _chip(f"共 {total} 条", "grey"),
    ]
    if len(groups) < total:
        head_content.append(_chip(f"合并为 {len(groups)} 组", "primary"))
    head_content.append(
        {"component": "span", "props": {"class": "cd2strm-count"}, "text": f"已显示最新 {total} 条"}
    )
    return {
        "component": "div",
        "props": {"class": "cd2strm-fsec"},
        "content": [
            {"component": "div", "props": {"class": "cd2strm-fhead"}, "content": head_content},
            {
                "component": "div",
                "props": {"class": "cd2strm-feed", "style": dict(FEED_BOX_STYLE)},
                "content": [table_head, *items],
            },
        ],
    }


def _organize_record_node(item: Dict[str, Any]) -> Dict[str, Any]:
    """单条整理记录的明细行（沿用原有表格列）。"""
    result = str(item.get("result") or "")
    if result == "success":
        result_class, result_text = "cd2strm-ok", "成功"
    elif result == "skipped":
        result_class, result_text = "cd2strm-skip", "跳过"
    else:
        result_class, result_text = "cd2strm-bad", "失败"
    return {
        "component": "div",
        "props": {"class": "cd2strm-tr org"},
        "content": [
            {"component": "div", "props": {"class": "cd2strm-t"}, "text": str(item.get("time") or "")},
            {
                "component": "div",
                "content": [
                    _chip(
                        "事件" if item.get("trigger") == "event" else "手动",
                        "info" if item.get("trigger") == "event" else "",
                    )
                ],
            },
            {
                "component": "div",
                "props": {"class": result_class, "title": str(item.get("message") or "")},
                "text": result_text,
            },
            {
                "component": "div",
                "props": {"class": "cd2strm-pth", "title": str(item.get("file") or "")},
                "text": str(item.get("file") or ""),
            },
            {
                "component": "div",
                "props": {
                    "class": "cd2strm-s",
                    "title": str(item.get("media") or item.get("message") or ""),
                },
                "text": str(item.get("media") or "—"),
            },
        ],
    }
def _organize_records_head() -> Dict[str, Any]:
    """整理记录的表头（明细行仍按这五列展示）。"""
    return {
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


def _organize_group_card(
    plugin_id: str,
    api_token: str,
    index: int,
    rule: OrganizeRule,
    stats: Dict[str, Any],
    records: List[Dict[str, Any]],
    hit_events: Optional[List[Dict[str, Any]]] = None,
    page_size: int = 5,
    merge_seconds: int = 0,
) -> Dict[str, Any]:
    """整理组面板：路径 + 按钮 + 整理记录（合并聚合行）+ CD2 通知时间线。"""
    name = rule.display_name(index)
    accent = GROUP_COLORS[index % len(GROUP_COLORS)]
    head: List[Dict[str, Any]] = [
        {
            "component": "span",
            "props": {"class": "cd2strm-stripe", "style": {"background": accent, "width": "5px"}},
        },
        {
            "component": "span",
            "props": {
                "class": "cd2strm-idx",
                "style": {
                    "background": accent,
                    "color": "#fff",
                    "border-radius": "4px",
                    "padding": "0 6px",
                    "line-height": "18px",
                    "font-weight": "700",
                },
            },
            "text": str(index + 1),
        },
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
            "props": {"class": "cd2strm-btns"},
            "content": [
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
        # 记录在上、CD2 通知在下（与 STRM 同步页一致）
        _records_feed("整理记录", _record_entries(records, "organize"), merge_seconds, _organize_records_head()),
        _sync_feed(
            1,
            page_size,
            _merge_events(hit_events or [], merge_seconds),
            None,
            None,
            "暂无命中通知：只有命中本整理组规则的通知才会出现在这里。",
        ),
    ]
    props: Dict[str, Any] = {
        "class": "cd2strm-group",
        "open": True,
        "style": {**_accent_border(accent, "1.5px", 0.65), "border-radius": "10px"},
    }
    return {
        "component": "details",
        "props": props,
        "content": [
            {
                "component": "summary",
                "props": {"class": "cd2strm-phead", "style": {"background": _tint(accent, 0.18)}},
                "content": head,
            },
            {"component": "div", "props": {"class": "cd2strm-sub"}, "content": sub},
        ],
    }


def _result_class(result: str) -> str:
    """记录结果 → 状态类名（三态：成功 / 跳过 / 失败）。"""
    if result == "success":
        return "cd2strm-ok"
    if result == "skipped":
        return "cd2strm-skip"
    return "cd2strm-bad"


def _result_text(result: str) -> str:
    """记录结果 → 中文文案（与整理页一致）。"""
    if result == "success":
        return "成功"
    if result == "skipped":
        return "跳过"
    return "失败"


def _mirror_record_node(item: Dict[str, Any]) -> Dict[str, Any]:
    """单条镜像记录的明细行（沿用原有表格列）。"""
    return {
        "component": "div",
        "props": {"class": "cd2strm-tr mir"},
        "content": [
            {"component": "div", "props": {"class": "cd2strm-t"}, "text": str(item.get("time") or "")},
            {
                "component": "div",
                "content": [
                    _chip(
                        "事件" if item.get("trigger") == "event" else "手动",
                        "info" if item.get("trigger") == "event" else "grey",
                    )
                ],
            },
            {
                "component": "div",
                "props": {
                    "class": _result_class(str(item.get("result") or "")),
                    "title": str(item.get("message") or ""),
                },
                "text": _result_text(str(item.get("result") or "")),
            },
            {
                "component": "div",
                "props": {"class": "cd2strm-pth", "title": str(item.get("path") or "")},
                "text": str(item.get("path") or ""),
            },
            {
                "component": "div",
                "props": {"class": "cd2strm-s", "title": str(item.get("target") or "")},
                "text": str(item.get("target") or ""),
            },
        ],
    }
def _mirror_records_head() -> Dict[str, Any]:
    """镜像记录的表头。"""
    return {
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
                    {"component": "div", "props": {"class": "cd2strm-t"}, "text": str(item.get("time") or "")},
                    {
                        "component": "div",
                        "content": [
                            # 与整理页一致：变更用中文徽章并按类型着色
                            _chip(
                                CHANGE_LABELS.get(str(item.get("change_type") or ""), "变更"),
                                CHANGE_TONES.get(str(item.get("change_type") or ""), "grey"),
                            )
                        ],
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
                            "class": "cd2strm-s cd2strm-bad",
                            "title": str(item.get("reason") or ""),
                        },
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
        "props": {"class": "cd2strm-fold", "style": {**BLOCK_BORDERS["others"]}},
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
    merge_seconds: int = 0,
) -> Dict[str, Any]:
    """镜像组面板：三项路径 + 按钮 + 镜像记录（合并聚合行）+ CD2 通知时间线。"""
    accent = GROUP_COLORS[index % len(GROUP_COLORS)]
    head: List[Dict[str, Any]] = [
        {
            "component": "span",
            "props": {"class": "cd2strm-stripe", "style": {"background": accent, "width": "5px"}},
        },
        {
            "component": "span",
            "props": {
                "class": "cd2strm-idx",
                "style": {
                    "background": accent,
                    "color": "#fff",
                    "border-radius": "4px",
                    "padding": "0 6px",
                    "line-height": "18px",
                    "font-weight": "700",
                },
            },
            "text": str(index + 1),
        },
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
            "props": {"class": "cd2strm-btns"},
            "content": [
                _button(
                    f"plugin/{plugin_id}/mirror?apikey={api_token}",
                    {"index": index, "operation": "delete"},
                    "删除这一组",
                    "mdi-delete-outline",
                    "error",
                ),
            ],
        },
        # 记录在上、CD2 通知在下（与 STRM 同步页一致）
        _records_feed("镜像记录", _record_entries(records, "mirror"), merge_seconds, _mirror_records_head()),
        _sync_feed(
            1,
            5,
            _merge_events(hit_events or [], merge_seconds),
            None,
            None,
            "暂无命中通知：只有监听目录里的删除通知才会命中本镜像组。",
        ),
    ]
    return _collapsible(
        summary=head,
        body=body,
        opened=True,
        css="cd2strm-group",
        summary_style={"background": _tint(accent, 0.18)},
        # 展开后的整块外框也用该组标识色
        style={**_accent_border(accent, "1.5px", 0.65), "border-radius": "10px"},
    )


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
    merge_seconds: int = 0,
) -> Dict[str, Any]:
    """构建单个目录组卡片：标题徽章、路径、操作按钮与该组的通知、操作记录。"""
    base = f"plugin/{plugin_id}"
    suffix = f"?apikey={api_token}"
    key = str(index)
    precise = (rule.process_mode or "precise") == "precise"
    failures = _safe_count(stats, "links_failed") + _safe_count(stats, "metadata_failed")
    body: List[Dict[str, Any]] = [
        {
            "component": "div",
            "props": {"class": "cd2strm-paths"},
            "content": [
                _path_cell("源目录", rule.media_dir or "未设置"),
                _path_cell("目的目录", rule.local_dir or "未设置"),
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
    note_groups = _merge_events(events, merge_seconds)
    act_groups = _merge_actions(actions, merge_seconds)
    pairs = _pair_groups(note_groups, act_groups)
    reverse_pairs = {
        act_index: note_index
        for note_index, act_indexes in pairs.items()
        for act_index in act_indexes
    }
    # 先操作记录（做了什么、生成了什么），再 CD2 通知（收到什么），两边按目录与时间对应
    body.append(_record_feed(page, page_size, act_groups, reverse_pairs, note_groups))
    body.append(_sync_feed(page, page_size, note_groups, pairs, act_groups))
    body.append(
        _pager(
            plugin_id,
            api_token,
            key,
            page,
            page_size,
            max(len(note_groups), len(act_groups)),
        )
    )
    # 头部：标识色条（每组一色）+ 序号徽章 + 组名 + 状态徽章 + 上次处理时间；
    # 全部目录组默认展开（用户要求），需要收起时点标题
    accent = GROUP_COLORS[index % len(GROUP_COLORS)]
    head: List[Dict[str, Any]] = [
        {
            "component": "span",
            "props": {
                "class": "cd2strm-stripe",
                "style": {"background": accent, "width": "5px"},
            },
        }
    ]
    head.append(
        {
            "component": "span",
            "props": {
                "class": "cd2strm-idx",
                "style": {
                    "background": accent,
                    "color": "#fff",
                    "border-radius": "4px",
                    "padding": "0 6px",
                    "line-height": "18px",
                    "font-weight": "700",
                },
                "title": f"第 {index + 1} 组",
            },
            "text": str(index + 1),
        }
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
    if failures:
        head.append(_chip(f"失败 {failures}", "error"))
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
    return _collapsible(
        summary=head,
        body=body,
        opened=True,
        css="cd2strm-group",
        # 整个组头一行染成该组的标识色（左侧再压一条实色竖条），一眼区分是哪一组
        summary_style={"background": _tint(accent, 0.18)},
        # 展开后的整块外框也用该组标识色
        style={**_accent_border(accent, "1.5px", 0.65), "border-radius": "10px"},
    )


def _collapsible(
    summary: List[Dict[str, Any]],
    body: List[Dict[str, Any]],
    opened: bool = False,
    css: str = "",
    summary_style: Optional[Dict[str, Any]] = None,
    style: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """构造原生可折叠块：details + summary，opened 决定默认是否展开。

    summary_style 用于给折叠头整行上色（目录组标识色）。
    """
    classes = "cd2strm-fold"
    if css:
        classes = f"{classes} {css}"
    props: Dict[str, Any] = {"class": classes}
    if opened:
        props["open"] = True
    if style:
        props["style"] = dict(style)
    summary_props: Dict[str, Any] = {}
    if summary_style:
        summary_props["style"] = dict(summary_style)
    return {
        "component": "details",
        "props": props,
        "content": [
            {"component": "summary", "props": summary_props, "content": summary},
            {"component": "div", "props": {"class": "cd2strm-sub"}, "content": body},
        ],
    }


# ---------------------------------------------------------------- 详情页 C 布局构建件
# 「活动流 + 常驻侧栏」：左栏按目录组给出时间线式的通知与操作记录流，右栏常驻运行状态与目录组导览。
# 本组构件只做排布与呈现；按钮、开关、分页、接口调用一律沿用原有构件，保证功能不丢。


def _split_path(path: str) -> tuple:
    """把路径拆成（目录, 文件名）：文件名在活动流里加粗，目录淡显。"""
    head, _, tail = path.rpartition("/")
    return head, tail


def _side_card(title: str, content: List[Dict[str, Any]]) -> Dict[str, Any]:
    """构造侧栏卡片（标题 + 若干内容节点）。"""
    return {
        "component": "div",
        "props": {"class": "cd2strm-scard"},
        "content": [
            {"component": "div", "props": {"class": "hd"}, "text": title},
            *content,
        ],
    }


def _status_line(
    title: str,
    parts: List[Tuple[str, str, str]],
    chips: Optional[List[Tuple[str, str]]] = None,
    hint: str = "",
    alerts: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """一行式状态行（与「连接状态」同款）：标题 + 若干「标签 值」+ 徽章 + 提示 + 红色告警。

    整理 / 镜像两个视图的状态区用它替代原来那块面板+KPI 网格，保持三个视图观感一致。
    """
    content: List[Dict[str, Any]] = [
        {"component": "span", "props": {"class": "cd2strm-fh"}, "text": title}
    ]
    for label, value, tone in parts:
        content.append({"component": "span", "props": {"style": dict(CONN_SEP_STYLE)}})
        content.append(
            {
                "component": "span",
                "props": {"style": {"display": "inline-flex", "align-items": "baseline", "gap": "5px"}},
                "content": [
                    {"component": "span", "props": {"class": "cd2strm-count"}, "text": label},
                    {"component": "span", "props": {"class": f"cd2strm-st {tone}".strip()}, "text": value},
                ],
            }
        )
    for text, tone in chips or []:
        content.append(_chip(text, tone))
    if hint:
        content.append(
            {"component": "span", "props": {"class": "cd2strm-hint", "style": {"margin": "0"}}, "text": hint}
        )
    for text in alerts or []:
        content.append({"component": "span", "props": {"class": "cd2strm-bad"}, "text": text})
    return {
        "component": "div",
        "props": {"class": "cd2strm-connline", "style": {**CONN_LINE_STYLE, **BLOCK_BORDERS["conn"]}},
        "content": content,
    }


def _organize_status_line(status: Dict[str, Any], group_count: int) -> Dict[str, Any]:
    """媒体整理的状态一行式。"""
    enabled = bool(status.get("organize_enabled"))
    alerts: List[str] = []
    if not enabled:
        alerts.append("媒体整理当前未启用：到配置页「媒体整理配置」里开启并填写整理组")
    if status.get("last_error"):
        alerts.append(f"最近错误：{status['last_error']}")
    return _status_line(
        "整理状态",
        [
            ("收到通知", str(status.get("accepted", 0)), ""),
            ("待整理", str(status.get("pending", 0)), "muted"),
            ("正在整理", str(status.get("running", 0)), "muted"),
            ("整理组", f"{group_count} 组", "muted"),
            ("整理记录", f"{int(status.get('record_count') or 0)} 条", "muted"),
        ],
        chips=[
            ("已启用" if enabled else "未启用", "success" if enabled else "grey"),
            ("通知开" if status.get("notify") else "通知关", "primary" if status.get("notify") else "grey"),
            ("通知来源：与 STRM 同步共用", "grey"),
            ("整理链：MoviePilot TransferChain", "grey"),
        ],
        alerts=alerts,
    )


def _mirror_status_line(status: Dict[str, Any], group_count: int) -> Dict[str, Any]:
    """镜像移动的状态一行式（含预演模式提醒）。"""
    enabled = bool(status.get("enabled"))
    dry_run = bool(status.get("dry_run", True))
    return _status_line(
        "镜像状态",
        [
            ("受理通知", str(status.get("accepted", 0)), ""),
            ("移动文件", str(status.get("moved_files", 0)), "ok"),
            ("移动目录", str(status.get("moved_dirs", 0)), "ok"),
            ("保护跳过", str(status.get("protected", 0)), "muted"),
            ("失败", str(status.get("failed", 0)), "bad" if status.get("failed") else "muted"),
            ("共", f"{group_count} 组", "muted"),
        ],
        chips=[
            ("已启用" if enabled else "已停用", "success" if enabled else "grey"),
            ("预演模式（不移动文件）" if dry_run else "正式执行（会移动文件）", "warn" if dry_run else "error"),
        ],
        hint=(
            "预演模式开启时只记录「将要移动什么」，不会真正移动文件"
            if dry_run
            else "监听目录里删除什么，就把镜像目录里对应的对象移到回收站；保护白名单命中的对象不移动"
        ),
    )


def _connection_line(status: Dict[str, Any]) -> Dict[str, Any]:
    """连接状态一行式：标题 + 每路地址（状态点、主机、连接情况、消息数）+ 最近错误。"""
    items: List[Dict[str, Any]] = [
        {"component": "span", "props": {"class": "cd2strm-fh"}, "text": "连接状态"}
    ]
    connections = status.get("connections") or []
    if not connections:
        items.append(
            {
                "component": "span",
                "props": {"class": "cd2strm-count"},
                "text": "插件未启用" if not status.get("enabled") else "尚未配置 CloudDrive2 地址",
            }
        )
    for index, item in enumerate(connections):
        ok = bool(item.get("connected"))
        host = str(item.get("host") or "")
        items.append({"component": "span", "props": {"style": dict(CONN_SEP_STYLE)}})
        addr: List[Dict[str, Any]] = [
            {
                "component": "span",
                # 类名与内联样式都给上：类名沿用既有 CSS，内联保证宿主不应用注入样式时也正常
                "props": {
                    "class": "cd2strm-dot",
                    "style": dict(
                        CONN_DOT_STYLE,
                        background=f"rgb(var(--v-theme-{'success' if ok else 'error'},46,125,50))",
                    ),
                },
            },
            {
                "component": "span",
                "text": str(item.get("label") or f"地址 {index + 1}"),
            },
        ]
        if host:
            addr.append(
                {
                    "component": "code",
                    "props": {"title": host, "style": {"font-size": "11.5px", "opacity": ".85"}},
                    "text": host,
                }
            )
        addr.append(
            {
                "component": "span",
                "props": {"class": "cd2strm-count"},
                "text": f"{'已连接' if ok else '未连接'} · {int(item.get('message_count') or 0)} 条",
            }
        )
        items.append({"component": "span", "props": {"class": "cd2strm-adr"}, "content": addr})
    if status.get("last_error"):
        items.append({"component": "span", "props": {"style": dict(CONN_SEP_STYLE)}})
        items.append(
            {
                "component": "span",
                "props": {"class": "cd2strm-bad", "title": str(status["last_error"])},
                "text": f"最近错误：{status['last_error']}",
            }
        )
    return {"component": "div", "props": {"class": "cd2strm-connline", "style": {**CONN_LINE_STYLE, **BLOCK_BORDERS["conn"]}}, "content": items}


def _feed_line(event: Dict[str, Any]) -> Dict[str, Any]:
    """把一条 CD2 通知渲染成活动流行：时间 / 轴点 / 变更+文件名 / 目录 / 结果。"""
    path = str(event.get("path") or "")
    directory, name = _split_path(path)
    result = str(event.get("result") or "")
    if not event.get("done"):
        tone, state_text = "run", "处理中"
    elif result.startswith("失败"):
        tone, state_text = "bad", "失败"
    elif result.startswith("跳过"):
        tone, state_text = "skip", "跳过"
    else:
        tone, state_text = "ok", "完成"
    if not result and not event.get("done"):
        result = "等待处理"
    head: List[Dict[str, Any]] = []
    if event.get("own_move"):
        # 镜像把对象移进回收站的回声：CD2 报的是 rename，但这里不该显示「改名」
        head.append(_chip("移入回收站", "warn"))
    else:
        head.append(_change_chip(str(event.get("change_type") or "")))
    outcome = str(event.get("outcome") or "")
    if outcome and outcome != "已受理":
        head.append(_chip(outcome, {"已忽略": "grey"}.get(outcome, "info")))
    head.append(
        {
            "component": "span",
            "props": {"class": "nm", "title": path},
            "text": name or path or "（无路径）",
        }
    )
    meta: List[Dict[str, Any]] = [
        {"component": "span", "props": {"class": f"cd2strm-st {tone}".strip()}, "text": state_text},
        {
            "component": "span",
            "props": {"class": "cd2strm-res", "title": result},
            "text": result or "—",
        },
    ]
    if event.get("internal"):
        meta.append(_chip("自身生成", "grey"))
    if event.get("source"):
        meta.append(_chip(str(event["source"]), "grey"))
    return {
        "component": "div",
        "props": {"class": f"cd2strm-fi {tone}".strip()},
        "content": [
            {"component": "span", "props": {"class": "tm"}, "text": str(event.get("time") or "")},
            {
                "component": "span",
                "props": {"class": "rail"},
                "content": [{"component": "span", "props": {"class": "dot"}}],
            },
            {
                "component": "div",
                "props": {"class": "bd"},
                "content": [
                    {"component": "div", "props": {"class": "top"}, "content": head},
                    {"component": "div", "props": {"class": "dr", "title": path}, "text": directory or "/"},
                    {"component": "div", "props": {"class": "mt"}, "content": meta},
                ],
            },
        ],
    }


def _time_seconds(text: str) -> Optional[int]:
    """把 MM-DD HH:MM:SS 里的时分秒换算成秒数（同一天内可比较）。"""
    try:
        _, clock = str(text).split(" ")
        hour, minute, second = (int(item) for item in clock.split(":"))
    except (ValueError, AttributeError):
        return None
    return (hour * 60 + minute) * 60 + second


def _merge_kind(event: Dict[str, Any]) -> str:
    """合并分类：自身「移入回收站」单独一类，其余按变更类型。"""
    if event.get("own_move"):
        return "move"
    return str(event.get("change_type") or "")


def _merge_events(
    events: List[Dict[str, Any]], seconds: int
) -> List[List[Dict[str, Any]]]:
    """把相邻的「同目录 + 同类型」通知合并成组（events 为最新在前）。

    合并条件：相邻两条间隔 ≤ seconds 且整组跨度 ≤ MERGE_SPAN_LIMIT；seconds ≤ 0 表示不合并。
    """
    if seconds <= 0:
        return [[event] for event in events]
    groups: List[Dict[str, Any]] = []
    for event in events:
        stamp = _time_seconds(str(event.get("time") or ""))
        key = (_merge_kind(event), _split_path(str(event.get("path") or ""))[0])
        if groups:
            current = groups[-1]
            if (
                current["key"] == key
                and stamp is not None
                and current["last"] is not None
                and abs(current["last"] - stamp) <= seconds
                and abs(current["first"] - stamp) <= MERGE_SPAN_LIMIT
            ):
                current["events"].append(event)
                current["last"] = stamp
                continue
        groups.append({"key": key, "events": [event], "first": stamp, "last": stamp})
    return [item["events"] for item in groups]


def _feed_group(
    rows: List[Dict[str, Any]], paired_acts: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """把同目录同类型的多条通知渲染成一条可展开的聚合行（方案 A）。

    摘要行给出：时间范围、变更徽章、目录尾两段、文件数、完成/等待/失败计数、历时、自身生成标记；
    含失败或等待处理的组默认展开，纯完成组默认折叠（点标题展开逐条明细）。
    若这一组与某组操作记录对应上，摘要里再补一段「→ 记录：新增 N · 失败 N」。
    """
    first = rows[0]
    path = str(first.get("path") or "")
    directory, _ = _split_path(path)
    done = sum(1 for item in rows if item.get("done"))
    waiting = len(rows) - done
    failed = sum(1 for item in rows if "失败" in str(item.get("result") or ""))
    skipped = sum(1 for item in rows if "跳过" in str(item.get("result") or ""))
    if failed or waiting:
        tone = "warn"
    elif skipped and skipped == len(rows):
        tone = "skip"
    else:
        tone = "ok"
    head: List[Dict[str, Any]] = []
    if first.get("own_move"):
        head.append(_chip("移入回收站", "warn"))
    else:
        head.append(_change_chip(str(first.get("change_type") or "")))
    tail = "/".join([item for item in directory.split("/") if item][-2:]) or directory
    head.append(
        {
            "component": "span",
            "props": {"class": "nm", "title": directory},
            "text": tail or "（无目录）",
        }
    )
    head.append(
        {"component": "span", "props": {"class": "cnt"}, "text": f"{len(rows)} 个文件"}
    )
    counts: List[Dict[str, Any]] = [
        {
            "component": "span",
            "props": {"class": f"cd2strm-st {tone}".strip()},
            "text": f"完成 {done}",
        }
    ]
    if waiting:
        counts.append(
            {"component": "span", "props": {"class": "cd2strm-st skip"}, "text": f"待回填 {waiting}"}
        )
    if skipped:
        counts.append(
            {"component": "span", "props": {"class": "cd2strm-st skip"}, "text": f"跳过 {skipped}"}
        )
    if failed:
        counts.append(
            {"component": "span", "props": {"class": "cd2strm-st bad"}, "text": f"失败 {failed}"}
        )
    span = abs((_time_seconds(str(rows[0].get("time") or "")) or 0)
               - (_time_seconds(str(rows[-1].get("time") or "")) or 0))
    if len(rows) > 1:
        counts.append(
            {
                "component": "span",
                "props": {"class": "cd2strm-res"},
                "text": f"历时 {span}s",
            }
        )
    if first.get("internal"):
        counts.append(_chip("自身生成", "grey"))
    if first.get("source"):
        counts.append(_chip(str(first["source"]), "grey"))
    if paired_acts:
        counts.append(
            {
                "component": "span",
                "props": {"class": "cd2strm-link"},
                "text": f"→ 对应记录：{_counters_text(paired_acts)}",
            }
        )
    counts.append(
        {
            "component": "span",
            "props": {"class": "chev"},
            "content": [
                {"component": "span", "props": {"class": "cd2strm-gclosed"}, "text": f"展开 {len(rows)} 条 ▾"},
                {"component": "span", "props": {"class": "cd2strm-gopen"}, "text": f"收起 {len(rows)} 条 ▴"},
            ],
        }
    )
    times = [str(item.get("time") or "") for item in rows]
    range_text = times[0] if len(times) == 1 else f'{times[-1].split(" ")[-1]}–{times[0].split(" ")[-1]}'
    summary: Dict[str, Any] = {
        "component": "summary",
        "content": [
            {"component": "span", "props": {"class": "tm"}, "text": range_text},
            {
                "component": "span",
                "props": {"class": "rail"},
                "content": [{"component": "span", "props": {"class": "dot"}}],
            },
            {
                "component": "div",
                "content": [
                    {"component": "div", "props": {"class": "cd2strm-gsum"}, "content": head},
                    {"component": "div", "props": {"class": "dr", "title": directory}, "text": directory},
                    {"component": "div", "props": {"class": "mt"}, "content": counts},
                ],
            },
        ],
    }
    # 合并行一律默认折叠（用户要求「默认折叠所有 CD2 通知」）；失败数在分区标题上有红徽章
    props: Dict[str, Any] = {"class": "cd2strm-gwrap"}
    return {
        "component": "details",
        "props": props,
        "content": [
            summary,
            {
                "component": "div",
                "props": {"class": "cd2strm-gdet"},
                "content": [_feed_line(item) for item in rows],
            },
        ],
    }


def _merge_actions(
    actions: List[Dict[str, Any]], seconds: int
) -> List[List[Dict[str, Any]]]:
    """把相邻的「同目录 + 同触发方式」操作记录合并成组（actions 为最新在前）。"""
    if seconds <= 0:
        return [[action] for action in actions]
    groups: List[Dict[str, Any]] = []
    for action in actions:
        stamp = _time_seconds(str(action.get("time") or ""))
        key = (str(action.get("trigger") or ""), _action_dir(action))
        if groups:
            current = groups[-1]
            if (
                current["key"] == key
                and stamp is not None
                and current["last"] is not None
                and abs(current["last"] - stamp) <= seconds
                and abs(current["first"] - stamp) <= MERGE_SPAN_LIMIT
            ):
                current["rows"].append(action)
                current["last"] = stamp
                continue
        groups.append({"key": key, "rows": [action], "first": stamp, "last": stamp})
    return [item["rows"] for item in groups]


def _action_dir(action: Dict[str, Any]) -> str:
    """操作记录的来源目录（记录里存的是源文件路径）。"""
    return _split_path(str(action.get("path") or ""))[0]


def _note_dir(event: Dict[str, Any]) -> str:
    """通知对应的目录：改名事件用目标路径，其余用自身路径。

    改名事件（例如从 CD2 暂存目录进媒体库）的 path 是暂存位置、new_path 才是落点，
    操作记录里的路径是落点，所以配对要用 new_path 那一侧。
    """
    return _split_path(str(event.get("new_path") or event.get("path") or ""))[0]


def _group_span(rows: List[Dict[str, Any]]) -> tuple:
    """一组记录/通知的时间范围（秒，最早 / 最晚）。"""
    stamps = [
        stamp
        for stamp in (_time_seconds(str(item.get("time") or "")) for item in rows)
        if stamp is not None
    ]
    if not stamps:
        return (None, None)
    return (min(stamps), max(stamps))


def _pair_groups(
    note_groups: List[List[Dict[str, Any]]],
    act_groups: List[List[Dict[str, Any]]],
) -> Dict[int, List[int]]:
    """把通知组与操作记录组按「同目录 + 时间相邻」配对。

    返回 {通知组下标: [记录组下标, ...]}：同一批通知可能被拆成多段记录（中间隔着一条其它目录的
    通知就会切开），所以一个通知组允许对应多段记录，展示时把它们的统计合计。
    目录相同是硬条件（通知用 new_path 的目录，记录用源文件路径的目录），时间上要求两段区间
    相差不超过 PAIR_SLACK 秒：批处理的记录往往与通知交错发生，完全不重叠也算同一批。
    """
    pairs: Dict[int, List[int]] = {}
    for note_index, notes in enumerate(note_groups):
        directory = _note_dir(notes[0])
        note_first, note_last = _group_span(notes)
        if not directory or None in (note_first, note_last):
            continue
        for act_index, acts in enumerate(act_groups):
            if _action_dir(acts[0]) != directory:
                continue
            act_first, act_last = _group_span(acts)
            if None in (act_first, act_last):
                continue
            if note_first - PAIR_SLACK <= act_last and act_first - PAIR_SLACK <= note_last:
                pairs.setdefault(note_index, []).append(act_index)
    return pairs


def _counters_text(actions: List[Dict[str, Any]]) -> str:
    """把一组记录的计数器加起来，生成「新增 55 · 跳过 0 · 失败 0」这样的短文案。"""
    total: Dict[str, int] = {}
    for action in actions:
        for key, value in (action.get("counters") or {}).items():
            total[key] = total.get(key, 0) + int(value or 0)
    parts = [f"新增 {total.get('links_created', 0)}"]
    if total.get("links_updated"):
        parts.append(f"更新 {total['links_updated']}")
    parts.append(f"跳过 {total.get('links_skipped', 0)}")
    parts.append(f"失败 {total.get('links_failed', 0) + total.get('metadata_failed', 0)}")
    if total.get("metadata_copied"):
        parts.append(f"元数据 {total['metadata_copied']}")
    cleaned = (
        total.get("removed_links", 0)
        + total.get("removed_metadata", 0)
        + total.get("removed_dirs", 0)
    )
    if cleaned:
        parts.append(f"清理 {cleaned}")
    return " · ".join(parts)


def _record_group(
    rows: List[Dict[str, Any]], note_count: int = 0
) -> Dict[str, Any]:
    """把同目录同触发方式的多条操作记录渲染成一条可展开的聚合行。"""
    first = rows[0]
    directory = _action_dir(first)
    total = len(rows)
    failed = sum(1 for item in rows if item.get("error"))
    failed += sum(
        1
        for item in rows
        for key in ("links_failed", "metadata_failed")
        if int((item.get("counters") or {}).get(key) or 0)
    )
    tone = "bad" if failed else "ok"
    tail = "/".join([part for part in directory.split("/") if part][-2:]) or directory
    head: List[Dict[str, Any]] = [
        _chip("事件" if str(first.get("trigger")) == "event" else "手动", "grey"),
        {"component": "span", "props": {"class": "nm", "title": directory}, "text": tail or "（无目录）"},
        {"component": "span", "props": {"class": "cnt"}, "text": f"{total} 次"},
    ]
    meta: List[Dict[str, Any]] = [
        {
            "component": "span",
            "props": {"class": f"cd2strm-st {tone}".strip()},
            "text": _counters_text(rows),
        }
    ]
    first_sec, last_sec = _group_span(rows)
    if total > 1 and first_sec is not None and last_sec is not None:
        meta.append(
            {
                "component": "span",
                "props": {"class": "cd2strm-res"},
                "text": f"历时 {abs(first_sec - last_sec)}s",
            }
        )
    if note_count:
        meta.append(
            {
                "component": "span",
                "props": {"class": "cd2strm-link"},
                "text": f"← 对应通知 {note_count} 条",
            }
        )
    meta.append(
        {
            "component": "span",
            "props": {"class": "chev"},
            "content": [
                {"component": "span", "props": {"class": "cd2strm-gclosed"}, "text": f"展开 {total} 条 ▾"},
                {"component": "span", "props": {"class": "cd2strm-gopen"}, "text": f"收起 {total} 条 ▴"},
            ],
        }
    )
    times = [str(item.get("time") or "") for item in rows]
    range_text = times[0] if len(times) == 1 else f'{times[-1].split(" ")[-1]}–{times[0].split(" ")[-1]}'
    props: Dict[str, Any] = {"class": "cd2strm-gwrap"}
    if failed:
        props["open"] = True
    return {
        "component": "details",
        "props": props,
        "content": [
            {
                "component": "summary",
                "content": [
                    {"component": "span", "props": {"class": "tm"}, "text": range_text},
                    {
                        "component": "span",
                        "props": {"class": "rail"},
                        "content": [{"component": "span", "props": {"class": "dot"}}],
                    },
                    {
                        "component": "div",
                        "content": [
                            {"component": "div", "props": {"class": "cd2strm-gsum"}, "content": head},
                            {"component": "div", "props": {"class": "dr", "title": directory}, "text": directory},
                            {"component": "div", "props": {"class": "mt"}, "content": meta},
                        ],
                    },
                ],
            },
            {
                "component": "div",
                "props": {"class": "cd2strm-gdet"},
                "content": [_record_line(item) for item in rows],
            },
        ],
    }


def _sync_feed(
    page: int,
    page_size: int,
    groups: List[List[Dict[str, Any]]],
    pairs: Optional[Dict[int, List[int]]] = None,
    act_groups: Optional[List[List[Dict[str, Any]]]] = None,
    empty_hint: str = "",
) -> Dict[str, Any]:
    """本组的 CD2 通知流：按合并窗口折叠同目录同类型的相邻通知，分页按合并后的条目算。"""
    pairs = pairs or {}
    total = sum(len(group) for group in groups)
    page = _clamp_page(page, page_size, len(groups))
    start = max(0, (page - 1) * page_size)
    window = list(enumerate(groups))[start : start + page_size]
    items: List[Dict[str, Any]] = []
    for index, group in window:
        if len(group) == 1:
            items.append(_feed_line(group[0]))
            continue
        paired: List[Dict[str, Any]] = []
        for act_index in pairs.get(index, []):
            if act_groups and 0 <= act_index < len(act_groups):
                paired.extend(act_groups[act_index])
        items.append(_feed_group(group, paired or None))
    if not items:
        items = [
            {
                "component": "div",
                "props": {"class": "cd2strm-hint"},
                "text": empty_hint or "暂无通知：CloudDrive2 只在变更经由它自身发生时推送。",
            }
        ]
    shown = sum(len(group) for _, group in window)
    failed = sum(
        1 for _, group in window for event in group if "失败" in str(event.get("result") or "")
    )
    head_content: List[Dict[str, Any]] = [
        {"component": "span", "props": {"class": "cd2strm-fh"}, "text": "CD2 通知"},
        _chip(f"共 {total} 条", "grey"),
    ]
    if len(groups) < total:
        head_content.append(_chip(f"合并为 {len(groups)} 组", "primary"))
    if failed:
        # 折叠起来也要能看出有没有失败
        head_content.append(_chip(f"失败 {failed}", "error"))
    head_content.append(
        {
            "component": "span",
            "props": {"class": "cd2strm-count"},
            "text": f"已显示最新 {shown} 条",
        }
    )
    # 默认折叠：标题行本身就是 summary，点开才看明细（三个视图一致）
    return {
        "component": "details",
        "props": {"class": "cd2strm-fold cd2strm-fsec"},
        "content": [
            {"component": "summary", "props": {"class": "cd2strm-fhead"}, "content": head_content},
            {
                "component": "div",
                "props": {"class": "cd2strm-feed", "style": dict(FEED_BOX_STYLE)},
                "content": items,
            },
        ],
    }


def _record_line(action: Dict[str, Any]) -> Dict[str, Any]:
    """把一条操作记录渲染成活动流行：时间 / 轴点 / 触发+统计 / 生成文件。"""
    text = str(action.get("summary") or "")
    error = str(action.get("error") or "")
    files = list(action.get("files") or [])
    file_nodes: List[Dict[str, Any]] = [
        {"component": "div", "props": {"class": "cd2strm-pth", "title": item}, "text": item}
        for item in files[:5]
    ]
    if len(files) > 5:
        file_nodes.append(
            {
                "component": "div",
                "props": {"class": "cd2strm-count"},
                "text": f"其余 {len(files) - 5} 个已省略",
            }
        )
    if not file_nodes:
        file_nodes.append({"component": "div", "props": {"class": "cd2strm-count"}, "text": "—"})
    tone = "bad" if error else "ok"
    meta: List[Dict[str, Any]] = [
        {
            "component": "span",
            "props": {"class": f"cd2strm-st {tone}".strip()},
            "text": "出错" if error else "完成",
        },
        {
            "component": "span",
            "props": {"class": "cd2strm-res", "title": text},
            "text": text or "无变化",
        },
    ]
    if error:
        meta.append(
            {
                "component": "span",
                "props": {"class": "cd2strm-res cd2strm-bad", "title": error},
                "text": f"错误：{error}",
            }
        )
    return {
        "component": "div",
        "props": {"class": f"cd2strm-fi {tone}".strip()},
        "content": [
            {"component": "span", "props": {"class": "tm"}, "text": str(action.get("time") or "")},
            {
                "component": "span",
                "props": {"class": "rail"},
                "content": [{"component": "span", "props": {"class": "dot"}}],
            },
            {
                "component": "div",
                "props": {"class": "bd"},
                "content": [
                    {
                        "component": "div",
                        "props": {"class": "top"},
                        "content": [
                            _chip(str(action.get("trigger") or "事件"), "grey"),
                            {
                                "component": "span",
                                "props": {"class": "nm"},
                                "text": str(action.get("rule") or "本组"),
                            },
                        ],
                    },
                    {"component": "div", "props": {"class": "mt"}, "content": meta},
                    {"component": "div", "props": {"class": "files"}, "content": file_nodes},
                ],
            },
        ],
    }


def _record_feed(
    page: int,
    page_size: int,
    groups: List[List[Dict[str, Any]]],
    reverse_pairs: Optional[Dict[int, int]] = None,
    note_groups: Optional[List[List[Dict[str, Any]]]] = None,
) -> Dict[str, Any]:
    """本组的操作记录流：同目录同触发方式的相邻记录折叠成一条聚合并行，分页按组算。"""
    reverse_pairs = reverse_pairs or {}
    total = sum(len(group) for group in groups)
    page = _clamp_page(page, page_size, len(groups))
    start = max(0, (page - 1) * page_size)
    window = list(enumerate(groups))[start : start + page_size]
    items: List[Dict[str, Any]] = []
    for index, group in window:
        if len(group) == 1:
            items.append(_record_line(group[0]))
            continue
        note_count = 0
        if index in reverse_pairs and note_groups:
            note_count = len(note_groups[reverse_pairs[index]])
        items.append(_record_group(group, note_count))
    if not items:
        items = [{"component": "div", "props": {"class": "cd2strm-hint"}, "text": "暂无操作记录"}]
    shown = sum(len(group) for _, group in window)
    head_content: List[Dict[str, Any]] = [
        {"component": "span", "props": {"class": "cd2strm-fh"}, "text": "操作记录"},
        _chip(f"共 {total} 条", "grey"),
    ]
    if len(groups) < total:
        head_content.append(_chip(f"合并为 {len(groups)} 组", "primary"))
    head_content.append(
        {
            "component": "span",
            "props": {"class": "cd2strm-count"},
            "text": f"已显示最新 {shown} 条",
        }
    )
    return {
        "component": "div",
        "props": {"class": "cd2strm-fsec"},
        "content": [
            {"component": "div", "props": {"class": "cd2strm-fhead"}, "content": head_content},
            {
                "component": "div",
                "props": {"class": "cd2strm-feed", "style": dict(FEED_BOX_STYLE)},
                "content": items,
            },
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
    """构造消息显示范围控制条：每页组数 + 上一页 / 下一页。

    合并显示之后，翻页单位是「合并后的条目（组）」而不是原始条数；
    各分区标题里已经写明「共 N 条 · 合并为 M 组 · 已显示最新 X 条」，这里只报页码与每页组数。
    """
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
                # 合并之后翻页按「组」算：这里写清每页多少组，别再拿组数冒充条数
                "text": f"第 {page} / {max_page} 页（每页 {page_size} 组 · 共 {total} 组）",
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
                body=[_feed_line(event) for event in items],
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
