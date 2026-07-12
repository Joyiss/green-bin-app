import assert from 'node:assert/strict';
import test from 'node:test';

import {
  DEFAULT_REVIEW_SUMMARY,
  getClarificationReasonCodes,
  getRecognitionReviewSummary,
  resolvePredictionFlowStatus,
} from '../app/prediction-flow.ts';
import {
  FEEDBACK_QUEUE_LIMIT,
  FEEDBACK_QUEUE_TTL_MS,
  mergeQueuedFeedback,
  pruneQueuedFeedback,
  sanitizeFeedbackUpdate,
  shouldShowGuidanceFeedback,
} from '../app/feedback-flow.ts';

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
