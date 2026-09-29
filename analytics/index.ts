import * as Application from 'expo-application';
import Constants from 'expo-constants';
import { Platform } from 'react-native';
import { PostHog } from 'posthog-react-native';

export type AnalyticsEnvironment = 'development' | 'preview' | 'production';
export type ScanErrorType =
  | 'network'
  | 'timeout'
  | 'rate_limit'
  | 'server'
  | 'invalid_response'
  | 'permission'
  | 'unknown';
export type ScanFailureStage = 'camera' | 'upload' | 'prediction' | 'guidance' | 'unknown';
export type ProviderVerificationOutcome = 'verified' | 'uncertain' | 'not_found' | 'error';

type AnalyticsEventProperties = {
  app_opened: Record<string, never>;
  scan_started: Record<string, never>;
  scan_completed: {
    duration_ms: number;
    disposal_category: string;
    local_guidance_available: boolean;
    source_count: number;
    provider_verified: boolean;
  };
  scan_failed: {
    duration_ms: number;
    error_type: ScanErrorType;
    failure_stage: ScanFailureStage;
  };
  scan_feedback_submitted: { rating: 'positive' | 'negative' };
  guidance_shared: Record<string, never>;
  guidance_copied: Record<string, never>;
  dropoff_viewed: Record<string, never>;
  dropoff_location_opened: Record<string, never>;
  provider_verification_completed: { outcome: ProviderVerificationOutcome };
  feedback_board_opened: Record<string, never>;
};

export type AnalyticsEventName = keyof AnalyticsEventProperties;

type AnalyticsClient = Pick<PostHog, 'capture'>;

const posthogKey = process.env.EXPO_PUBLIC_POSTHOG_KEY?.trim();
const posthogHost = process.env.EXPO_PUBLIC_POSTHOG_HOST?.trim();
const isAutomatedTest = process.env.NODE_ENV === 'test';
let didWarnAboutMissingConfiguration = false;
let didTrackAppOpen = false;

function analyticsEnvironment(): AnalyticsEnvironment {
  if (__DEV__) {
    return 'development';
  }

  return process.env.EXPO_PUBLIC_APP_ENV === 'preview' ? 'preview' : 'production';
}

const commonProperties = {
  app_version: Application.nativeApplicationVersion ?? Constants.expoConfig?.version ?? 'unknown',
  build_number: Application.nativeBuildVersion ?? 'unknown',
  platform: Platform.OS,
  environment: analyticsEnvironment(),
} as const;

const SAFE_DISPOSAL_CATEGORIES = new Set([
  'appliances', 'battery', 'cardboard', 'electronics', 'glass', 'hazardous',
  'metal', 'organic', 'paper', 'plastic', 'textiles', 'recycle', 'trash',
  'compost', 'drop-off', 'donate', 'unknown',
]);

function createClient(): AnalyticsClient | null {
  if (isAutomatedTest) {
    return null;
  }

  if (!posthogKey || !posthogHost) {
    if (__DEV__ && !didWarnAboutMissingConfiguration) {
      didWarnAboutMissingConfiguration = true;
      console.warn(
        '[analytics] PostHog is disabled because EXPO_PUBLIC_POSTHOG_KEY or EXPO_PUBLIC_POSTHOG_HOST is missing.',
      );
    }
    return null;
  }

  try {
    return new PostHog(posthogKey, {
      host: posthogHost,
      captureAppLifecycleEvents: false,
      capturePushNotificationOpened: false,
      capturePushNotificationSubscriptions: false,
      disableGeoip: true,
      disableRemoteFeatureFlags: true,
      disableSurveys: true,
      enableSessionReplay: false,
      personProfiles: 'never',
      preloadFeatureFlags: false,
      sendFeatureFlagEvent: false,
      setDefaultPersonProperties: false,
      customAppProperties: (properties) => ({
        $app_build: properties.$app_build,
        $app_version: properties.$app_version,
        $os_name: properties.$os_name,
      }),
    });
  } catch {
    return null;
  }
}

let analyticsClient = createClient();

export function captureAnalyticsEvent<EventName extends AnalyticsEventName>(
  event: EventName,
  ...args: AnalyticsEventProperties[EventName] extends Record<string, never>
    ? [] | [AnalyticsEventProperties[EventName]]
    : [AnalyticsEventProperties[EventName]]
) {
  const properties = args[0] ?? ({} as AnalyticsEventProperties[EventName]);

  try {
    const safeProperties = event === 'scan_completed'
      ? {
          ...properties,
          disposal_category: SAFE_DISPOSAL_CATEGORIES.has(
            String((properties as AnalyticsEventProperties['scan_completed']).disposal_category).toLowerCase(),
          )
            ? String((properties as AnalyticsEventProperties['scan_completed']).disposal_category).toLowerCase()
            : 'unknown',
        }
      : properties;
    analyticsClient?.capture(event, { ...commonProperties, ...safeProperties });
  } catch {
    // Analytics is best-effort and must never affect the application flow.
  }
}

export function captureAppOpened() {
  if (didTrackAppOpen) {
    return;
  }

  didTrackAppOpen = true;
  captureAnalyticsEvent('app_opened');
}

/** Test-only injection keeps the production SDK disabled under NODE_ENV=test. */
export function setAnalyticsClientForTests(client: AnalyticsClient | null) {
  if (process.env.NODE_ENV === 'test') {
    analyticsClient = client;
  }
}

/** Test-only reset for the cold-launch de-duplication guard. */
export function resetAnalyticsForTests() {
  if (process.env.NODE_ENV === 'test') {
    analyticsClient = null;
    didTrackAppOpen = false;
  }
}
