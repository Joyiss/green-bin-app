const mockStorage = new Map<string, string>();

jest.mock('@react-native-async-storage/async-storage', () => ({
  getItem: jest.fn(async (key: string) => mockStorage.get(key) ?? null),
  setItem: jest.fn(async (key: string, value: string) => {
    mockStorage.set(key, value);
  }),
}));

import {
  DEFAULT_DAILY_SCAN_LIMIT,
  DEFAULT_MONTHLY_SCAN_LIMIT,
  getScanUsageDisplayState,
  getScanUsageMetadata,
  normalizeScanUsageMetadata,
  saveScanUsageMetadata,
} from '@/storage/scanUsage';

const SERVER_USAGE = {
  daily_limit: 5,
  daily_scans_remaining: 2,
  daily_reset_at: '2026-07-10T00:00:00Z',
  monthly_limit: 20,
  monthly_scans_remaining: 8,
  monthly_reset_at: '2026-08-01T00:00:00Z',
};

describe('scan usage metadata', () => {
  beforeEach(() => {
    mockStorage.clear();
    jest.useFakeTimers();
    jest.setSystemTime(new Date('2026-07-09T12:00:00Z'));
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('uses the backend daily and monthly remaining counts', () => {
    expect(normalizeScanUsageMetadata(SERVER_USAGE)).toMatchObject({
      dailyLimit: 5,
      dailyScansRemaining: 2,
      dailyResetAt: '2026-07-10T00:00:00Z',
      monthlyLimit: 20,
      monthlyScansRemaining: 8,
      monthlyResetAt: '2026-08-01T00:00:00Z',
    });
  });

  it('resets the daily allowance without resetting the current month', async () => {
    await saveScanUsageMetadata(SERVER_USAGE);
    jest.setSystemTime(new Date('2026-07-10T12:00:00Z'));

    await expect(getScanUsageMetadata()).resolves.toMatchObject({
      dailyLimit: 5,
      dailyScansRemaining: 5,
      dailyResetAt: '2026-07-11T00:00:00.000Z',
      monthlyLimit: 20,
      monthlyScansRemaining: 8,
      monthlyResetAt: '2026-08-01T00:00:00Z',
    });
  });

  it('resets both allowances after the monthly boundary', async () => {
    await saveScanUsageMetadata(SERVER_USAGE);
    jest.setSystemTime(new Date('2026-08-01T00:00:00Z'));

    await expect(getScanUsageMetadata()).resolves.toBeNull();
    await expect(getScanUsageDisplayState()).resolves.toEqual({
      dailyLimit: DEFAULT_DAILY_SCAN_LIMIT,
      dailyResetAt: null,
      dailyScansRemaining: DEFAULT_DAILY_SCAN_LIMIT,
      hasStoredMetadata: false,
      monthlyLimit: DEFAULT_MONTHLY_SCAN_LIMIT,
      monthlyResetAt: null,
      monthlyScansRemaining: DEFAULT_MONTHLY_SCAN_LIMIT,
    });
  });
});
