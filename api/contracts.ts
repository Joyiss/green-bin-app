export type PredictionStatus = 'confident' | 'uncertain' | 'unknown';

export type PredictionClarification = {
  required?: unknown;
  reason_codes?: unknown;
  retake_recommended?: unknown;
  retake_guidance?: unknown;
  message?: unknown;
};

export type LocalGuidanceSource = {
  source_id: string | null;
  title: string;
  publisher: string | null;
  url: string;
  accessed: string | null;
};

export type LocalGuidanceDestination = {
  location_id: string;
  name: string;
  address: string;
  phone: string | null;
  hours: string | null;
  payment: string | null;
  directions_url: string | null;
};

export type LocalGuidance = {
  dataset_id: string;
  rules_version: string;
  rule_id: string;
  program_id: string;
  decision: string;
  applicability: 'applicable' | 'conditional' | 'excluded';
  local_action: string;
  preparation: string[];
  restrictions: string[];
  fees: {
    currency: string | null;
    line_items: Array<{
      label: string;
      amount: number;
      unit: string;
    }>;
  } | null;
  sources: LocalGuidanceSource[];
  earth911_material_label: string | null;
  allowed_location_names: string[];
  destinations: LocalGuidanceDestination[];
};

export type GuidanceSummary = {
  action_type: string;
  destination: string | null;
  qualifier: string | null;
};

export type GuidancePreparation = {
  required: boolean;
  steps: string[];
  no_preparation_message: string | null;
};

export type GuidanceReference = {
  source_title: string;
  url: string;
  supports_claim: string;
};

export type StructuredGuidance = {
  summary: GuidanceSummary;
  disposal_steps: string[];
  preparation: GuidancePreparation;
  important_notes: string[];
  reasoning: string;
  references: GuidanceReference[];
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
  guidance?: StructuredGuidance;
  prep_steps: string[];
  next_step: string | null;
  alternatives: string[];
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
  jurisdiction_id?: string;
  local_guidance?: LocalGuidance;
  daily_limit?: number;
  dailyLimit?: number;
  daily_scans_remaining?: number;
  dailyScansRemaining?: number;
  daily_reset_at?: string;
  dailyResetAt?: string;
  monthly_limit?: number;
  monthlyLimit?: number;
  monthly_scans_remaining?: number;
  monthlyScansRemaining?: number;
  monthly_reset_at?: string;
  monthlyResetAt?: string;
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
  error: 'daily_scan_limit_reached' | 'monthly_scan_limit_reached';
  daily_limit?: number;
  daily_scans_remaining?: number;
  daily_reset_at?: string;
  monthly_limit?: number;
  monthly_scans_remaining?: number;
  monthly_reset_at?: string;
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
  phone: string | null;
  source: string | null;
  official: boolean;
};

export type NearbyLocationsResponse = {
  item: string;
  material_id: number | null;
  locations: NearbyLocationResponse[];
  reason: 'unsupported_material' | null;
  earth911_search_skipped: boolean;
  material_resolution: Record<string, unknown> | null;
};

export type ProviderVerificationStatus = 'verified' | 'not_verified' | 'uncertain';
export type ProviderMatch = 'confirmed' | 'rejected' | 'uncertain';

export type ProviderEvidence = {
  title: string;
  url: string;
  snippet: string;
};

export type ProviderVerificationResult = {
  status: ProviderVerificationStatus;
  name: string;
  services: string[];
  match: ProviderMatch;
  reason: string;
  evidence: ProviderEvidence[];
};

export type ServiceProviderRecord = {
  id: string;
  canonical_name: string;
  raw_input_name: string;
  services: string[];
  city: string;
  state: string;
  county: string | null;
  status: ProviderVerificationStatus;
  evidence_urls: string[];
  verified_at: string;
};

export type ProviderRestriction = {
  reason: 'failed_attempts' | 'successful_confirmation' | 'verification_in_progress';
  retry_at: string;
};

export type VerifyProviderResponse = {
  verification_id: string;
  cached: boolean;
  result: ProviderVerificationResult;
  cooldown: ProviderRestriction | null;
};

