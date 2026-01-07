import aiohttp
from config import MISSKEY_SECRET_KEY, YUNHU_SECRET_KEY, MISSKEY_DOMAIN
import typing

async def createAccount(name: str, password: str) -> tuple[typing.Literal["ok", "authfail", "duplicate", "fatal"], str]:
    try:
        async with aiohttp.ClientSession() as session:
            result = await session.post(
                url=f"https://{MISSKEY_DOMAIN}/api/admin/accounts/create",
                json={
                    "username": name,
                    "password": password,
                    "i": MISSKEY_SECRET_KEY,
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

async def rescuePassword(userId: str) -> str:
    async with aiohttp.ClientSession() as session:
        result = await session.post(
            url="https://sk.lilingyi-awa.top/api/admin/reset-password",
            json={
                "userId": userId,
                "i": MISSKEY_SECRET_KEY,
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

async def fetchUserdoc(token: str) -> dict:
    async with aiohttp.ClientSession() as session:
        result = await session.post(
            url=f"https://{MISSKEY_DOMAIN}/api/i",
            json={"i": token}
        )
        doc = await result.json()
        doc["token"] = token
        return doc