import type { BottomTabBarProps } from '@react-navigation/bottom-tabs';
import { Ionicons } from '@expo/vector-icons';
import { BlurView } from 'expo-blur';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

export const BOTTOM_NAV_BAR_HEIGHT = 86;

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
  const bottomPadding = Math.max(insets.bottom, 14);

  return (
    <View pointerEvents="box-none" style={styles.wrapper}>
      <View pointerEvents="none" style={styles.shadowLayer} />
      <View style={styles.bar}>
        <BlurView intensity={58} style={StyleSheet.absoluteFill} tint="light" />
        <View
          style={[
            styles.barFill,
            {
              minHeight: BOTTOM_NAV_BAR_HEIGHT + Math.max(bottomPadding - 14, 0),
              paddingBottom: bottomPadding,
            },
          ]}>
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
    bottom: 0,
    backgroundColor: 'transparent',
    alignItems: 'center',
    left: 0,
    position: 'absolute',
    right: 0,
  },
  shadowLayer: {
    backgroundColor: 'rgba(15, 23, 42, 0.08)',
    bottom: 0,
    height: BOTTOM_NAV_BAR_HEIGHT + 20,
    left: 0,
    opacity: 0.7,
    position: 'absolute',
    right: 0,
    shadowColor: '#111827',
    shadowOffset: { width: 0, height: -10 },
    shadowOpacity: 0.1,
    shadowRadius: 24,
  },
  bar: {
    backgroundColor: 'rgba(248, 246, 241, 0.72)',
    borderColor: 'rgba(255, 255, 255, 0.62)',
    borderTopLeftRadius: 28,
    borderTopRightRadius: 28,
    borderTopWidth: 1,
    overflow: 'hidden',
    width: '100%',
  },
  barFill: {
    alignItems: 'center',
    backgroundColor: 'rgba(247, 244, 239, 0.38)',
    flexDirection: 'row',
    paddingHorizontal: 18,
    paddingTop: 12,
  },
  tabButton: {
    alignItems: 'center',
    borderRadius: 22,
    flex: 1,
    gap: 6,
    justifyContent: 'center',
    paddingVertical: 8,
  },
  tabButtonPressed: {
    opacity: 0.82,
  },
  iconBubble: {
    alignItems: 'center',
    backgroundColor: 'transparent',
    borderRadius: 999,
    height: 40,
    justifyContent: 'center',
    overflow: 'hidden',
    width: 40,
  },
  iconBubbleFocused: {
    backgroundColor: 'rgba(136, 211, 157, 0.18)',
  },
  tabLabel: {
    color: '#8A8E8D',
    fontSize: 12,
    fontWeight: '700',
    letterSpacing: 0.1,
  },
  tabLabelFocused: {
    color: '#4E8D63',
  },
});
