from . import eapis
import aiohttp
from .commons import get_misskey_utoken, NAME_MATCH, INT_MATCH, Session, Registration, mi_engine, LoginRequests, http, getMiRootSec
from config import MISSKEY_DOMAIN, DEFAULT_FOLLOW, REQUEST_DELIVER_TO
import random
import sqlalchemy as sa
import asyncio
from fastapi.responses import RedirectResponse, HTMLResponse
import json
import time

async def encore_make_login(userName: str):
    token = await get_misskey_utoken(userName)
    if token is None:
        return RedirectResponse("/")
    userdoc = await eapis.fetchUserdoc(token)
    with open("./loginer.js", "r", encoding="utf-8") as f:
        neojs = f.read()
    code = f"""
<!DOCTYPE html>
<html><head><meta charset="utf-8"/><title>登录中...</title></head><body><h1>登录中...</h1>
<script>
window.userAccount = {json.dumps(userdoc)};
localStorage.account = JSON.stringify(window.userAccount);
{neojs}
</script></body></html>
"""
    return HTMLResponse(code)

async def delegate_init(uid: int, username: str, nickname: str):
    token = await get_misskey_utoken(username)
    async with aiohttp.ClientSession() as session:
        await session.post(
            url=f"https://{MISSKEY_DOMAIN}/api/i/update",
            json={
                "name": nickname,
                "fields":[
                    {"name":"云湖号", "value":str(uid)}
                ],
                "i": token,
            }
        )
        for follow in DEFAULT_FOLLOW:
            await session.post(
                url=f"https://{MISSKEY_DOMAIN}/api/following/create",
                json={
                    "userId": follow,
                    "withReplies": True,
                    "i": token,
                }
            )

async def registration(uid: int, username: str, nickname: str):
    password = "".join(random.choice("1234567890qwertyuiopasdfghjklzxcvbnmQWERTYUIOPASDFGHJKLZXCVBNM") for _ in range(0, 12))
    if (INT_MATCH.match(username) and username != str(uid)) or not NAME_MATCH.match(username):
        await eapis.deliverMessage(
            uid=uid,
            message="您输入的用户名不合法！",
        )
        return
    async with Session() as session:
        if (prereg := await session.scalar(sa.select(Registration).where(Registration.yunhuId == uid))) is not None:
            await eapis.deliverMessage(
                uid=uid,
                message=f"您已经创建过账户，用户名：{prereg.userName}！如需创建多个账户，请联系管理员！",
            )
            return
        if (prereg := await session.scalar(sa.select(Registration).where(Registration.userName == username))) is not None:
            await eapis.deliverMessage(
                uid=uid,
                message=f"此用户名（{username}）已经被他人注册！",
            )
            return
        result, userId = await eapis.createAccount(username, password, rootSec=getMiRootSec())
        if result == "ok":
            asyncio.create_task(eapis.deliverMessage(
                uid=uid,
                message=f"账户注册成功！\n用户名：{username}\n初始密码：{password}",
            ))
            asyncio.create_task(delegate_init(uid, username, nickname))
            session.add(Registration(
                userName=username,
                yunhuId=uid,
                robotOwner=uid,
                userId=userId,
            ))
            await session.commit()
        elif result == "duplicate":
            asyncio.create_task(eapis.deliverMessage(
                uid=uid,
                message=f"此用户名（{username}）已经被他人注册！",
            ))
            session.add(Registration(userName=username))
            await session.commit()
        elif result == "authfail":
            await eapis.deliverMessage(
                uid=uid,
                message="内部密钥过期，请联系管理员！",
            )
        else:
            await eapis.deliverMessage(
                uid=uid,
                message="未知错误，请联系管理员！",
            )

async def rescue(uid: int):
    async with Session() as session:
        if (prereg := await session.scalar(sa.select(Registration).where(Registration.yunhuId == uid))) is None:
            await eapis.deliverMessage(
                uid=uid,
                message="您并未创建账户！",
            )
            return
    try:
        repass = await eapis.rescuePassword(prereg.userId, rootSec=getMiRootSec())
        await eapis.deliverMessage(
            uid=uid,
            message=f"账户重设成功！\n用户名：{prereg.userName}\n密码：{repass}",
        )
    except Exception:
        await eapis.deliverMessage(
            uid=uid,
            message="未知错误，请联系管理员！",
        )

async def safelockdown(uid: int):
    async with Session() as session:
        if (prereg := await session.scalar(sa.select(Registration).where(Registration.yunhuId == uid))) is None:
            await eapis.deliverMessage(
                uid=uid,
                message="您并未创建账户！",
            )
            return
    try:
        async with mi_engine.begin() as engine:
            ntoken = "".join(random.choice("qwertyuiopasdfghjklzxcvbnm1234567890QWERTYUIOPASDFGHJKLZXCVBNM") for _ in range(0, 16))
            await engine.execute(
                sa.text('UPDATE "user" SET "token" = :newtoken WHERE "id" = :userid'),
                {"userid": prereg.userId, "newtoken": ntoken},
            )
            await engine.execute(
                sa.text('UPDATE "user_profile" SET "password" = \'lockdowned\' WHERE "userId" = :userid'),
                {"userid": prereg.userId},
            )
            await engine.commit()
        await eapis.deliverMessage(
            uid=uid,
            message=f"账户落锁成功！",
        )
    except Exception:
        await eapis.deliverMessage(
            uid=uid,
            message="未知错误，请联系管理员！",
        )

