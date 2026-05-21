import { Ionicons } from '@expo/vector-icons';
import type { ReactNode } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

type ResultSheetProps = {
  label: string;
  title: string;
  materialTag?: string | null;
  summary: string;
  steps: string[];
  buttonLabel?: string;
  buttonIconName?: keyof typeof Ionicons.glyphMap;
  onButtonPress?: () => void;
  children?: ReactNode;
};

export function ResultSheet({
  label,
  title,
  materialTag,
  summary,
  steps,
  buttonLabel,
  buttonIconName = 'location-outline',
  onButtonPress,
  children,
}: ResultSheetProps) {
  return (
    <View style={styles.sheet}>
      <View style={styles.handle} />
      <Text style={styles.eyebrow}>{label}</Text>
      <Text style={styles.title}>{title}</Text>
      {materialTag ? (
        <View style={styles.tag}>
          <Ionicons color="#5B6470" name="leaf-outline" size={14} />
          <Text style={styles.tagText}>{materialTag}</Text>
        </View>
      ) : null}
      <Text style={styles.summary}>{summary}</Text>

      {steps.length ? (
        <View style={styles.steps}>
          {steps.map((step, index) => (
            <View key={step} style={styles.stepRow}>
              <View style={styles.stepIndex}>
                <Text style={styles.stepIndexText}>{index + 1}</Text>
              </View>
              <Text style={styles.stepText}>{step}</Text>
            </View>
          ))}
        </View>
      ) : null}

      {children}

      {buttonLabel && onButtonPress ? (
        <Pressable onPress={onButtonPress} style={styles.button}>
          <Ionicons color="#FFFFFF" name={buttonIconName} size={18} />
          <Text style={styles.buttonText}>{buttonLabel}</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  sheet: {
    backgroundColor: '#FFFEFC',
    borderRadius: 32,
    gap: 14,
    paddingHorizontal: 18,
    paddingTop: 12,
    paddingBottom: 18,
    shadowColor: '#0F172A',
    shadowOffset: { width: 0, height: 16 },
    shadowOpacity: 0.12,
    shadowRadius: 24,
  },
  handle: {
    alignSelf: 'center',
    backgroundColor: '#E6E1DA',
    borderRadius: 999,
    height: 5,
    marginBottom: 6,
    width: 38,
  },
  eyebrow: {
    color: '#9A948C',
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 2,
    textAlign: 'center',
  },
  title: {
    color: '#050505',
    fontSize: 34,
    fontWeight: '900',
    letterSpacing: -1.4,
    textAlign: 'center',
  },
  tag: {
    alignItems: 'center',
    alignSelf: 'center',
    borderColor: '#E8E2DA',
    borderRadius: 999,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 6,
    paddingHorizontal: 12,
    paddingVertical: 6,
  },
  tagText: {
    color: '#4E5661',
    fontSize: 12,
    fontWeight: '700',
  },
  summary: {
    color: '#66605B',
    fontSize: 14,
    lineHeight: 21,
    textAlign: 'center',
  },
  steps: {
    gap: 14,
    marginTop: 4,
  },
  stepRow: {
    flexDirection: 'row',
    gap: 12,
  },
  stepIndex: {
    alignItems: 'center',
    borderColor: '#E4DED7',
    borderRadius: 999,
    borderWidth: 1,
    height: 22,
    justifyContent: 'center',
    marginTop: 2,
    width: 22,
  },
  stepIndexText: {
    color: '#8B857F',
    fontSize: 11,
    fontWeight: '700',
  },
  stepText: {
    color: '#736C65',
    flex: 1,
    fontSize: 15,
    lineHeight: 23,
  },
  button: {
    alignItems: 'center',
    backgroundColor: '#050505',
    borderRadius: 999,
    flexDirection: 'row',
    gap: 8,
    justifyContent: 'center',
    marginTop: 8,
    paddingVertical: 17,
  },
  buttonText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '800',
  },
});
