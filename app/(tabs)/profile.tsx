import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect } from '@react-navigation/native';
import Constants from 'expo-constants';
import { useRouter } from 'expo-router';
import { useCallback, useEffect, useState, type ComponentProps } from 'react';
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

import { DEVELOPMENT_LOCATION_TOOLS_ENABLED } from '@/app/development-location';
import {
  AnimatedDisclosure,
  MOTION_DURATION_BASE,
  MOTION_EASING,
  useReducedMotionPreference,
} from '@/components/animated-interactions';
import { BOTTOM_NAV_BAR_HEIGHT } from '@/components/bottom-nav-bar';
import {
  cloneCurbsideDraft,
  CurbsideServiceSheet,
  EMPTY_CURBSIDE_DRAFT,
  type CurbsideDraft,
} from '@/components/curbside-service-sheet';
import { LocationTestingSection } from '@/components/location-testing-section';
import { PRIMARY_TEXT_STYLES, SECONDARY_TEXT_STYLES } from '@/constants/typography';
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';
import {
  DEFAULT_DAILY_SCAN_LIMIT,
  DEFAULT_MONTHLY_SCAN_LIMIT,
  getScanUsageDisplayState,
  type ScanUsageDisplayState,
} from '@/storage/scanUsage';

const FEEDBACK_EMAIL = 'mallela.rakshan@gmail.com';
const FEEDBACK_SUBJECT = 'Green Bin Feedback';
const FEEDBACK_BODY = [
  'What worked well?',
  '',
  'What was confusing?',
  '',
  'Was any scan result wrong?',
  '',
  'Device/app notes:',
].join('\n');

type DropoffDistanceMiles = 5 | 10 | 25 | 50;

type SettingsRowProps = {
  chevronExpanded?: boolean;
  icon: ComponentProps<typeof Ionicons>['name'];
  label: string;
  onPress?: () => void;
  showDivider?: boolean;
  value: string;
};

const DROPOFF_DISTANCES: DropoffDistanceMiles[] = [5, 10, 25, 50];
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

function DistanceChevron({ expanded }: { expanded: boolean }) {
  const reducedMotion = useReducedMotionPreference();
  const progress = useSharedValue(expanded ? 1 : 0);

  useEffect(() => {
    progress.value = reducedMotion
      ? expanded ? 1 : 0
      : withTiming(expanded ? 1 : 0, {
          duration: MOTION_DURATION_BASE,
          easing: MOTION_EASING,
        });
  }, [expanded, progress, reducedMotion]);

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [{ rotate: `${progress.value * 90}deg` }],
  }));

  return (
    <Animated.View style={!reducedMotion && animatedStyle}>
      <Ionicons color="#8D8A86" name="chevron-forward" size={18} />
    </Animated.View>
  );
}

function SettingsRow({
  chevronExpanded,
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
        chevronExpanded === undefined ? (
          <Ionicons color="#8D8A86" name="chevron-forward" size={18} />
        ) : (
          <DistanceChevron expanded={chevronExpanded} />
        )
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
  const [dropoffDistance, setDropoffDistance] = useState<DropoffDistanceMiles>(10);
  const [distanceMenuOpen, setDistanceMenuOpen] = useState(false);
  const [curbsideSheetVisible, setCurbsideSheetVisible] = useState(false);
  const [savedCurbsideDraft, setSavedCurbsideDraft] = useState<CurbsideDraft | null>(null);
  const [workingCurbsideDraft, setWorkingCurbsideDraft] = useState<CurbsideDraft>(
    cloneCurbsideDraft(EMPTY_CURBSIDE_DRAFT),
  );
  const appVersion = Constants.expoConfig?.version ?? 'Version unavailable (placeholder)';

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

  const openCurbsideSheet = useCallback(() => {
    setDistanceMenuOpen(false);
    setWorkingCurbsideDraft(
      cloneCurbsideDraft(savedCurbsideDraft ?? EMPTY_CURBSIDE_DRAFT),
    );
    setCurbsideSheetVisible(true);
  }, [savedCurbsideDraft]);

  const dismissCurbsideSheet = useCallback(() => {
    setWorkingCurbsideDraft(
      cloneCurbsideDraft(savedCurbsideDraft ?? EMPTY_CURBSIDE_DRAFT),
    );
    setCurbsideSheetVisible(false);
  }, [savedCurbsideDraft]);

  const saveCurbsideSheet = useCallback((draft: CurbsideDraft) => {
    const nextDraft = cloneCurbsideDraft(draft);
    setSavedCurbsideDraft(nextDraft);
    setWorkingCurbsideDraft(nextDraft);
    setCurbsideSheetVisible(false);
  }, []);

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
        <Text style={styles.title}>Profile.</Text>

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
              chevronExpanded={distanceMenuOpen}
              icon="navigate-outline"
              label="Maximum Drop-off Distance"
              onPress={() => setDistanceMenuOpen((open) => !open)}
              value={`${dropoffDistance} miles`}
            />
            <AnimatedDisclosure expanded={distanceMenuOpen}>
              <View accessibilityLabel="Maximum drop-off distance options" style={styles.distanceMenu}>
                {DROPOFF_DISTANCES.map((distance, index) => {
                  const selected = dropoffDistance === distance;
                  return (
                    <Pressable
                      accessibilityRole="radio"
                      accessibilityState={{ checked: selected }}
                      key={distance}
                      onPress={() => {
                        setDropoffDistance(distance);
                        setDistanceMenuOpen(false);
                      }}
                      style={({ pressed }) => [
                        styles.distanceOption,
                        index < DROPOFF_DISTANCES.length - 1 && styles.distanceOptionDivider,
                        pressed && styles.settingsRowPressed,
                      ]}
                    >
                      <Text style={[styles.distanceOptionText, selected && styles.distanceOptionTextSelected]}>
                        {distance} miles
                      </Text>
                      <Ionicons
                        color={selected ? '#2E6B47' : '#B7B2AC'}
                        name={selected ? 'checkmark-circle' : 'ellipse-outline'}
                        size={20}
                      />
                    </Pressable>
                  );
                })}
              </View>
            </AnimatedDisclosure>
            <SettingsRow
              icon="information-circle-outline"
              label="About Green Bin & Developer"
              onPress={() => router.push('/about-green-bin')}
              value="Learn more"
            />
            <SettingsRow
              icon="shield-checkmark-outline"
              label="Privacy & Terms"
              onPress={() => router.push('/privacy-terms')}
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

        {DEVELOPMENT_LOCATION_TOOLS_ENABLED ? <LocationTestingSection /> : null}
      </ScrollView>

      <CurbsideServiceSheet
        draft={workingCurbsideDraft}
        onChange={setWorkingCurbsideDraft}
        onDismiss={dismissCurbsideSheet}
        onSave={saveCurbsideSheet}
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
  distanceMenu: {
    backgroundColor: '#F7F5F1', borderBottomColor: '#ECE8E2', borderBottomWidth: StyleSheet.hairlineWidth,
    borderTopColor: '#ECE8E2', borderTopWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: 16, paddingLeft: 70,
  },
  distanceOption: {
    alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between', minHeight: 46,
  },
  distanceOptionDivider: { borderBottomColor: '#E7E2DB', borderBottomWidth: StyleSheet.hairlineWidth },
  distanceOptionText: { color: '#5F5A54', fontSize: 13, ...SECONDARY_TEXT_STYLES.semiBold },
  distanceOptionTextSelected: { color: '#24583A', ...SECONDARY_TEXT_STYLES.extraBold },
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
