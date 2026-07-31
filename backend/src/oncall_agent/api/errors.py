"""Uniform API exceptions and FastAPI exception handlers."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from oncall_agent.api.models import ErrorDetail, ErrorResponse

log = logging.getLogger(__name__)


class ApiError(Exception):
    """Expected HTTP failure rendered through the public error envelope."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        hint: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.hint = hint


def _response(status_code: int, code: str, message: str, hint: str | None) -> JSONResponse:
    body = ErrorResponse(error=ErrorDetail(code=code, message=message, hint=hint))
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))


def install_error_handlers(app: FastAPI) -> None:
    """Install consistent handlers for expected, validation, and unexpected errors."""

    @app.exception_handler(ApiError)
    async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
        return _response(exc.status_code, exc.code, exc.message, exc.hint)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        message = str(first.get("msg") or "Request validation failed")
        return _response(
            422,
            "validation_error",
            message,
            "Check the request body and query values",
        )

    @app.exception_handler(HTTPException)
    async def http_error_handler(_request: Request, exc: HTTPException) -> JSONResponse:
        return _response(exc.status_code, "http_error", str(exc.detail), None)

    @app.exception_handler(Exception)
    async def unexpected_error_handler(_request: Request, exc: Exception) -> JSONResponse:
        log.exception("Unhandled API error", exc_info=exc)
        return _response(
            500,
            "internal_error",
            "The backend could not complete the request",
            "Check the backend logs for the structured exception",
        )
