import {
  normalizeFeedbackResponse,
  normalizeHealthResponse,
  normalizeNearbyLocationsResponse,
  normalizePredictionResponse,
  normalizeSupportedLabelsResponse,
  type PredictionResponse,
} from '@/api/contracts';
import { ApiError, requestJson } from '@/api/request';
import { API_BASE_URL } from '@/constants/api';
import type { FeedbackUpdate, ScanFeedbackSubmission } from '@/app/feedback-flow';

const HEALTH_TIMEOUT_MS = 30_000;
const PREDICT_TIMEOUT_MS = 90_000;
const GET_TIMEOUT_MS = 20_000;
const FEEDBACK_TIMEOUT_MS = 15_000;
const HEALTH_CACHE_MS = 5 * 60 * 1000;

let healthPromise: Promise<void> | null = null;
let healthyUntil = 0;

function apiUrl(path: string) {
  if (!API_BASE_URL) {
    throw new ApiError('configuration');
  }
  return `${API_BASE_URL}${path}`;
}

export async function ensureApiReady({ force = false }: { force?: boolean } = {}) {
  if (!force && healthyUntil > Date.now()) {
    return;
  }
  if (healthPromise) {
    return healthPromise;
  }

  healthPromise = requestJson(apiUrl('/health'), {
    retryCount: 1,
    timeoutMs: HEALTH_TIMEOUT_MS,
    validate: normalizeHealthResponse,
  })
    .then(() => {
      healthyUntil = Date.now() + HEALTH_CACHE_MS;
    })
    .finally(() => {
      healthPromise = null;
    });
  return healthPromise;
}

export function prewarmApi() {
  return ensureApiReady().catch(() => undefined);
}

export function fetchSupportedLabels(signal?: AbortSignal) {
  return requestJson(apiUrl('/material_labels'), {
    retryCount: 1,
    signal,
    timeoutMs: GET_TIMEOUT_MS,
    validate: normalizeSupportedLabelsResponse,
  });
}

export function fetchPrediction({
  body,
  headers,
  signal,
}: {
  body: FormData;
  headers: Record<string, string>;
  signal?: AbortSignal;
}): Promise<PredictionResponse> {
  return requestJson(apiUrl('/predict'), {
    init: {
      method: 'POST',
      headers,
      body,
    },
    signal,
    timeoutMs: PREDICT_TIMEOUT_MS,
    validate: normalizePredictionResponse,
  });
}

export function fetchNearbyLocations(
  query: URLSearchParams,
  signal?: AbortSignal,
) {
  return requestJson(apiUrl(`/nearby_locations?${query.toString()}`), {
    retryCount: 1,
    signal,
    timeoutMs: GET_TIMEOUT_MS,
    validate: normalizeNearbyLocationsResponse,
  });
}

export function sendFeedback(
  requestId: string,
  update: FeedbackUpdate,
  signal?: AbortSignal,
) {
  return requestJson(apiUrl(`/feedback/${encodeURIComponent(requestId)}`), {
    init: {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(update),
    },
    signal,
    timeoutMs: FEEDBACK_TIMEOUT_MS,
    validate: (value) => normalizeFeedbackResponse(value, requestId),
  });
}

export function sendScanFeedback(
  submission: ScanFeedbackSubmission,
  signal?: AbortSignal,
) {
  return requestJson(
    apiUrl(`/scan-feedback/${encodeURIComponent(submission.request_id)}`),
    {
      init: {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(submission),
      },
      signal,
      timeoutMs: FEEDBACK_TIMEOUT_MS,
      validate: (value) => normalizeFeedbackResponse(value, submission.request_id),
    },
  );
}

