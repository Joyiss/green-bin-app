import {
  ApiContractError,
  normalizeCurrentProviderResponse,
  normalizeProviderVerificationResult,
  normalizeVerifyProviderResponse,
} from '@/api/contracts';

const result = {
  status: 'verified', name: 'City Sanitation', services: ['Residential recycling'],
  match: 'confirmed', location_match: 'exact', reason: 'The provider serves this location.',
  evidence: [{ title: 'Provider page', url: 'https://provider.example/service', snippet: 'Residential curbside collection.' }],
};

describe('provider API contracts', () => {
  it('accepts a consistent structured verification response', () => {
    expect(normalizeVerifyProviderResponse({
      verification_id: 'verification-id', cached: false, result, cooldown: null,
    }).result.match).toBe('confirmed');
  });

  it('rejects status and match mismatches', () => {
    expect(() => normalizeProviderVerificationResult({ ...result, match: 'uncertain' }))
      .toThrow(ApiContractError);
  });

  it('requires Gemini location_match without inferring it from reason text', () => {
    const { location_match: _locationMatch, ...missing } = result;
    expect(() => normalizeProviderVerificationResult(missing)).toThrow(ApiContractError);
    expect(() => normalizeProviderVerificationResult({ ...result, location_match: 'nearby' }))
      .toThrow(ApiContractError);
  });

  it.each(['javascript:alert(1)', 'data:text/plain,bad', 'file:///tmp/a', '/relative'])
  ('rejects unsafe evidence URL %s', (url) => {
    expect(() => normalizeProviderVerificationResult({
      ...result, evidence: [{ ...result.evidence[0], url }],
    })).toThrow(ApiContractError);
  });

  it('supports location-specific no-current-provider responses', () => {
    expect(normalizeCurrentProviderResponse({ provider: null, restriction: null }))
      .toEqual({ provider: null, restriction: null });
  });
});
