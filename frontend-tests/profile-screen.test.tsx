import { act, fireEvent, render, waitFor } from '@testing-library/react-native';
import { AccessibilityInfo, Alert, Linking } from 'react-native';
import { ApiError } from '@/api/request';

const mockPush = jest.fn();
const mockGetAppLocationContext: jest.Mock = jest.fn(async () => ({
  coordinates: { latitude: 33.7, longitude: -84.4 }, jurisdictionId: null,
  coarseDisposalLocation: { city: 'Atlanta', county: 'Fulton', state: 'Georgia' },
}));
const mockFetchCurrentProvider: jest.Mock = jest.fn(async () => ({ provider: null, restriction: null }));
const mockVerifyServiceProvider = jest.fn(async () => ({
  verification_id: 'verification-id', cached: false, cooldown: null,
  result: {
    status: 'verified', name: 'City Waste', services: ['Residential recycling'],
    match: 'confirmed', reason: 'Verified for this location.',
    evidence: [{ title: 'Provider', url: 'https://provider.example', snippet: 'Curbside service.' }],
  },
}));
const mockConfirmServiceProvider = jest.fn(async (_id: string, rawInputName: string) => ({
  provider: {
    id: 'provider-id', canonical_name: 'City Waste', raw_input_name: rawInputName,
    services: ['Residential recycling'], city: 'Atlanta', county: 'Fulton', state: 'Georgia',
    status: 'verified', evidence_urls: ['https://provider.example'],
    verified_at: '2026-08-16T00:00:00Z',
  },
}));
const mockGetScanUsageDisplayState = jest.fn(async () => ({
  dailyLimit: 5,
  dailyResetAt: '2026-08-16T00:00:00.000Z',
  dailyScansRemaining: 3,
  hasStoredMetadata: true,
  monthlyLimit: 20,
  monthlyResetAt: '2026-09-01T00:00:00.000Z',
  monthlyScansRemaining: 12,
}));

jest.mock('expo-router', () => ({
  useRouter: () => ({ push: mockPush }),
}));

jest.mock('@react-navigation/native', () => {
  const React = require('react');
  return {
    useFocusEffect: (callback: () => void | (() => void)) => {
      React.useEffect(callback, [callback]);
    },
  };
});

jest.mock('expo-constants', () => ({
  expoConfig: { version: '1.2.3' },
}));

jest.mock('react-native-safe-area-context', () => {
  const { View } = require('react-native');
  return {
    SafeAreaView: View,
    useSafeAreaInsets: () => ({ bottom: 12, left: 0, right: 0, top: 24 }),
  };
});

jest.mock('@/app/development-location', () => ({
  DEVELOPMENT_LOCATION_TOOLS_ENABLED: false,
  DEFAULT_DEVELOPMENT_LOCATION_SETTINGS: { location: { enabled: false } },
  loadDevelopmentLocationSettings: jest.fn(async () => ({ location: { enabled: false } })),
  resolveDevelopmentPredictionLocation: ({ deviceLocation, deviceJurisdictionId }: any) => ({
    coarseDisposalLocation: deviceLocation,
    jurisdictionId: deviceJurisdictionId,
    developmentOverrideActive: false,
  }),
}));

jest.mock('@/app/location-context', () => ({
  getAppLocationContext: (...args: any[]) => mockGetAppLocationContext.apply(null, args as any),
}));

jest.mock('@/api/client', () => ({
  fetchCurrentProvider: (...args: any[]) => mockFetchCurrentProvider.apply(null, args as any),
  verifyServiceProvider: (...args: any[]) => mockVerifyServiceProvider.apply(null, args as any),
  confirmServiceProvider: (...args: any[]) => mockConfirmServiceProvider.apply(null, args as any),
}));

jest.mock('@/components/bottom-nav-bar', () => ({
  BOTTOM_NAV_BAR_HEIGHT: 64,
}));

jest.mock('@/components/location-testing-section', () => ({
  LocationTestingSection: () => null,
}));

jest.mock('@/storage/scanUsage', () => ({
  DEFAULT_DAILY_SCAN_LIMIT: 5,
  DEFAULT_MONTHLY_SCAN_LIMIT: 20,
  getScanUsageDisplayState: () => mockGetScanUsageDisplayState(),
  getInstallationId: jest.fn(async () => 'raw-installation-id'),
}));

