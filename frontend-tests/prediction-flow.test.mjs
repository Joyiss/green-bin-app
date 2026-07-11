import assert from 'node:assert/strict';
import test from 'node:test';

import {
  DEFAULT_REVIEW_SUMMARY,
  getClarificationReasonCodes,
  getRecognitionReviewSummary,
  resolvePredictionFlowStatus,
} from '../app/prediction-flow.ts';

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
