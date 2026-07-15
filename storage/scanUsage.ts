import AsyncStorage from '@react-native-async-storage/async-storage';

export const DEFAULT_DAILY_SCAN_LIMIT = 40;
export const INSTALLATION_ID_STORAGE_KEY = 'green-bin:installation-id';
export const SCAN_USAGE_STORAGE_KEY = 'green-bin:scan-usage';

export type ScanUsageMetadata = {
  dailyLimit: number;
  scansRemaining: number;
  resetAt: string;
  updatedAt: string;
};

export type ScanUsageDisplayState = {
  dailyLimit: number;
  hasStoredMetadata: boolean;
  resetAt: string | null;
  scansRemaining: number;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function toPositiveInteger(value: unknown) {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return null;
  }

  const normalizedValue = Math.floor(value);
  return normalizedValue > 0 ? normalizedValue : null;
}

function toNonNegativeInteger(value: unknown) {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return null;
  }

  const normalizedValue = Math.floor(value);
  return normalizedValue >= 0 ? normalizedValue : null;
}

function createInstallationId() {
  const randomUUID = globalThis.crypto?.randomUUID;
  if (typeof randomUUID === 'function') {
    return `gb-${randomUUID.call(globalThis.crypto)}`;
  }

  return `gb-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
}

export async function getInstallationId() {
  const storedInstallationId = await AsyncStorage.getItem(INSTALLATION_ID_STORAGE_KEY);
  if (storedInstallationId?.trim()) {
    return storedInstallationId;
  }

  const installationId = createInstallationId();
  await AsyncStorage.setItem(INSTALLATION_ID_STORAGE_KEY, installationId);
  return installationId;
}

export function normalizeScanUsageMetadata(value: unknown): ScanUsageMetadata | null {
  if (!isRecord(value)) {
    return null;
  }

  const dailyLimit = toPositiveInteger(value.daily_limit ?? value.dailyLimit);
  const scansRemaining = toNonNegativeInteger(
    value.scans_remaining ?? value.scansRemaining,
  );
  const resetAt = value.reset_at ?? value.resetAt;

  if (
    dailyLimit === null ||
    scansRemaining === null ||
    typeof resetAt !== 'string' ||
    !resetAt.trim()
  ) {
    return null;
  }

  return {
    dailyLimit,
    scansRemaining: Math.min(scansRemaining, dailyLimit),
    resetAt,
    updatedAt: new Date().toISOString(),
  };
}

function isScanUsageCurrent(metadata: ScanUsageMetadata) {
  const resetTimestamp = Date.parse(metadata.resetAt);
  if (Number.isNaN(resetTimestamp)) {
    return false;
  }

  return resetTimestamp > Date.now();
}

export async function saveScanUsageMetadata(value: unknown) {
  const metadata = normalizeScanUsageMetadata(value);
  if (!metadata) {
    return null;
  }

  await AsyncStorage.setItem(SCAN_USAGE_STORAGE_KEY, JSON.stringify(metadata));
  return metadata;
}

export async function getScanUsageMetadata() {
  try {
    const storedValue = await AsyncStorage.getItem(SCAN_USAGE_STORAGE_KEY);
    if (!storedValue) {
      return null;
    }

    const parsedValue = JSON.parse(storedValue) as unknown;
    const metadata = normalizeScanUsageMetadata(parsedValue);
    if (!metadata || !isScanUsageCurrent(metadata)) {
      return null;
    }

    return metadata;
  } catch {
    return null;
  }
}

export async function getScanUsageDisplayState(): Promise<ScanUsageDisplayState> {
  const metadata = await getScanUsageMetadata();
  if (!metadata) {
    return {
      dailyLimit: DEFAULT_DAILY_SCAN_LIMIT,
      hasStoredMetadata: false,
      resetAt: null,
      scansRemaining: DEFAULT_DAILY_SCAN_LIMIT,
    };
  }

  return {
    dailyLimit: metadata.dailyLimit,
    hasStoredMetadata: true,
    resetAt: metadata.resetAt,
    scansRemaining: metadata.scansRemaining,
  };
}
