import asyncio
import fastapi
import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from config import SQLALCHEMY_URL, YUNHU_VERIFY_KEY, MISSKEY_DOMAIN, MISSKEY_SQLALCHEMY_URL, MISSKEY_ROOT_USER, DEFAULT_FOLLOW
from config import DIRECT_SOURCE, YUNHU_OAUTH_CLIENTID, YUNHU_OAUTH_CLIENTSEC, REQUEST_DELIVER_TO
import eapis
import re
import random
from contextlib import asynccontextmanager
from fastapi.responses import RedirectResponse, HTMLResponse
import typing
import time
import json
import aiohttp
from urllib.parse import quote

ORMBase = type("ORMBase", (DeclarativeBase, ), {})
engine = create_async_engine(SQLALCHEMY_URL)
mi_engine = create_async_engine(MISSKEY_SQLALCHEMY_URL)
Session = async_sessionmaker(engine)
miRootSec = ""

@asynccontextmanager
async def lifespan(_):
    global miRootSec
    token = await get_misskey_utoken(MISSKEY_ROOT_USER)
    assert token is not None
    miRootSec = token
    async with engine.begin() as conn:
        await conn.run_sync(ORMBase.metadata.create_all)
        del conn
    asyncio.create_task(expire_clearer())
    yield

http = fastapi.FastAPI(lifespan=lifespan)

class Registration(ORMBase):
    __tablename__ = "registration"
    userName: str = sa.Column(sa.String(45).with_variant(sa.String(45, 'ascii_bin'), 'mysql', 'mariadb'), primary_key=True)
    yunhuId: typing.Optional[int] = sa.Column(sa.BigInteger(), nullable=True, unique=True)
    robotOwner: typing.Optional[int] = sa.Column(sa.BigInteger(), nullable=True)
    userId: str = sa.Column(sa.String(45).with_variant(sa.String(45, 'ascii_bin'), 'mysql', 'mariadb'), nullable=True, unique=True)

class LoginRequests(ORMBase):
    __tablename__ = "login_request"
    rid: int = sa.Column(sa.BigInteger(), primary_key=True, autoincrement=False)
    secret: str = sa.Column(sa.String(32).with_variant(sa.String(32, 'ascii_bin'), 'mysql', 'mariadb'), nullable=False)
    userName: str = sa.Column(sa.Text(), nullable=False)
    expires: int = sa.Column(sa.BigInteger(), nullable=False, default=lambda: int(time.time()) + 600)

class OAuthRequests(ORMBase):
    __tablename__ = "oauth_request"
    rid1: int = sa.Column(sa.BigInteger(), primary_key=True, autoincrement=False)
    rid2: str = sa.Column(sa.String(32).with_variant(sa.String(32, 'ascii_bin'), 'mysql', 'mariadb'), primary_key=True)
    expires: int = sa.Column(sa.BigInteger(), nullable=False, default=lambda: int(time.time()) + 600)

async def expire_clearer():
    while True:
        try:
            async with Session() as sess:
                await sess.execute(
                    sa.delete(LoginRequests)
                    .where(LoginRequests.expires < int(time.time()))
                )
                await sess.execute(
                    sa.delete(OAuthRequests)
                    .where(OAuthRequests.expires < int(time.time()))
                )
        except Exception:
            pass
        await asyncio.sleep(2)

