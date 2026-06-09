import { LinearGradient } from 'expo-linear-gradient';
import { StatusBar } from 'expo-status-bar';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';

import { BOTTOM_NAV_BAR_HEIGHT } from '@/components/bottom-nav-bar';
import { ProfileSectionCard } from '@/components/profile-section-card';
import {
  mockProfileSections,
  mockProfileStats,
  mockProfileSummary,
} from '@/constants/mock-data';

export default function ProfileScreen() {
  const insets = useSafeAreaInsets();

  return (
    <SafeAreaView edges={['top']} style={styles.page}>
      <StatusBar style="dark" />

      <ScrollView
        contentContainerStyle={[
          styles.content,
          { paddingBottom: insets.bottom + BOTTOM_NAV_BAR_HEIGHT + 30 },
        ]}
        showsVerticalScrollIndicator={false}>
        <View style={styles.header}>
          <View style={styles.headerTextBlock}>
            <Text style={styles.title}>profile.</Text>
            <Text style={styles.subtitle}>
              A polished placeholder for future account, sync, and privacy settings.
            </Text>
          </View>

          <View style={styles.placeholderPill}>
            <Text style={styles.placeholderPillText}>{mockProfileSummary.placeholderBadge}</Text>
          </View>
        </View>

        <View style={styles.heroCard}>
          <View style={styles.heroTopRow}>
            <LinearGradient
              colors={['#A6D7A1', '#6DB07A']}
              end={{ x: 1, y: 1 }}
              start={{ x: 0, y: 0 }}
              style={styles.avatar}>
              <Text style={styles.avatarText}>{mockProfileSummary.initials}</Text>
            </LinearGradient>

            <View style={styles.heroTextBlock}>
              <Text style={styles.heroName}>{mockProfileSummary.name}</Text>
              <Text style={styles.heroEmail}>{mockProfileSummary.email}</Text>
              <View style={styles.membershipPill}>
                <Text style={styles.membershipPillText}>{mockProfileSummary.membershipLabel}</Text>
              </View>
            </View>
          </View>

          <Text style={styles.heroMessage}>{mockProfileSummary.statusMessage}</Text>
        </View>

        <View style={styles.statsSection}>
          <Text style={styles.sectionLabel}>Scan Stats</Text>

          <View style={styles.statsRow}>
            {mockProfileStats.map((stat) => (
              <View key={stat.id} style={styles.statCard}>
                <Text style={styles.statValue}>{stat.value}</Text>
                <Text style={styles.statLabel}>{stat.label}</Text>
                <Text style={styles.statCaption}>{stat.caption}</Text>
              </View>
            ))}
          </View>
        </View>

        {mockProfileSections.map((section) => (
          <ProfileSectionCard key={section.id} options={section.options} title={section.title} />
        ))}

        <View style={styles.footnoteCard}>
          <Text style={styles.footnoteText}>{mockProfileSummary.footnote}</Text>
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
    gap: 10,
  },
  headerTextBlock: {
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
    maxWidth: 280,
  },
  placeholderPill: {
    alignSelf: 'flex-start',
    backgroundColor: '#EBE7E1',
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 7,
  },
  placeholderPillText: {
    color: '#5B5650',
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 1.1,
    textTransform: 'uppercase',
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
  avatar: {
    alignItems: 'center',
    borderRadius: 24,
    height: 60,
    justifyContent: 'center',
    width: 60,
  },
  avatarText: {
    color: '#15311A',
    fontSize: 20,
    fontWeight: '900',
    letterSpacing: -0.8,
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
  membershipPill: {
    alignSelf: 'flex-start',
    backgroundColor: '#F4F1EC',
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  membershipPillText: {
    color: '#4F4A44',
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  heroMessage: {
    color: '#66605B',
    fontSize: 14,
    lineHeight: 20,
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
  statsRow: {
    flexDirection: 'row',
    gap: 8,
  },
  statCard: {
    backgroundColor: '#FFFFFF',
    borderColor: '#E9E5DF',
    borderRadius: 20,
    borderWidth: 1,
    flex: 1,
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
  footnoteCard: {
    backgroundColor: '#F7F4EF',
    borderColor: '#E6E1DA',
    borderRadius: 20,
    borderStyle: 'dashed',
    borderWidth: 1,
    paddingHorizontal: 16,
    paddingVertical: 14,
  },
  footnoteText: {
    color: '#746F69',
    fontSize: 12,
    lineHeight: 18,
  },
});
