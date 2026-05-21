import { Pressable, StyleSheet, Text } from 'react-native';

type SearchChipProps = {
  label: string;
  isActive: boolean;
};

export function SearchChip({ label, isActive }: SearchChipProps) {
  return (
    <Pressable style={[styles.chip, isActive && styles.chipActive]}>
      <Text style={[styles.text, isActive && styles.textActive]}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  chip: {
    backgroundColor: '#FFFFFF',
    borderColor: '#E7E4DE',
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: 14,
    paddingVertical: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  chipActive: {
    backgroundColor: '#050505',
    borderColor: '#050505',
  },
  text: {
    color: '#9A938C',
    fontSize: 12,
    fontWeight: '700',
    textAlign: 'center',
  },
  textActive: {
    color: '#FFFFFF',
  },
});
