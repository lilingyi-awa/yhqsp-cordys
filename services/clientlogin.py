import re
from . import eapis
from .commons import http, Session, ClientLoginToken, Registration, get_misskey_utoken, getMiRootSec, NAME_MATCH
from fastapi.responses import JSONResponse
import time
import random
import sqlalchemy as sa
import hashlib
import fastapi

CLIENT_REGISTER_MATCH = re.compile(r"^client-register:([a-f0-9]{64})$")

async def attach_client_login(user_uid: int, token_sha256: str):
    async with Session() as session:
        await session.merge(ClientLoginToken(
            uid=user_uid,
            token_sha256=token_sha256,
            expires=int(time.time()) + 600,
        ))
        await session.commit()

@http.get("/yunhubot/thirdapp/login")
async def thirdapp_login(req: fastapi.Request, yunhuID: int, username: str = ""):
    if not req.headers.get("Authorization", "").startswith("Bearer "):
        return JSONResponse({"status": 401, "signal": "INVALID_REQUEST"}, 401)
    token = hashlib.sha256(req.headers.get("Authorization", "").removeprefix("Bearer ").encode("utf-8")).hexdigest()
    async with Session() as session:
        uid = await session.scalar(
            sa.select(ClientLoginToken.uid)
            .where(ClientLoginToken.uid == yunhuID)
            .where(ClientLoginToken.token_sha256 == token)
        )
        if uid is None:
            return JSONResponse({"status": 401, "signal": "TOKEN_NOT_EXISTS"}, 401)
        account = await session.scalar(sa.select(Registration.userName).where(Registration.yunhuId == uid))
    if account is not None:
        return JSONResponse({"status": 200, "signal": "FOUNDED", "username": account, "token": await get_misskey_utoken(account)})
    if username == "":
        return JSONResponse({"status": 404, "signal": "NEED_REGISTER"}, 404)
    if not NAME_MATCH.match(username):
        return JSONResponse({"status": 400, "signal": "INVALID_USERNAME"}, 400)
    random_pwd = "".join(random.choice("1234567890qwertyuiopasdfghjklzxcvbnmQWERTYUIOPASDFGHJKLZXCVBNM") for _ in range(0, 32))
    result, userId = await eapis.createAccount(username, random_pwd, getMiRootSec())
    if result == "duplicate":
        return JSONResponse({"status": 400, "signal": "DUPLICATED_USERNAME"}, 400)
    async with Session() as session:
        session.add(Registration(
            userName=username,
            userId=userId,
            yunhuId=yunhuID,
            robotOwner=yunhuID,
        ))
        await session.commit()
    return JSONResponse({"status": 200, "signal": "REGISTERED", "username": username, "token": await get_misskey_utoken(username)})

@http.get("/yunhubot/thirdapp/userinfo/{username}")
async def getUser(username: str):
    async with Session() as session:
        result = await session.scalar(
            sa.select(Registration)
            .where(Registration.userName == username)
        )
        if result is None:
            return JSONResponse({"code": 404}, 404)
        return JSONResponse({"code": 200, "info": {
            "yunhu_uid": result.robotOwner,
            "type": ("person" if (result.yunhuId is not None) else "ias"),
        }})

@http.get("/yunhubot/thirdapp/numberinfo/{uid}")
async def getNumber(uid: int):
    async with Session() as session:
        result = await session.scalar(
            sa.select(Registration.userName)
            .where(Registration.yunhuId == uid)
        )
        iasList = await session.execute(
            sa.select(Registration.userName)
            .where(Registration.robotOwner == uid)
            .where(Registration.yunhuId == None)
        )
        iasList = [i._tuple()[0] for i in iasList]
        if result is None:
            return JSONResponse({"code": 404}, 404)
        return JSONResponse({"code": 200, "username": result, "ias": iasList})
