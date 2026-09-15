"""目录规则的数据结构与配置编解码。"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 默认生成链接的媒体后缀（分号分隔，与配置页展示一致）
DEFAULT_LINK_EXTS = ".mkv;.iso;.ts;.mp4;.avi;.rmvb;.wmv;.m2ts;.mpg;.flv;.rm;.mov"
# 默认同步的元数据后缀
DEFAULT_METADATA_EXTS = ".nfo;.ass;.ssa;.srt;.sup"
# 默认 strm 内容模板，占位符：{host}、{path}（URL 编码后的云盘路径）、{raw}（未编码云盘路径）、{local}（容器路径）
DEFAULT_STRM_TEMPLATE = "http://{host}/static/http/{host}/False/{path}"

# 单条规则的配置键前缀：r{index}_{字段名}
RULE_KEY_PREFIX = "r"

# 全局排除目录：gx_<序号>（对所有目录组生效）
GLOBAL_EXCLUDE_PREFIX = "gx_"

MAX_GLOBAL_EXCLUDES = 10
# 规则数量上限，避免配置页被误填的巨大数字撑爆
MAX_RULES = 20

# 整理组的配置键前缀：o{index}_{字段名}
ORGANIZE_KEY_PREFIX = "o"
# 整理组数量上限
MAX_ORGANIZE_RULES = 20

# 功能三：完全镜像（监听目录 → 镜像目录 → 回收站）
MIRROR_KEY_PREFIX = "d"

MAX_MIRROR_RULES = 20


@dataclass
class SyncRule:
    """一组「源目录 → 目的目录」的完整设置。"""

    # 文件夹设置
    name: str = ""
    enabled: bool = True
    media_dir: str = ""
    local_dir: str = ""
    exclude_dirs: str = ""
    # 同步功能
    update_link: bool = True
    update_metadata: bool = True
    metadata_overwrite: bool = False
    metadata_skip: bool = False
    metadata_mode: str = "local"
    # 处理方式：precise＝按通知处理单个对象；scan＝在受影响目录内做全量比对
    process_mode: str = "precise"
    # 清除功能
    clean_invalid_dir: bool = True
    clean_invalid_link: bool = True
    clean_invalid_metadata: bool = True
    # 删除时的联动行为（改名按「新路径=新增、旧路径=删除」处理，故不需要独立开关）
    on_delete_remove_link: bool = True
    on_delete_remove_metadata: bool = True
    # 软链接配置
    link_mode: str = "strm"
    strm_mode: str = "cloud"
    strm_template: str = DEFAULT_STRM_TEMPLATE
    link_min_size: int = 0
    mount_type: str = "cd2"
    cloud_host: str = ""
    cd2_root: str = "/mnt/cd2-mount"
    alist_root: str = ""
    link_exts: str = DEFAULT_LINK_EXTS
    metadata_exts: str = DEFAULT_METADATA_EXTS
    # 定时扫描
    schedule_enabled: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """转换为普通字典。"""
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "SyncRule":
        """由字典构造规则，未知键忽略、缺失键取默认值。"""
        if not data:
            return cls()
        known = {item.name for item in dataclasses.fields(cls)}
        payload = {key: value for key, value in data.items() if key in known}
        return cls(**payload)

    def clone(self) -> "SyncRule":
        """复制一份规则，用于详情页的「复制这一组」。"""
        copied = SyncRule.from_dict(self.to_dict())
        copied.name = f"{self.name} 副本" if self.name else "副本"
        return copied

    @property
    def exclude_list(self) -> List[str]:
        """排除目录列表（换行或分号分隔）。"""
        return _split_paths(self.exclude_dirs)

    @property
    def link_ext_set(self) -> set[str]:
        """生成链接的后缀集合（小写，含点）。"""
        return _split_exts(self.link_exts)

    @property
    def metadata_ext_set(self) -> set[str]:
        """同步元数据的后缀集合（小写，含点）。"""
        return _split_exts(self.metadata_exts)

    def is_active(self) -> bool:
        """判断规则当前是否参与处理：该组已启用且配置完整。"""
        return bool(self.enabled) and self.is_ready()

    def is_ready(self) -> bool:
        """判断规则是否具备执行条件。"""
        return bool(self.media_dir.strip()) and bool(self.local_dir.strip())

    def display_name(self, index: int) -> str:
        """用于页面与日志展示的名称。"""
        return self.name.strip() or f"目录组 {index + 1}"


@dataclass
class OrganizeRule:
    """一组「整理源目录 → 整理目的目录」的设置。

    整理功能与 STRM 同步完全隔离：各自规则、各自开关与统计，仅共用 CD2 通知。
    """

    # 目录设置
    name: str = ""
    enabled: bool = True
    src: str = ""
    dst: str = ""
    cd2_root: str = "/mnt/cd2-mount"
    exclude_dirs: str = ""
    # 插件自身行为
    notify: bool = False
    # 说明：整理模式、刮削、类型目录、分类目录、重命名、同名覆盖一律由命中的
    # MoviePilot「目录配置」决定，本插件不再提供这些设置。

    def to_dict(self) -> Dict[str, Any]:
        """转换为普通字典。"""
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "OrganizeRule":
        """由字典构造整理组，未知键忽略、缺失键取默认值。"""
        if not data:
            return cls()
        known = {item.name for item in dataclasses.fields(cls)}
        payload = {key: value for key, value in data.items() if key in known}
        return cls(**payload)

    def clone(self) -> "OrganizeRule":
        """复制一份整理组，用于详情页的「复制这一组」。"""
        copied = OrganizeRule.from_dict(self.to_dict())
        copied.name = f"{self.name} 副本" if self.name else "副本"
        return copied

    @property
    def exclude_list(self) -> List[str]:
        """排除目录列表（换行或分号分隔）。"""
        return _split_paths(self.exclude_dirs)

    def is_active(self) -> bool:
        """判断整理组当前是否参与处理：已启用且配置完整。"""
        return bool(self.enabled) and self.is_ready()

    def is_ready(self) -> bool:
        """判断整理组是否具备执行条件。"""
        return bool(self.src.strip()) and bool(self.dst.strip())

    def display_name(self, index: int) -> str:
        """用于页面与日志展示的名称。"""
        return self.name.strip() or f"整理组 {index + 1}"


@dataclass
class MirrorRule:
    """一组「监听目录 → 镜像目录 → 回收站」的完全镜像设置。

    完全镜像：监听目录里删除什么（文件或目录），就把镜像目录里对应的对象**移到回收站**，
    使监听目录与镜像目录保持镜像；保护白名单命中的对象留在镜像目录不移动。
    """

    # 目录设置（回收站每组单独设置）
    name: str = ""
    enabled: bool = False
    path1: str = ""
    path2: str = ""
    path3: str = ""
    cd2_root: str = "/mnt/cd2-mount"
    # 仅用于把监听目录的 .strm 换算成镜像目录中的视频文件，不参与保护判定
    media_exts: str = DEFAULT_LINK_EXTS
    # 保护白名单：文件夹名 / 无后缀文件名 / .后缀 / 文件名+后缀，命中的对象不移动
    protect: str = ""
    notify: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """转换为普通字典。"""
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "MirrorRule":
        """由字典构造镜像组，未知键忽略、缺失键取默认值。"""
        if not data:
            return cls()
        known = {item.name for item in dataclasses.fields(cls)}
        payload = {key: value for key, value in data.items() if key in known}
        return cls(**payload)

    def clone(self) -> "MirrorRule":
        """复制一份镜像组，用于详情页的「复制这一组」。"""
        copied = MirrorRule.from_dict(self.to_dict())
        copied.name = f"{self.name} 副本" if self.name else "副本"
        return copied

    @property
    def protect_list(self) -> List[str]:
        """保护白名单条目（换行或分号分隔）。"""
        return _split_paths(self.protect)

    @property
    def media_ext_set(self) -> set[str]:
        """把 .strm 换算成视频时使用的后缀集合（小写，含点）。"""
        return _split_exts(self.media_exts)

    def is_active(self) -> bool:
        """判断镜像组当前是否参与处理：已启用且三项路径齐全。"""
        return bool(self.enabled) and self.is_ready()

    def is_ready(self) -> bool:
        """判断镜像组是否具备执行条件（监听目录 / 镜像目录 / 回收站都要填写）。"""
        return bool(self.path1.strip()) and bool(self.path2.strip()) and bool(self.path3.strip())

    def display_name(self, index: int) -> str:
        """用于页面与日志展示的名称。"""
        return self.name.strip() or f"镜像组 {index + 1}"


def to_organize_internal(rule: "OrganizeRule", path: str) -> str:
    """把容器路径换算成整理内部路径（去掉 cd2 根目录前缀）。

    与 STRM 侧的 to_internal_path 同一口径：CD2 通知里的路径本身就是云盘内部路径
    （例如 /115/media/...），因此去掉 cd2 根目录后即可直接前缀比较。cd2_root 为空时
    原样返回，退化为「容器路径对容器路径」的旧行为。
    """
    target = normalize_path(path)
    if not target:
        return ""
    root = normalize_path(rule.cd2_root)
    if not root:
        return target
    if target == root:
        return "/"
    if target.startswith(f"{root}/"):
        return target[len(root) :] or "/"
    return target


def _split_paths(value: str) -> List[str]:
    """把多行或多段文本拆成路径列表。"""
    if not value:
        return []
    items: List[str] = []
    for chunk in str(value).replace(";", "\n").splitlines():
        item = chunk.strip()
        if item:
            items.append(item.rstrip("/"))
    return items


def _split_exts(value: str) -> set[str]:
    """把分号分隔的后缀文本拆成小写集合。"""
    result: set[str] = set()
    if not value:
        return result
    for chunk in str(value).replace(",", ";").split(";"):
        item = chunk.strip().lower()
        if not item:
            continue
        result.add(item if item.startswith(".") else f".{item}")
    return result


def rule_key(index: int, field_name: str) -> str:
    """生成某条规则某个字段在扁平配置中的键名。"""
    return f"{RULE_KEY_PREFIX}{index}_{field_name}"


def parse_rules(config: Optional[Dict[str, Any]]) -> List[SyncRule]:
    """从插件配置中解析全部规则，保持顺序与占位空组。"""
    if not config:
        return []
    count = _safe_int(config.get("rule_count"), default=0)
    count = max(0, min(count, MAX_RULES))
    rules: List[SyncRule] = []
    for index in range(count):
        payload = {
            item.name: config.get(rule_key(index, item.name))
            for item in dataclasses.fields(SyncRule)
            if rule_key(index, item.name) in config
        }
        rules.append(SyncRule.from_dict(payload))
    return rules


def build_rule_config(index: int, rule: SyncRule) -> Dict[str, Any]:
    """把一条规则摊平成配置键。"""
    return {rule_key(index, key): value for key, value in rule.to_dict().items()}


def build_all_rule_config(rules: List[SyncRule]) -> Dict[str, Any]:
    """把全部规则摊平成配置键，并同步 rule_count。"""
    payload: Dict[str, Any] = {"rule_count": len(rules)}
    for index, rule in enumerate(rules):
        payload.update(build_rule_config(index, rule))
    return payload


def organize_key(index: int, field_name: str) -> str:
    """生成某个整理组某个字段在扁平配置中的键名。"""
    return f"{ORGANIZE_KEY_PREFIX}{index}_{field_name}"


def parse_organize_rules(config: Optional[Dict[str, Any]]) -> List[OrganizeRule]:
    """从插件配置中解析全部整理组，保持顺序与占位空组。"""
    if not config:
        return []
    count = _safe_int(config.get("organize_count"), default=0)
    count = max(0, min(count, MAX_ORGANIZE_RULES))
    rules: List[OrganizeRule] = []
    for index in range(count):
        payload = {
            item.name: config.get(organize_key(index, item.name))
            for item in dataclasses.fields(OrganizeRule)
            if organize_key(index, item.name) in config
        }
        rules.append(OrganizeRule.from_dict(payload))
    return rules


def build_organize_config(index: int, rule: OrganizeRule) -> Dict[str, Any]:
    """把一个整理组摊平成配置键。"""
    return {organize_key(index, key): value for key, value in rule.to_dict().items()}


def build_all_organize_config(rules: List[OrganizeRule]) -> Dict[str, Any]:
    """把全部整理组摊平成配置键，并同步 organize_count。"""
    payload: Dict[str, Any] = {"organize_count": len(rules)}
    for index, rule in enumerate(rules):
        payload.update(build_organize_config(index, rule))
    return payload


def parse_organize_globals(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """解析媒体整理的全局开关。"""
    config = config or {}
    return {
        "organize_enabled": bool(config.get("organize_enabled")),
        "organize_notify": bool(config.get("organize_notify")),
    }


def mirror_key(index: int, field_name: str) -> str:
    """生成某个镜像组某个字段在扁平配置中的键名。"""
    return f"{MIRROR_KEY_PREFIX}{index}_{field_name}"


def parse_mirror_rules(config: Optional[Dict[str, Any]]) -> List[MirrorRule]:
    """从插件配置中解析全部镜像组，保持顺序与占位空组。"""
    if not config:
        return []
    count = _safe_int(config.get("mirror_count"), default=0)
    count = max(0, min(count, MAX_MIRROR_RULES))
    rules: List[MirrorRule] = []
    for index in range(count):
        payload = {
            item.name: config.get(mirror_key(index, item.name))
            for item in dataclasses.fields(MirrorRule)
            if mirror_key(index, item.name) in config
        }
        rules.append(MirrorRule.from_dict(payload))
    return rules


def build_mirror_config(index: int, rule: MirrorRule) -> Dict[str, Any]:
    """把一个镜像组摊平成配置键。"""
    return {mirror_key(index, key): value for key, value in rule.to_dict().items()}


def build_all_mirror_config(rules: List[MirrorRule]) -> Dict[str, Any]:
    """把全部镜像组摊平成配置键，并同步 mirror_count。"""
    payload: Dict[str, Any] = {"mirror_count": len(rules)}
    for index, rule in enumerate(rules):
        payload.update(build_mirror_config(index, rule))
    return payload


def parse_mirror_globals(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """解析镜像移动的全局开关（预演模式默认开启）。"""
    config = config or {}
    return {
        "mirror_enabled": bool(config.get("mirror_enabled")),
        "mirror_notify": bool(config.get("mirror_notify")),
        "mirror_dry_run": bool(config.get("mirror_dry_run", True)),
    }


def parse_globals(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """解析全局设置（连接、去抖、定时扫描等）。"""
    config = config or {}
    return {
        "enabled": bool(config.get("enabled")),
        "cd2_host": str(config.get("cd2_host") or "").strip(),
        "cd2_token": str(config.get("cd2_token") or "").strip(),
        "cd2_enabled": bool(config.get("cd2_enabled", True)),
        "cd2_host2": str(config.get("cd2_host2") or "").strip(),
        "cd2_token2": str(config.get("cd2_token2") or "").strip(),
        "cd2_enabled2": bool(config.get("cd2_enabled2", True)),
        "notify_only_matched": bool(config.get("notify_only_matched", False)),
        "notify": bool(config.get("notify")),
        "debounce_seconds": max(0, min(_safe_int(config.get("debounce_seconds"), default=5), 600)),
        "merge_seconds": max(0, min(_safe_int(config.get("merge_seconds"), default=2), 60)),
        "global_schedule_enabled": bool(config.get("global_schedule_enabled")),
        "global_schedule_hours": max(1, min(_safe_int(config.get("global_schedule_hours"), default=6), 168)),
        "onlyonce": bool(config.get("onlyonce")),
        # 全局排除目录：命中的路径不生成 strm、不同步元数据（对所有目录组生效）
        "exclude_dirs": parse_global_excludes(config),
    }


def parse_global_excludes(config: Optional[Dict[str, Any]]) -> List[str]:
    """解析全局排除目录（gx_1 … gx_10，只取可见行内的非空值）。"""
    if not config:
        return []
    count = max(
        0, min(_safe_int(config.get("exclude_row_count"), default=1), MAX_GLOBAL_EXCLUDES)
    )
    items: List[str] = []
    for index in range(1, count + 1):
        value = str(config.get(f"{GLOBAL_EXCLUDE_PREFIX}{index}") or "").strip()
        if value:
            items.append(value.rstrip("/"))
    return items


def default_config() -> Dict[str, Any]:
    """返回配置页默认值（含一个空白规则组）。"""
    payload: Dict[str, Any] = {
        "enabled": False,
        "cd2_host": "http://172.17.0.1:19798",
        "cd2_token": "",
        "cd2_enabled": True,
        "cd2_host2": "",
        "cd2_token2": "",
        "cd2_enabled2": True,
        "notify_only_matched": False,
        "notify": True,
        "debounce_seconds": 5,
        "merge_seconds": 2,
        "global_schedule_enabled": False,
        "global_schedule_hours": 6,
        "onlyonce": False,
        "exclude_row_count": 1,
        "rule_count": 1,
        "config_view": "sync",
        "organize_enabled": False,
        "organize_notify": False,
        "organize_count": 1,
        "mirror_enabled": False,
        "mirror_notify": False,
        "mirror_dry_run": True,
        "mirror_count": 1,
    }
    payload.update(
        {
            f"{GLOBAL_EXCLUDE_PREFIX}{index}": ""
            for index in range(1, MAX_GLOBAL_EXCLUDES + 1)
        }
    )
    payload.update(build_rule_config(0, SyncRule()))
    payload.update(build_organize_config(0, OrganizeRule()))
    payload.update(build_mirror_config(0, MirrorRule()))
    return payload


def _safe_int(value: Any, default: int = 0) -> int:
    """把任意值安全转换为整数。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_path(value: str) -> str:
    """规范化路径文本：反斜杠统一为斜杠、折叠重复斜杠、去空白与结尾斜杠。

    CD2 的推送里偶发 Windows 风格路径（如 `/115/media/AAA中转站\\某片`），
    不统一分隔符会导致前缀匹配失败，因此这里统一处理。
    """
    if not value:
        return ""
    text = str(value).strip().replace("\\", "/")
    while "//" in text:
        text = text.replace("//", "/")
    if text == "/":
        return "/"
    return text.rstrip("/")


