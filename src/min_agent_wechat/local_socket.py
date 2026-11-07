"""Bounded WebSocket JSON-RPC over an existing user's Unix socket, no daemon start."""
import base64
import hashlib
import json
import os
from pathlib import Path
import socket
import stat
import struct
import time
import uuid

MAX_MESSAGE = 4 * 1024 * 1024


class TransportError(Exception):
    pass


class RpcError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__("Codex 拒绝请求（错误码 " + str(code) + "）")


class LocalSocket:
    def __init__(self, path, timeout=12):
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.timeout = timeout
        try:
            path = Path(path).resolve(strict=True)
            info = path.stat()
            if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
                raise TransportError("控制通道必须是当前用户的本地 socket")
            self.socket.settimeout(timeout)
            self.socket.connect(str(path))
            key = base64.b64encode(os.urandom(16)).decode()
            self.socket.sendall(("GET / HTTP/1.1\r\nHost: localhost\r\nUpgrade: websocket\r\n"
                "Connection: Upgrade\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: " + key + "\r\n\r\n").encode())
            header = bytearray()
            while not header.endswith(b"\r\n\r\n"):
                header.extend(self._exact(1))
                if len(header) > 16384:
                    raise TransportError("控制通道握手过大")
            lines = bytes(header).decode("ascii").split("\r\n")
            headers = {k.lower().strip(): v.strip() for k, v in
                       (line.split(":", 1) for line in lines[1:] if ":" in line)}
            expected = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
            if (lines[0].split()[1] != "101" or headers.get("sec-websocket-accept") != expected
                    or headers.get("upgrade", "").lower() != "websocket"):
                raise TransportError("控制通道握手校验失败")
            self.call("initialize", {"clientInfo": {"name": "min_agent_wechat", "title": "WeChat card relay", "version": "0.2.0"},
                                     "capabilities": {"experimentalApi": True}})
            self._send(json.dumps({"method": "initialized", "params": {}}).encode())
        except Exception:
            self.close()
            raise

    def close(self):
        self.socket.close()

    def _exact(self, count):
        data = bytearray()
        while len(data) < count:
            chunk = self.socket.recv(count - len(data))
            if not chunk:
                raise TransportError("Codex 控制通道已断开")
            data.extend(chunk)
        return bytes(data)

    def _send(self, data, opcode=1):
        if len(data) > MAX_MESSAGE:
            raise TransportError("消息过大")
        mask = os.urandom(4)
        size = (bytes([128 | len(data)]) if len(data) < 126 else
                b"\xfe" + struct.pack("!H", len(data)) if len(data) <= 65535 else
                b"\xff" + struct.pack("!Q", len(data)))
        self.socket.sendall(bytes([128 | opcode]) + size + mask +
                            bytes(value ^ mask[index % 4] for index, value in enumerate(data)))

    def _receive(self, deadline):
        parts, total, fragmented = [], 0, False
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TransportError("Codex 响应超时")
            self.socket.settimeout(remaining)
            first, second = self._exact(2)
            opcode, final, size = first & 15, bool(first & 128), second & 127
            if first & 112 or second & 128:
                raise TransportError("不支持的 WebSocket 帧")
            if size == 126:
                size = struct.unpack("!H", self._exact(2))[0]
            elif size == 127:
                size = struct.unpack("!Q", self._exact(8))[0]
            if size > MAX_MESSAGE or total + size > MAX_MESSAGE:
                raise TransportError("Codex 响应过大")
            if opcode >= 8 and (not final or size > 125):
                raise TransportError("非法控制帧")
            data = self._exact(size)
            if opcode == 8:
                raise TransportError("Codex 控制通道已关闭")
            if opcode == 9:
                self._send(data, 10)
                continue
            if opcode == 10:
                continue
            if opcode not in (0, 1) or (opcode == 0) != fragmented:
                raise TransportError("不支持的消息分片")
            parts.append(data)
            total += size
            fragmented = not final
            if final:
                return json.loads(b"".join(parts))

    def call(self, method, params):
        identity = "wechat-" + uuid.uuid4().hex
        self.socket.settimeout(self.timeout)
        self._send(json.dumps({"id": identity, "method": method, "params": params}).encode())
        deadline = time.monotonic() + self.timeout
        while True:
            value = self._receive(deadline)
            if not isinstance(value, dict) or value.get("id") != identity:
                # Never answer unsolicited approval requests. Desktop remains the approver.
                continue
            if "error" in value:
                raise RpcError(value["error"].get("code"))
            if "result" not in value:
                raise TransportError("Codex 响应不完整")
            return value["result"]
