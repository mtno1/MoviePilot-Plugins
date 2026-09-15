"""strm/软链接生成、元数据同步、无效项清理与事件去抖调度。"""

from __future__ import annotations

import os
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from urllib.parse import quote

import requests

from .cd2web import build_static_url
from .rules import (
    DEFAULT_STRM_TEMPLATE,
    SyncRule,
    is_excluded,
    match_rule,
    normalize_path,
    to_organize_internal,
)

try:  # 宿主 v3 的日志入口
    from app.sdk.logging import logger
except Exception:  # pragma: no cover - 兼容旧入口
    from app.log import logger

# 单次扫描在记录里回报的文件名条数上限
MAX_REPORT_PATHS = 20


def atomic_write_text(path: Path, text: str) -> None:
    """原子写入文本，避免读取端读到半截文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    with open(temp, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.replace(temp, path)


def relative_posix(root: Path, target: Path) -> str:
    """返回相对根目录的 POSIX 风格路径，失败时返回原路径。"""
    try:
        return target.relative_to(root).as_posix()
    except ValueError:
        return target.as_posix()


def metadata_changed(source: Path, target: Path) -> bool:
    """判断元数据目标是否与源不同：先比大小，小文件再比内容，大文件退化为大小+时间。"""
    try:
        source_stat = source.stat()
        target_stat = target.stat()
    except OSError:
        return True
    if source_stat.st_size != target_stat.st_size:
        return True
    if source_stat.st_size > 2 * 1024 * 1024:
        return abs(source_stat.st_mtime - target_stat.st_mtime) > 1
    try:
        return source.read_bytes() != target.read_bytes()
    except OSError:
        return True


def should_overwrite_metadata(rule: SyncRule, source: Path, target: Path) -> bool:
    """按「元数据跳过 / 元数据覆盖」开关判断已存在的目标是否要重写。"""
    if rule.metadata_skip:
        return False
    if not rule.metadata_overwrite:
        return False
    return metadata_changed(source, target)


def related_metadata(rule: SyncRule, video: Path) -> List[Path]:
    """列出与某个视频同名的元数据文件（影片.nfo / 影片.srt / 影片-poster.jpg 等）。"""
    extensions = rule.metadata_ext_set
    if not extensions:
        return []
    stem = video.stem
    try:
        siblings = list(video.parent.iterdir())
    except OSError:
        return []
    return [
        item
        for item in siblings
        if item.is_file() and item.suffix.lower() in extensions and item.name.startswith(stem)
    ]


def cloud_path_of(rule: SyncRule, container_path: str) -> str:
    """把容器内路径换算成云盘路径。"""
    target = normalize_path(container_path)
    if rule.mount_type == "cd2" and rule.cd2_root:
        root = normalize_path(rule.cd2_root)
        if target.startswith(root):
            return target[len(root) :] or "/"
    if rule.mount_type == "alist" and rule.alist_root:
        root = normalize_path(rule.alist_root)
        if target.startswith(root):
            return target[len(root) :] or "/"
    return target


def build_strm_content(rule: SyncRule, container_path: str) -> str:
    """按规则生成 strm 文件内容。"""
    if rule.strm_mode == "local":
        return normalize_path(container_path)
    cloud_path = cloud_path_of(rule, container_path)
    template = (rule.strm_template or "").strip() or DEFAULT_STRM_TEMPLATE
    try:
        return template.format(
            host=rule.cloud_host.strip(),
            path=quote(cloud_path, safe=""),
            raw=cloud_path,
            local=normalize_path(container_path),
        )
    except (KeyError, IndexError, ValueError):
        logger.warning(f"strm 模板不合法，已回退默认模板：{template}")
        return DEFAULT_STRM_TEMPLATE.format(
            host=rule.cloud_host.strip(), path=quote(cloud_path, safe="")
        )


def target_path(rule: SyncRule, source: Path) -> Optional[Path]:
    """计算某个源文件在目的目录中的目标路径。"""
    media_root = Path(normalize_path(rule.media_dir))
    try:
        relative = source.relative_to(media_root)
    except ValueError:
        return None
    base = Path(normalize_path(rule.local_dir)) / relative
    if rule.link_mode == "symlink":
        return base
    if base.suffix.lower() == ".strm":
        return base
    return base.with_suffix(".strm")


def ensure_link(rule: SyncRule, source: Path) -> Tuple[str, Optional[Path]]:
    """生成或更新一个 strm / 软链接，返回（结果，目标路径）。"""
    target = target_path(rule, source)
    if target is None:
        return "skipped", None
    if rule.link_mode == "symlink":
        return _ensure_symlink(rule, source, target)
    return _ensure_strm(rule, source, target)


def _ensure_strm(rule: SyncRule, source: Path, target: Path) -> Tuple[str, Optional[Path]]:
    """写入 strm 文件，内容一致时不改动。"""
    content = build_strm_content(rule, str(source))
    if target.is_file() and not target.is_symlink():
        try:
            current = target.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            current = ""
        if current == content:
            return "skipped", target
        if not rule.update_link:
            return "skipped", target
        atomic_write_text(target, content)
        return "updated", target
    atomic_write_text(target, content)
    return "created", target


def _ensure_symlink(rule: SyncRule, source: Path, target: Path) -> Tuple[str, Optional[Path]]:
    """创建指向源文件的符号链接，指向一致时不改动。"""
    if target.is_symlink():
        try:
            current = os.readlink(target)
        except OSError:
            current = ""
        if normalize_path(current) == normalize_path(str(source)):
            return "skipped", target
        if not rule.update_link:
            return "skipped", target
        _replace_symlink(source, target)
        return "updated", target
    if target.exists():
        if not rule.update_link:
            return "skipped", target
        target.unlink()
    _replace_symlink(source, target)
    return "created", target


def _replace_symlink(source: Path, target: Path) -> None:
    """原子替换符号链接。"""
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(f".{target.name}.tmp")
    if temp.is_symlink() or temp.exists():
        temp.unlink()
    os.symlink(str(source), temp)
    os.replace(temp, target)


def sync_metadata_dir(
    rule: SyncRule, source_dir: Path, target_dir: Path
) -> Tuple[Dict[str, int], Set[str]]:
    """把单个源目录的元数据同步到目的目录，返回统计与期望文件集合。"""
    stats = {"metadata_copied": 0, "metadata_skipped": 0, "metadata_failed": 0}
    expected: Set[str] = set()
    extensions = rule.metadata_ext_set
    if not extensions or not rule.update_metadata:
        return stats, expected
    try:
        candidates = sorted(
            item
            for item in source_dir.iterdir()
            if item.is_file() and item.suffix.lower() in extensions
        )
    except OSError as err:
        logger.warning(f"读取元数据目录失败 {source_dir}：{err}")
        return stats, expected
    local_root = Path(normalize_path(rule.local_dir))
    for item in candidates:
        target = target_dir / item.name
        expected.add(relative_posix(local_root, target))
        if target.exists() and not should_overwrite_metadata(rule, item, target):
            stats["metadata_skipped"] += 1
            continue
        try:
            if rule.metadata_mode == "cloud":
                _download_metadata(rule, item, target)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target)
            stats["metadata_copied"] += 1
        except Exception as err:  # pylint: disable=broad-except
            stats["metadata_failed"] += 1
            logger.warning(f"同步元数据失败 {item} -> {target}：{err}")
    return stats, expected


def _download_metadata(rule: SyncRule, source: Path, target: Path) -> None:
    """云端模式下通过 CloudDrive2 静态直链下载元数据文件。"""
    url = build_static_url(rule.cloud_host, cloud_path_of(rule, str(source)))
    response = requests.get(url, timeout=(10, 60), stream=True)
    try:
        response.raise_for_status()
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(f".{target.name}.tmp")
        with open(temp, "wb") as handle:
            for chunk in response.iter_content(chunk_size=65536):
                if chunk:
                    handle.write(chunk)
        os.replace(temp, target)
    finally:
        response.close()
    try:
        mtime = source.stat().st_mtime
        os.utime(target, (mtime, mtime))
    except OSError:
        pass


def metadata_target_path(rule: SyncRule, source: Path) -> Optional[Path]:
    """计算元数据类对象（按原名复制）在目的目录中的目标路径。"""
    media_root = Path(normalize_path(rule.media_dir))
    try:
        relative = source.relative_to(media_root)
    except ValueError:
        return None
    return Path(normalize_path(rule.local_dir)) / relative


def sync_metadata_one(rule: SyncRule, source: Path) -> Tuple[str, Optional[Path]]:
    """同步单个元数据文件，返回（结果，目标路径）。"""
    if not rule.update_metadata:
        return "skipped", None
    media_root = Path(normalize_path(rule.media_dir))
    local_root = Path(normalize_path(rule.local_dir))
    try:
        relative = source.relative_to(media_root)
    except ValueError:
        return "skipped", None
    target = local_root / relative
    if target.exists() and not should_overwrite_metadata(rule, source, target):
        return "skipped", target
    try:
        if rule.metadata_mode == "cloud":
            _download_metadata(rule, source, target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        return "copied", target
    except Exception as err:  # pylint: disable=broad-except
        logger.warning(f"同步元数据失败 {source} -> {target}：{err}")
        return "failed", target


def remove_target_subtree(target: Path, stats: Dict[str, Any]) -> int:
    """删除某个目录在目的目录中的整个子树，返回删除的文件数。"""
    if not target.exists():
        return 0
    removed = 0
    for item in sorted(target.rglob("*"), reverse=True):
        try:
            if item.is_dir() and not item.is_symlink():
                item.rmdir()
            else:
                item.unlink()
                removed += 1
        except OSError:
            stats["cleaned_failed"] += 1
    try:
        target.rmdir()
    except OSError:
        pass
    return removed


def _count_metadata(stats: Dict[str, Any], outcome: str) -> None:
    """累计一次元数据同步结果。"""
    if outcome == "copied":
        stats["metadata_copied"] += 1
    elif outcome == "failed":
        stats["metadata_failed"] += 1
    else:
        stats["metadata_skipped"] += 1


def _sync_related_metadata(rule: SyncRule, source: Path, stats: Dict[str, Any]) -> None:
    """同步与某个视频同名的元数据文件。"""
    for item in related_metadata(rule, source):
        outcome, _target = sync_metadata_one(rule, item)
        _count_metadata(stats, outcome)


def _globally_excluded(global_excludes: Optional[List[str]], path: str) -> bool:
    """判断路径是否落在「全局排除目录」内（对所有目录组生效）。"""
    if not global_excludes:
        return False
    target = normalize_path(path)
    if not target:
        return False
    for item in global_excludes:
        normalized = normalize_path(str(item))
        if normalized and (target == normalized or target.startswith(f"{normalized}/")):
            return True
    return False


def apply_event(
    rule: SyncRule,
    path: str,
    change_type: str,
    is_dir: bool,
    action: str = "full",
    global_excludes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """按单条 CloudDrive2 通知精确处理一个对象（精确模式）。

    action：link＝只生成链接；meta＝只同步元数据；full＝按变更类型完整处理。
    """
    started = time.time()
    stats: Dict[str, Any] = {
        "trigger": "event",
        "rule": rule.name,
        "scanned_files": 0,
        "links_created": 0,
        "links_updated": 0,
        "links_skipped": 0,
        "links_failed": 0,
        "metadata_copied": 0,
        "metadata_skipped": 0,
        "metadata_failed": 0,
        "removed_links": 0,
        "removed_metadata": 0,
        "removed_dirs": 0,
        "cleaned_failed": 0,
        "error": "",
        "created_paths": [],
        "updated_paths": [],
        "seconds": 0.0,
    }
    if not rule.is_ready():
        stats["error"] = "规则缺少源目录或目的目录"
        return stats
    if not rule.enabled:
        stats["error"] = "该目录组已停用"
        return stats
    source = Path(normalize_path(path))
    media_root = Path(normalize_path(rule.media_dir))
    local_root = Path(normalize_path(rule.local_dir))
    try:
        relative = source.relative_to(media_root)
    except ValueError:
        stats["error"] = f"路径不在源目录内：{source}"
        return stats
    if is_excluded(rule, str(source)):
        stats["seconds"] = round(time.time() - started, 2)
        return stats
    if _globally_excluded(global_excludes, str(source)):
        # 全局排除目录：不生成 strm、不同步元数据（只计为跳过）
        stats["seconds"] = round(time.time() - started, 2)
        return stats
    if is_dir:
        if change_type != "delete":
            # 新目录内可能整批出现文件，交给目录扫描兜底
            return scan_rule(rule, scope=str(source), trigger="event")
        if rule.on_delete_remove_link:
            stats["removed_links"] += remove_target_subtree(local_root / relative, stats)
        stats["seconds"] = round(time.time() - started, 2)
        return stats
    suffix = source.suffix.lower()
    if change_type == "delete" or not source.exists():
        if suffix in rule.link_ext_set:
            target = target_path(rule, source)
            if target is not None and rule.on_delete_remove_link:
                if target.exists() or target.is_symlink():
                    try:
                        target.unlink()
                        stats["removed_links"] += 1
                    except OSError:
                        stats["cleaned_failed"] += 1
            if rule.on_delete_remove_metadata:
                for item in related_metadata(rule, source):
                    try:
                        metadata_target = local_root / item.relative_to(media_root)
                    except ValueError:
                        continue
                    if metadata_target.exists():
                        try:
                            metadata_target.unlink()
                            stats["removed_metadata"] += 1
                        except OSError:
                            stats["cleaned_failed"] += 1
        elif suffix in rule.metadata_ext_set and rule.on_delete_remove_metadata:
            metadata_target = local_root / relative
            if metadata_target.exists():
                try:
                    metadata_target.unlink()
                    stats["removed_metadata"] += 1
                except OSError:
                    stats["cleaned_failed"] += 1
        stats["seconds"] = round(time.time() - started, 2)
        return stats
    if action == "meta":
        if suffix in rule.link_ext_set:
            _sync_related_metadata(rule, source, stats)
        elif suffix in rule.metadata_ext_set:
            outcome, _target = sync_metadata_one(rule, source)
            _count_metadata(stats, outcome)
        stats["seconds"] = round(time.time() - started, 2)
        return stats
    if suffix in rule.link_ext_set:
        stats["scanned_files"] = 1
        if rule.link_min_size:
            try:
                if source.stat().st_size < int(rule.link_min_size) * 1024 * 1024:
                    stats["links_skipped"] += 1
                    stats["seconds"] = round(time.time() - started, 2)
                    return stats
            except OSError:
                stats["links_failed"] += 1
                stats["seconds"] = round(time.time() - started, 2)
                return stats
        try:
            outcome, target = ensure_link(rule, source)
        except Exception as err:  # pylint: disable=broad-except
            stats["links_failed"] += 1
            stats["error"] = str(err)
            stats["seconds"] = round(time.time() - started, 2)
            return stats
        if outcome == "created":
            stats["links_created"] += 1
            if target is not None:
                stats["created_paths"].append(str(target))
        elif outcome == "updated":
            stats["links_updated"] += 1
            if target is not None:
                stats["updated_paths"].append(str(target))
        else:
            stats["links_skipped"] += 1
        if action != "link":
            _sync_related_metadata(rule, source, stats)
    elif suffix in rule.metadata_ext_set:
        outcome, _target = sync_metadata_one(rule, source)
        _count_metadata(stats, outcome)
    stats["seconds"] = round(time.time() - started, 2)
    return stats


def clean_targets(
    rule: SyncRule,
    expected_links: Set[str],
    expected_metadata: Set[str],
    scope: Path,
    allow_remove_links: bool,
    allow_remove_metadata: bool,
    allow_remove_dirs: bool,
) -> Dict[str, int]:
    """清理目的目录中的无效链接、无效元数据与空目录。"""
    stats = {"removed_links": 0, "removed_metadata": 0, "removed_dirs": 0, "cleaned_failed": 0}
    local_root = Path(normalize_path(rule.local_dir))
    if not scope.is_dir():
        return stats
    metadata_exts = rule.metadata_ext_set
    directories: List[Path] = []
    for current, _dir_names, file_names in os.walk(scope, topdown=False):
        current_path = Path(current)
        directories.append(current_path)
        for name in file_names:
            target = current_path / name
            relative = relative_posix(local_root, target)
            suffix = target.suffix.lower()
            if suffix == ".strm" or target.is_symlink():
                if relative in expected_links or not allow_remove_links:
                    continue
                try:
                    target.unlink()
                    stats["removed_links"] += 1
                except OSError:
                    stats["cleaned_failed"] += 1
            elif suffix in metadata_exts:
                if relative in expected_metadata or not allow_remove_metadata:
                    continue
                try:
                    target.unlink()
                    stats["removed_metadata"] += 1
                except OSError:
                    stats["cleaned_failed"] += 1
    if allow_remove_dirs:
        for directory in directories:
            if directory == local_root or directory == scope:
                continue
            try:
                if not any(directory.iterdir()):
                    directory.rmdir()
                    stats["removed_dirs"] += 1
            except OSError:
                continue
    return stats


def scan_rule(
    rule: SyncRule,
    scope: Optional[str] = None,
    allow_remove_links: Optional[bool] = None,
    allow_remove_metadata: Optional[bool] = None,
    allow_remove_dirs: Optional[bool] = None,
    trigger: str = "manual",
    progress: Optional[Callable[[Dict[str, Any]], None]] = None,
    global_excludes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """扫描一组目录：补齐链接、同步元数据并清理无效项。"""
    started = time.time()

    def _report(scanned: int, stage: str) -> None:
        """上报扫描进度（回调可选，异常不影响扫描）。"""
        if progress is None:
            return
        try:
            progress(
                {
                    "scanned": scanned,
                    "stage": stage,
                    "elapsed": round(time.time() - started, 1),
                }
            )
        except Exception:  # pylint: disable=broad-except
            pass

    _report(0, "准备")
    stats: Dict[str, Any] = {
        "trigger": trigger,
        "rule": rule.name,
        "scanned_files": 0,
        "links_created": 0,
        "links_updated": 0,
        "links_skipped": 0,
        "links_failed": 0,
        "metadata_copied": 0,
        "metadata_skipped": 0,
        "metadata_failed": 0,
        "removed_links": 0,
        "removed_metadata": 0,
        "removed_dirs": 0,
        "cleaned_failed": 0,
        "error": "",
        "seconds": 0.0,
    }
    if not rule.is_ready():
        stats["error"] = "规则缺少源目录或目的目录"
        return stats
    if not rule.enabled:
        stats["error"] = "该目录组已停用"
        return stats
    source_root = Path(normalize_path(rule.media_dir))
    local_root = Path(normalize_path(rule.local_dir))
    if not source_root.is_dir():
        stats["error"] = f"源目录不存在：{source_root}"
        return stats
    walk_root = source_root
    scope_target = local_root
    if scope:
        candidate = Path(normalize_path(scope))
        try:
            relative = candidate.relative_to(source_root)
            walk_root = candidate
            scope_target = local_root / relative
        except ValueError:
            walk_root = source_root
            scope_target = local_root
    link_exts = rule.link_ext_set
    metadata_exts = rule.metadata_ext_set
    min_size = max(0, int(rule.link_min_size)) * 1024 * 1024
    expected_links: Set[str] = set()
    expected_metadata: Set[str] = set()
    created_paths: List[str] = []
    updated_paths: List[str] = []
    metadata_dirs: List[Tuple[Path, Path]] = []
    if not walk_root.is_dir():
        if trigger == "event":
            # 事件驱动的竞态：目录已被移走/改名（例如媒体整理刚把它搬走），
            # 属正常追赶现象，不视为失败（不落记录、不推失败通知）。
            stats["missing_scope"] = 1
            return stats
        stats["error"] = f"扫描目录不存在：{walk_root}"
        return stats
    for current, dir_names, file_names in os.walk(walk_root):
        current_path = Path(current)
        if is_excluded(rule, str(current_path)):
            dir_names[:] = []
            continue
        if _globally_excluded(global_excludes, str(current_path)):
            # 全局排除目录：不生成 strm、不同步元数据
            dir_names[:] = []
            continue
        dir_names[:] = [
            name for name in dir_names if not is_excluded(rule, str(current_path / name))
        ]
        metadata_candidate = False
        for name in file_names:
            source = current_path / name
            if source.is_symlink() and not source.exists():
                continue
            suffix = source.suffix.lower()
            if suffix in link_exts:
                stats["scanned_files"] += 1
                if stats["scanned_files"] % 25 == 0:
                    _report(stats["scanned_files"], "扫描源目录")
                if min_size:
                    try:
                        if source.stat().st_size < min_size:
                            continue
                    except OSError:
                        continue
                try:
                    outcome, target = ensure_link(rule, source)
                except Exception as err:  # pylint: disable=broad-except
                    stats["links_failed"] += 1
                    logger.warning(f"生成链接失败 {source}：{err}")
                    continue
                if target is not None:
                    expected_links.add(relative_posix(local_root, target))
                if outcome == "created":
                    stats["links_created"] += 1
                    if target is not None and len(created_paths) < MAX_REPORT_PATHS:
                        created_paths.append(str(target))
                elif outcome == "updated":
                    stats["links_updated"] += 1
                    if target is not None and len(updated_paths) < MAX_REPORT_PATHS:
                        updated_paths.append(str(target))
                else:
                    stats["links_skipped"] += 1
            elif suffix in metadata_exts:
                metadata_candidate = True
        if metadata_candidate and rule.update_metadata:
            try:
                relative_dir = current_path.relative_to(source_root)
            except ValueError:
                relative_dir = Path(".")
            metadata_dirs.append((current_path, local_root / relative_dir))
    _report(stats["scanned_files"], "同步元数据")
    for source_dir, target_dir in metadata_dirs:
        meta_stats, meta_expected = sync_metadata_dir(rule, source_dir, target_dir)
        for key, value in meta_stats.items():
            stats[key] = stats.get(key, 0) + value
        expected_metadata.update(meta_expected)
    _report(stats["scanned_files"], "清理无效项")
    cleanup = clean_targets(
        rule,
        expected_links,
        expected_metadata,
        scope_target,
        rule.clean_invalid_link if allow_remove_links is None else allow_remove_links,
        rule.clean_invalid_metadata if allow_remove_metadata is None else allow_remove_metadata,
        rule.clean_invalid_dir if allow_remove_dirs is None else allow_remove_dirs,
    )
    for key, value in cleanup.items():
        stats[key] = stats.get(key, 0) + value
    stats["created_paths"] = created_paths
    stats["updated_paths"] = updated_paths
    stats["seconds"] = round(time.time() - started, 2)
    return stats


def _scope_for(rule: SyncRule, raw_path: str, change_type: str, is_dir: bool) -> str:
    """推导一次变更需要扫描的目录范围。"""
    target = normalize_path(raw_path)
    if not target:
        return ""
    if normalize_path(rule.media_dir) == target:
        return target
    if change_type == "delete" or not is_dir:
        parent = str(Path(target).parent)
        return normalize_path(parent)
    return target


class EventDispatcher:
    """把 CloudDrive2 变更事件按规则与目录去抖合并后交给扫描回调。"""

    def __init__(
        self,
        rules_provider: Callable[[], List[SyncRule]],
        resolver: Callable[
            [Dict[str, Any], List[SyncRule]],
            List[Tuple[int, str, float, Dict[str, Any]]],
        ],
        worker: Callable[[int, Dict[str, Any], str], None],
    ):
        """保存规则来源、事件解析回调与处理回调。"""
        self._rules_provider = rules_provider
        self._resolver = resolver
        self._worker = worker
        self._pending: Dict[Tuple[int, str], Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._accepted = 0
        self._ignored = 0

    def start(self) -> None:
        """启动去抖调度线程。"""
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._loop, name="Cd2EventDispatcher", daemon=True
            )
            self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """停止去抖调度线程。"""
        self._stop_event.set()
        with self._lock:
            thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout)
        with self._lock:
            self._pending.clear()

    def status(self) -> Dict[str, Any]:
        """返回调度器状态快照。"""
        with self._lock:
            pending = len(self._pending)
        return {
            "accepted": self._accepted,
            "ignored": self._ignored,
            "pending": pending,
            "running": bool(self._thread and self._thread.is_alive()),
        }

    def submit(self, event: Dict[str, Any]) -> Optional[Tuple[int, str]]:
        """登记一个变更事件，返回（规则下标，规则名称）。"""
        rules = self._rules_provider()
        if not rules:
            return None
        targets = self._resolver(event, rules) or []
        if not targets:
            self._ignored += 1
            return None
        hit: Optional[Tuple[int, str]] = None
        with self._lock:
            for index, key, delay, payload in targets:
                self._pending[(index, key)] = {
                    "deadline": time.time() + max(0.0, float(delay)),
                    "payload": payload,
                }
                if hit is None:
                    hit = (index, rules[index].display_name(index))
            self._accepted += 1
        return hit

    def _loop(self) -> None:
        """每秒检查一次到期任务并执行扫描。"""
        while not self._stop_event.is_set():
            self._stop_event.wait(1)
            self._flush_due()

    def _flush_due(self) -> None:
        """执行所有已过期的处理任务。"""
        now = time.time()
        with self._lock:
            due = [
                (key, dict(item.get("payload") or {}))
                for key, item in self._pending.items()
                if item["deadline"] <= now
            ]
            for key, _payload in due:
                self._pending.pop(key, None)
        for (index, _key), payload in due:
            if self._stop_event.is_set():
                return
            try:
                self._worker(index, payload, "event")
            except Exception as err:  # pylint: disable=broad-except
                logger.error(f"处理 CloudDrive2 变更事件失败 {payload}：{err}")


# ===================== 媒体整理（第 2 步） =====================

# 整理后允许交给整理链的视频后缀（与 STRM 侧默认白名单一致）
ORGANIZE_VIDEO_EXTS = {
    ".mkv",
    ".iso",
    ".ts",
    ".mp4",
    ".avi",
    ".rmvb",
    ".wmv",
    ".m2ts",
    ".mpg",
    ".flv",
    ".rm",
    ".mov",
}


def is_organize_candidate(container_path: str) -> bool:
    """判断容器路径是否是整理候选（只处理视频文件）。"""
    if not container_path:
        return False
    return Path(container_path).suffix.lower() in ORGANIZE_VIDEO_EXTS


def match_organize_rule(rules: List[Any], container_path: str) -> Optional[int]:
    """按「整理源目录」匹配整理组，返回下标；目的目录内或排除目录内一律跳过。

    匹配口径与 STRM 侧一致：把通知路径与整理组路径**都换算成 CD2 内部路径**再比较，
    因此既支持 CD2 推送的内部路径（/115/media/...），也支持挂载路径
    （/mnt/cd2-mount/115/media/...），且不依赖文件是否已经可见。
    """
    raw = normalize_path(container_path)
    if not raw:
        return None
    for index, rule in enumerate(rules):
        if not rule.is_active():
            continue
        target = to_organize_internal(rule, raw)
        src = to_organize_internal(rule, rule.src)
        if not src:
            continue
        dst = to_organize_internal(rule, rule.dst)
        in_src = target == src or target.startswith(f"{src}/")
        in_dst = bool(dst) and (target == dst or target.startswith(f"{dst}/"))
        if not in_src:
            # 源目录之外（含落在整理目的目录内，避免把自己的产物再整理一遍）
            continue
        # 源目录优先：只有「目的目录嵌在源目录之内」时才防循环跳过；
        # 目的目录是源目录的父级（如「中转站 → 媒体库根」）属正常用法，应照常受理。
        nested_dst = bool(dst) and (dst == src or dst.startswith(f"{src}/"))
        if nested_dst and in_dst:
            continue
        excluded = False
        for item in rule.exclude_list:
            item_path = to_organize_internal(rule, item)
            if item_path and (target == item_path or target.startswith(f"{item_path}/")):
                excluded = True
                break
        if excluded:
            continue
        return index
    return None


def organize_container_path(rule: Any, raw_path: str) -> str:
    """把 CD2 通知路径换算成容器内路径（优先使用整理组自己的 cd2 根目录）。"""
    target = normalize_path(raw_path)
    if not target:
        return ""
    root = normalize_path(getattr(rule, "cd2_root", ""))
    if not root:
        return target
    if target == root or target.startswith(f"{root}/"):
        return target
    return f"{root}/{target.lstrip('/')}"


def _transfer_chain() -> Any:
    """惰性获取 MoviePilot 整理链（宿主缺失时返回 None，不影响其它功能）。"""
    try:
        from app.chain.transfer import TransferChain  # pylint: disable=import-outside-toplevel

        return TransferChain()
    except Exception:  # pragma: no cover - 仅在宿主缺失时触发
        return None


def _storage_chain() -> Any:
    """惰性获取 MoviePilot 存储链。"""
    try:
        from app.chain.storage import StorageChain  # pylint: disable=import-outside-toplevel

        return StorageChain()
    except Exception:  # pragma: no cover - 仅在宿主缺失时触发
        return None


def _file_item(path: Path) -> Any:
    """构建存储层的文件项（失败时返回 None，不抛异常）。"""
    storage = _storage_chain()
    if storage is None:
        return None
    try:
        return storage.get_file_item(storage="local", path=path)
    except Exception as err:  # pylint: disable=broad-except
        logger.warning(f"构建文件项失败 {path}：{err}")
        return None


def _folder_from_dest(dest: str, target_root: str) -> str:
    """从整理后的落点推回「整理生成的文件夹名」（取不到返回空串）。"""
    if not dest or not target_root:
        return ""
    try:
        relative = Path(str(dest)).relative_to(Path(str(target_root)))
    except ValueError:
        return ""
    parts = relative.parts
    if not parts:
        return ""
    if len(parts) == 1:
        # 只有一层：是目录就取它，是文件（直接落在目的根目录）则拿不到媒体文件夹
        only = parts[0]
        return "" if Path(only).suffix else only
    return parts[0]


def _history_media(src_path: str, target_root: str = "") -> str:
    """读回整理结果信息：优先「整理生成的文件夹名」，其次「类型 · 标题 (年份)」。

    取不到时返回空串，不影响整理本身。
    """
    if not src_path:
        return ""
    try:
        from app.application.history import (  # pylint: disable=import-outside-toplevel
            get_transfer_history_repository,
        )

        snapshot = get_transfer_history_repository().get_success_by_src(
            src_path, storage="local"
        )
    except Exception:  # pragma: no cover - 宿主接口缺失或查询失败时静默降级
        return ""
    if snapshot is None:
        return ""
    folder = _folder_from_dest(str(getattr(snapshot, "dest", "") or ""), target_root)
    if folder:
        return folder
    title = str(getattr(snapshot, "title", "") or "").strip()
    year = str(getattr(snapshot, "year", "") or "").strip()
    media_type = str(getattr(snapshot, "type", "") or "").strip()
    name = f"{title} ({year})" if title and year else title
    return " · ".join(part for part in (media_type, name) if part)


def _media_from_receipt(payload: Any, target_root: str) -> str:
    """从整理链回执解析「整理生成的文件夹名」（取不到返回空串）。

    回执形如 {"items": [{"target": "…/媒体名 [tmdb-x]/Season 1/文件.mkv", ...}], "message": "…"}，
    target 为文件落点、target_dir 为媒体目录；文件与目录整理都适用。
    """
    if not isinstance(payload, dict):
        return ""
    for key in ("target", "target_dir", "dest"):
        folder = _folder_from_dest(str(payload.get(key) or ""), target_root)
        if folder:
            return folder
    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        for key in ("target", "target_dir", "dest"):
            folder = _folder_from_dest(str(item.get(key) or ""), target_root)
            if folder:
                return folder
    return ""


def _receipt_message(payload: Any) -> str:
    """从整理链回执里取可读的失败原因（取不到返回空串）。"""
    if isinstance(payload, str):
        return payload
    if not isinstance(payload, dict):
        return ""
    message = str(payload.get("message") or "").strip()
    if message:
        return message
    for item in payload.get("items") or []:
        if isinstance(item, dict):
            text = str(item.get("message") or "").strip()
            if text:
                return text
    return ""


def _run_manual_transfer(
    rule: Any, fileitem: Any, source_path: str = ""
) -> Tuple[bool, str, str, str]:
    """把文件项（文件或目录）交给 MoviePilot 整理链。

    返回（是否成功、结果说明、媒体名、失败原因）。文件与目录共用这一段调用。
    """
    chain = _transfer_chain()
    if chain is None:
        return False, "整理链不可用", "", "无法加载 MoviePilot 整理链（TransferChain）"
    try:
        ok, payload = chain.manual_transfer(
            fileitem=fileitem,
            target_storage="local",
            target_path=Path(str(rule.dst)),
            # 整理模式、刮削、类型目录、分类目录一律交给命中的 MoviePilot 目录配置：
            # 传 None 时宿主会回退到该目录配置的 transfer_type / scraping /
            # library_type_folder / library_category_folder。
            transfer_type=None,
            scrape=None,
            library_type_folder=None,
            library_category_folder=None,
            force=False,
            background=False,
            sync_extra_files=True,
            report_results=True,
        )
    except Exception as err:  # pylint: disable=broad-except
        return False, "整理链异常", "", str(err)
    if not ok:
        reason = _receipt_message(payload) or json_dumps_short(payload)
        return False, "整理失败", "", reason or "整理链返回失败"
    target_root = str(getattr(rule, "dst", "") or "")
    media = ""
    if isinstance(payload, dict):
        media = str(
            payload.get("title") or payload.get("name") or payload.get("media_title") or ""
        )
        if not media:
            media = _media_from_receipt(payload, target_root)
    if not media:
        media = _history_media(source_path, target_root)
    return True, "整理成功", media, ""


def organize_file(rule: Any, container_path: str) -> Tuple[bool, str, str, str]:
    """把一个文件交给 MoviePilot 整理链处理。

    体积过滤、整理模式与源文件去留均由 MoviePilot 整理链按命中的目录配置决定。
    返回（是否成功、结果说明、媒体名、失败原因）。
    """
    source = Path(container_path)
    if not source.exists():
        return False, "文件不存在", "", "文件不存在或尚未可见"
    if source.is_dir():
        return False, "路径是目录", "", "该路径是目录，应使用目录整理逻辑"
    fileitem = _file_item(source)
    if not fileitem:
        return False, "无法构建文件项", "", "StorageChain 未返回文件项"
    return _run_manual_transfer(rule, fileitem, str(source))


def organize_path(rule: Any, container_path: str) -> Tuple[bool, str, str, str]:
    """按路径类型整理：目录→整目录交给整理链；文件→organize_file。

    体积过滤、整理模式、刮削、目录分级与源文件去留均由 MoviePilot 整理链按命中的
    目录配置决定。
    """
    source = Path(container_path)
    if not source.exists():
        return False, "路径不存在", "", "路径不存在或尚未可见"
    if not source.is_dir():
        return organize_file(rule, container_path)
    fileitem = _file_item(source)
    if not fileitem:
        return False, "无法构建文件项", "", "StorageChain 未返回目录项"
    return _run_manual_transfer(rule, fileitem, str(source))


def json_dumps_short(value: Any) -> str:
    """把整理链返回的对象压成一行短文本，便于写入记录。"""
    try:
        import json  # pylint: disable=import-outside-toplevel

        text = json.dumps(value, ensure_ascii=False)
    except Exception:  # pragma: no cover - 极端兜底
        text = str(value)
    return text[:200]


# ------------------------------------------------------------------ 功能三：镜像移动
# 时间戳冲突后缀与单次移动上限
MIRROR_TIMESTAMP_FORMAT = "%Y%m%d-%H%M%S"
MIRROR_MOVE_LIMIT = 50


def to_mirror_internal(rule: Any, path: str) -> str:
    """把容器路径换算成镜像内部路径（去掉 CD2 根目录前缀），口径与功能 1/2 一致。"""
    target = normalize_path(path)
    if not target:
        return ""
    root = normalize_path(str(getattr(rule, "cd2_root", "") or ""))
    if not root:
        return target
    if target == root:
        return "/"
    if target.startswith(f"{root}/"):
        return target[len(root) :] or "/"
    return target


def match_mirror_rule(rules: List[Any], container_path: str) -> Optional[int]:
    """按「监听目录」匹配镜像组，返回下标；只认监听目录内的对象。

    这里只看路径是否就绪（不看 enabled），停用的组也会被匹配到 —— 由调用方
    区分「组已停用」与「未命中监听目录」两种未受理原因。
    """
    raw = normalize_path(container_path)
    if not raw:
        return None
    for index, rule in enumerate(rules):
        if not rule.is_ready():
            continue
        base = to_mirror_internal(rule, rule.path1)
        if not base:
            continue
        target = to_mirror_internal(rule, raw)
        if target == base or target.startswith(f"{base}/"):
            return index
    return None


def mirror_relative(rule: Any, raw_path: str) -> str:
    """取通知对象相对「监听目录」的子路径（空串表示就是监听目录本身）。"""
    base = to_mirror_internal(rule, rule.path1)
    target = to_mirror_internal(rule, raw_path)
    if not base or not target:
        return ""
    if target == base:
        return ""
    if target.startswith(f"{base}/"):
        return target[len(base) + 1 :]
    return ""


def mirror_target_path(rule: Any, raw_path: str) -> Optional[Path]:
    """算出该通知对象在「镜像目录」中对应的容器路径。"""
    path2 = normalize_path(rule.path2)
    if not path2:
        return None
    relative = mirror_relative(rule, raw_path)
    base = Path(path2)
    return base / relative if relative else base


def mirror_media_exts(rule: Any) -> Set[str]:
    """镜像组用于把 .strm 换算成视频的后缀集合。"""
    value = getattr(rule, "media_ext_set", None)
    if isinstance(value, set):
        return {str(item).lower() for item in value}
    text = str(getattr(rule, "media_exts", "") or "")
    result: Set[str] = set()
    for chunk in text.replace(",", ";").split(";"):
        item = chunk.strip().lower()
        if item:
            result.add(item if item.startswith(".") else f".{item}")
    return result


def _match_protect_entry(rule: Any, path: Path, is_dir: bool) -> bool:
    """按对象名判断是否命中保护白名单。

    四种写法：
    - 文件夹名（如 花絮）：只匹配目录，按完整名精确比较；
    - 无后缀文件名（如 README）：只匹配**没有后缀**的文件，按完整名比较；
    - .后缀（如 .nfo）：匹配同后缀的任意文件；
    - 文件名+后缀（如 poster.jpg）：匹配该文件。
    """
    entries = [str(item).strip() for item in (rule.protect_list or []) if str(item).strip()]
    if not entries:
        return False
    name = path.name
    suffix = path.suffix.lower()
    for item in entries:
        low = item.lower()
        if low.startswith("."):
            if not is_dir and suffix == low:
                return True
        elif "." not in item:
            if is_dir and name == item:
                return True
            # 无后缀文件（如 README、花絮）：条目本身不带点，按完整名匹配
            if not is_dir and not suffix and name.lower() == low:
                return True
        elif not is_dir and name.lower() == low:
            return True
    return False


def is_protected(rule: Any, target: Path, is_dir: bool) -> bool:
    """判断镜像目录里的对象是否受保护（自身或任一祖先目录命中保护目录条目）。"""
    if _match_protect_entry(rule, target, is_dir):
        return True
    root = Path(normalize_path(rule.path2))
    try:
        parts = target.relative_to(root).parts
    except ValueError:
        return False
    current = root
    for part in parts[:-1]:
        current = current / part
        if _match_protect_entry(rule, current, True):
            return True
    return False


def _inside(root: Path, target: Path) -> bool:
    """判断 target 是否严格位于 root 之内（拒绝越界与 ..）。"""
    try:
        target.relative_to(Path(normalize_path(str(root))))
    except ValueError:
        return False
    return True


def _unique_dest(dest: Path) -> Path:
    """目标已存在时改成「同名 + 时间戳」（仍冲突则继续加序号）。"""
    from datetime import datetime  # pylint: disable=import-outside-toplevel

    stamp = datetime.now().strftime(MIRROR_TIMESTAMP_FORMAT)
    candidate = dest.with_name(f"{dest.stem}.{stamp}{dest.suffix}")
    counter = 1
    while candidate.exists() or candidate.is_symlink():
        candidate = dest.with_name(f"{dest.stem}.{stamp}-{counter}{dest.suffix}")
        counter += 1
    return candidate


def _move_one(
    rule: Any,
    src: Path,
    dry_run: bool,
    stats: Dict[str, Any],
    moved: List[str],
    protected: List[str],
    skipped: List[str],
    failed: List[str],
) -> None:
    """把单个文件（或目录树里的每一项）移到回收站；受保护项留在原地。"""
    path2 = Path(normalize_path(rule.path2))
    path3 = Path(normalize_path(rule.path3))
    if path3 == Path("."):
        stats["failed"] += 1
        failed.append(f"{src.name}（未配置回收站）")
        return
    if not _inside(path2, src):
        stats["failed"] += 1
        failed.append(f"{src}（不在镜像目录之内，已拒绝）")
        return
    if src.is_symlink():
        stats["skipped"] += 1
        skipped.append(f"{src.name}（符号链接，已跳过）")
        return
    if is_protected(rule, src, src.is_dir()):
        stats["protected"] += 1
        protected.append(str(src))
        return
    if src.is_dir():
        try:
            children = sorted(src.iterdir())
        except OSError as err:
            stats["failed"] += 1
            failed.append(f"{src.name}（{err}）")
            return
        for child in children:
            _move_one(rule, child, dry_run, stats, moved, protected, skipped, failed)
        if not dry_run:
            try:
                if src.is_dir() and not any(src.iterdir()):
                    src.rmdir()
            except OSError:
                pass
        return
    if not src.exists():
        stats["skipped"] += 1
        skipped.append(f"{src.name}（不存在或尚未可见）")
        return
    if not dry_run and stats["moved_files"] >= MIRROR_MOVE_LIMIT:
        stats["failed"] += 1
        failed.append("单次移动超过上限，已中止")
        return
    try:
        relative = src.relative_to(path2)
    except ValueError:
        stats["failed"] += 1
        failed.append(f"{src}（无法计算相对路径）")
        return
    dest = path3 / relative
    if not _inside(path3, dest):
        stats["failed"] += 1
        failed.append(f"{dest}（超出回收站，已拒绝）")
        return
    if dry_run:
        final = _unique_dest(dest) if (dest.exists() or dest.is_symlink()) else dest
        stats["moved_files"] += 1
        moved.append(f"{src} → {final}（预演）")
        return
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() or dest.is_symlink():
            dest = _unique_dest(dest)
        shutil.move(str(src), str(dest))
    except Exception as err:  # pylint: disable=broad-except
        stats["failed"] += 1
        failed.append(f"{src.name}（{err}）")
        return
    stats["moved_files"] += 1
    moved.append(f"{src} → {dest}")


def move_mirror_targets(
    rule: Any, raw_path: str, is_dir: bool, dry_run: bool = True, trigger: str = "event"
) -> Dict[str, Any]:
    """处理一条「监听目录删除」通知：把镜像目录中对应的对象移到回收站。"""
    started = time.time()
    stats: Dict[str, Any] = {
        "moved_files": 0,
        "moved_dirs": 0,
        "protected": 0,
        "skipped": 0,
        "failed": 0,
    }
    moved: List[str] = []
    protected: List[str] = []
    skipped: List[str] = []
    failed: List[str] = []
    target = mirror_target_path(rule, raw_path)
    if target is None:
        stats["skipped"] += 1
        skipped.append("未配置镜像目录")
    elif is_dir:
        if not target.is_dir():
            stats["skipped"] += 1
            skipped.append(f"{target}（不存在或尚未可见）")
        else:
            _move_one(rule, target, dry_run, stats, moved, protected, skipped, failed)
            if stats["moved_files"]:
                stats["moved_dirs"] = 1
    else:
        name = Path(normalize_path(raw_path)).name
        if name.lower().endswith(".strm"):
            stem = Path(name).stem
            exts = mirror_media_exts(rule)
            candidates: List[Path] = []
            if target.parent.is_dir():
                try:
                    candidates = sorted(
                        item
                        for item in target.parent.iterdir()
                        if item.is_file()
                        and item.stem == stem
                        and item.suffix.lower() in exts
                    )
                except OSError:
                    candidates = []
            if not candidates:
                stats["skipped"] += 1
                skipped.append(f"{target.parent} 内未找到同名的视频文件：{name}")
            for item in candidates:
                _move_one(rule, item, dry_run, stats, moved, protected, skipped, failed)
        elif not target.exists():
            stats["skipped"] += 1
            skipped.append(f"{target}（不存在或尚未可见）")
        else:
            _move_one(rule, target, dry_run, stats, moved, protected, skipped, failed)
    result = "failed" if stats["failed"] else ("success" if moved else "skipped")
    return {
        "trigger": trigger,
        "result": result,
        "dry_run": bool(dry_run),
        "path": str(raw_path),
        "is_dir": bool(is_dir),
        "target": str(target) if target else "",
        "moved": moved,
        # 明细列表与计数字段分开命名，避免与 stats 里的同名计数互相覆盖
        "protected_items": protected,
        "skipped_items": skipped,
        "failed_items": failed,
        "seconds": round(time.time() - started, 2),
        **stats,
    }
