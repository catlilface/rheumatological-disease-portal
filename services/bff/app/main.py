from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.routers import knowledge, screenings

# TODO(MIS-18): передавать Settings через DI при создании приложения,
# включая настройку CORS и allowed_hosts, вместо глобального Settings().
from app.settings import Settings

settings = Settings()

app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    openapi_url=None,
    docs_url=None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors.allow_origins,
    allow_methods=settings.cors.allow_methods,
    allow_headers=settings.cors.allow_headers,
    allow_credentials=settings.cors.allow_credentials,
    expose_headers=settings.cors.expose_headers,
    max_age=settings.cors.max_age,
)
# The last middleware added runs first, including before CORS preflight handling.
app.add_middleware(
    TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts, www_redirect=False,
)


@app.middleware("http")
async def log_exchange(request: Request, call_next):
    call = uuid4().hex
    logger.info("http.received call={} method={}", call, request.method)
    try:
        response = await call_next(request)
    except Exception:
        logger.error("http.response call={} status=500", call)
        raise
    # Log the route template, never query strings, IDs, cookies or response bodies.
    route = getattr(request.scope.get("route"), "path", "unmatched")
    logger.info("http.response call={} route={} status={}", call, route, response.status_code)
    return response


app.include_router(screenings.router, prefix="/api/v1")
app.include_router(knowledge.router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
