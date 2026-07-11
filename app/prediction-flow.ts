export type PredictionFlowStatus = 'confident' | 'uncertain' | 'unknown';

export type PredictionClarification = {
  required?: unknown;
  reason_codes?: unknown;
  retake_recommended?: unknown;
  retake_guidance?: unknown;
  message?: unknown;
};

export type PredictionFlowInput = {
  status?: unknown;
  clarification?: PredictionClarification | null;
};

export const DEFAULT_REVIEW_SUMMARY = 'Choose the item that best matches your scan.';

export function requiresRecognitionClarification(prediction: PredictionFlowInput) {
  return prediction.clarification?.required === true;
}

export function resolvePredictionFlowStatus(
  prediction: PredictionFlowInput,
): PredictionFlowStatus {
  if (requiresRecognitionClarification(prediction)) {
    return 'uncertain';
  }

  if (
    prediction.status === 'confident' ||
    prediction.status === 'uncertain' ||
    prediction.status === 'unknown'
  ) {
    return prediction.status;
  }

  return 'unknown';
}

function nonEmptyText(value: unknown) {
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}

export function getClarificationReasonCodes(prediction: PredictionFlowInput) {
  const reasonCodes = prediction.clarification?.reason_codes;
  if (!Array.isArray(reasonCodes)) {
    return [];
  }

  return reasonCodes.filter(
    (reasonCode): reasonCode is string =>
      typeof reasonCode === 'string' && reasonCode.trim().length > 0,
  );
}

export function getRecognitionReviewSummary(prediction: PredictionFlowInput) {
  if (!requiresRecognitionClarification(prediction)) {
    return DEFAULT_REVIEW_SUMMARY;
  }

  const message = nonEmptyText(prediction.clarification?.message);
  const retakeGuidance = nonEmptyText(prediction.clarification?.retake_guidance);

  if (message && retakeGuidance && message !== retakeGuidance) {
    return `${message} ${retakeGuidance}`;
  }

  return message ?? retakeGuidance ?? DEFAULT_REVIEW_SUMMARY;
}
