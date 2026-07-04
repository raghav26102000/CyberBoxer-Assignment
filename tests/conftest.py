import asyncio
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.services.cache import invalidate_all


async def _create_tables(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture()
def client():
    # StaticPool keeps a single shared connection alive for the lifetime
    # of the engine, which SQLite's ":memory:" mode requires to persist
    # data across the multiple sessions FastAPI opens per request.
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    asyncio.run(_create_tables(engine))

    TestingSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)

    async def override_get_db():
        async with TestingSessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    # The report cache is a module-level dict shared across tests in the
    # same process -- clear it so one test's data can't leak into
    # another's cached report response.
    invalidate_all()

    # Not using `with TestClient(app) as ...` on purpose: that would run
    # the app's lifespan, which creates tables on the *production*
    # engine (a real claims.db file) as a side effect. Tests use their
    # own isolated in-memory engine instead, created above.
    test_client = TestClient(app)
    yield test_client

    app.dependency_overrides.clear()
