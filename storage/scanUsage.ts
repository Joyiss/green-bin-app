import AsyncStorage from '@react-native-async-storage/async-storage';

export const DEFAULT_DAILY_SCAN_LIMIT = 5;
export const DEFAULT_MONTHLY_SCAN_LIMIT = 20;
export const INSTALLATION_ID_STORAGE_KEY = 'green-bin:installation-id';
export const SCAN_USAGE_STORAGE_KEY = 'green-bin:scan-usage';

export type ScanUsageMetadata = {
  dailyLimit: number;
  dailyScansRemaining: number;
  dailyResetAt: string;
  monthlyLimit: number;
  monthlyScansRemaining: number;
  monthlyResetAt: string;
  updatedAt: string;
};

export type ScanUsageDisplayState = {
  dailyLimit: number;
  dailyResetAt: string | null;
  dailyScansRemaining: number;
  hasStoredMetadata: boolean;
  monthlyLimit: number;
  monthlyResetAt: string | null;
  monthlyScansRemaining: number;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function toPositiveInteger(value: unknown) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null;
  const normalizedValue = Math.floor(value);
  return normalizedValue > 0 ? normalizedValue : null;
}

function toNonNegativeInteger(value: unknown) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null;
  const normalizedValue = Math.floor(value);
  return normalizedValue >= 0 ? normalizedValue : null;
}

function nextUtcDay(now = new Date()) {
  return new Date(
    Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + 1),
  ).toISOString();
}

function nextUtcMonth(now = new Date()) {
  return new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() + 1, 1)).toISOString();
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
  if (storedInstallationId?.trim()) return storedInstallationId;
  const installationId = createInstallationId();
  await AsyncStorage.setItem(INSTALLATION_ID_STORAGE_KEY, installationId);
  return installationId;
}

export function normalizeScanUsageMetadata(value: unknown): ScanUsageMetadata | null {
  if (!isRecord(value)) return null;

  const dailyLimit = toPositiveInteger(value.daily_limit ?? value.dailyLimit);
  const dailyScansRemaining = toNonNegativeInteger(
    value.daily_scans_remaining ??
      value.dailyScansRemaining ??
      value.scans_remaining ??
      value.scansRemaining,
  );
  const dailyResetAt =
    value.daily_reset_at ?? value.dailyResetAt ?? value.reset_at ?? value.resetAt;
  const monthlyLimit =
    toPositiveInteger(value.monthly_limit ?? value.monthlyLimit) ??
    DEFAULT_MONTHLY_SCAN_LIMIT;
  const monthlyScansRemaining =
    toNonNegativeInteger(
      value.monthly_scans_remaining ?? value.monthlyScansRemaining,
    ) ?? monthlyLimit;
  const monthlyResetAt =
    value.monthly_reset_at ?? value.monthlyResetAt ?? nextUtcMonth();

  if (
    dailyLimit === null ||
    dailyScansRemaining === null ||
    typeof dailyResetAt !== 'string' ||
    !dailyResetAt.trim() ||
    typeof monthlyResetAt !== 'string' ||
    !monthlyResetAt.trim()
  ) {
    return null;
  }

  return {
    dailyLimit,
    dailyScansRemaining: Math.min(dailyScansRemaining, dailyLimit),
    dailyResetAt,
    monthlyLimit,
    monthlyScansRemaining: Math.min(monthlyScansRemaining, monthlyLimit),
    monthlyResetAt,
    updatedAt: new Date().toISOString(),
  };
}

export async function saveScanUsageMetadata(value: unknown) {
  const metadata = normalizeScanUsageMetadata(value);
  if (!metadata) return null;
  await AsyncStorage.setItem(SCAN_USAGE_STORAGE_KEY, JSON.stringify(metadata));
  return metadata;
}

export async function getScanUsageMetadata() {
  try {
    const storedValue = await AsyncStorage.getItem(SCAN_USAGE_STORAGE_KEY);
    if (!storedValue) return null;
    const metadata = normalizeScanUsageMetadata(JSON.parse(storedValue) as unknown);
    if (!metadata) return null;

    const monthlyResetTimestamp = Date.parse(metadata.monthlyResetAt);
    if (Number.isNaN(monthlyResetTimestamp) || monthlyResetTimestamp <= Date.now()) {
      return null;
    }
    const dailyResetTimestamp = Date.parse(metadata.dailyResetAt);
    if (Number.isNaN(dailyResetTimestamp)) return null;
    if (dailyResetTimestamp <= Date.now()) {
      return {
        ...metadata,
        dailyScansRemaining: metadata.dailyLimit,
        dailyResetAt: nextUtcDay(),
      };
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
      dailyResetAt: null,
      dailyScansRemaining: DEFAULT_DAILY_SCAN_LIMIT,
      hasStoredMetadata: false,
      monthlyLimit: DEFAULT_MONTHLY_SCAN_LIMIT,
      monthlyResetAt: null,
      monthlyScansRemaining: DEFAULT_MONTHLY_SCAN_LIMIT,
    };
  }
  return {
    dailyLimit: metadata.dailyLimit,
    dailyResetAt: metadata.dailyResetAt,
    dailyScansRemaining: metadata.dailyScansRemaining,
    hasStoredMetadata: true,
    monthlyLimit: metadata.monthlyLimit,
    monthlyResetAt: metadata.monthlyResetAt,
    monthlyScansRemaining: metadata.monthlyScansRemaining,
  };
}
