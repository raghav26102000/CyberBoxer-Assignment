import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.database import Base, engine
from app.exceptions import APIError
from app.logging_config import logger
from app.rate_limit import limiter
from app.routers import upload, claims, customers, reports, health


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Dev convenience only: creates tables if they don't exist yet.
    # The source of truth for schema changes is Alembic (see
    # alembic/versions/) -- run `alembic upgrade head` for a real deploy.
    # This just means `uvicorn app.main:app` works out of the box on a
    # fresh clone without forcing a migration step first.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(
    title="Insurance Claims Processing API",
    description="Upload, validate, and analyze insurance claim data.",
    version="1.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

app.include_router(upload.router)
app.include_router(claims.router)
app.include_router(customers.router)
app.include_router(reports.router)
app.include_router(health.router)


# ---------------------------------------------------------------- middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration_ms = round((time.time() - start) * 1000, 2)
    # Deliberately log method/path/status/duration only -- no query params,
    # bodies, or headers, since those can carry PII (names, ages, etc.)
    # or secrets (the API key header).
    logger.info(f"{request.method} {request.url.path} -> {response.status_code} ({duration_ms}ms)")
    return response


# ------------------------------------------------------------- error handlers
@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    logger.warning(f"RateLimitExceeded: {request.client.host if request.client else 'unknown'} on {request.url.path}")
    return JSONResponse(
        status_code=429,
        content={"error": "RateLimitExceeded", "message": f"Rate limit exceeded: {exc.detail}"},
    )


@app.exception_handler(APIError)
async def api_error_handler(request: Request, exc: APIError):
    logger.warning(f"{exc.error_type}: {exc.message}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.error_type, "message": exc.message},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    logger.warning(f"RequestValidationError: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={"error": "ValidationError", "message": str(exc.errors())},
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled exception on {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "InternalServerError", "message": "An unexpected error occurred"},
    )


@app.get("/", tags=["Root"])
def root():
    return {"message": "Insurance Claims Processing API. See /docs for Swagger UI."}
