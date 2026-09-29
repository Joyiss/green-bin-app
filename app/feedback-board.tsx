import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useCallback, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { WebView } from 'react-native-webview';

import { captureAnalyticsEvent } from '@/analytics';
import { PRIMARY_TEXT_STYLES, SECONDARY_TEXT_STYLES } from '@/constants/typography';

const FEATUREBASE_PORTAL_URL = 'https://greenbin.featurebase.app/';

export default function FeedbackBoardScreen() {
  const router = useRouter();
  const [isLoading, setIsLoading] = useState(true);
  const [hasError, setHasError] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const hasTrackedOpenRef = useRef(false);

  const handleLoadStart = useCallback(() => {
    setHasError(false);
    setIsLoading(true);
  }, []);

  const handleLoadEnd = useCallback(() => {
    setIsLoading(false);
  }, []);

  const handleLoadSuccess = useCallback(() => {
    if (hasTrackedOpenRef.current) {
      return;
    }

    hasTrackedOpenRef.current = true;
    captureAnalyticsEvent('feedback_board_opened');
  }, []);

  const handleLoadError = useCallback(() => {
    setHasError(true);
    setIsLoading(false);
  }, []);

  const handleRetry = useCallback(() => {
    setHasError(false);
    setIsLoading(true);
    setReloadKey((currentKey) => currentKey + 1);
  }, []);

  return (
    <SafeAreaView edges={['top', 'bottom']} style={styles.page}>
      <View style={styles.header}>
        <Pressable
          accessibilityLabel="Back to Profile"
          accessibilityRole="button"
          hitSlop={8}
          onPress={() => router.back()}
          style={({ pressed }) => [styles.backButton, pressed && styles.pressed]}
        >
          <Ionicons color="#242220" name="chevron-back" size={22} />
          <Text style={styles.backLabel}>Back</Text>
        </Pressable>
        <Text style={styles.headerTitle}>Send Feedback</Text>
        <View style={styles.headerSpacer} />
      </View>

      <View style={styles.portalContainer}>
        <WebView
          key={reloadKey}
          onError={handleLoadError}
          onHttpError={handleLoadError}
          onLoad={handleLoadSuccess}
          onLoadEnd={handleLoadEnd}
          onLoadStart={handleLoadStart}
          originWhitelist={['https://*']}
          source={{ uri: FEATUREBASE_PORTAL_URL }}
          style={styles.webView}
          testID="featurebase-webview"
        />

        {isLoading && !hasError ? (
          <View style={styles.stateOverlay}>
            <ActivityIndicator
              accessibilityLabel="Loading feedback portal"
              color="#2E6B47"
              size="large"
            />
            <Text style={styles.stateMessage}>Loading feedback…</Text>
          </View>
        ) : null}

        {hasError ? (
          <View accessibilityRole="alert" style={styles.stateOverlay}>
            <View style={styles.errorIcon}>
              <Ionicons color="#2E6B47" name="cloud-offline-outline" size={28} />
            </View>
            <Text style={styles.errorTitle}>Couldn’t load feedback</Text>
            <Text style={styles.errorMessage}>
              Check your connection, then try again.
            </Text>
            <Pressable
              accessibilityRole="button"
              onPress={handleRetry}
              style={({ pressed }) => [styles.retryButton, pressed && styles.pressed]}
            >
              <Text style={styles.retryLabel}>Try Again</Text>
            </Pressable>
          </View>
        ) : null}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  page: {
    backgroundColor: '#F3F1EE',
    flex: 1,
  },
  header: {
    alignItems: 'center',
    backgroundColor: '#F3F1EE',
    borderBottomColor: '#E5E0D9',
    borderBottomWidth: StyleSheet.hairlineWidth,
    flexDirection: 'row',
    minHeight: 58,
    paddingHorizontal: 14,
  },
  backButton: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 2,
    minHeight: 44,
    width: 82,
  },
  backLabel: {
    color: '#242220',
    fontSize: 15,
    ...SECONDARY_TEXT_STYLES.semiBold,
  },
  headerTitle: {
    color: '#171614',
    flex: 1,
    fontSize: 18,
    textAlign: 'center',
    ...PRIMARY_TEXT_STYLES.title,
  },
  headerSpacer: {
    width: 82,
  },
  pressed: {
    opacity: 0.7,
  },
  portalContainer: {
    backgroundColor: '#FFFFFF',
    flex: 1,
  },
  webView: {
    backgroundColor: '#FFFFFF',
    flex: 1,
  },
  stateOverlay: {
    alignItems: 'center',
    backgroundColor: '#F8F6F2',
    bottom: 0,
    gap: 14,
    justifyContent: 'center',
    left: 0,
    paddingHorizontal: 32,
    position: 'absolute',
    right: 0,
    top: 0,
  },
  stateMessage: {
    color: '#6F6A64',
    fontSize: 14,
    ...SECONDARY_TEXT_STYLES.regular,
  },
  errorIcon: {
    alignItems: 'center',
    backgroundColor: '#E5F0E8',
    borderRadius: 18,
    height: 52,
    justifyContent: 'center',
    width: 52,
  },
  errorTitle: {
    color: '#171614',
    fontSize: 20,
    textAlign: 'center',
    ...PRIMARY_TEXT_STYLES.title,
  },
  errorMessage: {
    color: '#6F6A64',
    fontSize: 14,
    lineHeight: 21,
    textAlign: 'center',
    ...SECONDARY_TEXT_STYLES.regular,
  },
  retryButton: {
    alignItems: 'center',
    backgroundColor: '#1B1B1B',
    borderRadius: 999,
    justifyContent: 'center',
    marginTop: 4,
    minHeight: 46,
    paddingHorizontal: 24,
  },
  retryLabel: {
    color: '#FFFFFF',
    fontSize: 14,
    ...SECONDARY_TEXT_STYLES.semiBold,
  },
});