def build_connections(globals_conf: Dict[str, Any]) -> List[Dict[str, str]]:
    """组装 CD2 连接列表：只保留已启用且地址与令牌齐全的条目。"""
    pairs = (
        (
            "地址 1",
            globals_conf.get("cd2_host"),
            globals_conf.get("cd2_token"),
            globals_conf.get("cd2_enabled", True),
        ),
        (
            "地址 2",
            globals_conf.get("cd2_host2"),
            globals_conf.get("cd2_token2"),
            globals_conf.get("cd2_enabled2", True),
        ),
    )
    profiles: List[Dict[str, str]] = []
    for label, host, token, enabled in pairs:
        if not enabled:
            continue
        host_text = str(host or "").strip()
        token_text = str(token or "").strip()
        if not host_text or not token_text:
            continue
        profiles.append({"label": label, "host": host_text, "token": token_text})
    return profiles


def match_rule(rules: List[SyncRule], container_path: str) -> Tuple[Optional[int], Optional[str]]:
    """找出容器路径归属的规则与相对路径，最长前缀优先。"""
    target = normalize_path(container_path)
    if not target:
        return None, None
    best_index: Optional[int] = None
    best_relative = ""
    for index, rule in enumerate(rules):
        root = normalize_path(rule.media_dir)
        if not root or not rule.is_active():
            continue
        if target == root:
            relative = ""
        elif target.startswith(f"{root}/"):
            relative = target[len(root) + 1 :]
        else:
            continue
        if best_index is None or len(root) > len(normalize_path(rules[best_index].media_dir)):
            best_index = index
            best_relative = relative
    return best_index, best_relative


