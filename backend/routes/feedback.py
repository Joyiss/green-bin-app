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


class FeedbackUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_correct: bool | None = None
    guidance_helpful: bool | None = None
    prediction_changed: bool | None = None
    corrected_item: str | None = Field(default=None, min_length=1, max_length=200)
    correction_request_id: str | None = Field(default=None, min_length=1, max_length=96)

    @model_validator(mode="after")
    def validate_feedback_update(self) -> "FeedbackUpdate":
        provided = self.model_fields_set
        if not provided:
            raise ValueError("At least one feedback field is required.")

        correction_fields = {"corrected_item", "correction_request_id"} & provided
        if correction_fields and self.prediction_changed is not True:
            raise ValueError(
                "corrected_item and correction_request_id require prediction_changed=true."
            )
        if self.prediction_changed is True and (
            not self.corrected_item or not self.correction_request_id
        ):
            raise ValueError(
                "prediction_changed=true requires corrected_item and correction_request_id."
            )
        return self


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


def _validate_trusted_correction(
    correction_context: dict[str, Any],
    feedback: FeedbackUpdate,
) -> None:
    if feedback.prediction_changed is not True:
        return
    if (
        correction_context.get("request_id") != feedback.correction_request_id
        or correction_context.get("corrected_item") != feedback.corrected_item
    ):
        raise HTTPException(
            status_code=409,
            detail={"error": "correction_context_mismatch"},
        )


@router.put("/feedback/{request_id}")
def record_feedback(request_id: str, feedback: FeedbackUpdate) -> dict[str, Any]:
    normalized_request_id = _validate_request_id(request_id)
    try:
        feedback_repository.get_feedback_context(normalized_request_id)
        if feedback.prediction_changed is True:
            try:
                correction_context = feedback_repository.get_correction_context(
                    original_request_id=normalized_request_id,
                    correction_request_id=feedback.correction_request_id or "",
                )
            except feedback_repository.FeedbackContextNotFound:
                raise HTTPException(
                    status_code=409,
                    detail={"error": "correction_context_mismatch"},
                )
            _validate_trusted_correction(correction_context, feedback)
        update_payload = feedback.model_dump(exclude_unset=True)
        feedback_repository.update_user_feedback(
            normalized_request_id,
            update_payload,
        )
    except feedback_repository.FeedbackContextNotFound:
        raise HTTPException(
            status_code=404,
            detail={"error": "feedback_context_not_found"},
        )
    except feedback_repository.FeedbackRepositoryUnavailable:
        raise HTTPException(
            status_code=503,
            detail={"error": "feedback_unavailable"},
        )

    logger.info(
        "Closed-test feedback recorded. request_id=%s item_correct_submitted=%s guidance_helpful_submitted=%s prediction_changed=%s",
        normalized_request_id,
        "item_correct" in feedback.model_fields_set,
        "guidance_helpful" in feedback.model_fields_set,
        feedback.prediction_changed is True,
    )
    return {"recorded": True, "request_id": normalized_request_id}


@router.put("/scan-feedback/{request_id}")
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
    except feedback_repository.FeedbackRepositoryUnavailable:
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
