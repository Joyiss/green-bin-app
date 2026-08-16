import {
  normalizeFeedbackResponse,
  normalizeHealthResponse,
  normalizeNearbyLocationsResponse,
  normalizePredictionResponse,
  normalizeSupportedLabelsResponse,
  normalizeConfirmProviderResponse,
  normalizeCurrentProviderResponse,
  normalizeVerifyProviderResponse,
  type PredictionResponse,
} from '@/api/contracts';
import { ApiError, requestJson } from '@/api/request';
import { API_BASE_URL } from '@/constants/api';
import type { FeedbackUpdate, ScanFeedbackSubmission } from '@/app/feedback-flow';

const HEALTH_TIMEOUT_MS = 30_000;
const PREDICT_TIMEOUT_MS = 90_000;
const GET_TIMEOUT_MS = 20_000;
const FEEDBACK_TIMEOUT_MS = 15_000;
const PROVIDER_TIMEOUT_MS = 45_000;
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

export type ProviderLocationRequest = { city: string; state: string; county?: string };

export function fetchCurrentProvider(
  location: ProviderLocationRequest,
  clientId: string,
  signal?: AbortSignal,
) {
  const query = new URLSearchParams({ city: location.city, state: location.state });
  if (location.county) query.set('county', location.county);
  return requestJson(apiUrl(`/service-providers/current?${query.toString()}`), {
    init: { headers: { 'X-GreenBin-Client-Id': clientId } },
    signal,
    timeoutMs: GET_TIMEOUT_MS,
    validate: normalizeCurrentProviderResponse,
  });
}

export function verifyServiceProvider(
  serviceName: string,
  location: ProviderLocationRequest,
  clientId: string,
  signal?: AbortSignal,
) {
  return requestJson(apiUrl('/service-providers/verify'), {
    init: {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-GreenBin-Client-Id': clientId },
      body: JSON.stringify({ service_name: serviceName, location }),
    },
    signal,
    timeoutMs: PROVIDER_TIMEOUT_MS,
    validate: normalizeVerifyProviderResponse,
  });
}

export function confirmServiceProvider(
  verificationId: string,
  rawInputName: string,
  clientId: string,
  signal?: AbortSignal,
) {
  return requestJson(apiUrl('/service-providers/confirm'), {
    init: {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-GreenBin-Client-Id': clientId },
      body: JSON.stringify({ verification_id: verificationId, raw_input_name: rawInputName }),
    },
    signal,
    timeoutMs: PROVIDER_TIMEOUT_MS,
    validate: normalizeConfirmProviderResponse,
  });
}

