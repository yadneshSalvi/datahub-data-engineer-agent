"""Local post-mortem memory list and detail endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request

from oncall_agent.api.errors import ApiError
from oncall_agent.api.models import ErrorResponse, PostmortemRecord

router = APIRouter(tags=["postmortems"])


@router.get("/postmortems", response_model=list[PostmortemRecord])
async def list_postmortems(
    request: Request,
    q: str = Query(default="", max_length=200),
    root_cause_urn: str | None = Query(default=None),
) -> list[PostmortemRecord]:
    """Search the local memory mirror by text and exact root-cause URN."""

    rows = await request.app.state.store.list_postmortems(
        query=q,
        root_cause_urn=root_cause_urn,
    )
    return [PostmortemRecord.model_validate(row) for row in rows]


@router.get(
    "/postmortems/{postmortem_id}",
    response_model=PostmortemRecord,
    responses={404: {"model": ErrorResponse}},
)
async def get_postmortem(postmortem_id: str, request: Request) -> PostmortemRecord:
    """Return full markdown, JSON, DataHub links, and runs that reused this memory."""

    row = await request.app.state.store.get_postmortem(postmortem_id)
    if row is None:
        raise ApiError(
            404,
            "postmortem_not_found",
            f"Post-mortem {postmortem_id} does not exist",
        )
    return PostmortemRecord.model_validate(row)

