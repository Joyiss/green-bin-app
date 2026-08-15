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
import { scannerChromeVisibility } from '../app/confident-result-state.ts';
import {
  RESULT_SHEET_COLLAPSED,
  RESULT_SHEET_EXPANDED,
  RESULT_SHEET_HIDDEN,
  resolveResultSheetSnapTarget,
} from '../app/result-sheet-snap.ts';
import {
  buildResultSheetPresentation,
  resultSheetMaxHeight,
  sourceUrlKey,
  splitGuidanceStep,
} from '../app/result-sheet-model.ts';

function resultFixture(overrides = {}) {
  return {
    item: 'Portable speaker',
    category: 'Electronics',
    status: 'confident',
    disposal_action: 'drop-off',
    material_code: null,
    impact_level: 'Source-Grounded Guidance',
    summary: 'Use River County Device Recovery for drop-off.',
    prep_steps: ['Preparation: Keep the device intact.'],
    next_step: 'Schedule a drop-off with River County Device Recovery.',
    alternatives: [],
    steps: [
      'Preparation: Keep the device intact.',
      'Schedule a drop-off with River County Device Recovery.',
    ],
    warnings: [],
    guidance_metadata: {
      confidence: 'high',
      accepted_sources: [
        {
          title: 'River County Device Recovery',
          organization: 'River County Device Recovery',
          url: 'http://provider.example/takeback?campaign=one',
          source_role: 'direct_service_provider',
          program_name: 'River County Device Recovery Program',
          claim_scope: ['own_accepted_items', 'own_services'],
          support_description: 'Accepts small devices by appointment.',
          jurisdiction: { location_scope: 'River City, Ohio' },
        },
        {
          title: 'Duplicate source',
          url: 'https://www.provider.example/takeback/#details',
          source_role: 'direct_service_provider',
        },
      ],
    },
    ...overrides,
  };
}

test('result presentation preserves named routes and conservative step text', () => {
  const presentation = buildResultSheetPresentation(resultFixture(), {
    location: { city: 'River City', state: 'Ohio' },
    showNearbyButton: true,
  });

  assert.match(presentation.bestOption, /River County Device Recovery/);
  assert.equal(presentation.destinationLabel, 'River County Device Recovery Program');
  assert.equal(presentation.keyQualifier, 'Keep the device intact.');
  assert.deepEqual(presentation.preparationSteps, [{
    title: 'Preparation',
    body: 'Keep the device intact.',
  }]);
  assert.deepEqual(presentation.steps[0], {
    title: 'Preparation',
    body: 'Keep the device intact.',
  });
  assert.deepEqual(
    splitGuidanceStep('Keep the original guidance exactly as written'),
    { title: 'Keep the original guidance exactly as written' },
  );
  assert.equal(presentation.primaryAction?.label, 'Find Drop-Off Options');
  assert.equal(presentation.primaryAction?.behavior, 'nearby');
});

test('result metadata prefers the disposal stream over casing material', () => {
  const presentation = buildResultSheetPresentation(
    resultFixture({
      category: 'Special waste',
      recognition_details: {
        normalized: {
          disposal_category: 'Electronics',
          material_category: 'Plastic',
        },
      },
    }),
    { location: { city: 'River City', state: 'Ohio' } },
  );
  assert.deepEqual(presentation.status[0], { label: 'Category', value: 'Electronics' });
});

test('references deduplicate comparison URLs while preserving the original link', () => {
  assert.equal(
    sourceUrlKey('http://provider.example/takeback?campaign=one'),
    sourceUrlKey('https://www.provider.example/takeback/#details'),
  );
  const presentation = buildResultSheetPresentation(resultFixture());
  assert.equal(presentation.references.length, 1);
  assert.equal(
    presentation.references[0].url,
    'http://provider.example/takeback?campaign=one',
  );
  assert.equal(presentation.references[0].role, 'Local service provider');
  assert.equal(
    presentation.references[0].description,
    'Accepts small devices by appointment.',
  );
});

test('route-specific primary labels and instruction behavior are deterministic', () => {
  const cases = [
    ['drop-off', 'Use the staffed site.', true, 'Find Drop-Off Options', 'nearby'],
    ['recycle', 'Schedule pickup for collection.', true, 'View Collection Options', 'nearby'],
    ['donate/reuse', 'Donate through the reuse program.', true, 'Find Reuse Options', 'nearby'],
    ['recycle', 'Place it in the curbside cart.', false, 'View Curbside Instructions', 'scroll_steps'],
    ['compost', 'Place it in the organics cart.', false, 'View Compost Instructions', 'scroll_steps'],
    ['trash', 'Place it in household trash.', false, 'View Disposal Instructions', 'scroll_steps'],
  ];
  for (const [action, nextStep, nearby, label, behavior] of cases) {
    const presentation = buildResultSheetPresentation(
      resultFixture({ disposal_action: action, next_step: nextStep }),
      { showNearbyButton: nearby },
    );
    assert.equal(presentation.primaryAction?.label, label);
    assert.equal(presentation.primaryAction?.behavior, behavior);
  }
});

