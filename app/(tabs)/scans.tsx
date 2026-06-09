import { useFocusEffect } from '@react-navigation/native';
import { StatusBar } from 'expo-status-bar';
import { useCallback, useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';

import { BOTTOM_NAV_BAR_HEIGHT } from '@/components/bottom-nav-bar';
import {
  ScanHistoryCard,
  type ScanHistoryCardItem,
  type ScanHistoryCardThumbnailVariant,
} from '@/components/scan-history-card';
import { getRecentScans, type RecentScan } from '../../storage/recentScans';

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
      thumbnailVariant: getFallbackThumbnailVariant(scan.finalItem),
    });
  });

  return Array.from(sections.values());
}

export default function RecentScansScreen() {
  const insets = useSafeAreaInsets();
  const [recentScans, setRecentScans] = useState<RecentScan[]>([]);
  const [hasLoadedScans, setHasLoadedScans] = useState(false);

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

  const sections = buildSections(recentScans);

  return (
    <SafeAreaView edges={['top']} style={styles.page}>
      <StatusBar style="dark" />

      <ScrollView
        contentContainerStyle={[
          styles.content,
          { paddingBottom: insets.bottom + BOTTOM_NAV_BAR_HEIGHT + 26 },
        ]}
        showsVerticalScrollIndicator={false}>
        <View style={styles.header}>
          <Text style={styles.title}>scans.</Text>
          <Text style={styles.subtitle}>{getMonthlySummary(recentScans)}</Text>
        </View>

        {sections.map((section) => (
          <View key={section.id} style={styles.section}>
            <Text style={styles.sectionTitle}>{section.title}</Text>

            <View style={styles.cardStack}>
              {section.items.map((item) => (
                <ScanHistoryCard item={item} key={item.id} />
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
  title: {
    color: '#050505',
    fontSize: 34,
    fontWeight: '900',
    letterSpacing: -1.3,
  },
  subtitle: {
    color: '#898783',
    fontSize: 14,
    lineHeight: 20,
    maxWidth: 260,
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
  },
  cardStack: {
    gap: 14,
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
  },
  emptySubtitle: {
    color: '#898783',
    fontSize: 14,
    lineHeight: 20,
  },
});
