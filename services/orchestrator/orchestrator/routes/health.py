"""Health route — checks backend reachability."""
import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/health")
async def health(request: Request) -> JSONResponse:
    settings = request.app.state.settings
    backend = settings.ollama_url
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Ollama's root endpoint returns "Ollama is running" (200).
            # /health does not exist in Ollama — use / instead.
            resp = await client.get(f"{backend}/")
        if resp.status_code == 200:
            return JSONResponse({"status": "ok", "backend": backend})
        return JSONResponse(
            {
                "status": "unhealthy",
                "backend": backend,
                "detail": f"backend returned HTTP {resp.status_code}",
            },
            status_code=503,
        )
    except httpx.HTTPError as e:
        return JSONResponse(
            {"status": "unhealthy", "backend": backend, "detail": str(e)},
            status_code=503,
        )
