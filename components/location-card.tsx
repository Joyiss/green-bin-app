import { Ionicons } from '@expo/vector-icons';
import { Pressable, StyleSheet, Text, View } from 'react-native';

export type LocationCardProps = {
  type: string;
  name: string;
  address: string;
  status: string;
  distance: string;
  accent: string;
  mapStyle: 'grid' | 'building' | 'pin';
  onPress?: () => void;
};

function MapPreview({ accent, mapStyle }: { accent: string; mapStyle: LocationCardProps['mapStyle'] }) {
  if (mapStyle === 'building') {
    return (
      <View style={styles.previewFrame}>
        <View style={[styles.previewSky, { backgroundColor: '#D7E6EF' }]} />
        <View style={styles.previewBuildingBase} />
        <View style={[styles.previewBuildingSign, { backgroundColor: accent }]} />
      </View>
    );
  }

  return (
    <View style={[styles.previewFrame, styles.previewMap]}>
      <View style={styles.previewCurveOne} />
      <View style={styles.previewCurveTwo} />
      <View style={[styles.previewPin, { backgroundColor: accent }]} />
    </View>
  );
}

export function LocationCard({
  type,
  name,
  address,
  status,
  distance,
  accent,
  mapStyle,
  onPress,
}: LocationCardProps) {
  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <View style={styles.headerText}>
          <View style={styles.typeRow}>
            <Text style={styles.type}>{type.toUpperCase()}</Text>
            <View style={[styles.dot, { backgroundColor: accent }]} />
          </View>
          <Text style={styles.name}>{name}</Text>
          <Text style={styles.address}>{address}</Text>
        </View>
        <MapPreview accent={accent} mapStyle={mapStyle} />
      </View>

      <View style={styles.metaRow}>
        <View style={styles.metaItem}>
          <Ionicons color="#AAADB3" name="time-outline" size={14} />
          <Text style={styles.metaText}>{status}</Text>
        </View>
        <View style={styles.metaItem}>
          <Ionicons color="#AAADB3" name="navigate-outline" size={14} />
          <Text style={styles.metaText}>{distance}</Text>
        </View>
      </View>

      <Pressable
        disabled={!onPress}
        onPress={onPress}
        style={[styles.button, !onPress && styles.buttonDisabled]}>
        <Text style={styles.buttonText}>Go</Text>
        <Ionicons color="#FFFFFF" name="compass-outline" size={14} />
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#FFFFFF',
    borderColor: '#E6E3DE',
    borderRadius: 28,
    borderWidth: 1,
    gap: 18,
    padding: 18,
    shadowColor: '#111827',
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.05,
    shadowRadius: 18,
  },
  header: {
    flexDirection: 'row',
    gap: 14,
  },
  headerText: {
    flex: 1,
    gap: 6,
  },
  typeRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 6,
  },
  type: {
    color: '#B1ACA5',
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 1.2,
  },
  dot: {
    borderRadius: 999,
    height: 6,
    width: 6,
  },
  name: {
    color: '#171717',
    fontSize: 16,
    fontWeight: '800',
    lineHeight: 22,
  },
  address: {
    color: '#78726C',
    fontSize: 14,
    lineHeight: 20,
  },
  metaRow: {
    flexDirection: 'row',
    gap: 18,
  },
  metaItem: {
    alignItems: 'center',
    flexDirection: 'row',
    flexShrink: 1,
    gap: 6,
  },
  metaText: {
    color: '#89847E',
    flexShrink: 1,
    fontSize: 12,
    fontWeight: '600',
  },
  button: {
    alignItems: 'center',
    backgroundColor: '#050505',
    borderRadius: 999,
    flexDirection: 'row',
    gap: 8,
    justifyContent: 'center',
    paddingVertical: 14,
  },
  buttonDisabled: {
    opacity: 0.7,
  },
  buttonText: {
    color: '#FFFFFF',
    fontSize: 15,
    fontWeight: '800',
  },
  previewFrame: {
    borderRadius: 16,
    height: 56,
    overflow: 'hidden',
    width: 56,
  },
  previewMap: {
    backgroundColor: '#EFF3F6',
  },
  previewCurveOne: {
    backgroundColor: '#D5DEE6',
    borderRadius: 10,
    height: 70,
    left: 18,
    position: 'absolute',
    top: -10,
    transform: [{ rotate: '28deg' }],
    width: 12,
  },
  previewCurveTwo: {
    backgroundColor: '#DCE6EC',
    borderRadius: 10,
    height: 12,
    left: -4,
    position: 'absolute',
    top: 18,
    transform: [{ rotate: '-18deg' }],
    width: 72,
  },
  previewPin: {
    borderRadius: 999,
    height: 14,
    left: 31,
    position: 'absolute',
    top: 16,
    width: 14,
  },
  previewSky: {
    height: 28,
  },
  previewBuildingBase: {
    backgroundColor: '#8F6E55',
    height: 28,
  },
  previewBuildingSign: {
    borderRadius: 4,
    height: 8,
    left: 10,
    position: 'absolute',
    top: 24,
    width: 36,
  },
});