async def whoami(uid: int):
    async with Session() as session:
        if (prereg := await session.scalar(sa.select(Registration).where(Registration.yunhuId == uid))) is None:
            await eapis.deliverMessage(
                uid=uid,
                message="您并未创建账户！",
            )
            return
    await eapis.deliverMessage(
        uid=uid,
        message=f"用户名：{prereg.userName}",
    )

async def whoisthey(uid: int, query: str):
    if not NAME_MATCH.match(query):
        await eapis.deliverMessage(
            uid=uid,
            message="未查询到记录！",
        )
    async with Session() as session:
        target = await session.scalar(sa.select(Registration).where(Registration.userName == query))
    if target is None:
        await eapis.deliverMessage(
            uid=uid,
            message="未查询到记录！",
        )
    if target.yunhuId is not None:
        await eapis.deliverMessage(
            uid=uid,
            message=f"账户名：{query}\n类型：用户账户\n云湖UID：{target.yunhuId}",
        )
    if target.robotOwner is not None:
        await eapis.deliverMessage(
            uid=uid,
            message=f"账户名：{query}\n类型：IAS账户\n云湖UID（创建者）：{target.robotOwner}",
        )
    else:
        await eapis.deliverMessage(
            uid=uid,
            message="账户名：{query}\n类型：IAS账户\n云湖UID（创建者）：无",
        )

async def accept_fun_request(uid: int, name: str, content: str):
    await eapis.deliverMessage(
        uid=REQUEST_DELIVER_TO,
        message=f"收到申请！\n申请者：{name}（{uid}）\n申请内容：\n{content}",
    )

async def quicklogin(uid: int):
    async with Session() as session:
        if (prereg := await session.scalar(sa.select(Registration).where(Registration.yunhuId == uid))) is None:
            await eapis.deliverMessage(
                uid=uid,
                message="您并未创建账户！",
            )
            return
        rid = (int(time.time() * 1000 - 1767787667721) << 10) + random.randrange(0, 2048)
        secret = ''.join(random.choice('1234567890qwertyuiopasdfghjklzxcvbnmQWERTYUIOPASDFGHJKLMNBVCXZ') for _ in range(0, 32))
        session.add(LoginRequests(
            rid=rid,
            secret=secret,
            userName=prereg.userName,
        ))
        del prereg
        await session.commit()
    await eapis.deliverMessage(
        uid=uid,
        message="请点击下面的按钮快捷登录（10分钟内有效，仅可使用一次）：",
        buttons=[
            {
                "text": "登录",
                "actionType": 1,
                "url": f"https://{MISSKEY_DOMAIN}/yunhubot/vslogin/{rid}/{secret}"
            }
        ],
    )

async def quicklogin_ias(uid: int, name: str):
    async with Session() as session:
        if (prereg := await session.scalar(sa.select(Registration).where(Registration.userName == name))) is None:
            await eapis.deliverMessage(
                uid=uid,
                message="IAS账户不存在！",
            )
            return
        if prereg.userId != uid and prereg.robotOwner != uid:
            await eapis.deliverMessage(
                uid=uid,
                message="不是您的IAS账户！",
            )
            return
        rid = (int(time.time() * 1000 - 1767787667721) << 10) + random.randrange(0, 2048)
        secret = ''.join(random.choice('1234567890qwertyuiopasdfghjklzxcvbnmQWERTYUIOPASDFGHJKLMNBVCXZ') for _ in range(0, 32))
        session.add(LoginRequests(
            rid=rid,
            secret=secret,
            userName=prereg.userName,
        ))
        del prereg
        await session.commit()
    await eapis.deliverMessage(
        uid=uid,
        message="请点击下面的按钮快捷登录（10分钟内有效，仅可使用一次）：",
        buttons=[
            {
                "text": "登录",
                "actionType": 1,
                "url": f"https://{MISSKEY_DOMAIN}/yunhubot/vslogin/{rid}/{secret}"
            }
        ],
    )

@http.get("/yunhubot/vslogin/{rid}/{secret}")
async def vslogin(rid: int, secret: str):
    async with Session() as session:
        record = await session.scalar(
            sa.select(LoginRequests)
            .where(LoginRequests.rid == rid)
            .where(LoginRequests.secret == secret)
            .where(LoginRequests.expires > int(time.time()))
        )
        if record is None:
            return RedirectResponse("/")
        userName = record.userName
        await session.execute(sa.delete(LoginRequests).where(LoginRequests.rid == rid))
        await session.commit()
        del record
    return await encore_make_login(userName)        
