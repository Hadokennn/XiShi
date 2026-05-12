from fastapi import FastAPI

from xishi.config import settings

app = FastAPI(
    title="Xishi",
    description="手帐式第二大脑 - M1 阶段",
    version="0.1.0",
)

@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "version": app.version,
        "db_configured": bool(settings.database_url),
        "llm_configured": bool(settings.anthropic_api_key or settings.deepseek_api_key or settings.moonshot_api_key),
    }
