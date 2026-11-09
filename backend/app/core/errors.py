"""Application error hierarchy and FastAPI exception handler."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Base class for all application errors."""

    code: str = "INTERNAL_ERROR"
    status_code: int = 500

    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code


class NotFoundError(AppError):
    code = "NOT_FOUND"
    status_code = 404

    def __init__(self, message: str = "Resource not found"):
        super().__init__(message)


class ForbiddenError(AppError):
    code = "FORBIDDEN"
    status_code = 403

    def __init__(self, message: str = "Access denied", *, code: str = "FORBIDDEN"):
        super().__init__(message, code=code)


class ConflictError(AppError):
    status_code = 409

    def __init__(self, message: str, *, code: str = "CONFLICT"):
        super().__init__(message, code=code)


class ValidationError(AppError):
    code = "VALIDATION_ERROR"
    status_code = 422

    def __init__(self, message: str):
        super().__init__(message)


class UnauthorizedError(AppError):
    status_code = 401

    def __init__(self, message: str = "Authentication required", *, code: str = "UNAUTHORIZED"):
        super().__init__(message, code=code)


class RateLimitError(AppError):
    code = "RATE_LIMITED"
    status_code = 429

    def __init__(self, message: str = "Too many requests"):
        super().__init__(message)


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Convert AppError into a uniform JSON error response."""
    request_id = getattr(request.state, "request_id", "unknown")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "request_id": request_id,
            }
        },
    )
