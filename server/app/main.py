from fastapi import FastAPI

from app.settings import Settings

settings = Settings()

app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    openapi_url=None,
    docs_url=None,
    redoc_url=None,
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
