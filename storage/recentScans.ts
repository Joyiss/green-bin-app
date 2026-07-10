import AsyncStorage from '@react-native-async-storage/async-storage';

export const RECENT_SCANS_STORAGE_KEY = 'green-bin:recent-scans';
export const MAX_RECENT_SCANS = 50;

export type RecentScanRecognitionStatus = 'confident' | 'uncertain' | 'unknown';
export type RecentScanDisposalStatus = 'needs_action' | 'disposed';

export type RecentScanGuidanceSnapshot = {
  itemName: string;
  category: string | null;
  disposalAction: string | null;
  materialCode: string | null;
  impactLevel: string | null;
  summary: string | null;
  steps: string[];
  warnings: string[];
  guidanceSource: string | null;
  guidanceMetadata: Record<string, unknown> | null;
  recognitionSource: string | null;
  imageUri: string | null;
  createdAt: string;
  normalizedItem: string | null;
  disposalCategory: string | null;
  broadCategory: string | null;
  materialCategory: string | null;
  requiresLocationCheck: boolean;
  supportsDonationReuse: boolean;
};

export type RecentScan = {
  id: string;
  predictedItem: string | null;
  finalItem: string;
  wasCorrected: boolean;
  imageUri: string | null;
  category: string | null;
  disposalLabel: string;
  disposalAction: string | null;
  materialCode: string | null;
  impactLevel: string | null;
  recognitionStatus: RecentScanRecognitionStatus;
  disposalStatus: RecentScanDisposalStatus;
  createdAt: string;
  scannedAt: string;
  updatedAt: string;
  materialTag?: string | null;
  summary?: string | null;
  steps: string[];
  guidanceSnapshot: RecentScanGuidanceSnapshot;
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

function normalizeRecentScanRecognitionStatus(value: unknown): RecentScanRecognitionStatus {
  if (value === 'confident' || value === 'uncertain' || value === 'unknown') {
    return value;
  }

  return 'confident';
}

function normalizeRecentScanDisposalStatus(value: unknown): RecentScanDisposalStatus {
  if (value === 'disposed') {
    return 'disposed';
  }

  return 'needs_action';
}

function normalizeOptionalRecord(value: unknown): Record<string, unknown> | null {
  if (!isRecord(value) || Array.isArray(value)) {
    return null;
  }

  return value;
}

function normalizeOptionalBoolean(value: unknown) {
  return value === true;
}

function normalizeRecentScan(value: unknown): RecentScan | null {
  if (!isRecord(value)) {
    return null;
  }

  const { id, finalItem, scannedAt } = value;

  if (
    typeof id !== 'string' ||
    typeof finalItem !== 'string' ||
    typeof scannedAt !== 'string'
  ) {
    return null;
  }

  const disposalLabel = typeof value.disposalLabel === 'string' ? value.disposalLabel : 'TRASH';
  const wasCorrected = typeof value.wasCorrected === 'boolean' ? value.wasCorrected : false;
  const createdAt = typeof value.createdAt === 'string' ? value.createdAt : scannedAt;
  const updatedAt = typeof value.updatedAt === 'string' ? value.updatedAt : scannedAt;
  const imageUri = normalizeOptionalString(value.imageUri);
  const category = normalizeOptionalString(value.category);
  const disposalAction = normalizeOptionalString(value.disposalAction);
  const materialCode = normalizeOptionalString(value.materialCode);
  const impactLevel = normalizeOptionalString(value.impactLevel);
  const summary = normalizeOptionalString(value.summary);
  const steps = isStringArray(value.steps) ? value.steps : [];
  const guidanceSnapshotValue = normalizeOptionalRecord(value.guidanceSnapshot);
  const guidanceSnapshotSteps = isStringArray(guidanceSnapshotValue?.steps)
    ? guidanceSnapshotValue.steps
    : steps;

  return {
    id,
    predictedItem: normalizeOptionalString(value.predictedItem),
    finalItem,
    wasCorrected,
    imageUri,
    category,
    disposalLabel,
    disposalAction,
    materialCode,
    impactLevel,
    recognitionStatus: normalizeRecentScanRecognitionStatus(value.recognitionStatus ?? value.status),
    disposalStatus: normalizeRecentScanDisposalStatus(value.disposalStatus),
    createdAt,
    scannedAt,
    updatedAt,
    materialTag: normalizeOptionalString(value.materialTag),
    summary,
    steps,
    guidanceSnapshot: {
      itemName: typeof guidanceSnapshotValue?.itemName === 'string' ? guidanceSnapshotValue.itemName : finalItem,
      category: normalizeOptionalString(guidanceSnapshotValue?.category) ?? category,
      disposalAction: normalizeOptionalString(guidanceSnapshotValue?.disposalAction) ?? disposalAction,
      materialCode: normalizeOptionalString(guidanceSnapshotValue?.materialCode) ?? materialCode,
      impactLevel: normalizeOptionalString(guidanceSnapshotValue?.impactLevel) ?? impactLevel,
      summary: normalizeOptionalString(guidanceSnapshotValue?.summary) ?? summary,
      steps: guidanceSnapshotSteps,
      warnings: isStringArray(guidanceSnapshotValue?.warnings) ? guidanceSnapshotValue.warnings : [],
      guidanceSource: normalizeOptionalString(guidanceSnapshotValue?.guidanceSource),
      guidanceMetadata: normalizeOptionalRecord(guidanceSnapshotValue?.guidanceMetadata),
      recognitionSource: normalizeOptionalString(guidanceSnapshotValue?.recognitionSource),
      imageUri: normalizeOptionalString(guidanceSnapshotValue?.imageUri) ?? imageUri,
      createdAt: typeof guidanceSnapshotValue?.createdAt === 'string'
        ? guidanceSnapshotValue.createdAt
        : createdAt,
      normalizedItem: normalizeOptionalString(guidanceSnapshotValue?.normalizedItem),
      disposalCategory: normalizeOptionalString(guidanceSnapshotValue?.disposalCategory),
      broadCategory: normalizeOptionalString(guidanceSnapshotValue?.broadCategory),
      materialCategory: normalizeOptionalString(guidanceSnapshotValue?.materialCategory),
      requiresLocationCheck: normalizeOptionalBoolean(guidanceSnapshotValue?.requiresLocationCheck),
      supportsDonationReuse: normalizeOptionalBoolean(guidanceSnapshotValue?.supportsDonationReuse),
    },
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
