export type PredictionStatus = 'confident' | 'uncertain' | 'unknown';

export type PredictionClarification = {
  required?: unknown;
  reason_codes?: unknown;
  retake_recommended?: unknown;
  retake_guidance?: unknown;
  message?: unknown;
};

export type RawPredictionCandidate =
  | string
  | {
      label?: unknown;
      name?: unknown;
      item_label?: unknown;
      selected_item?: unknown;
      selectedItem?: unknown;
      score?: unknown;
      confidence?: unknown;
      similarity?: unknown;
      guidance_supported?: unknown;
      guidanceSupported?: unknown;
    }
  | [unknown, unknown?];

export type PredictionResponse = {
  request_id?: string;
  item: string;
  category: string;
  status: PredictionStatus;
  candidates?: RawPredictionCandidate[] | null;
  disposal_action: string | null;
  material_code: string | null;
  impact_level: string | null;
  summary?: string | null;
  steps: string[];
  guidance_source?: string;
  guidanceSource?: string;
  recognition_source?: string;
  recognitionSource?: string;
  recognition_confidence?: Record<string, unknown>;
  recognitionConfidence?: Record<string, unknown>;
  clarification?: PredictionClarification | null;
  guidance_confidence?: Record<string, unknown>;
  guidanceConfidence?: Record<string, unknown>;
  warnings?: string[];
  guidance_metadata?: Record<string, unknown>;
  guidanceMetadata?: Record<string, unknown>;
  daily_limit?: number;
  dailyLimit?: number;
  scans_remaining?: number;
  scansRemaining?: number;
  reset_at?: string;
  resetAt?: string;
  recognition_details?: {
    candidates?: RawPredictionCandidate[] | null;
    raw_item_label?: unknown;
    normalized?: {
      normalized_item?: unknown;
      disposal_category?: unknown;
      broad_category?: unknown;
      material_category?: unknown;
      item_label?: unknown;
      matched_supported_label?: unknown;
    } | null;
  } | null;
};

export type ScanLimitResponse = {
  error: 'daily_scan_limit_reached';
  daily_limit?: number;
  scans_remaining?: number;
  reset_at?: string;
};

export type NearbyLocationResponse = {
  id: string;
  type: string;
  name: string;
  address: string;
  status: string;
  distance: string;
  accent: string;
  mapStyle: 'grid' | 'building' | 'pin';
  directionsUrl: string | null;
};

export type NearbyLocationsResponse = {
  item: string;
  material_id: number | null;
  locations: NearbyLocationResponse[];
  reason: 'unsupported_material' | null;
  earth911_search_skipped: boolean;
  material_resolution: Record<string, unknown> | null;
};

export class ApiContractError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ApiContractError';
  }
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function text(value: unknown) {
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}

function optionalRecord(value: unknown) {
  return isRecord(value) ? value : undefined;
}

function stringArray(value: unknown) {
  return Array.isArray(value)
    ? value
        .map((item) => text(item))
        .filter((item): item is string => item !== null)
    : [];
}

function finiteInteger(value: unknown, minimum = 0) {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return undefined;
  }
  const normalized = Math.floor(value);
  return normalized >= minimum ? normalized : undefined;
}

function optionalHttpsUrl(value: unknown) {
  const candidate = text(value);
  if (!candidate) {
    return null;
  }
  try {
    const parsed = new URL(candidate);
    return parsed.protocol === 'https:' ? parsed.toString() : null;
  } catch {
    return null;
  }
}

