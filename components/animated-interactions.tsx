import {
  AccessibilityInfo,
  Pressable,
  StyleSheet,
  type PressableProps,
  type ViewStyle,
} from 'react-native';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import Animated, {
  Easing,
  FadeIn,
  FadeOut,
  LinearTransition,
  useAnimatedStyle,
  useSharedValue,
  withSequence,
  withTiming,
} from 'react-native-reanimated';
import { Ionicons } from '@expo/vector-icons';

export const MOTION_DURATION_FAST = 160;
export const MOTION_DURATION_BASE = 220;
export const MOTION_EASING = Easing.out(Easing.cubic);

const ReanimatedPressable = Animated.createAnimatedComponent(Pressable);

export function useReducedMotionPreference() {
  const [reducedMotion, setReducedMotion] = useState(false);

  useEffect(() => {
    let mounted = true;

    AccessibilityInfo.isReduceMotionEnabled()
      .then((enabled) => {
        if (mounted) {
          setReducedMotion(enabled);
        }
      })
      .catch(() => undefined);

    const subscription = AccessibilityInfo.addEventListener?.(
      'reduceMotionChanged',
      setReducedMotion,
    );

    return () => {
      mounted = false;
      subscription?.remove?.();
    };
  }, []);

  return reducedMotion;
}

type AnimatedPressableProps = PressableProps & {
  pressScale?: number;
  selected?: boolean;
  selectedPulseScale?: number;
};

export function AnimatedPressable({
  children,
  disabled,
  onPressIn,
  onPressOut,
  pressScale = 0.97,
  selected,
  selectedPulseScale = 1.06,
  style,
  ...props
}: AnimatedPressableProps) {
  const reducedMotion = useReducedMotionPreference();
  const scale = useSharedValue(1);
  const wasSelected = useRef(selected);

  useEffect(() => {
    if (selected && !wasSelected.current && !reducedMotion && !disabled) {
      scale.value = withSequence(
        withTiming(selectedPulseScale, {
          duration: 90,
          easing: MOTION_EASING,
        }),
        withTiming(1, {
          duration: MOTION_DURATION_FAST,
          easing: MOTION_EASING,
        }),
      );
    }

    wasSelected.current = selected;
  }, [disabled, reducedMotion, scale, selected, selectedPulseScale]);

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value }],
  }));

  return (
    <ReanimatedPressable
      {...props}
      disabled={disabled}
      onPressIn={(event) => {
        if (!disabled && !reducedMotion) {
          scale.value = withTiming(pressScale, {
            duration: 90,
            easing: MOTION_EASING,
          });
        }
        onPressIn?.(event);
      }}
      onPressOut={(event) => {
        if (!disabled && !reducedMotion) {
          scale.value = withTiming(1, {
            duration: MOTION_DURATION_FAST,
            easing: MOTION_EASING,
          });
        }
        onPressOut?.(event);
      }}
      style={(state) => [
        typeof style === 'function' ? style(state) : style,
        !reducedMotion && animatedStyle,
      ]}>
      {children}
    </ReanimatedPressable>
  );
}

type AnimatedDisclosureProps = {
  children: ReactNode;
  expanded: boolean;
  style?: ViewStyle;
};

export function AnimatedDisclosure({ children, expanded, style }: AnimatedDisclosureProps) {
  const reducedMotion = useReducedMotionPreference();
  const layout = reducedMotion
    ? undefined
    : LinearTransition.duration(MOTION_DURATION_BASE).easing(MOTION_EASING);
  const entering = reducedMotion
    ? undefined
    : FadeIn.duration(MOTION_DURATION_FAST).easing(MOTION_EASING);
  const exiting = reducedMotion
    ? undefined
    : FadeOut.duration(140).easing(MOTION_EASING);

  return (
    <Animated.View layout={layout} style={[styles.disclosure, style]}>
      {expanded ? (
        <Animated.View entering={entering} exiting={exiting} layout={layout}>
          {children}
        </Animated.View>
      ) : null}
    </Animated.View>
  );
}

type AnimatedChevronProps = {
  color: string;
  expanded: boolean;
  size: number;
};

export function AnimatedChevron({ color, expanded, size }: AnimatedChevronProps) {
  const reducedMotion = useReducedMotionPreference();
  const progress = useSharedValue(expanded ? 1 : 0);

  useEffect(() => {
    progress.value = reducedMotion
      ? expanded ? 1 : 0
      : withTiming(expanded ? 1 : 0, {
          duration: MOTION_DURATION_BASE,
          easing: MOTION_EASING,
        });
  }, [expanded, progress, reducedMotion]);

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [{ rotate: `${progress.value * 180}deg` }],
  }));

  return (
    <Animated.View style={!reducedMotion && animatedStyle}>
      <Ionicons color={color} name="chevron-down" size={size} />
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  disclosure: {
    overflow: 'hidden',
  },
});
