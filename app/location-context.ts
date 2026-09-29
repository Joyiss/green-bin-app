import * as Location from 'expo-location';

import {
  detectJurisdiction,
  extractCoarseDisposalLocation,
  type CoarseDisposalLocation,
} from '@/app/jurisdiction';

const LOCATION_CACHE_MS = 5 * 60 * 1000;
const POSITION_TIMEOUT_MS = 15_000;
const LAST_KNOWN_TIMEOUT_MS = 5_000;
const GEOCODE_TIMEOUT_MS = 10_000;

async function settleWithin<T>(promise: Promise<T>, timeoutMs: number): Promise<T | null> {
  let timeoutId: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      promise.catch(() => null),
      new Promise<null>((resolve) => {
        timeoutId = setTimeout(() => resolve(null), timeoutMs);
      }),
    ]);
  } finally {
    if (timeoutId) clearTimeout(timeoutId);
  }
}

export type AppCoordinates = {
  latitude: number;
  longitude: number;
};

export type AppLocationContext = {
  coordinates: AppCoordinates;
  jurisdictionId: string | null;
  coarseDisposalLocation: CoarseDisposalLocation | null;
};

export class LocationPermissionError extends Error {
  readonly openSettings: boolean;

  constructor(openSettings: boolean) {
    super('Location permission denied');
    this.name = 'LocationPermissionError';
    this.openSettings = openSettings;
  }
}

export class LocationUnavailableError extends Error {
  constructor() {
    super('Location unavailable');
    this.name = 'LocationUnavailableError';
  }
}

let cachedContext: { value: AppLocationContext; expiresAt: number } | null = null;

async function getUsablePosition() {
  const currentPosition = await settleWithin(
    Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced }),
    POSITION_TIMEOUT_MS,
  );
  return currentPosition ?? settleWithin(
    Location.getLastKnownPositionAsync(),
    LAST_KNOWN_TIMEOUT_MS,
  );
}

export async function getAppLocationContext({
  requestPermission = true,
}: {
  requestPermission?: boolean;
} = {}): Promise<AppLocationContext> {
  if (cachedContext && cachedContext.expiresAt > Date.now()) {
    return cachedContext.value;
  }

  let permission = await Location.getForegroundPermissionsAsync();
  if (permission.status !== 'granted' && permission.canAskAgain && requestPermission) {
    permission = await Location.requestForegroundPermissionsAsync();
  }
  if (permission.status !== 'granted') {
    throw new LocationPermissionError(!permission.canAskAgain);
  }

  const position = await getUsablePosition();
  if (
    !position ||
    !Number.isFinite(position.coords.latitude) ||
    !Number.isFinite(position.coords.longitude)
  ) {
    throw new LocationUnavailableError();
  }

  const coordinates = {
    latitude: position.coords.latitude,
    longitude: position.coords.longitude,
  };
  let jurisdictionId: string | null = null;
  let coarseDisposalLocation: CoarseDisposalLocation | null = null;
  try {
    const addresses = await settleWithin(Location.reverseGeocodeAsync(coordinates), GEOCODE_TIMEOUT_MS);
    if (addresses) {
      jurisdictionId = detectJurisdiction(addresses);
      coarseDisposalLocation = extractCoarseDisposalLocation(addresses);
    }
  } catch {
    jurisdictionId = null;
    coarseDisposalLocation = null;
  }

  const value = { coordinates, jurisdictionId, coarseDisposalLocation };
  cachedContext = {
    value,
    expiresAt: Date.now() + LOCATION_CACHE_MS,
  };
  return value;
}

export function clearLocationContextCacheForTests() {
  cachedContext = null;
}
