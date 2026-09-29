import { act, fireEvent, render } from '@testing-library/react-native';

const mockBack = jest.fn();
const mockCaptureAnalyticsEvent = jest.fn();

jest.mock('@/analytics', () => ({
  captureAnalyticsEvent: (...args: unknown[]) => mockCaptureAnalyticsEvent(...args),
}));

jest.mock('expo-router', () => ({
  useRouter: () => ({ back: mockBack }),
}));

jest.mock('react-native-safe-area-context', () => {
  const { View } = require('react-native');
  return { SafeAreaView: View };
});

jest.mock('react-native-webview', () => {
  const React = require('react');
  const { View } = require('react-native');
  return {
    WebView: (props: any) => React.createElement(View, props),
  };
});

import FeedbackBoardScreen from '@/app/feedback-board';

describe('Feedback board screen', () => {
  beforeEach(() => {
    mockBack.mockClear();
    mockCaptureAnalyticsEvent.mockClear();
  });

  it('renders Featurebase inside the app with a native back button', async () => {
    const screen = await render(<FeedbackBoardScreen />);
    const webView = screen.getByTestId('featurebase-webview');

    expect(screen.getByText('Send Feedback')).toBeTruthy();
    expect(webView.props.source).toEqual({
      uri: 'https://greenbin.featurebase.app/',
    });
    expect(screen.getByText('Loading feedback…')).toBeTruthy();

    await fireEvent.press(screen.getByLabelText('Back to Profile'));
    expect(mockBack).toHaveBeenCalledTimes(1);
  });

  it('hides loading when the portal finishes loading', async () => {
    const screen = await render(<FeedbackBoardScreen />);

    await fireEvent(screen.getByTestId('featurebase-webview'), 'loadEnd');

    expect(screen.queryByText('Loading feedback…')).toBeNull();
  });

  it('tracks a successful portal open only once', async () => {
    const screen = await render(<FeedbackBoardScreen />);
    const webView = screen.getByTestId('featurebase-webview');

    await fireEvent(webView, 'loadEnd');
    await fireEvent(webView, 'loadEnd');
    screen.rerender(<FeedbackBoardScreen />);

    expect(mockCaptureAnalyticsEvent).toHaveBeenCalledTimes(1);
    expect(mockCaptureAnalyticsEvent).toHaveBeenCalledWith('feedback_board_opened');
  });

  it('shows an error state and retries the embedded portal', async () => {
    const screen = await render(<FeedbackBoardScreen />);

    await fireEvent(screen.getByTestId('featurebase-webview'), 'error');
    await fireEvent(screen.getByTestId('featurebase-webview'), 'loadEnd');
    expect(mockCaptureAnalyticsEvent).not.toHaveBeenCalled();
    expect(screen.getByText('Couldn’t load feedback')).toBeTruthy();
    expect(screen.getByText('Check your connection, then try again.')).toBeTruthy();

    await fireEvent.press(screen.getByText('Try Again'));
    expect(screen.queryByText('Couldn’t load feedback')).toBeNull();
    expect(screen.getByText('Loading feedback…')).toBeTruthy();
    expect(screen.getByTestId('featurebase-webview').props.source).toEqual({
      uri: 'https://greenbin.featurebase.app/',
    });
  });

  it('ends a stalled load and allows a retry without an endless spinner', async () => {
    jest.useFakeTimers();
    try {
      const screen = await render(<FeedbackBoardScreen />);
      await act(async () => {
        jest.advanceTimersByTime(20_000);
      });
      expect(screen.queryByText('Loading feedback…')).toBeNull();
      expect(screen.getByText('Couldn’t load feedback')).toBeTruthy();

      await fireEvent.press(screen.getByText('Try Again'));
      expect(screen.getByText('Loading feedback…')).toBeTruthy();
      await fireEvent(screen.getByTestId('featurebase-webview'), 'loadEnd');
      await act(async () => {
        jest.advanceTimersByTime(20_000);
      });
      expect(screen.queryByText('Couldn’t load feedback')).toBeNull();
    } finally {
      jest.useRealTimers();
    }
  });
});
