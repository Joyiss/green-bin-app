import type { BottomTabBarProps } from '@react-navigation/bottom-tabs';
import { Ionicons } from '@expo/vector-icons';
import { BlurView } from 'expo-blur';
import { LinearGradient } from 'expo-linear-gradient';
import { Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

export const BOTTOM_NAV_BAR_HEIGHT = 64;
const BOTTOM_NAV_BAR_WIDTH = 282;
const BAR_HORIZONTAL_PADDING = 14;

const tabs = {
  index: {
    label: 'Scan',
    icon: 'camera-outline' as const,
    activeIcon: 'camera' as const,
  },
  nearby: {
    label: 'Nearby',
    icon: 'location-outline' as const,
    activeIcon: 'location' as const,
  },
};

export function BottomNavBar({ state, descriptors, navigation }: BottomTabBarProps) {
  const insets = useSafeAreaInsets();
  const bottomOffset = Math.max(insets.bottom, 12);
  const isAndroid = Platform.OS === 'android';

  const activeColor = 'rgba(10, 12, 14, 0.92)';
  const inactiveColor = '#7A7F7E';

  const tabCount = state.routes.length;
  const tabWidth = (BOTTOM_NAV_BAR_WIDTH - BAR_HORIZONTAL_PADDING * 2) / tabCount;
  const selectedBubbleLeft = BAR_HORIZONTAL_PADDING + tabWidth * state.index;

  return (
    <View pointerEvents="box-none" style={styles.wrapper}>
      {/* Shadow Layer */}
      <View pointerEvents="none" style={[styles.shadowLayer, isAndroid && styles.shadowLayerAndroid, { bottom: bottomOffset }]} />

      {/* Bar Container */}
      <View style={[styles.bar, isAndroid && styles.barAndroid, { bottom: bottomOffset }]}>
        
        {!isAndroid ? (
          <>
            {/* Layer 1: iOS glass treatment */}
            <LinearGradient
              pointerEvents="none"
              colors={[
                'rgba(255, 255, 255, 0.08)',
                'rgba(245, 250, 255, 0.04)',
                'rgba(227, 239, 248, 0.015)',
                'rgba(150, 168, 186, 0.045)',
              ]}
              start={{ x: 0.08, y: 0 }}
              end={{ x: 0.92, y: 1 }}
              style={styles.glassGradient}
            />

            <LinearGradient
              pointerEvents="none"
              colors={[
                'rgba(255, 255, 255, 0.3)',
                'rgba(255, 255, 255, 0.12)',
                'rgba(255, 255, 255, 0)',
              ]}
              locations={[0, 0.45, 1]}
              start={{ x: 0, y: 0.5 }}
              end={{ x: 1, y: 0.5 }}
              style={styles.topHighlight}
            />

            <LinearGradient
              pointerEvents="none"
              colors={[
                'rgba(78, 97, 122, 0)',
                'rgba(78, 97, 122, 0.015)',
                'rgba(58, 72, 94, 0.045)',
              ]}
              locations={[0.24, 0.76, 1]}
              start={{ x: 0.5, y: 0 }}
              end={{ x: 0.5, y: 1 }}
              style={styles.bottomShade}
            />

            <View pointerEvents="none" style={styles.edgeRing} />

            {/* Layer 2: iOS blur */}
            <BlurView
              blurReductionFactor={4}
              experimentalBlurMethod="none"
              intensity={32}
              style={StyleSheet.absoluteFill}
              tint="default"
            />
          </>
        ) : null}

        {/* Layer 4: Interactive Content Layer */}
        <View style={[styles.barFill, isAndroid && styles.barFillAndroid]}>
          <View
            pointerEvents="none"
            style={[
              styles.selectedBubble,
              {
                left: selectedBubbleLeft,
                width: tabWidth,
              },
            ]}
          >
            {isAndroid ? (
              <>
                <View pointerEvents="none" style={styles.focusedTabSurfaceAndroid} />
                <View pointerEvents="none" style={styles.focusedTabEdgeAndroid} />
              </>
            ) : (
              <>
                <View pointerEvents="none" style={styles.focusedTabSurface} />
                <LinearGradient
                  pointerEvents="none"
                  colors={[
                    'rgba(255, 255, 255, 0.32)',
                    'rgba(255, 255, 255, 0.16)',
                    'rgba(235, 238, 242, 0.075)',
                    'rgba(210, 216, 222, 0.045)',
                  ]}
                  locations={[0, 0.3, 0.72, 1]}
                  start={{ x: 0.08, y: 0 }}
                  end={{ x: 0.92, y: 1 }}
                  style={styles.focusedTabGlass}
                />
                <View pointerEvents="none" style={styles.focusedTabEdge} />
              </>
            )}
          </View>

          {state.routes.map((route, index) => {
            const isFocused = state.index === index;
            const config = tabs[route.name as keyof typeof tabs];

            const onPress = () => {
              const event = navigation.emit({
                type: 'tabPress',
                target: route.key,
                canPreventDefault: true,
              });

              if (!isFocused && !event.defaultPrevented) {
                navigation.navigate(route.name, route.params);
              }
            };

            const onLongPress = () => {
              navigation.emit({
                type: 'tabLongPress',
                target: route.key,
              });
            };

            return (
              <Pressable
                key={route.key}
                accessibilityLabel={descriptors[route.key].options.tabBarAccessibilityLabel}
                accessibilityRole="button"
                accessibilityState={isFocused ? { selected: true } : {}}
                onLongPress={onLongPress}
                onPress={onPress}
                style={({ pressed }) => [
                  styles.tabButton,
                  isAndroid && styles.tabButtonAndroid,
                  pressed && styles.tabButtonPressed,
                ]}
              >
                <View style={styles.iconBubble}>
                  <Ionicons
                    color={isFocused ? activeColor : inactiveColor}
                    name={isFocused ? config.activeIcon : config.icon}
                    size={21}
                  />
                </View>
                <Text style={[styles.tabLabel, { color: isFocused ? activeColor : inactiveColor }]}>
                  {config.label}
                </Text>
              </Pressable>
            );
          })}
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    backgroundColor: 'transparent',
    alignItems: 'center',
    bottom: 0,
    left: 0,
    position: 'absolute',
    right: 0,
  },
  shadowLayer: {
    backgroundColor: 'rgba(20, 32, 48, 0.02)',
    borderRadius: 999,
    height: BOTTOM_NAV_BAR_HEIGHT,
    opacity: 0.34,
    position: 'absolute',
    width: BOTTOM_NAV_BAR_WIDTH,
    shadowColor: '#102033',
    shadowOffset: { width: 0, height: 7 },
    shadowOpacity: 0.04,
    shadowRadius: 14,
    transform: [{ scaleX: 0.92 }, { translateY: 5 }],
  },
  shadowLayerAndroid: {
    backgroundColor: 'rgba(15, 23, 42, 0.08)',
    opacity: 0.18,
    elevation: 4,
  },
  bar: {
    backgroundColor: 'rgba(248, 251, 255, 0.022)',
    borderColor: 'rgba(255, 255, 255, 0.26)',
    borderRadius: 999,
    borderWidth: 1,
    overflow: 'hidden',
    position: 'absolute',
    width: BOTTOM_NAV_BAR_WIDTH,
  },
  barAndroid: {
    backgroundColor: '#FFFFFF',
    borderColor: 'rgba(15, 23, 42, 0.08)',
  },
  glassGradient: {
    ...StyleSheet.absoluteFillObject,
    borderRadius: 999,
    zIndex: 1,
  },
  topHighlight: {
    borderRadius: 999,
    height: 2,
    left: 16,
    position: 'absolute',
    right: 42,
    top: 1,
    zIndex: 2,
  },
  bottomShade: {
    ...StyleSheet.absoluteFillObject,
    borderRadius: 999,
    zIndex: 3,
  },
  edgeRing: {
    ...StyleSheet.absoluteFillObject,
    borderColor: 'rgba(255, 255, 255, 0.42)',
    borderRadius: 999,
    borderWidth: 1,
    zIndex: 4,
  },
  barFill: {
    alignItems: 'center',
    backgroundColor: 'transparent',
    borderRadius: 999,
    flexDirection: 'row',
    minHeight: BOTTOM_NAV_BAR_HEIGHT,
    paddingHorizontal: BAR_HORIZONTAL_PADDING,
    paddingVertical: 8,
    position: 'relative',
    width: BOTTOM_NAV_BAR_WIDTH,
    zIndex: 7,
  },
  barFillAndroid: {
    backgroundColor: 'transparent',
  },
  selectedBubble: {
    bottom: 8,
    borderRadius: 999,
    overflow: 'hidden',
    position: 'absolute',
    top: 8,
    zIndex: 1,
  },
  tabButton: {
    alignItems: 'center',
    borderRadius: 999,
    flex: 1,
    gap: 4,
    justifyContent: 'center',
    minWidth: 0,
    paddingHorizontal: 20,
    paddingVertical: 10,
    position: 'relative',
    zIndex: 5,
  },
  tabButtonAndroid: {
    paddingHorizontal: 16,
  },
  tabButtonPressed: {
    opacity: 0.82,
  },
  focusedTabSurface: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(255, 255, 255, 0.12)',
    borderRadius: 999,
  },
  focusedTabSurfaceAndroid: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: '#F4F4F5',
    borderRadius: 999,
  },
  focusedTabGlass: {
    ...StyleSheet.absoluteFillObject,
    borderRadius: 999,
  },
  focusedTabEdge: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'transparent',
    borderColor: 'rgba(185, 190, 198, 0.58)',
    borderRadius: 999,
    borderWidth: 1,
  },
  focusedTabEdgeAndroid: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'transparent',
    borderColor: 'rgba(15, 23, 42, 0.1)',
    borderRadius: 999,
    borderWidth: 1,
  },
  iconBubble: {
    alignItems: 'center',
    backgroundColor: 'transparent',
    borderRadius: 999,
    height: 28,
    justifyContent: 'center',
    overflow: 'hidden',
    width: 28,
  },
  tabLabel: {
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 0.1,
    textAlign: 'center',
    width: '100%',
  },
});
