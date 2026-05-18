"""GET /v1/state — current active selections + Ollama residency snapshot."""
from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/v1/state")
async def get_state(request: Request) -> dict:
    state_store = request.app.state.state_store
    residency = request.app.state.residency
    ollama_status = await residency.query()
    return {
        "active": state_store.get_state(),
        "system": {"ollama": ollama_status},
    }
