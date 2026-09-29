const mockGetForegroundPermissionsAsync = jest.fn();
const mockRequestForegroundPermissionsAsync = jest.fn();
const mockGetCurrentPositionAsync = jest.fn();
const mockGetLastKnownPositionAsync = jest.fn();
const mockReverseGeocodeAsync = jest.fn();

jest.mock('expo-location', () => ({
  Accuracy: { Balanced: 3 },
  getForegroundPermissionsAsync: (...args: unknown[]) => mockGetForegroundPermissionsAsync(...args),
  requestForegroundPermissionsAsync: (...args: unknown[]) => mockRequestForegroundPermissionsAsync(...args),
  getCurrentPositionAsync: (...args: unknown[]) => mockGetCurrentPositionAsync(...args),
  getLastKnownPositionAsync: (...args: unknown[]) => mockGetLastKnownPositionAsync(...args),
  reverseGeocodeAsync: (...args: unknown[]) => mockReverseGeocodeAsync(...args),
}));

import {
  clearLocationContextCacheForTests,
  getAppLocationContext,
  LocationPermissionError,
  LocationUnavailableError,
} from '@/app/location-context';

const position = { coords: { latitude: 33.7, longitude: -84.4 } };

describe('location context failure recovery', () => {
  beforeEach(() => {
    jest.useFakeTimers();
    clearLocationContextCacheForTests();
    mockGetForegroundPermissionsAsync.mockReset();
    mockRequestForegroundPermissionsAsync.mockReset();
    mockGetCurrentPositionAsync.mockReset();
    mockGetLastKnownPositionAsync.mockReset();
    mockReverseGeocodeAsync.mockReset();
  });

  afterEach(() => jest.useRealTimers());

  it('reports denied permission without requesting a position', async () => {
    mockGetForegroundPermissionsAsync.mockResolvedValue({ status: 'denied', canAskAgain: false });
    await expect(getAppLocationContext()).rejects.toBeInstanceOf(LocationPermissionError);
    expect(mockGetCurrentPositionAsync).not.toHaveBeenCalled();
  });

  it('recovers after a permission denial on a later attempt', async () => {
    mockGetForegroundPermissionsAsync
      .mockResolvedValueOnce({ status: 'denied', canAskAgain: true })
      .mockResolvedValueOnce({ status: 'granted', canAskAgain: true });
    mockRequestForegroundPermissionsAsync.mockResolvedValue({ status: 'denied', canAskAgain: true });
    mockGetCurrentPositionAsync.mockResolvedValue(position);
    mockReverseGeocodeAsync.mockResolvedValue([]);
    await expect(getAppLocationContext()).rejects.toBeInstanceOf(LocationPermissionError);
    await expect(getAppLocationContext()).resolves.toMatchObject({ coordinates: position.coords });
  });

  it('bounds both stalled position requests and returns an unavailable state', async () => {
    mockGetForegroundPermissionsAsync.mockResolvedValue({ status: 'granted', canAskAgain: true });
    mockGetCurrentPositionAsync.mockReturnValue(new Promise(() => {}));
    mockGetLastKnownPositionAsync.mockReturnValue(new Promise(() => {}));
    const request = getAppLocationContext();
    const outcome = expect(request).rejects.toBeInstanceOf(LocationUnavailableError);
    await jest.advanceTimersByTimeAsync(20_000);
    await outcome;
  });

  it('continues with general guidance when reverse geocoding stalls', async () => {
    mockGetForegroundPermissionsAsync.mockResolvedValue({ status: 'granted', canAskAgain: true });
    mockGetCurrentPositionAsync.mockResolvedValue(position);
    mockReverseGeocodeAsync.mockReturnValue(new Promise(() => {}));
    const request = getAppLocationContext();
    await jest.advanceTimersByTimeAsync(10_000);
    await expect(request).resolves.toMatchObject({
      coordinates: position.coords,
      jurisdictionId: null,
      coarseDisposalLocation: null,
    });
  });
});
