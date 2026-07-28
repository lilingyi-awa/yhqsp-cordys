from .commons import Session, get_misskey_utoken, Registration
import aiohttp
from config import MISSKEY_DOMAIN
import sqlalchemy as sa
from . import eapis

async def commit_content(uid: int, forms: dict):
    forms = {v["label"]: v for v in forms.values()}
    async with Session() as session:
        userName = await session.scalar(sa.select(Registration.userName).where(Registration.yunhuId == uid))
    if userName is None:
        await eapis.deliverMessage(uid, "错误：您尚未注册QSpace账户！")
        return
    text = forms["帖子内容"]["value"]
    cw = forms["内容警告"]["value"]
    if len(text) <= 0:
        await eapis.deliverMessage(uid, "请输入帖子内容！")
        return
    if len(text) > 1000:
        await eapis.deliverMessage(uid, "帖子内容过长（最多3000字）！")
        return
    if len(cw) > 100:
        await eapis.deliverMessage(uid, "内容警告过长（最多100字）！")
        return
    if cw == "":
        cw = None
    token = await get_misskey_utoken(userName)
    async with aiohttp.ClientSession() as session:
        result = await session.post(
            url=f"https://{MISSKEY_DOMAIN}/api/notes/create",
            json={
                "text": text,
                "visibility": {
                    "公开": "public",
                    "悄悄公开": "home",
                    "仅关注": "followers",
                }.get(forms["可见性"]["selectValue"], "public"),
                "localOnly": (not forms["参与联邦宇宙"]["value"]),
                "cw": cw,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        status = result.status
        result = await result.json()
    if status == 200:
        await eapis.deliverMessage(uid, f"帖子发布成功：https://{MISSKEY_DOMAIN}/notes/{result['createdNote']['id']}")
        return
    try:
        error = {
            "NO_SUCH_REPLY_TARGET": "回帖目标不存在。",
            "CANNOT_REPLY_TO_AN_INVISIBLE_NOTE": "回帖目标不存在。",
            "CANNOT_REPLY_TO_A_PURE_RENOTE": "回帖目标不存在。",
            "CANNOT_REPLY_TO_SPECIFIED_VISIBILITY_NOTE_WITH_EXTENDED_VISIBILITY": "回帖目标不存在。",
            "YOU_HAVE_BEEN_BLOCKED": "由于对方隐私设置，您不可以回帖。",
            "CONTAINS_TOO_MANY_MENTIONS": "您@了太多的人。",
            "RATE_LIMIT_EXCEEDED": "操作次数过多，请休息一下再发帖。",
            "CREDENTIAL_REQUIRED": "系统内部错误 140",
            "AUTHENTICATION_FAILED": "系统内部错误 141",
            "INTERNAL_ERROR": "系统内部错误 131",
            "INVALID_PARAM": "系统内部错误 167",
        }.get(result["error"]["code"], "Misskey层错误：" + result["error"]["message"])
    except KeyError:
        error = "系统内部错误 162"
    await eapis.deliverMessage(uid, f"帖子发布失败。\n{error}")

