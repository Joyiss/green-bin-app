import AsyncStorage from '@react-native-async-storage/async-storage';

import type { CoarseDisposalLocation } from './jurisdiction';

const FORSYTH_COUNTY_OVERRIDE_ID = 'forsyth_county_ga';

export const DEVELOPMENT_LOCATION_STORAGE_KEY =
  'green-bin:development-disposal-location';

export type DevelopmentLocationOverride = {
  enabled: boolean;
  city: string;
  county: string | null;
  state: string;
  country: string;
  jurisdictionId: string | null;
};

export type DevelopmentLocationSettings = {
  location: DevelopmentLocationOverride;
};

export type DevelopmentLocationPreset = {
  id: 'real' | 'austin' | 'atlanta' | 'seattle' | 'custom';
  label: string;
  location: DevelopmentLocationOverride | null;
};

export type DevelopmentPredictionLocation = {
  coarseDisposalLocation: CoarseDisposalLocation | null;
  jurisdictionId: string | null;
  developmentOverrideActive: boolean;
};

type LocalStorageAdapter = {
  getItem(key: string): Promise<string | null>;
  removeItem(key: string): Promise<void>;
  setItem(key: string, value: string): Promise<void>;
};

export const DEVICE_LOCATION_OVERRIDE: DevelopmentLocationOverride = {
  enabled: false,
  city: '',
  county: null,
  state: '',
  country: '',
  jurisdictionId: null,
};

export const DEFAULT_DEVELOPMENT_LOCATION_SETTINGS: DevelopmentLocationSettings = {
  location: DEVICE_LOCATION_OVERRIDE,
};

export const DEVELOPMENT_LOCATION_PRESETS: DevelopmentLocationPreset[] = [
  {
    id: 'real',
    label: 'Use Device Location',
    location: DEVICE_LOCATION_OVERRIDE,
  },
  {
    id: 'austin',
    label: 'Austin, Travis County, Texas',
    location: {
      enabled: true,
      city: 'Austin',
      county: 'Travis County',
      state: 'Texas',
      country: 'United States',
      jurisdictionId: null,
    },
  },
  {
    id: 'atlanta',
    label: 'Atlanta, Fulton County, Georgia',
    location: {
      enabled: true,
      city: 'Atlanta',
      county: 'Fulton County',
      state: 'Georgia',
      country: 'United States',
      jurisdictionId: null,
    },
  },
  {
    id: 'seattle',
    label: 'Seattle, King County, Washington',
    location: {
      enabled: true,
      city: 'Seattle',
      county: 'King County',
      state: 'Washington',
      country: 'United States',
      jurisdictionId: null,
    },
  },
  {
    id: 'custom',
    label: 'Custom Location',
    location: null,
  },
];

function cleanLocationPart(value: unknown) {
  if (typeof value !== 'string') {
    return '';
  }
  return value.trim().replace(/\s+/g, ' ').slice(0, 120);
}

function normalizeLocationPart(value: string | null) {
  return (value ?? '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function resolveOverrideJurisdictionId({
  county,
  state,
  country,
}: {
  county: string | null;
  state: string;
  country: string;
}) {
  const normalizedCounty = normalizeLocationPart(county);
  const normalizedState = normalizeLocationPart(state);
  const normalizedCountry = normalizeLocationPart(country);
  const isForsythCounty =
    normalizedCounty === 'forsyth' || normalizedCounty === 'forsyth county';
  const isGeorgia = normalizedState === 'ga' || normalizedState === 'georgia';
  const isUnitedStates =
    normalizedCountry === 'us' ||
    normalizedCountry === 'usa' ||
    normalizedCountry === 'united states' ||
    normalizedCountry === 'united states of america';

  return isForsythCounty && isGeorgia && isUnitedStates
    ? FORSYTH_COUNTY_OVERRIDE_ID
    : null;
}

export function areDevelopmentLocationToolsEnabled(
  isDevelopment: boolean,
  secureTestingEnabled = false,
) {
  return isDevelopment || secureTestingEnabled;
}

// Manual/test locations remain reusable developer tooling, but are disabled for
// the closed-testing build so device location is the only tester-facing flow.
export const DEVELOPMENT_LOCATION_TOOLS_ENABLED = false;

