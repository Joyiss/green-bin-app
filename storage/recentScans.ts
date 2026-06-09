import AsyncStorage from '@react-native-async-storage/async-storage';

export const RECENT_SCANS_STORAGE_KEY = 'green-bin:recent-scans';
export const MAX_RECENT_SCANS = 50;

export type RecentScan = {
  id: string;
  predictedItem: string | null;
  finalItem: string;
  wasCorrected: boolean;
  imageUri: string | null;
  category: string | null;
  disposalLabel: string;
  disposalAction: string | null;
  scannedAt: string;
  materialTag?: string | null;
  summary?: string | null;
  steps?: string[];
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string');
}

function normalizeOptionalString(value: unknown) {
  return typeof value === 'string' ? value : null;
}

function normalizeRecentScan(value: unknown): RecentScan | null {
  if (!isRecord(value)) {
    return null;
  }

  const { id, finalItem, disposalLabel, scannedAt, wasCorrected } = value;

  if (
    typeof id !== 'string' ||
    typeof finalItem !== 'string' ||
    typeof disposalLabel !== 'string' ||
    typeof scannedAt !== 'string' ||
    typeof wasCorrected !== 'boolean'
  ) {
    return null;
  }

  return {
    id,
    predictedItem: normalizeOptionalString(value.predictedItem),
    finalItem,
    wasCorrected,
    imageUri: normalizeOptionalString(value.imageUri),
    category: normalizeOptionalString(value.category),
    disposalLabel,
    disposalAction: normalizeOptionalString(value.disposalAction),
    scannedAt,
    materialTag: normalizeOptionalString(value.materialTag),
    summary: normalizeOptionalString(value.summary),
    steps: isStringArray(value.steps) ? value.steps : [],
  };
}

function toScanTimestamp(scannedAt: string) {
  const timestamp = Date.parse(scannedAt);
  return Number.isNaN(timestamp) ? 0 : timestamp;
}

function sortRecentScans(scans: RecentScan[]) {
  return [...scans].sort((left, right) => toScanTimestamp(right.scannedAt) - toScanTimestamp(left.scannedAt));
}

function trimRecentScans(scans: RecentScan[]) {
  return sortRecentScans(scans).slice(0, MAX_RECENT_SCANS);
}

async function writeRecentScans(scans: RecentScan[]) {
  const normalizedScans = trimRecentScans(scans);
  await AsyncStorage.setItem(RECENT_SCANS_STORAGE_KEY, JSON.stringify(normalizedScans));
  return normalizedScans;
}

export async function getRecentScans() {
  try {
    const storedValue = await AsyncStorage.getItem(RECENT_SCANS_STORAGE_KEY);
    if (!storedValue) {
      return [];
    }

    const parsedValue = JSON.parse(storedValue) as unknown;
    if (!Array.isArray(parsedValue)) {
      return [];
    }

    return trimRecentScans(
      parsedValue
        .map((scan) => normalizeRecentScan(scan))
        .filter((scan): scan is RecentScan => scan !== null)
    );
  } catch {
    return [];
  }
}

export async function saveRecentScan(scan: RecentScan) {
  const recentScans = await getRecentScans();
  const nextScans = [scan, ...recentScans.filter((existingScan) => existingScan.id !== scan.id)];

  return writeRecentScans(nextScans);
}

export async function updateRecentScan(id: string, updates: Partial<RecentScan>) {
  const recentScans = await getRecentScans();
  const scanIndex = recentScans.findIndex((scan) => scan.id === id);

  if (scanIndex === -1) {
    return recentScans;
  }

  const nextScans = [...recentScans];
  nextScans[scanIndex] = {
    ...nextScans[scanIndex],
    ...updates,
    id: nextScans[scanIndex].id,
  };

  return writeRecentScans(nextScans);
}

export async function deleteRecentScan(id: string) {
  const recentScans = await getRecentScans();
  const nextScans = recentScans.filter((scan) => scan.id !== id);

  if (nextScans.length === recentScans.length) {
    return recentScans;
  }

  return writeRecentScans(nextScans);
}

export async function clearRecentScans() {
  await AsyncStorage.removeItem(RECENT_SCANS_STORAGE_KEY);
}
