import fastapi
from config import YUNHU_VERIFY_KEY
import asyncio
from .commons import http
from .basics import registration, rescue, whoami, whoisthey, quicklogin, quicklogin_ias, accept_fun_request, safelockdown
from .clientlogin import CLIENT_REGISTER_MATCH, attach_client_login
from .contents import commit_content

@http.post("/yunhubot/receive")
async def accept(req: fastapi.Request, secret: str):
    if secret != YUNHU_VERIFY_KEY:
        return None
    code = await req.json()
    if code["header"]["eventType"] == "message.receive.instruction":
        if code["event"]["message"]["commandId"] == 2234:
            asyncio.create_task(registration(
                uid=int(code["event"]["sender"]["senderId"]),
                username=code["event"]["message"]["content"]["text"],
                nickname=code["event"]["sender"]["senderNickname"],
            ))
        if code["event"]["message"]["commandId"] == 2235:
            asyncio.create_task(rescue(int(code["event"]["sender"]["senderId"])))
        if code["event"]["message"]["commandId"] == 2236:
            asyncio.create_task(whoami(int(code["event"]["sender"]["senderId"])))
        if code["event"]["message"]["commandId"] == 2239:
            asyncio.create_task(whoisthey(
                uid=int(code["event"]["sender"]["senderId"]),
                query=code["event"]["message"]["content"]["text"],
            ))
        if code["event"]["message"]["commandId"] == 2240:
            asyncio.create_task(quicklogin(int(code["event"]["sender"]["senderId"])))
        if code["event"]["message"]["commandId"] == 2273:
            asyncio.create_task(quicklogin_ias(int(code["event"]["sender"]["senderId"]), code["event"]["message"]["content"]["text"]))
        if code["event"]["message"]["commandId"] == 2357:
            asyncio.create_task(accept_fun_request(
                code["event"]["sender"]["senderId"],
                code["event"]["sender"]["senderNickname"],
                code["event"]["message"]["content"]["text"]
            ))
        if code["event"]["message"]["commandId"] == 2441:
            asyncio.create_task(safelockdown(int(code["event"]["sender"]["senderId"])))
        if code["event"]["message"]["commandId"] == 2540:
            asyncio.create_task(commit_content(int(code["event"]["sender"]["senderId"]), code["event"]["message"]["content"]["formJson"]))
    if code["header"]["eventType"] == "message.receive.normal":
        if code["event"]["message"]["contentType"] == "text":
            text = code["event"]["message"]["content"]["text"]
            if (m := CLIENT_REGISTER_MATCH.match(text)):
                asyncio.create_task(attach_client_login(int(code["event"]["sender"]["senderId"]), m.group(1)))
    if code["header"]["eventType"] == "bot.shortcut.menu":
        if code["event"]["menuId"] == "VO9SDAQ9":
            asyncio.create_task(quicklogin(int(code["event"]["senderId"])))
