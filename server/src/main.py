from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Response
from redis.asyncio import Redis
from sqlalchemy import Engine

from infra.pg.pg import create_pg_engine
from infra.redis import create_redis_client
from log.logger import register_logger
from v1.auth import router as auth_router


load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    pg_engine: Engine | None = None
    redis_client: Redis | None = None
    try:
        pg_engine = create_pg_engine()
        redis_client = await create_redis_client()
        app.state.pg_engine = pg_engine
        app.state.redis = redis_client
        yield
        '''以下为清理函数'''
    finally:
        if redis_client is not None:
            await redis_client.aclose()
        if pg_engine is not None:
            pg_engine.dispose()


app = FastAPI(lifespan=lifespan)
register_logger(app)
app.include_router(auth_router.router, prefix="/v1")


@app.get("/healthz")
async def healthz():
    return Response(status_code=200, content="OK")
