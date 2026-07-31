import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import {
  DEFAULT_REVIEW_SUMMARY,
  getClarificationReasonCodes,
  getRecognitionReviewSummary,
  resolvePredictionFlowStatus,
} from '../app/prediction-flow.ts';
import {
  createFeedbackSubmissionCoordinator,
  FeedbackRequestError,
  FEEDBACK_QUEUE_LIMIT,
  FEEDBACK_QUEUE_TTL_MS,
  flushQueuedFeedbackEntries,
  isRetryableFeedbackStatus,
  mergeQueuedFeedback,
  pruneQueuedFeedback,
  sanitizeFeedbackUpdate,
  shouldShowGuidanceFeedback,
} from '../app/feedback-flow.ts';
import { resolveApiBaseUrl } from '../app/api-config.ts';
import {
  ApiContractError,
  normalizeFeedbackResponse,
  normalizeHealthResponse,
  normalizeNearbyLocationsResponse,
  normalizePredictionResponse,
  normalizeScanLimitResponse,
  normalizeSupportedLabelsResponse,
} from '../api/contracts.ts';
import {
  acquireRequestLock,
  ApiError,
  releaseRequestLock,
  requestJson,
} from '../api/request.ts';
import {
  appendCoarseDisposalLocation,
  appendJurisdictionId,
  detectJurisdiction,
  extractCoarseDisposalLocation,
  FORSYTH_COUNTY_JURISDICTION_ID,
  resolveJurisdictionForPrediction,
} from '../app/jurisdiction.ts';
import {
  areDevelopmentLocationToolsEnabled,
  createDevelopmentLocationOverride,
  DEFAULT_DEVELOPMENT_LOCATION_SETTINGS,
  DEVELOPMENT_LOCATION_PRESETS,
  loadDevelopmentLocationSettings,
  resetToDeviceLocation,
  resolveDevelopmentPredictionLocation,
  saveDevelopmentLocationSettings,
  shouldShowDevelopmentLocation,
} from '../app/development-location.ts';

test('jurisdiction detection requires a Georgia county-level Forsyth match', () => {
  assert.equal(
    detectJurisdiction([
      {
        country: 'United States',
        isoCountryCode: 'US',
        region: 'Georgia',
        subregion: 'Forsyth County',
      },
    ]),
    FORSYTH_COUNTY_JURISDICTION_ID,
  );
  assert.equal(
    detectJurisdiction([
      {
        country: 'United States',
        region: 'Georgia',
        subregion: 'Monroe County',
        district: null,
      },
    ]),
    null,
  );
  assert.equal(
    detectJurisdiction([
      {
        country: 'United States',
        region: 'North Carolina',
        subregion: 'Forsyth County',
      },
    ]),
    null,
  );
});

test('denied or unavailable location omits jurisdiction without failing prediction', async () => {
  assert.equal(
    await resolveJurisdictionForPrediction(async () => {
      throw new Error('permission denied');
    }),
    null,
  );
  assert.equal(
    await resolveJurisdictionForPrediction(async () => {
      throw new Error('position unavailable');
    }),
    null,
  );
});

test('prediction form includes only a resolved stable jurisdiction id', () => {
  const appended = [];
  const formData = {
    append(name, value) {
      appended.push([name, value]);
    },
  };
  appendJurisdictionId(formData, null);
  appendJurisdictionId(formData, FORSYTH_COUNTY_JURISDICTION_ID);

  assert.deepEqual(appended, [
    ['jurisdiction_id', FORSYTH_COUNTY_JURISDICTION_ID],
  ]);
});

test('prediction form includes only coarse disposal location fields', () => {
  const location = extractCoarseDisposalLocation([
    {
      city: 'Raleigh',
      subregion: 'Wake County',
      region: 'North Carolina',
      country: 'United States',
    },
  ]);
  assert.deepEqual(location, {
    city: 'Raleigh',
    county: 'Wake County',
    state: 'North Carolina',
    country: 'United States',
  });

  const appended = [];
  appendCoarseDisposalLocation(
    {
      append(name, value) {
        appended.push([name, value]);
      },
    },
    location,
  );
  assert.deepEqual(appended, [
    ['city', 'Raleigh'],
    ['county', 'Wake County'],
    ['state', 'North Carolina'],
    ['country', 'United States'],
  ]);
});

