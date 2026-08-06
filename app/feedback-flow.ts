export const FEEDBACK_QUEUE_LIMIT = 25;
export const FEEDBACK_QUEUE_TTL_MS = 7 * 24 * 60 * 60 * 1000;

export type FeedbackUpdate = {
  item_correct?: boolean;
  guidance_helpful?: boolean;
  prediction_changed?: boolean;
  corrected_item?: string;
  correction_request_id?: string;
};

export const SCAN_FEEDBACK_REASON_VALUES = [
  'item_identified_incorrectly',
  'disposal_guidance_incorrect',
  'local_information_inaccurate',
  'missing_important_information',
  'other',
] as const;

export type ScanFeedbackReason = (typeof SCAN_FEEDBACK_REASON_VALUES)[number];
export type ScanFeedbackRating = 'positive' | 'negative';

export type ScanFeedbackSubmission = {
  request_id: string;
  item_name: string;
  location: string | null;
  guidance: Record<string, unknown>;
  rating: ScanFeedbackRating;
  reasons: ScanFeedbackReason[];
  details: string | null;
};

export type QueuedFeedback = {
  requestId: string;
  update: FeedbackUpdate;
  queuedAt: number;
};

const FEEDBACK_SUCCESS_CACHE_LIMIT = 100;

export class FeedbackRequestError extends Error {
  readonly retryable: boolean;
  readonly status: number;

  constructor(status: number) {
    super(`Feedback request failed with status ${status}`);
    this.name = 'FeedbackRequestError';
    this.status = status;
    this.retryable = isRetryableFeedbackStatus(status);
  }
}

export function isRetryableFeedbackStatus(status: number) {
  return status === 408 || status === 425 || status === 429 || status >= 500;
}

export function isRetryableFeedbackError(error: unknown) {
  if (error instanceof FeedbackRequestError) {
    return error.retryable;
  }
  if (error && typeof error === 'object' && 'retryable' in error) {
    return (error as { retryable?: unknown }).retryable !== false;
  }
  return true;
}

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

function feedbackPayloadKey(requestId: string, update: FeedbackUpdate) {
  return `${requestId.trim()}:${JSON.stringify(sanitizeFeedbackUpdate(update))}`;
}

export function createFeedbackSubmissionCoordinator(
  send: (requestId: string, update: FeedbackUpdate) => Promise<void>,
) {
  const inFlight = new Map<string, Promise<void>>();
  const successful = new Map<string, true>();

  return (requestId: string, update: FeedbackUpdate): Promise<void> => {
    const sanitizedUpdate = sanitizeFeedbackUpdate(update);
    if (!requestId.trim() || !Object.keys(sanitizedUpdate).length) {
      return Promise.resolve();
    }

    const key = feedbackPayloadKey(requestId, sanitizedUpdate);
    if (successful.has(key)) {
      return Promise.resolve();
    }
    const existing = inFlight.get(key);
    if (existing) {
      return existing;
    }

    const request = send(requestId, sanitizedUpdate)
      .then(() => {
        successful.set(key, true);
        while (successful.size > FEEDBACK_SUCCESS_CACHE_LIMIT) {
          const oldestKey = successful.keys().next().value;
          if (typeof oldestKey !== 'string') {
            break;
          }
          successful.delete(oldestKey);
        }
      })
      .finally(() => {
        if (inFlight.get(key) === request) {
          inFlight.delete(key);
        }
      });
    inFlight.set(key, request);
    return request;
  };
}

export async function flushQueuedFeedbackEntries(
  entries: QueuedFeedback[],
  send: (requestId: string, update: FeedbackUpdate) => Promise<void>,
) {
  const remaining: QueuedFeedback[] = [];
  for (const entry of [...entries].reverse()) {
    try {
      await send(entry.requestId, entry.update);
    } catch (error) {
      if (isRetryableFeedbackError(error)) {
        remaining.push(entry);
      }
    }
  }
  return remaining;
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
