"""Text-only iLink adapter, based on Tencent's public plugin 2.4.10 protocol.

No SDK execution, HTTP redirects, arbitrary recipients, or credential logging.
"""
import base64
import json
import secrets
import socket
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://ilinkai.weixin.qq.com"
VERSION = "2.4.10"


class LinkError(Exception):
    def __init__(self, message, expired=False):
        super().__init__(message)
        self.expired = expired


def trusted_base(value):
    parsed = urllib.parse.urlsplit(value)
    host = parsed.hostname or ""
    if (parsed.scheme != "https" or not host.endswith(".weixin.qq.com")
            or parsed.username or parsed.password or parsed.port not in (None, 443)
            or parsed.query or parsed.fragment or parsed.path not in ("", "/")):
        raise LinkError("微信接口地址未通过校验")
    return "https://" + host


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(base, endpoint, body=None, token="", timeout=35):
    headers = {"iLink-App-Id": "bot", "iLink-App-ClientVersion": str(0x02040A),
               "Content-Type": "application/json", "AuthorizationType": "ilink_bot_token",
               "X-WECHAT-UIN": base64.b64encode(str(secrets.randbits(32)).encode()).decode()}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(trusted_base(base) + "/ilink/bot/" + endpoint,
                                 data=data, headers=headers)
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=timeout) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise LinkError("微信响应过大")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError()
    except urllib.error.HTTPError as error:
        raise LinkError("微信 HTTP 错误：" + str(error.code), error.code in (401, 403)) from None
    except (socket.timeout, TimeoutError):
        raise LinkError("微信请求超时") from None
    except (OSError, ValueError):
        raise LinkError("微信网络或响应异常") from None
    if value.get("ret", 0) != 0 or value.get("errcode", 0) != 0:
        code = value.get("errcode") or value.get("ret")
        # Server text may contain credentials. Only expose numeric codes.
        safe_code = str(code) if isinstance(code, int) else "未知"
        raise LinkError("微信接口错误：" + safe_code, code == -14)
    return value


class Client:
    def __init__(self, credentials, transport=request):
        self.base = trusted_base(credentials["base_url"])
        self.token = credentials["token"]
        self.owner = credentials["owner"]
        self.transport = transport
        if not self.token or not self.owner:
            raise LinkError("绑定信息不完整；拒绝启用")

    def post(self, endpoint, payload):
        return self.transport(self.base, endpoint, {
            **payload, "base_info": {"channel_version": VERSION, "bot_agent": "MinAgent/0.1"}},
            token=self.token)

    def updates(self, cursor):
        return self.post("getupdates", {"get_updates_buf": cursor})

    def send(self, text, context, client_id):
        if not context:
            raise LinkError("缺少回复上下文")
        return self.post("sendmessage", {"msg": {
            "from_user_id": "", "to_user_id": self.owner, "client_id": client_id,
            "message_type": 2, "message_state": 2, "context_token": context,
            "item_list": [{"type": 1, "text_item": {"text": text}}]}})
