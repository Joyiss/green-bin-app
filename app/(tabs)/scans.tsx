import { useFocusEffect } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useCallback, useRef, useState } from 'react';
import { Alert, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Swipeable } from 'react-native-gesture-handler';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';

import { BOTTOM_NAV_BAR_HEIGHT } from '@/components/bottom-nav-bar';
import { PRIMARY_TEXT_STYLES, SECONDARY_TEXT_STYLES } from '@/constants/typography';
import {
  ScanHistoryCard,
  type ScanHistoryCardItem,
  type ScanHistoryCardThumbnailVariant,
} from '@/components/scan-history-card';
import {
  clearRecentScans,
  deleteRecentScan,
  getRecentScans,
  type RecentScan,
} from '../../storage/recentScans';

type ScanHistorySection = {
  id: string;
  title: string;
  items: ScanHistoryCardItem[];
};

function toValidDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function isSameDay(left: Date, right: Date) {
  return (
    left.getFullYear() === right.getFullYear() &&
    left.getMonth() === right.getMonth() &&
    left.getDate() === right.getDate()
  );
}

function getDayKey(date: Date) {
  return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
}

function getSectionTitle(date: Date, now: Date) {
  if (isSameDay(date, now)) {
    return 'Today';
  }

  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);

  if (isSameDay(date, yesterday)) {
    return 'Yesterday';
  }

  return date.toLocaleDateString([], {
    month: 'long',
    day: 'numeric',
  });
}

function formatScanTime(scannedAt: string) {
  const date = toValidDate(scannedAt);
  if (!date) {
    return '';
  }

  return date.toLocaleTimeString([], {
    hour: 'numeric',
    minute: '2-digit',
  });
}

function getMonthlySummary(scans: RecentScan[]) {
  const now = new Date();
  const monthlyCount = scans.filter((scan) => {
    const scannedDate = toValidDate(scan.scannedAt);

    return (
      scannedDate &&
      scannedDate.getFullYear() === now.getFullYear() &&
      scannedDate.getMonth() === now.getMonth()
    );
  }).length;

  return `You've scanned ${monthlyCount} ${monthlyCount === 1 ? 'item' : 'items'} this month.`;
}

function getFallbackThumbnailVariant(itemName: string): ScanHistoryCardThumbnailVariant {
  const normalizedName = itemName.toLowerCase();

  if (normalizedName.includes('box') || normalizedName.includes('cardboard')) {
    return 'cardboard-boxes';
  }

  if (normalizedName.includes('can') || normalizedName.includes('aluminum')) {
    return 'aluminum-can';
  }

  return 'plastic-bottle';
}

function buildSections(scans: RecentScan[]) {
  const now = new Date();
  const sections = new Map<string, ScanHistorySection>();

  scans.forEach((scan, index) => {
    const scannedDate = toValidDate(scan.scannedAt);
    const sectionId = scannedDate ? getDayKey(scannedDate) : `unknown-${index}`;

    if (!sections.has(sectionId)) {
      sections.set(sectionId, {
        id: sectionId,
        title: scannedDate ? getSectionTitle(scannedDate, now) : 'Earlier',
        items: [],
      });
    }

    sections.get(sectionId)?.items.push({
      id: scan.id,
      itemName: scan.finalItem,
      disposalLabel: scan.disposalLabel,
      scannedAtLabel: formatScanTime(scan.scannedAt),
      imageUri: scan.imageUri,
      disposalStatus: scan.disposalStatus,
      thumbnailVariant: getFallbackThumbnailVariant(scan.finalItem),
    });
  });

  return Array.from(sections.values());
}

