import os
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import URL, Engine
from sqlmodel import Session, create_engine


def create_pg_engine() -> Engine:
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
    return create_engine(url, pool_pre_ping=True)


def get_session(request: Request) -> Iterator[Session]:
    engine: Engine = request.app.state.pg_engine
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
