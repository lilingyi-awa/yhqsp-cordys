import asyncio
import fastapi
import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from contextlib import asynccontextmanager
from config import SQLALCHEMY_URL, MISSKEY_SQLALCHEMY_URL, MISSKEY_ROOT_USER
import time
import re
import typing

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

def getMiRootSec():
    return miRootSec

http = fastapi.FastAPI(lifespan=lifespan)

class Registration(ORMBase):
    __tablename__ = "registration"
    userName = sa.Column(sa.String(45).with_variant(sa.String(45, 'ascii_bin'), 'mysql', 'mariadb'), primary_key=True)
    yunhuId = sa.Column(sa.BigInteger(), nullable=True, unique=True)
    robotOwner = sa.Column(sa.BigInteger(), nullable=True)
    userId = sa.Column(sa.String(45).with_variant(sa.String(45, 'ascii_bin'), 'mysql', 'mariadb'), nullable=True, unique=True)

class LoginRequests(ORMBase):
    __tablename__ = "login_request"
    rid = sa.Column(sa.BigInteger(), primary_key=True, autoincrement=False)
    secret = sa.Column(sa.String(32).with_variant(sa.String(32, 'ascii_bin'), 'mysql', 'mariadb'), nullable=False)
    userName = sa.Column(sa.Text(), nullable=False)
    expires = sa.Column(sa.BigInteger(), nullable=False, default=lambda: int(time.time()) + 600)

class OAuthRequests(ORMBase):
    __tablename__ = "oauth_request"
    rid1 = sa.Column(sa.BigInteger(), primary_key=True, autoincrement=False)
    rid2 = sa.Column(sa.String(32).with_variant(sa.String(32, 'ascii_bin'), 'mysql', 'mariadb'), primary_key=True)
    expires = sa.Column(sa.BigInteger(), nullable=False, default=lambda: int(time.time()) + 600)

class OAuthRegisterToken(ORMBase):
    __tablename__ = "oauth_register_token"
    uid = sa.Column(sa.BigInteger(), primary_key=True, autoincrement=False)
    secret = sa.Column(sa.String(32).with_variant(sa.String(32, 'ascii_bin'), 'mysql', 'mariadb'), nullable=False)
    expires = sa.Column(sa.BigInteger(), nullable=False, default=lambda: int(time.time()) + 600)

class ClientLoginToken(ORMBase):
    __tablename__ = "client_login_token"
    uid = sa.Column(sa.BigInteger(), primary_key=True, autoincrement=False)
    token_sha256 = sa.Column(sa.String(64).with_variant(sa.String(64, 'ascii_bin'), 'mysql', 'mariadb'), primary_key=True)
    expires = sa.Column(sa.BigInteger(), nullable=False, default=lambda: int(time.time()) + 600)

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
                await sess.execute(
                    sa.delete(OAuthRegisterToken)
                    .where(OAuthRegisterToken.expires < int(time.time()))
                )
                await sess.commit()
        except Exception:
            pass
        await asyncio.sleep(2)

NAME_MATCH = re.compile(r"^[a-z0-9]{3,20}$")
INT_MATCH = re.compile(r"^[1-9][0-9]*$")

async def get_misskey_utoken(username: str) -> typing.Optional[str]:
    async with mi_engine.begin() as conn:
        return await conn.scalar(
            sa.text('SELECT "user"."token" FROM "user" where "user"."username" = :username and "user"."host" is null'),
            {"username": username},
        )
