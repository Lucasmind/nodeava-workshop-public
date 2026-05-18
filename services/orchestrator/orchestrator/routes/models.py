"""Models route — proxies the backend's /v1/models for OpenAI compatibility."""
import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/v1/models")
async def list_models(request: Request) -> JSONResponse:
    backend = request.app.state.settings.ollama_url
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{backend}/v1/models")
        if resp.status_code == 200:
            return JSONResponse(resp.json())
    except httpx.HTTPError:
        pass
    return JSONResponse({"object": "list", "data": []})
