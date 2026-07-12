export const FEEDBACK_QUEUE_LIMIT = 25;
export const FEEDBACK_QUEUE_TTL_MS = 7 * 24 * 60 * 60 * 1000;

export type FeedbackUpdate = {
  item_correct?: boolean;
  guidance_helpful?: boolean;
  prediction_changed?: boolean;
  corrected_item?: string;
  correction_request_id?: string;
};

export type QueuedFeedback = {
  requestId: string;
  update: FeedbackUpdate;
  queuedAt: number;
};

export function sanitizeFeedbackUpdate(value: unknown): FeedbackUpdate {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return {};
  }
  const source = value as Record<string, unknown>;
  const sanitized: FeedbackUpdate = {};
  if (typeof source.item_correct === 'boolean') {
    sanitized.item_correct = source.item_correct;
  }
  if (typeof source.guidance_helpful === 'boolean') {
    sanitized.guidance_helpful = source.guidance_helpful;
  }
  if (typeof source.prediction_changed === 'boolean') {
    sanitized.prediction_changed = source.prediction_changed;
  }
  if (typeof source.corrected_item === 'string' && source.corrected_item.trim()) {
    sanitized.corrected_item = source.corrected_item.trim().slice(0, 200);
  }
  if (
    typeof source.correction_request_id === 'string' &&
    source.correction_request_id.trim()
  ) {
    sanitized.correction_request_id = source.correction_request_id.trim().slice(0, 96);
  }
  return sanitized;
}

export function mergeQueuedFeedback(
  entries: QueuedFeedback[],
  incoming: QueuedFeedback,
  now = Date.now(),
) {
  const unexpired = entries.filter(
    (entry) => now - entry.queuedAt < FEEDBACK_QUEUE_TTL_MS,
  );
  const existing = unexpired.find((entry) => entry.requestId === incoming.requestId);
  const merged: QueuedFeedback = existing
    ? {
        requestId: incoming.requestId,
        update: { ...existing.update, ...incoming.update },
        queuedAt: incoming.queuedAt,
      }
    : incoming;

  return [
    ...unexpired.filter((entry) => entry.requestId !== incoming.requestId),
    merged,
  ]
    .sort((left, right) => right.queuedAt - left.queuedAt)
    .slice(0, FEEDBACK_QUEUE_LIMIT);
}

export function pruneQueuedFeedback(entries: QueuedFeedback[], now = Date.now()) {
  return entries
    .filter((entry) => now - entry.queuedAt < FEEDBACK_QUEUE_TTL_MS)
    .sort((left, right) => right.queuedAt - left.queuedAt)
    .slice(0, FEEDBACK_QUEUE_LIMIT);
}

export function shouldShowGuidanceFeedback({
  disposalAction,
  guidanceSource,
  clarificationRequired,
}: {
  disposalAction: string | null;
  guidanceSource?: string | null;
  clarificationRequired: boolean;
}) {
  if (clarificationRequired || !disposalAction) {
    return false;
  }
  return ![
    'recognition_clarification_required',
    'safe_fallback',
  ].includes((guidanceSource ?? '').trim().toLowerCase());
}
