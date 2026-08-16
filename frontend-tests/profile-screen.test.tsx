import { fireEvent, render } from '@testing-library/react-native';
import { AccessibilityInfo } from 'react-native';

const mockPush = jest.fn();
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
}));

import ProfileScreen, {
  formatResetTiming,
  getAllowanceProgress,
} from '@/app/(tabs)/profile';

describe('Profile screen redesign', () => {
  beforeEach(() => {
    mockPush.mockClear();
    mockGetScanUsageDisplayState.mockClear();
    jest.spyOn(AccessibilityInfo, 'isReduceMotionEnabled').mockResolvedValue(true);
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

  it('saves curbside values in memory and discards later unsaved edits', async () => {
    const screen = await render(<ProfileScreen />);

    await fireEvent.press(screen.getByText('Curbside Service'));
    await fireEvent.press(screen.getByText('Yes'));
    await fireEvent.changeText(
      screen.getByLabelText('Curbside recycling provider name'),
      'City Waste',
    );
    await fireEvent.press(screen.getByLabelText('Trash pickup day, Monday'));
    await fireEvent.press(screen.getByLabelText('Recycling pickup day, Tuesday'));
    await fireEvent(screen.getByLabelText('Pickup reminders'), 'valueChange', true);
    await fireEvent.press(screen.getByText('Save'));

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

  it('routes information rows to their separate screens', async () => {
    const screen = await render(<ProfileScreen />);

    await fireEvent.press(screen.getByText('About Green Bin & Developer'));
    await fireEvent.press(screen.getByText('Privacy & Terms'));

    expect(mockPush).toHaveBeenNthCalledWith(1, '/about-green-bin');
    expect(mockPush).toHaveBeenNthCalledWith(2, '/privacy-terms');
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
