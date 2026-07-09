import { LinearGradient } from 'expo-linear-gradient';
import { useEffect } from 'react';
import { StyleSheet, View, useWindowDimensions, type StyleProp, type ViewStyle } from 'react-native';
import Reanimated, {
  Easing,
  cancelAnimation,
  useAnimatedStyle,
  useSharedValue,
  withDelay,
  withRepeat,
  withSequence,
  withTiming,
} from 'react-native-reanimated';

const SHIMMER_BAND_WIDTH = 120;

function SkeletonBlock({
  shimmerStyle,
  style,
}: {
  shimmerStyle: StyleProp<ViewStyle>;
  style?: StyleProp<ViewStyle>;
}) {
  return (
    <View style={[styles.block, style]}>
      <Reanimated.View pointerEvents="none" style={[styles.shimmerBand, shimmerStyle]}>
        <LinearGradient
          colors={[
            'rgba(255,255,255,0)',
            'rgba(255,255,255,0.24)',
            'rgba(255,255,255,0.58)',
            'rgba(255,255,255,0.24)',
            'rgba(255,255,255,0)',
          ]}
          locations={[0, 0.22, 0.5, 0.78, 1]}
          start={{ x: 0, y: 0.5 }}
          end={{ x: 1, y: 0.5 }}
          style={StyleSheet.absoluteFillObject}
        />
      </Reanimated.View>
    </View>
  );
}

export function LocationCardSkeleton({ compact = false }: { compact?: boolean }) {
  const { width } = useWindowDimensions();
  const shimmerProgress = useSharedValue(0);
  const shimmerTravel = Math.max(width - 36, 320) + SHIMMER_BAND_WIDTH;

  useEffect(() => {
    shimmerProgress.value = withRepeat(
      withSequence(
        withTiming(1, {
          duration: 2400,
          easing: Easing.bezier(0.4, 0, 0.2, 1),
        }),
        withDelay(520, withTiming(0, { duration: 0 })),
      ),
      -1,
      false,
    );

    return () => {
      cancelAnimation(shimmerProgress);
      shimmerProgress.value = 0;
    };
  }, [shimmerProgress]);

  const shimmerStyle = useAnimatedStyle(() => ({
    transform: [{ translateX: -SHIMMER_BAND_WIDTH + shimmerProgress.value * shimmerTravel }],
  }));

  return (
    <View accessibilityLabel="Loading location" accessibilityRole="progressbar" style={styles.card}>
      <View style={styles.header}>
        <View style={styles.headerText}>
          <View style={styles.typeRow}>
            <SkeletonBlock shimmerStyle={shimmerStyle} style={styles.typeLabel} />
            <SkeletonBlock shimmerStyle={shimmerStyle} style={styles.dot} />
          </View>
          <SkeletonBlock shimmerStyle={shimmerStyle} style={styles.titleLine} />
          <SkeletonBlock
            shimmerStyle={shimmerStyle}
            style={[styles.titleLine, compact ? styles.titleShortCompact : styles.titleShort]}
          />
          <View style={styles.addressGroup}>
            <SkeletonBlock shimmerStyle={shimmerStyle} style={styles.addressLine} />
            <SkeletonBlock shimmerStyle={shimmerStyle} style={styles.addressShort} />
          </View>
        </View>
        <SkeletonBlock shimmerStyle={shimmerStyle} style={styles.preview} />
      </View>

      <View style={styles.metaRow}>
        <View style={styles.metaItem}>
          <SkeletonBlock shimmerStyle={shimmerStyle} style={styles.metaIcon} />
          <SkeletonBlock shimmerStyle={shimmerStyle} style={styles.metaText} />
        </View>
        <View style={styles.metaItem}>
          <SkeletonBlock shimmerStyle={shimmerStyle} style={styles.metaIcon} />
          <SkeletonBlock shimmerStyle={shimmerStyle} style={styles.distanceText} />
        </View>
      </View>

      <SkeletonBlock shimmerStyle={shimmerStyle} style={styles.button} />
    </View>
  );
}

export function LocationCardSkeletonList() {
  return (
    <>
      <LocationCardSkeleton />
      <LocationCardSkeleton compact />
      <LocationCardSkeleton />
    </>
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
    gap: 8,
  },
  typeRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 6,
  },
  block: {
    backgroundColor: '#ECE8E2',
    overflow: 'hidden',
  },
  shimmerBand: {
    bottom: -6,
    position: 'absolute',
    top: -6,
    width: SHIMMER_BAND_WIDTH,
  },
  typeLabel: {
    borderRadius: 5,
    height: 12,
    width: 112,
  },
  dot: {
    borderRadius: 999,
    height: 7,
    width: 7,
  },
  titleLine: {
    borderRadius: 7,
    height: 18,
    width: '88%',
  },
  titleShort: {
    width: '74%',
  },
  titleShortCompact: {
    width: '48%',
  },
  addressGroup: {
    gap: 7,
    paddingTop: 4,
  },
  addressLine: {
    borderRadius: 7,
    height: 15,
    width: '78%',
  },
  addressShort: {
    borderRadius: 7,
    height: 15,
    width: '55%',
  },
  preview: {
    borderRadius: 16,
    height: 56,
    width: 56,
  },
  metaRow: {
    flexDirection: 'row',
    gap: 18,
  },
  metaItem: {
    alignItems: 'center',
    flexDirection: 'row',
    flexShrink: 1,
    gap: 7,
  },
  metaIcon: {
    borderRadius: 999,
    height: 14,
    width: 14,
  },
  metaText: {
    borderRadius: 7,
    height: 14,
    width: 156,
  },
  distanceText: {
    borderRadius: 7,
    height: 14,
    width: 44,
  },
  button: {
    borderRadius: 999,
    height: 47,
  },
});
