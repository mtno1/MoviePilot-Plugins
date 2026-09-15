"""CloudDrive2 gRPC-Web 客户端：只订阅推送消息与读取挂载点，不做任何修改操作。

MoviePilot 运行环境没有 grpcio，但 CloudDrive2 同时提供 gRPC-Web 接口
（POST /clouddrive.CloudDriveFileSrv/<Method>，content-type: application/grpc-web+proto），
因此这里用标准库 + requests 手写帧解析，做到零新增依赖。

约定：本客户端只调用 PushMessage（接收变更通知）与 GetMountPoints（只读自检），
不调用任何会创建、修改、移动、删除文件或改动 CloudDrive2 设置的接口。
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple
from urllib.parse import quote

import requests

try:  # 宿主 v3 的日志入口
    from app.sdk.logging import logger
except Exception:  # pragma: no cover - 兼容旧入口
    from app.log import logger

# CloudDrive2 服务名与推送消息类型
SERVICE_NAME = "clouddrive.CloudDriveFileSrv"
MSG_FILE_SYSTEM_CHANGE = 4
MSG_MOUNT_POINT_CHANGE = 5
MSG_CLOUD_API_CHANGE = 9

# FileSystemChange.ChangeType
CHANGE_CREATE = 0
CHANGE_DELETE = 1
CHANGE_RENAME = 2
CHANGE_NAMES = {CHANGE_CREATE: "create", CHANGE_DELETE: "delete", CHANGE_RENAME: "rename"}

# protobuf wire type
WIRE_VARINT = 0
WIRE_FIXED64 = 1
WIRE_LEN = 2
WIRE_FIXED32 = 5


class CloudDriveError(Exception):
    """CloudDrive2 调用失败。"""

    def __init__(self, status: Optional[int], message: str):
        """记录 gRPC 状态码与错误信息。"""
        super().__init__(message)
        self.status = status
        self.message = message


def read_varint(data: bytes, position: int) -> Tuple[int, int]:
    """读取一个 varint，返回（值，新位置）。"""
    result = 0
    shift = 0
    index = position
    while index < len(data):
        byte = data[index]
        index += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, index
        shift += 7
        if shift > 63:
            break
    raise ValueError("varint 越界")


def decode_fields(data: bytes) -> Dict[int, List[Any]]:
    """把 protobuf 消息解码为 {字段号: [值]}；varint 为 int，长度限定为 bytes。"""
    fields: Dict[int, List[Any]] = {}
    position = 0
    size = len(data)
    while position < size:
        key, position = read_varint(data, position)
        field_no = key >> 3
        wire_type = key & 0x07
        if wire_type == WIRE_VARINT:
            value, position = read_varint(data, position)
        elif wire_type == WIRE_LEN:
            length, position = read_varint(data, position)
            value = data[position : position + length]
            position += length
        elif wire_type == WIRE_FIXED64:
            value = data[position : position + 8]
            position += 8
        elif wire_type == WIRE_FIXED32:
            value = data[position : position + 4]
            position += 4
        else:
            raise ValueError(f"不支持的 protobuf wire type：{wire_type}")
        fields.setdefault(field_no, []).append(value)
    return fields


def _first_int(fields: Dict[int, List[Any]], field_no: int, default: int = 0) -> int:
    """取某字段的第一个 varint 值。"""
    values = fields.get(field_no)
    if not values:
        return default
    value = values[0]
    return value if isinstance(value, int) else default


def _first_text(fields: Dict[int, List[Any]], field_no: int) -> Optional[str]:
    """取某字段的第一个字符串值。"""
    values = fields.get(field_no)
    if not values:
        return None
    value = values[0]
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def parse_file_system_change(payload: bytes) -> Dict[str, Any]:
    """解析 FileSystemChange 消息。"""
    fields = decode_fields(payload)
    change_code = _first_int(fields, 1, CHANGE_CREATE)
    return {
        "change_type": CHANGE_NAMES.get(change_code, "unknown"),
        "is_dir": bool(_first_int(fields, 2)),
        "path": _first_text(fields, 3) or "",
        "new_path": _first_text(fields, 4) or "",
    }


def parse_mount_points(payload: bytes) -> List[Dict[str, Any]]:
    """解析 GetMountPointsResult 消息。"""
    result: List[Dict[str, Any]] = []
    for raw in decode_fields(payload).get(1, []):
        if not isinstance(raw, bytes):
            continue
        fields = decode_fields(raw)
        result.append(
            {
                "mount_point": _first_text(fields, 1) or "",
                "source_dir": _first_text(fields, 2) or "",
                "local_mount": bool(_first_int(fields, 3)),
                "read_only": bool(_first_int(fields, 4)),
                "is_mounted": bool(_first_int(fields, 9)),
            }
        )
    return result


def parse_push_message(payload: bytes) -> Dict[str, Any]:
    """解析 CloudDrivePushMessage 消息。"""
    fields = decode_fields(payload)
    message_type = _first_int(fields, 1, -1)
    message: Dict[str, Any] = {"message_type": message_type}
    if message_type == MSG_FILE_SYSTEM_CHANGE:
        raw = fields.get(5)
        if raw and isinstance(raw[0], bytes):
            message.update(parse_file_system_change(raw[0]))
    return message


def encode_frame(payload: bytes) -> bytes:
    """按 gRPC-Web 规范封装一帧请求体。"""
    return b"\x00" + len(payload).to_bytes(4, "big") + payload


def iter_frames(response: requests.Response) -> Iterator[Tuple[int, bytes]]:
    """迭代 gRPC-Web 响应帧，产出（标志位，负载）。"""
    buffer = bytearray()
    for chunk in response.iter_content(chunk_size=16384):
        if not chunk:
            continue
        buffer.extend(chunk)
        while len(buffer) >= 5:
            flags = buffer[0]
            length = int.from_bytes(buffer[1:5], "big")
            if len(buffer) < 5 + length:
                break
            payload = bytes(buffer[5 : 5 + length])
            del buffer[: 5 + length]
            yield flags, payload


def parse_trailer(payload: bytes) -> Tuple[Optional[int], str]:
    """解析 gRPC-Web 尾部帧中的 grpc-status / grpc-message。"""
    status: Optional[int] = None
    message = ""
    for line in payload.decode("utf-8", errors="replace").splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if key == "grpc-status":
            try:
                status = int(value)
            except ValueError:
                status = None
        elif key == "grpc-message":
            message = requests.utils.unquote(value)
    return status, message


def build_static_url(host: str, cloud_path: str) -> str:
    """拼出 CloudDrive2 静态直链地址。"""
    normalized = host.strip().rstrip("/")
    if not normalized.startswith("http"):
        normalized = f"http://{normalized}"
    return f"{normalized}/static/http/{normalized.split('://', 1)[1]}/False/{quote(cloud_path, safe='')}"


def is_idle_timeout(error: BaseException) -> bool:
    """判断异常是否为长连接空闲读取超时（CloudDrive2 不心跳，属正常现象）。

    读取过程中超时时，requests 走的是 ``ConnectionError('... Read timed out')`` 分支；
    只有连接前的超时才抛 ``Timeout``，因此两种都要识别。
    """
    if isinstance(error, requests.exceptions.ReadTimeout):
        return True
    if isinstance(error, requests.exceptions.ConnectionError):
        return "read timed out" in str(error).lower()
    return False


class CloudDriveWebClient:
    """CloudDrive2 gRPC-Web 客户端。"""

    def __init__(
        self,
        host: str,
        token: str,
        read_timeout: int = 300,
        connect_timeout: int = 10,
    ):
        """保存连接参数，延迟建立会话。"""
        self.host = (host or "").strip().rstrip("/")
        if self.host and not self.host.startswith("http"):
            self.host = f"http://{self.host}"
        self.token = (token or "").strip()
        self.read_timeout = read_timeout
        self.connect_timeout = connect_timeout
        self._session = requests.Session()

    def close(self) -> None:
        """关闭底层会话。"""
        try:
            self._session.close()
        except Exception:  # pragma: no cover - 关闭失败无需处理
            pass

    def _url(self, method: str) -> str:
        """拼出某个 RPC 的调用地址。"""
        return f"{self.host}/{SERVICE_NAME}/{method}"

    def _headers(self) -> Dict[str, str]:
        """构造 gRPC-Web 请求头。"""
        return {
            "content-type": "application/grpc-web+proto",
            "x-grpc-web": "1",
            "x-user-agent": "grpc-web-python",
            "authorization": f"Bearer {self.token}",
        }

    def _check_ready(self) -> None:
        """校验基础配置是否完整。"""
        if not self.host:
            raise CloudDriveError(None, "未配置 CloudDrive2 地址")
        if not self.token:
            raise CloudDriveError(None, "未配置 CloudDrive2 API 令牌")

    @staticmethod
    def _header_status(response: requests.Response) -> Tuple[Optional[int], str]:
        """读取响应头里的 grpc-status。"""
        raw_status = response.headers.get("grpc-status")
        status: Optional[int] = None
        if raw_status is not None:
            try:
                status = int(raw_status)
            except ValueError:
                status = None
        message = requests.utils.unquote(response.headers.get("grpc-message", ""))
        return status, message

    def _unary(self, method: str, payload: bytes = b"") -> bytes:
        """执行一元调用并返回响应消息体。"""
        self._check_ready()
        response = self._session.post(
            self._url(method),
            headers=self._headers(),
            data=encode_frame(payload),
            stream=True,
            timeout=(self.connect_timeout, self.read_timeout),
        )
        try:
            header_status, header_message = self._header_status(response)
            if header_status not in (None, 0):
                raise CloudDriveError(header_status, header_message or "CloudDrive2 拒绝请求")
            body = b""
            status: Optional[int] = None
            message = ""
            for flags, chunk in iter_frames(response):
                if flags & 0x80:
                    status, message = parse_trailer(chunk)
                else:
                    body = chunk
            if status not in (None, 0):
                raise CloudDriveError(status, message or "CloudDrive2 调用失败")
            return body
        finally:
            response.close()

    def get_mount_points(self) -> List[Dict[str, Any]]:
        """查询挂载点列表，需要令牌具备「获取挂载点」权限。"""
        return parse_mount_points(self._unary("GetMountPoints"))

    def open_push_stream(self) -> requests.Response:
        """建立推送消息长连接，返回原始响应对象供逐帧读取。"""
        self._check_ready()
        response = self._session.post(
            self._url("PushMessage"),
            headers=self._headers(),
            data=encode_frame(b""),
            stream=True,
            timeout=(self.connect_timeout, self.read_timeout),
        )
        header_status, header_message = self._header_status(response)
        if header_status not in (None, 0):
            response.close()
            raise CloudDriveError(header_status, header_message or "CloudDrive2 拒绝订阅")
        if response.status_code >= 400:
            response.close()
            raise CloudDriveError(None, f"CloudDrive2 返回 HTTP {response.status_code}")
        return response


class PushSubscriber:
    """后台守护线程，订阅 CloudDrive2 推送消息流并按需指数退避重连。"""

    def __init__(
        self,
        client: CloudDriveWebClient,
        handler: Callable[[Dict[str, Any]], None],
        debounce_logger=None,
    ):
        """保存客户端与消息处理回调。"""
        self._client = client
        self._handler = handler
        self._logger = debounce_logger or logger
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._connected = False
        self._message_count = 0
        self._last_message_at = 0.0
        self._last_error = ""
        self._reconnects = 0

    def start(self) -> None:
        """启动订阅线程（重复调用不产生第二个线程）。"""
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run, name="Cd2PushSubscriber", daemon=True
            )
            self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """停止订阅线程。"""
        self._stop_event.set()
        with self._lock:
            thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout)
        self._connected = False

    def reset_stats(self) -> None:
        """重置运行时计数（累计通知数、重连次数、最近错误）。"""
        with self._lock:
            self._message_count = 0
            self._last_message_at = 0.0
            self._last_error = ""
            self._reconnects = 0

    def status(self) -> Dict[str, Any]:
        """返回订阅状态快照。"""
        return {
            "connected": self._connected,
            "message_count": self._message_count,
            "last_message_at": self._last_message_at,
            "last_error": self._last_error,
            "reconnects": self._reconnects,
            "running": bool(self._thread and self._thread.is_alive()),
        }

    def _run(self) -> None:
        """订阅主循环：空闲超时立即重连，真实故障按 5→300 秒退避。"""
        delay = 5
        while not self._stop_event.is_set():
            idle_timeout = False
            try:
                self._consume()
                delay = 5
            except Exception as err:  # pylint: disable=broad-except
                if is_idle_timeout(err):
                    # 空闲超时立即重连；若按故障退避，漏通知窗口会不断放大。
                    idle_timeout = True
                    self._last_error = ""
                else:
                    self._last_error = str(err)
                    self._logger.warning(f"CloudDrive2 推送订阅中断：{err}")
            finally:
                self._connected = False
            if self._stop_event.is_set():
                break
            self._reconnects += 1
            if idle_timeout:
                # 立即重连但保留 1 秒间隔，避免对端异常时形成忙循环
                self._stop_event.wait(1)
                continue
            self._stop_event.wait(delay)
            delay = min(delay * 2, 300)

    def _consume(self) -> None:
        """消费一次长连接，直到断开或收到停止信号。"""
        response = self._client.open_push_stream()
        self._connected = True
        self._last_error = ""
        self._logger.info("CloudDrive2 推送订阅已连接")
        try:
            for flags, chunk in iter_frames(response):
                if self._stop_event.is_set():
                    break
                if flags & 0x80:
                    status, message = parse_trailer(chunk)
                    if status not in (None, 0):
                        raise CloudDriveError(status, message or "CloudDrive2 推送流结束")
                    continue
                message = parse_push_message(chunk)
                if not message or "change_type" not in message:
                    continue
                self._message_count += 1
                self._last_message_at = time.time()
                try:
                    self._handler(message)
                except Exception as err:  # pylint: disable=broad-except
                    self._logger.error(f"处理 CloudDrive2 变更事件失败：{err}")
        finally:
            response.close()