export type CurrentProviderResponse = {
  provider: ServiceProviderRecord | null;
  restriction: ProviderRestriction | null;
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

function optionalSourceUrl(value: unknown) {
  const candidate = text(value);
  if (!candidate) {
    return null;
  }
  try {
    const parsed = new URL(candidate);
    return parsed.protocol === 'https:' || parsed.protocol === 'http:'
      ? parsed.toString()
      : null;
  } catch {
    return null;
  }
}

function obviousDuplicate(first?: string | null, second?: string | null) {
  if (!first || !second) return false;
  const normalize = (candidate: string) => candidate
    .toLocaleLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();
  const left = normalize(first);
  const right = normalize(second);
  return left === right || (
    Math.min(left.length, right.length) >= 24
    && (left.includes(right) || right.includes(left))
  );
}

function normalizeStructuredGuidance(value: unknown): StructuredGuidance | undefined {
  if (!isRecord(value) || !isRecord(value.summary) || !isRecord(value.preparation)) {
    return undefined;
  }
  const actionType = text(value.summary.action_type);
  if (!actionType) return undefined;
  const destination = text(value.summary.destination);
  const rawQualifier = text(value.summary.qualifier);
  let qualifier = obviousDuplicate(rawQualifier, actionType)
    || obviousDuplicate(rawQualifier, destination)
    ? null
    : rawQualifier;
  const rawSteps = stringArray(value.preparation.steps);
  if (qualifier && rawSteps.some((step) => obviousDuplicate(step, qualifier))) {
    qualifier = null;
  }
  const summaryValues = [actionType, destination, qualifier];
  const disposalSteps = stringArray(value.disposal_steps).filter(
    (step, index, all) => all.findIndex((existing) => obviousDuplicate(step, existing)) === index,
  );
  const steps = rawSteps.filter(
    (step, index, all) => !summaryValues.some((existing) => obviousDuplicate(step, existing))
      && all.findIndex((existing) => obviousDuplicate(step, existing)) === index,
  );
  const importantNotes = stringArray(value.important_notes).filter(
    (note, index, all) => ![...summaryValues, ...steps].some(
      (existing) => obviousDuplicate(note, existing),
    ) && all.findIndex((existing) => obviousDuplicate(note, existing)) === index,
  );
  const references = Array.isArray(value.references)
    ? value.references.flatMap((candidate) => {
        if (!isRecord(candidate)) return [];
        const sourceTitle = text(candidate.source_title);
        const url = optionalSourceUrl(candidate.url);
        const supportsClaim = text(candidate.supports_claim);
        return sourceTitle && url && supportsClaim
          ? [{ source_title: sourceTitle, url, supports_claim: supportsClaim }]
          : [];
      }).filter((reference, index, all) => all.findIndex(
        (candidate) => candidate.url.toLocaleLowerCase().replace(/\/+$/, '')
          === reference.url.toLocaleLowerCase().replace(/\/+$/, ''),
      ) === index)
    : [];
  return {
    summary: { action_type: actionType, destination, qualifier },
    disposal_steps: disposalSteps,
    preparation: {
      required: steps.length > 0,
      steps,
      no_preparation_message: steps.length
        ? null
        : text(value.preparation.no_preparation_message),
    },
    important_notes: importantNotes,
    reasoning: text(value.reasoning) ?? '',
    references,
  };
}

function normalizeLocalGuidance(value: unknown): LocalGuidance | undefined {
  if (!isRecord(value)) {
    return undefined;
  }
  const datasetId = text(value.dataset_id);
  const rulesVersion = text(value.rules_version);
  const ruleId = text(value.rule_id);
  const programId = text(value.program_id);
  const decision = text(value.decision);
  const localAction = text(value.local_action);
  const applicability = value.applicability;
  if (
    !datasetId ||
    !rulesVersion ||
    !ruleId ||
    !programId ||
    !decision ||
    !localAction ||
    (applicability !== 'applicable' &&
      applicability !== 'conditional' &&
      applicability !== 'excluded')
  ) {
    return undefined;
  }

  const fees = isRecord(value.fees)
    ? {
        currency: text(value.fees.currency),
        line_items: Array.isArray(value.fees.line_items)
          ? value.fees.line_items
              .map((item) => {
                if (!isRecord(item)) {
                  return null;
                }
                const label = text(item.label);
                const unit = text(item.unit);
                const amount =
                  typeof item.amount === 'number' && Number.isFinite(item.amount)
                    ? item.amount
                    : null;
                return label && unit && amount !== null && amount >= 0
                  ? { label, amount, unit }
                  : null;
              })
              .filter(
                (
                  item,
                ): item is { label: string; amount: number; unit: string } =>
                  item !== null,
              )
          : [],
      }
    : null;
  const sources = Array.isArray(value.sources)
    ? value.sources
        .map((source) => {
          if (!isRecord(source)) {
            return null;
          }
          const title = text(source.title);
          const url = optionalSourceUrl(source.url);
          return title && url
            ? {
                source_id: text(source.source_id),
                title,
                publisher: text(source.publisher),
                url,
                accessed: text(source.accessed),
              }
            : null;
        })
        .filter((source): source is LocalGuidanceSource => source !== null)
    : [];
  const destinations = Array.isArray(value.destinations)
    ? value.destinations
        .map((destination) => {
          if (!isRecord(destination)) {
            return null;
          }
          const locationId = text(destination.location_id);
          const name = text(destination.name);
          if (!locationId || !name) {
            return null;
          }
          return {
            location_id: locationId,
            name,
            address: text(destination.address) ?? 'Address unavailable',
            phone: text(destination.phone),
            hours: text(destination.hours),
            payment: text(destination.payment),
            directions_url: optionalHttpsUrl(destination.directions_url),
          };
        })
        .filter(
          (destination): destination is LocalGuidanceDestination =>
            destination !== null,
        )
    : [];

  return {
    dataset_id: datasetId,
    rules_version: rulesVersion,
    rule_id: ruleId,
    program_id: programId,
    decision,
    applicability,
    local_action: localAction,
    preparation: stringArray(value.preparation),
    restrictions: stringArray(value.restrictions),
    fees,
    sources,
    earth911_material_label: text(value.earth911_material_label),
    allowed_location_names: stringArray(value.allowed_location_names),
    destinations,
  };
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
    guidance: normalizeStructuredGuidance(value.guidance),
    prep_steps: stringArray(value.prep_steps),
    next_step: text(value.next_step),
    alternatives: stringArray(value.alternatives),
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
    jurisdiction_id: text(value.jurisdiction_id) ?? undefined,
    local_guidance: normalizeLocalGuidance(value.local_guidance),
    daily_limit: finiteInteger(value.daily_limit, 1),
    dailyLimit: finiteInteger(value.dailyLimit, 1),
    daily_scans_remaining: finiteInteger(value.daily_scans_remaining),
    dailyScansRemaining: finiteInteger(value.dailyScansRemaining),
    daily_reset_at: text(value.daily_reset_at) ?? undefined,
    dailyResetAt: text(value.dailyResetAt) ?? undefined,
    monthly_limit: finiteInteger(value.monthly_limit, 1),
    monthlyLimit: finiteInteger(value.monthlyLimit, 1),
    monthly_scans_remaining: finiteInteger(value.monthly_scans_remaining),
    monthlyScansRemaining: finiteInteger(value.monthlyScansRemaining),
    monthly_reset_at: text(value.monthly_reset_at) ?? undefined,
    monthlyResetAt: text(value.monthlyResetAt) ?? undefined,
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
  if (
    !isRecord(value) ||
    (value.error !== 'daily_scan_limit_reached' &&
      value.error !== 'monthly_scan_limit_reached')
  ) {
    return null;
  }
  return {
    error: value.error,
    daily_limit: finiteInteger(value.daily_limit ?? value.dailyLimit, 1),
    daily_scans_remaining: finiteInteger(
      value.daily_scans_remaining ?? value.dailyScansRemaining,
    ),
    daily_reset_at: text(value.daily_reset_at ?? value.dailyResetAt) ?? undefined,
    monthly_limit: finiteInteger(value.monthly_limit ?? value.monthlyLimit, 1),
    monthly_scans_remaining: finiteInteger(
      value.monthly_scans_remaining ?? value.monthlyScansRemaining,
    ),
    monthly_reset_at: text(value.monthly_reset_at ?? value.monthlyResetAt) ?? undefined,
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
    phone: text(value.phone),
    source: text(value.source),
    official: value.official === true,
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

function safeEvidenceUrl(value: unknown) {
  const candidate = text(value);
  if (!candidate) return null;
  try {
    const parsed = new URL(candidate);
    if ((parsed.protocol !== 'http:' && parsed.protocol !== 'https:') || !parsed.hostname) {
      return null;
    }
    return candidate;
  } catch {
    return null;
  }
}

function normalizeProviderStatus(value: unknown): ProviderVerificationStatus | null {
  return value === 'verified' || value === 'not_verified' || value === 'uncertain'
    ? value
    : null;
}

function normalizeProviderRestriction(value: unknown): ProviderRestriction | null {
  if (!isRecord(value)) return null;
  const reason = value.reason ?? value.cooldown_reason;
  const retryAt = text(value.retry_at);
  if (
    (reason !== 'failed_attempts' &&
      reason !== 'successful_confirmation' &&
      reason !== 'verification_in_progress') ||
    !retryAt ||
    Number.isNaN(Date.parse(retryAt))
  ) {
    return null;
  }
  return { reason, retry_at: retryAt };
}

export function normalizeProviderVerificationResult(value: unknown): ProviderVerificationResult {
  if (!isRecord(value)) {
    throw new ApiContractError('Provider verification result is invalid.');
  }
  const status = normalizeProviderStatus(value.status);
  const match =
    value.match === 'confirmed' || value.match === 'rejected' || value.match === 'uncertain'
      ? value.match
      : null;
  const expectedMatch = status
    ? { verified: 'confirmed', not_verified: 'rejected', uncertain: 'uncertain' }[status]
    : null;
  const name = text(value.name);
  const reason = text(value.reason);
  if (!status || !match || match !== expectedMatch || !name || !reason || !Array.isArray(value.evidence)) {
    throw new ApiContractError('Provider verification result is inconsistent.');
  }
  const evidence = value.evidence.map((item) => {
    if (!isRecord(item)) throw new ApiContractError('Provider evidence is invalid.');
    const title = text(item.title);
    const url = safeEvidenceUrl(item.url);
    const snippet = text(item.snippet);
    if (!title || !url || !snippet) throw new ApiContractError('Provider evidence is invalid.');
    return { title, url, snippet };
  });
  return { status, name, services: stringArray(value.services), match, reason, evidence };
}

function normalizeServiceProviderRecord(value: unknown): ServiceProviderRecord {
  if (!isRecord(value)) throw new ApiContractError('Service provider record is invalid.');
  const id = text(value.id);
  const canonicalName = text(value.canonical_name);
  const rawInputName = text(value.raw_input_name);
  const city = text(value.city);
  const state = text(value.state);
  const status = normalizeProviderStatus(value.status);
  const verifiedAt = text(value.verified_at);
  if (!id || !canonicalName || !rawInputName || !city || !state || !status || !verifiedAt) {
    throw new ApiContractError('Service provider record is invalid.');
  }
  const evidenceUrls = Array.isArray(value.evidence_urls)
    ? value.evidence_urls.map(safeEvidenceUrl).filter((url): url is string => url !== null)
    : [];
  return {
    id, canonical_name: canonicalName, raw_input_name: rawInputName,
    services: stringArray(value.services), city, state, county: text(value.county), status,
    evidence_urls: evidenceUrls, verified_at: verifiedAt,
  };
}

export function normalizeVerifyProviderResponse(value: unknown): VerifyProviderResponse {
  if (!isRecord(value)) throw new ApiContractError('Provider verification response is invalid.');
  const verificationId = text(value.verification_id);
  if (!verificationId || typeof value.cached !== 'boolean') {
    throw new ApiContractError('Provider verification response is invalid.');
  }
  return {
    verification_id: verificationId,
    cached: value.cached,
    result: normalizeProviderVerificationResult(value.result),
    cooldown: normalizeProviderRestriction(value.cooldown),
  };
}

export function normalizeCurrentProviderResponse(value: unknown): CurrentProviderResponse {
  if (!isRecord(value)) throw new ApiContractError('Current provider response is invalid.');
  return {
    provider: value.provider === null ? null : normalizeServiceProviderRecord(value.provider),
    restriction: normalizeProviderRestriction(value.restriction),
  };
}

export function normalizeConfirmProviderResponse(value: unknown) {
  if (!isRecord(value)) throw new ApiContractError('Provider confirmation response is invalid.');
  return { provider: normalizeServiceProviderRecord(value.provider) };
}

export function normalizeProviderCooldownError(value: unknown): ProviderRestriction | null {
  if (!isRecord(value)) return null;
  const detail = isRecord(value.detail) ? value.detail : value;
  return normalizeProviderRestriction(detail);
}
