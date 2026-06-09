import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import { Image, Pressable, StyleSheet, Text, View } from 'react-native';

export type ScanHistoryCardThumbnailVariant =
  | 'plastic-bottle'
  | 'cardboard-boxes'
  | 'aluminum-can';

export type ScanHistoryCardItem = {
  id: string;
  itemName: string;
  disposalLabel: string;
  scannedAtLabel: string;
  imageUri?: string | null;
  thumbnailVariant?: ScanHistoryCardThumbnailVariant;
};

function ScanThumbnail({ variant }: { variant: ScanHistoryCardThumbnailVariant }) {
  return (
    <LinearGradient
      colors={['#F7F7F7', '#ECECEC']}
      end={{ x: 0.9, y: 1 }}
      start={{ x: 0.15, y: 0 }}
      style={styles.thumbnailTile}>
      {variant === 'plastic-bottle' ? (
        <View style={styles.bottleWrap}>
          <View style={styles.bottleCap} />
          <LinearGradient
            colors={['rgba(255,255,255,0.98)', 'rgba(219,226,235,0.9)']}
            end={{ x: 1, y: 0.9 }}
            start={{ x: 0, y: 0.1 }}
            style={styles.bottleBody}
          />
          <View style={styles.bottleCrushOne} />
          <View style={styles.bottleCrushTwo} />
        </View>
      ) : null}

      {variant === 'cardboard-boxes' ? (
        <View style={styles.cardboardStack}>
          {Array.from({ length: 5 }).map((_, index) => (
            <View
              key={`box-layer-${index}`}
              style={[
                styles.cardboardLayer,
                {
                  top: 12 + index * 7,
                  width: 40 + index * 2,
                },
              ]}
            />
          ))}
        </View>
      ) : null}

      {variant === 'aluminum-can' ? (
        <View style={styles.canWrap}>
          <LinearGradient
            colors={['#E7E7E7', '#A8A8A8', '#F8F8F8', '#8E8E8E']}
            locations={[0, 0.26, 0.63, 1]}
            style={styles.canBody}
          />
          <View style={styles.canTop} />
          <View style={styles.canBottomShadow} />
        </View>
      ) : null}
    </LinearGradient>
  );
}

export function ScanHistoryCard({ item }: { item: ScanHistoryCardItem }) {
  return (
    <Pressable disabled style={({ pressed }) => [styles.card, pressed && styles.cardPressed]}>
      <View style={styles.thumbnailWrap}>
        {item.imageUri ? (
          <Image source={{ uri: item.imageUri }} style={styles.thumbnailImage} />
        ) : (
          <ScanThumbnail variant={item.thumbnailVariant ?? 'plastic-bottle'} />
        )}
      </View>

      <View style={styles.content}>
        <Text numberOfLines={2} style={styles.itemName}>
          {item.itemName}
        </Text>

        <View style={styles.metaRow}>
          <View style={styles.badge}>
            <Text style={styles.badgeText}>{item.disposalLabel}</Text>
          </View>
          <Text style={styles.timeText}>{item.scannedAtLabel}</Text>
        </View>
      </View>

      <View style={styles.chevronButton}>
        <Ionicons color="#181818" name="chevron-forward" size={22} />
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    borderColor: '#ECE8E2',
    borderRadius: 28,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 12,
    minHeight: 102,
    paddingHorizontal: 14,
    paddingVertical: 14,
    shadowColor: '#111827',
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.06,
    shadowRadius: 16,
  },
  cardPressed: {
    opacity: 0.92,
  },
  thumbnailWrap: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  thumbnailImage: {
    borderRadius: 20,
    height: 64,
    width: 64,
  },
  thumbnailTile: {
    borderRadius: 20,
    height: 64,
    overflow: 'hidden',
    width: 64,
  },
  content: {
    flex: 1,
    gap: 8,
    justifyContent: 'center',
  },
  itemName: {
    color: '#050505',
    fontSize: 16,
    fontWeight: '800',
    letterSpacing: -0.35,
    lineHeight: 22,
  },
  metaRow: {
    alignItems: 'center',
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
  },
  badge: {
    alignItems: 'center',
    backgroundColor: '#050505',
    borderRadius: 999,
    justifyContent: 'center',
    paddingHorizontal: 12,
    paddingVertical: 6,
  },
  badgeText: {
    color: '#FFFFFF',
    fontSize: 11,
    fontWeight: '800',
    letterSpacing: 0.4,
  },
  timeText: {
    color: '#908F8D',
    fontSize: 12,
    fontWeight: '600',
    lineHeight: 16,
  },
  chevronButton: {
    alignItems: 'center',
    borderColor: '#E4E1DB',
    borderRadius: 999,
    borderWidth: 1,
    height: 42,
    justifyContent: 'center',
    width: 42,
  },
  bottleWrap: {
    height: 38,
    left: 10,
    position: 'absolute',
    top: 14,
    transform: [{ rotate: '-18deg' }],
    width: 46,
  },
  bottleBody: {
    borderRadius: 12,
    height: 20,
    left: 7,
    position: 'absolute',
    top: 10,
    width: 32,
  },
  bottleCap: {
    backgroundColor: '#1C6BEB',
    borderRadius: 5,
    height: 11,
    left: 0,
    position: 'absolute',
    top: 14,
    width: 11,
  },
  bottleCrushOne: {
    backgroundColor: 'rgba(219, 226, 235, 0.92)',
    borderRadius: 10,
    height: 15,
    left: 24,
    position: 'absolute',
    top: 4,
    transform: [{ rotate: '32deg' }],
    width: 10,
  },
  bottleCrushTwo: {
    backgroundColor: 'rgba(232, 236, 242, 0.94)',
    borderRadius: 8,
    height: 13,
    left: 30,
    position: 'absolute',
    top: 14,
    transform: [{ rotate: '-24deg' }],
    width: 9,
  },
  cardboardStack: {
    flex: 1,
  },
  cardboardLayer: {
    backgroundColor: '#C5AA88',
    borderColor: '#B7956E',
    borderRadius: 4,
    borderWidth: 1,
    height: 8,
    left: 14,
    position: 'absolute',
  },
  canWrap: {
    alignItems: 'center',
    flex: 1,
    justifyContent: 'center',
  },
  canBody: {
    borderRadius: 18,
    height: 42,
    width: 28,
  },
  canTop: {
    backgroundColor: '#ECECEC',
    borderColor: '#B8B8B8',
    borderRadius: 999,
    borderWidth: 1,
    height: 7,
    position: 'absolute',
    top: 11,
    width: 18,
  },
  canBottomShadow: {
    backgroundColor: 'rgba(12, 12, 12, 0.08)',
    borderRadius: 999,
    bottom: 10,
    height: 6,
    position: 'absolute',
    width: 28,
  },
});
