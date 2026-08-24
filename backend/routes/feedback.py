from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

try:
    from ..repositories import feedback_repository
except ImportError:
    from repositories import feedback_repository

router = APIRouter()
logger = logging.getLogger(__name__)
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$")


ScanFeedbackReason = Literal[
    "item_identified_incorrectly",
    "disposal_guidance_incorrect",
    "local_information_inaccurate",
    "missing_important_information",
    "other",
]


class ScanFeedbackSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=96)
    item_name: str = Field(min_length=1, max_length=200)
    location: str | None = Field(default=None, max_length=300)
    guidance: dict[str, Any]
    rating: Literal["positive", "negative"]
    reasons: list[ScanFeedbackReason] = Field(default_factory=list, max_length=5)
    details: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def normalize_submission(self) -> "ScanFeedbackSubmission":
        self.request_id = self.request_id.strip()
        self.item_name = self.item_name.strip()
        self.location = self.location.strip() if self.location and self.location.strip() else None
        self.details = self.details.strip() if self.details and self.details.strip() else None
        self.reasons = list(dict.fromkeys(self.reasons))
        if self.rating == "positive":
            self.reasons = []
            self.details = None
        return self


def _validate_request_id(request_id: str) -> str:
    normalized = request_id.strip()
    if not _REQUEST_ID_PATTERN.fullmatch(normalized):
        raise HTTPException(status_code=422, detail={"error": "invalid_request_id"})
    return normalized


@router.put("/feedback/{request_id}")
def record_scan_feedback(
    request_id: str,
    feedback: ScanFeedbackSubmission,
) -> dict[str, Any]:
    normalized_request_id = _validate_request_id(request_id)
    if feedback.request_id != normalized_request_id:
        raise HTTPException(
            status_code=409,
            detail={"error": "request_id_mismatch"},
        )

    payload = feedback.model_dump()
    payload["submitted_at"] = datetime.now(timezone.utc).isoformat()
    try:
        feedback_repository.upsert_scan_feedback(payload)
    except feedback_repository.FeedbackRepositoryUnavailable as exc:
        logger.warning(
            "Scan feedback unavailable. request_id=%s error_type=%s",
            normalized_request_id,
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail={"error": "feedback_unavailable"},
        )

    logger.info(
        "Scan feedback recorded. request_id=%s rating=%s reason_count=%s",
        normalized_request_id,
        feedback.rating,
        len(feedback.reasons),
    )
    return {"recorded": True, "request_id": normalized_request_id}


# Temporary request-contract alias for older closed-test clients. Both paths use
# exactly the same scan_feedback model and repository implementation.
router.add_api_route(
    "/scan-feedback/{request_id}",
    record_scan_feedback,
    methods=["PUT"],
    include_in_schema=False,
)
