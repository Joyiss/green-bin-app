import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect } from '@react-navigation/native';
import Constants from 'expo-constants';
import { useRouter } from 'expo-router';
import { useCallback, useRef, useState, type ComponentProps } from 'react';
import {
  Alert,
  Linking,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';

import {
  DEFAULT_DEVELOPMENT_LOCATION_SETTINGS,
  DEVELOPMENT_LOCATION_TOOLS_ENABLED,
  loadDevelopmentLocationSettings,
  resolveDevelopmentPredictionLocation,
} from '@/app/development-location';
import { getAppLocationContext } from '@/app/location-context';
import type { CoarseDisposalLocation } from '@/app/jurisdiction';
import {
  confirmServiceProvider,
  fetchCurrentProvider,
  verifyServiceProvider,
  type ProviderLocationRequest,
} from '@/api/client';
import {
  normalizeProviderCooldownError,
  type ProviderRestriction,
  type ProviderVerificationResult,
  type ServiceProviderRecord,
} from '@/api/contracts';
import { ApiError, getApiErrorMessage } from '@/api/request';
import { BOTTOM_NAV_BAR_HEIGHT } from '@/components/bottom-nav-bar';
import {
  cloneCurbsideDraft,
  CurbsideServiceSheet,
  EMPTY_CURBSIDE_DRAFT,
  type CurbsideDraft,
} from '@/components/curbside-service-sheet';
import { PRIMARY_TEXT_STYLES, SECONDARY_TEXT_STYLES } from '@/constants/typography';
import {
  DEFAULT_DAILY_SCAN_LIMIT,
  DEFAULT_MONTHLY_SCAN_LIMIT,
  getScanUsageDisplayState,
  getInstallationId,
  type ScanUsageDisplayState,
} from '@/storage/scanUsage';

const FEEDBACK_EMAIL = 'mallela.rakshan@gmail.com';
const FEEDBACK_SUBJECT = 'Green Bin Feedback';
const PRIVACY_TERMS_URL = 'https://joyiss.github.io/green-bin-legal/';
const FEEDBACK_BODY = [
  'What worked well?',
  '',
  'What was confusing?',
  '',
  'Was any scan result wrong?',
  '',
  'Device/app notes:',
].join('\n');

type SettingsRowProps = {
  icon: ComponentProps<typeof Ionicons>['name'];
  label: string;
  onPress?: () => void;
  showDivider?: boolean;
  value: string;
};

const RESET_TIMING_PLACEHOLDER =
  'Reset timing available after your next accepted scan.';

const DEFAULT_SCAN_USAGE_DISPLAY_STATE: ScanUsageDisplayState = {
  dailyLimit: DEFAULT_DAILY_SCAN_LIMIT,
  dailyResetAt: null,
  dailyScansRemaining: DEFAULT_DAILY_SCAN_LIMIT,
  hasStoredMetadata: false,
  monthlyLimit: DEFAULT_MONTHLY_SCAN_LIMIT,
  monthlyResetAt: null,
  monthlyScansRemaining: DEFAULT_MONTHLY_SCAN_LIMIT,
};

function getFeedbackMailtoUrl() {
  const subject = encodeURIComponent(FEEDBACK_SUBJECT);
  const body = encodeURIComponent(FEEDBACK_BODY);
  return `mailto:${FEEDBACK_EMAIL}?subject=${subject}&body=${body}`;
}

function normalizedProviderName(value: string) {
  return value.trim().replace(/\s+/g, ' ').toLocaleLowerCase();
}

function providerLocationLabel(location: ProviderLocationRequest | null) {
  return location ? [location.city, location.county, location.state].filter(Boolean).join(', ') : null;
}

async function resolveProfileProviderLocation(): Promise<ProviderLocationRequest | null> {
  const settings = DEVELOPMENT_LOCATION_TOOLS_ENABLED
    ? await loadDevelopmentLocationSettings()
    : DEFAULT_DEVELOPMENT_LOCATION_SETTINGS;
  let deviceLocation: CoarseDisposalLocation | null = null;
  let deviceJurisdictionId: string | null = null;
  if (!DEVELOPMENT_LOCATION_TOOLS_ENABLED || !settings.location.enabled) {
    try {
      const context = await getAppLocationContext({ requestPermission: false });
      deviceLocation = context.coarseDisposalLocation;
      deviceJurisdictionId = context.jurisdictionId;
    } catch {
      return null;
    }
  }
  const resolved = resolveDevelopmentPredictionLocation({
    deviceLocation,
    deviceJurisdictionId,
    settings,
  }).coarseDisposalLocation;
  if (!resolved?.city?.trim() || !resolved.state?.trim()) return null;
  return {
    city: resolved.city.trim(),
    state: resolved.state.trim(),
    ...(resolved.county?.trim() ? { county: resolved.county.trim() } : {}),
  };
}

export function getAllowanceProgress(scansRemaining: number, limit: number) {
  if (!Number.isFinite(limit) || limit <= 0) {
    return 0;
  }
  return Math.min(1, Math.max(0, scansRemaining / limit));
}

export function formatResetTiming(resetAt: string | null) {
  if (!resetAt) {
    return RESET_TIMING_PLACEHOLDER;
  }

  const resetDate = new Date(resetAt);
  if (Number.isNaN(resetDate.getTime())) {
    return RESET_TIMING_PLACEHOLDER;
  }

  return `Resets ${new Intl.DateTimeFormat(undefined, {
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    month: 'short',
  }).format(resetDate)}`;
}

function SettingsRow({
  icon,
  label,
  onPress,
  showDivider = true,
  value,
}: SettingsRowProps) {
  const content = (
    <>
      <View style={styles.settingsIcon}>
        <Ionicons color="#1B1B1B" name={icon} size={21} />
      </View>
      <View style={styles.settingsText}>
        <Text style={styles.settingsLabel}>{label}</Text>
        <Text numberOfLines={1} style={styles.settingsValue}>{value}</Text>
      </View>
      {onPress ? (
        <Ionicons color="#8D8A86" name="chevron-forward" size={18} />
      ) : null}
    </>
  );

  return (
    <View>
      {onPress ? (
        <Pressable
          accessibilityHint={`Open ${label}`}
          accessibilityRole="button"
          onPress={onPress}
          style={({ pressed }) => [styles.settingsRow, pressed && styles.settingsRowPressed]}
        >
          {content}
        </Pressable>
      ) : (
        <View accessibilityLabel={`${label}, ${value}`} style={styles.settingsRow}>
          {content}
        </View>
      )}
      {showDivider ? <View style={styles.settingsDivider} /> : null}
    </View>
  );
}

function AllowanceMeter({
  label,
  limit,
  remaining,
  resetAt,
}: {
  label: string;
  limit: number;
  remaining: number;
  resetAt: string | null;
}) {
  const progress = getAllowanceProgress(remaining, limit);
  return (
    <View style={styles.allowanceMeter}>
      <View style={styles.allowanceMeterHeader}>
        <Text style={styles.allowanceMeterLabel}>{label}</Text>
        <Text style={styles.allowanceCount}>{remaining} of {limit} remaining</Text>
      </View>
      <View style={styles.allowanceTrack}>
        <View
          style={[
            styles.allowanceFill,
            { width: `${progress * 100}%` as `${number}%` },
          ]}
        />
      </View>
      <Text style={styles.allowanceReset}>{formatResetTiming(resetAt)}</Text>
    </View>
  );
}

export default function ProfileScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [scanUsage, setScanUsage] = useState<ScanUsageDisplayState>(
    DEFAULT_SCAN_USAGE_DISPLAY_STATE,
  );
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [curbsideSheetVisible, setCurbsideSheetVisible] = useState(false);
  const [savedCurbsideDraft, setSavedCurbsideDraft] = useState<CurbsideDraft | null>(null);
  const [workingCurbsideDraft, setWorkingCurbsideDraft] = useState<CurbsideDraft>(
    cloneCurbsideDraft(EMPTY_CURBSIDE_DRAFT),
  );
  const [providerLocation, setProviderLocation] = useState<ProviderLocationRequest | null>(null);
  const [savedProvider, setSavedProvider] = useState<ServiceProviderRecord | null>(null);
  const [providerRestriction, setProviderRestriction] = useState<ProviderRestriction | null>(null);
  const [providerResult, setProviderResult] = useState<ProviderVerificationResult | null>(null);
  const [providerStatus, setProviderStatus] = useState<'idle' | 'loading' | 'verified' | 'not_verified' | 'uncertain' | 'cooldown' | 'failure'>('idle');
  const [providerError, setProviderError] = useState<string | null>(null);
  const [verificationId, setVerificationId] = useState<string | null>(null);
  const [providerSaving, setProviderSaving] = useState(false);
  const providerConfirmingRef = useRef(false);
  const appVersion = Constants.expoConfig?.version ?? 'Unavailable';

  useFocusEffect(
    useCallback(() => {
      let isActive = true;
      void getScanUsageDisplayState().then((storedScanUsage) => {
        if (isActive) {
          setScanUsage(storedScanUsage);
        }
      });
      return () => {
        isActive = false;
      };
    }, []),
  );

  useFocusEffect(
    useCallback(() => {
      let isActive = true;
      const controller = new AbortController();
      setProviderStatus('loading');
      setProviderError(null);
      setProviderResult(null);
      setVerificationId(null);
      void (async () => {
        const location = await resolveProfileProviderLocation();
        if (!isActive) return;
        setProviderLocation(location);
        if (!location) {
          setSavedProvider(null);
          setSavedCurbsideDraft(null);
          setProviderStatus('failure');
          setProviderError('Location is unavailable. Green Bin will not request it again from this screen.');
          return;
        }
        try {
          const clientId = await getInstallationId();
          const response = await fetchCurrentProvider(location, clientId, controller.signal);
          if (!isActive) return;
          setSavedProvider(response.provider);
          setProviderRestriction(response.restriction);
          if (response.provider) {
            const draft = { ...EMPTY_CURBSIDE_DRAFT, providerName: response.provider.raw_input_name };
            setSavedCurbsideDraft(draft);
            setWorkingCurbsideDraft(cloneCurbsideDraft(draft));
            setProviderResult(null);
            setProviderStatus('verified');
          } else {
            setSavedCurbsideDraft(null);
            setProviderResult(null);
            setProviderStatus('idle');
          }
        } catch {
          if (!isActive) return;
          setSavedProvider(null);
          setProviderRestriction(null);
          setProviderStatus('failure');
          setProviderError('Could not load the provider for this location. You can try again by reopening Profile.');
        }
      })();
      return () => {
        isActive = false;
        controller.abort();
      };
    }, []),
  );

  const handleRefresh = useCallback(async () => {
    setIsRefreshing(true);
    try {
      setScanUsage(await getScanUsageDisplayState());
    } finally {
      setIsRefreshing(false);
    }
  }, []);

  const handleSendFeedbackPress = useCallback(async () => {
    const feedbackUrl = getFeedbackMailtoUrl();
    try {
      const canOpenFeedbackUrl = await Linking.canOpenURL(feedbackUrl);
      if (!canOpenFeedbackUrl) {
        Alert.alert('Could not open email', `Please email feedback to ${FEEDBACK_EMAIL}.`);
        return;
      }
      await Linking.openURL(feedbackUrl);
    } catch {
      Alert.alert('Could not open email', `Please email feedback to ${FEEDBACK_EMAIL}.`);
    }
  }, []);

  const handlePrivacyTermsPress = useCallback(async () => {
    try {
      const canOpenPrivacyTerms = await Linking.canOpenURL(PRIVACY_TERMS_URL);
      if (!canOpenPrivacyTerms) {
        throw new Error('Privacy and terms URL is unavailable');
      }
      await Linking.openURL(PRIVACY_TERMS_URL);
    } catch {
      Alert.alert(
        'Could not open Privacy & Terms',
        `Please visit ${PRIVACY_TERMS_URL}`,
      );
    }
  }, []);

  const openCurbsideSheet = useCallback(() => {
    setWorkingCurbsideDraft(
      cloneCurbsideDraft(savedCurbsideDraft ?? EMPTY_CURBSIDE_DRAFT),
    );
    if (savedProvider) {
      setProviderResult(null);
      setProviderStatus('verified');
    } else if (providerLocation) {
      setProviderResult(null);
      setProviderStatus('idle');
    }
    setProviderError(providerLocation ? null : 'Current city and state are unavailable.');
    setVerificationId(null);
    setCurbsideSheetVisible(true);
  }, [providerLocation, savedCurbsideDraft, savedProvider]);

  const dismissCurbsideSheet = useCallback(() => {
    setWorkingCurbsideDraft(
      cloneCurbsideDraft(savedCurbsideDraft ?? EMPTY_CURBSIDE_DRAFT),
    );
    setCurbsideSheetVisible(false);
  }, [savedCurbsideDraft]);

  const handleCurbsideDraftChange = useCallback((draft: CurbsideDraft) => {
    if (normalizedProviderName(draft.providerName) !== normalizedProviderName(workingCurbsideDraft.providerName)) {
      const stillConfirmed = savedProvider && (
        normalizedProviderName(draft.providerName) === normalizedProviderName(savedProvider.raw_input_name) ||
        normalizedProviderName(draft.providerName) === normalizedProviderName(savedProvider.canonical_name)
      );
      setProviderResult(null);
      setProviderStatus(stillConfirmed ? 'verified' : 'idle');
      setVerificationId(null);
      setProviderError(null);
    }
    setWorkingCurbsideDraft(draft);
  }, [savedProvider, workingCurbsideDraft.providerName]);

  const handleVerifyProvider = useCallback(async () => {
    const name = workingCurbsideDraft.providerName.trim();
    if (!name) {
      setProviderStatus('failure');
      setProviderError('Provider name is required.');
      return;
    }
    if (!providerLocation) {
      setProviderStatus('failure');
      setProviderError('Current city and state are unavailable.');
      Alert.alert('Location unavailable', 'Green Bin cannot verify a provider until an existing city and state are available.');
      return;
    }
    setProviderStatus('loading');
    setProviderError(null);
    setProviderResult(null);
    setVerificationId(null);
    try {
      const clientId = await getInstallationId();
      const response = await verifyServiceProvider(name, providerLocation, clientId);
      setProviderResult(response.result);
      setVerificationId(response.verification_id);
      setProviderStatus(response.result.status);
      if (response.cooldown) {
        const retry = new Date(response.cooldown.retry_at).toLocaleString();
        setProviderError(`Three unsuccessful attempts reached the limit. Try again after ${retry}.`);
        Alert.alert('Provider verification paused', `Try again after ${retry}.`);
      }
    } catch (error) {
      const cooldown = error instanceof ApiError ? normalizeProviderCooldownError(error.body) : null;
      if (cooldown) {
        const retry = new Date(cooldown.retry_at).toLocaleString();
        const message = cooldown.reason === 'successful_confirmation'
          ? `A provider was recently confirmed. You can change it after ${retry}.`
          : cooldown.reason === 'failed_attempts'
            ? `Three unsuccessful attempts reached the limit. Try again after ${retry}.`
            : 'A verification is already in progress. Please wait a moment.';
        setProviderStatus('cooldown');
        setProviderError(message);
        Alert.alert('Provider verification unavailable', message);
      } else {
        setProviderStatus('failure');
        setProviderError(getApiErrorMessage(error, 'nearby'));
      }
    }
  }, [providerLocation, workingCurbsideDraft.providerName]);

  const confirmPendingProvider = useCallback(async () => {
    const rawName = workingCurbsideDraft.providerName.trim();
    if (
      providerConfirmingRef.current ||
      !rawName ||
      !verificationId ||
      !providerLocation ||
      providerStatus !== 'verified'
    ) {
      return false;
    }
    providerConfirmingRef.current = true;
    setProviderSaving(true);
    try {
      const clientId = await getInstallationId();
      const confirmedProvider = (await confirmServiceProvider(
        verificationId, rawName, clientId,
      )).provider;
      const nextDraft = cloneCurbsideDraft(workingCurbsideDraft);
      const verifiedAt = Date.parse(confirmedProvider.verified_at);
      setSavedProvider(confirmedProvider);
      setSavedCurbsideDraft(nextDraft);
      setWorkingCurbsideDraft(nextDraft);
      setProviderResult(null);
      setVerificationId(null);
      setProviderStatus('verified');
      setProviderError(null);
      setProviderRestriction({
        reason: 'successful_confirmation',
        retry_at: new Date(verifiedAt + 24 * 60 * 60 * 1000).toISOString(),
      });
      return true;
    } catch (error) {
      const cooldown = error instanceof ApiError ? normalizeProviderCooldownError(error.body) : null;
      const message = cooldown
        ? `This provider cannot be changed until ${new Date(cooldown.retry_at).toLocaleString()}.`
        : 'Green Bin could not save this provider. Please try again.';
      if (cooldown) setProviderRestriction(cooldown);
      setProviderStatus(cooldown ? 'cooldown' : 'failure');
      setProviderError(message);
      Alert.alert('Could not save provider', message);
      return false;
    } finally {
      providerConfirmingRef.current = false;
      setProviderSaving(false);
    }
  }, [providerLocation, providerStatus, verificationId, workingCurbsideDraft]);

  const saveCurbsideSheet = useCallback(async (draft: CurbsideDraft) => {
    if (!draft.providerName.trim() || providerStatus !== 'verified' || !providerLocation) return false;
    const existingMatch = savedProvider && (
      normalizedProviderName(draft.providerName) === normalizedProviderName(savedProvider.raw_input_name) ||
      normalizedProviderName(draft.providerName) === normalizedProviderName(savedProvider.canonical_name)
    );
    if (!existingMatch) return false;
    const nextDraft = cloneCurbsideDraft(draft);
    setSavedCurbsideDraft(nextDraft);
    setWorkingCurbsideDraft(nextDraft);
    setCurbsideSheetVisible(false);
    return true;
  }, [providerLocation, providerStatus, savedProvider]);

  const providerLocked = Boolean(
    savedProvider &&
    providerRestriction?.reason === 'successful_confirmation' &&
    Date.parse(providerRestriction.retry_at) > Date.now()
  );
  const savedProviderMatchesDraft = Boolean(savedProvider && (
    normalizedProviderName(workingCurbsideDraft.providerName) === normalizedProviderName(savedProvider.raw_input_name) ||
    normalizedProviderName(workingCurbsideDraft.providerName) === normalizedProviderName(savedProvider.canonical_name)
  ));

  return (
    <SafeAreaView edges={['top']} style={styles.page}>
      <ScrollView
        contentContainerStyle={[
          styles.content,
          { paddingBottom: insets.bottom + BOTTOM_NAV_BAR_HEIGHT + 44 },
        ]}
        refreshControl={
          <RefreshControl
            onRefresh={handleRefresh}
            refreshing={isRefreshing}
            tintColor="#2E6B47"
          />
        }
        showsVerticalScrollIndicator={false}
      >
        <Text style={styles.title}>profile.</Text>

        <View style={styles.scanAllowanceCard}>
          <View style={styles.allowanceHeadingRow}>
            <View style={styles.scanAllowanceIcon}>
              <Ionicons color="#1B1B1B" name="scan-outline" size={24} />
            </View>
            <View style={styles.allowanceHeadingText}>
              <Text style={styles.scanAllowanceTitle}>Scan Allowance</Text>
              <Text style={styles.scanAllowanceCaption}>Your available Green Bin scans</Text>
            </View>
          </View>
          <AllowanceMeter
            label="Today"
            limit={scanUsage.dailyLimit}
            remaining={scanUsage.dailyScansRemaining}
            resetAt={scanUsage.dailyResetAt}
          />
          <View style={styles.allowanceDivider} />
          <AllowanceMeter
            label="This month"
            limit={scanUsage.monthlyLimit}
            remaining={scanUsage.monthlyScansRemaining}
            resetAt={scanUsage.monthlyResetAt}
          />
        </View>

        <View style={styles.settingsSection}>
          <Text style={styles.sectionTitle}>Settings</Text>
          <View style={styles.settingsCard}>
            <SettingsRow
              icon="home-outline"
              label="Curbside Service"
              onPress={openCurbsideSheet}
              value={savedCurbsideDraft ? 'Configured' : 'Not configured'}
            />
            <SettingsRow
              icon="information-circle-outline"
              label="About Green Bin"
              onPress={() => router.push('/about-green-bin')}
              value="Learn more"
            />
            <SettingsRow
              icon="shield-checkmark-outline"
              label="Privacy & Terms"
              onPress={() => void handlePrivacyTermsPress()}
              value="View"
            />
            <SettingsRow
              icon="phone-portrait-outline"
              label="App Version"
              showDivider={false}
              value={appVersion}
            />
          </View>
        </View>

        <View style={styles.sectionGroup}>
          <Text style={styles.sectionLabel}>Feedback</Text>
          <Pressable
            accessibilityRole="button"
            onPress={handleSendFeedbackPress}
            style={({ pressed }) => [styles.actionCard, pressed && styles.cardPressed]}
          >
            <View style={styles.actionIcon}>
              <Ionicons color="#1B1B1B" name="mail-outline" size={20} />
            </View>
            <View style={styles.actionTextBlock}>
              <Text style={styles.actionTitle}>Send feedback</Text>
              <Text style={styles.actionDescription}>
                Share what worked, what was confusing, or any scan result that looked wrong.
              </Text>
            </View>
            <Ionicons color="#8D8A86" name="chevron-forward" size={18} />
          </Pressable>
        </View>

      </ScrollView>

      <CurbsideServiceSheet
        draft={workingCurbsideDraft}
        locationLabel={providerLocationLabel(providerLocation)}
        onChange={handleCurbsideDraftChange}
        onConfirm={confirmPendingProvider}
        onDismiss={dismissCurbsideSheet}
        onSave={saveCurbsideSheet}
        onVerify={() => void handleVerifyProvider()}
        providerError={providerError}
        providerLocked={providerLocked}
        providerLockRetryAt={providerLocked ? providerRestriction?.retry_at ?? null : null}
        providerResult={providerResult}
        providerStatus={providerStatus}
        saveDisabled={
          !workingCurbsideDraft.providerName.trim() ||
          providerStatus !== 'verified' ||
          !savedProviderMatchesDraft ||
          !providerLocation
        }
        saving={providerSaving}
        visible={curbsideSheetVisible}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  page: { backgroundColor: '#F3F1EE', flex: 1 },
  content: { gap: 24, paddingHorizontal: 18, paddingTop: 14 },
  title: {
    color: '#050505', fontSize: 36, letterSpacing: -1.4, ...PRIMARY_TEXT_STYLES.header,
  },
  scanAllowanceCard: {
    backgroundColor: '#FFFFFF', borderColor: '#E7E2DB', borderRadius: 28,
    borderWidth: 1, gap: 18, padding: 20, shadowColor: '#111827',
    shadowOffset: { width: 0, height: 8 }, shadowOpacity: 0.06, shadowRadius: 18,
  },
  allowanceHeadingRow: { alignItems: 'center', flexDirection: 'row', gap: 13 },
  scanAllowanceIcon: {
    alignItems: 'center', backgroundColor: '#F4F1EC', borderRadius: 17,
    height: 48, justifyContent: 'center', width: 48,
  },
  allowanceHeadingText: { flex: 1, gap: 3 },
  scanAllowanceTitle: {
    color: '#161616', fontSize: 20, letterSpacing: -0.4, ...PRIMARY_TEXT_STYLES.title,
  },
  scanAllowanceCaption: { color: '#7B7670', fontSize: 12, ...SECONDARY_TEXT_STYLES.regular },
  allowanceMeter: { gap: 8 },
  allowanceMeterHeader: {
    alignItems: 'baseline', flexDirection: 'row', gap: 10, justifyContent: 'space-between',
  },
  allowanceMeterLabel: { color: '#33312E', fontSize: 13, ...PRIMARY_TEXT_STYLES.label },
  allowanceCount: {
    color: '#1B1B1B', fontSize: 13, fontVariant: ['tabular-nums'], ...SECONDARY_TEXT_STYLES.extraBold,
  },
  allowanceTrack: {
    backgroundColor: '#E5E5E5', borderRadius: 999, height: 10, overflow: 'hidden',
  },
  allowanceFill: { backgroundColor: '#1B1B1B', borderRadius: 999, height: '100%' },
  allowanceReset: { color: '#8A857F', fontSize: 11, lineHeight: 16, ...SECONDARY_TEXT_STYLES.regular },
  allowanceDivider: { backgroundColor: '#EEEAE4', height: StyleSheet.hairlineWidth },
  settingsSection: { gap: 12 },
  sectionTitle: { color: '#111111', fontSize: 25, letterSpacing: -0.6, ...PRIMARY_TEXT_STYLES.title },
  settingsCard: {
    backgroundColor: '#FFFFFF', borderColor: '#E7E2DB', borderRadius: 24,
    borderWidth: 1, overflow: 'hidden', shadowColor: '#111827',
    shadowOffset: { width: 0, height: 5 }, shadowOpacity: 0.04, shadowRadius: 14,
  },
  settingsRow: {
    alignItems: 'center', flexDirection: 'row', gap: 12, minHeight: 72,
    paddingHorizontal: 16, paddingVertical: 12,
  },
  settingsRowPressed: { backgroundColor: '#F5F2ED' },
  settingsIcon: {
    alignItems: 'center', backgroundColor: '#F4F1EC', borderRadius: 14,
    height: 42, justifyContent: 'center', width: 42,
  },
  settingsText: { flex: 1, gap: 3, minWidth: 0 },
  settingsLabel: { color: '#1D1C1A', fontSize: 14, ...PRIMARY_TEXT_STYLES.label },
  settingsValue: { color: '#827D77', fontSize: 12, ...SECONDARY_TEXT_STYLES.regular },
  settingsDivider: { backgroundColor: '#ECE8E2', height: StyleSheet.hairlineWidth, marginLeft: 70 },
  sectionGroup: { gap: 10 },
  sectionLabel: {
    color: '#807B75', fontSize: 10, letterSpacing: 2.8, paddingHorizontal: 4,
    textTransform: 'uppercase', ...PRIMARY_TEXT_STYLES.label,
  },
  actionCard: {
    alignItems: 'center', backgroundColor: '#FFFFFF', borderColor: '#E9E5DF',
    borderRadius: 24, borderWidth: 1, flexDirection: 'row', gap: 12, padding: 16,
    shadowColor: '#111827', shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.05, shadowRadius: 16,
  },
  cardPressed: { opacity: 0.86 },
  actionIcon: {
    alignItems: 'center', backgroundColor: '#F4F1EC', borderRadius: 14,
    height: 40, justifyContent: 'center', width: 40,
  },
  actionTextBlock: { flex: 1, gap: 4 },
  actionTitle: { color: '#161616', fontSize: 15, letterSpacing: -0.2, ...PRIMARY_TEXT_STYLES.title },
  actionDescription: { color: '#7B7670', fontSize: 12, lineHeight: 17, ...SECONDARY_TEXT_STYLES.regular },
});
