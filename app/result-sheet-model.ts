import type { LocalGuidance, PredictionResponse } from '@/api/contracts';

export type ResultSheetFact = {
  label: string;
  value: string;
};

export type ResultSheetStep = {
  title: string;
  body?: string;
};

export type ResultSheetReference = {
  description?: string;
  domain: string;
  role: string;
  title: string;
  url: string;
};

export type ResultSheetEvidence = {
  summary?: string;
  rows: ResultSheetFact[];
};

export type ResultSheetPrimaryAction = {
  behavior: 'nearby' | 'scroll_steps';
  label: string;
};

export type ResultSheetPresentation = {
  action: string;
  bestOption: string;
  destinationLabel?: string;
  evidence: ResultSheetEvidence | null;
  facts: ResultSheetFact[];
  item: string;
  keyQualifier?: string;
  noPreparationMessage?: string;
  preparationSteps?: ResultSheetStep[];
  primaryAction: ResultSheetPrimaryAction | null;
  references: ResultSheetReference[];
  status: ResultSheetFact[];
  steps: ResultSheetStep[];
  warnings: string[];
};

type PresentationOptions = {
  location?: {
    city?: string | null;
    state?: string | null;
  } | null;
  showNearbyButton?: boolean;
};

function record(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function text(value: unknown) {
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}

function strings(value: unknown) {
  return Array.isArray(value)
    ? value.map(text).filter((item): item is string => item !== null)
    : [];
}

function uniqueStrings(values: (string | null | undefined)[]) {
  const seen = new Set<string>();
  return values.filter((value): value is string => {
    if (!value) {
      return false;
    }
    const key = value.toLocaleLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
    if (!key || seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

function normalizedText(value: string) {
  return value.toLocaleLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
}

function repeatsText(first?: string | null, second?: string | null) {
  if (!first || !second) return false;
  const left = normalizedText(first);
  const right = normalizedText(second);
  if (!left || !right) return false;
  return left === right || (
    Math.min(left.length, right.length) >= 24
    && (left.includes(right) || right.includes(left))
  );
}

function guidanceMetadata(response: PredictionResponse) {
  return record(response.guidanceMetadata) ?? record(response.guidance_metadata) ?? {};
}

function metadataArray(metadata: Record<string, unknown>, ...keys: string[]) {
  for (const key of keys) {
    if (Array.isArray(metadata[key])) {
      return metadata[key] as unknown[];
    }
  }
  return [];
}

function metadataText(metadata: Record<string, unknown>, ...keys: string[]) {
  for (const key of keys) {
    const value = text(metadata[key]);
    if (value) {
      return value;
    }
  }
  return null;
}

function normalizedRecognitionValue(response: PredictionResponse, key: string) {
  return text(record(response.recognition_details?.normalized)?.[key]);
}

export function splitGuidanceStep(step: string): ResultSheetStep {
  const normalized = step.trim();
  const colonMatch = normalized.match(/^([^:]{3,56}):\s+(.+)$/);
  if (colonMatch && colonMatch[1].trim().split(/\s+/).length <= 8) {
    return { title: colonMatch[1].trim(), body: colonMatch[2].trim() };
  }

  const sentenceMatch = normalized.match(/^(.{3,70}?[.!?])\s+(.+)$/);
  if (sentenceMatch) {
    return { title: sentenceMatch[1].trim(), body: sentenceMatch[2].trim() };
  }

  return { title: normalized };
}

export function sourceUrlKey(value: string) {
  const candidate = value.trim();
  try {
    const parsed = new URL(candidate);
    const host = parsed.host.toLocaleLowerCase().replace(/^www\./, '');
    const path = parsed.pathname.replace(/\/{2,}/g, '/').replace(/\/+$/, '');
    return `${host}${path}`.toLocaleLowerCase();
  } catch {
    return candidate
      .replace(/^[a-z][a-z0-9+.-]*:\/\//i, '')
      .split(/[?#]/, 1)[0]
      .replace(/^www\./i, '')
      .replace(/\/+$/, '')
      .toLocaleLowerCase();
  }
}

function sourceDomain(url: string) {
  try {
    return new URL(url).host.replace(/^www\./i, '');
  } catch {
    return url.replace(/^[a-z][a-z0-9+.-]*:\/\//i, '').split(/[/?#]/, 1)[0];
  }
}

function sourceRoleLabel(source: Record<string, unknown>) {
  const role = text(source.source_role)?.toLocaleLowerCase();
  if (role === 'direct_service_provider') {
    return 'Local service provider';
  }
  if (role === 'retailer_takeback') {
    return 'Retail take-back program';
  }
  if (role === 'reputable_supporting') {
    return 'Supporting source';
  }
  if (role === 'official_primary') {
    const jurisdiction = record(source.jurisdiction);
    const scope = text(jurisdiction?.location_scope)?.toLocaleLowerCase() ?? '';
    const trust = text(source.trust_level)?.toLocaleLowerCase() ?? '';
    return /city|county|local|provider/.test(`${scope} ${trust}`)
      ? 'Official local guidance'
      : 'Public agency guidance';
  }
  return 'Supporting source';
}

function referenceFromAcceptedSource(value: unknown): ResultSheetReference | null {
  const source = record(value);
  if (!source || text(source.source_role)?.toLocaleLowerCase() === 'discovery_only') {
    return null;
  }
  const url = text(source.url);
  const title = text(source.title) ?? text(source.organization);
  if (!url || !title) {
    return null;
  }
  const description = text(source.support_description);
  return {
    ...(description ? { description } : {}),
    domain: sourceDomain(url),
    role: sourceRoleLabel(source),
    title,
    url,
  };
}

function referenceFromLocalSource(value: LocalGuidance['sources'][number]) {
  return {
    domain: sourceDomain(value.url),
    role: 'Official local guidance',
    title: value.title,
    url: value.url,
  } satisfies ResultSheetReference;
}

function buildReferences(response: PredictionResponse, metadata: Record<string, unknown>) {
  const structuredReferences: ResultSheetReference[] = (response.guidance?.references ?? []).map(
    (source) => ({
      description: source.supports_claim,
      domain: sourceDomain(source.url),
      role: 'Supporting source',
      title: source.source_title,
      url: source.url,
    }),
  );
  const references = structuredReferences.length ? structuredReferences : metadataArray(metadata, 'accepted_sources', 'acceptedSources')
    .map(referenceFromAcceptedSource)
    .filter((value): value is ResultSheetReference => value !== null);

  for (const source of response.local_guidance?.sources ?? []) {
    references.push(referenceFromLocalSource(source));
  }

  const sourceNames = strings(metadata.source_names ?? metadata.sourceNames);
  const sourceUrls = strings(metadata.source_urls ?? metadata.sourceUrls);
  sourceUrls.forEach((url, index) => {
    references.push({
      domain: sourceDomain(url),
      role: 'Supporting source',
      title: sourceNames[index] ?? sourceDomain(url),
      url,
    });
  });

  const seen = new Set<string>();
  return references.filter((reference) => {
    const key = sourceUrlKey(reference.url);
    if (!key || seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

function actionLabel(value: string | null) {
  const action = (value ?? '').trim().toLocaleLowerCase();
  if (action === 'donate/reuse') return 'Donate or reuse';
  if (action === 'drop-off' || action === 'household hazardous waste') return 'Drop off';
  if (action === 'check local guidance') return 'Check local guidance';
  if (action === 'recycle') return 'Recycle';
  if (action === 'compost') return 'Compost';
  if (action === 'trash') return 'Use trash';
  return text(value) ?? '';
}

export function isPreparationInstruction(value: string) {
  const normalized = normalizedText(value);
  if (!normalized) return false;
  const preparation = /\b(empty|rinse|wash|clean|dry|drain|remove|detach|separate|sort|bag|wrap|package|pack|seal|close|cap|secure|tape|protect|wipe|erase|delete|back up|disconnect)\b|\b(keep|leave)\b.{0,40}\bintact\b/;
  const route = /\b(schedule|appointment|visit|call|contact|take|bring|deliver|drop off|find|choose|travel|drive|hours|directions)\b/;
  return preparation.test(normalized) && (!route.test(normalized) || /\b(bag|wrap|package|seal|secure|tape|protect)\b/.test(normalized));
}

function acceptedSourcePrograms(metadata: Record<string, unknown>) {
  return metadataArray(metadata, 'accepted_sources', 'acceptedSources')
    .map((value) => text(record(value)?.program_name ?? record(value)?.programName))
    .filter((value): value is string => value !== null);
}

function acceptedSourceQualifiers(metadata: Record<string, unknown>) {
  const qualifiers: string[] = [];
  for (const value of metadataArray(metadata, 'accepted_sources', 'acceptedSources')) {
    const source = record(value);
    if (!source) continue;
    for (const key of ['conditions', 'limitations']) {
      const direct = text(source[key]);
      if (direct) qualifiers.push(direct);
      qualifiers.push(...strings(source[key]));
    }
  }
  return uniqueStrings(qualifiers);
}

function genericDestination(response: PredictionResponse) {
  const action = (response.disposal_action ?? '').toLocaleLowerCase();
  const route = [response.next_step, response.local_guidance?.local_action]
    .filter(Boolean)
    .join(' ')
    .toLocaleLowerCase();
  if (/curbside|\bcart\b/.test(route)) {
    if (action.includes('compost')) return 'Curbside compost collection';
    if (action.includes('trash')) return 'Household trash collection';
    return 'Curbside recycling';
  }
  if (/scheduled|pick[ -]?up|collection service/.test(route)) return 'Scheduled collection service';
  if (action.includes('hazardous')) return 'Household hazardous waste facility';
  if (action.includes('donate') || action.includes('reuse')) return 'Donation or reuse program';
  if (action.includes('compost')) return 'Compost collection';
  if (action.includes('trash')) return 'Household trash';
  if (action.includes('drop-off')) return 'Local drop-off site';
  if (action.includes('recycle')) return 'Recycling collection';
  return null;
}

function destinationLabel(response: PredictionResponse, metadata: Record<string, unknown>) {
  return text(response.local_guidance?.destinations[0]?.name)
    ?? text(response.local_guidance?.allowed_location_names[0])
    ?? acceptedSourcePrograms(metadata)[0]
    ?? genericDestination(response);
}

function shortQualifier(value?: string | null) {
  const candidate = text(value);
  if (!candidate) return null;
  const withoutLabel = candidate.replace(/^(preparation|prepare|before disposal):\s*/i, '');
  const firstSentence = withoutLabel.match(/^(.+?[.!?])(?:\s|$)/)?.[1] ?? withoutLabel;
  return firstSentence.length <= 88 ? firstSentence : null;
}

function keyQualifier(
  response: PredictionResponse,
  metadata: Record<string, unknown>,
  destination: string | null,
  preparationSteps: string[],
) {
  const warnings = uniqueStrings(response.warnings ?? [])
    .filter((warning) => !repeatsText(warning, response.summary) && !repeatsText(warning, response.next_step));
  const warning = warnings.map(shortQualifier).find((value): value is string => value !== null);
  if (warning && !repeatsText(warning, destination)) return warning;
  const sourceQualifier = acceptedSourceQualifiers(metadata)
    .map(shortQualifier)
    .find((value): value is string => value !== null && !repeatsText(value, destination));
  if (sourceQualifier) return sourceQualifier;
  const preparation = preparationSteps.map(shortQualifier).find((value): value is string => value !== null);
  if (preparation && !repeatsText(preparation, destination)) return preparation;
  if (/\bpaid\b/i.test(response.local_guidance?.local_action ?? '')) return 'Paid collection';
  const fee = firstFee(response.local_guidance);
  return fee ? `Fee: ${fee}` : null;
}

function primaryAction(
  response: PredictionResponse,
  showNearbyButton: boolean,
  hasSteps: boolean,
): ResultSheetPrimaryAction | null {
  const action = (response.disposal_action ?? '').toLocaleLowerCase();
  const routeText = [response.next_step, response.local_guidance?.local_action]
    .filter(Boolean)
    .join(' ')
    .toLocaleLowerCase();
  let label: string | null = null;
  let route: 'location' | 'instructions' | null = null;

  if (action.includes('donate') || action.includes('reuse')) {
    label = 'Find Reuse Options';
    route = 'location';
  } else if (/scheduled|pick[ -]?up|appointment/.test(routeText)) {
    label = 'View Collection Options';
    route = 'location';
  } else if (action.includes('compost')) {
    label = 'View Compost Instructions';
    route = 'instructions';
  } else if (action.includes('trash')) {
    label = 'View Disposal Instructions';
    route = 'instructions';
  } else if (/curbside|\bcart\b/.test(routeText)) {
    label = 'View Curbside Instructions';
    route = 'instructions';
  } else if (
    action.includes('drop-off') ||
    action.includes('hazardous') ||
    (action.includes('recycle') && showNearbyButton)
  ) {
    label = 'Find Drop-Off Options';
    route = 'location';
  }

  if (!label || !route) {
    return null;
  }
  if (route === 'location' && showNearbyButton) {
    return { behavior: 'nearby', label };
  }
  return hasSteps ? { behavior: 'scroll_steps', label } : null;
}

function firstFee(guidance?: LocalGuidance) {
  const fee = guidance?.fees?.line_items[0];
  if (!fee) return null;
  const amount = guidance?.fees?.currency === 'USD' ? `$${fee.amount}` : String(fee.amount);
  return `${amount} / ${fee.unit}`;
}

function buildFacts(
  response: PredictionResponse,
  metadata: Record<string, unknown>,
  prepSteps: string[],
) {
  const facts: ResultSheetFact[] = [];
  if (prepSteps[0]) facts.push({ label: 'Preparation', value: prepSteps[0] });
  const fee = firstFee(response.local_guidance);
  if (fee) facts.push({ label: 'Fee', value: fee });
  if (metadata.requires_location_check === true || metadata.requiresLocationCheck === true) {
    facts.push({ label: 'Location required', value: 'Yes' });
  }
  const confidence =
    metadataText(metadata, 'confidence') ??
    text(record(response.guidance_confidence ?? response.guidanceConfidence)?.level);
  if (confidence) facts.push({ label: 'Confidence', value: confidence });
  return facts.slice(0, 3);
}

function buildEvidence(
  response: PredictionResponse,
  references: ResultSheetReference[],
  category: string | null,
) {
  const confidence =
    text(record(response.guidance_confidence ?? response.guidanceConfidence)?.level) ??
    metadataText(guidanceMetadata(response), 'confidence');
  const route = text(response.guidance?.summary.destination)
    ?? text(response.next_step)
    ?? text(response.local_guidance?.local_action);
  const rows: ResultSheetFact[] = [
    { label: 'Item identified', value: response.item },
    ...(category ? [{ label: 'Category or material', value: category }] : []),
    ...(route ? [{ label: 'Local route found', value: route }] : []),
    ...(confidence ? [{ label: 'Confidence', value: confidence }] : []),
  ];
  if (!route && references.length === 0) {
    return null;
  }
  const source = references[0];
  const summary = text(response.guidance?.reasoning) ?? (source?.description
    ? `${response.item} was matched with ${source.title}: ${source.description}`
    : undefined);
  return { ...(summary ? { summary } : {}), rows };
}

export function resultSheetMaxHeight(
  windowHeight: number,
  safeAreaTop: number,
  bottomOffset: number,
  topGap = 12,
) {
  return Math.max(0, windowHeight - safeAreaTop - bottomOffset - topGap);
}

export function buildResultSheetPresentation(
  response: PredictionResponse,
  options: PresentationOptions = {},
): ResultSheetPresentation {
  const metadata = guidanceMetadata(response);
  const structured = response.guidance;
  const prepSteps = uniqueStrings(structured?.preparation.steps ?? response.prep_steps ?? []);
  const preparationOnly = structured
    ? prepSteps
    : prepSteps.filter(isPreparationInstruction);
  const nextStep = text(response.next_step);
  const disposalSteps = uniqueStrings(structured?.disposal_steps ?? response.steps ?? []);
  const rawSteps = disposalSteps.length
    ? disposalSteps
    : uniqueStrings([...prepSteps, nextStep]);
  const steps = rawSteps.map(splitGuidanceStep);
  const references = buildReferences(response, metadata);
  const category =
    normalizedRecognitionValue(response, 'disposal_category') ??
    (response.category !== 'Unknown' ? text(response.category) : null) ??
    normalizedRecognitionValue(response, 'material_category');
  const location = [text(options.location?.city), text(options.location?.state)]
    .filter(Boolean)
    .join(', ');
  const localStatus = references.length
    ? 'Local guidance found'
    : metadata.requires_location_check === true || metadata.requiresLocationCheck === true
      ? 'Location check needed'
      : null;
  const status: ResultSheetFact[] = [
    ...(category ? [{ label: 'Category', value: category }] : []),
    ...(localStatus ? [{ label: 'Guidance', value: localStatus }] : []),
    ...(location ? [{ label: 'Location', value: location }] : []),
  ];
  const summary = text(response.summary);
  const bestOption = summary ?? nextStep ?? actionLabel(response.disposal_action);
  const destination = text(structured?.summary.destination) ?? destinationLabel(response, metadata);
  const qualifier = text(structured?.summary.qualifier)
    ?? keyQualifier(response, metadata, destination, preparationOnly);
  const action = actionLabel(text(structured?.summary.action_type) ?? response.disposal_action);
  const warnings = structured?.important_notes ?? uniqueStrings(response.warnings ?? []);
  const noPreparationMessage = !preparationOnly.length
    ? text(structured?.preparation.no_preparation_message)
    : null;

  return {
    action,
    bestOption,
    ...(destination ? { destinationLabel: destination } : {}),
    evidence: buildEvidence(response, references, category),
    facts: buildFacts(response, metadata, prepSteps),
    item: response.item,
    ...(qualifier ? { keyQualifier: qualifier } : {}),
    ...(noPreparationMessage ? { noPreparationMessage } : {}),
    preparationSteps: preparationOnly.map(splitGuidanceStep),
    primaryAction: primaryAction(response, options.showNearbyButton === true, steps.length > 0),
    references,
    status,
    steps,
    warnings: uniqueStrings(warnings),
  };
}
