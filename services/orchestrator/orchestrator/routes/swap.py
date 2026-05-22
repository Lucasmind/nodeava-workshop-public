"""POST /v1/swap — flip a valve."""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from orchestrator.catalog import CatalogError

router = APIRouter()


_VALID_KINDS = {"brain", "voice", "avatar", "personality", "tools"}


class SwapBody(BaseModel):
    kind: str
    id: str
    value: bool | None = None


@router.post("/v1/swap")
async def post_swap(request: Request, body: SwapBody) -> JSONResponse:
    if body.kind not in _VALID_KINDS:
        return JSONResponse({"error": f"unknown kind '{body.kind}'"}, status_code=400)

    state_store = request.app.state.state_store

    if body.kind == "tools":
        if body.value is None or not isinstance(body.value, bool):
            return JSONResponse(
                {"error": f"tools swap requires 'value' (boolean), got {body.value!r}"},
                status_code=400,
            )
        try:
            state_store.set_tool(body.id, body.value)
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
    else:
        try:
            state_store.set_state(body.kind, body.id)
        except CatalogError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=400)

    residency = request.app.state.residency
    return JSONResponse(
        {
            "active": state_store.get_state(),
            "system": {"ollama": await residency.query()},
        },
        status_code=200,
    )
