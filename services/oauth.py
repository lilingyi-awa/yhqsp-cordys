from .commons import http, OAuthRegisterToken, Session, OAuthRequests, Registration, LoginRequests, NAME_MATCH, INT_MATCH, getMiRootSec
import time
import random
from fastapi.responses import RedirectResponse
import sqlalchemy as sa
from config import MISSKEY_DOMAIN, YUNHU_OAUTH_CLIENTID, YUNHU_OAUTH_CLIENTSEC
import re
from .basics import encore_make_login
import aiohttp
from urllib.parse import quote
from fastapi.responses import HTMLResponse, RedirectResponse
import fastapi
from . import eapis

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
            secret = "".join(random.choice("1234567890qwertyuiopasdfghjklzxcvbnmQWERTYUIOPASDFGHJKLZXCVBNM") for _ in range(0, 32))
            await session.merge(OAuthRegisterToken(
                uid=int(user_id),
                secret=secret,
                expires=int(time.time()) + 600,
            ))
            req = RedirectResponse("/yunhubot/oauth/register.html", 302)
            req.set_cookie("r5ckip2PFs3w6JK_uid", user_id)
            req.set_cookie("r5ckip2PFs3w6JK_token", secret)
            return req
        else:
            return await encore_make_login(account.userName)

OAUTH_REGISTER_HTML = open('./oauth-register.html', "r", encoding="utf-8").read()
@http.get("/yunhubot/oauth/register.html")
async def oauth_register_page(req: fastapi.Request):
    if "r5ckip2PFs3w6JK_uid" not in req.cookies or not re.match(r"^[1-9][0-9]+$", req.cookies["r5ckip2PFs3w6JK_uid"]):
        return RedirectResponse("/", 302)
    if "r5ckip2PFs3w6JK_token" not in req.cookies or not re.match(r"^[0-9a-zA-Z]{32}$", req.cookies["r5ckip2PFs3w6JK_token"]):
        return RedirectResponse("/", 302)
    async with Session() as session:
        uid = int(req.cookies["r5ckip2PFs3w6JK_uid"])
        secret = req.cookies["r5ckip2PFs3w6JK_token"]
        if (p := await session.scalar(
            sa.select(OAuthRegisterToken)
            .where(OAuthRegisterToken.uid == uid)
            .where(OAuthRegisterToken.secret == secret)
        )) is None:
            return RedirectResponse("/", 302)
        if (m := await session.scalar(sa.select(Registration).where(Registration.yunhuId == uid))) is not None:
            await session.delete(p)
            await session.commit()
            return await encore_make_login(m.userName)
    return HTMLResponse(OAUTH_REGISTER_HTML.replace("{{YUNHU_UID}}", str(uid)))

@http.get("/yunhubot/oauth/register-api")
async def oauth_register_page(req: fastapi.Request, username: str):
    if not NAME_MATCH.match(username):
        return {"code": "name_invalid"}
    if "r5ckip2PFs3w6JK_uid" not in req.cookies or not INT_MATCH.match(req.cookies["r5ckip2PFs3w6JK_uid"]):
        return {"code": "unauthorized"}
    if "r5ckip2PFs3w6JK_token" not in req.cookies or not re.match(r"^[0-9a-zA-Z]{32}$", req.cookies["r5ckip2PFs3w6JK_token"]):
        return {"code": "unauthorized"}
    async with Session() as session:
        uid = int(req.cookies["r5ckip2PFs3w6JK_uid"])
        secret = req.cookies["r5ckip2PFs3w6JK_token"]
        if (p := await session.scalar(
            sa.select(OAuthRegisterToken)
            .where(OAuthRegisterToken.uid == uid)
            .where(OAuthRegisterToken.secret == secret)
        )) is None:
            return RedirectResponse("/", 302)
        if (m := await session.scalar(sa.select(Registration).where(Registration.yunhuId == uid))) is not None:
            username = m.userName
        else:
            if (m := await session.scalar(sa.select(Registration).where(Registration.userName == username))) is not None:
                return {"code": "name_conflict"}
            ok, mid = await eapis.createAccount(username, secret[:15], getMiRootSec)
            if ok == "duplicate":
                return {"code": "name_conflict"}
            elif ok != "ok":
                return {"code": "fatal"}
            session.add(Registration(
                userId=mid,
                userName=username,
                yunhuId=uid,
                robotOwner=uid,
            ))
        await session.delete(p)
        rid = (int(time.time() * 1000 - 1767787667721) << 10) + random.randrange(0, 2048)
        secret = ''.join(random.choice('1234567890qwertyuiopasdfghjklzxcvbnmQWERTYUIOPASDFGHJKLMNBVCXZ') for _ in range(0, 32))
        session.add(LoginRequests(
            rid=rid,
            secret=secret,
            userName=username,
        ))
        await session.commit()
        return {"code": "ok", "rid": rid, "secret": secret}
