"""
Domain exceptions with HTTP status codes and machine-readable error codes.
All custom exceptions inherit from AppError so callers can catch broadly
or narrowly as needed.
"""
from __future__ import annotations

from http import HTTPStatus


class AppError(Exception):
    """Base class for all application exceptions."""

    http_status: int = HTTPStatus.INTERNAL_SERVER_ERROR
    error_code: str = "INTERNAL_ERROR"

    def __init__(self, message: str, *, detail: str | None = None):
        super().__init__(message)
        self.message = message
        self.detail = detail or message

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.error_code,
            "message": self.message,
            "detail": self.detail,
        }


# ── Validation ────────────────────────────────────────────────────────────────

class ValidationError(AppError):
    http_status = HTTPStatus.UNPROCESSABLE_ENTITY
    error_code = "VALIDATION_ERROR"


class EmptyInputError(ValidationError):
    error_code = "EMPTY_INPUT"


class InvalidFieldError(ValidationError):
    error_code = "INVALID_FIELD"


# ── Not found ─────────────────────────────────────────────────────────────────

class NotFoundError(AppError):
    http_status = HTTPStatus.NOT_FOUND
    error_code = "NOT_FOUND"


# ── Agent errors ──────────────────────────────────────────────────────────────

class AgentError(AppError):
    http_status = HTTPStatus.INTERNAL_SERVER_ERROR
    error_code = "AGENT_ERROR"


class AgentTimeoutError(AgentError):
    error_code = "AGENT_TIMEOUT"


class AgentRetryExhaustedError(AgentError):
    error_code = "AGENT_RETRY_EXHAUSTED"


# ── Orchestrator errors ───────────────────────────────────────────────────────

class OrchestratorError(AppError):
    http_status = HTTPStatus.INTERNAL_SERVER_ERROR
    error_code = "ORCHESTRATOR_ERROR"


class AgentNotRegisteredError(OrchestratorError):
    http_status = HTTPStatus.NOT_FOUND
    error_code = "AGENT_NOT_REGISTERED"


# ── Service errors ────────────────────────────────────────────────────────────

class ServiceError(AppError):
    http_status = HTTPStatus.BAD_GATEWAY
    error_code = "SERVICE_ERROR"


class PublishError(ServiceError):
    error_code = "PUBLISH_ERROR"


class ReviewNotApprovedError(ServiceError):
    http_status = HTTPStatus.CONFLICT
    error_code = "REVIEW_NOT_APPROVED"


class RAGError(ServiceError):
    error_code = "RAG_ERROR"
