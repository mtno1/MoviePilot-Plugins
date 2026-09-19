"""CD2 Strm 同步：接收 CloudDrive2 变更通知，生成 strm / 软链接并同步元数据。"""

from __future__ import annotations

import logging
import os
import queue
import re
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytz
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import Body

from app.plugins import _PluginBase
from app.schemas.types import EventType
from app.sdk.config import settings
from app.sdk.events import Event, eventmanager
from app.sdk.logging import logger

from .cd2web import CloudDriveError, CloudDriveWebClient, PushSubscriber
from .engine import (
    EventDispatcher,
    _scope_for,
    apply_event,
    in_mirror_recycle,
    is_organize_candidate,
    match_mirror_rule,
    match_organize_rule,
    metadata_target_path,
    move_mirror_targets,
    organize_file,
    organize_container_path,
    organize_path,
    scan_rule,
    target_path,
)
from .rules import (
    MirrorRule,
    OrganizeRule,
    SyncRule,
    build_all_mirror_config,
    build_all_organize_config,
    build_all_rule_config,
    build_connections,
    build_rule_config,
    classify_event,
    default_config,
    is_excluded,
    match_rule,
    normalize_path,
    parse_globals,
    parse_mirror_globals,
    parse_mirror_rules,
    parse_organize_globals,
    parse_organize_rules,
    parse_rules,
    to_organize_internal,
)
from .ui import build_form, build_page

# 规则键：r<下标>_<字段名>
RULE_KEY_PATTERN = re.compile(r"^r\d+_")
# 整理组的配置键前缀
ORGANIZE_KEY_PATTERN = re.compile(r"^o\d+_")

# 镜像组键：d<下标>_<字段名>
MIRROR_KEY_PATTERN = re.compile(r"^d\d+_")
# 事件与统计的保留条数
MAX_EVENTS = 100
# /clear-notify 的 target 取值与展示名（hit 只清命中列表，unaccepted 只清未匹配缓冲）
CLEAR_TARGET_LABELS = {"hit": "命中", "unaccepted": "未匹配"}
CLEAR_TARGETS = ("hit", "unaccepted", "all")
# 各功能的（命中通知列表, 未匹配缓冲）字段名
NOTIFY_FIELDS = {
    "sync": ("_events", "_ignored_events"),
    "organize": ("_organize_events", "_organize_ignored"),
    "mirror": ("_mirror_events", "_mirror_ignored"),
}
# 整理侧「未受理通知」的保留条数
ORGANIZE_IGNORE_LIMIT = 50
# 宿主整理链的良性拒绝（重复通知 / 挂载尚未可见 / 体积过滤）——按「跳过」处理，不算失败
BENIGN_ORGANIZE_HINTS = (
    "小于最小体积",
    "路径不存在",
    "已在整理队列中",
    "请等待当前任务结束后重新整理",
    "没有找到可整理的媒体文件",
)


def _is_benign_organize_rejection(message: str, reason: str = "") -> bool:
    """判断整理链的拒绝是否属于良性，用于把「跳过」与「失败」分开。"""
    text = f"{message or ''} {reason or ''}"
    return any(hint in text for hint in BENIGN_ORGANIZE_HINTS)


def _benign_skip_reason(message: str, reason: str = "") -> str:
    """给良性拒绝一个简短可读的原因（供命中通知的「结果」列展示）。"""
    text = f"{message or ''} {reason or ''}"
    if "已在整理队列中" in text or "请等待当前任务结束后重新整理" in text:
        return "重复通知（文件已在整理队列中）"
    if "没有找到可整理的媒体文件" in text:
        return "目录内暂未看到可整理文件"
    return reason or message

# 镜像移动：未受理缓冲上限与单条记录里展示的对象上限
MIRROR_IGNORE_LIMIT = 50
MIRROR_REPORT_PATHS = 20
# 目录级事件在合并窗口之后额外等待的秒数（让文件级事件先处理，减少重复劳动）
DIR_SCAN_EXTRA_SECONDS = 3
# 同一源对象拆出的多个自动任务在该窗口内合并为一条操作记录
ACTION_MERGE_SECONDS = 10
# 参与汇总/合并的计数字段
COUNTER_KEYS = (
    "scanned_files",
    "links_created",
    "links_updated",
    "links_skipped",
    "links_failed",
    "metadata_copied",
    "metadata_skipped",
    "metadata_failed",
    "removed_links",
    "removed_metadata",
    "removed_dirs",
    "cleaned_failed",
)
# 判定「有实质动作」的字段（跳过类不计，避免自动任务刷出全 0 记录）
ACTIVITY_KEYS = (
    "links_created",
    "links_updated",
    "links_failed",
    "metadata_copied",
    "metadata_failed",
    "removed_links",
    "removed_metadata",
    "removed_dirs",
    "cleaned_failed",
)
# 插件自身的日志文件（「清空全部日志」会就地清空它，不影响 MoviePilot 主日志）
PLUGIN_LOG_PATH = Path("/config/logs/plugins/cd2strmsync.log")