test('unsupported result-sheet sections and actions are omitted', () => {
  const presentation = buildResultSheetPresentation(
    resultFixture({
      disposal_action: 'check local guidance',
      guidance_metadata: {},
      next_step: null,
      prep_steps: [],
      steps: [],
      warnings: [],
    }),
  );
  assert.equal(presentation.primaryAction, null);
  assert.equal(presentation.references.length, 0);
  assert.equal(presentation.warnings.length, 0);
  assert.equal(presentation.evidence, null);
});

test('result sheet height uses nearly all safe available space', () => {
  assert.equal(resultSheetMaxHeight(844, 44, 96), 692);
});

test('confident result keeps the Scan screen backdrop while hiding other scanner chrome', () => {
  assert.deepEqual(scannerChromeVisibility('confident'), {
    showBottomTabs: false,
    showCamera: true,
    showDevelopmentLocation: false,
  });
  assert.deepEqual(scannerChromeVisibility('idle'), {
    showBottomTabs: true,
    showCamera: true,
    showDevelopmentLocation: true,
  });
  assert.deepEqual(scannerChromeVisibility('uncertain'), {
    showBottomTabs: true,
    showCamera: true,
    showDevelopmentLocation: true,
  });
});

test('result sheet swipes snap through expanded, collapsed, and hidden in order', () => {
  const offsets = { collapsedOffset: 600, hiddenOffset: 800 };

  assert.equal(resolveResultSheetSnapTarget({
    ...offsets,
    state: RESULT_SHEET_EXPANDED,
    translationY: 100,
    velocityY: 0,
  }), RESULT_SHEET_EXPANDED);
  assert.equal(resolveResultSheetSnapTarget({
    ...offsets,
    state: RESULT_SHEET_EXPANDED,
    translationY: 700,
    velocityY: 1600,
  }), RESULT_SHEET_COLLAPSED);
  assert.equal(resolveResultSheetSnapTarget({
    ...offsets,
    state: RESULT_SHEET_COLLAPSED,
    translationY: 30,
    velocityY: 0,
  }), RESULT_SHEET_COLLAPSED);
  assert.equal(resolveResultSheetSnapTarget({
    ...offsets,
    state: RESULT_SHEET_COLLAPSED,
    translationY: -120,
    velocityY: -1200,
  }), RESULT_SHEET_EXPANDED);
  assert.equal(resolveResultSheetSnapTarget({
    ...offsets,
    state: RESULT_SHEET_COLLAPSED,
    translationY: 120,
    velocityY: 600,
  }), RESULT_SHEET_HIDDEN);
});

test('full-screen result uses loaded Fredoka and Inter faces and hides the custom tab bar', async () => {
  const [typographySource, resultSource, legacySheetSource, scannerSource, tabLayoutSource] = await Promise.all([
    readFile(new URL('../constants/typography.ts', import.meta.url), 'utf8'),
    readFile(new URL('../components/confident-result-screen.tsx', import.meta.url), 'utf8'),
    readFile(new URL('../components/result-sheet.tsx', import.meta.url), 'utf8'),
    readFile(new URL('../app/(tabs)/index.tsx', import.meta.url), 'utf8'),
    readFile(new URL('../app/(tabs)/_layout.tsx', import.meta.url), 'utf8'),
  ]);
  for (const [alias, source] of [
    ['Fredoka-Medium', 'Fredoka_500Medium'],
    ['Fredoka-SemiBold', 'Fredoka_600SemiBold'],
    ['Inter-Regular', 'Inter_400Regular'],
    ['Inter-Medium', 'Inter_500Medium'],
    ['Inter-SemiBold', 'Inter_600SemiBold'],
  ]) {
    assert.match(typographySource, new RegExp(`FONT_SOURCES\\['${alias}'\\] = ${source}`));
  }
  assert.match(resultSource, /FREDOKA_TEXT_STYLES/);
  assert.match(resultSource, /INTER_TEXT_STYLES/);
  assert.doesNotMatch(resultSource, /MANROPE_TEXT_STYLES/);
  assert.doesNotMatch(resultSource, /SourceSans|serif/);
  assert.doesNotMatch(resultSource, /\bselectable\b/);
  assert.doesNotMatch(legacySheetSource, /\bselectable\b/);
  assert.match(resultSource, /warning-outline/);
  assert.match(scannerSource, /scannerChrome\.showCamera/);
  assert.match(scannerSource, /showCameraLoadingImmediatelyRef/);
  assert.match(scannerSource, /scannerChrome\.showDevelopmentLocation/);
  assert.match(tabLayoutSource, /hidden \? null : <BottomNavBar/);
});

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
          title: 'HTTP source',
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
  assert.equal(prediction.local_guidance?.sources.length, 2);
  assert.equal(
    prediction.local_guidance?.sources[1].url,
    'http://unsafe.example.test/',
  );
  assert.equal(
    prediction.local_guidance?.destinations[0].location_id,
    'tolbert_street_center',
  );
});

