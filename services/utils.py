from .commons import http, mi_engine, Registration, Session
from config import DIRECT_SOURCE, MISSKEY_DOMAIN
import fastapi
from .import eapis
import aiohttp
from fastapi.responses import RedirectResponse
import sqlalchemy as sa

@http.get("/identicon/{name}")
async def identicon(name: str):
    ecp = name
    if name == "":
        return RedirectResponse("https://arisnet.top/q-identicon/icon/" + name, 302)
    name = name.split("@")
    if len(name) != 2 or name[1] != MISSKEY_DOMAIN:
        return RedirectResponse("https://arisnet.top/q-identicon/icon/" + ecp, 302)
    name = name[0]
    async with Session() as session:
        if (prereg := await session.scalar(sa.select(Registration).where(Registration.userName == name))) is None:
            return RedirectResponse("https://arisnet.top/q-identicon/icon/" + ecp, 302)
        if prereg.yunhuId is None:
            return RedirectResponse("https://arisnet.top/q-identicon/icon/" + ecp, 302)
        return RedirectResponse(await eapis.getAvatarUrl(prereg.yunhuId))

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
