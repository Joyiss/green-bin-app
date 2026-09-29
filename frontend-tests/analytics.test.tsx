import {
  captureAnalyticsEvent,
  captureAppOpened,
  resetAnalyticsForTests,
  setAnalyticsClientForTests,
} from '@/analytics';

describe('analytics wrapper', () => {
  afterEach(() => {
    resetAnalyticsForTests();
  });

  it('is a safe no-op when analytics configuration is unavailable', () => {
    resetAnalyticsForTests();

    expect(() => captureAnalyticsEvent('scan_started')).not.toThrow();
    expect(() => {
      captureAnalyticsEvent('scan_failed', {
        duration_ms: 25,
        error_type: 'network',
        failure_stage: 'upload',
      });
    }).not.toThrow();
  });

  it('adds only safe common metadata to typed event properties', () => {
    const capture = jest.fn();
    setAnalyticsClientForTests({ capture } as never);

    captureAnalyticsEvent('scan_completed', {
      duration_ms: 1200,
      disposal_category: 'recycle',
      local_guidance_available: true,
      source_count: 2,
      provider_verified: false,
    });

    expect(capture).toHaveBeenCalledWith('scan_completed', {
      app_version: expect.any(String),
      build_number: expect.any(String),
      platform: expect.any(String),
      environment: 'development',
      duration_ms: 1200,
      disposal_category: 'recycle',
      local_guidance_available: true,
      source_count: 2,
      provider_verified: false,
    });
  });

  it('captures app_opened once even when startup reruns', () => {
    const capture = jest.fn();
    setAnalyticsClientForTests({ capture } as never);

    captureAppOpened();
    captureAppOpened();

    expect(capture).toHaveBeenCalledTimes(1);
    expect(capture).toHaveBeenCalledWith('app_opened', expect.any(Object));
  });

  it('swallows SDK failures', () => {
    setAnalyticsClientForTests({
      capture: () => {
        throw new Error('SDK failure');
      },
    } as never);

    expect(() => captureAnalyticsEvent('guidance_shared')).not.toThrow();
  });
});