def is_excluded(rule: SyncRule, container_path: str) -> bool:
    """判断路径是否落在排除目录内。"""
    target = normalize_path(container_path)
    for item in rule.exclude_list:
        if target == item or target.startswith(f"{item}/"):
            return True
    # 目的目录若落在源目录内，视为排除，避免插件自身产物被再次当成源文件处理
    media_root = normalize_path(rule.media_dir)
    local_root = normalize_path(rule.local_dir)
    if (
        media_root
        and local_root
        and local_root != media_root
        and local_root.startswith(f"{media_root}/")
        and (target == local_root or target.startswith(f"{local_root}/"))
    ):
        return True
    return False


def has_nested_target(rule: SyncRule) -> bool:
    """判断目的目录是否落在源目录内（会形成自反馈循环，需要提示）。"""
    media_root = normalize_path(rule.media_dir)
    local_root = normalize_path(rule.local_dir)
    if not media_root or not local_root or local_root == media_root:
        return False
    return local_root.startswith(f"{media_root}/")


def to_internal_path(rule: SyncRule, container_path: str) -> str:
    """把容器路径换算成 CD2 内部路径（去掉挂载根前缀）。"""
    target = normalize_path(container_path)
    if not target:
        return ""
    for root in (rule.cd2_root, rule.alist_root):
        normalized = normalize_path(root)
        if normalized and (target == normalized or target.startswith(f"{normalized}/")):
            return target[len(normalized) :] or "/"
    return target


