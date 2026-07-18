import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Image,
  Linking,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';

import { getNearbyFallback, supportsNearbyDonationReuse } from '@/constants/nearby-search';
import { setLastNearbyScanContext } from '@/constants/scan-session';
import {
  getRecentScans,
  updateRecentScan,
  type RecentScan,
  type RecentScanDisposalStatus,
} from '@/storage/recentScans';

type RecentScanRouteParams = {
  id?: string | string[];
};

function getRouteValue(value: string | string[] | undefined) {
  if (typeof value === 'string') {
    return value;
  }

  if (Array.isArray(value)) {
    return value[0];
  }

  return null;
}

function getMetadataStringArray(
  metadata: Record<string, unknown> | null,
  ...keys: string[]
) {
  if (!metadata) {
    return [];
  }

  for (const key of keys) {
    const value = metadata[key];
    if (!Array.isArray(value)) {
      continue;
    }

    const values = value
      .map((item) => (typeof item === 'string' ? item.trim() : ''))
      .filter(Boolean);

    if (values.length) {
      return values;
    }
  }

  return [];
}

function getMetadataBoolean(metadata: Record<string, unknown> | null, ...keys: string[]) {
  if (!metadata) {
    return false;
  }

  return keys.some((key) => metadata[key] === true);
}

function formatLabel(value: string | null | undefined) {
  if (!value) {
    return null;
  }

  return value
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function formatScanDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return 'Recent scan';
  }

  return date.toLocaleString([], {
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    month: 'short',
  });
}

function getDisposalActionLabel(action: string | null) {
  return formatLabel(action) ?? 'Follow Local Guidance';
}

function getSnapshotCategory(scan: RecentScan) {
  return scan.guidanceSnapshot.category ?? scan.category;
}

function getNearbyContext(scan: RecentScan) {
  const snapshot = scan.guidanceSnapshot;
  const metadata = snapshot.guidanceMetadata;
  const disposalCategory =
    snapshot.disposalCategory ?? (getNearbyFallback(snapshot.category) ? snapshot.category : null);
  const requiresLocationCheck =
    snapshot.requiresLocationCheck ||
    getMetadataBoolean(metadata, 'requiresLocationCheck', 'requires_location_check');
  const supportsDonationReuse =
    snapshot.supportsDonationReuse ||
    supportsNearbyDonationReuse({
      item: snapshot.normalizedItem ?? snapshot.itemName,
      disposalCategory,
      disposalAction: snapshot.disposalAction,
      summary: snapshot.summary,
      steps: snapshot.steps,
    });

  return {
    item: snapshot.itemName,
    normalizedItem: snapshot.normalizedItem,
    disposalCategory,
    broadCategory: snapshot.broadCategory,
    materialCategory: snapshot.materialCategory,
    disposalAction: snapshot.disposalAction,
    requiresLocationCheck,
    supportsDonationReuse,
  };
}

function isEpaUrl(value: string | null | undefined) {
  if (!value) {
    return false;
  }

  try {
    const hostname = new URL(value).hostname.toLowerCase();
    return hostname === 'epa.gov' || hostname.endsWith('.epa.gov');
  } catch {
    return false;
  }
}

function getSourceRows(metadata: Record<string, unknown> | null) {
  const sourceNames = getMetadataStringArray(metadata, 'sourceNames', 'source_names');
  const sourceUrls = getMetadataStringArray(metadata, 'sourceUrls', 'source_urls');

  return sourceNames.map((name, index) => {
    const sourceUrl = sourceUrls[index];
    return {
      id: `${name}-${index}`,
      name,
      url: isEpaUrl(sourceUrl) ? sourceUrl : null,
    };
  });
}