export default function RecentScansScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [recentScans, setRecentScans] = useState<RecentScan[]>([]);
  const [hasLoadedScans, setHasLoadedScans] = useState(false);
  const openSwipeableRef = useRef<Swipeable | null>(null);
  const swipeableRefs = useRef<Record<string, Swipeable | null>>({});

  useFocusEffect(
    useCallback(() => {
      let isActive = true;

      void (async () => {
        try {
          const storedScans = await getRecentScans();
          if (!isActive) {
            return;
          }

          setRecentScans(storedScans);
        } finally {
          if (isActive) {
            setHasLoadedScans(true);
          }
        }
      })();

      return () => {
        isActive = false;
      };
    }, [])
  );

  const handleSwipeableOpen = useCallback((swipeable: Swipeable) => {
    if (openSwipeableRef.current && openSwipeableRef.current !== swipeable) {
      openSwipeableRef.current.close();
    }

    openSwipeableRef.current = swipeable;
  }, []);

  const handleSwipeableClose = useCallback((swipeable: Swipeable) => {
    if (openSwipeableRef.current === swipeable) {
      openSwipeableRef.current = null;
    }
  }, []);

  const closeAllSwipeables = useCallback(() => {
    Object.values(swipeableRefs.current).forEach((swipeable) => {
      swipeable?.close();
    });

    openSwipeableRef.current = null;
    swipeableRefs.current = {};
  }, []);

  const handleDeleteScan = useCallback(
    async (scanId: string) => {
      const previousScans = recentScans;
      const swipeable = swipeableRefs.current[scanId];

      swipeable?.close();

      if (openSwipeableRef.current === swipeable) {
        openSwipeableRef.current = null;
      }

      setRecentScans((currentScans) => currentScans.filter((scan) => scan.id !== scanId));

      try {
        await deleteRecentScan(scanId);
      } catch {
        setRecentScans(previousScans);
        Alert.alert('Could not delete scan. Please try again.');
      } finally {
        delete swipeableRefs.current[scanId];
      }
    },
    [recentScans]
  );

  const handleConfirmClearAll = useCallback(async () => {
    const previousScans = recentScans;

    closeAllSwipeables();
    setRecentScans([]);

    try {
      await clearRecentScans();
    } catch {
      setRecentScans(previousScans);
      Alert.alert('Could not clear scans. Please try again.');
    }
  }, [closeAllSwipeables, recentScans]);

  const handleClearAllPress = useCallback(() => {
    Alert.alert(
      'Clear all scans?',
      'This will remove your recent scan history from this device.',
      [
        {
          style: 'cancel',
          text: 'Cancel',
        },
        {
          style: 'destructive',
          text: 'Clear All',
          onPress: () => {
            void handleConfirmClearAll();
          },
        },
      ]
    );
  }, [handleConfirmClearAll]);

  const renderRightActions = useCallback(
    (scanId: string) => (
      <Pressable
        accessibilityLabel="Delete recent scan"
        accessibilityRole="button"
        onPress={() => {
          void handleDeleteScan(scanId);
        }}
        style={({ pressed }) => [styles.deleteAction, pressed && styles.deleteActionPressed]}>
        <Ionicons color="#FFFFFF" name="trash-outline" size={28} />
      </Pressable>
    ),
    [handleDeleteScan]
  );

  const sections = buildSections(recentScans);

  return (
    <SafeAreaView edges={['top']} style={styles.page}>

      <ScrollView
        contentContainerStyle={[
          styles.content,
          { paddingBottom: insets.bottom + BOTTOM_NAV_BAR_HEIGHT + 26 },
        ]}
        showsVerticalScrollIndicator={false}>
        <View style={styles.header}>
          <View style={styles.headerTopRow}>
            <Text style={styles.title}>scans.</Text>
            {recentScans.length > 0 ? (
              <Pressable
                accessibilityLabel="Clear all recent scans"
                accessibilityRole="button"
                onPress={handleClearAllPress}
                style={({ pressed }) => [
                  styles.clearAllButton,
                  pressed && styles.clearAllButtonPressed,
                ]}>
                <Text style={styles.clearAllText}>Clear All</Text>
              </Pressable>
            ) : null}
          </View>
          <Text style={styles.subtitle}>{getMonthlySummary(recentScans)}</Text>
        </View>

        {sections.map((section) => (
          <View key={section.id} style={styles.section}>
            <Text style={styles.sectionTitle}>{section.title}</Text>

            <View style={styles.cardStack}>
              {section.items.map((item) => (
                <Swipeable
                  containerStyle={styles.swipeableContainer}
                  friction={2}
                  key={item.id}
                  onSwipeableClose={(_direction, swipeable) => {
                    handleSwipeableClose(swipeable);
                  }}
                  onSwipeableOpen={(direction, swipeable) => {
                    if (direction === 'right') {
                      handleSwipeableOpen(swipeable);
                    }
                  }}
                  overshootRight={false}
                  ref={(ref) => {
                    swipeableRefs.current[item.id] = ref;
                  }}
                  renderRightActions={() => renderRightActions(item.id)}
                  rightThreshold={56}>
                  <ScanHistoryCard
                    item={item}
                    onPress={() => {
                      closeAllSwipeables();
                      router.push({
                        pathname: '/recent-scan/[id]',
                        params: { id: item.id },
                      });
                    }}
                  />
                </Swipeable>
              ))}
            </View>
          </View>
        ))}

        {hasLoadedScans && sections.length === 0 ? (
          <View style={styles.emptyState}>
            <Text style={styles.emptyTitle}>No recent scans yet.</Text>
            <Text style={styles.emptySubtitle}>Scan an item to build your history.</Text>
          </View>
        ) : null}
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
    gap: 24,
    paddingHorizontal: 18,
    paddingTop: 12,
  },
  header: {
    gap: 10,
    paddingTop: 4,
  },
  headerTopRow: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  title: {
    color: '#050505',
    fontSize: 34,
    fontWeight: '900',
    letterSpacing: -1.3,
    ...PRIMARY_TEXT_STYLES.header,
  },
  clearAllButton: {
    alignItems: 'center',
    backgroundColor: '#ECE8E2',
    borderRadius: 999,
    justifyContent: 'center',
    minHeight: 44,
    paddingHorizontal: 12,
    paddingVertical: 7,
  },
  clearAllButtonPressed: {
    opacity: 0.82,
  },
  clearAllText: {
    color: '#6F6962',
    fontSize: 12,
    fontWeight: '800',
    letterSpacing: 0.2,
    ...PRIMARY_TEXT_STYLES.button,
  },
  subtitle: {
    color: '#898783',
    fontSize: 14,
    lineHeight: 20,
    maxWidth: 260,
    ...SECONDARY_TEXT_STYLES.regular,
  },
  section: {
    gap: 14,
  },
  sectionTitle: {
    color: '#817C76',
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 3.2,
    paddingHorizontal: 16,
    textTransform: 'uppercase',
    ...PRIMARY_TEXT_STYLES.label,
  },
  cardStack: {
    gap: 14,
  },
  swipeableContainer: {
    borderRadius: 28,
  },
  deleteAction: {
    alignItems: 'center',
    backgroundColor: '#F24747',
    borderRadius: 28,
    justifyContent: 'center',
    marginLeft: 12,
    minHeight: 102,
    width: 96,
  },
  deleteActionPressed: {
    opacity: 0.88,
  },
  emptyState: {
    backgroundColor: '#FFFFFF',
    borderColor: '#ECE8E2',
    borderRadius: 28,
    borderWidth: 1,
    gap: 8,
    paddingHorizontal: 22,
    paddingVertical: 24,
    shadowColor: '#111827',
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.06,
    shadowRadius: 16,
  },
  emptyTitle: {
    color: '#050505',
    fontSize: 18,
    fontWeight: '800',
    letterSpacing: -0.4,
    ...PRIMARY_TEXT_STYLES.title,
  },
  emptySubtitle: {
    color: '#898783',
    fontSize: 14,
    lineHeight: 20,
    ...SECONDARY_TEXT_STYLES.regular,
  },
});
