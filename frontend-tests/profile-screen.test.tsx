import { act, fireEvent, render, waitFor } from '@testing-library/react-native';
import { AccessibilityInfo, Alert, Linking, StyleSheet } from 'react-native';
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
    match: 'confirmed', location_match: 'exact', reason: 'City Waste serves the broader Atlanta area.',
    evidence: [{ title: 'Provider', url: 'https://provider.example', snippet: 'Curbside service.' }],
  },
}));
const mockConfirmServiceProvider = jest.fn(async (_id: string, rawInputName: string) => ({
  provider: {
    id: 'provider-id', canonical_name: 'City Waste', raw_input_name: rawInputName,
    services: ['Residential recycling'], city: 'Atlanta', county: 'Fulton', state: 'Georgia',
    status: 'verified', evidence_urls: ['https://provider.example'],
    verified_at: new Date().toISOString(),
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

    expect(screen.getByText('profile.')).toBeTruthy();
    expect(screen.getByText('3 of 5 remaining')).toBeTruthy();
    expect(screen.getByText('12 of 20 remaining')).toBeTruthy();
    expect(screen.getByText('App Version')).toBeTruthy();
    expect(screen.getByText('1.2.3')).toBeTruthy();
    expect(screen.queryByText('Your activity')).toBeNull();
    expect(screen.queryByText('Scan Stats')).toBeNull();
    expect(screen.queryByText('Progress')).toBeNull();
  });

  it('hides unfinished distance, pickup schedule, reminder, and location-testing controls', async () => {
    const screen = await render(<ProfileScreen />);

    expect(screen.queryByText('Maximum Drop-off Distance')).toBeNull();
    expect(screen.queryByText('Pickup reminders')).toBeNull();
    expect(screen.queryByText('Trash pickup day')).toBeNull();
    expect(screen.queryByText('Test Location')).toBeNull();
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

  it('confirms an exact match inline, persists it, and does not confirm again on Save', async () => {
    const screen = await render(<ProfileScreen />);

    await waitFor(() => expect(mockFetchCurrentProvider).toHaveBeenCalled());
    await fireEvent.press(screen.getByText('Curbside Service'));
    jest.useFakeTimers();
    await fireEvent.changeText(
      screen.getByLabelText('Curbside recycling provider name'),
      'City Waste',
    );
    await act(async () => { jest.advanceTimersByTime(600); });
    await fireEvent.press(screen.getByLabelText('Verify provider name'));
    await waitFor(() => expect(screen.getByText('Provider found for your area. Confirming locks changes for 24 hours.')).toBeTruthy());
    expect(StyleSheet.flatten(screen.getByLabelText('Curbside recycling provider name').props.style))
      .toMatchObject({ borderColor: '#4F9A68', borderWidth: 2 });
    expect(screen.queryByText('City Waste serves the broader Atlanta area.')).toBeNull();
    expect(screen.queryByText('Residential recycling')).toBeNull();
    expect(screen.queryByText('Curbside service.')).toBeNull();
    await fireEvent.press(screen.getByLabelText('Confirm provider name'));
    await waitFor(() => expect(mockConfirmServiceProvider).toHaveBeenCalledTimes(1));
    expect(screen.getByLabelText('Locked curbside provider field')).toBeTruthy();
    expect(screen.queryByLabelText('Confirm provider name')).toBeNull();
    await fireEvent.press(screen.getByText('Confirm & Save'));
    jest.useRealTimers();

    expect(screen.getByText('Configured')).toBeTruthy();
    expect(mockConfirmServiceProvider).toHaveBeenCalledTimes(1);

    await fireEvent.press(screen.getByText('Curbside Service'));
    expect(screen.getByDisplayValue('City Waste')).toBeTruthy();
    expect(screen.getByLabelText('Curbside recycling provider name').props.editable).toBe(false);
    await fireEvent.press(screen.getByText('Confirm & Save'));
    expect(mockConfirmServiceProvider).toHaveBeenCalledTimes(1);
  });

  it('prevents duplicate Confirm presses from restarting the cooldown', async () => {
    let resolveConfirmation: ((value: any) => void) | null = null;
    mockConfirmServiceProvider.mockImplementationOnce(() => new Promise((resolve) => {
      resolveConfirmation = resolve;
    }));
    const screen = await render(<ProfileScreen />);
    await waitFor(() => expect(mockFetchCurrentProvider).toHaveBeenCalled());
    await fireEvent.press(screen.getByText('Curbside Service'));
    jest.useFakeTimers();
    await fireEvent.changeText(screen.getByLabelText('Curbside recycling provider name'), 'City Waste');
    await act(async () => { jest.advanceTimersByTime(600); });
    await fireEvent.press(screen.getByLabelText('Verify provider name'));
    await waitFor(() => expect(screen.getByLabelText('Confirm provider name')).toBeTruthy());
    const confirmButton = screen.getByLabelText('Confirm provider name');
    await fireEvent.press(confirmButton);
    await fireEvent.press(confirmButton);
    expect(mockConfirmServiceProvider).toHaveBeenCalledTimes(1);
    await act(async () => {
      resolveConfirmation?.({
        provider: {
          id: 'provider-id', canonical_name: 'City Waste', raw_input_name: 'City Waste',
          services: ['Residential recycling'], city: 'Atlanta', county: 'Fulton', state: 'Georgia',
          status: 'verified', evidence_urls: [], verified_at: new Date().toISOString(),
        },
      });
    });
    await waitFor(() => expect(screen.getByLabelText('Locked curbside provider field')).toBeTruthy());
    expect(mockConfirmServiceProvider).toHaveBeenCalledTimes(1);
    jest.useRealTimers();
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
      await waitFor(() => expect(screen.getByLabelText('Confirm provider name')).toBeTruthy());

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

  it('shows the regional confirmation modal and No, edit does not persist', async () => {
    mockVerifyServiceProvider.mockResolvedValueOnce({
      verification_id: 'regional-id', cached: false, cooldown: null,
      result: {
        status: 'verified', name: 'Custom Disposal', services: ['Residential trash'],
        match: 'confirmed', location_match: 'regional', reason: 'Serves Metro Atlanta.',
        evidence: [{ title: 'Services', url: 'https://custom.example', snippet: 'Metro Atlanta service.' }],
      },
    });
    const screen = await render(<ProfileScreen />);
    await waitFor(() => expect(mockFetchCurrentProvider).toHaveBeenCalled());
    await fireEvent.press(screen.getByText('Curbside Service'));
    jest.useFakeTimers();
    await fireEvent.changeText(screen.getByLabelText('Curbside recycling provider name'), 'Custom Disposal');
    await act(async () => { jest.advanceTimersByTime(600); });
    await fireEvent.press(screen.getByLabelText('Verify provider name'));
    await waitFor(() => expect(screen.getByText('Is this your provider?')).toBeTruthy());
    expect(screen.getByText("We found Custom Disposal, but couldn’t confirm service in your exact city. Is this the curbside provider you use?")).toBeTruthy();
    expect(screen.getByText('After confirmation, this provider cannot be changed for 24 hours.')).toBeTruthy();
    await fireEvent.press(screen.getByText('No, edit'));
    expect(screen.queryByText('Is this your provider?')).toBeNull();
    expect(screen.getByLabelText('Curbside recycling provider name').props.editable).not.toBe(false);
    expect(mockConfirmServiceProvider).not.toHaveBeenCalled();
    jest.useRealTimers();
  });

  it('confirms a regional match from the modal and locks the field', async () => {
    mockVerifyServiceProvider.mockResolvedValueOnce({
      verification_id: 'regional-id', cached: false, cooldown: null,
      result: {
        status: 'verified', name: 'Custom Disposal', services: ['Residential trash'],
        match: 'confirmed', location_match: 'regional', reason: 'Serves Metro Atlanta.',
        evidence: [{ title: 'Services', url: 'https://custom.example', snippet: 'Metro Atlanta service.' }],
      },
    });
    const screen = await render(<ProfileScreen />);
    await waitFor(() => expect(mockFetchCurrentProvider).toHaveBeenCalled());
    await fireEvent.press(screen.getByText('Curbside Service'));
    jest.useFakeTimers();
    await fireEvent.changeText(screen.getByLabelText('Curbside recycling provider name'), 'Custom Disposal');
    await act(async () => { jest.advanceTimersByTime(600); });
    await fireEvent.press(screen.getByLabelText('Verify provider name'));
    await waitFor(() => expect(screen.getByText('Yes, confirm')).toBeTruthy());
    await fireEvent.press(screen.getByText('Yes, confirm'));
    await waitFor(() => expect(mockConfirmServiceProvider).toHaveBeenCalledTimes(1));
    expect(screen.queryByText('Is this your provider?')).toBeNull();
    expect(screen.getByLabelText('Locked curbside provider field')).toBeTruthy();
    jest.useRealTimers();
  });

  it('uses the same confirmation modal for a verified provider with unknown location coverage', async () => {
    mockVerifyServiceProvider.mockResolvedValueOnce({
      verification_id: 'unknown-id', cached: false, cooldown: null,
      result: {
        status: 'verified', name: 'Neighborhood Waste', services: ['Residential recycling'],
        match: 'confirmed', location_match: 'unknown', reason: 'No precise service area is published.',
        evidence: [{ title: 'Home', url: 'https://neighborhood.example', snippet: 'Residential service.' }],
      },
    });
    const screen = await render(<ProfileScreen />);
    await waitFor(() => expect(mockFetchCurrentProvider).toHaveBeenCalled());
    await fireEvent.press(screen.getByText('Curbside Service'));
    jest.useFakeTimers();
    await fireEvent.changeText(screen.getByLabelText('Curbside recycling provider name'), 'Neighborhood Waste');
    await act(async () => { jest.advanceTimersByTime(600); });
    await fireEvent.press(screen.getByLabelText('Verify provider name'));
    await waitFor(() => expect(screen.getByText('Is this your provider?')).toBeTruthy());
    expect(mockConfirmServiceProvider).not.toHaveBeenCalled();
    jest.useRealTimers();
  });

  it('shows Retry for a provider not found or explicitly outside the area', async () => {
    mockVerifyServiceProvider.mockResolvedValueOnce({
      verification_id: 'outside-id', cached: false, cooldown: null,
      result: {
        status: 'not_verified', name: 'Other State Dumpsters', services: ['Dumpster rental'],
        match: 'rejected', location_match: 'outside', reason: 'Operates outside Georgia.',
        evidence: [{ title: 'Service', url: 'https://outside.example', snippet: 'Commercial dumpsters.' }],
      },
    });
    const screen = await render(<ProfileScreen />);
    await waitFor(() => expect(mockFetchCurrentProvider).toHaveBeenCalled());
    await fireEvent.press(screen.getByText('Curbside Service'));
    jest.useFakeTimers();
    const input = screen.getByLabelText('Curbside recycling provider name');
    await fireEvent.changeText(input, 'Other State Dumpsters');
    await act(async () => { jest.advanceTimersByTime(600); });
    await fireEvent.press(screen.getByLabelText('Verify provider name'));
    await waitFor(() => expect(screen.getByText('Retry')).toBeTruthy());
    expect(screen.getByText('We couldn’t confirm this residential curbside provider. Check the name and try again.')).toBeTruthy();
    expect(screen.queryByText('Operates outside Georgia.')).toBeNull();
    expect(screen.queryByText('Dumpster rental')).toBeNull();
    await fireEvent.changeText(input, 'Corrected Provider');
    expect(screen.queryByText('Retry')).toBeNull();
    expect(mockConfirmServiceProvider).not.toHaveBeenCalled();
    jest.useRealTimers();
  });

  it('shows an app-styled cooldown with the exact retry time for a locked provider', async () => {
    const retryAt = '2099-08-17T14:30:00Z';
    const currentProvider = {
      id: 'locked', canonical_name: 'City Waste', raw_input_name: 'City Waste',
      services: ['Recycling'], city: 'Atlanta', county: 'Fulton', state: 'Georgia',
      status: 'verified', evidence_urls: [], verified_at: '2099-08-16T14:30:00Z',
    };
    mockFetchCurrentProvider.mockResolvedValueOnce({
      provider: currentProvider,
      restriction: { reason: 'successful_confirmation', retry_at: retryAt },
    });
    const screen = await render(<ProfileScreen />);
    await waitFor(() => expect(screen.getByText('Configured')).toBeTruthy());
    await fireEvent.press(screen.getByText('Curbside Service'));
    const input = screen.getByLabelText('Curbside recycling provider name');
    expect(input.props.editable).toBe(false);
    expect(StyleSheet.flatten(input.props.style)).toMatchObject({ backgroundColor: '#E8E5E0' });
    expect(screen.queryByLabelText('Verify provider name')).toBeNull();
    await fireEvent.press(screen.getByLabelText('Locked curbside provider field'));
    expect(screen.getByText('Changes are paused for 24 hours')).toBeTruthy();
    expect(screen.getByText(`Your confirmed provider can be changed after ${new Date(retryAt).toLocaleString()}.`)).toBeTruthy();
    expect(StyleSheet.flatten(screen.getByLabelText('Provider cooldown popup').props.style))
      .toMatchObject({ paddingBottom: 32 });
    expect(StyleSheet.flatten(screen.getByText('Got it').parent?.props.style))
      .toMatchObject({ flex: 0, width: '100%' });
    await fireEvent.press(screen.getByText('Got it'));
    expect(screen.queryByText('Changes are paused for 24 hours')).toBeNull();
  });

  it('shows an uncertain result and keeps confirmation disabled', async () => {
    mockVerifyServiceProvider.mockResolvedValueOnce({
      verification_id: 'uncertain-id', cached: true, cooldown: null,
      result: {
        status: 'uncertain', name: 'Possible Provider', services: [], match: 'uncertain',
        location_match: 'unknown',
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
    await waitFor(() => expect(screen.getByText('We couldn’t confirm this residential curbside provider. Check the name and try again.')).toBeTruthy());
    expect(screen.getByText('Retry')).toBeTruthy();
    expect(screen.queryByText('Is this your provider?')).toBeNull();
    expect(screen.queryByText('The available evidence does not confirm this service area.')).toBeNull();
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

    await fireEvent.press(screen.getByText('About Green Bin'));
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