test('automatic prediction location preserves reverse-geocoded device context', () => {
  const deviceLocation = {
    city: 'Cumming',
    county: 'Forsyth County',
    state: 'Georgia',
    country: 'United States',
  };
  assert.deepEqual(
    resolveDevelopmentPredictionLocation({
      deviceLocation,
      deviceJurisdictionId: FORSYTH_COUNTY_JURISDICTION_ID,
      settings: DEFAULT_DEVELOPMENT_LOCATION_SETTINGS,
      toolsEnabled: true,
    }),
    {
      coarseDisposalLocation: deviceLocation,
      jurisdictionId: FORSYTH_COUNTY_JURISDICTION_ID,
      developmentOverrideActive: false,
    },
  );
});

test('selected test location replaces device fields sent to prediction', () => {
  const austin = DEVELOPMENT_LOCATION_PRESETS.find(
    (preset) => preset.id === 'austin',
  );
  assert.ok(austin?.location);
  const context = resolveDevelopmentPredictionLocation({
    deviceLocation: {
      city: 'Cumming',
      county: 'Forsyth County',
      state: 'Georgia',
      country: 'United States',
    },
    deviceJurisdictionId: FORSYTH_COUNTY_JURISDICTION_ID,
    settings: { location: austin.location },
    toolsEnabled: true,
  });
  const fields = [];
  const formData = {
    append(name, value) {
      fields.push([name, value]);
    },
  };
  appendJurisdictionId(formData, context.jurisdictionId);
  appendCoarseDisposalLocation(formData, context.coarseDisposalLocation);

  assert.deepEqual(fields, [
    ['city', 'Austin'],
    ['county', 'Travis County'],
    ['state', 'Texas'],
    ['country', 'United States'],
  ]);
  assert.equal(context.jurisdictionId, null);
  assert.equal(JSON.stringify(fields).includes('latitude'), false);
  assert.equal(JSON.stringify(fields).includes('longitude'), false);
});

test('non-Forsyth custom test location cannot inherit the Forsyth jurisdiction', () => {
  const atlanta = createDevelopmentLocationOverride(
    'Atlanta',
    'Fulton County',
    'Georgia',
    'United States',
  );
  assert.ok(atlanta);
  assert.equal(atlanta.jurisdictionId, null);
  const context = resolveDevelopmentPredictionLocation({
    deviceLocation: {
      city: 'Cumming',
      county: 'Forsyth County',
      state: 'Georgia',
      country: 'United States',
    },
    deviceJurisdictionId: FORSYTH_COUNTY_JURISDICTION_ID,
    settings: { location: atlanta },
    toolsEnabled: true,
  });
  assert.equal(context.jurisdictionId, null);
  assert.equal(context.coarseDisposalLocation?.county, 'Fulton County');
});

test('stored override resets to the automatic device workflow', async () => {
  const values = new Map();
  const storage = {
    async getItem(key) {
      return values.get(key) ?? null;
    },
    async setItem(key, value) {
      values.set(key, value);
    },
    async removeItem(key) {
      values.delete(key);
    },
  };
  const seattle = DEVELOPMENT_LOCATION_PRESETS.find(
    (preset) => preset.id === 'seattle',
  );
  assert.ok(seattle?.location);
  await saveDevelopmentLocationSettings(
    { location: seattle.location },
    storage,
  );
  assert.equal(
    (await loadDevelopmentLocationSettings(storage)).location.city,
    'Seattle',
  );
  const reset = await resetToDeviceLocation(storage);
  assert.equal(reset.location.enabled, false);
  assert.equal(
    (await loadDevelopmentLocationSettings(storage)).location.enabled,
    false,
  );

  const deviceLocation = {
    city: 'Raleigh',
    county: 'Wake County',
    state: 'North Carolina',
    country: 'United States',
  };
  assert.deepEqual(
    resolveDevelopmentPredictionLocation({
      deviceLocation,
      deviceJurisdictionId: null,
      settings: reset,
      toolsEnabled: true,
    }).coarseDisposalLocation,
    deviceLocation,
  );
});

