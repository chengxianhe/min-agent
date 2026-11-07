"""QR login. The owner must scan and confirm on their own phone."""
import time
import urllib.parse

from .files import read_json, save_json
from .ilink import BASE_URL, LinkError, request, trusted_base


def login(directory, stop, transport=request, timeout=300):
    ui = directory / "connection.json"
    save_json(ui, {"status": "loading", "message": "正在获取微信二维码…"})
    qr = transport(BASE_URL, "get_bot_qrcode?bot_type=3", {"local_token_list": []})
    if not all(isinstance(qr.get(k), str) and qr[k] for k in ("qrcode", "qrcode_img_content")):
        raise LinkError("微信没有返回有效二维码")
    payload = qr["qrcode_img_content"]
    base, verify_code, previous = BASE_URL, "", ""
    deadline = time.monotonic() + timeout
    while not stop.is_set() and time.monotonic() < deadline:
        code_file = directory / "verify-code.json"
        if code_file.exists():
            code = read_json(code_file).get("code", "")
            code_file.unlink()
            if isinstance(code, str) and code.isascii() and code.isdigit() and 4 <= len(code) <= 12:
                verify_code = code
        query = {"qrcode": qr["qrcode"]}
        if verify_code:
            query["verify_code"] = verify_code
        if not previous:
            save_json(ui, {"status": "wait", "message": "用你的个人微信扫一扫，然后在手机上确认。",
                           "qr": payload})
            previous = "wait"
        try:
            value = transport(base, "get_qrcode_status?" + urllib.parse.urlencode(query))
        except LinkError as error:
            if error.expired:
                raise
            save_json(ui, {"status": "wait", "message": str(error) + "，正在重试…", "qr": payload})
            stop.wait(2)
            continue
        status = value.get("status")
        if status == "confirmed":
            token, owner, bot = value.get("bot_token"), value.get("ilink_user_id"), value.get("ilink_bot_id")
            if not all(isinstance(v, str) and v.strip() for v in (token, owner, bot)):
                raise LinkError("微信未返回完整本人身份信息；为避免接收陌生人任务，连接已停止")
            credentials = {"token": token, "owner": owner, "bot_id": bot,
                           "base_url": trusted_base(value.get("baseurl") or BASE_URL), "bound_at": time.time()}
            save_json(directory / "credentials.json", credentials)
            save_json(ui, {"status": "connected", "message": "已连接。现在可以在微信里发文字任务。"})
            return credentials
        if status in ("expired", "verify_code_blocked", "binded_redirect"):
            messages = {"expired": "二维码已过期，请重新启动连接获取新码。",
                        "verify_code_blocked": "配对码验证已被限制，请稍后重试。",
                        "binded_redirect": "这个连接已被绑定；请在微信中检查原连接，不会覆盖其他客户端。"}
            raise LinkError(messages[status])
        if status == "scaned_but_redirect":
            base = trusted_base("https://" + value.get("redirect_host", ""))
        elif status == "need_verifycode":
            save_json(ui, {"status": "need_verifycode", "qr": payload,
                           "message": "请在下方输入手机微信显示的数字。" if not verify_code else "配对码未通过，请重新输入。"})
            verify_code = ""
        elif status in ("scaned", "wait"):
            if status == "scaned":
                verify_code = ""
            save_json(ui, {"status": status, "qr": payload, "message":
                          "已扫码，请在微信确认连接。" if status == "scaned" else "请使用个人微信扫一扫。"})
        else:
            raise LinkError("微信返回了暂不支持的登录状态，连接已停止")
        previous = status
        stop.wait(1)
    raise LinkError("连接已取消或二维码等待超时，请重新启动连接。")
