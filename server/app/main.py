from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

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
    allow_origins=settings.cors_allow_origins,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
    allow_credentials=settings.cors_allow_credentials,
    expose_headers=settings.cors_expose_headers,
    max_age=settings.cors_max_age,
)
# The last middleware added runs first, including before CORS preflight handling.
app.add_middleware(
    TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts, www_redirect=False,
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