test('location switcher and stored overrides are unavailable in production', () => {
  const austin = DEVELOPMENT_LOCATION_PRESETS.find(
    (preset) => preset.id === 'austin',
  );
  assert.ok(austin?.location);
  assert.equal(areDevelopmentLocationToolsEnabled(false), false);
  assert.equal(shouldShowDevelopmentLocation(false, austin.location), false);
  assert.deepEqual(
    resolveDevelopmentPredictionLocation({
      deviceLocation: {
        city: 'Cumming',
        county: 'Forsyth County',
        state: 'Georgia',
        country: 'United States',
      },
      deviceJurisdictionId: FORSYTH_COUNTY_JURISDICTION_ID,
      settings: { location: austin.location },
      toolsEnabled: false,
    }),
    {
      coarseDisposalLocation: {
        city: 'Cumming',
        county: 'Forsyth County',
        state: 'Georgia',
        country: 'United States',
      },
      jurisdictionId: FORSYTH_COUNTY_JURISDICTION_ID,
      developmentOverrideActive: false,
    },
  );
});

test('custom test locations require city, state, and country', () => {
  assert.equal(
    createDevelopmentLocationOverride('', 'Wake County', 'North Carolina', 'US'),
    null,
  );
  assert.equal(
    createDevelopmentLocationOverride('Raleigh', 'Wake County', '', 'US'),
    null,
  );
  assert.equal(
    createDevelopmentLocationOverride(
      'Raleigh',
      'Wake County',
      'North Carolina',
      '',
    ),
    null,
  );
});

test('location override files contain no legacy search integration', async () => {
  const legacyName = ['d', 'd', 'g', 's'].join('');
  const sourceFiles = [
    '../app/development-location.ts',
    '../app/jurisdiction.ts',
    '../app/(tabs)/index.tsx',
    '../app/(tabs)/profile.tsx',
  ];
  const sources = await Promise.all(
    sourceFiles.map((path) =>
      readFile(new URL(path, import.meta.url), 'utf8'),
    ),
  );
  for (const source of sources) {
    assert.equal(source.toLowerCase().includes(legacyName), false);
  }
});

test('explicit clarification overrides a confident legacy status', () => {
  const prediction = {
    status: 'confident',
    clarification: {
      required: true,
      reason_codes: ['specific_container_feature_conflict'],
      retake_recommended: true,
      retake_guidance: 'Retake the photo with the opening and closure visible.',
      message: 'Please confirm which container is shown.',
    },
  };

  assert.equal(resolvePredictionFlowStatus(prediction), 'uncertain');
  assert.deepEqual(getClarificationReasonCodes(prediction), [
    'specific_container_feature_conflict',
  ]);
  assert.equal(
    getRecognitionReviewSummary(prediction),
    'Please confirm which container is shown. Retake the photo with the opening and closure visible.',
  );
});

test('legacy uncertain responses remain compatible without additive fields', () => {
  const prediction = { status: 'uncertain' };

  assert.equal(resolvePredictionFlowStatus(prediction), 'uncertain');
  assert.equal(getRecognitionReviewSummary(prediction), DEFAULT_REVIEW_SUMMARY);
  assert.deepEqual(getClarificationReasonCodes(prediction), []);
});

test('nonblocking medium recognition can preserve conditional guidance', () => {
  const prediction = {
    status: 'confident',
    recognition_confidence: { level: 'medium', blocking: false },
  };

  assert.equal(resolvePredictionFlowStatus(prediction), 'confident');
});

