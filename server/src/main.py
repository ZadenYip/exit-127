from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, Response
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from error.handlers import register_exception_handlers
from infra.pg.pg import create_pg_engine
from infra.redis import create_redis_client
from log.logger import register_logger
from v1.auth import router as auth_router
from v1.classes import router as classes_router


load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    pg_engine: AsyncEngine | None = None
    redis_client: Redis | None = None
    try:
        pg_engine = await create_pg_engine()
        redis_client = await create_redis_client()
        app.state.pg_engine = pg_engine
        app.state.redis = redis_client
        yield
        '''以下为清理函数'''
    finally:
        if redis_client is not None:
            await redis_client.aclose()
        if pg_engine is not None:
            await pg_engine.dispose()


app = FastAPI(lifespan=lifespan)
register_logger(app)
register_exception_handlers(app)

def register_v1_router(app: FastAPI, router: APIRouter):
    app.include_router(router, prefix="/v1")

register_v1_router(app, auth_router.router)
register_v1_router(app, classes_router.router)


@app.get("/healthz")
async def healthz():
    return Response(status_code=200, content="OK")
