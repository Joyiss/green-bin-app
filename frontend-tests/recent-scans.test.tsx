const mockStorage = new Map<string, string>();
const mockFiles = new Set<string>();

jest.mock('@react-native-async-storage/async-storage', () => ({
  getItem: jest.fn(async (key: string) => mockStorage.get(key) ?? null),
  setItem: jest.fn(async (key: string, value: string) => { mockStorage.set(key, value); }),
  removeItem: jest.fn(async (key: string) => { mockStorage.delete(key); }),
}));

jest.mock('expo-file-system', () => {
  const uriFor = (parts: Array<string | { uri: string }>) => {
    const [base, ...rest] = parts.map((part) => typeof part === 'string' ? part : part.uri);
    return [base.replace(/\/$/, ''), ...rest].join('/');
  };
  class MockDirectory {
    uri: string;
    constructor(...parts: Array<string | { uri: string }>) { this.uri = uriFor(parts); }
    create() {}
  }
  class MockFile {
    uri: string;
    constructor(...parts: Array<string | { uri: string }>) { this.uri = uriFor(parts); }
    get exists() { return mockFiles.has(this.uri); }
    copy(destination: MockFile) { mockFiles.add(destination.uri); }
    delete() { mockFiles.delete(this.uri); }
  }
  return { Directory: MockDirectory, File: MockFile, Paths: { document: { uri: 'file:///documents' } } };
});

import {
  clearRecentScans,
  deleteRecentScan,
  getRecentScans,
  saveRecentScan,
  type RecentScan,
} from '@/storage/recentScans';

function makeScan(id: string): RecentScan {
  const imageUri = `file:///cache/${id}.jpg`;
  return {
    id,
    predictedItem: null,
    finalItem: 'Mock item',
    wasCorrected: false,
    imageUri,
    category: 'Mock',
    disposalLabel: 'RECYCLE',
    disposalAction: 'recycle',
    materialCode: null,
    impactLevel: null,
    recognitionStatus: 'confident',
    disposalStatus: 'needs_action',
    createdAt: '2026-09-01T00:00:00Z',
    scannedAt: '2026-09-01T00:00:00Z',
    updatedAt: '2026-09-01T00:00:00Z',
    steps: [],
    guidanceSnapshot: {
      itemName: 'Mock item', category: 'Mock', disposalAction: 'recycle',
      materialCode: null, impactLevel: null, summary: null, steps: [], warnings: [],
      guidanceSource: null, guidanceMetadata: null, recognitionSource: null,
      imageUri, createdAt: '2026-09-01T00:00:00Z', normalizedItem: null,
      disposalCategory: null, broadCategory: null, materialCategory: null,
      requiresLocationCheck: false, supportsDonationReuse: false,
      jurisdictionId: null, localRuleId: null, localGuidance: null,
    },
  };
}

describe('recent scan image lifetime', () => {
  beforeEach(() => {
    mockStorage.clear();
    mockFiles.clear();
  });

  it('copies a cache photo to documents and preserves its URI after reading history again', async () => {
    const saved = await saveRecentScan(makeScan('scan-1'));
    const imageUri = saved[0].imageUri;
    expect(imageUri).toBe('file:///documents/recent-scan-images/scan-1.jpg');
    expect(saved[0].guidanceSnapshot.imageUri).toBe(imageUri);
    expect(mockFiles.has(imageUri!)).toBe(true);
    expect((await getRecentScans())[0].imageUri).toBe(imageUri);
  });

  it('removes only app-owned photos when a history entry is deleted or all history is cleared', async () => {
    await saveRecentScan(makeScan('scan-1'));
    await saveRecentScan(makeScan('scan-2'));
    await deleteRecentScan('scan-1');
    expect(mockFiles.has('file:///documents/recent-scan-images/scan-1.jpg')).toBe(false);
    expect(mockFiles.has('file:///documents/recent-scan-images/scan-2.jpg')).toBe(true);
    await clearRecentScans();
    expect(mockFiles.size).toBe(0);
  });
});