test('user-confirmed selection continues into a confident result', () => {
  const prediction = {
    status: 'confident',
    recognition_source: 'user_confirmed_selection',
    recognition_confidence: { level: 'high', blocking: false },
  };

  assert.equal(resolvePredictionFlowStatus(prediction), 'confident');
});

test('strong legacy responses preserve the normal one-step experience', () => {
  assert.equal(resolvePredictionFlowStatus({ status: 'confident' }), 'confident');
});

test('malformed additive clarification fields do not block older clients', () => {
  const prediction = {
    status: 'confident',
    clarification: {
      required: 'true',
      reason_codes: 'specific_container_feature_conflict',
    },
  };

  assert.equal(resolvePredictionFlowStatus(prediction), 'confident');
  assert.deepEqual(getClarificationReasonCodes(prediction), []);
});

test('feedback queue merges updates by original request id', () => {
  const now = 100_000;
  const merged = mergeQueuedFeedback(
    [
      {
        requestId: 'mobile-original-1',
        update: { item_correct: false },
        queuedAt: now - 1,
      },
    ],
    {
      requestId: 'mobile-original-1',
      update: {
        prediction_changed: true,
        corrected_item: 'Metal Cup',
        correction_request_id: 'mobile-correction-2',
      },
      queuedAt: now,
    },
    now,
  );

  assert.equal(merged.length, 1);
  assert.deepEqual(merged[0].update, {
    item_correct: false,
    prediction_changed: true,
    corrected_item: 'Metal Cup',
    correction_request_id: 'mobile-correction-2',
  });
});

test('feedback queue expires old entries and remains capped', () => {
  const now = 10 * FEEDBACK_QUEUE_TTL_MS;
  const entries = Array.from({ length: FEEDBACK_QUEUE_LIMIT + 5 }, (_, index) => ({
    requestId: `request-${index}`,
    update: { guidance_helpful: true },
    queuedAt: now - index,
  }));
  entries.push({
    requestId: 'expired',
    update: { item_correct: false },
    queuedAt: now - FEEDBACK_QUEUE_TTL_MS,
  });

  const pruned = pruneQueuedFeedback(entries, now);

  assert.equal(pruned.length, FEEDBACK_QUEUE_LIMIT);
  assert.equal(pruned.some((entry) => entry.requestId === 'expired'), false);
});

test('guidance feedback is shown only for an actual disposal action', () => {
  assert.equal(
    shouldShowGuidanceFeedback({
      disposalAction: 'trash',
      guidanceSource: 'llm_general_fallback',
      clarificationRequired: false,
    }),
    true,
  );
  assert.equal(
    shouldShowGuidanceFeedback({
      disposalAction: null,
      guidanceSource: 'safe_fallback',
      clarificationRequired: false,
    }),
    false,
  );
  assert.equal(
    shouldShowGuidanceFeedback({
      disposalAction: null,
      guidanceSource: 'recognition_clarification_required',
      clarificationRequired: true,
    }),
    false,
  );
});

test('feedback payload sanitization removes diagnostic and private fields', () => {
  assert.deepEqual(
    sanitizeFeedbackUpdate({
      item_correct: false,
      guidance_confidence: { level: 'high' },
      reason_codes: ['do-not-send'],
      photo: 'base64',
      location: { lat: 1, lon: 2 },
      personal_information: 'do-not-send',
    }),
    { item_correct: false },
  );
});

