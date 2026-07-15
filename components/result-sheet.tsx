import { Ionicons } from '@expo/vector-icons';
import { useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  Pressable,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  View,
  type LayoutChangeEvent,
  type ScrollViewProps,
} from 'react-native';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import Animated, {
  Easing,
  runOnJS,
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';

const IS_ANDROID = Platform.OS === 'android';
const SHEET_COLLAPSE_THRESHOLD = 96;
const ANDROID_SHEET_COLLAPSE_THRESHOLD = 50;
const ANDROID_SHEET_VELOCITY_THRESHOLD = 500;
const SHEET_COLLAPSE_ACTIVATION_OFFSET = IS_ANDROID ? 8 : 14;
const SHEET_COLLAPSE_HORIZONTAL_TOLERANCE = IS_ANDROID ? 80 : 24;
const SHEET_HEIGHT_SNAP_CONFIG = {
  duration: 180,
  easing: Easing.out(Easing.cubic),
};
const SHOULD_RESIZE_SHEET_DURING_DRAG = !IS_ANDROID;
const SHEET_STATE_EXPANDED = 0;
const SHEET_STATE_COLLAPSED = 1;

type ResultSheetDisplayMode = 'expandable' | 'static';
type ResultSheetViewState = 'expanded' | 'collapsed';
type GestureLogPhase = 'ended' | 'cancelled';
type GestureLogReason =
  | 'collapse-distance'
  | 'collapse-velocity'
  | 'expand-distance'
  | 'expand-velocity'
  | 'snap-back'
  | 'gesture-cancelled-or-failed';

type ResultSheetProps = {
  label: string;
  title: string;
  materialTag?: string | null;
  summary: string;
  steps: string[];
  warnings?: string[];
  guidanceMetadata?: Record<string, unknown> | null;
  guidanceSource?: string;
  displayMode?: ResultSheetDisplayMode;
  keyboardShouldPersistTaps?: ScrollViewProps['keyboardShouldPersistTaps'];

  buttonLabel?: string;
  buttonIconName?: keyof typeof Ionicons.glyphMap;
  onButtonPress?: () => void;

  secondaryButtonLabel?: string;
  secondaryButtonIconName?: keyof typeof Ionicons.glyphMap;
  onSecondaryButtonPress?: () => void;

  children?: ReactNode;
};

function logAndroidSheetGestureDecision(
  translationY: number,
  velocityY: number,
  currentState: ResultSheetViewState,
  targetState: ResultSheetViewState,
  phase: GestureLogPhase,
  reason: GestureLogReason,
) {
  if (!IS_ANDROID || !__DEV__) {
    return;
  }

  console.debug('[ResultSheet Android gesture]', {
    translationY: Math.round(translationY),
    velocityY: Math.round(velocityY),
    currentState,
    targetState,
    phase,
    reason,
  });
}

export function ResultSheet({
  label,
  title,
  materialTag,
  summary,
  steps,
  warnings = [],
  displayMode = 'static',
  keyboardShouldPersistTaps,
  buttonLabel,
  buttonIconName = 'location-outline',
  onButtonPress,
  secondaryButtonLabel,
  secondaryButtonIconName = 'swap-horizontal-outline',
  onSecondaryButtonPress,
  children,
}: ResultSheetProps) {
  // Collapse is local presentation state; full close/reset still belongs to the outer close button.
  const [sheetDisplayState, setSheetDisplayState] = useState<ResultSheetViewState>('expanded');
  const showSecondaryButton = secondaryButtonLabel && onSecondaryButtonPress;
  const showPrimaryButton = buttonLabel && onButtonPress;
  const isExpandable = displayMode === 'expandable';
  const isCollapsed = isExpandable && sheetDisplayState === 'collapsed';
  const [expandedSheetHeight, setExpandedSheetHeight] = useState(0);
  const [headerHeight, setHeaderHeight] = useState(0);
  const [footerHeight, setFooterHeight] = useState(0);
  const sheetHeightValue = useSharedValue(0);
  const expandedHeightValue = useSharedValue(0);
  const collapsedHeightValue = useSharedValue(0);
  const sheetStateValue = useSharedValue(SHEET_STATE_EXPANDED);
  const hasMeasuredExpandableLayout = expandedSheetHeight > 0 && headerHeight > 0 && footerHeight > 0;

  useEffect(() => {
    setSheetDisplayState('expanded');
    sheetStateValue.value = SHEET_STATE_EXPANDED;
    sheetHeightValue.value = expandedHeightValue.value;

    return () => {
      sheetHeightValue.value = 0;
    };
  }, [displayMode, expandedHeightValue, label, sheetHeightValue, sheetStateValue, title]);

  useEffect(() => {
    const nextCollapsedHeight = Math.max(headerHeight + footerHeight, 0);
    expandedHeightValue.value = expandedSheetHeight;
    collapsedHeightValue.value = nextCollapsedHeight;

    if (sheetStateValue.value === SHEET_STATE_COLLAPSED) {
      sheetHeightValue.value = nextCollapsedHeight;
      return;
    }

    if (expandedSheetHeight > 0) {
      sheetHeightValue.value = expandedSheetHeight;
    }
  }, [
    collapsedHeightValue,
    expandedHeightValue,
    expandedSheetHeight,
    footerHeight,
    headerHeight,
    sheetHeightValue,
    sheetStateValue,
  ]);

  const handleExpandedSheetLayout = ({ nativeEvent }: LayoutChangeEvent) => {
    const nextHeight = nativeEvent.layout.height;

    if (sheetDisplayState === 'expanded' && Math.abs(nextHeight - expandedSheetHeight) > 1) {
      setExpandedSheetHeight(nextHeight);
    }
  };

  const handleHeaderLayout = ({ nativeEvent }: LayoutChangeEvent) => {
    setHeaderHeight(nativeEvent.layout.height);
  };

  const handleFooterLayout = ({ nativeEvent }: LayoutChangeEvent) => {
    setFooterHeight(nativeEvent.layout.height);
  };

  const expandableSheetStyle = useAnimatedStyle(() => ({
    height: sheetHeightValue.value,
  }));

  const collapseGesture = useMemo(
    () => {
      const collapseSheet = () => {
        setSheetDisplayState('collapsed');
      };
      const expandSheet = () => {
        setSheetDisplayState('expanded');
      };

      return Gesture.Pan()
        // The gesture resizes the sheet from the top; its bottom stays anchored by the parent wrapper.
        .enabled(isExpandable && hasMeasuredExpandableLayout)
        .activeOffsetY([-SHEET_COLLAPSE_ACTIVATION_OFFSET, SHEET_COLLAPSE_ACTIVATION_OFFSET])
        .failOffsetX([
          -SHEET_COLLAPSE_HORIZONTAL_TOLERANCE,
          SHEET_COLLAPSE_HORIZONTAL_TOLERANCE,
        ])
        .onUpdate((event) => {
          if (!SHOULD_RESIZE_SHEET_DURING_DRAG) {
            return;
          }

          const startHeight =
            sheetStateValue.value === SHEET_STATE_COLLAPSED
              ? collapsedHeightValue.value
              : expandedHeightValue.value;

          sheetHeightValue.value = Math.min(
            Math.max(startHeight - event.translationY, collapsedHeightValue.value),
            expandedHeightValue.value,
          );
        })
        .onEnd((event) => {
          const currentState = sheetStateValue.value;
          let targetState = currentState;
          let reason: GestureLogReason = 'snap-back';

          if (currentState === SHEET_STATE_EXPANDED) {
            if (IS_ANDROID && event.velocityY > ANDROID_SHEET_VELOCITY_THRESHOLD) {
              targetState = SHEET_STATE_COLLAPSED;
              reason = 'collapse-velocity';
            } else if (
              event.translationY >=
              (IS_ANDROID ? ANDROID_SHEET_COLLAPSE_THRESHOLD : SHEET_COLLAPSE_THRESHOLD)
            ) {
              targetState = SHEET_STATE_COLLAPSED;
              reason = 'collapse-distance';
            }
          }

          if (currentState === SHEET_STATE_COLLAPSED) {
            if (IS_ANDROID && event.velocityY < -ANDROID_SHEET_VELOCITY_THRESHOLD) {
              targetState = SHEET_STATE_EXPANDED;
              reason = 'expand-velocity';
            } else if (
              event.translationY <=
              -(IS_ANDROID ? ANDROID_SHEET_COLLAPSE_THRESHOLD : SHEET_COLLAPSE_THRESHOLD)
            ) {
              targetState = SHEET_STATE_EXPANDED;
              reason = 'expand-distance';
            }
          }

          const targetHeight =
            targetState === SHEET_STATE_COLLAPSED
              ? collapsedHeightValue.value
              : expandedHeightValue.value;
          const currentStateLabel =
            currentState === SHEET_STATE_COLLAPSED ? 'collapsed' : 'expanded';
          const targetStateLabel =
            targetState === SHEET_STATE_COLLAPSED ? 'collapsed' : 'expanded';

          if (IS_ANDROID) {
            runOnJS(logAndroidSheetGestureDecision)(
              event.translationY,
              event.velocityY,
              currentStateLabel,
              targetStateLabel,
              'ended',
              reason,
            );
          }

          if (targetState !== currentState) {
            sheetStateValue.value = targetState;
            sheetHeightValue.value = withTiming(
              targetHeight,
              SHEET_HEIGHT_SNAP_CONFIG,
              (finished) => {
                if (!finished) {
                  return;
                }

                if (targetState === SHEET_STATE_COLLAPSED) {
                  runOnJS(collapseSheet)();
                  return;
                }

                runOnJS(expandSheet)();
              },
            );
            return;
          }

          sheetHeightValue.value = withTiming(
            targetHeight,
            SHEET_HEIGHT_SNAP_CONFIG,
          );
        })
        .onFinalize((event, success) => {
          if (IS_ANDROID && !success) {
            const currentState =
              sheetStateValue.value === SHEET_STATE_COLLAPSED ? 'collapsed' : 'expanded';

            runOnJS(logAndroidSheetGestureDecision)(
              event.translationY,
              event.velocityY,
              currentState,
              currentState,
              'cancelled',
              'gesture-cancelled-or-failed',
            );
          }
        });
    },
    [
      collapsedHeightValue,
      expandedHeightValue,
      hasMeasuredExpandableLayout,
      isExpandable,
      sheetHeightValue,
      sheetStateValue,
    ],
  );

  const headerContent = (
    <View style={styles.header}>
      <View style={styles.handle} />

      <Text style={styles.eyebrow}>{label}</Text>
      <Text style={styles.title}>{title}</Text>

      {materialTag ? (
        <View style={styles.tag}>
          <Ionicons color="#5B6470" name="leaf-outline" size={14} />
          <Text numberOfLines={1} style={styles.tagText}>
            {materialTag}
          </Text>
        </View>
      ) : null}
    </View>
  );

  const detailsContent = (
    <View
      pointerEvents={isCollapsed ? 'none' : 'auto'}
      style={[styles.detailsRegion, isCollapsed && styles.detailsRegionCollapsed]}>
      <ScrollView
        bounces={false}
        contentContainerStyle={styles.bodyContent}
        keyboardShouldPersistTaps={keyboardShouldPersistTaps}
        nestedScrollEnabled
        showsVerticalScrollIndicator={false}
        style={styles.body}>
        <Text selectable style={styles.summary}>{summary}</Text>

        {steps.length ? (
          <View style={styles.steps}>
            {steps.map((step, index) => (
              <View key={`${step}-${index}`} style={styles.stepRow}>
                <View style={styles.stepIndex}>
                  <Text style={styles.stepIndexText}>{index + 1}</Text>
                </View>
                <Text selectable style={styles.stepText}>{step}</Text>
              </View>
            ))}
          </View>
        ) : null}

        {warnings.length ? (
          <View style={styles.warnings}>
            {warnings.map((warning, index) => (
              <View key={`${warning}-${index}`} style={styles.warningRow}>
                <Ionicons color="#8A6434" name="warning-outline" size={17} />
                <Text selectable style={styles.warningText}>{warning}</Text>
              </View>
            ))}
          </View>
        ) : null}

        {children}
      </ScrollView>
    </View>
  );

  const footerContent = (
    <View onLayout={handleFooterLayout} style={styles.footer}>
      {(showSecondaryButton || showPrimaryButton) ? (
        <>
          {showSecondaryButton ? (
            <Pressable
              onPress={onSecondaryButtonPress}
              style={({ pressed }) => [
                styles.secondaryButton,
                pressed && styles.buttonPressed,
              ]}>
              <Ionicons color="#333333" name={secondaryButtonIconName} size={17} />
              <Text style={styles.secondaryButtonText}>{secondaryButtonLabel}</Text>
            </Pressable>
          ) : null}

          {showPrimaryButton ? (
            <Pressable
              onPress={onButtonPress}
              style={({ pressed }) => [
                styles.button,
                pressed && styles.buttonPressed,
              ]}>
              <Ionicons color="#FFFFFF" name={buttonIconName} size={18} />
              <Text style={styles.buttonText}>{buttonLabel}</Text>
            </Pressable>
          ) : null}
        </>
      ) : null}
    </View>
  );

  if (!isExpandable) {
    return (
      <View style={styles.sheetShadow}>
        <View style={styles.sheetClip}>
          {headerContent}
          {detailsContent}
          {footerContent}
        </View>
      </View>
    );
  }

  return (
    <Animated.View
      style={[
        styles.sheetShadow,
        styles.expandableSheet,
        hasMeasuredExpandableLayout && expandableSheetStyle,
      ]}>
      <View style={[styles.sheetClip, styles.expandableSheetClip]}>
        <View onLayout={handleExpandedSheetLayout} pointerEvents="none" style={styles.expandedMeasure}>
          {headerContent}
          <View style={styles.measureDetails}>{detailsContent}</View>
          {footerContent}
        </View>

        <GestureDetector gesture={collapseGesture}>
          <Animated.View onLayout={handleHeaderLayout} style={styles.headerLayer}>
            {headerContent}
          </Animated.View>
        </GestureDetector>

        <View
          pointerEvents={isCollapsed ? 'none' : 'auto'}
          style={[
            styles.expandableDetailsLayer,
            { top: headerHeight, bottom: footerHeight },
            isCollapsed && styles.detailsRegionCollapsed,
          ]}>
          {detailsContent}
        </View>

        <View onLayout={handleFooterLayout} style={styles.footerLayer}>
          {footerContent}
        </View>
      </View>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  sheetShadow: {
    borderRadius: 32,
    flexShrink: 1,
    maxHeight: '100%',
    minHeight: 220,
    shadowColor: '#0F172A',
    elevation: 8,
    shadowOffset: { width: 0, height: 16 },
    shadowOpacity: 0.12,
    shadowRadius: 24,
  },
  sheetClip: {
    backgroundColor: '#FFFEFC',
    borderRadius: 32,
    flexShrink: 1,
    maxHeight: '100%',
    minHeight: 220,
    overflow: 'hidden',
  },
  expandableSheet: {
    minHeight: 0,
    position: 'relative',
  },
  expandableSheetClip: {
    flex: 1,
    minHeight: 0,
    position: 'relative',
  },
  expandedMeasure: {
    opacity: 0,
  },
  headerLayer: {
    backgroundColor: '#FFFEFC',
    left: 0,
    position: 'absolute',
    right: 0,
    top: 0,
    zIndex: 4,
  },
  header: {
    paddingHorizontal: 18,
    paddingTop: 14,
    paddingBottom: 10,
    position: 'relative',
  },
  handle: {
    alignSelf: 'center',
    backgroundColor: '#E6E1DA',
    borderRadius: 999,
    height: 5,
    marginBottom: 12,
    width: 38,
  },
  eyebrow: {
    color: '#9A948C',
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 2,
    textAlign: 'center',
  },
  title: {
    color: '#050505',
    fontSize: 32,
    fontWeight: '900',
    letterSpacing: -1.3,
    textAlign: 'center',
    marginBottom: 10,
    marginTop: 8,
  },
  tag: {
    alignItems: 'center',
    alignSelf: 'center',
    borderColor: '#E8E2DA',
    borderRadius: 999,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 6,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  tagText: {
    color: '#4E5661',
    fontSize: 12,
    fontWeight: '700',
  },
  body: {
    flexGrow: 0,
    flexShrink: 1,
  },
  detailsRegion: {
    flexShrink: 1,
    zIndex: 1,
  },
  detailsRegionCollapsed: {
    opacity: 0,
  },
  expandableDetailsLayer: {
    left: 0,
    overflow: 'hidden',
    position: 'absolute',
    right: 0,
    zIndex: 1,
  },
  measureDetails: {
    flexShrink: 1,
  },
  bodyContent: {
    gap: 12,
    paddingHorizontal: 18,
    paddingBottom: 14,
  },
  summary: {
    color: '#66605B',
    fontSize: 14,
    lineHeight: 21,
    textAlign: 'center',
  },
  steps: {
    gap: 10,
    marginTop: 2,
  },
  stepRow: {
    flexDirection: 'row',
    gap: 10,
  },
  stepIndex: {
    alignItems: 'center',
    borderColor: '#E4DED7',
    borderRadius: 999,
    borderWidth: 1,
    height: 22,
    justifyContent: 'center',
    marginTop: 2,
    width: 22,
  },
  stepIndexText: {
    color: '#8B857F',
    fontSize: 11,
    fontWeight: '700',
  },
  stepText: {
    color: '#736C65',
    flex: 1,
    fontSize: 15,
    lineHeight: 21,
  },
  warnings: {
    backgroundColor: '#FBF4E8',
    borderColor: '#EEDFC7',
    borderRadius: 18,
    borderWidth: 1,
    gap: 8,
    padding: 12,
  },
  warningRow: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 8,
  },
  warningText: {
    color: '#76552D',
    flex: 1,
    fontSize: 14,
    lineHeight: 20,
  },
  footer: {
    backgroundColor: '#FFFEFC',
    gap: 8,
    paddingHorizontal: 18,
    paddingTop: 6,
    paddingBottom: 12,
    zIndex: 5,
  },
  footerLayer: {
    bottom: 0,
    left: 0,
    position: 'absolute',
    right: 0,
    zIndex: 5,
  },
  secondaryButton: {
    alignItems: 'center',
    backgroundColor: '#F4F1EC',
    borderColor: '#E3DED6',
    borderRadius: 999,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 7,
    justifyContent: 'center',
    paddingVertical: 13,
  },
  secondaryButtonText: {
    color: '#333333',
    fontSize: 14,
    fontWeight: '800',
  },
  button: {
    alignItems: 'center',
    backgroundColor: '#050505',
    borderRadius: 999,
    flexDirection: 'row',
    gap: 8,
    justifyContent: 'center',
    paddingVertical: 15,
  },
  buttonPressed: {
    opacity: 0.82,
  },
  buttonText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '800',
  },
});
