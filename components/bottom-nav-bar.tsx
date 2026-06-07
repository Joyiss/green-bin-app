import type { BottomTabBarProps } from '@react-navigation/bottom-tabs';
import { Ionicons } from '@expo/vector-icons';
import { BlurView } from 'expo-blur';
import { Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

export const BOTTOM_NAV_BAR_HEIGHT = 64;

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

  return (
    <View pointerEvents="box-none" style={styles.wrapper}>
      <View
        pointerEvents="none"
        style={[styles.shadowLayer, isAndroid && styles.shadowLayerAndroid, { bottom: bottomOffset }]}
      />

      <View style={[styles.bar, isAndroid && styles.barAndroid, { bottom: bottomOffset }]}>
        <BlurView
          blurReductionFactor={isAndroid ? 1 : 2}
          experimentalBlurMethod={isAndroid ? 'dimezisBlurView' : 'none'}
          intensity={100}
          style={StyleSheet.absoluteFill}
          tint={isAndroid ? 'light' : 'systemThinMaterialLight'}
        />

        {isAndroid ? <View pointerEvents="none" style={styles.androidFrostLayer} /> : null}
        {isAndroid ? <View pointerEvents="none" style={styles.glossHighlight} /> : null}
        {isAndroid ? <View pointerEvents="none" style={styles.innerBorder} /> : null}

        <View style={[styles.barFill, isAndroid && styles.barFillAndroid]}>
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
                  isFocused && styles.tabButtonFocused,
                  isFocused && isAndroid && styles.tabButtonFocusedAndroid,
                  pressed && styles.tabButtonPressed,
                ]}>
                <View style={[styles.iconBubble, isFocused && styles.iconBubbleFocused]}>
                  <Ionicons
                    color={isFocused ? '#4E8D63' : '#8A8E8D'}
                    name={isFocused ? config.activeIcon : config.icon}
                    size={21}
                  />
                </View>

                <Text style={[styles.tabLabel, isFocused && styles.tabLabelFocused]}>
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
    backgroundColor: 'rgba(17, 24, 39, 0.06)',
    borderRadius: 999,
    height: BOTTOM_NAV_BAR_HEIGHT,
    opacity: 0.5,
    position: 'absolute',
    width: 262,
    shadowColor: '#111827',
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.16,
    shadowRadius: 24,
  },
  shadowLayerAndroid: {
    backgroundColor: 'rgba(0, 0, 0, 0.12)',
    opacity: 0.25,
    elevation: 18,
  },
  bar: {
    backgroundColor: 'rgba(251, 250, 247, 0.14)',
    borderColor: 'rgba(255, 255, 255, 0.28)',
    borderRadius: 999,
    borderWidth: 1,
    minWidth: 278,
    overflow: 'hidden',
    position: 'absolute',
  },
  barAndroid: {
    backgroundColor: 'rgba(255, 255, 255, 0.18)',
    borderColor: 'rgba(255, 255, 255, 0.35)',
  },
  androidFrostLayer: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(255, 255, 255, 0.05)',
  },
  glossHighlight: {
    position: 'absolute',
    top: 0,
    left: 8,
    right: 8,
    height: 1.5,
    backgroundColor: 'rgba(255, 255, 255, 0.75)',
    borderRadius: 999,
    opacity: 0.9,
    zIndex: 2,
  },
  innerBorder: {
    position: 'absolute',
    top: 1,
    left: 1,
    right: 1,
    bottom: 1,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.25)',
    zIndex: 2,
  },
  barFill: {
    alignItems: 'center',
    backgroundColor: 'rgba(255, 255, 255, 0.06)',
    borderRadius: 999,
    flexDirection: 'row',
    minHeight: BOTTOM_NAV_BAR_HEIGHT,
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  barFillAndroid: {
    backgroundColor: 'rgba(255, 255, 255, 0.10)',
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
  },
  tabButtonAndroid: {
    paddingHorizontal: 16,
  },
  tabButtonFocused: {
    backgroundColor: 'rgba(255, 255, 255, 0.34)',
  },
  tabButtonFocusedAndroid: {
    backgroundColor: 'rgba(255, 255, 255, 0.28)',
  },
  tabButtonPressed: {
    opacity: 0.82,
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
  iconBubbleFocused: {
    backgroundColor: 'transparent',
  },
  tabLabel: {
    color: '#8A8E8D',
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 0.1,
    textAlign: 'center',
    width: '100%',
  },
  tabLabelFocused: {
    color: '#4E8D63',
  },
});
