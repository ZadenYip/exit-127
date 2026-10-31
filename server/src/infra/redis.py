import os
from typing import Annotated

from fastapi import Depends, Request
from redis.asyncio import Redis


async def create_redis_client() -> Redis:
    """ 使用环境配置创建异步 Redis 客户端 """
    redis_client = Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        db=int(os.getenv("REDIS_DB", "0")),
        username=os.getenv("REDIS_USERNAME"),
        password=os.getenv("REDIS_PASSWORD"),
        decode_responses=True,
        socket_connect_timeout=3,
        socket_timeout=5,
    )
    await redis_client.ping()
    return redis_client


def get_redis(request: Request) -> Redis:
    return request.app.state.redis


RedisDep = Annotated[Redis, Depends(get_redis)]