test('structured guidance normalizes empty preparation and removes cross-section duplicates', () => {
  const prediction = normalizePredictionResponse({
    status: 'confident',
    item: 'Battery',
    category: 'Special waste',
    disposal_action: 'drop-off',
    material_code: null,
    impact_level: 'Source-Grounded Guidance',
    prep_steps: [],
    next_step: 'County battery site',
    alternatives: [],
    steps: [],
    guidance: {
      summary: {
        action_type: 'drop-off',
        destination: 'County battery site',
        qualifier: 'Residents only.',
      },
      preparation: {
        required: true,
        steps: ['County battery site', 'County battery site'],
        no_preparation_message: null,
      },
      important_notes: ['Residents only.', 'Appointments are required.'],
      reasoning: 'The county handles batteries through a dedicated collection route.',
      references: [{
        source_title: 'County battery program',
        url: 'https://county.example/batteries',
        supports_claim: 'Batteries are accepted at the county site.',
      }],
    },
  });

  assert.deepEqual(prediction.guidance?.preparation, {
    required: false,
    steps: [],
    no_preparation_message: null,
  });
  assert.deepEqual(prediction.guidance?.important_notes, ['Appointments are required.']);
  const presentation = buildResultSheetPresentation(prediction);
  assert.equal(presentation.action, 'Drop off');
  assert.equal(presentation.destinationLabel, 'County battery site');
  assert.equal(presentation.noPreparationMessage, undefined);
  assert.equal(presentation.evidence?.summary, prediction.guidance?.reasoning);
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
      daily_limit: 5,
      daily_scans_remaining: -1,
      daily_reset_at: 123,
      monthly_limit: 20,
      monthly_scans_remaining: 7,
      monthly_reset_at: '2026-08-01T00:00:00Z',
      scans_remaining: -1,
      reset_at: 123,
    }),
    {
      error: 'daily_scan_limit_reached',
      daily_limit: 5,
      daily_scans_remaining: undefined,
      daily_reset_at: undefined,
      monthly_limit: 20,
      monthly_scans_remaining: 7,
      monthly_reset_at: '2026-08-01T00:00:00Z',
      scans_remaining: undefined,
      reset_at: undefined,
    },
  );
  assert.deepEqual(
    normalizeScanLimitResponse({
      error: 'monthly_scan_limit_reached',
      daily_limit: 5,
      daily_scans_remaining: 3,
      daily_reset_at: '2026-07-10T00:00:00Z',
      monthly_limit: 20,
      monthly_scans_remaining: 0,
      monthly_reset_at: '2026-08-01T00:00:00Z',
    }),
    {
      error: 'monthly_scan_limit_reached',
      daily_limit: 5,
      daily_scans_remaining: 3,
      daily_reset_at: '2026-07-10T00:00:00Z',
      monthly_limit: 20,
      monthly_scans_remaining: 0,
      monthly_reset_at: '2026-08-01T00:00:00Z',
      scans_remaining: undefined,
      reset_at: undefined,
    },
  );
  assert.equal(normalizeScanLimitResponse({ error: 'other' }), null);
});

test('mobile predict requests allow at least 60 seconds', async () => {
  const clientSource = await readFile(new URL('../api/client.ts', import.meta.url), 'utf8');
  const match = clientSource.match(/PREDICT_TIMEOUT_MS\s*=\s*([0-9_]+)/);
  assert.ok(match);
  const timeoutMs = Number(match[1].replaceAll('_', ''));
  assert.ok(timeoutMs >= 60_000);
  assert.match(clientSource, /timeoutMs:\s*PREDICT_TIMEOUT_MS/);
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