export function createDevelopmentLocationOverride(
  city: unknown,
  county: unknown,
  state: unknown,
  country: unknown,
): DevelopmentLocationOverride | null {
  const normalizedCity = cleanLocationPart(city);
  const normalizedCounty = cleanLocationPart(county);
  const normalizedState = cleanLocationPart(state);
  const normalizedCountry = cleanLocationPart(country);
  if (!normalizedCity || !normalizedState || !normalizedCountry) {
    return null;
  }
  return {
    enabled: true,
    city: normalizedCity,
    county: normalizedCounty || null,
    state: normalizedState,
    country: normalizedCountry,
    jurisdictionId: resolveOverrideJurisdictionId({
      county: normalizedCounty || null,
      state: normalizedState,
      country: normalizedCountry,
    }),
  };
}

export function normalizeDevelopmentLocationSettings(
  value: unknown,
): DevelopmentLocationSettings {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return DEFAULT_DEVELOPMENT_LOCATION_SETTINGS;
  }
  const record = value as Record<string, unknown>;
  const rawLocation =
    record.location && typeof record.location === 'object' && !Array.isArray(record.location)
      ? (record.location as Record<string, unknown>)
      : null;
  const location =
    rawLocation?.enabled === true
      ? createDevelopmentLocationOverride(
          rawLocation.city,
          rawLocation.county,
          rawLocation.state,
          rawLocation.country,
        )
      : DEVICE_LOCATION_OVERRIDE;
  return {
    location: location ?? DEVICE_LOCATION_OVERRIDE,
  };
}

export function getDevelopmentLocationPresetId(
  location: DevelopmentLocationOverride,
): DevelopmentLocationPreset['id'] {
  if (!location.enabled) {
    return 'real';
  }
  const matchingPreset = DEVELOPMENT_LOCATION_PRESETS.find((preset) => {
    if (!preset.location?.enabled) {
      return false;
    }
    return (
      preset.location.city === location.city &&
      preset.location.county === location.county &&
      preset.location.state === location.state &&
      preset.location.country === location.country
    );
  });
  return matchingPreset?.id ?? 'custom';
}

export function resolveDevelopmentPredictionLocation({
  deviceLocation,
  deviceJurisdictionId,
  settings,
  preservedContext,
  toolsEnabled = DEVELOPMENT_LOCATION_TOOLS_ENABLED,
}: {
  deviceLocation: CoarseDisposalLocation | null;
  deviceJurisdictionId: string | null;
  settings: DevelopmentLocationSettings;
  preservedContext?: DevelopmentPredictionLocation | null;
  toolsEnabled?: boolean;
}): DevelopmentPredictionLocation {
  if (preservedContext) {
    return preservedContext;
  }
  const override =
    toolsEnabled && settings.location.enabled
      ? settings.location
      : DEVICE_LOCATION_OVERRIDE;
  if (!override.enabled) {
    return {
      coarseDisposalLocation: deviceLocation,
      jurisdictionId: deviceJurisdictionId,
      developmentOverrideActive: false,
    };
  }
  return {
    coarseDisposalLocation: {
      city: override.city,
      ...(override.county ? { county: override.county } : {}),
      state: override.state,
      country: override.country,
    },
    jurisdictionId: override.jurisdictionId,
    developmentOverrideActive: true,
  };
}

export async function loadDevelopmentLocationSettings(
  storage: LocalStorageAdapter = AsyncStorage,
) {
  if (!DEVELOPMENT_LOCATION_TOOLS_ENABLED && storage === AsyncStorage) {
    return DEFAULT_DEVELOPMENT_LOCATION_SETTINGS;
  }
  try {
    const storedValue = await storage.getItem(DEVELOPMENT_LOCATION_STORAGE_KEY);
    return storedValue
      ? normalizeDevelopmentLocationSettings(JSON.parse(storedValue) as unknown)
      : DEFAULT_DEVELOPMENT_LOCATION_SETTINGS;
  } catch {
    return DEFAULT_DEVELOPMENT_LOCATION_SETTINGS;
  }
}

export async function saveDevelopmentLocationSettings(
  value: DevelopmentLocationSettings,
  storage: LocalStorageAdapter = AsyncStorage,
) {
  const normalized = normalizeDevelopmentLocationSettings(value);
  if (!DEVELOPMENT_LOCATION_TOOLS_ENABLED && storage === AsyncStorage) {
    return normalized;
  }
  await storage.setItem(
    DEVELOPMENT_LOCATION_STORAGE_KEY,
    JSON.stringify(normalized),
  );
  return normalized;
}

export async function resetToDeviceLocation(
  storage: LocalStorageAdapter = AsyncStorage,
) {
  return saveDevelopmentLocationSettings(
    DEFAULT_DEVELOPMENT_LOCATION_SETTINGS,
    storage,
  );
}

export function shouldShowDevelopmentLocation(
  toolsEnabled: boolean,
  location: DevelopmentLocationOverride,
) {
  return toolsEnabled && location.enabled;
}
