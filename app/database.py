from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.config import ASYNC_DATABASE_URL

connect_args = {"check_same_thread": False} if "sqlite" in ASYNC_DATABASE_URL else {}

engine = create_async_engine(ASYNC_DATABASE_URL, connect_args=connect_args)
SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


# SQLite does not enforce FOREIGN KEY constraints by default -- it accepts
# them in the schema but silently ignores violations unless this pragma is
# set on every connection. Without this, a claim could reference a
# nonexistent policy_id via direct SQL and SQLite would allow it, which
# defeats the point of declaring the ForeignKey in models.py at all.
if "sqlite" in ASYNC_DATABASE_URL:
    @event.listens_for(engine.sync_engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


async def get_db():
    """FastAPI dependency that yields an async DB session and always closes it."""
    async with SessionLocal() as session:
        yield session