def _safe_int(value: Any, default: int = 0) -> int:
    """把任意值安全转换为整数。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _strip_scheme(value: str) -> str:
    """去掉地址中的协议前缀，得到 host:port 形式。"""
    text = (value or "").strip()
    if "://" in text:
        text = text.split("://", 1)[1]
    return text.rstrip("/")


def _format_time(timestamp: float) -> str:
    """把时间戳格式化成可读文本。"""
    if not timestamp:
        return "无"
    try:
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
    except (OSError, OverflowError, ValueError):
        return "无"


def _format_stats(stats: Dict[str, Any]) -> str:
    """把扫描统计整理成一行可读文本（兼容 counters 嵌套写法）。"""
    counters = stats.get("counters") if isinstance(stats.get("counters"), dict) else stats
    if stats.get("error"):
        return f"失败：{stats['error']}"
    seconds = stats.get("seconds", counters.get("seconds", 0))
    return (
        f"新增 {counters.get('links_created', 0)} / 更新 {counters.get('links_updated', 0)}"
        f" / 跳过 {counters.get('links_skipped', 0)} / 失败 {counters.get('links_failed', 0)}"
        f"｜扫描媒体 {counters.get('scanned_files', 0)}"
        f"｜元数据 {counters.get('metadata_copied', 0)}"
        f"｜清理 链接 {counters.get('removed_links', 0)} / 元数据 {counters.get('removed_metadata', 0)}"
        f" / 空目录 {counters.get('removed_dirs', 0)}"
        f"｜耗时 {seconds}s"
    )


def _files_of(stats: Dict[str, Any]) -> List[str]:
    """取出本次生成/更新的文件清单。"""
    return [
        *[f"生成 {item}" for item in (stats.get("created_paths") or [])],
        *[f"更新 {item}" for item in (stats.get("updated_paths") or [])],
    ]


def _merge_files(old: List[str], new: List[str]) -> List[str]:
    """合并文件清单并去重。"""
    result = list(old)
    for item in new:
        if item not in result:
            result.append(item)
    return result


def _short_path(path: str, keep: int = 2, limit: int = 62) -> str:
    """把长路径折叠成「…/末两级」，便于在通知里阅读（完整路径见插件页面）。"""
    text = normalize_path(str(path or "")).rstrip("/")
    if not text:
        return ""
    if len(text) <= limit:
        return text
    parts = [item for item in text.split("/") if item]
    if len(parts) <= keep:
        return text
    return "…/" + "/".join(parts[-keep:])


def _short_text(text: str, limit: int = 90) -> str:
    """截断过长的说明文字（通知里只保留开头，完整内容见插件页面）。"""
    value = str(text or "").strip().replace("\n", " ")
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _file_name(path: str) -> str:
    """取路径中的文件名（通知里文件名单独一行，不与目录混在一起）。"""
    text = normalize_path(str(path or "")).rstrip("/")
    return text.rsplit("/", 1)[-1] if text else ""


def _strip_file_prefix(item: str) -> str:
    """去掉操作记录文件清单里的「生成 / 更新」前缀。"""
    text = str(item or "")
    for prefix in ("生成 ", "更新 "):
        if text.startswith(prefix):
            return text[len(prefix) :]
    return text


def _truncate_plugin_log(path: Optional[Path] = None) -> bool:
    """就地清空插件日志文件，优先复用已打开的日志句柄以免产生空洞。"""
    target_path = path or PLUGIN_LOG_PATH
    if not target_path.exists():
        return False
    target = str(target_path)
    for logger_ref in list(logging.Logger.manager.loggerDict.values()):
        for handler in getattr(logger_ref, "handlers", None) or []:
            if not isinstance(handler, logging.FileHandler):
                continue
            if str(getattr(handler, "baseFilename", "")) != target:
                continue
            try:
                handler.stream.seek(0)
                handler.stream.truncate(0)
                return True
            except Exception:  # pylint: disable=broad-except
                break
    try:
        with open(target_path, "w", encoding="utf-8"):
            pass
        return True
    except OSError as err:
        logger.warning(f"清空插件日志失败：{err}")
        return False


class Cd2StrmSync(_PluginBase):
    """CloudDrive2 变更通知驱动的 strm 同步插件。"""

    plugin_name = "CD2 API Strm 同步、媒体整理与镜像移动"
    plugin_desc = (
        "接收 CloudDrive2 变更通知：按多组「源目录→目的目录」规则生成 strm / 软链接并同步元数据；"
        "可另按独立的整理规则把文件交给 MoviePilot 整理链入库；还可按镜像规则把镜像目录中对应的"
        "对象移到回收站（保护白名单命中的对象不移动）。三者互不影响，共用通知。"
    )
    plugin_icon = "https://raw.githubusercontent.com/mtno1/MoviePilot-Plugins/main/icons/cd2strmsync.png"
    plugin_version = "1.34.1"
    plugin_author = "mtno1"
    plugin_label = "云盘"
    plugin_config_prefix = "cd2strmsync_"
    plugin_order = 30
    auth_level = 1

    def __init__(self) -> None:
        """初始化运行时容器。"""
        super().__init__()
        self._enabled = False
        self._notify = True
        self._rules: List[SyncRule] = []
        self._globals: Dict[str, Any] = {}
        self._clients: List[CloudDriveWebClient] = []
        self._subscribers: List[PushSubscriber] = []
        self._connections: List[Dict[str, str]] = []
        self._dispatcher: Optional[EventDispatcher] = None
        self._scan_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._rule_stats: Dict[str, Dict[str, Any]] = {}
        self._events: List[Dict[str, Any]] = []
        self._ignored_events: List[Dict[str, Any]] = []
        self._ignored_count = 0
        self._excluded_count = 0
        self._actions: List[Dict[str, Any]] = []
        self._display: Dict[str, Any] = {"page_size": 5, "pages": {}}
        self._scanning: Dict[str, bool] = {}
        self._progress: Dict[str, Dict[str, Any]] = {}
        self._organize_rules: List[OrganizeRule] = []
        self._organize_globals: Dict[str, Any] = {}
        self._organize_stats: Dict[str, Dict[str, Any]] = {}
        self._organize_records: List[Dict[str, Any]] = []
        self._organize_ignored: List[Dict[str, Any]] = []
        self._organize_events: List[Dict[str, Any]] = []
        self._mirror_rules: List[MirrorRule] = []
        self._mirror_globals: Dict[str, Any] = {}
        self._mirror_stats: Dict[str, Dict[str, Any]] = {}
        self._mirror_records: List[Dict[str, Any]] = []
        self._mirror_ignored: List[Dict[str, Any]] = []
        self._mirror_events: List[Dict[str, Any]] = []
        self._mirror_queue: "queue.Queue[Tuple[int, str, bool, str]]" = queue.Queue()
        self._mirror_worker: Optional[threading.Thread] = None
        self._mirror_stop = threading.Event()
        self._mirror_seen: set[str] = set()
        self._mirror_busy = False
        self._mirror_timers: List[threading.Timer] = []
        self._active_view = "sync"
        self._organize_queue: "queue.Queue[Tuple[int, str, str]]" = queue.Queue()
        self._organize_worker: Optional[threading.Thread] = None
        self._organize_stop = threading.Event()
        self._organize_seen: set[str] = set()
        self._organize_busy = False
        self._last_error = ""
        self._dirty = False

    def init_plugin(self, config: dict = None) -> None:
        """按配置重建目录规则、推送订阅与事件调度。"""
        self.stop_service()
        self._release_runtime()
        payload = dict(config or {})
        self._globals = parse_globals(payload)
        fallback_host = _strip_scheme(str(self._globals.get("cd2_host") or ""))
        rules = parse_rules(payload)
        for rule in rules:
            if not rule.cloud_host:
                rule.cloud_host = fallback_host
        self._rules = rules
        self._enabled = bool(self._globals.get("enabled"))
        self._notify = bool(self._globals.get("notify"))
        self._organize_rules = parse_organize_rules(payload)
        self._organize_globals = parse_organize_globals(payload)
        self._mirror_rules = parse_mirror_rules(payload)
        self._mirror_globals = parse_mirror_globals(payload)
        self._last_error = ""
        if self._globals.get("onlyonce") and not self._enabled:
            # 插件未启用时不会注册一次性扫描服务，直接把开关复位，避免长期挂在开启状态
            self._consume_onlyonce()
        self._restore_state()
        if not self._enabled:
            logger.info("CD2 Strm 同步插件未启用")
            return
        self._connections = build_connections(self._globals)
        if not self._connections:
            self._last_error = "缺少 CloudDrive2 地址或 API 令牌"
            logger.warning(f"CD2 Strm 同步插件配置不完整：{self._last_error}")
            return
        for profile in self._connections:
            client = CloudDriveWebClient(profile["host"], profile["token"])
            subscriber = PushSubscriber(client, self._make_handler(profile["label"]))
            self._clients.append(client)
            self._subscribers.append(subscriber)
            subscriber.start()
        self._dispatcher = EventDispatcher(
            self._rules_snapshot,
            self._resolve_event,
            self._apply_event,
        )
        self._dispatcher.start()
        self._start_organize_worker()
        self._start_mirror_worker()
        # 启动时补一次回填：让上次遗留的「处理中」通知（例如路径对不上而没回填的改名事件）
        # 在插件重载/重启后就能显示真实结果，不用等下一次扫描
        for index in range(len(self._rules)):
            self._reconcile_events(index)
        labels = "、".join(profile["label"] for profile in self._connections)
        logger.info(
            f"CD2 Strm 同步插件已启动，共 {len(self._rules)} 组目录规则，"
            f"{len(self._connections)} 路订阅（{labels}）"
        )

    def get_state(self) -> bool:
        """返回插件启用状态。"""
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """注册远程命令：手动触发一次全量扫描。"""
        return [
            {
                "cmd": "/cd2strm_scan",
                "event": EventType.PluginAction,
                "desc": "CD2 Strm 全量扫描",
                "category": "云盘",
                "data": {"action": "cd2strm_scan"},
            }
        ]

    def get_api(self) -> List[Dict[str, Any]]:
        """注册插件接口，供详情页按钮调用。"""
        return [
            {
                "path": "/status",
                "endpoint": self.api_status,
                "methods": ["GET"],
                "summary": "插件运行状态",
            },
            {
                "path": "/scan",
                "endpoint": self.api_scan,
                "methods": ["POST"],
                "summary": "立即扫描指定目录组",
                "description": "参数 index 为目录组下标",
            },
            {
                "path": "/rule",
                "endpoint": self.api_rule,
                "methods": ["POST"],
                "summary": "复制或删除目录组",
                "description": "参数 index 为目录组下标，operation 为 copy 或 delete",
            },
            {
                "path": "/display",
                "endpoint": self.api_display,
                "methods": ["POST"],
                "summary": "调整消息显示范围",
                "description": "参数 index 为目录组下标（其它通知用 other）、page 为页码、page_size 为每页条数",
            },
            {
                "path": "/clear",
                "endpoint": self.api_clear,
                "methods": ["POST"],
                "summary": "清空某个目录组的显示数值",
                "description": "参数 index 为目录组下标；只清空统计数值，不影响操作记录与文件",
            },
            {
                "path": "/purge",
                "endpoint": self.api_purge,
                "methods": ["POST"],
                "summary": "一键清除日志、通知与操作记录",
                "description": "清空 CD2 通知、操作记录、页面统计、插件日志文件与订阅计数",
            },
            {
                "path": "/clear-notify",
                "endpoint": self.api_clear_notify,
                "methods": ["POST"],
                "summary": "只清除 CD2 通知列表（可按功能或全部）",
                "description": "参数 scope 为 sync / organize / mirror，或 all（三个功能一起清）；"
                "target 取 hit（只清命中列表）/ unaccepted（只清未匹配缓冲）/ all（两者都清，缺省）；"
                "只清通知，不动统计数值、操作记录与插件日志",
            },
            {
                "path": "/clear-count",
                "endpoint": self.api_clear_count,
                "methods": ["POST"],
                "summary": "只清空某个功能视图的统计数值",
                "description": "参数 scope 为 sync / organize / mirror；只清数值（sync 另含未匹配与排除目录计数），"
                "不动通知列表、操作记录与插件日志",
            },
            {
                "path": "/clear-log",
                "endpoint": self.api_clear_log,
                "methods": ["POST"],
                "summary": "只清空插件日志文件",
                "description": "不动 CD2 通知、操作记录与统计",
            },
            {
                "path": "/refresh",
                "endpoint": self.api_refresh,
                "methods": ["POST"],
                "summary": "刷新详情页数据（含扫描进度）",
                "description": "只返回当前状态，不修改任何数据；前端点击后会重载页面",
            },
            {
                "path": "/test",
                "endpoint": self.api_test,
                "methods": ["POST"],
                "summary": "测试 CloudDrive2 连接与令牌权限",
            },
            {
                "path": "/view",
                "endpoint": self.api_view,
                "methods": ["POST"],
                "summary": "切换详情页视图",
                "description": "参数 view 为 sync 或 organize；写入后前端会重载页面",
            },
            {
                "path": "/organize",
                "endpoint": self.api_organize,
                "methods": ["POST"],
                "summary": "复制或删除整理组",
                "description": "参数 index 为整理组下标，operation 为 copy 或 delete",
            },
            {
                "path": "/organize-clear",
                "endpoint": self.api_organize_clear,
                "methods": ["POST"],
                "summary": "清空某个整理组的显示数值",
                "description": "只清空统计数值，不影响整理记录与文件",
            },
            {
                "path": "/organize-scan",
                "endpoint": self.api_organize_scan,
                "methods": ["POST"],
                "summary": "立即整理指定整理组",
                "description": "参数 index 为整理组下标（整理链将在第 2 步接入）",
            },
            {
                "path": "/toggle",
                "endpoint": self.api_toggle,
                "methods": ["POST"],
                "summary": "启用或停用某个路径组",
                "description": "参数 scope 为 sync / organize / mirror，index 为组下标，enabled 为布尔值",
            },
            {
                "path": "/mirror",
                "endpoint": self.api_mirror,
                "methods": ["POST"],
                "summary": "复制或删除镜像组",
                "description": "参数 index 为镜像组下标，operation 为 copy 或 delete",
            },
            {
                "path": "/mirror-clear",
                "endpoint": self.api_mirror_clear,
                "methods": ["POST"],
                "summary": "清空某个镜像组的显示数值",
                "description": "只清空统计数值，不影响镜像记录与文件",
            },
        ]

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """返回配置表单与默认配置。"""
        config = dict(default_config())
        saved = self.get_config()
        if isinstance(saved, dict):
            config.update({key: value for key, value in saved.items() if value is not None})
        rules = parse_rules(config)
        if not rules:
            rules = [SyncRule()]
            config.update(build_rule_config(0, rules[0]))
        config["rule_count"] = len(rules)
        organize_rules = parse_organize_rules(config)
        if not organize_rules:
            organize_rules = [OrganizeRule()]
            config.update(build_all_organize_config(organize_rules))
        config["organize_count"] = len(organize_rules)
        mirror_rules = parse_mirror_rules(config)
        if not mirror_rules:
            mirror_rules = [MirrorRule()]
            config.update(build_all_mirror_config(mirror_rules))
        config["mirror_count"] = len(mirror_rules)
        return [build_form(config, rules, organize_rules, mirror_rules)], config

    def _events_for_page(self) -> List[Dict[str, Any]]:
        """详情页用的命中通知（最新在前），并给历史事件补上「镜像移入回收站」标记。

        旧版本记录的事件没有 own_move 字段，这里按回收站目标现算一次，
        免得历史行继续显示成「改名」、或者一直挂在「处理中」。
        """
        events = list(reversed(self._events))[:MAX_EVENTS]
        if not self._mirror_rules:
            return events
        patched: List[Dict[str, Any]] = []
        for event in events:
            if event.get("own_move") or str(event.get("change_type") or "") != "rename":
                patched.append(event)
                continue
            new_path = str(event.get("new_path") or "")
            if not new_path or not in_mirror_recycle(self._mirror_rules, new_path):
                patched.append(event)
                continue
            item = dict(event)
            item["own_move"] = True
            item["internal"] = True
            item["done"] = True
            item["result"] = str(event.get("result") or "") or "已移入回收站"
            patched.append(item)
        return patched

    def get_page(self) -> List[dict]:
        """返回插件详情页：状态、目录组操作按钮与最近事件。"""
        if not self._enabled:
            return [
                {
                    "component": "VAlert",
                    "props": {
                        "type": "info",
                        "variant": "tonal",
                        "text": "插件未启用：请先填写 CloudDrive2 地址与 API 令牌，并开启插件。",
                    },
                }
            ]
        if not self._rules:
            return [
                {
                    "component": "VAlert",
                    "props": {
                        "type": "info",
                        "variant": "tonal",
                        "text": "尚未配置目录组：请在插件配置中添加「源目录」与「目的目录」。",
                    },
                }
            ]
        # 命中的通知与未匹配的通知分开存储，避免被自身产物刷屏挤掉
        others: List[Dict[str, Any]] = []
        if not self._globals.get("notify_only_matched"):
            others = list(reversed(self._ignored_events))[:MAX_EVENTS]
        display = dict(self._display)
        # 详情页通知合并显示：开关关闭时窗口置 0（等于不合并）
        display["merge_seconds"] = (
            int(self._globals.get("notify_merge_seconds") or 0)
            if self._globals.get("notify_merge", True)
            else 0
        )
        return build_page(
            self.__class__.__name__,
            str(getattr(settings, "API_TOKEN", "") or ""),
            self._status_snapshot(),
            self._rules,
            self._rule_stats,
            self._events_for_page(),
            list(reversed(self._actions))[:MAX_EVENTS],
            display,
            others,
            self._ignored_count,
            self._excluded_count,
            dict(self._progress),
            self._active_view,
            self._organize_rules,
            self._organize_snapshot(),
            list(reversed(self._organize_records))[:MAX_EVENTS],
            self._mirror_rules,
            self._mirror_snapshot(),
            list(reversed(self._mirror_records))[:MAX_EVENTS],
        )

    def get_service(self) -> List[Dict[str, Any]]:
        """声明宿主统一调度的服务：健康检查、定时扫描与保存后一次扫描。"""
        services: List[Dict[str, Any]] = []
        if not self._enabled:
            return services
        services.append(
            {
                "id": "Cd2StrmSyncHealth",
                "name": "CD2 Strm 订阅健康检查",
                "trigger": IntervalTrigger(minutes=1),
                "func": self._health_check,
                "kwargs": {},
            }
        )
        if self._globals.get("global_schedule_enabled"):
            hours = max(1, _safe_int(self._globals.get("global_schedule_hours"), 6))
            services.append(
                {
                    "id": "Cd2StrmSyncSchedule",
                    "name": "CD2 Strm 目录定时扫描",
                    "trigger": IntervalTrigger(hours=hours),
                    "func": self._scheduled_scan,
                    "kwargs": {},
                }
            )
        if self._globals.get("onlyonce"):
            run_date = datetime.now(tz=pytz.timezone(str(settings.TZ))) + timedelta(seconds=10)
            services.append(
                {
                    "id": "Cd2StrmSyncOnce",
                    "name": "CD2 Strm 保存后全量扫描",
                    "trigger": DateTrigger(run_date=run_date),
                    "func": self._onlyonce_scan,
                    "kwargs": {},
                }
            )
        return services

    def stop_service(self) -> None:
        """停止订阅、调度线程并释放客户端。"""
        if self._dispatcher:
            self._dispatcher.stop()
        for subscriber in self._subscribers:
            subscriber.stop()
        self._client_close()

    @eventmanager.register(EventType.PluginAction)
    def cd2_action(self, event: Event = None) -> None:
        """响应远程命令触发的全量扫描。"""
        if not event or not event.event_data:
            return
        if event.event_data.get("action") != "cd2strm_scan":
            return
        if not self._enabled:
            logger.warning("CD2 Strm 同步插件未启用，忽略全量扫描命令")
            return
        for index in range(len(self._rules)):
            self._start_scan(index, trigger="command")

    def api_status(self) -> Dict[str, Any]:
        """返回插件运行状态。"""
        return {
            "success": True,
            "message": "",
            "data": {
                "status": self._status_snapshot(),
                "stats": self._rule_stats,
                "view": self._active_view,
                "organize": self._organize_snapshot(),
                "mirror": self._mirror_snapshot(),
            },
        }

    def api_scan(self, payload: Dict[str, Any] = Body(default=None)) -> Dict[str, Any]:
        """立即扫描指定目录组。"""
        index = _safe_int((payload or {}).get("index"), -1)
        if not 0 <= index < len(self._rules):
            return {"success": False, "message": "目录组不存在", "data": None}
        if not self._rules[index].enabled:
            return {"success": False, "message": "该目录组已停用，请先启用", "data": None}
        started = self._start_scan(index)
        return {
            "success": True,
            "message": "扫描已开始，完成后刷新页面查看结果" if started else "该目录组正在扫描中",
            "data": {"index": index, "started": started},
        }

    def api_rule(self, payload: Dict[str, Any] = Body(default=None)) -> Dict[str, Any]:
        """复制或删除一个目录组。"""
        data = payload or {}
        index = _safe_int(data.get("index"), -1)
        operation = str(data.get("operation") or "")
        if not 0 <= index < len(self._rules):
            return {"success": False, "message": "目录组不存在", "data": None}
        rules = [SyncRule.from_dict(rule.to_dict()) for rule in self._rules]
        if operation == "copy":
            rules.insert(index + 1, rules[index].clone())
        elif operation == "delete":
            if len(rules) <= 1:
                return {"success": False, "message": "至少保留一个目录组", "data": None}
            rules.pop(index)
        else:
            return {"success": False, "message": "不支持的操作", "data": None}
        self._save_rules(rules)
        return {
            "success": True,
            "message": "配置已更新，打开配置页即可看到新的目录组",
            "data": {"rule_count": len(rules)},
        }

    def api_test(self, payload: Dict[str, Any] = Body(default=None)) -> Dict[str, Any]:
        """逐个测试已启用地址的连接与令牌权限（只读）。"""
        del payload
        profiles = build_connections(self._globals)
        if not profiles:
            return {
                "success": False,
                "message": "请先保存 CloudDrive2 地址与 API 令牌",
                "data": None,
            }
        results: List[Dict[str, Any]] = []
        for profile in profiles:
            client = CloudDriveWebClient(profile["host"], profile["token"])
            try:
                mounts = client.get_mount_points()
                results.append(
                    {
                        "label": profile["label"],
                        "success": True,
                        "detail": f"{len(mounts)} 个挂载点",
                    }
                )
            except CloudDriveError as err:
                results.append(
                    {"label": profile["label"], "success": False, "detail": err.message}
                )
            except Exception as err:  # pylint: disable=broad-except
                results.append(
                    {"label": profile["label"], "success": False, "detail": str(err)}
                )
            finally:
                client.close()
        message = "　｜　".join(
            f"{item['label']}：{'正常' if item['success'] else '失败'}（{item['detail']}）"
            for item in results
        )
        return {
            "success": all(item["success"] for item in results),
            "message": message,
            "data": {"results": results},
        }

    def api_display(self, payload: Dict[str, Any] = Body(default=None)) -> Dict[str, Any]:
        """调整详情页的消息显示范围（每页条数与页码）。"""
        data = payload or {}
        size = _safe_int(data.get("page_size"), 0)
        with self._state_lock:
            if size:
                self._display["page_size"] = max(5, min(size, 100))
                self._display["pages"] = {}
            key = data.get("index")
            page = _safe_int(data.get("page"), 0)
            if key is not None and page:
                pages = self._display.setdefault("pages", {})
                pages[str(key)] = max(1, page)
            self._dirty = True
        self._persist_state()
        return {
            "success": True,
            "message": "",
            "data": {"display": dict(self._display)},
        }

    def api_refresh(self, payload: Dict[str, Any] = Body(default=None)) -> Dict[str, Any]:
        """刷新详情页数据：只回传当前进度与状态，不修改任何数据。"""
        del payload
        with self._state_lock:
            scanning = sum(1 for value in self._scanning.values() if value)
            progress = {key: dict(value) for key, value in self._progress.items()}
        return {
            "success": True,
            "message": "",
            "data": {"scanning": scanning, "progress": progress},
        }

    def api_clear(self, payload: Dict[str, Any] = Body(default=None)) -> Dict[str, Any]:
        """清空某个目录组上方显示的统计数值（不影响操作记录与已生成的文件）。"""
        index = _safe_int((payload or {}).get("index"), -1)
        if not 0 <= index < len(self._rules):
            return {"success": False, "message": "目录组不存在", "data": None}
        with self._state_lock:
            self._rule_stats.pop(str(index), None)
            self._dirty = True
        self._persist_state()
        return {
            "success": True,
            "message": "已清空该目录组的显示数值",
            "data": {"index": index},
        }

    def api_purge(self, payload: Dict[str, Any] = Body(default=None)) -> Dict[str, Any]:
        """一键清除 CD2 通知、操作记录、页面统计与插件日志。"""
        del payload
        with self._state_lock:
            cleared_events = len(self._events)
            cleared_ignored = len(self._ignored_events)
            cleared_actions = len(self._actions)
            self._events = []
            self._ignored_events = []
            self._ignored_count = 0
            self._excluded_count = 0
            self._actions = []
            self._rule_stats = {}
            cleared_organize = len(self._organize_records)
            self._organize_records = []
            self._organize_stats = {}
            cleared_organize_ignored = len(self._organize_ignored)
            self._organize_ignored = []
            cleared_organize_events = len(self._organize_events)
            self._organize_events = []
            cleared_mirror = len(self._mirror_records)
            self._mirror_records = []
            self._mirror_stats = {}
            self._mirror_ignored = []
            cleared_mirror_events = len(self._mirror_events)
            self._mirror_events = []
            self._dirty = True
        self._persist_state()
        for subscriber in self._subscribers:
            subscriber.reset_stats()
        log_cleared = _truncate_plugin_log()
        message = (
            f"已清空：通知 {cleared_events} 条 / 其它通知 {cleared_ignored} 条"
            f" / 操作记录 {cleared_actions} 条"
        )
        if cleared_organize:
            message += f" / 整理记录 {cleared_organize} 条"
        if cleared_organize_ignored:
            message += f" / 未匹配通知 {cleared_organize_ignored} 条"
        if cleared_organize_events:
            message += f" / 整理命中通知 {cleared_organize_events} 条"
        if cleared_mirror:
            message += f" / 镜像记录 {cleared_mirror} 条"
        if cleared_mirror_events:
            message += f" / 镜像命中通知 {cleared_mirror_events} 条"
        message += "，插件日志已清空" if log_cleared else "（插件日志文件不存在）"
        return {
            "success": True,
            "message": message,
            "data": {
                "events": cleared_events,
                "ignored": cleared_ignored,
                "actions": cleared_actions,
                "organize_records": cleared_organize,
                "log_cleared": log_cleared,
            },
        }

    def api_clear_notify(self, payload: Dict[str, Any] = Body(default=None)) -> Dict[str, Any]:
        """只清除 CD2 通知（不动统计数值与插件日志）。

        target：hit 只清命中列表；unaccepted 只清未匹配（未受理）缓冲；
        all（缺省，与旧行为一致）两者一起清。统计数值改由 /clear-count 负责。
        scope=all（详情页顶部「消息与日志」区的「清空通知与记录」按钮）在 target=all 时
        额外清空操作记录，使按钮名与行为一致；单视图 scope 一律不动操作记录。
        """
        payload = payload or {}
        scope = str(payload.get("scope") or "sync").strip()
        target = str(payload.get("target") or "all").strip().lower()
        if target not in CLEAR_TARGETS:
            return {"success": False, "message": "不支持的 target", "data": None}
        if scope == "all":
            with self._state_lock:
                cleared = 0
                for hit_attr, unaccepted_attr in NOTIFY_FIELDS.values():
                    if target in ("hit", "all"):
                        cleared += len(getattr(self, hit_attr))
                        setattr(self, hit_attr, [])
                    if target in ("unaccepted", "all"):
                        cleared += len(getattr(self, unaccepted_attr))
                        setattr(self, unaccepted_attr, [])
                cleared_actions = len(self._actions) if target == "all" else 0
                if cleared_actions:
                    self._actions = []
                self._dirty = True
            self._persist_state()
            message = (
                f"已清除全部功能的{CLEAR_TARGET_LABELS.get(target, '全部')} CD2 通知 {cleared} 条"
            )
            if cleared_actions:
                message += f" / 操作记录 {cleared_actions} 条"
            return {
                "success": True,
                "message": message,
                "data": {
                    "scope": scope,
                    "target": target,
                    "cleared": cleared,
                    "actions": cleared_actions,
                },
            }
        if scope == "sync":
            with self._state_lock:
                cleared = 0
                if target in ("hit", "all"):
                    cleared += len(self._events)
                    self._events = []
                if target in ("unaccepted", "all"):
                    cleared += len(self._ignored_events)
                    self._ignored_events = []
                self._dirty = True
            self._persist_state()
            return {
                "success": True,
                "message": f"已清除{CLEAR_TARGET_LABELS.get(target, '全部')} CD2 通知 {cleared} 条",
                "data": {"scope": scope, "target": target, "cleared": cleared},
            }
        if scope == "organize":
            with self._state_lock:
                cleared = 0
                if target in ("hit", "all"):
                    cleared += len(self._organize_events)
                    self._organize_events = []
                if target in ("unaccepted", "all"):
                    cleared += len(self._organize_ignored)
                    self._organize_ignored = []
                self._dirty = True
            self._persist_state()
            return {
                "success": True,
                "message": f"已清除{CLEAR_TARGET_LABELS.get(target, '全部')} CD2 通知 {cleared} 条",
                "data": {"scope": scope, "target": target, "cleared": cleared},
            }
        if scope == "mirror":
            with self._state_lock:
                cleared = 0
                if target in ("hit", "all"):
                    cleared += len(self._mirror_events)
                    self._mirror_events = []
                if target in ("unaccepted", "all"):
                    cleared += len(self._mirror_ignored)
                    self._mirror_ignored = []
                self._dirty = True
            self._persist_state()
            return {
                "success": True,
                "message": f"已清除{CLEAR_TARGET_LABELS.get(target, '全部')} CD2 通知 {cleared} 条",
                "data": {"scope": scope, "target": target, "cleared": cleared},
            }
        return {"success": False, "message": "不支持的视图", "data": None}

    def api_clear_count(self, payload: Dict[str, Any] = Body(default=None)) -> Dict[str, Any]:
        """只清空某个功能视图的统计数值（不动通知列表、操作记录与插件日志）。

        sync：各组统计数值 + 未匹配计数与排除目录计数；organize / mirror：所有组的统计数值。
        """
        scope = str((payload or {}).get("scope") or "sync").strip()
        if scope not in ("sync", "organize", "mirror"):
            return {"success": False, "message": "不支持的视图", "data": None}
        with self._state_lock:
            if scope == "sync":
                groups = len(self._rule_stats)
                self._rule_stats = {}
                self._ignored_count = 0
                self._excluded_count = 0
            elif scope == "organize":
                groups = len(self._organize_stats)
                self._organize_stats = {}
            else:
                groups = len(self._mirror_stats)
                self._mirror_stats = {}
            self._dirty = True
        self._persist_state()
        return {
            "success": True,
            "message": f"已清空统计数值（{groups} 组）",
            "data": {"scope": scope, "groups": groups},
        }

    def api_clear_log(self, payload: Dict[str, Any] = Body(default=None)) -> Dict[str, Any]:
        """只清空插件日志文件（不动 CD2 通知、操作记录与统计）。"""
        del payload
        cleared = _truncate_plugin_log()
        return {
            "success": bool(cleared),
            "message": "插件日志已清空" if cleared else "插件日志文件不存在或无法清空",
            "data": {"log_cleared": bool(cleared)},
        }

    def api_view(self, payload: Dict[str, Any] = Body(default=None)) -> Dict[str, Any]:
        """切换详情页视图（sync / organize / mirror）。"""
        view = str((payload or {}).get("view") or "").strip()
        if view not in ("sync", "organize", "mirror"):
            return {"success": False, "message": "不支持的视图", "data": None}
        self._active_view = view
        self._dirty = True
        self._persist_state()
        return {"success": True, "message": "已切换视图", "data": {"view": view}}

    def api_toggle(self, payload: Dict[str, Any] = Body(default=None)) -> Dict[str, Any]:
        """启用或停用一个路径组（STRM 目录组与整理组共用）。"""
        data = payload or {}
        scope = str(data.get("scope") or "").strip()
        index = _safe_int(data.get("index"), -1)
        enabled = bool(data.get("enabled"))
        if scope == "sync":
            if not 0 <= index < len(self._rules):
                return {"success": False, "message": "目录组不存在", "data": None}
            rules_list = [SyncRule.from_dict(rule.to_dict()) for rule in self._rules]
            rules_list[index].enabled = enabled
            self._save_rules(rules_list)
        elif scope == "organize":
            if not 0 <= index < len(self._organize_rules):
                return {"success": False, "message": "整理组不存在", "data": None}
            rules_list = [
                OrganizeRule.from_dict(rule.to_dict()) for rule in self._organize_rules
            ]
            rules_list[index].enabled = enabled
            self._save_organize_rules(rules_list)
        elif scope == "mirror":
            if not 0 <= index < len(self._mirror_rules):
                return {"success": False, "message": "镜像组不存在", "data": None}
            rules_list = [MirrorRule.from_dict(rule.to_dict()) for rule in self._mirror_rules]
            rules_list[index].enabled = enabled
            self._save_mirror_rules(rules_list)
        else:
            return {"success": False, "message": "不支持的视图", "data": None}
        return {
            "success": True,
            "message": "该组已启用" if enabled else "该组已停用",
            "data": {"scope": scope, "index": index, "enabled": enabled},
        }

    def api_mirror(self, payload: Dict[str, Any] = Body(default=None)) -> Dict[str, Any]:
        """复制或删除一个镜像组。"""
        data = payload or {}
        index = _safe_int(data.get("index"), -1)
        operation = str(data.get("operation") or "")
        if not 0 <= index < len(self._mirror_rules):
            return {"success": False, "message": "镜像组不存在", "data": None}
        rules = [MirrorRule.from_dict(rule.to_dict()) for rule in self._mirror_rules]
        if operation == "copy":
            rules.insert(index + 1, rules[index].clone())
        elif operation == "delete":
            if len(rules) <= 1:
                return {"success": False, "message": "至少保留一个镜像组", "data": None}
            rules.pop(index)
        else:
            return {"success": False, "message": "不支持的操作", "data": None}
        self._save_mirror_rules(rules)
        return {
            "success": True,
            "message": "配置已更新，打开配置页即可看到新的镜像组",
            "data": {"mirror_count": len(rules)},
        }

    def api_mirror_clear(self, payload: Dict[str, Any] = Body(default=None)) -> Dict[str, Any]:
        """清空某个镜像组的统计数值（不动镜像记录与文件）。"""
        index = _safe_int((payload or {}).get("index"), -1)
        if not 0 <= index < len(self._mirror_rules):
            return {"success": False, "message": "镜像组不存在", "data": None}
        with self._state_lock:
            self._mirror_stats.pop(str(index), None)
            self._dirty = True
        self._persist_state()
        return {"success": True, "message": "已清空该镜像组的显示数值", "data": None}

    def api_organize(self, payload: Dict[str, Any] = Body(default=None)) -> Dict[str, Any]:
        """复制或删除一个整理组。"""
        data = payload or {}
        index = _safe_int(data.get("index"), -1)
        operation = str(data.get("operation") or "")
        if not 0 <= index < len(self._organize_rules):
            return {"success": False, "message": "整理组不存在", "data": None}
        rules = [OrganizeRule.from_dict(rule.to_dict()) for rule in self._organize_rules]
        if operation == "copy":
            rules.insert(index + 1, rules[index].clone())
        elif operation == "delete":
            if len(rules) <= 1:
                return {"success": False, "message": "至少保留一个整理组", "data": None}
            rules.pop(index)
        else:
            return {"success": False, "message": "不支持的操作", "data": None}
        self._save_organize_rules(rules)
        return {
            "success": True,
            "message": "配置已更新，打开配置页即可看到新的整理组",
            "data": {"organize_count": len(rules)},
        }

    def api_organize_clear(self, payload: Dict[str, Any] = Body(default=None)) -> Dict[str, Any]:
        """清空某个整理组的统计数值（不动整理记录与文件）。"""
        index = _safe_int((payload or {}).get("index"), -1)
        if not 0 <= index < len(self._organize_rules):
            return {"success": False, "message": "整理组不存在", "data": None}
        with self._state_lock:
            self._organize_stats.pop(str(index), None)
            self._dirty = True
        self._persist_state()
        return {"success": True, "message": "已清空该整理组的显示数值", "data": None}

    def api_organize_scan(self, payload: Dict[str, Any] = Body(default=None)) -> Dict[str, Any]:
        """立即整理指定整理组：扫描源目录并把视频文件逐个交给整理链。"""
        index = _safe_int((payload or {}).get("index"), -1)
        if not 0 <= index < len(self._organize_rules):
            return {"success": False, "message": "整理组不存在", "data": None}
        if not self._organize_globals.get("organize_enabled"):
            return {"success": False, "message": "媒体整理未启用，请先在配置页开启", "data": None}
        rule = self._organize_rules[index]
        if not rule.enabled:
            return {"success": False, "message": "该整理组已停用，请先启用", "data": None}
        if not rule.is_ready():
            return {
                "success": False,
                "message": "请先填写该整理组的源目录与目的目录",
                "data": None,
            }
        source = Path(rule.src.strip())
        if not source.is_dir():
            return {"success": False, "message": f"整理源目录不可见：{source}", "data": None}
        queued = 0
        skipped = 0
        excluded = {os.path.normpath(item) for item in rule.exclude_list}
        for root, _dirs, files in os.walk(source):
            current = os.path.normpath(root)
            if any(current == item or current.startswith(f"{item}{os.sep}") for item in excluded):
                continue
            for name in files:
                path = os.path.join(root, name)
                if not is_organize_candidate(path):
                    continue
                self._enqueue_organize(index, path, "manual")
                queued += 1
        if not queued:
            return {"success": True, "message": "该整理组没有待整理的视频文件", "data": {"queued": 0}}
        return {
            "success": True,
            "message": f"已提交 {queued} 个文件到整理队列，稍后可在「整理记录」查看结果",
            "data": {"queued": queued, "skipped": skipped},
        }

    def _organize_snapshot(self) -> Dict[str, Any]:
        """汇总媒体整理的运行状态供详情页展示。"""
        with self._state_lock:
            stats = {key: dict(value) for key, value in self._organize_stats.items()}
            record_count = len(self._organize_records)
            ignored = list(self._organize_ignored)
            events = list(self._organize_events)
        return {
            "organize_enabled": bool(self._organize_globals.get("organize_enabled")),
            "notify": bool(self._organize_globals.get("organize_notify")),
            "accepted": sum(int(item.get("accepted") or 0) for item in stats.values()),
            "pending": self._organize_queue.qsize(),
            # 「正在整理」＝当前有任务在执行或排队；工作线程是常驻的，不能拿线程存活当判据
            "running": 1 if (self._organize_busy or self._organize_queue.qsize() > 0) else 0,
            "record_count": record_count,
            "group_count": len(self._organize_rules),
            "stats": stats,
            "ignored": ignored,
            "ignored_count": len(ignored),
            "events": events,
            "hit_count": len(events),
            "last_error": "",
        }

    def _save_organize_rules(self, rules: List[OrganizeRule]) -> None:
        """把整理组写回插件配置并同步内存状态。"""
        config = dict(self.get_config() or {})
        for key in [item for item in config if ORGANIZE_KEY_PATTERN.match(str(item))]:
            config.pop(key, None)
        config.update(build_all_organize_config(rules))
        self.update_config(config)
        self._organize_rules = rules

    def _mirror_snapshot(self) -> Dict[str, Any]:
        """汇总镜像移动的运行状态供详情页展示（第 B 步为骨架，执行链待第 C 步）。"""
        with self._state_lock:
            stats = {key: dict(value) for key, value in self._mirror_stats.items()}
            record_count = len(self._mirror_records)
            ignored = list(self._mirror_ignored)
            events = list(self._mirror_events)
        return {
            "enabled": bool(self._mirror_globals.get("mirror_enabled")),
            "dry_run": bool(self._mirror_globals.get("mirror_dry_run", True)),
            "notify": bool(self._mirror_globals.get("mirror_notify")),
            "accepted": sum(int(item.get("accepted") or 0) for item in stats.values()),
            "moved_files": sum(int(item.get("moved_files") or 0) for item in stats.values()),
            "moved_dirs": sum(int(item.get("moved_dirs") or 0) for item in stats.values()),
            "protected": sum(int(item.get("protected") or 0) for item in stats.values()),
            "skipped": sum(int(item.get("skipped") or 0) for item in stats.values()),
            "failed": sum(int(item.get("failed") or 0) for item in stats.values()),
            "pending": self._mirror_queue.qsize(),
            "running": 1 if (self._mirror_busy or self._mirror_queue.qsize() > 0) else 0,
            "record_count": record_count,
            "group_count": len(self._mirror_rules),
            "stats": stats,
            "ignored": ignored,
            "ignored_count": len(ignored),
            "events": events,
            "hit_count": len(events),
        }

    def _save_mirror_rules(self, rules: List[MirrorRule]) -> None:
        """把镜像组写回插件配置并同步内存状态。"""
        config = dict(self.get_config() or {})
        for key in [item for item in config if MIRROR_KEY_PATTERN.match(str(item))]:
            config.pop(key, None)
        config.update(build_all_mirror_config(rules))
        self.update_config(config)
        self._mirror_rules = rules

    def _start_organize_worker(self) -> None:
        """按需启动整理工作线程（单线程串行，避免并发刮削）。"""
        if not self._organize_globals.get("organize_enabled"):
            return
        if self._organize_worker and self._organize_worker.is_alive():
            return
        self._organize_stop.clear()
        self._organize_worker = threading.Thread(
            target=self._organize_loop,
            name="cd2strm-organize",
            daemon=True,
        )
        self._organize_worker.start()

    def _stop_organize_worker(self) -> None:
        """停止整理工作线程并清空去重集合。"""
        self._organize_stop.set()
        worker = self._organize_worker
        if worker and worker.is_alive():
            worker.join(timeout=2)
        self._organize_worker = None
        self._organize_busy = False
        with self._state_lock:
            self._organize_seen = set()

    def _organize_loop(self) -> None:
        """串行消费整理队列。"""
        while not self._organize_stop.is_set():
            try:
                index, container_path, trigger = self._organize_queue.get(timeout=1)
            except queue.Empty:
                continue
            try:
                self._organize_busy = True
                self._organize_one(index, container_path, trigger)
            except Exception as err:  # pylint: disable=broad-except
                logger.error(f"媒体整理失败 {container_path}：{err}")
            finally:
                self._organize_busy = False
                self._organize_queue.task_done()

    def _hit_events_of(self, view: str) -> List[Dict[str, Any]]:
        """取某个功能的「命中通知」缓冲。"""
        return self._mirror_events if view == "mirror" else self._organize_events

    def _record_hit_event(
        self,
        view: str,
        index: int,
        key_path: str,
        display_path: str,
        change_type: str = "create",
        new_path: str = "",
        is_dir: bool = False,
        source: str = "",
    ) -> None:
        """记录一条命中本功能规则的通知（受理即记录，执行完成后再回填结果）。

        key_path 用于与执行结果配对；display_path 是页面上展示的路径。
        同一对象尚未处理完时重复通知只更新最近一条，不新增行。
        """
        events = self._hit_events_of(view)
        key = normalize_path(key_path)
        record = {
            "time": _format_time(time.time()),
            "change_type": change_type,
            "path": display_path,
            "new_path": new_path,
            "is_dir": bool(is_dir),
            "source": source,
            "rule_index": index,
            "raw": key,
            "outcome": "已受理",
            "done": False,
            "result": "",
        }
        with self._state_lock:
            for item in reversed(events):
                if item.get("rule_index") == index and item.get("raw") == key:
                    if item.get("done"):
                        break
                    item.update({k: v for k, v in record.items() if k != "raw"})
                    self._dirty = True
                    return
            events.append(record)
            if len(events) > MAX_EVENTS:
                del events[:-MAX_EVENTS]
            self._dirty = True

    def _update_hit_event(
        self, view: str, index: int, key_path: str, result: str, done: bool = True
    ) -> None:
        """回填某条命中通知的处理结果（页面上表现为行尾 ✔ 与悬停结果）。"""
        events = self._hit_events_of(view)
        key = normalize_path(key_path)
        with self._state_lock:
            for item in reversed(events):
                if item.get("rule_index") == index and item.get("raw") == key:
                    item["done"] = bool(done)
                    item["result"] = result
                    self._dirty = True
                    return

    def _dispatch_organize(self, message: Dict[str, Any], source: str = "") -> None:
        """按整理规则受理通知（与 STRM 侧各自独立处理）。

        候选路径：create 看 path；rename 同时看 path 与 new_path——优先取「命中规则且实际
        存在」的那个，避免「搬出源目录」制造假失败。没有候选命中时写入「未受理」缓冲，
        便于在详情页自查原因。
        """
        if not self._organize_globals.get("organize_enabled") or not self._organize_rules:
            return
        change_type = str(message.get("change_type") or "")
        if change_type not in ("create", "rename"):
            return
        is_dir = bool(message.get("is_dir"))
        candidates: List[str] = []
        for raw in (str(message.get("path") or ""), str(message.get("new_path") or "")):
            if raw and raw not in candidates:
                candidates.append(raw)
        matches: List[Tuple[int, str, bool]] = []
        reasons: List[str] = []
        for raw in candidates:
            # 目录事件整目录整理，不做视频后缀过滤
            if not is_dir and not is_organize_candidate(raw):
                reasons.append("非视频文件")
                continue
            index = match_organize_rule(self._organize_rules, raw)
            if index is None:
                reasons.append(self._organize_reject_reason(raw))
                continue
            rule = self._organize_rules[index]
            container_path = organize_container_path(rule, raw)
            matches.append((index, container_path, Path(container_path).exists()))
        if matches:
            chosen = next((item for item in matches if item[2]), matches[0])
            self._accept_organize(
                chosen[0],
                chosen[1],
                change_type=change_type,
                new_path=str(message.get("new_path") or ""),
                is_dir=is_dir,
                source=source,
            )
            return
        if reasons:
            self._record_organize_ignored(
                change_type,
                candidates[0] if candidates else "",
                message,
                reasons[0],
                source,
            )

    def _accept_organize(
        self,
        index: int,
        container_path: str,
        change_type: str = "create",
        new_path: str = "",
        is_dir: bool = False,
        source: str = "",
    ) -> None:
        """受理一条整理任务：计数、记入命中通知，再按合并窗口去抖后进入串行队列。"""
        self._record_hit_event(
            "organize",
            index,
            container_path,
            container_path,
            change_type=change_type,
            new_path=new_path,
            is_dir=is_dir,
            source=source,
        )
        with self._state_lock:
            stats = self._organize_stats.setdefault(str(index), {})
            stats["accepted"] = int(stats.get("accepted") or 0) + 1
            self._dirty = True
        self._persist_state()
        delay = max(0, int(self._globals.get("merge_seconds") or 2))
        timer = threading.Timer(delay, self._enqueue_organize, args=(index, container_path, "event"))
        timer.daemon = True
        timer.start()

    def _organize_reject_reason(self, raw: str) -> str:
        """给出某条通知未被整理受理的具体原因（用于自查）。"""
        for rule in self._organize_rules:
            if not rule.is_active():
                continue
            target = to_organize_internal(rule, raw)
            src = to_organize_internal(rule, rule.src)
            dst = to_organize_internal(rule, rule.dst)
            in_src = bool(src) and (target == src or target.startswith(f"{src}/"))
            in_dst = bool(dst) and (target == dst or target.startswith(f"{dst}/"))
            nested_dst = bool(dst) and bool(src) and (dst == src or dst.startswith(f"{src}/"))
            if in_dst and (not in_src or nested_dst):
                return "落在整理目的目录内"
            if in_src:
                for item in rule.exclude_list:
                    item_path = to_organize_internal(rule, item)
                    if item_path and (target == item_path or target.startswith(f"{item_path}/")):
                        return "落在排除目录内"
        return "未命中整理规则"

    def _record_organize_ignored(
        self,
        change_type: str,
        raw: str,
        message: Dict[str, Any],
        reason: str,
        source: str = "",
    ) -> None:
        """记录一条未被整理受理的通知，便于在详情页自查。"""
        with self._state_lock:
            self._organize_ignored.append(
                {
                    "time": datetime.now().strftime("%m-%d %H:%M:%S"),
                    "change_type": change_type,
                    "path": raw,
                    "new_path": str((message or {}).get("new_path") or ""),
                    "is_dir": bool((message or {}).get("is_dir")),
                    "reason": reason,
                    "source": source,
                }
            )
            if len(self._organize_ignored) > ORGANIZE_IGNORE_LIMIT:
                self._organize_ignored = self._organize_ignored[-ORGANIZE_IGNORE_LIMIT:]
            self._dirty = True
        self._persist_state()

    def _enqueue_organize(self, index: int, container_path: str, trigger: str) -> None:
        """把整理任务放进串行队列（同一文件去重）。"""
        if not self._organize_globals.get("organize_enabled"):
            return
        key = f"{index}|{container_path}"
        with self._state_lock:
            if key in self._organize_seen:
                return
            self._organize_seen.add(key)
        self._organize_queue.put((index, container_path, trigger))
        self._start_organize_worker()

    def _organize_one(self, index: int, container_path: str, trigger: str) -> None:
        """执行一次整理，写入统计与记录，并按开关推送通知。"""
        if not 0 <= index < len(self._organize_rules):
            return
        rule = self._organize_rules[index]
        ok, message, media, reason = organize_path(rule, container_path)
        skipped = (not ok) and _is_benign_organize_rejection(message, reason)
        result = "success" if ok else ("skipped" if skipped else "failed")
        now_text = _format_time(time.time())
        with self._state_lock:
            stats = self._organize_stats.setdefault(str(index), {})
            counter = {"success": "organized", "skipped": "skipped", "failed": "failed"}[result]
            stats[counter] = int(stats.get(counter) or 0) + 1
            stats["time"] = now_text
            # 「跳过」只计入统计与日志，不写进整理记录表（例如整理成功后源文件已移走的通知）
            if result != "skipped":
                self._organize_records.append(
                    {
                        "time": now_text,
                        "trigger": trigger,
                        "result": result,
                        "rule_index": index,
                        "media": media,
                        "file": container_path,
                        "message": message if ok else (reason or message),
                    }
                )
                self._organize_records = self._organize_records[-MAX_EVENTS:]
            self._organize_seen.discard(f"{index}|{container_path}")
            self._dirty = True
        hit_result = (
            f"已整理：{media or '—'}"
            if ok
            else (
                f"跳过：{_benign_skip_reason(message, reason)}"
                if skipped
                else f"失败：{reason or message}"
            )
        )
        self._update_hit_event("organize", index, container_path, hit_result)
        self._persist_state()
        logger.info(
            f"[整理] {rule.display_name(index)} {result}：{container_path}"
            + ("（目录）" if Path(container_path).is_dir() else "")
            + (f"（{reason}）" if reason and not ok else "")
        )
        self._notify_organize(index, rule, ok, message, media, container_path, reason, result)

    def _notify_organize(
        self,
        index: int,
        rule: OrganizeRule,
        ok: bool,
        message: str,
        media: str,
        container_path: str,
        reason: str,
        result: str = "failed",
    ) -> None:
        """按开关推送整理结果（全局或该整理组任一开启即推送）。"""
        if not (self._organize_globals.get("organize_notify") or rule.notify):
            return
        if result == "skipped":
            # 「跳过」不是失败：例如整理成功后源文件已被移走而产生的回声通知，
            # 只记日志与统计，不推送，避免误导为失败。
            return
        name = rule.display_name(index)
        parent = container_path.rsplit("/", 1)[0] if "/" in str(container_path) else ""
        if ok:
            title = f"✅ 整理完成 · {name}"
            lines = ["🎞 **已整理**"]
            if media:
                lines.append(f"🏷 `{media}`")
            lines.append(f"📄 `{_file_name(container_path)}`")
            if parent:
                lines.append(f"📁 `{_short_path(parent)}`")
        else:
            title = f"⚠️ 整理失败 · {name}"
            lines = [
                "❌ **整理失败**",
                f"📌 **原因** `{_short_text(reason or message)}`",
                f"📄 `{_file_name(container_path)}`",
            ]
            if parent:
                lines.append(f"📁 `{_short_path(parent)}`")
        try:
            self.post_message(title=title, text="\n".join(lines))
        except Exception as err:  # pylint: disable=broad-except
            logger.warning(f"整理通知发送失败：{err}")

    def _start_mirror_worker(self) -> None:
        """按需启动镜像移动工作线程（单线程串行，避免并发移动）。"""
        if not self._mirror_globals.get("mirror_enabled"):
            return
        if self._mirror_worker and self._mirror_worker.is_alive():
            return
        self._mirror_stop.clear()
        self._mirror_worker = threading.Thread(
            target=self._mirror_loop, name="cd2-mirror", daemon=True
        )
        self._mirror_worker.start()

    def _stop_mirror_worker(self) -> None:
        """停止镜像移动工作线程、丢弃待处理任务与去抖计时器。"""
        self._mirror_stop.set()
        while not self._mirror_queue.empty():
            try:
                self._mirror_queue.get_nowait()
            except queue.Empty:
                break
        worker, self._mirror_worker = self._mirror_worker, None
        if worker and worker.is_alive():
            worker.join(timeout=2)
        for timer in list(self._mirror_timers):
            timer.cancel()
        self._mirror_timers = []
        self._mirror_seen = set()
        self._mirror_busy = False

    def _mirror_loop(self) -> None:
        """串行消费镜像任务。"""
        while not self._mirror_stop.is_set():
            try:
                index, raw_path, is_dir, trigger = self._mirror_queue.get(timeout=1)
            except queue.Empty:
                continue
            try:
                self._mirror_one(index, raw_path, is_dir, trigger)
            except Exception as err:  # pylint: disable=broad-except
                logger.error(f"镜像移动处理失败：{err}")
            finally:
                self._mirror_busy = False
                self._mirror_queue.task_done()

    def _dispatch_mirror(self, message: Dict[str, Any], source: str = "") -> None:
        """镜像移动独立受理一条 CD2 通知（与 STRM 同步、媒体整理互不影响）。

        开关语义：总开关关闭 → 完全不处理（不记录）；总开关开但该组停用 → 记入未受理
        缓冲；总开关 + 该组开 → 受理，预演模式下只记录将要移动什么、不实际移动。
        """
        if not self._mirror_globals.get("mirror_enabled") or not self._mirror_rules:
            return
        change_type = str(message.get("change_type") or "")
        raw_path = str(message.get("path") or "")
        is_dir = bool(message.get("is_dir"))
        if not raw_path or change_type != "delete":
            return
        index = match_mirror_rule(self._mirror_rules, raw_path)
        if index is None:
            self._record_mirror_ignored(
                change_type, raw_path, is_dir, source, "未命中监听目录"
            )
            return
        rule = self._mirror_rules[index]
        if not rule.enabled:
            self._record_mirror_ignored(change_type, raw_path, is_dir, source, "该镜像组已停用")
            return
        self._record_hit_event(
            "mirror",
            index,
            raw_path,
            self._to_container_path(raw_path) or normalize_path(raw_path),
            change_type=change_type,
            is_dir=is_dir,
            source=source,
        )
        with self._state_lock:
            stats = self._mirror_stats.setdefault(str(index), {})
            stats["accepted"] = int(stats.get("accepted") or 0) + 1
            stats["time"] = _format_time(time.time())
            self._dirty = True
        self._persist_state()
        self._enqueue_mirror(index, raw_path, is_dir, "event")

    def _record_mirror_ignored(
        self,
        change_type: str,
        raw_path: str,
        is_dir: bool,
        source: str,
        reason: str,
    ) -> None:
        """记录一条未被镜像受理的删除通知（供页面自查）。"""
        with self._state_lock:
            self._mirror_ignored.append(
                {
                    "time": _format_time(time.time()),
                    "change_type": change_type,
                    "path": self._to_container_path(raw_path) or raw_path,
                    "is_dir": is_dir,
                    "reason": reason,
                    "source": source,
                }
            )
            while len(self._mirror_ignored) > MIRROR_IGNORE_LIMIT:
                self._mirror_ignored.pop(0)
            self._dirty = True
        self._persist_state()

    def _enqueue_mirror(self, index: int, raw_path: str, is_dir: bool, trigger: str) -> None:
        """去抖后把任务放进镜像队列（同一对象只处理一次）。"""
        delay = float(self._globals.get("merge_seconds") or 2)
        key = f"{index}|{normalize_path(raw_path)}|{int(is_dir)}"
        with self._state_lock:
            if key in self._mirror_seen:
                return
            self._mirror_seen.add(key)
            if len(self._mirror_seen) > 500:
                self._mirror_seen = {key}

        def _push() -> None:
            self._mirror_queue.put((index, raw_path, is_dir, trigger))

        if delay > 0:
            timer = threading.Timer(delay, _push)
            timer.daemon = True
            with self._state_lock:
                self._mirror_timers = [item for item in self._mirror_timers if item.is_alive()]
                self._mirror_timers.append(timer)
            timer.start()
        else:
            _push()

    def _mirror_one(self, index: int, raw_path: str, is_dir: bool, trigger: str) -> None:
        """执行一次镜像移动（预演时只记录不落盘）。"""
        if not 0 <= index < len(self._mirror_rules):
            return
        rule = self._mirror_rules[index]
        dry_run = bool(self._mirror_globals.get("mirror_dry_run", True))
        self._mirror_busy = True
        try:
            outcome = move_mirror_targets(
                rule, raw_path, is_dir, dry_run=dry_run, trigger=trigger
            )
        finally:
            self._mirror_busy = False
        now = _format_time(time.time())
        record: Dict[str, Any] = {
            "time": now,
            "ts": time.time(),
            "trigger": trigger,
            "result": str(outcome.get("result") or "skipped"),
            "dry_run": dry_run,
            "path": str(outcome.get("path") or ""),
            "is_dir": bool(outcome.get("is_dir")),
            "target": str(outcome.get("target") or ""),
            "moved": list(outcome.get("moved") or [])[:MIRROR_REPORT_PATHS],
            "protected": list(outcome.get("protected_items") or [])[:MIRROR_REPORT_PATHS],
            "skipped": list(outcome.get("skipped_items") or [])[:MIRROR_REPORT_PATHS],
            "failed": list(outcome.get("failed_items") or [])[:MIRROR_REPORT_PATHS],
            "rule": rule.display_name(index),
            "rule_index": index,
        }
        with self._state_lock:
            current = self._mirror_stats.setdefault(str(index), {})
            for key in ("moved_files", "moved_dirs", "protected", "skipped", "failed"):
                current[key] = int(current.get(key) or 0) + int(outcome.get(key) or 0)
            current["time"] = now
            current["dry_run"] = dry_run
            if record["result"] != "skipped":
                self._mirror_records.append(record)
                while len(self._mirror_records) > MAX_EVENTS:
                    self._mirror_records.pop(0)
            self._dirty = True
        moved_total = int(outcome.get("moved_files") or 0) + int(outcome.get("moved_dirs") or 0)
        if record["result"] == "failed":
            hit_result = "失败：" + ("；".join(record["failed"]) or "未知原因")
        elif record["result"] == "skipped":
            hit_result = "跳过：" + ("；".join(record["skipped"]) or "无可移动对象")
        else:
            prefix = "预演：将移动" if dry_run else "已移动"
            hit_result = f"{prefix} {moved_total or len(record['moved'])} 项"
        self._update_hit_event("mirror", index, raw_path, hit_result)
        self._persist_state()
        detail = "；".join(record["moved"] or record["failed"] or record["skipped"]) or "无变化"
        logger.info(
            f"[镜像] {rule.display_name(index)} {record['result']}"
            f"{'（预演）' if dry_run else ''}：{record['path']} → {detail}"
        )
        if record["result"] != "skipped":
            self._notify_mirror(record, rule)

    def _notify_mirror(self, record: Dict[str, Any], rule: MirrorRule) -> None:
        """按开关推送镜像移动结果（全局或该组任一开启即推送；跳过不推）。"""
        if not (self._mirror_globals.get("mirror_notify") or rule.notify):
            return
        name = rule.display_name(int(record.get("rule_index") or 0))
        dry_run = bool(record.get("dry_run"))
        moved = list(record.get("moved") or [])
        protected = list(record.get("protected") or [])
        failed = list(record.get("failed") or [])
        skipped = list(record.get("skipped") or [])
        if record.get("result") == "failed":
            title = f"⚠️ 镜像移动 · 失败 · {name}"
            lines = [f"❌ **失败 {len(failed)} 项**"]
        elif dry_run:
            title = f"🧪 镜像移动 · 预演 · {name}"
            lines = [f"🧪 **预演：将移动 {len(moved)} 项**（未真正移动）"]
        else:
            title = f"🔁 镜像移动 · {name}"
            lines = [f"✅ **已移动 {len(moved)} 项**"]
        if record.get("path"):
            lines.append(f"📄 监听目录 `{_file_name(str(record['path']))}`")
        if moved:
            lines.append("")
            lines.append("📦 **将移动到**" if dry_run else "📦 **已移动到**")
            for item in moved[:3]:
                lines.append(f"- `{_file_name(item)}`")
            if len(moved) > 3:
                lines.append(f"- 其余 {len(moved) - 3} 条见插件页面")
        if protected:
            lines.append(f"🛡 保护保留 {len(protected)} 项（未移动）")
        if failed:
            lines.append("")
            lines.append(f"❌ **失败 {len(failed)} 项**")
            for item in failed[:3]:
                lines.append(f"- `{_short_path(item, 3)}`")
        if skipped:
            lines.append(f"⏭ 跳过 {len(skipped)} 项")
        if record.get("target"):
            lines.append("")
            lines.append(f"🗑 `{_short_path(str(record['target']))}`")
        try:
            self.post_message(title=title, text="\n".join(lines))
        except Exception as err:  # pylint: disable=broad-except
            logger.warning(f"推送镜像移动通知失败：{err}")

    def _rules_snapshot(self) -> List[SyncRule]:
        """返回当前规则列表副本，供调度器读取。"""
        return list(self._rules)

    def _resolve_event(
        self, event: Dict[str, Any], rules: List[SyncRule]
    ) -> List[Tuple[int, str, float, Dict[str, Any]]]:
        """把一条通知解析成（规则下标，合并键，延迟秒数，处理载荷）列表。"""
        change_type = str(event.get("change_type") or "")
        is_dir = bool(event.get("is_dir"))
        merge_seconds = float(self._globals.get("merge_seconds") or 2)
        dir_seconds = float(self._globals.get("debounce_seconds") or 5)
        results: List[Tuple[int, str, float, Dict[str, Any]]] = []
        for raw in (event.get("path") or "", event.get("new_path") or ""):
            if not raw:
                continue
            index, _relative = match_rule(rules, raw)
            if index is None:
                continue
            rule = rules[index]
            if not rule.is_active() or is_excluded(rule, raw):
                continue
            path = normalize_path(raw)
            suffix = Path(path).suffix.lower()
            if not is_dir and change_type != "delete" and suffix not in rule.link_ext_set:
                if suffix not in rule.metadata_ext_set:
                    continue
            mode = rule.process_mode or "precise"
            if mode == "precise":
                if (
                    not is_dir
                    and change_type in ("create", "rename")
                    and suffix in rule.link_ext_set
                ):
                    # 新增视频：立即只写 strm；同名元数据延后到合并窗口后再同步，
                    # 避免读到仍在写入的半截元数据文件。
                    results.append(
                        (
                            index,
                            f"{path}#link",
                            0.0,
                            {
                                "path": path,
                                "change_type": change_type,
                                "is_dir": False,
                                "mode": mode,
                                "action": "link",
                            },
                        )
                    )
                    results.append(
                        (
                            index,
                            f"{path}#meta",
                            merge_seconds,
                            {
                                "path": path,
                                "change_type": change_type,
                                "is_dir": False,
                                "mode": mode,
                                "action": "meta",
                            },
                        )
                    )
                    continue
                if not is_dir and suffix in rule.metadata_ext_set:
                    action = "meta"
                else:
                    action = "full"
                delay = merge_seconds
                if is_dir and change_type != "delete":
                    # 目录事件排到合并窗口之后，避免与文件级任务重复处理同一批文件
                    delay = merge_seconds + DIR_SCAN_EXTRA_SECONDS
                key = path
            else:
                scope = _scope_for(rule, path, change_type, is_dir)
                if not scope:
                    continue
                delay = dir_seconds
                key = scope
                action = "full"
            results.append(
                (
                    index,
                    key,
                    delay,
                    {
                        "path": path,
                        "change_type": change_type,
                        "is_dir": is_dir,
                        "mode": mode,
                        "action": action,
                    },
                )
            )
        return results

    def _apply_event(
        self, index: int, payload: Dict[str, Any], trigger: str
    ) -> Dict[str, Any]:
        """处理一条已合并的通知：精确模式按对象处理，目录模式按目录扫描。"""
        if not 0 <= index < len(self._rules):
            return {}
        rule = self._rules[index]
        path = str(payload.get("path") or "")
        if not path:
            return {}
        is_dir = bool(payload.get("is_dir"))
        with self._scan_lock:
            if str(payload.get("mode") or "precise") == "precise":
                stats = apply_event(
                    rule,
                    path,
                    str(payload.get("change_type") or ""),
                    is_dir,
                    str(payload.get("action") or "full"),
                    global_excludes=self._globals.get("exclude_dirs"),
                )
            else:
                stats = scan_rule(
                    rule,
                    scope=path if is_dir else str(Path(path).parent),
                    allow_remove_links=rule.on_delete_remove_link,
                    allow_remove_metadata=rule.on_delete_remove_metadata,
                    allow_remove_dirs=rule.clean_invalid_dir,
                    trigger="event",
                    global_excludes=self._globals.get("exclude_dirs"),
                )
        self._store_stats(index, stats, path)
        self._reconcile_events(index)
        self._notify_scan(rule, index, stats)
        return stats

    def _make_handler(self, label: str):
        """为某路订阅生成带来源标注的消息处理函数。"""
        return lambda message: self._on_push_message(message, label)

    def _on_push_message(self, message: Dict[str, Any], source: str = "") -> None:
        """处理一条 CloudDrive2 推送消息：先按源目录归类，再决定是否处理。"""
        change_type = str(message.get("change_type") or "")
        raw_path = str(message.get("path") or "")
        if not change_type or not raw_path:
            return
        # 媒体整理与 STRM 同步完全隔离：这里独立受理一次，命中与否都不影响下方逻辑
        self._dispatch_organize(message, source)
        # 镜像移动同样独立受理一次，三个功能互不影响
        self._dispatch_mirror(message, source)
        raw_new = str(message.get("new_path") or "")
        is_dir = bool(message.get("is_dir"))
        rule_index: Optional[int] = None
        category = "rule_miss"
        for candidate in (raw_path, raw_new):
            if not candidate:
                continue
            index, current = classify_event(
                self._rules,
                candidate,
                is_dir=is_dir,
                global_excludes=self._globals.get("exclude_dirs"),
            )
            if current == "matched":
                rule_index, category = index, current
                break
            if category == "rule_miss" and current != "rule_miss":
                rule_index, category = index, current
        rule_name = ""
        if rule_index is not None and category == "matched":
            rule_name = self._rules[rule_index].display_name(rule_index)
        # 镜像移动的回声：CD2 把「移进回收站」报成 rename，这类通知是本插件自己的动作，
        # 只登记一条可追溯记录，不再进 STRM 处理链（否则会留下永远「处理中」的幽灵行）
        own_move = (
            change_type == "rename"
            and bool(raw_new)
            and in_mirror_recycle(self._mirror_rules, self._to_container_path(raw_new))
        )
        if category == "matched" and self._dispatcher and not own_move:
            container_path = self._to_container_path(raw_path)
            new_path = self._to_container_path(raw_new) if raw_new else ""
            hit = self._dispatcher.submit(
                {
                    "change_type": change_type,
                    "is_dir": is_dir,
                    "path": container_path,
                    "new_path": new_path,
                }
            )
            if hit:
                rule_index, rule_name = hit
        self._record_event(
            change_type,
            self._to_container_path(raw_path) or raw_path,
            rule_name,
            rule_index,
            is_dir,
            source,
            category,
            self._to_container_path(raw_new) if raw_new else "",
            own_move=own_move,
        )

    def _to_container_path(self, raw_path: str) -> str:
        """把 CloudDrive2 上报路径换算成容器内路径。"""
        target = normalize_path(raw_path)
        if not target:
            return ""
        roots = self._candidate_roots()
        for root in roots:
            if target == root or target.startswith(f"{root}/"):
                return target
        fallback = ""
        for root in roots:
            candidate = f"{root}/{target.lstrip('/')}"
            if match_rule(self._rules, candidate)[0] is not None:
                return candidate
            if not fallback and Path(candidate).exists():
                fallback = candidate
        return fallback or target


    def _candidate_roots(self) -> List[str]:
        """收集规则中用到的挂载根目录，长前缀优先。"""
        roots = set()
        for rule in self._rules:
            for value in (rule.cd2_root, rule.alist_root):
                root = normalize_path(value)
                if root:
                    roots.add(root)
        return sorted(roots, key=len, reverse=True)

    def _record_event(
        self,
        change_type: str,
        container_path: str,
        rule_name: str,
        rule_index: Optional[int],
        is_dir: bool,
        source: str = "",
        category: str = "rule_miss",
        new_path: str = "",
        own_move: bool = False,
    ) -> None:
        """记录一条变更事件：命中的进「CD2 通知」，其余按类别归档。

        own_move=True 表示这是「镜像移动把对象移进回收站」的回声通知：受理即完成，
        不再进处理队列，页面上显示「移入回收站」并标注自身生成。
        """
        record = {
            "time": datetime.now().strftime("%m-%d %H:%M:%S"),
            "change_type": change_type,
            "rule": rule_name or "-",
            "rule_index": rule_index,
            "is_dir": is_dir,
            "outcome": "已受理" if rule_name else "已忽略",
            "path": container_path,
            "new_path": new_path,
            "source": source,
            "category": category,
            "internal": category == "internal" or own_move,
            "own_move": own_move,
            "done": own_move,
            "result": "已移入回收站" if own_move else "",
        }
        with self._state_lock:
            if category == "excluded":
                # 排除目录内的变更只计数，不进列表
                self._excluded_count += 1
                self._dirty = True
                return
            if rule_index is None:
                self._ignored_events.append(record)
                if len(self._ignored_events) > MAX_EVENTS:
                    self._ignored_events = self._ignored_events[-MAX_EVENTS:]
                self._ignored_count += 1
            else:
                self._events.append(record)
                if len(self._events) > MAX_EVENTS:
                    self._events = self._events[-MAX_EVENTS:]
            self._dirty = True


    def _start_scan(self, index: int, trigger: str = "manual") -> bool:
        """在后台线程中启动一次扫描，返回是否已受理。"""
        if not 0 <= index < len(self._rules):
            return False
        key = str(index)
        with self._state_lock:
            if self._scanning.get(key):
                return False
            self._scanning[key] = True
        thread = threading.Thread(
            target=self._scan_thread,
            args=(index, trigger),
            name=f"Cd2StrmScan{index}",
            daemon=True,
        )
        thread.start()
        return True

    def _scan_thread(self, index: int, trigger: str) -> None:
        """后台扫描线程入口。"""
        try:
            self._run_scan(index, "", trigger)
        finally:
            with self._state_lock:
                self._scanning[str(index)] = False

    def _run_scan(self, index: int, scope: str, trigger: str = "manual") -> Dict[str, Any]:
        """执行一次扫描并记录结果。"""
        if not 0 <= index < len(self._rules):
            return {}
        rule = self._rules[index]
        allow_links = rule.clean_invalid_link
        allow_metadata = rule.clean_invalid_metadata
        allow_dirs = rule.clean_invalid_dir
        if trigger in ("event", "command"):
            allow_links = rule.on_delete_remove_link
            allow_metadata = rule.on_delete_remove_metadata
        key = str(index)
        track_progress = trigger in ("manual", "schedule", "once")
        if track_progress:
            self._progress[key] = {"scanned": 0, "stage": "准备", "elapsed": 0.0}

        def _on_progress(payload: Dict[str, Any], key: str = key) -> None:
            """把扫描进度写入内存（仅供页面展示）。"""
            self._progress[key] = dict(payload)

        try:
            with self._scan_lock:
                stats = scan_rule(
                    rule,
                    scope=scope or None,
                    allow_remove_links=allow_links,
                    allow_remove_metadata=allow_metadata,
                    allow_remove_dirs=allow_dirs,
                    trigger=trigger,
                    progress=_on_progress if track_progress else None,
                    global_excludes=self._globals.get("exclude_dirs"),
                )
        finally:
            if track_progress:
                self._progress.pop(key, None)
        self._store_stats(index, stats)
        self._reconcile_events(index)
        self._notify_scan(rule, index, stats)
        return stats

    def _store_stats(
        self, index: int, stats: Dict[str, Any], path: str = ""
    ) -> None:
        """记录一次处理结果：自动任务的空结果不落记录，同一次通知的多个任务合并为一条。"""
        has_activity = any(int(stats.get(key) or 0) for key in ACTIVITY_KEYS) or bool(
            stats.get("created_paths") or stats.get("updated_paths")
        )
        # 自动任务（event）没有实质动作时不写记录，也不覆盖页面上一次的统计
        if str(stats.get("trigger") or "") == "event" and not has_activity and not stats.get("error"):
            return
        name = (
            self._rules[index].display_name(index)
            if 0 <= index < len(self._rules)
            else str(index)
        )
        now = time.time()
        time_text = datetime.now().strftime("%m-%d %H:%M:%S")
        seconds = float(stats.get("seconds") or 0)
        with self._state_lock:
            merged = False
            current: Dict[str, Any] = {}
            if path and self._actions:
                last = self._actions[-1]
                if (
                    last.get("rule_index") == index
                    and last.get("path") == path
                    and now - float(last.get("ts") or 0) <= ACTION_MERGE_SECONDS
                ):
                    counters = dict(last.get("counters") or {})
                    for key in COUNTER_KEYS:
                        counters[key] = int(counters.get(key, 0)) + int(stats.get(key) or 0)
                    last["counters"] = counters
                    last["files"] = _merge_files(
                        list(last.get("files") or []), _files_of(stats)
                    )
                    last["seconds"] = round(float(last.get("seconds") or 0) + seconds, 2)
                    last["time"] = time_text
                    last["ts"] = now
                    last["trigger"] = str(stats.get("trigger") or last.get("trigger") or "")
                    if stats.get("error"):
                        last["error"] = str(stats["error"])
                    last["summary"] = _format_stats(last)
                    current = last
                    merged = True
            if not merged:
                counters = {key: int(stats.get(key) or 0) for key in COUNTER_KEYS}
                current = {
                    "time": time_text,
                    "ts": now,
                    "path": path,
                    "rule": name,
                    "rule_index": index,
                    "trigger": str(stats.get("trigger") or ""),
                    "counters": counters,
                    "seconds": round(seconds, 2),
                    "error": str(stats.get("error") or ""),
                    "files": _files_of(stats),
                }
                current["summary"] = _format_stats(current)
                self._actions.append(current)
                if len(self._actions) > MAX_EVENTS:
                    self._actions = self._actions[-MAX_EVENTS:]
            self._rule_stats[str(index)] = {
                **dict(current.get("counters") or {}),
                "time": current.get("time") or "",
                "trigger": current.get("trigger") or "",
                "rule": name,
                "error": current.get("error") or "",
                "seconds": current.get("seconds") or 0,
            }
            self._dirty = True
            new_record = not merged
        self._persist_state()
        if new_record and self._notify:
            self._schedule_record_notify(current, name)

    def _reconcile_candidates(self, event: Dict[str, Any]) -> List[Path]:
        """回填用的候选对象：先事件自身路径，再改名事件的目标路径。

        CD2 的暂存/内部路径（例如 /115/media/AAA/…）在容器里并不存在，真正的落点是
        改名事件里的 new_path（媒体库里的新位置），只看 path 会让这类通知永远停在「处理中」。
        """
        candidates: List[str] = []
        for value in (event.get("path"), event.get("new_path")):
            text = str(value or "")
            if text and text not in candidates:
                candidates.append(text)
        return [Path(item) for item in candidates]

    def _reconcile_source(
        self, rule: SyncRule, event: Dict[str, Any], source: Path
    ) -> bool:
        """按一个候选路径判定该通知是否已完成；完成则回填并返回 True。"""
        suffix = source.suffix.lower()
        if suffix in rule.link_ext_set:
            target = target_path(rule, source)
            if target is not None and target.exists():
                event["done"] = True
                event["result"] = (
                    "已生成 strm" if target.suffix.lower() == ".strm" else "已生成软链接"
                )
                return True
            if event.get("change_type") == "delete" and not source.exists():
                event["done"] = True
                event["result"] = "已清理"
                return True
            return False
        if event.get("is_dir"):
            event["done"] = True
            event["result"] = "已扫描"
            return True
        if suffix in rule.metadata_ext_set:
            # 元数据按原名复制，目标与源同名；不再让这类通知永远停在「处理中」
            if not rule.update_metadata:
                event["done"] = True
                event["result"] = "跳过：未开启元数据同步"
                return True
            target = metadata_target_path(rule, source)
            if target is not None and target.exists():
                event["done"] = True
                event["result"] = "已同步元数据"
                return True
            if event.get("change_type") == "delete" and not source.exists():
                event["done"] = True
                event["result"] = "已清理"
                return True
            return False
        return False

    def _reconcile_events(self, index: int) -> None:
        """用扫描结果回填通知的完成状态，供页面显示完成标记。"""
        if not 0 <= index < len(self._rules):
            return
        rule = self._rules[index]
        changed = False
        with self._state_lock:
            for event in self._events:
                if event.get("done") or event.get("rule_index") != index:
                    continue
                for source in self._reconcile_candidates(event):
                    if self._reconcile_source(rule, event, source):
                        changed = True
                        break
            if changed:
                self._dirty = True
        if changed:
            self._persist_state()

    def _notify_scan(self, rule: SyncRule, index: int, stats: Dict[str, Any]) -> None:
        """按需推送扫描结果通知。"""
        if not self._notify:
            return
        name = rule.display_name(index)
        if stats.get("error"):
            self.post_message(
                title=f"⚠️ CD2 Strm · {name} · 扫描失败",
                text=f"❌ **扫描失败**\n📌 **原因** `{_short_text(str(stats['error']))}`",
            )
            return
        failed = _safe_int(stats.get("links_failed"), 0) + _safe_int(stats.get("metadata_failed"), 0)
        if not failed:
            return
        self.post_message(
            title=f"⚠️ CD2 Strm · {name} · 存在失败项",
            text=(
                f"❌ **失败 {failed} 项**\n"
                f"🔍 扫描 {stats.get('scanned_files', 0)} 个文件\n"
                f"- 链接失败 {stats.get('links_failed', 0)}\n"
                f"- 元数据失败 {stats.get('metadata_failed', 0)}"
            ),
        )

    def _scheduled_scan(self) -> None:
        """定时服务：对所有开启定时扫描的目录组做全量扫描。"""
        for index, rule in enumerate(self._rules):
            if not rule.schedule_enabled:
                continue
            self._run_scan(index, "", "schedule")

    def _onlyonce_scan(self) -> None:
        """保存配置后的一次性全量扫描，执行完自动把开关复位为关闭。"""
        if not self._globals.get("onlyonce"):
            return
        try:
            for index in range(len(self._rules)):
                self._run_scan(index, "", "once")
        finally:
            self._consume_onlyonce()

    def _consume_onlyonce(self) -> None:
        """把「保存后立即执行一次」复位为关闭并落盘。"""
        self._globals["onlyonce"] = False
        try:
            config = dict(self.get_config() or {})
            if not config.get("onlyonce"):
                return
            config["onlyonce"] = False
            self.update_config(config)
            logger.info("「保存后立即执行一次」已执行，开关自动复位为关闭")
        except Exception as err:  # pylint: disable=broad-except
            logger.warning(f"复位「保存后立即执行一次」失败：{err}")

    def _health_check(self) -> None:
        """健康检查：订阅线程掉线时重新拉起，并定期落盘状态。"""
        for index, subscriber in enumerate(self._subscribers):
            if subscriber.status().get("running"):
                continue
            label = (
                self._connections[index]["label"]
                if index < len(self._connections)
                else f"地址 {index + 1}"
            )
            logger.warning(f"CloudDrive2 订阅线程已退出（{label}），正在重新拉起")
            subscriber.start()
        self._persist_state()

    def _status_snapshot(self) -> Dict[str, Any]:
        """汇总运行状态供详情页展示（支持多路订阅）。"""
        dispatcher = self._dispatcher.status() if self._dispatcher else {}
        connections: List[Dict[str, Any]] = []
        total_messages = 0
        last_at = 0.0
        last_error = self._last_error
        for index, subscriber in enumerate(self._subscribers):
            data = subscriber.status()
            label = (
                self._connections[index]["label"]
                if index < len(self._connections)
                else f"地址 {index + 1}"
            )
            connections.append(
                {
                    "label": label,
                    "host": (
                        str(self._connections[index].get("host") or "")
                        if index < len(self._connections)
                        else ""
                    ),
                    "connected": bool(data.get("connected")),
                    "message_count": int(data.get("message_count") or 0),
                }
            )
            total_messages += int(data.get("message_count") or 0)
            last_at = max(last_at, float(data.get("last_message_at") or 0))
            if not last_error and data.get("last_error"):
                last_error = str(data["last_error"])
        with self._state_lock:
            scanning = sum(1 for value in self._scanning.values() if value)
        schedule_text = "已关闭"
        if self._globals.get("global_schedule_enabled"):
            schedule_text = f"每 {self._globals.get('global_schedule_hours', 6)} 小时"
        return {
            "enabled": self._enabled,
            "connected": bool(connections) and all(item["connected"] for item in connections),
            "connections": connections,
            "message_count": total_messages,
            "last_message_at": _format_time(last_at),
            "pending": dispatcher.get("pending", 0),
            "accepted": dispatcher.get("accepted", 0),
            "ignored": dispatcher.get("ignored", 0),
            "scanning": scanning,
            "schedule_text": schedule_text,
            "last_error": last_error,
        }

    def _save_rules(self, rules: List[SyncRule]) -> None:
        """把规则写回插件配置并同步内存状态。"""
        config = dict(self.get_config() or {})
        for key in [item for item in config if RULE_KEY_PATTERN.match(str(item))]:
            config.pop(key, None)
        config.update(build_all_rule_config(rules))
        self.update_config(config)
        self._rules = rules

    def _restore_state(self) -> None:
        """从插件数据中恢复统计与事件。"""
        try:
            data = self.get_data("state") or {}
        except Exception as err:  # pylint: disable=broad-except
            logger.warning(f"读取插件状态失败：{err}")
            data = {}
        if isinstance(data, dict):
            self._rule_stats = data.get("rule_stats") or {}
            self._events = data.get("events") or []
            self._ignored_events = data.get("ignored_events") or []
            self._ignored_count = int(data.get("ignored_count") or 0)
            self._excluded_count = int(data.get("excluded_count") or 0)
            self._actions = data.get("actions") or []
            display = data.get("display") or {}
            if isinstance(display, dict):
                self._display = {
                    "page_size": max(5, _safe_int(display.get("page_size"), 5)),
                    "pages": display.get("pages") or {},
                }
            self._organize_stats = data.get("organize_stats") or {}
            self._organize_records = data.get("organize_records") or []
            self._organize_ignored = data.get("organize_ignored") or []
            self._organize_events = data.get("organize_events") or []
            self._mirror_stats = data.get("mirror_stats") or {}
            self._mirror_records = data.get("mirror_records") or []
            self._mirror_ignored = data.get("mirror_ignored") or []
            self._mirror_events = data.get("mirror_events") or []
            view = str(data.get("active_view") or "sync")
            self._active_view = view if view in ("sync", "organize", "mirror") else "sync"

    def _persist_state(self) -> None:
        """把统计与事件写入插件数据。"""
        with self._state_lock:
            if not self._dirty:
                return
            payload = {
                "rule_stats": dict(self._rule_stats),
                "events": list(self._events),
                "ignored_events": list(self._ignored_events),
                "ignored_count": self._ignored_count,
                "excluded_count": self._excluded_count,
                "actions": list(self._actions),
                "display": dict(self._display),
                "organize_stats": dict(self._organize_stats),
                "organize_records": list(self._organize_records),
                "organize_ignored": list(self._organize_ignored),
                "organize_events": list(self._organize_events),
                "mirror_stats": dict(self._mirror_stats),
                "mirror_records": list(self._mirror_records),
                "mirror_ignored": list(self._mirror_ignored),
                "mirror_events": list(self._mirror_events),
                "active_view": self._active_view,
            }
            self._dirty = False
        try:
            self.save_data("state", payload)
        except Exception as err:  # pylint: disable=broad-except
            logger.warning(f"保存插件状态失败：{err}")

    def _release_runtime(self) -> None:
        """清空运行时引用。"""
        self._stop_organize_worker()
        self._stop_mirror_worker()
        self._dispatcher = None
        self._subscribers = []
        self._client_close()

    def _client_close(self) -> None:
        """关闭全部 CloudDrive2 客户端。"""
        for client in self._clients:
            client.close()
        self._clients = []

    def _schedule_record_notify(self, record: Dict[str, Any], rule_name: str) -> None:
        """等合并窗口过去后再推送该条操作记录（保证内容已定型）。"""
        timer = threading.Timer(
            ACTION_MERGE_SECONDS + 1.0,
            self._notify_record,
            args=(record, rule_name),
        )
        timer.daemon = True
        timer.start()

    def _notify_record(self, record: Dict[str, Any], rule_name: str) -> None:
        """把一条已定型的操作记录推送到 MoviePilot 通知渠道（含绑定的 Telegram）。"""
        if not self._notify or not isinstance(record, dict):
            return
        error = str(record.get("error") or "")
        counters = dict(record.get("counters") or {})
        created = int(counters.get("links_created", 0))
        updated = int(counters.get("links_updated", 0))
        skipped = int(counters.get("links_skipped", 0))
        failed = int(counters.get("links_failed", 0))
        cleaned = (
            int(counters.get("removed_links", 0))
            + int(counters.get("removed_metadata", 0))
            + int(counters.get("removed_dirs", 0))
        )
        title = f"⚠️ CD2 Strm · {rule_name} · 失败" if error else f"🎬 CD2 Strm · {rule_name}"
        if error:
            lines = [f"❌ **失败 {failed}** · 新增 {created} · 跳过 {skipped}"]
        else:
            lines = [f"📊 **新增 {created} · 更新 {updated} · 跳过 {skipped} · 失败 {failed}**"]
        lines.append(
            f"🔍 扫描 {int(counters.get('scanned_files', 0))}"
            f" · 🗂 元数据 {int(counters.get('metadata_copied', 0))}"
            f" · 🧹 清理 {cleaned}"
            f" · ⏱ {record.get('seconds', 0)}s"
        )
        files = list(record.get("files") or [])
        if files:
            new_files = [item for item in files if str(item).startswith("生成 ")]
            changed_files = [item for item in files if str(item).startswith("更新 ")]
            if new_files and changed_files:
                head = f"生成 {len(new_files)} · 更新 {len(changed_files)} 个文件"
            elif changed_files:
                head = f"更新 {len(changed_files)} 个文件"
            else:
                head = f"生成 {len(new_files)} 个文件"
            lines.append("")
            lines.append(f"📄 **{head}**")
            for item in files[:3]:
                lines.append(f"- `{_file_name(_strip_file_prefix(item))}`")
            if len(files) > 3:
                lines.append(f"- 其余 {len(files) - 3} 条见插件页面")
        if error:
            lines.append("")
            lines.append(f"📌 **原因** `{_short_text(error)}`")
        if record.get("path"):
            lines.append("")
            lines.append(f"📁 `{_short_path(str(record['path']))}`")
        try:
            self.post_message(title=title, text="\n".join(lines))
        except Exception as err:  # pylint: disable=broad-except
            logger.warning(f"发送操作记录通知失败：{err}")
