import { Ionicons } from '@expo/vector-icons';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import type { MockProfileOption } from '@/constants/mock-data';

type ProfileSectionCardProps = {
  title: string;
  options: MockProfileOption[];
};

export function ProfileSectionCard({ title, options }: ProfileSectionCardProps) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle}>{title}</Text>

      <View style={styles.card}>
        {options.map((option, index) => {
          const isLastItem = index === options.length - 1;

          return (
            <Pressable
              disabled
              key={option.id}
              style={({ pressed }) => [
                styles.row,
                !isLastItem && styles.rowDivider,
                pressed && styles.rowPressed,
              ]}>
              <View style={styles.iconBubble}>
                <Ionicons color="#1B1B1B" name={option.iconName} size={18} />
              </View>

              <View style={styles.textBlock}>
                <Text style={styles.rowTitle}>{option.title}</Text>
                <Text style={styles.rowDescription}>{option.description}</Text>
              </View>

              <View style={styles.trailing}>
                {option.value ? <Text style={styles.valueText}>{option.value}</Text> : null}
                {option.badge ? (
                  <View style={styles.badge}>
                    <Text style={styles.badgeText}>{option.badge}</Text>
                  </View>
                ) : null}
                <Ionicons color="#8D8A86" name="chevron-forward" size={18} />
              </View>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  section: {
    gap: 10,
  },
  sectionTitle: {
    color: '#807B75',
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 2.8,
    paddingHorizontal: 4,
    textTransform: 'uppercase',
  },
  card: {
    backgroundColor: '#FFFFFF',
    borderColor: '#E9E5DF',
    borderRadius: 24,
    borderWidth: 1,
    overflow: 'hidden',
    shadowColor: '#111827',
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.05,
    shadowRadius: 16,
  },
  row: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 12,
    paddingHorizontal: 16,
    paddingVertical: 14,
  },
  rowDivider: {
    borderBottomColor: '#F1EDE7',
    borderBottomWidth: 1,
  },
  rowPressed: {
    opacity: 0.9,
  },
  iconBubble: {
    alignItems: 'center',
    backgroundColor: '#F4F1EC',
    borderRadius: 14,
    height: 38,
    justifyContent: 'center',
    width: 38,
  },
  textBlock: {
    flex: 1,
    gap: 4,
  },
  rowTitle: {
    color: '#161616',
    fontSize: 15,
    fontWeight: '800',
    letterSpacing: -0.2,
  },
  rowDescription: {
    color: '#7B7670',
    fontSize: 12,
    lineHeight: 17,
  },
  trailing: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 8,
  },
  valueText: {
    color: '#8B857F',
    fontSize: 11,
    fontWeight: '700',
    textTransform: 'uppercase',
  },
  badge: {
    alignItems: 'center',
    backgroundColor: '#F4F1EC',
    borderRadius: 999,
    justifyContent: 'center',
    paddingHorizontal: 10,
    paddingVertical: 5,
  },
  badgeText: {
    color: '#4A4743',
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 0.4,
    textTransform: 'uppercase',
  },
});
