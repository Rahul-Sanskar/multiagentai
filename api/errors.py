"""
Centralised exception handlers.
Register all handlers via register_error_handlers(app).
"""
from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from api.schemas_v1 import ErrorDetail, ErrorResponse
from utils.exceptions import AppError
from utils.logger import get_logger

logger = get_logger("errors")


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "")


def _error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    field: str | None = None,
) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorDetail(code=code, message=message, field=field),
        request_id=_request_id(request),
    )
    return JSONResponse(status_code=status_code, content=body.model_dump())


def register_error_handlers(app: FastAPI) -> None:

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        errors = exc.errors()
        first = errors[0] if errors else {}
        field = ".".join(str(loc) for loc in first.get("loc", [])) or None
        message = first.get("msg", "Validation error")
        logger.warning(
            "validation_error",
            path=request.url.path,
            field=field,
            message=message,
            request_id=_request_id(request),
        )
        return _error_response(
            request, status.HTTP_422_UNPROCESSABLE_ENTITY,
            "VALIDATION_ERROR", message, field,
        )

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        # All typed domain exceptions — log at appropriate level
        if exc.http_status >= 500:
            logger.error(
                "app_error",
                code=exc.error_code,
                message=exc.message,
                path=request.url.path,
                request_id=_request_id(request),
                exc_info=True,
            )
        else:
            logger.warning(
                "app_error",
                code=exc.error_code,
                message=exc.message,
                path=request.url.path,
                request_id=_request_id(request),
            )
        return _error_response(
            request, exc.http_status, exc.error_code, exc.message,
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        logger.warning(
            "value_error",
            path=request.url.path,
            error=str(exc),
            request_id=_request_id(request),
        )
        return _error_response(
            request, status.HTTP_400_BAD_REQUEST, "BAD_REQUEST", str(exc),
        )

    @app.exception_handler(KeyError)
    async def key_error_handler(request: Request, exc: KeyError):
        logger.warning(
            "not_found",
            path=request.url.path,
            error=str(exc),
            request_id=_request_id(request),
        )
        return _error_response(
            request, status.HTTP_404_NOT_FOUND,
            "NOT_FOUND", f"Resource not found: {exc}",
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception):
        logger.error(
            "unhandled_error",
            path=request.url.path,
            error=str(exc),
            exc_info=True,
            request_id=_request_id(request),
        )
        return _error_response(
            request, status.HTTP_500_INTERNAL_SERVER_ERROR,
            "INTERNAL_ERROR", "An unexpected error occurred.",
        )