export function normalizePredictionResponse(value: unknown): PredictionResponse {
  if (!isRecord(value)) {
    throw new ApiContractError('Prediction response must be an object.');
  }

  const status = value.status;
  if (status !== 'confident' && status !== 'uncertain' && status !== 'unknown') {
    throw new ApiContractError('Prediction status is invalid.');
  }

  const item = text(value.item) ?? '';
  if (status === 'confident' && !item) {
    throw new ApiContractError('A confident prediction requires an item.');
  }

  const recognitionDetails = optionalRecord(value.recognition_details);
  const normalizedDetails = optionalRecord(recognitionDetails?.normalized);
  const candidates = Array.isArray(value.candidates)
    ? (value.candidates as RawPredictionCandidate[])
    : null;
  const recognitionCandidates = Array.isArray(recognitionDetails?.candidates)
    ? (recognitionDetails.candidates as RawPredictionCandidate[])
    : null;

  return {
    request_id: text(value.request_id)?.slice(0, 96),
    item,
    category: text(value.category) ?? 'Unknown',
    status,
    candidates,
    disposal_action: text(value.disposal_action),
    material_code: text(value.material_code),
    impact_level: text(value.impact_level),
    summary: text(value.summary),
    steps: stringArray(value.steps),
    guidance_source: text(value.guidance_source) ?? undefined,
    guidanceSource: text(value.guidanceSource) ?? undefined,
    recognition_source: text(value.recognition_source) ?? undefined,
    recognitionSource: text(value.recognitionSource) ?? undefined,
    recognition_confidence: optionalRecord(value.recognition_confidence),
    recognitionConfidence: optionalRecord(value.recognitionConfidence),
    clarification: isRecord(value.clarification)
      ? (value.clarification as PredictionClarification)
      : null,
    guidance_confidence: optionalRecord(value.guidance_confidence),
    guidanceConfidence: optionalRecord(value.guidanceConfidence),
    warnings: stringArray(value.warnings),
    guidance_metadata: optionalRecord(value.guidance_metadata),
    guidanceMetadata: optionalRecord(value.guidanceMetadata),
    daily_limit: finiteInteger(value.daily_limit, 1),
    dailyLimit: finiteInteger(value.dailyLimit, 1),
    scans_remaining: finiteInteger(value.scans_remaining),
    scansRemaining: finiteInteger(value.scansRemaining),
    reset_at: text(value.reset_at) ?? undefined,
    resetAt: text(value.resetAt) ?? undefined,
    recognition_details: recognitionDetails
      ? {
          candidates: recognitionCandidates,
          raw_item_label: recognitionDetails.raw_item_label,
          normalized: normalizedDetails
            ? {
                normalized_item: normalizedDetails.normalized_item,
                disposal_category: normalizedDetails.disposal_category,
                broad_category: normalizedDetails.broad_category,
                material_category: normalizedDetails.material_category,
                item_label: normalizedDetails.item_label,
                matched_supported_label: normalizedDetails.matched_supported_label,
              }
            : null,
        }
      : null,
  };
}

export function normalizeScanLimitResponse(value: unknown): ScanLimitResponse | null {
  if (!isRecord(value) || value.error !== 'daily_scan_limit_reached') {
    return null;
  }
  return {
    error: 'daily_scan_limit_reached',
    daily_limit: finiteInteger(value.daily_limit ?? value.dailyLimit, 1),
    scans_remaining: finiteInteger(value.scans_remaining ?? value.scansRemaining),
    reset_at: text(value.reset_at ?? value.resetAt) ?? undefined,
  };
}

export function normalizeHealthResponse(value: unknown) {
  if (!isRecord(value) || value.status !== 'ok') {
    throw new ApiContractError('Health response is invalid.');
  }
  return { status: 'ok' as const };
}

export function normalizeFeedbackResponse(value: unknown, requestId: string) {
  if (
    !isRecord(value) ||
    value.recorded !== true ||
    text(value.request_id) !== requestId
  ) {
    throw new ApiContractError('Feedback acknowledgement is invalid.');
  }
  return { recorded: true as const, request_id: requestId };
}

export function normalizeSupportedLabelsResponse(value: unknown) {
  if (!isRecord(value) || !Array.isArray(value.labels)) {
    throw new ApiContractError('Supported labels response is invalid.');
  }
  const labels = [...new Set(stringArray(value.labels))];
  if (!labels.length) {
    throw new ApiContractError('Supported labels response is empty.');
  }
  return { labels };
}

const LOCATION_ACCENTS = ['#88D39D', '#F2C572', '#7FC6FF'] as const;

function normalizeLocation(value: unknown, index: number): NearbyLocationResponse | null {
  if (!isRecord(value)) {
    return null;
  }
  const id = text(value.id);
  const name = text(value.name);
  if (!id || !name) {
    return null;
  }
  const mapStyle =
    value.mapStyle === 'grid' || value.mapStyle === 'building' || value.mapStyle === 'pin'
      ? value.mapStyle
      : 'pin';
  const accent = text(value.accent);

  return {
    id,
    type: text(value.type) ?? 'Recycling site',
    name,
    address: text(value.address) ?? 'Address unavailable',
    status: text(value.status) ?? 'Hours unavailable',
    distance: text(value.distance) ?? 'Distance unavailable',
    accent:
      accent && /^#[0-9a-f]{6}$/i.test(accent)
        ? accent
        : LOCATION_ACCENTS[index % LOCATION_ACCENTS.length],
    mapStyle,
    directionsUrl: optionalHttpsUrl(value.directionsUrl),
  };
}

export function normalizeNearbyLocationsResponse(value: unknown): NearbyLocationsResponse {
  if (!isRecord(value) || !Array.isArray(value.locations)) {
    throw new ApiContractError('Nearby locations response is invalid.');
  }
  const reason = value.reason === 'unsupported_material' ? value.reason : null;
  const materialId = finiteInteger(value.material_id, 1);

  return {
    item: text(value.item) ?? '',
    material_id: materialId ?? null,
    locations: value.locations
      .map(normalizeLocation)
      .filter((location): location is NearbyLocationResponse => location !== null),
    reason,
    earth911_search_skipped: value.earth911_search_skipped === true,
    material_resolution: isRecord(value.material_resolution)
      ? value.material_resolution
      : null,
  };
}