NAME_MATCH = re.compile(r"^[a-z0-9]{3,20}$")
INT_MATCH = re.compile(r"^[1-9][0-9]*$")

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
        result, userId = await eapis.createAccount(username, password, rootSec=miRootSec)
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
        repass = await eapis.rescuePassword(prereg.userId, rootSec=miRootSec)
        await eapis.deliverMessage(
            uid=uid,
            message=f"账户重设成功！\n用户名：{prereg.userName}\n密码：{repass}",
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
    if code["header"]["eventType"] == "bot.shortcut.menu":
        if code["event"]["menuId"] == "VO9SDAQ9":
            asyncio.create_task(quicklogin(int(code["event"]["senderId"])))

@http.get("/identicon/{name}")
async def identicon(name: str):
    if name == "":
        return RedirectResponse("https://cn.cravatar.com/avatar/")
    name = name.split("@")
    if len(name) != 2 or name[1] != MISSKEY_DOMAIN:
        return RedirectResponse("https://cn.cravatar.com/avatar/")
    name = name[0]
    async with Session() as session:
        if (prereg := await session.scalar(sa.select(Registration).where(Registration.userName == name))) is None:
            return RedirectResponse("https://cn.cravatar.com/avatar/")
        if prereg.yunhuId is None:
            return RedirectResponse("https://cn.cravatar.com/avatar/")
        return RedirectResponse(await eapis.getAvatarUrl(prereg.yunhuId))

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

async def get_misskey_utoken(username: str) -> typing.Optional[str]:
    async with mi_engine.begin() as conn:
        return await conn.scalar(
            sa.text('SELECT "user"."token" FROM "user" where "user"."username" = :username and "user"."host" is null'),
            {"username": username},
        )

@http.get("/files/{webpublickey}")
async def webpublic(webpublickey: str, req: fastapi.Request):
    SQL = 'SELECT uri FROM drive_file WHERE "webpublicAccessKey" = :key LIMIT 1'
    async with mi_engine.begin() as conn:
        uri = await conn.scalar(sa.text(SQL), {"key": webpublickey})
        if not isinstance(uri, str) or uri == "":
            return fastapi.responses.Response(status_code=404)
        for allowance in DIRECT_SOURCE:
            if uri.startswith(allowance):
                return fastapi.responses.RedirectResponse(uri)
    async def reader_iv():
        async with aiohttp.ClientSession() as sess:
            result = await sess.get(
                url=uri,
                headers={k: v for k, v in req.headers.items() if k.lower() in ["range", "sec-fetch-dest", "sec-fetch-mode"]}
            )
            yield result.status
            if result.status >= 400:
                yield {}
                yield b""
                return
            yield result.headers
            ran = result.content
            while True:
                block = await ran.readany()
                if not block:
                    break
                yield block
    iv = reader_iv()
    status = await iv.asend(None)
    mutter = await iv.asend(None)
    return fastapi.responses.StreamingResponse(
        iv,
        status_code=status,
        headers={k: v for k, v in mutter.items() if k.lower() in [
            "content-length",
            "content-range",
            "accept-ranges",
            "etag",
            "last-modified",
        ]},
        media_type=mutter.get("Content-Type", "image/webp"),
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

@http.get("/yunhubot/oauth-invoke")
async def oauth_invoke():
    rid1 = (int(time.time() * 1000 - 1773475653968) << 10) + random.randrange(0, 2048)
    rid2 = ''.join(random.choice('1234567890qwertyuiopasdfghjklzxcvbnmQWERTYUIOPASDFGHJKLMNBVCXZ') for _ in range(0, 32))
    async with Session() as session:
        session.add(OAuthRequests(rid1=rid1, rid2=rid2))
        await session.commit()
    goto = "https://oauth2.jwzhd.com/oauth/authorize"
    goto += f"?response_type=code&client_id={YUNHU_OAUTH_CLIENTID}"
    goto += f"&redirect_uri=https://{MISSKEY_DOMAIN}/yunhubot/oauth&callback&scope=profile&state={rid1}-{rid2}"
    return RedirectResponse(goto)

@http.get("/yunhubot/oauth")
async def oauth_receive(code: str, state: str):
    if not re.match(r"^[1-9][0-9]*\-[0-9a-zA-Z]{32}$", state):
        return RedirectResponse("/")
    rid1, rid2 = state.split("-")
    async with Session() as session:
        bob = await session.scalar(sa.select(OAuthRequests).where(OAuthRequests.rid1 == rid1).where(OAuthRequests.rid2 == rid2))
        if bob is None:
            return RedirectResponse("/")
        await session.execute(sa.delete(OAuthRequests).where(OAuthRequests.rid1 == rid1).where(OAuthRequests.rid2 == rid2))
        await session.commit()
    async with aiohttp.ClientSession() as session:
        result = await session.post(
            url="https://oauth2.jwzhd.com/oauth/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data=(
                "grant_type=authorization_code"
                f"&code={quote(code)}"
                f"&redirect_uri=https://{MISSKEY_DOMAIN}/yunhubot/oauth"
                f"&client_id={YUNHU_OAUTH_CLIENTID}&client_secret={YUNHU_OAUTH_CLIENTSEC}"
            ),
        )
        result = await result.json()
        if "access_token" not in result:
            return RedirectResponse("/")
        access_token = result["access_token"]
        userdoc = await session.get(url="https://oauth2.jwzhd.com/api/userinfo", headers={"Authorization": "Bearer " + access_token})
        userdoc = await userdoc.json()
        user_id = userdoc["user_id"]
    async with Session() as session:
        if (account := await session.scalar(sa.select(Registration).where(Registration.yunhuId == int(user_id)))) is None:
            repo = """
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"/><title>提示</title><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body><p>您还没有注册账户，请在Cordys处操作完成注册。</p>
<ul><li>机器人ID：91975597</li>
<li>机器人链接：<a href="https://yhfx.jwznb.com/share?key=k8PKWfRWUGT0&ts=1773482829" style="color: black;">https://yhfx.jwznb.com/share?key=k8PKWfRWUGT0&ts=1773482829</a></li></ul>
</body></html>
"""
            return HTMLResponse(repo)
        else:
            return await encore_make_login(account.userName)

@http.get('/nodeinfo/{version}')
def nodeinfo(version: str):
    return fastapi.responses.JSONResponse({
        "version": version,
        "software": {
            "name": "sinokey",
            "version": "2026.3.1-liliko",
            "homepage": "https://misskey-social.com.cn"
        },
        "protocols": [
            "activitypub",
        ],
        "services": {
            "inbound": [],
            "outbound": [
                "atom1.0",
                "rss2.0"
            ]
        },
        # Vanity Claims
        "usage": {
            "users": {
                "total": int((time.time() - 1700000000) * 8.0),
                "activeHalfyear": int((time.time() - 1700000000) * 3.1),
                "activeMonth": int((time.time() - 1700000000) * 0.91),
            },
            "localPosts": int((time.time() - 1500000000) * 19.6),
            "localComments": int((time.time() - 1220000000) * 27.1),
        },
        "openRegistrations": True,
        "metadata": {
            "nodeName": "lilikoBBS",
            "nodeDescription": "lilikoBBS（aka. 云湖QSpace）是一个普通的联邦宇宙实例。",
            "nodeAdmins": [
                {
                    "name": "Prenext Inc.",
                    "email": "alan_sudo@yeah.net"
                }
            ],
            "maintainer": {
                "name": "Prenext Inc.",
                "email": "alan_sudo@yeah.net"
            },
            "langs": ["zh"],
        },
    }, headers={
        "Content-Type": f"application/json; profile=\"http://nodeinfo.diaspora.software/ns/schema/{version}#\"; charset=utf-8",
    })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(http, host="0.0.0.0", port=14928)