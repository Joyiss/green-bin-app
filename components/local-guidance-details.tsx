import { Ionicons } from '@expo/vector-icons';
import { Alert, Linking, Pressable, StyleSheet, Text, View } from 'react-native';

import type { LocalGuidance } from '@/api/contracts';
import { PRIMARY_TEXT_STYLES, SECONDARY_TEXT_STYLES } from '@/constants/typography';

function formatFee(amount: number, currency: string | null) {
  if (currency === 'USD') {
    return `$${amount.toFixed(amount % 1 === 0 ? 0 : 2)}`;
  }
  return `${amount}${currency ? ` ${currency}` : ''}`;
}

export function LocalGuidanceDetails({
  guidance,
}: {
  guidance: LocalGuidance;
}) {
  const fees = guidance.fees?.line_items ?? [];
  const primarySource = guidance.sources[0];

  return (
    <View style={styles.section}>
      <View style={styles.headingRow}>
        <Ionicons color="#2F6B52" name="shield-checkmark-outline" size={17} />
        <Text style={styles.heading}>Based on Forsyth County guidance</Text>
      </View>

      {fees.length ? (
        <View style={styles.group}>
          <Text style={styles.label}>FEES</Text>
          {fees.map((fee) => (
            <Text key={`${fee.label}-${fee.unit}`} selectable style={styles.value}>
              {fee.label}: {formatFee(fee.amount, guidance.fees?.currency ?? null)} / {fee.unit}
            </Text>
          ))}
        </View>
      ) : null}

      {guidance.allowed_location_names.length ? (
        <View style={styles.group}>
          <Text style={styles.label}>DESTINATION</Text>
          <Text selectable style={styles.value}>
            {guidance.allowed_location_names.join(', ')}
          </Text>
        </View>
      ) : null}

      {primarySource?.url ? (
        <Pressable
          accessibilityRole="link"
          onPress={() => {
            Linking.openURL(primarySource.url).catch(() => {
              Alert.alert(
                'Unable to open source',
                'Try opening the official guidance source in your browser.',
              );
            });
          }}
          style={({ pressed }) => [styles.sourceLink, pressed && styles.pressed]}>
          <Ionicons color="#2F6B52" name="open-outline" size={15} />
          <Text style={styles.sourceText}>{primarySource.title}</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  section: {
    borderTopColor: '#E6E1DA',
    borderTopWidth: 1,
    gap: 10,
    paddingTop: 12,
  },
  headingRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 7,
  },
  heading: {
    color: '#2F6B52',
    flex: 1,
    fontSize: 14,
    fontWeight: '800',
    ...PRIMARY_TEXT_STYLES.title,
  },
  group: {
    gap: 3,
  },
  label: {
    color: '#9A948C',
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 0,
    ...PRIMARY_TEXT_STYLES.label,
  },
  value: {
    color: '#66605B',
    fontSize: 14,
    lineHeight: 20,
    ...SECONDARY_TEXT_STYLES.regular,
  },
  sourceLink: {
    alignItems: 'center',
    alignSelf: 'flex-start',
    flexDirection: 'row',
    gap: 6,
    paddingVertical: 3,
  },
  sourceText: {
    color: '#2F6B52',
    flexShrink: 1,
    fontSize: 13,
    fontWeight: '700',
    ...SECONDARY_TEXT_STYLES.bold,
  },
  pressed: {
    opacity: 0.7,
  },
});
