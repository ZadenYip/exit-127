import logging
import os
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import URL, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

logger = logging.getLogger(__name__)

async def create_pg_engine() -> AsyncEngine:
    user = os.getenv("POSTGRES_USER")
    password = os.getenv("POSTGRES_PASSWORD")
    database = os.getenv("POSTGRES_DB")
    if not user or not password or not database:
        raise ValueError("Missing required environment variables for PostgreSQL connection.")

    url = URL.create(
        drivername="postgresql+psycopg",
        username=user,
        password=password,
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=database,
    )
    
    engine = create_async_engine(
        url,
        pool_pre_ping=True,
        pool_timeout=5,
        connect_args={"connect_timeout": 5},
        hide_parameters=True,
    )
    
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
        logger.info("successfully connected to PostgreSQL database: %s", database)
    return engine


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    engine: AsyncEngine = request.app.state.pg_engine
    async with AsyncSession(engine) as session:
        yield session


PGSessionDep = Annotated[AsyncSession, Depends(get_session)]
