import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';

import { PRIMARY_TEXT_STYLES, SECONDARY_TEXT_STYLES } from '@/constants/typography';

export default function PrivacyTermsScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();

  return (
    <SafeAreaView edges={['top']} style={styles.page}>
      <View style={styles.header}>
        <Pressable
          accessibilityLabel="Back to Profile"
          accessibilityRole="button"
          hitSlop={8}
          onPress={() => router.back()}
          style={({ pressed }) => [styles.backButton, pressed && styles.pressed]}
        >
          <Ionicons color="#20201E" name="arrow-back" size={22} />
        </Pressable>
        <Text style={styles.headerTitle}>Privacy & Terms</Text>
        <View style={styles.headerSpacer} />
      </View>

      <ScrollView
        contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + 28 }]}
        showsVerticalScrollIndicator={false}
      >
        <Text style={styles.title}>Privacy & Terms</Text>
        <View style={styles.notice}>
          <Ionicons color="#765A26" name="information-circle-outline" size={21} />
          <Text style={styles.noticeText}>
            Placeholder information only. Final legal text will be added before release.
          </Text>
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Privacy</Text>
          <Text style={styles.cardBody}>
            Placeholder: describe what Green Bin collects, how local scan history is handled, and
            how users can manage their information.
          </Text>
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Terms</Text>
          <Text style={styles.cardBody}>
            Placeholder: describe acceptable use, recycling-guidance limitations, and applicable
            service terms.
          </Text>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  page: { backgroundColor: '#F3F1EE', flex: 1 },
  header: {
    alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between',
    minHeight: 58, paddingHorizontal: 18,
  },
  backButton: {
    alignItems: 'center', backgroundColor: '#FFFFFF', borderColor: '#E5E0D9',
    borderRadius: 999, borderWidth: 1, height: 42, justifyContent: 'center', width: 42,
  },
  pressed: { opacity: 0.72 },
  headerTitle: { color: '#242220', fontSize: 16, ...PRIMARY_TEXT_STYLES.label },
  headerSpacer: { width: 42 },
  content: { gap: 16, paddingHorizontal: 18, paddingTop: 20 },
  title: { color: '#050505', fontSize: 30, letterSpacing: -1, ...PRIMARY_TEXT_STYLES.header },
  notice: {
    alignItems: 'flex-start', backgroundColor: '#FFF9ED', borderColor: '#EBCF96',
    borderRadius: 18, borderWidth: 1, flexDirection: 'row', gap: 10, padding: 14,
  },
  noticeText: { color: '#765A26', flex: 1, fontSize: 12, lineHeight: 18, ...SECONDARY_TEXT_STYLES.semiBold },
  card: {
    backgroundColor: '#FFFFFF', borderColor: '#E7E2DB', borderRadius: 24,
    borderWidth: 1, gap: 9, padding: 18,
  },
  cardTitle: { color: '#1B1A18', fontSize: 17, ...PRIMARY_TEXT_STYLES.title },
  cardBody: { color: '#746F69', fontSize: 13, lineHeight: 20, ...SECONDARY_TEXT_STYLES.regular },
});