import ProfileScreen, {
  formatResetTiming,
  getAllowanceProgress,
} from '@/app/(tabs)/profile';

describe('Profile screen redesign', () => {
  beforeEach(() => {
    mockPush.mockClear();
    mockGetScanUsageDisplayState.mockClear();
    mockFetchCurrentProvider.mockClear();
    mockVerifyServiceProvider.mockClear();
    mockConfirmServiceProvider.mockClear();
    mockGetAppLocationContext.mockClear();
    mockGetAppLocationContext.mockResolvedValue({
      coordinates: { latitude: 33.7, longitude: -84.4 }, jurisdictionId: null,
      coarseDisposalLocation: { city: 'Atlanta', county: 'Fulton', state: 'Georgia' },
    });
    mockFetchCurrentProvider.mockResolvedValue({ provider: null, restriction: null });
    jest.spyOn(AccessibilityInfo, 'isReduceMotionEnabled').mockResolvedValue(true);
    jest.spyOn(Linking, 'canOpenURL').mockResolvedValue(true);
    jest.spyOn(Linking, 'openURL').mockResolvedValue(undefined);
    jest.mocked(Linking.canOpenURL).mockClear();
    jest.mocked(Linking.openURL).mockClear();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('renders allowance and settings without legacy activity content', async () => {
    const screen = await render(<ProfileScreen />);

    expect(screen.getByText('Profile.')).toBeTruthy();
    expect(screen.getByText('3 of 5 remaining')).toBeTruthy();
    expect(screen.getByText('12 of 20 remaining')).toBeTruthy();
    expect(screen.getByText('App Version')).toBeTruthy();
    expect(screen.getByText('1.2.3')).toBeTruthy();
    expect(screen.queryByText('Your activity')).toBeNull();
    expect(screen.queryByText('Scan Stats')).toBeNull();
    expect(screen.queryByText('Progress')).toBeNull();
  });

  it('updates the drop-off distance for the current render session', async () => {
    const screen = await render(<ProfileScreen />);

    await fireEvent.press(screen.getByText('Maximum Drop-off Distance'));
    await fireEvent.press(screen.getByText('25 miles'));

    expect(screen.getByText('25 miles')).toBeTruthy();
    expect(screen.queryByLabelText('Maximum drop-off distance options')).toBeNull();
  });

  it('reuses location without requesting permission and scopes current-provider loading', async () => {
    await render(<ProfileScreen />);
    await waitFor(() => expect(mockFetchCurrentProvider).toHaveBeenCalled());
    expect(mockGetAppLocationContext).toHaveBeenCalledWith({ requestPermission: false });
    expect(mockFetchCurrentProvider.mock.calls[0][0]).toEqual({
      city: 'Atlanta', county: 'Fulton', state: 'Georgia',
    });
  });

  it('does not load a previous location provider after location changes', async () => {
    const oldProvider = {
      id: 'old', canonical_name: 'Atlanta Waste', raw_input_name: 'Atlanta Waste',
      services: ['Recycling'], city: 'Atlanta', county: 'Fulton', state: 'Georgia',
      status: 'verified', evidence_urls: [], verified_at: '2026-08-16T00:00:00Z',
    };
    mockFetchCurrentProvider.mockResolvedValueOnce({ provider: oldProvider, restriction: null });
    const first = await render(<ProfileScreen />);
    await waitFor(() => expect(first.getByText('Configured')).toBeTruthy());
    await first.unmount();

    mockGetAppLocationContext.mockResolvedValueOnce({
      coordinates: { latitude: 47.6, longitude: -122.3 }, jurisdictionId: null,
      coarseDisposalLocation: { city: 'Seattle', county: 'King', state: 'Washington' },
    });
    mockFetchCurrentProvider.mockResolvedValueOnce({ provider: null, restriction: null });
    const second = await render(<ProfileScreen />);
    await waitFor(() => expect(second.getByText('Not configured')).toBeTruthy());
    expect(mockFetchCurrentProvider.mock.calls.at(-1)?.[0]).toEqual({
      city: 'Seattle', county: 'King', state: 'Washington',
    });
  });

  it('saves curbside values in memory and discards later unsaved edits', async () => {
    const screen = await render(<ProfileScreen />);

    await waitFor(() => expect(mockFetchCurrentProvider).toHaveBeenCalled());
    await fireEvent.press(screen.getByText('Curbside Service'));
    await fireEvent.press(screen.getByText('Yes'));
    jest.useFakeTimers();
    await fireEvent.changeText(
      screen.getByLabelText('Curbside recycling provider name'),
      'City Waste',
    );
    await fireEvent.press(screen.getByLabelText('Trash pickup day, Monday'));
    await fireEvent.press(screen.getByLabelText('Recycling pickup day, Tuesday'));
    await fireEvent(screen.getByLabelText('Pickup reminders'), 'valueChange', true);
    await act(async () => { jest.advanceTimersByTime(600); });
    await fireEvent.press(screen.getByLabelText('Verify provider name'));
    await waitFor(() => expect(screen.getByText('Verified for this location.')).toBeTruthy());
    await fireEvent.press(screen.getByText('Confirm & Save'));
    await waitFor(() => expect(mockConfirmServiceProvider).toHaveBeenCalled());
    jest.useRealTimers();

    expect(screen.getByText('Configured')).toBeTruthy();

    await fireEvent.press(screen.getByText('Curbside Service'));
    expect(screen.getByDisplayValue('City Waste')).toBeTruthy();
    await fireEvent.changeText(
      screen.getByLabelText('Curbside recycling provider name'),
      'Unsaved Provider',
    );
    await fireEvent.press(screen.getByLabelText('Close curbside service settings'));

    await fireEvent.press(screen.getByText('Curbside Service'));
    expect(screen.getByDisplayValue('City Waste')).toBeTruthy();
    expect(screen.queryByDisplayValue('Unsaved Provider')).toBeNull();
  });

  it('reveals Verify after typing pauses and resets it for edits, clearing, and reopen', async () => {
    const screen = await render(<ProfileScreen />);

    await fireEvent.press(screen.getByText('Curbside Service'));
    const providerInput = screen.getByLabelText('Curbside recycling provider name');
    expect(screen.queryByLabelText('Verify provider name')).toBeNull();

    jest.useFakeTimers();
    try {
      await fireEvent.changeText(providerInput, 'City Waste');
      expect(screen.queryByLabelText('Verify provider name')).toBeNull();

      await act(async () => {
        jest.advanceTimersByTime(599);
      });
      expect(screen.queryByLabelText('Verify provider name')).toBeNull();

      await act(async () => {
        jest.advanceTimersByTime(1);
      });
      const verifyButton = screen.getByLabelText('Verify provider name');
      expect(verifyButton).toBeTruthy();

      await fireEvent.press(verifyButton);
      expect(screen.getByDisplayValue('City Waste')).toBeTruthy();

      await fireEvent.changeText(providerInput, 'City Waste Services');
      expect(screen.queryByLabelText('Verify provider name')).toBeNull();

      await act(async () => {
        jest.advanceTimersByTime(600);
      });
      expect(screen.getByLabelText('Verify provider name')).toBeTruthy();

      await fireEvent.changeText(providerInput, '');
      expect(screen.queryByLabelText('Verify provider name')).toBeNull();
      await act(async () => {
        jest.advanceTimersByTime(600);
      });
      expect(screen.queryByLabelText('Verify provider name')).toBeNull();

      await fireEvent.changeText(providerInput, 'Unsaved Provider');
      await fireEvent.press(screen.getByLabelText('Close curbside service settings'));
      await fireEvent.press(screen.getByText('Curbside Service'));
      expect(screen.queryByDisplayValue('Unsaved Provider')).toBeNull();
    } finally {
      jest.runOnlyPendingTimers();
      jest.useRealTimers();
    }
  });

  it('shows an uncertain result and keeps confirmation disabled', async () => {
    mockVerifyServiceProvider.mockResolvedValueOnce({
      verification_id: 'uncertain-id', cached: true, cooldown: null,
      result: {
        status: 'uncertain', name: 'Possible Provider', services: [], match: 'uncertain',
        reason: 'The available evidence does not confirm this service area.',
        evidence: [{ title: 'Search result', url: 'https://provider.example', snippet: 'Service details are unclear.' }],
      },
    });
    const screen = await render(<ProfileScreen />);
    await waitFor(() => expect(mockFetchCurrentProvider).toHaveBeenCalled());
    await fireEvent.press(screen.getByText('Curbside Service'));
    jest.useFakeTimers();
    await fireEvent.changeText(screen.getByLabelText('Curbside recycling provider name'), 'Possible Provider');
    await act(async () => { jest.advanceTimersByTime(600); });
    await fireEvent.press(screen.getByLabelText('Verify provider name'));
    await waitFor(() => expect(screen.getByText('The available evidence does not confirm this service area.')).toBeTruthy());
    expect(screen.getByText('Confirm & Save').parent?.props.accessibilityState.disabled).toBe(true);
    jest.useRealTimers();
  });

  it('shows the backend cooldown retry time in a modal and sheet state', async () => {
    const retryAt = '2026-08-17T00:00:00Z';
    mockVerifyServiceProvider.mockRejectedValueOnce(new ApiError('rate_limit', {
      status: 429,
      body: { detail: { error: 'provider_cooldown', cooldown_reason: 'failed_attempts', retry_at: retryAt } },
    }));
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation(() => undefined);
    const screen = await render(<ProfileScreen />);
    await waitFor(() => expect(mockFetchCurrentProvider).toHaveBeenCalled());
    await fireEvent.press(screen.getByText('Curbside Service'));
    jest.useFakeTimers();
    await fireEvent.changeText(screen.getByLabelText('Curbside recycling provider name'), 'Rejected Provider');
    await act(async () => { jest.advanceTimersByTime(600); });
    await fireEvent.press(screen.getByLabelText('Verify provider name'));
    await waitFor(() => expect(alertSpy).toHaveBeenCalledWith(
      'Provider verification unavailable', expect.stringContaining('Three unsuccessful attempts'),
    ));
    expect(screen.getByText(/Three unsuccessful attempts reached the limit/)).toBeTruthy();
    jest.useRealTimers();
  });

  it('opens About in-app and Privacy & Terms in the external browser', async () => {
    const screen = await render(<ProfileScreen />);

    await fireEvent.press(screen.getByText('About Green Bin & Developer'));
    await fireEvent.press(screen.getByText('Privacy & Terms'));

    expect(mockPush).toHaveBeenCalledWith('/about-green-bin');
    expect(Linking.canOpenURL).toHaveBeenCalledWith(
      'https://joyiss.github.io/green-bin-legal/',
    );
    expect(Linking.openURL).toHaveBeenCalledWith(
      'https://joyiss.github.io/green-bin-legal/',
    );
  });

  it('shows a helpful alert when Privacy & Terms cannot be opened', async () => {
    jest.mocked(Linking.canOpenURL).mockResolvedValue(false);
    const alertSpy = jest.spyOn(Alert, 'alert').mockImplementation(() => undefined);
    const screen = await render(<ProfileScreen />);

    await fireEvent.press(screen.getByText('Privacy & Terms'));

    expect(alertSpy).toHaveBeenCalledWith(
      'Could not open Privacy & Terms',
      'Please visit https://joyiss.github.io/green-bin-legal/',
    );
    expect(Linking.openURL).not.toHaveBeenCalled();
  });
});

describe('Profile allowance helpers', () => {
  it('clamps remaining allowance progress', () => {
    expect(getAllowanceProgress(3, 5)).toBe(0.6);
    expect(getAllowanceProgress(8, 5)).toBe(1);
    expect(getAllowanceProgress(-2, 5)).toBe(0);
    expect(getAllowanceProgress(2, 0)).toBe(0);
  });

  it('uses a clear reset placeholder when timing is unavailable', () => {
    expect(formatResetTiming(null)).toBe(
      'Reset timing available after your next accepted scan.',
    );
    expect(formatResetTiming('not-a-date')).toBe(
      'Reset timing available after your next accepted scan.',
    );
  });
});
