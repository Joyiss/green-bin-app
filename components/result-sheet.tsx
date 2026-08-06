import { Ionicons } from '@expo/vector-icons';
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import {
  Alert,
  Linking,
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

import {
  MANROPE_TEXT_STYLES,
  PRIMARY_TEXT_STYLES,
  SECONDARY_TEXT_STYLES,
} from '@/constants/typography';
import type { ResultSheetPresentation } from '@/app/result-sheet-model';

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
const GUIDANCE_FONT = {
  bold: { ...MANROPE_TEXT_STYLES.bold, fontWeight: '700' as const },
  medium: { ...MANROPE_TEXT_STYLES.medium, fontWeight: '500' as const },
  regular: { ...MANROPE_TEXT_STYLES.regular, fontWeight: '400' as const },
  semiBold: { ...MANROPE_TEXT_STYLES.semiBold, fontWeight: '600' as const },
};

function comparisonText(value: string) {
  return value.toLocaleLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
}

function repeatsText(first?: string | null, second?: string | null) {
  if (!first || !second) return false;
  const left = comparisonText(first);
  const right = comparisonText(second);
  if (!left || !right) return false;
  return left === right || (Math.min(left.length, right.length) >= 32
    && (left.includes(right) || right.includes(left)));
}

function isShortRouteTitle(value?: string | null) {
  if (!value || value.length > 72 || /[.!?]/.test(value)) return false;
  return value.trim().split(/\s+/).length <= 10;
}

function userFacingStatusValue(label: string, value: string) {
  const normalizedLabel = label.toLocaleLowerCase();
  const normalizedValue = value.toLocaleLowerCase();
  if (/required|match|confidence/.test(normalizedLabel)) return null;
  if (normalizedLabel === 'guidance') {
    if (normalizedValue.includes('local guidance')) return 'Local guidance';
    if (normalizedValue.includes('location check')) return null;
  }
  return value;
}

function isUsefulQuickFact(label: string) {
  return !/confidence|location required|preparation/i.test(label);
}

type ResultSheetDisplayMode = 'expandable' | 'static';
type ResultSheetViewState = 'expanded' | 'collapsed';

type ResultSheetProps = {
  label: string;
  title: string;
  materialTag?: string | null;
  summary: string;
  steps: string[];
  warnings?: string[];
  guidanceMetadata?: Record<string, unknown> | null;
  guidanceSource?: string;
  guidancePresentation?: ResultSheetPresentation;
  displayMode?: ResultSheetDisplayMode;
  keyboardShouldPersistTaps?: ScrollViewProps['keyboardShouldPersistTaps'];

  buttonLabel?: string;
  buttonIconName?: keyof typeof Ionicons.glyphMap;
  onButtonPress?: () => void;

  secondaryButtonLabel?: string;
  secondaryButtonIconName?: keyof typeof Ionicons.glyphMap;
  onSecondaryButtonPress?: () => void;
  onClose?: () => void;

  children?: ReactNode;
};

export function ResultSheet({
  label,
  title,
  materialTag,
  summary,
  steps,
  warnings = [],
  guidancePresentation,
  displayMode = 'static',
  keyboardShouldPersistTaps,
  buttonLabel,
  buttonIconName = 'location-outline',
  onButtonPress,
  secondaryButtonLabel,
  secondaryButtonIconName = 'swap-horizontal-outline',
  onSecondaryButtonPress,
  onClose,
  children,
}: ResultSheetProps) {
  // Collapse is local presentation state; full close/reset still belongs to the outer close button.
  const [sheetDisplayState, setSheetDisplayState] = useState<ResultSheetViewState>('expanded');
  const showSecondaryButton = secondaryButtonLabel && onSecondaryButtonPress;
  const showPrimaryButton = guidancePresentation?.primaryAction
    ? guidancePresentation.primaryAction.behavior === 'scroll_steps' || Boolean(onButtonPress)
    : buttonLabel && onButtonPress;
  const isExpandable = displayMode === 'expandable';
  const isCollapsed = isExpandable && sheetDisplayState === 'collapsed';
  const [expandedSheetHeight, setExpandedSheetHeight] = useState(0);
  const [headerHeight, setHeaderHeight] = useState(0);
  const [footerHeight, setFooterHeight] = useState(0);
  const [referencesExpanded, setReferencesExpanded] = useState(false);
  const scrollRef = useRef<ScrollView>(null);
  const whatToDoY = useRef(0);
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
    setReferencesExpanded(false);
  }, [guidancePresentation?.item]);

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

          if (currentState === SHEET_STATE_EXPANDED) {
            if (IS_ANDROID && event.velocityY > ANDROID_SHEET_VELOCITY_THRESHOLD) {
              targetState = SHEET_STATE_COLLAPSED;
            } else if (
              event.translationY >=
              (IS_ANDROID ? ANDROID_SHEET_COLLAPSE_THRESHOLD : SHEET_COLLAPSE_THRESHOLD)
            ) {
              targetState = SHEET_STATE_COLLAPSED;
            }
          }

          if (currentState === SHEET_STATE_COLLAPSED) {
            if (IS_ANDROID && event.velocityY < -ANDROID_SHEET_VELOCITY_THRESHOLD) {
              targetState = SHEET_STATE_EXPANDED;
            } else if (
              event.translationY <=
              -(IS_ANDROID ? ANDROID_SHEET_COLLAPSE_THRESHOLD : SHEET_COLLAPSE_THRESHOLD)
            ) {
              targetState = SHEET_STATE_EXPANDED;
            }
          }

          const targetHeight =
            targetState === SHEET_STATE_COLLAPSED
              ? collapsedHeightValue.value
              : expandedHeightValue.value;
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

  const visibleStatus = guidancePresentation?.status
    .map((status) => userFacingStatusValue(status.label, status.value))
    .filter((value): value is string => Boolean(value)) ?? [];

  const guidanceHeader = guidancePresentation ? (
    <View style={styles.guidanceHeader} testID="confident-result-header">
      <View style={[styles.handle, styles.guidanceHandle]} />
      <View style={styles.guidanceTopRow}>
        <Text maxFontSizeMultiplier={1.3} style={styles.guidanceScreenTitle}>
          Disposal details
        </Text>
        <View style={styles.guidanceHeaderActions}>
          {showSecondaryButton ? (
            <Pressable
              accessibilityRole="button"
              onPress={onSecondaryButtonPress}
              style={({ pressed }) => [
                styles.headerChangeItem,
                pressed && styles.buttonPressed,
              ]}>
              <Text maxFontSizeMultiplier={1.2} style={styles.headerChangeItemText}>
                Change Item
              </Text>
            </Pressable>
          ) : null}
          {onClose ? (
            <Pressable
              accessibilityLabel="Close scan result"
              accessibilityRole="button"
              hitSlop={8}
              onPress={onClose}
              style={({ pressed }) => [styles.sheetCloseButton, pressed && styles.buttonPressed]}>
              <Ionicons color="#3F4642" name="close" size={20} />
            </Pressable>
          ) : null}
        </View>
      </View>
      <Text maxFontSizeMultiplier={1.3} selectable style={styles.itemName} testID="recognized-item">
        {guidancePresentation.item}
      </Text>
      {visibleStatus.length ? (
        <View style={styles.statusRow} testID="compact-status-row">
          {visibleStatus.map((value, index) => (
            <View key={`${value}-${index}`} style={styles.statusItem}>
              {index > 0 ? <Text style={styles.statusSeparator}>·</Text> : null}
              <Text maxFontSizeMultiplier={1.3} style={styles.statusValue}>
                {value}
              </Text>
            </View>
          ))}
        </View>
      ) : null}
    </View>
  ) : null;

  const headerContent = guidanceHeader ?? (
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

  const openReference = (url: string) => {
    Linking.openURL(url).catch(() => {
      Alert.alert('Unable to open source', 'Try opening the source in your browser.');
    });
  };

  const confidenceRow = guidancePresentation?.evidence?.rows.find(
    (row) => row.label.toLocaleLowerCase() === 'confidence',
  );
  const localRouteRow = guidancePresentation?.evidence?.rows.find(
    (row) => row.label.toLocaleLowerCase() === 'local route found',
  );
  const evidenceRows = guidancePresentation?.evidence?.rows.filter(
    (row) => row !== confidenceRow && row !== localRouteRow,
  ) ?? [];
  const localRoute = localRouteRow?.value ?? null;
  const routeTitle = isShortRouteTitle(localRoute) ? localRoute : null;
  const routeDescription = localRoute && !routeTitle ? localRoute : null;
  const optionDescription = guidancePresentation
    && !repeatsText(guidancePresentation.bestOption, guidancePresentation.action)
    && !repeatsText(guidancePresentation.bestOption, localRoute)
    ? guidancePresentation.bestOption
    : null;
  const visibleFacts = guidancePresentation?.facts
    .filter((fact) => isUsefulQuickFact(fact.label))
    .slice(0, 3) ?? [];

  const guidanceDetails = guidancePresentation ? (
    <>
      <View style={styles.bestOptionCard} testID="best-option-card">
        <Text style={styles.cardEyebrow}>Best option</Text>
        <Text
          maxFontSizeMultiplier={1.2}
          selectable
          style={styles.bestOptionAction}
          testID="best-option-action">
          {guidancePresentation.action}
        </Text>
        {routeTitle ? (
          <Text maxFontSizeMultiplier={1.35} selectable style={styles.bestOptionTitle}>
            {routeTitle}
          </Text>
        ) : null}
        {routeDescription ? (
          <Text maxFontSizeMultiplier={1.45} selectable style={styles.bestOptionDescription}>
            {routeDescription}
          </Text>
        ) : null}
        {optionDescription ? (
          <Text
            maxFontSizeMultiplier={1.45}
            selectable
            style={styles.bestOptionDescription}
            testID="best-option-text">
            {optionDescription}
          </Text>
        ) : null}
        {visibleFacts.length ? (
          <View style={styles.quickFactsRow}>
            {visibleFacts.map((fact) => (
              <View key={`${fact.label}-${fact.value}`} style={styles.quickFact}>
                <Text maxFontSizeMultiplier={1.3} style={styles.quickFactLabel}>{fact.label}</Text>
                <Text maxFontSizeMultiplier={1.3} selectable style={styles.quickFactValue}>
                  {fact.value}
                </Text>
              </View>
            ))}
          </View>
        ) : null}
      </View>

      {guidancePresentation.steps.length ? (
        <View
          onLayout={({ nativeEvent }) => {
            whatToDoY.current = nativeEvent.layout.y;
          }}
          testID="what-to-do-section">
          <Text style={styles.sectionHeading}>What to do</Text>
          <View style={styles.sectionCard}>
            {guidancePresentation.steps.map((step, index) => (
              <View
                key={`${step.title}-${index}`}
                style={styles.guidanceStepRow}
                testID={index === 0 ? 'first-guidance-step' : undefined}>
                <View style={styles.guidanceStepIndex}>
                  <Text style={styles.guidanceStepIndexText}>{index + 1}</Text>
                </View>
                <View style={styles.guidanceStepCopy}>
                  <Text
                    maxFontSizeMultiplier={1.4}
                    selectable
                    style={[
                      styles.guidanceStepTitle,
                      !step.body && step.title.length > 64 && styles.guidanceStepLongText,
                    ]}>
                    {step.title}
                  </Text>
                  {step.body ? (
                    <Text maxFontSizeMultiplier={1.5} selectable style={styles.guidanceStepBody}>
                      {step.body}
                    </Text>
                  ) : null}
                </View>
              </View>
            ))}
          </View>
        </View>
      ) : null}

      {guidancePresentation.warnings.length ? (
        <View>
          <Text style={styles.sectionHeading}>Important note</Text>
          <View style={styles.guidanceWarnings}>
            {guidancePresentation.warnings.map((warning, index) => (
              <View key={`${warning}-${index}`} style={styles.warningRow}>
                <Ionicons color="#8A6434" name="warning-outline" size={18} />
                <Text selectable style={[styles.warningText, styles.guidanceWarningText]}>
                  {warning}
                </Text>
              </View>
            ))}
          </View>
        </View>
      ) : null}

      {guidancePresentation.evidence ? (
        <View>
          <Text style={styles.sectionHeading}>Why Green Bin recommends this</Text>
          <View style={styles.sectionCard}>
            {confidenceRow ? (
              <View style={styles.confidenceRow}>
                <View style={styles.confidenceIndicator}>
                  <Ionicons color="#2F6B52" name="checkmark" size={15} />
                </View>
                <View>
                  <Text style={styles.confidenceLabel}>Confidence</Text>
                  <Text style={styles.confidenceValue}>{confidenceRow.value}</Text>
                </View>
              </View>
            ) : null}
            {guidancePresentation.evidence.summary ? (
              <Text maxFontSizeMultiplier={1.5} selectable style={styles.evidenceSummary}>
                {guidancePresentation.evidence.summary}
              </Text>
            ) : null}
            {evidenceRows.length ? (
              <View style={styles.evidenceRows}>
                {evidenceRows.map((row) => (
                  <View key={`${row.label}-${row.value}`} style={styles.evidenceRow}>
                    <Text style={styles.evidenceLabel}>{row.label}</Text>
                    <Text maxFontSizeMultiplier={1.4} selectable style={styles.evidenceValue}>
                      {row.value}
                    </Text>
                  </View>
                ))}
              </View>
            ) : null}
          </View>
        </View>
      ) : null}

      {guidancePresentation.references.length ? (
        <View>
          <Text style={styles.sectionHeading}>References</Text>
          <Pressable
            accessibilityLabel="References"
            accessibilityRole="button"
            accessibilityState={{ expanded: referencesExpanded }}
            onPress={() => setReferencesExpanded((current) => !current)}
            style={({ pressed }) => [styles.referencesToggle, pressed && styles.buttonPressed]}>
            <View style={styles.sourceIcons}>
              {guidancePresentation.references.slice(0, 4).map((reference, index) => (
                <View
                  key={`${reference.url}-${index}`}
                  style={[styles.sourceIcon, index > 0 && styles.sourceIconOverlap]}>
                  <Ionicons color="#11100F" name="document-text-outline" size={15} />
                </View>
              ))}
            </View>
            <Text style={styles.referenceCount}>
              {guidancePresentation.references.length}{' '}
              {guidancePresentation.references.length === 1 ? 'source' : 'sources'}
            </Text>
            <Ionicons
              color="#807B75"
              name={referencesExpanded ? 'chevron-up' : 'chevron-down'}
              size={18}
            />
          </Pressable>
          {referencesExpanded ? (
            <View style={styles.referenceCards}>
              {guidancePresentation.references.map((reference) => (
                <View key={reference.url} style={styles.referenceCard}>
                  <Text selectable style={styles.referenceTitle}>{reference.title}</Text>
                  <Text style={styles.referenceDomain}>{reference.domain}</Text>
                  <Text style={styles.referenceRole}>{reference.role}</Text>
                  {reference.description ? (
                    <Text selectable style={styles.referenceDescription}>
                      {reference.description}
                    </Text>
                  ) : null}
                  <Pressable
                    accessibilityLabel={`Open source: ${reference.title}`}
                    accessibilityRole="link"
                    onPress={() => openReference(reference.url)}
                    style={({ pressed }) => [styles.openSource, pressed && styles.buttonPressed]}>
                    <Text style={styles.openSourceText}>Open source</Text>
                    <Ionicons color="#11100F" name="open-outline" size={15} />
                  </Pressable>
                </View>
              ))}
            </View>
          ) : null}
        </View>
      ) : null}

      {children ? (
        <View>
          {children}
        </View>
      ) : null}
    </>
  ) : null;

  const detailsContent = (
    <View
      pointerEvents={isCollapsed ? 'none' : 'auto'}
      style={[styles.detailsRegion, isCollapsed && styles.detailsRegionCollapsed]}>
      <ScrollView
        accessibilityLabel={guidancePresentation ? 'Disposal guidance details' : undefined}
        bounces={false}
        contentContainerStyle={[
          styles.bodyContent,
          guidancePresentation && styles.guidanceBodyContent,
        ]}
        keyboardShouldPersistTaps={keyboardShouldPersistTaps}
        nestedScrollEnabled
        ref={scrollRef}
        showsVerticalScrollIndicator={false}
        style={styles.body}>
        {guidanceDetails ?? (
          <>
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
          </>
        )}
      </ScrollView>
    </View>
  );

  const footerContent = (showPrimaryButton || (!guidancePresentation && showSecondaryButton)) ? (
    <View
      onLayout={handleFooterLayout}
      style={[styles.footer, guidancePresentation && styles.guidanceFooter]}>
      <>
          {!guidancePresentation && showSecondaryButton ? (
            <Pressable
              accessibilityRole="button"
              onPress={onSecondaryButtonPress}
              style={({ pressed }) => [
                styles.secondaryButton,
                guidancePresentation && styles.guidanceSecondaryButton,
                pressed && styles.buttonPressed,
              ]}>
              <Ionicons color="#333333" name={secondaryButtonIconName} size={17} />
              <Text
                maxFontSizeMultiplier={guidancePresentation ? 1.2 : undefined}
                numberOfLines={guidancePresentation ? 1 : undefined}
                style={[
                  styles.secondaryButtonText,
                  guidancePresentation && styles.guidanceSecondaryButtonText,
                ]}>
                {secondaryButtonLabel}
              </Text>
            </Pressable>
          ) : null}

          {showPrimaryButton ? (
            <Pressable
              accessibilityLabel={guidancePresentation?.primaryAction?.label ?? buttonLabel}
              accessibilityRole="button"
              onPress={() => {
                if (guidancePresentation?.primaryAction?.behavior === 'scroll_steps') {
                  scrollRef.current?.scrollTo({ animated: true, y: Math.max(whatToDoY.current - 8, 0) });
                  return;
                }
                onButtonPress?.();
              }}
              style={({ pressed }) => [
                styles.button,
                guidancePresentation && styles.guidancePrimaryButton,
                pressed && styles.buttonPressed,
              ]}>
              <Ionicons
                color="#FFFFFF"
                name={guidancePresentation?.primaryAction?.behavior === 'scroll_steps'
                  ? 'list-outline'
                  : buttonIconName}
                size={18}
              />
              <Text
                maxFontSizeMultiplier={guidancePresentation ? 1.2 : undefined}
                numberOfLines={guidancePresentation ? 2 : undefined}
                style={[styles.buttonText, guidancePresentation && styles.guidanceButtonText]}>
                {guidancePresentation?.primaryAction?.label ?? buttonLabel}
              </Text>
            </Pressable>
          ) : null}
      </>
    </View>
  ) : null;

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
        guidancePresentation && styles.guidanceFill,
        hasMeasuredExpandableLayout && expandableSheetStyle,
      ]}>
      <View style={[styles.sheetClip, styles.expandableSheetClip]}>
        <View
          onLayout={handleExpandedSheetLayout}
          pointerEvents="none"
          style={[styles.expandedMeasure, guidancePresentation && styles.guidanceExpandedMeasure]}>
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
  guidanceFill: {
    height: '100%',
  },
  expandableSheetClip: {
    flex: 1,
    minHeight: 0,
    position: 'relative',
  },
  expandedMeasure: {
    opacity: 0,
  },
  guidanceExpandedMeasure: {
    minHeight: '100%',
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
  guidanceHeader: {
    backgroundColor: '#FFFCF8',
    paddingBottom: 10,
    paddingHorizontal: 21,
    paddingTop: 8,
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
  guidanceHandle: {
    marginBottom: 7,
  },
  guidanceTopRow: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    minHeight: 42,
  },
  guidanceScreenTitle: {
    color: '#3C3935',
    flex: 1,
    fontSize: 16,
    lineHeight: 22,
    ...GUIDANCE_FONT.semiBold,
  },
  guidanceHeaderActions: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 7,
  },
  headerChangeItem: {
    alignItems: 'center',
    minHeight: 40,
    justifyContent: 'center',
    paddingHorizontal: 7,
  },
  headerChangeItemText: {
    color: '#68625C',
    fontSize: 14,
    lineHeight: 20,
    ...GUIDANCE_FONT.medium,
  },
  sheetCloseButton: {
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    borderColor: '#E7E1D9',
    borderRadius: 999,
    borderWidth: 1,
    height: 42,
    justifyContent: 'center',
    shadowColor: '#302B27',
    shadowOffset: { width: 0, height: 3 },
    shadowOpacity: 0.04,
    shadowRadius: 8,
    width: 42,
  },
  itemName: {
    color: '#171614',
    fontSize: 29,
    letterSpacing: -0.7,
    lineHeight: 36,
    marginTop: 6,
    ...GUIDANCE_FONT.semiBold,
  },
  statusRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginTop: 5,
  },
  statusItem: {
    alignItems: 'center',
    flexDirection: 'row',
    maxWidth: '100%',
  },
  statusValue: {
    color: '#77716B',
    fontSize: 14,
    lineHeight: 20,
    ...GUIDANCE_FONT.regular,
  },
  statusSeparator: {
    color: '#B1AAA2',
    fontSize: 14,
    lineHeight: 20,
    paddingHorizontal: 6,
    ...GUIDANCE_FONT.regular,
  },
  eyebrow: {
    color: '#9A948C',
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 2,
    textAlign: 'center',
    ...PRIMARY_TEXT_STYLES.label,
  },
  title: {
    color: '#050505',
    fontSize: 32,
    fontWeight: '900',
    letterSpacing: -1.3,
    textAlign: 'center',
    marginBottom: 10,
    marginTop: 8,
    ...PRIMARY_TEXT_STYLES.header,
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
    ...SECONDARY_TEXT_STYLES.bold,
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
    gap: 22,
    paddingBottom: 20,
    paddingHorizontal: 18,
    paddingTop: 4,
  },
  guidanceBodyContent: {
    gap: 23,
    paddingBottom: 17,
    paddingHorizontal: 21,
    paddingTop: 4,
  },
  bestOptionCard: {
    backgroundColor: '#FFFFFF',
    borderColor: '#E6E0D8',
    borderRadius: 24,
    borderWidth: 1,
    gap: 8,
    padding: 17,
    shadowColor: '#2B332F',
    shadowOffset: { width: 0, height: 5 },
    shadowOpacity: 0.035,
    shadowRadius: 12,
  },
  cardEyebrow: {
    color: '#817B74',
    fontSize: 12,
    letterSpacing: 0.35,
    lineHeight: 17,
    ...GUIDANCE_FONT.medium,
  },
  bestOptionAction: {
    color: '#11100F',
    fontSize: 36,
    letterSpacing: -1.1,
    lineHeight: 42,
    ...GUIDANCE_FONT.bold,
  },
  bestOptionTitle: {
    color: '#282522',
    fontSize: 21,
    lineHeight: 28,
    ...GUIDANCE_FONT.semiBold,
  },
  bestOptionDescription: {
    color: '#3F3B37',
    fontSize: 16,
    lineHeight: 24,
    ...GUIDANCE_FONT.regular,
  },
  quickFactsRow: {
    borderTopColor: '#ECE7E0',
    borderTopWidth: 1,
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginTop: 2,
    paddingTop: 11,
  },
  quickFact: {
    flexGrow: 1,
    flexShrink: 1,
    minWidth: 86,
  },
  quickFactLabel: {
    color: '#8A847D',
    fontSize: 13,
    lineHeight: 19,
    ...GUIDANCE_FONT.regular,
  },
  quickFactValue: {
    color: '#393632',
    fontSize: 15,
    lineHeight: 21,
    marginTop: 1,
    ...GUIDANCE_FONT.semiBold,
  },
  sectionHeading: {
    color: '#77716B',
    fontSize: 18.5,
    lineHeight: 24,
    marginBottom: 11,
    ...GUIDANCE_FONT.semiBold,
  },
  sectionCard: {
    backgroundColor: '#FFFFFF',
    borderColor: '#E7E1D9',
    borderRadius: 24,
    borderWidth: 1,
    gap: 14,
    padding: 17,
    shadowColor: '#2B332F',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.025,
    shadowRadius: 10,
  },
  guidanceStepRow: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 12,
  },
  guidanceStepIndex: {
    alignItems: 'center',
    backgroundColor: '#F4F0EA',
    borderRadius: 999,
    height: 26,
    justifyContent: 'center',
    marginTop: 1,
    width: 26,
  },
  guidanceStepIndexText: {
    color: '#2F6B52',
    fontSize: 12,
    ...GUIDANCE_FONT.semiBold,
  },
  guidanceStepCopy: {
    flex: 1,
  },
  guidanceStepTitle: {
    color: '#252A27',
    fontSize: 16,
    lineHeight: 24,
    ...GUIDANCE_FONT.semiBold,
  },
  guidanceStepLongText: {
    ...GUIDANCE_FONT.regular,
  },
  guidanceStepBody: {
    color: '#625D57',
    fontSize: 16,
    lineHeight: 24,
    marginTop: 2,
    ...GUIDANCE_FONT.regular,
  },
  guidanceWarnings: {
    backgroundColor: '#FFFDF9',
    borderColor: '#E8DED0',
    borderRadius: 22,
    borderWidth: 1,
    gap: 10,
    padding: 15,
  },
  confidenceRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 10,
  },
  confidenceIndicator: {
    alignItems: 'center',
    borderColor: '#69A88B',
    borderRadius: 999,
    borderWidth: 2,
    height: 38,
    justifyContent: 'center',
    width: 38,
  },
  confidenceLabel: {
    color: '#8A847D',
    fontSize: 13,
    lineHeight: 17,
    ...GUIDANCE_FONT.regular,
  },
  confidenceValue: {
    color: '#2F6B52',
    fontSize: 16,
    lineHeight: 20,
    textTransform: 'capitalize',
    ...GUIDANCE_FONT.semiBold,
  },
  evidenceSummary: {
    color: '#3C3935',
    fontSize: 16,
    lineHeight: 25,
    ...GUIDANCE_FONT.regular,
  },
  evidenceRows: {
    borderTopColor: '#ECE7E0',
    borderTopWidth: 1,
  },
  evidenceRow: {
    borderBottomColor: '#F0ECE6',
    borderBottomWidth: 1,
    gap: 4,
    paddingVertical: 9,
  },
  evidenceLabel: {
    color: '#8C857D',
    fontSize: 13,
    lineHeight: 18,
    ...GUIDANCE_FONT.regular,
  },
  evidenceValue: {
    color: '#333834',
    fontSize: 15,
    lineHeight: 22,
    ...GUIDANCE_FONT.regular,
  },
  referencesToggle: {
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    borderColor: '#E7E1D9',
    borderRadius: 24,
    borderWidth: 1,
    flexDirection: 'row',
    minHeight: 66,
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  sourceIcons: {
    flexDirection: 'row',
  },
  sourceIcon: {
    alignItems: 'center',
    backgroundColor: '#FFFEFC',
    borderColor: '#FFFFFF',
    borderRadius: 999,
    borderWidth: 2,
    height: 30,
    justifyContent: 'center',
    width: 30,
  },
  sourceIconOverlap: {
    marginLeft: -9,
  },
  referenceCount: {
    color: '#716B65',
    flex: 1,
    fontSize: 14,
    marginLeft: 12,
    textAlign: 'right',
    ...GUIDANCE_FONT.regular,
  },
  referenceCards: {
    gap: 10,
    marginTop: 10,
  },
  referenceCard: {
    backgroundColor: '#FFFFFF',
    borderColor: '#E7E1D9',
    borderRadius: 18,
    borderWidth: 1,
    padding: 14,
  },
  referenceTitle: {
    color: '#252A27',
    fontSize: 15,
    lineHeight: 21,
    ...GUIDANCE_FONT.semiBold,
  },
  referenceDomain: {
    color: '#8C857D',
    fontSize: 12,
    marginTop: 2,
    ...GUIDANCE_FONT.regular,
  },
  referenceRole: {
    alignSelf: 'flex-start',
    backgroundColor: '#F3EFEA',
    borderRadius: 999,
    color: '#625D57',
    fontSize: 12,
    marginTop: 8,
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 4,
    ...GUIDANCE_FONT.regular,
  },
  referenceDescription: {
    color: '#67615B',
    fontSize: 15,
    lineHeight: 22,
    marginTop: 6,
    ...GUIDANCE_FONT.regular,
  },
  openSource: {
    alignItems: 'center',
    alignSelf: 'flex-start',
    flexDirection: 'row',
    gap: 6,
    marginTop: 10,
    paddingVertical: 3,
  },
  openSourceText: {
    color: '#2F6B52',
    fontSize: 14,
    ...GUIDANCE_FONT.semiBold,
  },
  summary: {
    color: '#66605B',
    fontSize: 14,
    lineHeight: 21,
    textAlign: 'center',
    ...SECONDARY_TEXT_STYLES.regular,
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
    ...SECONDARY_TEXT_STYLES.bold,
  },
  stepText: {
    color: '#736C65',
    flex: 1,
    fontSize: 15,
    lineHeight: 21,
    ...SECONDARY_TEXT_STYLES.regular,
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
    ...SECONDARY_TEXT_STYLES.regular,
  },
  guidanceWarningText: {
    fontSize: 16,
    lineHeight: 24,
    ...GUIDANCE_FONT.regular,
  },
  footer: {
    backgroundColor: '#FFFEFC',
    gap: 8,
    paddingHorizontal: 18,
    paddingTop: 6,
    paddingBottom: 12,
    zIndex: 5,
  },
  guidanceFooter: {
    paddingBottom: 6,
    paddingHorizontal: 21,
    paddingTop: 3,
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
    ...PRIMARY_TEXT_STYLES.button,
  },
  guidanceSecondaryButton: {
    minHeight: 55,
    paddingHorizontal: 12,
    paddingVertical: 0,
    width: 118,
  },
  guidanceSecondaryButtonText: {
    fontSize: 16,
    fontWeight: '600',
    ...PRIMARY_TEXT_STYLES.label,
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
  guidancePrimaryButton: {
    minHeight: 54,
    paddingHorizontal: 16,
    paddingVertical: 0,
  },
  buttonPressed: {
    opacity: 0.82,
  },
  buttonText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '800',
    ...PRIMARY_TEXT_STYLES.button,
  },
  guidanceButtonText: {
    fontSize: 17,
    lineHeight: 22,
    textAlign: 'center',
    ...GUIDANCE_FONT.bold,
  },
});
