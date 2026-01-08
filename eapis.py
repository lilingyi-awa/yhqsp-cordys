import aiohttp
from config import YUNHU_SECRET_KEY, MISSKEY_DOMAIN
import typing

async def createAccount(name: str, password: str, rootSec: str) -> tuple[typing.Literal["ok", "authfail", "duplicate", "fatal"], str]:
    try:
        async with aiohttp.ClientSession() as session:
            result = await session.post(
                url=f"https://{MISSKEY_DOMAIN}/api/admin/accounts/create",
                json={
                    "username": name,
                    "password": password,
                    "i": rootSec,
                }
            )
            if result.status == 200:
                code = await result.json()
                return ("ok", code["id"])
            if result.status in (400, 401, 403):
                return ("authfail", "")
            if result.status == 500:
                code = await result.json()
                if code["error"]["info"]["e"]["message"] == "DUPLICATED_USERNAME":
                    return ("duplicate", "")
            return ("fatal", "")
    except Exception:
        return ("fatal", "")

async def rescuePassword(userId: str, rootSec: str) -> str:
    async with aiohttp.ClientSession() as session:
        result = await session.post(
            url="https://sk.lilingyi-awa.top/api/admin/reset-password",
            json={
                "userId": userId,
                "i": rootSec,
            }
        )
        assert result.status == 200
        return (await result.json())["password"]

async def deliverMessage(uid: int, message: str, mtype: str = "text", buttons: list[dict] = []):
    async with aiohttp.ClientSession() as session:
        await session.post(
            url=f"https://chat-go.jwzhd.com/open-apis/v1/bot/send?token={YUNHU_SECRET_KEY}",
            json={
                "recvId": str(uid),
                "recvType": "user",
                "contentType": mtype,
                "content": {
                    "text": message,
                    "buttons": buttons,
                },
            },
        )

async def getAvatarUrl(uid: int):
    async with aiohttp.ClientSession() as session:
        custodian = (await (await session.get(url=f"https://chat-web-go.jwzhd.com/v1/user/homepage?userId={uid}")).json())["data"]["user"]
        if custodian["userId"] == "https://cn.cravatar.com/avatar/":
            return None
        avatarUrl: str = custodian["avatarUrl"]
        if avatarUrl.startswith("https://chat-img.jwznb.com/"):
            avatarUrl = "https://jwznb-static.lilingyi-awa.top/" + avatarUrl.removeprefix("https://chat-img.jwznb.com/")
        return avatarUrl

async def fetchUserdoc(token: str) -> dict:
    async with aiohttp.ClientSession() as session:
        result = await session.post(
            url=f"https://{MISSKEY_DOMAIN}/api/i",
            json={"i": token}
        )
        doc = await result.json()
        doc["token"] = token
        return doc