test('feedback queue drops terminal 4xx responses and retains transient failures', async () => {
  const entries = [
    { requestId: 'missing', update: { item_correct: false }, queuedAt: 1 },
    { requestId: 'invalid', update: { guidance_helpful: true }, queuedAt: 2 },
    { requestId: 'unavailable', update: { item_correct: true }, queuedAt: 3 },
    { requestId: 'limited', update: { guidance_helpful: false }, queuedAt: 4 },
    { requestId: 'offline', update: { prediction_changed: false }, queuedAt: 5 },
  ];

  const remaining = await flushQueuedFeedbackEntries(entries, async (requestId) => {
    if (requestId === 'missing') throw new FeedbackRequestError(404);
    if (requestId === 'invalid') throw new FeedbackRequestError(422);
    if (requestId === 'unavailable') throw new FeedbackRequestError(503);
    if (requestId === 'limited') throw new FeedbackRequestError(429);
    if (requestId === 'offline') throw new TypeError('Network request failed');
  });

  assert.deepEqual(
    new Set(remaining.map((entry) => entry.requestId)),
    new Set(['unavailable', 'limited', 'offline']),
  );
  assert.equal(isRetryableFeedbackStatus(404), false);
  assert.equal(isRetryableFeedbackStatus(409), false);
  assert.equal(isRetryableFeedbackStatus(503), true);
});

test('feedback submission suppresses concurrent and recently successful duplicates', async () => {
  let sendCount = 0;
  let releaseFirst;
  const firstRequest = new Promise((resolve) => {
    releaseFirst = resolve;
  });
  const coordinatedSend = createFeedbackSubmissionCoordinator(async () => {
    sendCount += 1;
    if (sendCount === 1) {
      await firstRequest;
    }
  });
  const update = { item_correct: false };

  const first = coordinatedSend('request-1', update);
  const concurrentDuplicate = coordinatedSend('request-1', update);
  assert.equal(sendCount, 1);
  releaseFirst();
  await Promise.all([first, concurrentDuplicate]);

  await coordinatedSend('request-1', update);
  assert.equal(sendCount, 1);

  await coordinatedSend('request-1', {
    item_correct: false,
    prediction_changed: true,
  });
  assert.equal(sendCount, 2);
});

test('release API URL resolution requires an explicit HTTPS endpoint', () => {
  assert.equal(
    resolveApiBaseUrl({
      configuredUrl: 'https://green-bin-app.onrender.com/',
      developmentHost: null,
      isDevelopment: false,
    }),
    'https://green-bin-app.onrender.com',
  );
  assert.equal(
    resolveApiBaseUrl({
      configuredUrl: 'http://green-bin-app.onrender.com',
      developmentHost: null,
      isDevelopment: false,
    }),
    null,
  );
  assert.equal(
    resolveApiBaseUrl({
      configuredUrl: null,
      developmentHost: '192.168.1.5',
      isDevelopment: false,
    }),
    null,
  );
});

test('development API URL resolution permits configured HTTP and host discovery', () => {
  assert.equal(
    resolveApiBaseUrl({
      configuredUrl: 'http://dev.example.test:9000/',
      developmentHost: null,
      isDevelopment: true,
    }),
    'http://dev.example.test:9000',
  );
  assert.equal(
    resolveApiBaseUrl({
      configuredUrl: null,
      developmentHost: '192.168.1.5',
      isDevelopment: true,
    }),
    'http://192.168.1.5:8000',
  );
});

test('prediction validation rejects incompatible core fields and normalizes optional data', () => {
  assert.throws(
    () => normalizePredictionResponse({ status: 'confident', item: '' }),
    ApiContractError,
  );
  assert.throws(
    () => normalizePredictionResponse({ status: 'maybe', item: 'Bottle' }),
    ApiContractError,
  );

  const prediction = normalizePredictionResponse({
    status: 'confident',
    item: ' Bottle ',
    category: null,
    disposal_action: 42,
    material_code: ' PET ',
    prep_steps: [' Empty loose contents. ', null, 7],
    next_step: ' Use Green Bin nearby options. ',
    alternatives: [' Reuse if suitable. ', null],
    steps: [' Empty it. ', null, 7],
    warnings: 'not-an-array',
    recognition_details: {
      normalized: {
        normalized_item: 'plastic bottle',
      },
    },
  });

  assert.equal(prediction.item, 'Bottle');
  assert.equal(prediction.category, 'Unknown');
  assert.equal(prediction.disposal_action, null);
  assert.equal(prediction.material_code, 'PET');
  assert.deepEqual(prediction.prep_steps, ['Empty loose contents.']);
  assert.equal(prediction.next_step, 'Use Green Bin nearby options.');
  assert.deepEqual(prediction.alternatives, ['Reuse if suitable.']);
  assert.deepEqual(prediction.steps, ['Empty it.']);
  assert.deepEqual(prediction.warnings, []);
});

