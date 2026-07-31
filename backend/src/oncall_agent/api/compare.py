"""Cold-versus-recall run comparison endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from oncall_agent.api.errors import ApiError
from oncall_agent.api.models import CompareResponse, ErrorResponse

router = APIRouter(tags=["compare"])


@router.get(
    "/compare",
    response_model=CompareResponse,
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def compare_runs(
    request: Request,
    a: str | None = Query(default=None),
    b: str | None = Query(default=None),
) -> CompareResponse:
    """Compare an explicit pair or auto-select the newest cold/recall root-cause pair."""

    if (a is None) != (b is None):
        raise ApiError(
            422,
            "compare_pair_incomplete",
            "Query parameters a and b must be supplied together",
            "Omit both to auto-select the newest cold-versus-recall pair",
        )
    comparison = await request.app.state.store.compare_runs(a, b)
    if comparison is None:
        raise ApiError(
            404,
            "comparison_not_found",
            "No comparable pair of runs was found",
            "Complete cold and recall triages sharing one root cause, or provide valid a and b IDs",
        )
    return CompareResponse.model_validate(comparison)

