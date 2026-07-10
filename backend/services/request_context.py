from __future__ import annotations

from contextvars import ContextVar, Token


_PREDICT_REQUEST_ID: ContextVar[str | None] = ContextVar(
    "predict_request_id",
    default=None,
)


def get_predict_request_id() -> str | None:
    return _PREDICT_REQUEST_ID.get()


def set_predict_request_id(request_id: str | None) -> Token[str | None]:
    return _PREDICT_REQUEST_ID.set(request_id)


def reset_predict_request_id(token: Token[str | None]) -> None:
    _PREDICT_REQUEST_ID.reset(token)