test('prediction contract preserves safe structured local guidance', () => {
  const prediction = normalizePredictionResponse({
    status: 'confident',
    item: 'Laptop',
    category: 'Electronics',
    disposal_action: 'Drop off',
    material_code: null,
    impact_level: 'Local Guidance',
    steps: [],
    jurisdiction_id: 'forsyth_county_ga',
    local_guidance: {
      dataset_id: 'forsyth_county_ga_local_disposal_guidance_v1',
      rules_version: '1',
      rule_id: 'fc_electronics',
      program_id: 'forsyth_county_convenience_centers',
      decision: 'accepted_with_conditions',
      applicability: 'applicable',
      local_action: 'paid_drop_off',
      preparation: [],
      restrictions: ['Tolbert Street Center only'],
      fees: {
        currency: 'USD',
        line_items: [
          { label: 'Other electronic', amount: 2, unit: 'each' },
        ],
      },
      sources: [
        {
          source_id: 'S1',
          title: 'Forsyth County Recycling Convenience Centers',
          publisher: 'Forsyth County',
          url: 'https://example.test/forsyth',
          accessed: '2026-07-26',
        },
        {
          title: 'Unsafe source',
          url: 'http://unsafe.example.test',
        },
      ],
      earth911_material_label: null,
      allowed_location_names: ['Tolbert Street Center'],
      destinations: [
        {
          location_id: 'tolbert_street_center',
          name: 'Tolbert Street Center',
          address: '351 Tolbert Street',
          phone: '(770) 781-2176',
          directions_url: 'https://maps.example.test/tolbert',
        },
      ],
    },
  });

  assert.equal(prediction.jurisdiction_id, 'forsyth_county_ga');
  assert.equal(prediction.local_guidance?.rule_id, 'fc_electronics');
  assert.equal(prediction.local_guidance?.fees?.line_items[0].amount, 2);
  assert.equal(prediction.local_guidance?.sources.length, 1);
  assert.equal(
    prediction.local_guidance?.destinations[0].location_id,
    'tolbert_street_center',
  );
});

