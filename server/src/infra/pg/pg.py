import logging
import os
from collections.abc import Iterator
from pydoc import text
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import URL, Engine, text
from sqlmodel import Session, create_engine

logger = logging.getLogger(__name__)

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
    
    engine = create_engine(
        url,
        pool_pre_ping=True,
        pool_timeout=5,
        connect_args={"connect_timeout": 5},
        hide_parameters=True,
    )
    
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
        logger.info("successfully connected to PostgreSQL database: %s", database)
    return engine


def get_session(request: Request) -> Iterator[Session]:
    engine: Engine = request.app.state.pg_engine
    with Session(engine) as session:
        yield session


PGSessionDep = Annotated[Session, Depends(get_session)]
