import asyncio
from collections.abc import AsyncGenerator, Callable, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi import FastAPI, Response
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.redis import RedisContainer

from error.handlers import register_exception_handlers
from log.logger import register_logger
from v1.auth import router as auth_router
from v1.classes import router as classes_router


AnyIOBackend = tuple[str, dict[str, Callable[[], asyncio.AbstractEventLoop]]]


@dataclass(slots=True)
class Backend:
    app: FastAPI
    client: AsyncClient
    engine: AsyncEngine
    redis: Redis


@pytest.fixture(scope="session")
def anyio_backend() -> AnyIOBackend:
    """Use one Windows-compatible asyncio backend for the test session."""
    return "asyncio", {"loop_factory": asyncio.SelectorEventLoop}


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    schema_path = (
        Path(__file__).resolve().parents[2]
        / "docker"
        / "pg"
        / "init-scripts"
        / "000_schema.sql"
    )
    if not schema_path.is_file():
        raise FileNotFoundError(f"PostgreSQL schema file not found: {schema_path}")

    with PostgresContainer(
        "postgres:18.6-alpine", driver="psycopg"
    ).with_volume_mapping(
        str(schema_path),
        "/docker-entrypoint-initdb.d/000_schema.sql",
        mode="ro",
    ) as container:
        yield container


@pytest.fixture(scope="session")
def redis_container() -> Iterator[RedisContainer]:
    with RedisContainer("redis:8.8-alpine") as container:
        yield container


@pytest.fixture(scope="session")
async def app_backend(
    postgres_container: PostgresContainer,
    redis_container: RedisContainer,
    anyio_backend: AnyIOBackend,
) -> AsyncGenerator[Backend, None]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        engine = create_async_engine(
            postgres_container.get_connection_url(driver="psycopg"),
            connect_args={"connect_timeout": 5},
        )
        redis_host = redis_container.get_container_host_ip()
        if redis_host in {"localhost", "::1"}:
            redis_host = "127.0.0.1"
        redis = Redis(
            host=redis_host,
            port=int(redis_container.get_exposed_port(6379)),
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        try:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            await redis.ping()

            app.state.pg_engine = engine
            app.state.redis = redis
            yield
        finally:
            await redis.aclose()
            await engine.dispose()

    app = FastAPI(lifespan=lifespan)
    register_logger(app)
    register_exception_handlers(app)
    app.include_router(auth_router.router, prefix="/v1")
    app.include_router(classes_router.router, prefix="/v1")

    @app.get("/healthz")
    async def healthz() -> Response:
        return Response(status_code=200, content="OK")

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="https://testserver",
        ) as client:
            yield Backend(
                app=app,
                client=client,
                engine=app.state.pg_engine,
                redis=app.state.redis,
            )


@pytest.fixture
async def backend(app_backend: Backend) -> Backend:
    async with app_backend.engine.begin() as connection:
        result = await connection.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = :schema"),
            {"schema": "public"},
        )
        quote = app_backend.engine.dialect.identifier_preparer.quote
        tables = ", ".join(
            f'"public".{quote(name)}' for name in result.scalars()
        )
        if tables:
            await connection.execute(
                text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE")
            )

    await app_backend.redis.flushdb()
    app_backend.client.cookies.clear()
    return app_backend