test('endpoint validators enforce acknowledgements and safe location defaults', () => {
  assert.deepEqual(normalizeHealthResponse({ status: 'ok' }), { status: 'ok' });
  assert.throws(() => normalizeHealthResponse({ status: 'starting' }), ApiContractError);
  assert.deepEqual(
    normalizeFeedbackResponse({ recorded: true, request_id: 'request-1' }, 'request-1'),
    { recorded: true, request_id: 'request-1' },
  );
  assert.throws(
    () => normalizeFeedbackResponse({ recorded: true, request_id: 'other' }, 'request-1'),
    ApiContractError,
  );
  assert.deepEqual(
    normalizeSupportedLabelsResponse({ labels: [' Battery ', '', 7, 'Battery'] }),
    { labels: ['Battery'] },
  );

  const nearby = normalizeNearbyLocationsResponse({
    item: 'Battery',
    locations: [
      {
        id: 'location-1',
        name: 'Drop-off',
        directionsUrl: 'http://unsafe.example.test',
        accent: 'not-a-color',
      },
      { id: '', name: 'Malformed' },
    ],
  });
  assert.equal(nearby.locations.length, 1);
  assert.equal(nearby.locations[0].directionsUrl, null);
  assert.equal(nearby.locations[0].address, 'Address unavailable');
  assert.match(nearby.locations[0].accent, /^#[0-9A-F]{6}$/i);
});

test('scan limit validation ignores malformed metadata', () => {
  assert.deepEqual(
    normalizeScanLimitResponse({
      error: 'daily_scan_limit_reached',
      daily_limit: 40,
      scans_remaining: -1,
      reset_at: 123,
    }),
    {
      error: 'daily_scan_limit_reached',
      daily_limit: 40,
      scans_remaining: undefined,
      reset_at: undefined,
    },
  );
  assert.equal(normalizeScanLimitResponse({ error: 'other' }), null);
});

test('safe GET policy retries one transient server failure', async () => {
  let fetchCount = 0;
  const result = await requestJson('https://example.test/health', {
    fetchImpl: async () => {
      fetchCount += 1;
      return fetchCount === 1
        ? new Response(JSON.stringify({ error: 'starting' }), { status: 503 })
        : new Response(JSON.stringify({ status: 'ok' }), { status: 200 });
    },
    retryCount: 1,
    retryDelayMs: 0,
    timeoutMs: 100,
    validate: normalizeHealthResponse,
  });

  assert.deepEqual(result, { status: 'ok' });
  assert.equal(fetchCount, 2);
});

test('rate limits and POST-style requests are never automatically retried', async () => {
  let rateLimitFetchCount = 0;
  await assert.rejects(
    requestJson('https://example.test/predict', {
      fetchImpl: async () => {
        rateLimitFetchCount += 1;
        return new Response(JSON.stringify({ error: 'daily_scan_limit_reached' }), {
          status: 429,
        });
      },
      init: { method: 'POST' },
      retryCount: 1,
      retryDelayMs: 0,
      timeoutMs: 100,
      validate: normalizePredictionResponse,
    }),
    (error) =>
      error instanceof ApiError &&
      error.kind === 'rate_limit' &&
      error.retryable === true,
  );
  assert.equal(rateLimitFetchCount, 1);

  let postFetchCount = 0;
  await assert.rejects(
    requestJson('https://example.test/predict', {
      fetchImpl: async () => {
        postFetchCount += 1;
        throw new TypeError('offline');
      },
      init: { method: 'POST' },
      timeoutMs: 100,
      validate: normalizePredictionResponse,
    }),
    (error) => error instanceof ApiError && error.kind === 'network',
  );
  assert.equal(postFetchCount, 1);
});

test('timeouts abort the request and malformed success bodies are classified', async () => {
  await assert.rejects(
    requestJson('https://example.test/predict', {
      fetchImpl: (_url, init) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () => reject(new Error('aborted')), {
            once: true,
          });
        }),
      timeoutMs: 5,
      validate: normalizePredictionResponse,
    }),
    (error) => error instanceof ApiError && error.kind === 'timeout',
  );

  await assert.rejects(
    requestJson('https://example.test/health', {
      fetchImpl: async () =>
        new Response(JSON.stringify({ status: 'unexpected' }), { status: 200 }),
      timeoutMs: 100,
      validate: normalizeHealthResponse,
    }),
    (error) => error instanceof ApiError && error.kind === 'invalid_response',
  );
});

test('synchronous request locks block duplicate work until released', () => {
  const lock = { current: false };

  assert.equal(acquireRequestLock(lock), true);
  assert.equal(acquireRequestLock(lock), false);
  releaseRequestLock(lock);
  assert.equal(acquireRequestLock(lock), true);
});

test('caller cancellation aborts stale work without retrying it', async () => {
  const controller = new AbortController();
  let fetchCount = 0;
  const request = requestJson('https://example.test/nearby', {
    fetchImpl: (_url, init) => {
      fetchCount += 1;
      return new Promise((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => reject(new Error('aborted')), {
          once: true,
        });
      });
    },
    retryCount: 1,
    timeoutMs: 100,
    signal: controller.signal,
    validate: normalizeNearbyLocationsResponse,
  });

  controller.abort();
  await assert.rejects(
    request,
    (error) => error instanceof ApiError && error.message === 'Request was cancelled.',
  );
  assert.equal(fetchCount, 1);
});
