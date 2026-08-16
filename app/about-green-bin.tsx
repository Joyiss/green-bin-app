import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';

import { PRIMARY_TEXT_STYLES, SECONDARY_TEXT_STYLES } from '@/constants/typography';

export default function AboutGreenBinScreen() {
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
        <Text style={styles.headerTitle}>About</Text>
        <View style={styles.headerSpacer} />
      </View>

      <ScrollView
        contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + 28 }]}
        showsVerticalScrollIndicator={false}
      >
        <Text style={styles.title}>About Green Bin & Developer</Text>
        <Text style={styles.intro}>
          More information about the app and its creator will be added here.
        </Text>

        <View style={styles.card}>
          <View style={styles.icon}>
            <Ionicons color="#2E6B47" name="leaf-outline" size={23} />
          </View>
          <View style={styles.cardText}>
            <Text style={styles.cardTitle}>About Green Bin</Text>
            <Text style={styles.cardBody}>
              Placeholder: app mission, recycling guidance approach, and supported communities.
            </Text>
          </View>
        </View>

        <View style={styles.card}>
          <View style={styles.icon}>
            <Ionicons color="#2E6B47" name="code-slash-outline" size={23} />
          </View>
          <View style={styles.cardText}>
            <Text style={styles.cardTitle}>About the Developer</Text>
            <Text style={styles.cardBody}>
              Placeholder: developer biography, project background, and future contact links.
            </Text>
          </View>
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
  intro: { color: '#77716B', fontSize: 14, lineHeight: 21, ...SECONDARY_TEXT_STYLES.regular },
  card: {
    alignItems: 'flex-start', backgroundColor: '#FFFFFF', borderColor: '#E7E2DB',
    borderRadius: 24, borderWidth: 1, flexDirection: 'row', gap: 13, padding: 18,
  },
  icon: {
    alignItems: 'center', backgroundColor: '#EEF3EB', borderRadius: 15,
    height: 44, justifyContent: 'center', width: 44,
  },
  cardText: { flex: 1, gap: 7 },
  cardTitle: { color: '#1B1A18', fontSize: 16, ...PRIMARY_TEXT_STYLES.title },
  cardBody: { color: '#746F69', fontSize: 13, lineHeight: 20, ...SECONDARY_TEXT_STYLES.regular },
});
