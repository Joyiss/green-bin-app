import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { Image, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';

import { PRIMARY_TEXT_STYLES, SECONDARY_TEXT_STYLES } from '@/constants/typography';

export default function AboutGreenBinScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();

  return (
    <SafeAreaView edges={['top']} style={styles.page}>
      <View style={styles.header}>
        <Pressable
          accessibilityLabel="Close About Green Bin"
          accessibilityRole="button"
          hitSlop={8}
          onPress={() => router.back()}
          style={({ pressed }) => [styles.closeButton, pressed && styles.pressed]}
        >
          <Ionicons color="#242220" name="close" size={24} />
        </Pressable>
      </View>

      <ScrollView
        contentContainerStyle={[
          styles.scrollContent,
          { paddingBottom: Math.max(insets.bottom, 20) + 32 },
        ]}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.content}>
          <Image
            accessibilityLabel="Portrait of Rakshan"
            resizeMode="cover"
            source={require('../assets/images/rakshan.jpg')}
            style={styles.portrait}
          />

          <View style={styles.copy}>
            <Text style={styles.greeting}>Hi, I’m Rakshan 👋</Text>

            <Text style={styles.paragraph}>
              I built Green Bin because figuring out where something goes shouldn’t feel like a
              guessing game.
            </Text>

            <Text style={styles.paragraph}>
              After seeing litter on my way to school, I wondered if I could build something that
              made proper disposal a little easier. So now you can snap a photo and let Green Bin
              help with the confusing part ♻️
            </Text>

            <Text style={styles.paragraph}>
              I’m a high school student who loves building with AI, opens way too many browser tabs,
              and hopes this app helps one less item end up in the wrong bin :)
            </Text>

            <Text style={styles.paragraph}>Thanks for giving Green Bin a try!</Text>
          </View>
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
  header: {
    alignItems: 'flex-end',
    minHeight: 58,
    paddingHorizontal: 18,
    paddingTop: 8,
  },
  closeButton: {
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    borderColor: '#E5E0D9',
    borderRadius: 999,
    borderWidth: 1,
    height: 46,
    justifyContent: 'center',
    shadowColor: '#111827',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.06,
    shadowRadius: 10,
    width: 46,
  },
  pressed: {
    opacity: 0.72,
  },
  scrollContent: {
    paddingHorizontal: 24,
    paddingTop: 14,
  },
  content: {
    alignSelf: 'center',
    maxWidth: 620,
    width: '100%',
  },
  portrait: {
    alignSelf: 'center',
    borderRadius: 68,
    height: 136,
    marginBottom: 42,
    marginTop: 12,
    width: 136,
  },
  copy: {
    gap: 22,
  },
  greeting: {
    color: '#171614',
    fontSize: 21,
    letterSpacing: -0.25,
    lineHeight: 30,
    ...PRIMARY_TEXT_STYLES.label,
  },
  paragraph: {
    color: '#292724',
    fontSize: 17,
    lineHeight: 28,
    ...SECONDARY_TEXT_STYLES.regular,
  },
});