export default function RecentScanDetailScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const routeParams = useLocalSearchParams<RecentScanRouteParams>();
  const scanId = getRouteValue(routeParams.id);
  const [scan, setScan] = useState<RecentScan | null>(null);
  const [hasLoaded, setHasLoaded] = useState(false);
  const [isUpdatingStatus, setIsUpdatingStatus] = useState(false);

  useEffect(() => {
    let isActive = true;

    void (async () => {
      try {
        const scans = await getRecentScans();
        if (!isActive) {
          return;
        }

        setScan(scans.find((recentScan) => recentScan.id === scanId) ?? null);
      } finally {
        if (isActive) {
          setHasLoaded(true);
        }
      }
    })();

    return () => {
      isActive = false;
    };
  }, [scanId]);

  const sourceRows = useMemo(
    () => getSourceRows(scan?.guidanceSnapshot.guidanceMetadata ?? null),
    [scan?.guidanceSnapshot.guidanceMetadata],
  );

  const handleToggleDisposalStatus = async () => {
    if (!scan || isUpdatingStatus) {
      return;
    }

    const previousScan = scan;
    const nextDisposalStatus: RecentScanDisposalStatus =
      scan.disposalStatus === 'disposed' ? 'needs_action' : 'disposed';
    const updatedAt = new Date().toISOString();

    setIsUpdatingStatus(true);
    setScan({
      ...scan,
      disposalStatus: nextDisposalStatus,
      updatedAt,
    });

    try {
      await updateRecentScan(scan.id, {
        disposalStatus: nextDisposalStatus,
        updatedAt,
      });
    } catch {
      setScan(previousScan);
      Alert.alert('Could not update this scan. Please try again.');
    } finally {
      setIsUpdatingStatus(false);
    }
  };

  const handleFindNearby = () => {
    if (!scan) {
      return;
    }

    const nearbyContext = getNearbyContext(scan);
    const scanSessionId = `recent-${scan.id}-${Date.now()}`;

    setLastNearbyScanContext({
      scanSessionId,
      ...nearbyContext,
    });
    router.navigate({
      pathname: '/(tabs)/nearby',
      params: {
        autoSearch: 'true',
        item: nearbyContext.item,
        normalizedItem: nearbyContext.normalizedItem ?? undefined,
        disposalCategory: nearbyContext.disposalCategory ?? undefined,
        broadCategory: nearbyContext.broadCategory ?? undefined,
        materialCategory: nearbyContext.materialCategory ?? undefined,
        disposalAction: nearbyContext.disposalAction ?? undefined,
        requiresLocationCheck: String(nearbyContext.requiresLocationCheck),
        scanSessionId,
        supportsDonationReuse: String(nearbyContext.supportsDonationReuse),
      },
    });
  };

  if (!hasLoaded) {
    return (
      <SafeAreaView style={styles.page}>
        <StatusBar style="dark" />
        <View style={styles.loadingState}>
          <ActivityIndicator color="#050505" size="small" />
        </View>
      </SafeAreaView>
    );
  }

  if (!scan) {
    return (
      <SafeAreaView style={styles.page}>
        <StatusBar style="dark" />
        <View style={[styles.notFoundState, { paddingBottom: insets.bottom + 24 }]}>
          <View style={styles.notFoundIcon}>
            <Ionicons color="#5F5A54" name="alert-circle-outline" size={24} />
          </View>
          <Text selectable style={styles.notFoundTitle}>Scan not found</Text>
          <Text selectable style={styles.notFoundText}>
            This recent scan may have been deleted from this device.
          </Text>
          <Pressable
            accessibilityRole="button"
            onPress={() => router.back()}
            style={styles.primaryButton}>
            <Text style={styles.primaryButtonText}>Back to scans</Text>
          </Pressable>
        </View>
      </SafeAreaView>
    );
  }

  const snapshot = scan.guidanceSnapshot;
  const category = getSnapshotCategory(scan);
  const materialInfo = [snapshot.materialCode, snapshot.impactLevel]
    .map((value) => value?.trim())
    .filter(Boolean)
    .join(' · ');
  const statusButtonLabel =
    scan.disposalStatus === 'disposed' ? 'Mark as needs action' : 'Mark as disposed';
  const statusButtonIcon =
    scan.disposalStatus === 'disposed' ? 'refresh-outline' : 'checkmark-circle-outline';
  const showSourceSection = sourceRows.length > 0;

  return (
    <SafeAreaView edges={['top']} style={styles.page}>
      <StatusBar style="dark" />
      <ScrollView
        contentContainerStyle={[
          styles.content,
          { paddingBottom: insets.bottom + 26 },
        ]}
        showsVerticalScrollIndicator={false}>
        <View style={styles.header}>
          <Pressable
            accessibilityLabel="Close recent scan details"
            accessibilityRole="button"
            onPress={() => router.back()}
            style={({ pressed }) => [styles.iconButton, pressed && styles.buttonPressed]}>
            <Ionicons color="#181818" name="close" size={22} />
          </Pressable>

          <View
            style={[
              styles.statusPill,
              scan.disposalStatus === 'disposed' && styles.statusPillDisposed,
            ]}>
            <Ionicons
              color={scan.disposalStatus === 'disposed' ? '#2E6B47' : '#7C6A52'}
              name={scan.disposalStatus === 'disposed' ? 'checkmark-circle-outline' : 'time-outline'}
              size={15}
            />
            <Text
              style={[
                styles.statusPillText,
                scan.disposalStatus === 'disposed' && styles.statusPillTextDisposed,
              ]}>
              {scan.disposalStatus === 'disposed' ? 'Disposed' : 'Needs action'}
            </Text>
          </View>
        </View>

        <View style={styles.hero}>
          {snapshot.imageUri ? (
            <Image source={{ uri: snapshot.imageUri }} style={styles.heroImage} />
          ) : (
            <View style={styles.heroPlaceholder}>
              <Ionicons color="#817C76" name="image-outline" size={34} />
            </View>
          )}
        </View>

        <View style={styles.titleBlock}>
          <Text selectable style={styles.scanDate}>{formatScanDate(scan.createdAt)}</Text>
          <Text selectable style={styles.title}>{snapshot.itemName}</Text>
          <View style={styles.chipRow}>
            <View style={styles.actionChip}>
              <Text style={styles.actionChipText}>{getDisposalActionLabel(snapshot.disposalAction)}</Text>
            </View>
            {category ? (
              <View style={styles.infoChip}>
                <Text style={styles.infoChipText}>{category}</Text>
              </View>
            ) : null}
          </View>
          {materialInfo ? (
            <Text selectable style={styles.materialText}>{materialInfo}</Text>
          ) : null}
        </View>

        {snapshot.summary ? (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Summary</Text>
            <Text selectable style={styles.summaryText}>{snapshot.summary}</Text>
          </View>
        ) : null}

        {snapshot.steps.length ? (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Steps</Text>
            <View style={styles.steps}>
              {snapshot.steps.map((step, index) => (
                <View key={`${step}-${index}`} style={styles.stepRow}>
                  <View style={styles.stepIndex}>
                    <Text style={styles.stepIndexText}>{index + 1}</Text>
                  </View>
                  <Text selectable style={styles.stepText}>{step}</Text>
                </View>
              ))}
            </View>
          </View>
        ) : null}

        {snapshot.warnings.length ? (
          <View style={styles.warningSection}>
            {snapshot.warnings.map((warning, index) => (
              <View key={`${warning}-${index}`} style={styles.warningRow}>
                <Ionicons color="#8A6434" name="warning-outline" size={18} />
                <Text selectable style={styles.warningText}>{warning}</Text>
              </View>
            ))}
          </View>
        ) : null}

        {showSourceSection ? (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Sources</Text>
            <View style={styles.sourceList}>
              {sourceRows.map((source) => {
                const sourceUrl = source.url;

                return sourceUrl ? (
                  <Pressable
                    accessibilityRole="link"
                    key={source.id}
                    onPress={() => {
                      Linking.openURL(sourceUrl).catch(() => {
                        Alert.alert(
                          'Unable to open source',
                          'Try opening the guidance source in your browser.',
                        );
                      });
                    }}
                    style={({ pressed }) => [
                      styles.sourceRow,
                      styles.sourceLinkRow,
                      pressed && styles.buttonPressed,
                    ]}>
                    <Text selectable style={styles.sourceLinkText}>{source.name}</Text>
                    <Ionicons color="#2F6B52" name="open-outline" size={16} />
                  </Pressable>
                ) : (
                  <View key={source.id} style={styles.sourceRow}>
                    <Text selectable style={styles.sourceText}>{source.name}</Text>
                  </View>
                );
              })}
            </View>
          </View>
        ) : null}

        <View style={styles.actions}>
          <Pressable
            accessibilityRole="button"
            disabled={isUpdatingStatus}
            onPress={handleToggleDisposalStatus}
            style={({ pressed }) => [
              styles.secondaryButton,
              pressed && styles.buttonPressed,
              isUpdatingStatus && styles.buttonDisabled,
            ]}>
            <Ionicons color="#333333" name={statusButtonIcon} size={17} />
            <Text style={styles.secondaryButtonText}>{statusButtonLabel}</Text>
          </Pressable>

          <Pressable
            accessibilityRole="button"
            onPress={handleFindNearby}
            style={({ pressed }) => [styles.primaryButton, pressed && styles.buttonPressed]}>
            <Ionicons color="#FFFFFF" name="location-outline" size={18} />
            <Text style={styles.primaryButtonText}>Find Nearby Locations</Text>
          </Pressable>
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
    gap: 16,
    paddingHorizontal: 18,
    paddingTop: 12,
  },
  loadingState: {
    alignItems: 'center',
    flex: 1,
    justifyContent: 'center',
  },
  notFoundState: {
    alignItems: 'center',
    flex: 1,
    gap: 12,
    justifyContent: 'center',
    paddingHorizontal: 22,
  },
  notFoundIcon: {
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    borderColor: '#ECE8E2',
    borderRadius: 999,
    borderWidth: 1,
    height: 54,
    justifyContent: 'center',
    width: 54,
  },
  notFoundTitle: {
    color: '#050505',
    fontSize: 22,
    fontWeight: '900',
  },
  notFoundText: {
    color: '#736C65',
    fontSize: 15,
    lineHeight: 22,
    textAlign: 'center',
  },
  header: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  iconButton: {
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    borderColor: '#ECE8E2',
    borderRadius: 999,
    borderWidth: 1,
    height: 44,
    justifyContent: 'center',
    width: 44,
  },
  statusPill: {
    alignItems: 'center',
    backgroundColor: '#F5EFE5',
    borderColor: '#E8D9C4',
    borderRadius: 999,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 6,
    paddingHorizontal: 12,
    paddingVertical: 9,
  },
  statusPillDisposed: {
    backgroundColor: '#E9F4EC',
    borderColor: '#CFE5D4',
  },
  statusPillText: {
    color: '#7C6A52',
    fontSize: 12,
    fontWeight: '800',
  },
  statusPillTextDisposed: {
    color: '#2E6B47',
  },
  hero: {
    backgroundColor: '#FFFFFF',
    borderColor: '#ECE8E2',
    borderRadius: 28,
    borderWidth: 1,
    height: 244,
    overflow: 'hidden',
  },
  heroImage: {
    height: '100%',
    width: '100%',
  },
  heroPlaceholder: {
    alignItems: 'center',
    flex: 1,
    justifyContent: 'center',
  },
  titleBlock: {
    alignItems: 'center',
    gap: 10,
    paddingHorizontal: 4,
    paddingVertical: 4,
  },
  scanDate: {
    color: '#9A948C',
    fontSize: 11,
    fontWeight: '800',
    letterSpacing: 2,
    textTransform: 'uppercase',
  },
  title: {
    color: '#050505',
    fontSize: 34,
    fontWeight: '900',
    letterSpacing: -1.2,
    lineHeight: 40,
    textAlign: 'center',
  },
  chipRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    justifyContent: 'center',
  },
  actionChip: {
    backgroundColor: '#050505',
    borderRadius: 999,
    paddingHorizontal: 13,
    paddingVertical: 8,
  },
  actionChipText: {
    color: '#FFFFFF',
    fontSize: 12,
    fontWeight: '800',
  },
  infoChip: {
    backgroundColor: '#FFFFFF',
    borderColor: '#E4DED7',
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: 13,
    paddingVertical: 8,
  },
  infoChipText: {
    color: '#5F5A54',
    fontSize: 12,
    fontWeight: '800',
  },
  materialText: {
    color: '#736C65',
    fontSize: 13,
    fontWeight: '700',
    textAlign: 'center',
  },
  section: {
    backgroundColor: '#FFFFFF',
    borderColor: '#ECE8E2',
    borderRadius: 28,
    borderWidth: 1,
    gap: 12,
    padding: 18,
  },
  sectionTitle: {
    color: '#817C76',
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 3,
    textTransform: 'uppercase',
  },
  summaryText: {
    color: '#66605B',
    fontSize: 15,
    lineHeight: 22,
  },
  steps: {
    gap: 12,
  },
  stepRow: {
    flexDirection: 'row',
    gap: 10,
  },
  stepIndex: {
    alignItems: 'center',
    borderColor: '#E4DED7',
    borderRadius: 999,
    borderWidth: 1,
    height: 24,
    justifyContent: 'center',
    marginTop: 1,
    width: 24,
  },
  stepIndexText: {
    color: '#8B857F',
    fontSize: 11,
    fontWeight: '800',
  },
  stepText: {
    color: '#736C65',
    flex: 1,
    fontSize: 15,
    lineHeight: 22,
  },
  warningSection: {
    backgroundColor: '#FBF4E8',
    borderColor: '#EEDFC7',
    borderRadius: 24,
    borderWidth: 1,
    gap: 10,
    padding: 14,
  },
  warningRow: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 9,
  },
  warningText: {
    color: '#76552D',
    flex: 1,
    fontSize: 14,
    lineHeight: 20,
  },
  sourceList: {
    gap: 8,
  },
  sourceRow: {
    alignItems: 'center',
    alignSelf: 'flex-start',
    backgroundColor: '#F5F2ED',
    borderColor: '#E7E0D8',
    borderRadius: 999,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 6,
    maxWidth: '100%',
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  sourceLinkRow: {
    backgroundColor: '#EEF6F1',
    borderColor: '#D6E8DD',
  },
  sourceText: {
    color: '#736C65',
    fontSize: 14,
    fontWeight: '800',
  },
  sourceLinkText: {
    color: '#2F6B52',
    fontSize: 14,
    fontWeight: '800',
  },
  actions: {
    gap: 10,
  },
  secondaryButton: {
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    borderColor: '#E3DED6',
    borderRadius: 999,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 8,
    justifyContent: 'center',
    paddingVertical: 14,
  },
  secondaryButtonText: {
    color: '#333333',
    fontSize: 14,
    fontWeight: '800',
  },
  primaryButton: {
    alignItems: 'center',
    backgroundColor: '#050505',
    borderRadius: 999,
    flexDirection: 'row',
    gap: 8,
    justifyContent: 'center',
    paddingHorizontal: 18,
    paddingVertical: 15,
  },
  primaryButtonText: {
    color: '#FFFFFF',
    fontSize: 15,
    fontWeight: '800',
  },
  buttonPressed: {
    opacity: 0.82,
  },
  buttonDisabled: {
    opacity: 0.6,
  },
});
