import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect } from '@react-navigation/native';
import Constants from 'expo-constants';
import { StatusBar } from 'expo-status-bar';
import { useCallback, useMemo, useState } from 'react';
import {
  Alert,
  Linking,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';

import {
  createDevelopmentLocationOverride,
  DEFAULT_DEVELOPMENT_LOCATION_SETTINGS,
  DEVELOPMENT_LOCATION_PRESETS,
  DEVELOPMENT_LOCATION_TOOLS_ENABLED,
  getDevelopmentLocationPresetId,
  loadDevelopmentLocationSettings,
  saveDevelopmentLocationSettings,
  type DevelopmentLocationPreset,
  type DevelopmentLocationSettings,
} from '@/app/development-location';
import { BOTTOM_NAV_BAR_HEIGHT } from '@/components/bottom-nav-bar';
import { getRecentScans, type RecentScan } from '@/storage/recentScans';
import {
  DEFAULT_DAILY_SCAN_LIMIT,
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

type ProfileStat = {
  id: string;
  value: string;
  label: string;
  caption: string;
};

type ProfileStatsSummary = {
  completionPercent: number;
  disposedScans: number;
  needsActionScans: number;
  stats: ProfileStat[];
  statusMessage: string;
  totalScans: number;
};

const DEFAULT_SCAN_USAGE_DISPLAY_STATE: ScanUsageDisplayState = {
  dailyLimit: DEFAULT_DAILY_SCAN_LIMIT,
  hasStoredMetadata: false,
  resetAt: null,
  scansRemaining: DEFAULT_DAILY_SCAN_LIMIT,
};

function formatAttributeLabel(value: string | null | undefined) {
  const normalizedValue = value
    ?.replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

  if (!normalizedValue) {
    return null;
  }

  return normalizedValue.replace(/\b[a-z]/g, (character) => character.toUpperCase());
}

function getCategoryOrMaterial(scan: RecentScan) {
  const categoryCandidates = [
    scan.category,
    scan.guidanceSnapshot.materialCategory,
    scan.guidanceSnapshot.broadCategory,
    scan.materialCode,
  ];

  for (const categoryCandidate of categoryCandidates) {
    const categoryLabel = formatAttributeLabel(categoryCandidate);

    if (categoryLabel) {
      return categoryLabel;
    }
  }

  return null;
}

function getMostCommonCategory(scans: RecentScan[]) {
  const categoryCounts = new Map<string, number>();
  let mostCommonCategory: string | null = null;
  let highestCount = 0;

  scans.forEach((scan) => {
    const category = getCategoryOrMaterial(scan);

    if (!category) {
      return;
    }

    const count = (categoryCounts.get(category) ?? 0) + 1;
    categoryCounts.set(category, count);

    if (count > highestCount) {
      highestCount = count;
      mostCommonCategory = category;
    }
  });

  return mostCommonCategory;
}

function getFeedbackMailtoUrl() {
  const subject = encodeURIComponent(FEEDBACK_SUBJECT);
  const body = encodeURIComponent(FEEDBACK_BODY);

  return `mailto:${FEEDBACK_EMAIL}?subject=${subject}&body=${body}`;
}

function getProfileStatsSummary(scans: RecentScan[]): ProfileStatsSummary {
  const totalScans = scans.length;
  const disposedScans = scans.filter((scan) => scan.disposalStatus === 'disposed').length;
  const needsActionScans = scans.filter((scan) => scan.disposalStatus === 'needs_action').length;
  const topCategory = getMostCommonCategory(scans);
  const completionPercent =
    totalScans > 0 ? Math.round((disposedScans / totalScans) * 100) : 0;
  const needsActionLabel = needsActionScans === 1 ? 'item still needs' : 'items still need';
  const statusMessage =
    totalScans === 0
      ? 'Scan your first item to start building your local disposal profile.'
      : needsActionScans > 0
        ? `${needsActionScans} ${needsActionLabel} action. Mark items disposed as you finish them.`
        : "All scanned items are marked disposed. You're all caught up.";

  return {
    completionPercent,
    disposedScans,
    needsActionScans,
    stats: [
      {
        id: 'total-scans',
        value: String(totalScans),
        label: 'Total',
        caption: 'Saved on this device',
      },
      {
        id: 'disposed-scans',
        value: String(disposedScans),
        label: 'Disposed',
        caption: 'Marked complete',
      },
      {
        id: 'needs-action-scans',
        value: String(needsActionScans),
        label: 'Needs Action',
        caption: 'Still open',
      },
      {
        id: 'top-category',
        value: topCategory ?? 'None yet',
        label: 'Top Type',
        caption: 'Most common category/material',
      },
    ],
    statusMessage,
    totalScans,
  };
}

function LocationTestingSection() {
  const [settings, setSettings] = useState<DevelopmentLocationSettings>(
    DEFAULT_DEVELOPMENT_LOCATION_SETTINGS,
  );
  const [selectedPreset, setSelectedPreset] =
    useState<DevelopmentLocationPreset['id']>('real');
  const [customCity, setCustomCity] = useState('');
  const [customCounty, setCustomCounty] = useState('');
  const [customState, setCustomState] = useState('');
  const [customCountry, setCustomCountry] = useState('United States');
  const customOverride = createDevelopmentLocationOverride(
    customCity,
    customCounty,
    customState,
    customCountry,
  );

  useFocusEffect(
    useCallback(() => {
      let isActive = true;
      void loadDevelopmentLocationSettings().then((storedSettings) => {
        if (!isActive) {
          return;
        }
        setSettings(storedSettings);
        const presetId = getDevelopmentLocationPresetId(storedSettings.location);
        setSelectedPreset(presetId);
        if (presetId === 'custom') {
          setCustomCity(storedSettings.location.city);
          setCustomCounty(storedSettings.location.county ?? '');
          setCustomState(storedSettings.location.state);
          setCustomCountry(storedSettings.location.country);
        }
      });
      return () => {
        isActive = false;
      };
    }, []),
  );

  const persistSettings = useCallback(
    async (nextSettings: DevelopmentLocationSettings) => {
      try {
        const storedSettings =
          await saveDevelopmentLocationSettings(nextSettings);
        setSettings(storedSettings);
      } catch {
        Alert.alert(
          'Could not save testing location',
          'Try selecting the location again.',
        );
      }
    },
    [],
  );

  const handlePresetPress = useCallback(
    (preset: DevelopmentLocationPreset) => {
      setSelectedPreset(preset.id);
      if (preset.id === 'custom' || !preset.location) {
        return;
      }
      void persistSettings({ location: preset.location });
    },
    [persistSettings],
  );

  const handleApplyCustomLocation = useCallback(() => {
    if (!customOverride) {
      return;
    }
    void persistSettings({ location: customOverride });
  }, [customOverride, persistSettings]);

  const selectedLocationLabel = settings.location.enabled
    ? [
        settings.location.city,
        settings.location.county,
        settings.location.state,
        settings.location.country,
      ]
        .filter(Boolean)
        .join(', ')
    : 'Automatic device location';

  return (
    <View style={styles.devSection}>
      <View style={styles.devHeadingRow}>
        <View style={styles.devIcon}>
          <Ionicons color="#7A4E00" name="construct-outline" size={19} />
        </View>
        <View style={styles.devHeadingText}>
          <Text style={styles.devTitle}>Location Testing</Text>
          <Text style={styles.devDescription}>
            Development-only override for testing local Tavily guidance.
          </Text>
        </View>
      </View>

      <View style={styles.devCurrentLocation}>
        <Text style={styles.devCurrentLocationLabel}>Currently selected</Text>
        <Text style={styles.devCurrentLocationValue}>{selectedLocationLabel}</Text>
      </View>

      <View style={styles.devPresetList}>
        {DEVELOPMENT_LOCATION_PRESETS.map((preset) => {
          const selected = selectedPreset === preset.id;
          return (
            <Pressable
              accessibilityRole="radio"
              accessibilityState={{ checked: selected }}
              key={preset.id}
              onPress={() => handlePresetPress(preset)}
              style={({ pressed }) => [
                styles.devPreset,
                selected && styles.devPresetSelected,
                pressed && styles.cardPressed,
              ]}
            >
              <Ionicons
                color={selected ? '#2E6B47' : '#9A948C'}
                name={selected ? 'radio-button-on' : 'radio-button-off'}
                size={18}
              />
              <Text
                style={[
                  styles.devPresetText,
                  selected && styles.devPresetTextSelected,
                ]}
              >
                {preset.label}
              </Text>
            </Pressable>
          );
        })}
      </View>

      {selectedPreset === 'custom' ? (
        <View style={styles.devCustomFields}>
          <TextInput
            accessibilityLabel="Custom test city"
            autoCapitalize="words"
            onChangeText={setCustomCity}
            placeholder="City"
            placeholderTextColor="#9A948C"
            style={styles.devInput}
            value={customCity}
          />
          <TextInput
            accessibilityLabel="Custom test county"
            autoCapitalize="words"
            onChangeText={setCustomCounty}
            placeholder="County (optional)"
            placeholderTextColor="#9A948C"
            style={styles.devInput}
            value={customCounty}
          />
          <TextInput
            accessibilityLabel="Custom test state"
            autoCapitalize="words"
            onChangeText={setCustomState}
            placeholder="State"
            placeholderTextColor="#9A948C"
            style={styles.devInput}
            value={customState}
          />
          <TextInput
            accessibilityLabel="Custom test country"
            autoCapitalize="words"
            onChangeText={setCustomCountry}
            placeholder="Country"
            placeholderTextColor="#9A948C"
            style={styles.devInput}
            value={customCountry}
          />
          <Pressable
            accessibilityRole="button"
            disabled={!customOverride}
            onPress={handleApplyCustomLocation}
            style={({ pressed }) => [
              styles.devApplyButton,
              !customOverride && styles.devApplyButtonDisabled,
              pressed && customOverride && styles.cardPressed,
            ]}
          >
            <Text style={styles.devApplyButtonText}>Use Custom Location</Text>
          </Pressable>
        </View>
      ) : null}

      <Text style={styles.devNote}>
        This changes only the coarse location sent with prediction requests.
        Precise device coordinates are never included.
      </Text>
    </View>
  );
}

export default function ProfileScreen() {
  const insets = useSafeAreaInsets();
  const [recentScans, setRecentScans] = useState<RecentScan[]>([]);
  const [scanUsage, setScanUsage] = useState<ScanUsageDisplayState>(
    DEFAULT_SCAN_USAGE_DISPLAY_STATE,
  );
  const [isRefreshing, setIsRefreshing] = useState(false);
  const statsSummary = useMemo(() => getProfileStatsSummary(recentScans), [recentScans]);
  const appVersion = Constants.expoConfig?.version;
  const scanUsageTitle = scanUsage.hasStoredMetadata
    ? `${scanUsage.scansRemaining} scans left today`
    : `${scanUsage.dailyLimit} scans available today`;
  const scanUsageCaption = scanUsage.hasStoredMetadata
    ? `Daily limit: ${scanUsage.dailyLimit}. Updates after each scan.`
    : `${scanUsage.dailyLimit} daily scans for this test build.`;

  useFocusEffect(
    useCallback(() => {
      let isActive = true;

      void (async () => {
        const [storedScans, storedScanUsage] = await Promise.all([
          getRecentScans(),
          getScanUsageDisplayState(),
        ]);

        if (isActive) {
          setRecentScans(storedScans);
          setScanUsage(storedScanUsage);
        }
      })();

      return () => {
        isActive = false;
      };
    }, [])
  );

  const handleRefresh = useCallback(async () => {
    setIsRefreshing(true);

    try {
      const [storedScans, storedScanUsage] = await Promise.all([
        getRecentScans(),
        getScanUsageDisplayState(),
      ]);
      setRecentScans(storedScans);
      setScanUsage(storedScanUsage);
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

  return (
    <SafeAreaView edges={['top']} style={styles.page}>
      <StatusBar style="dark" />

      <ScrollView
        contentContainerStyle={[
          styles.content,
          { paddingBottom: insets.bottom + BOTTOM_NAV_BAR_HEIGHT + 30 },
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
        <View style={styles.header}>
          <Text style={styles.title}>profile.</Text>
          <Text style={styles.subtitle}>
            Local scan activity and test build details for this device.
          </Text>
        </View>

        <View style={styles.heroCard}>
          <View style={styles.heroTopRow}>
            <View style={styles.heroIcon}>
              <Ionicons color="#15311A" name="leaf-outline" size={26} />
            </View>

            <View style={styles.heroTextBlock}>
              <Text style={styles.heroName}>Your activity</Text>
              <Text style={styles.heroEmail}>Recent scans saved on this device</Text>
            </View>
          </View>

          <Text style={styles.heroMessage}>{statsSummary.statusMessage}</Text>
        </View>

        <View style={styles.scanAllowanceCard}>
          <View style={styles.scanAllowanceIcon}>
            <Ionicons color="#15311A" name="scan-outline" size={21} />
          </View>
          <View style={styles.scanAllowanceTextBlock}>
            <Text style={styles.sectionLabel}>Daily Scans</Text>
            <Text style={styles.scanAllowanceTitle}>{scanUsageTitle}</Text>
            <Text style={styles.scanAllowanceCaption}>{scanUsageCaption}</Text>
          </View>
        </View>

        <View style={styles.statsSection}>
          <Text style={styles.sectionLabel}>Scan Stats</Text>

          <View style={styles.statsGrid}>
            {statsSummary.stats.map((stat) => (
              <View key={stat.id} style={styles.statCard}>
                <Text
                  style={[
                    styles.statValue,
                    stat.id === 'top-category' && styles.statValueLong,
                  ]}
                >
                  {stat.value}
                </Text>
                <Text style={styles.statLabel}>{stat.label}</Text>
                <Text style={styles.statCaption}>{stat.caption}</Text>
              </View>
            ))}
          </View>
        </View>

        <View style={styles.progressCard}>
          <View style={styles.progressTopRow}>
            <View style={styles.progressTextBlock}>
              <Text style={styles.sectionLabel}>Progress</Text>
              <Text style={styles.progressTitle}>
                {statsSummary.totalScans > 0
                  ? `${statsSummary.disposedScans} of ${statsSummary.totalScans} items marked disposed`
                  : 'No scans yet'}
              </Text>
            </View>

            {statsSummary.totalScans > 0 ? (
              <Text style={styles.progressPercent}>
                {statsSummary.completionPercent}% complete
              </Text>
            ) : null}
          </View>

          {statsSummary.totalScans > 0 ? (
            <View style={styles.progressTrack}>
              <View
                style={[
                  styles.progressFill,
                  { width: `${statsSummary.completionPercent}%` },
                ]}
              />
            </View>
          ) : (
            <Text style={styles.progressEmptyText}>
              Scan your first item to start tracking progress.
            </Text>
          )}
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

        {DEVELOPMENT_LOCATION_TOOLS_ENABLED ? (
          <LocationTestingSection />
        ) : null}

        <View style={styles.infoCard}>
          <View style={styles.infoIcon}>
            <Ionicons color="#2E6B47" name="phone-portrait-outline" size={20} />
          </View>
          <View style={styles.infoTextBlock}>
            <Text style={styles.infoTitle}>Privacy and local data</Text>
            <Text style={styles.infoText}>
              Recent scans are stored locally on this device for the test build. No account is
              required to use Green Bin.
            </Text>
          </View>
        </View>

        <View style={styles.appInfoCard}>
          <Text style={styles.infoTitle}>App info</Text>
          <Text style={styles.infoText}>
            Green Bin beta closed testing build{appVersion ? ` - Version ${appVersion}` : ''}
          </Text>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  page: {
    backgroundColor: '#F3F1EE',
    flex: 1,
  },
  content: {
    gap: 18,
    paddingHorizontal: 18,
    paddingTop: 12,
  },
  header: {
    gap: 8,
  },
  title: {
    color: '#050505',
    fontSize: 34,
    fontWeight: '900',
    letterSpacing: -1.3,
  },
  subtitle: {
    color: '#8A8782',
    fontSize: 14,
    lineHeight: 20,
    maxWidth: 300,
  },
  heroCard: {
    backgroundColor: '#FFFFFF',
    borderColor: '#E9E5DF',
    borderRadius: 28,
    borderWidth: 1,
    gap: 14,
    padding: 18,
    shadowColor: '#111827',
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.05,
    shadowRadius: 16,
  },
  heroTopRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 14,
  },
  heroIcon: {
    alignItems: 'center',
    backgroundColor: '#F4F1EC',
    borderRadius: 24,
    height: 60,
    justifyContent: 'center',
    width: 60,
  },
  heroTextBlock: {
    flex: 1,
    gap: 4,
  },
  heroName: {
    color: '#111111',
    fontSize: 20,
    fontWeight: '800',
    letterSpacing: -0.4,
  },
  heroEmail: {
    color: '#8A8782',
    fontSize: 13,
  },
  heroMessage: {
    color: '#66605B',
    fontSize: 14,
    lineHeight: 20,
  },
  scanAllowanceCard: {
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    borderColor: '#E9E5DF',
    borderRadius: 24,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 14,
    padding: 16,
    shadowColor: '#111827',
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.05,
    shadowRadius: 16,
  },
  scanAllowanceIcon: {
    alignItems: 'center',
    backgroundColor: '#F4F1EC',
    borderRadius: 16,
    height: 44,
    justifyContent: 'center',
    width: 44,
  },
  scanAllowanceTextBlock: {
    flex: 1,
    gap: 5,
  },
  scanAllowanceTitle: {
    color: '#161616',
    fontSize: 18,
    fontWeight: '900',
    letterSpacing: -0.3,
  },
  scanAllowanceCaption: {
    color: '#746F69',
    fontSize: 12,
    lineHeight: 17,
  },
  statsSection: {
    gap: 10,
  },
  sectionLabel: {
    color: '#807B75',
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 2.8,
    paddingHorizontal: 4,
    textTransform: 'uppercase',
  },
  statsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  statCard: {
    backgroundColor: '#FFFFFF',
    borderColor: '#E9E5DF',
    borderRadius: 20,
    borderWidth: 1,
    flexBasis: '48%',
    flexGrow: 1,
    gap: 4,
    minHeight: 102,
    paddingHorizontal: 12,
    paddingVertical: 14,
    shadowColor: '#111827',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.04,
    shadowRadius: 12,
  },
  statValue: {
    color: '#111111',
    fontSize: 22,
    fontVariant: ['tabular-nums'],
    fontWeight: '900',
    letterSpacing: -0.6,
  },
  statValueLong: {
    fontSize: 17,
    lineHeight: 22,
  },
  statLabel: {
    color: '#272727',
    fontSize: 11,
    fontWeight: '800',
    letterSpacing: 0.2,
    textTransform: 'uppercase',
  },
  statCaption: {
    color: '#8A8782',
    fontSize: 11,
    lineHeight: 15,
  },
  progressCard: {
    backgroundColor: '#FFFFFF',
    borderColor: '#E9E5DF',
    borderRadius: 24,
    borderWidth: 1,
    gap: 14,
    padding: 18,
    shadowColor: '#111827',
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.05,
    shadowRadius: 16,
  },
  progressTopRow: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 12,
    justifyContent: 'space-between',
  },
  progressTextBlock: {
    flex: 1,
    gap: 8,
  },
  progressTitle: {
    color: '#161616',
    fontSize: 16,
    fontWeight: '800',
    letterSpacing: -0.2,
    lineHeight: 22,
  },
  progressPercent: {
    color: '#2E6B47',
    fontSize: 13,
    fontVariant: ['tabular-nums'],
    fontWeight: '900',
  },
  progressTrack: {
    backgroundColor: '#EFF4EA',
    borderRadius: 999,
    height: 10,
    overflow: 'hidden',
  },
  progressFill: {
    backgroundColor: '#6DB07A',
    borderRadius: 999,
    height: '100%',
  },
  progressEmptyText: {
    color: '#746F69',
    fontSize: 14,
    lineHeight: 20,
  },
  sectionGroup: {
    gap: 10,
  },
  actionCard: {
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    borderColor: '#E9E5DF',
    borderRadius: 24,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 12,
    padding: 16,
    shadowColor: '#111827',
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.05,
    shadowRadius: 16,
  },
  cardPressed: {
    opacity: 0.86,
  },
  actionIcon: {
    alignItems: 'center',
    backgroundColor: '#F4F1EC',
    borderRadius: 14,
    height: 40,
    justifyContent: 'center',
    width: 40,
  },
  actionTextBlock: {
    flex: 1,
    gap: 4,
  },
  actionTitle: {
    color: '#161616',
    fontSize: 15,
    fontWeight: '800',
    letterSpacing: -0.2,
  },
  actionDescription: {
    color: '#7B7670',
    fontSize: 12,
    lineHeight: 17,
  },
  infoCard: {
    alignItems: 'flex-start',
    backgroundColor: '#FFFFFF',
    borderColor: '#E9E5DF',
    borderRadius: 24,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 12,
    padding: 16,
    shadowColor: '#111827',
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.05,
    shadowRadius: 16,
  },
  infoIcon: {
    alignItems: 'center',
    backgroundColor: '#F4F1EC',
    borderRadius: 14,
    height: 40,
    justifyContent: 'center',
    width: 40,
  },
  infoTextBlock: {
    flex: 1,
    gap: 5,
  },
  infoTitle: {
    color: '#161616',
    fontSize: 15,
    fontWeight: '800',
    letterSpacing: -0.2,
  },
  infoText: {
    color: '#746F69',
    fontSize: 13,
    lineHeight: 19,
  },
  appInfoCard: {
    backgroundColor: '#F7F4EF',
    borderColor: '#E6E1DA',
    borderRadius: 20,
    borderWidth: 1,
    gap: 5,
    paddingHorizontal: 16,
    paddingVertical: 14,
  },
  devSection: {
    backgroundColor: '#FFF9ED',
    borderColor: '#EBCF96',
    borderRadius: 24,
    borderWidth: 1,
    gap: 14,
    padding: 16,
  },
  devHeadingRow: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 12,
  },
  devIcon: {
    alignItems: 'center',
    backgroundColor: '#FBE7BC',
    borderRadius: 14,
    height: 40,
    justifyContent: 'center',
    width: 40,
  },
  devHeadingText: {
    flex: 1,
    gap: 4,
  },
  devTitle: {
    color: '#4F3200',
    fontSize: 16,
    fontWeight: '900',
  },
  devDescription: {
    color: '#765A26',
    fontSize: 12,
    lineHeight: 17,
  },
  devCurrentLocation: {
    backgroundColor: '#FBEFD3',
    borderRadius: 12,
    gap: 3,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  devCurrentLocationLabel: {
    color: '#80683B',
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 1,
    textTransform: 'uppercase',
  },
  devCurrentLocationValue: {
    color: '#4F3200',
    fontSize: 13,
    fontWeight: '800',
    lineHeight: 18,
  },
  devPresetList: {
    gap: 7,
  },
  devPreset: {
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    borderColor: '#E8DFD0',
    borderRadius: 14,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 10,
    minHeight: 44,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  devPresetSelected: {
    backgroundColor: '#F1F8EF',
    borderColor: '#76A882',
  },
  devPresetText: {
    color: '#5F5A54',
    flex: 1,
    fontSize: 13,
    fontWeight: '700',
  },
  devPresetTextSelected: {
    color: '#234C31',
  },
  devCustomFields: {
    gap: 8,
  },
  devInput: {
    backgroundColor: '#FFFFFF',
    borderColor: '#DDD4C5',
    borderRadius: 12,
    borderWidth: 1,
    color: '#171717',
    fontSize: 14,
    minHeight: 44,
    paddingHorizontal: 12,
  },
  devApplyButton: {
    alignItems: 'center',
    backgroundColor: '#2E6B47',
    borderRadius: 12,
    justifyContent: 'center',
    minHeight: 42,
    paddingHorizontal: 14,
  },
  devApplyButtonDisabled: {
    backgroundColor: '#AFA89E',
    opacity: 0.65,
  },
  devApplyButtonText: {
    color: '#FFFFFF',
    fontSize: 13,
    fontWeight: '800',
  },
  devNote: {
    color: '#765A26',
    fontSize: 11,
    fontWeight: '600',
    lineHeight: 16,
  },
});