def _match_internal(rules: List[SyncRule], raw_path: str) -> Optional[int]:
    """按 CD2 内部路径前缀找出最长匹配的规则下标。"""
    best: Optional[int] = None
    best_length = -1
    for index, rule in enumerate(rules):
        if not rule.is_active():
            continue
        source = to_internal_path(rule, rule.media_dir)
        if not source:
            continue
        if raw_path == source or raw_path.startswith(f"{source}/"):
            if len(source) > best_length:
                best, best_length = index, len(source)
    return best


def classify_event(
    rules: List[SyncRule],
    raw_path: str,
    is_dir: bool = False,
    global_excludes: Optional[List[str]] = None,
) -> Tuple[Optional[int], str]:
    """按七档顺序把一条 CD2 变更归类，返回（规则下标，类别）。

    类别取值：matched（命中，需处理）/ excluded（排除目录，仅计数）/
    internal（自身产物）/ whitelist_miss（白名单外）/ rule_miss（规则外）。
    判定一律基于 CD2 内部路径，不依赖文件是否仍然存在。

    全局排除目录（global_excludes）优先于一切：命中的路径一律归为 excluded，
    只计数、不生成 strm、不同步元数据。
    """
    target = normalize_path(raw_path)
    if not target:
        return None, "rule_miss"
    for item in global_excludes or []:
        normalized = normalize_path(str(item))
        if normalized and (target == normalized or target.startswith(f"{normalized}/")):
            return None, "excluded"
    for rule in rules:
        if not rule.is_active():
            continue
        candidates = [
            *rule.exclude_list,
            *[to_internal_path(rule, item) for item in rule.exclude_list],
        ]
        for item in candidates:
            if item and (target == item or target.startswith(f"{item}/")):
                return None, "excluded"
    for rule in rules:
        if not rule.is_active():
            continue
        dest = to_internal_path(rule, rule.local_dir)
        if dest and (target == dest or target.startswith(f"{dest}/")):
            return None, "internal"
    index = _match_internal(rules, target)
    if index is None:
        return None, "rule_miss"
    rule = rules[index]
    if is_dir:
        return index, "matched"
    suffix = Path(target).suffix.lower()
    if suffix in rule.link_ext_set or suffix in rule.metadata_ext_set:
        return index, "matched"
    name = target.rsplit("/", 1)[-1]
    if name.startswith("."):
        return None, "internal"
    return None, "whitelist_miss"
