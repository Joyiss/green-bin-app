import { Ionicons, MaterialCommunityIcons } from '@expo/vector-icons';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import {
  Alert,
  Linking,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { isPreparationInstruction, type ResultSheetPresentation } from '@/app/result-sheet-model';
import { FREDOKA_TEXT_STYLES, INTER_TEXT_STYLES } from '@/constants/typography';

type ConfidentResultScreenProps = {
  bottomInset: number;
  children?: ReactNode;
  feedbackToastVisible?: boolean;
  onClose: () => void;
  onPrimaryAction?: () => void;
  presentation: ResultSheetPresentation;
  topInset: number;
};

const FONT = {
  bodyMedium: { ...INTER_TEXT_STYLES.medium, fontWeight: '500' as const },
  bodyRegular: { ...INTER_TEXT_STYLES.regular, fontWeight: '400' as const },
  bodySemiBold: { ...INTER_TEXT_STYLES.semiBold, fontWeight: '600' as const },
  headingMedium: { ...FREDOKA_TEXT_STYLES.medium, fontWeight: '500' as const },
  headingSemiBold: { ...FREDOKA_TEXT_STYLES.semiBold, fontWeight: '600' as const },
};

function comparisonText(value: string) {
  return value.toLocaleLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
}

function repeats(first?: string | null, second?: string | null) {
  if (!first || !second) return false;
  const left = comparisonText(first);
  const right = comparisonText(second);
  if (!left || !right) return false;
  return left === right || (Math.min(left.length, right.length) >= 30
    && (left.includes(right) || right.includes(left)));
}

function roleIcon(role: string): keyof typeof Ionicons.glyphMap {
  const normalized = role.toLocaleLowerCase();
  if (normalized.includes('official') || normalized.includes('agency')) return 'business-outline';
  if (normalized.includes('retail')) return 'bag-handle-outline';
  if (normalized.includes('provider')) return 'location-outline';
  return 'document-text-outline';
}

function cleanDisplayText(value?: string | null) {
  if (!value) return null;
  const cleaned = value
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '$1')
    .replace(/[*_`#>~]+/g, '')
    .replace(/^\s*[-+]\s+/gm, '')
    .replace(/\s+/g, ' ')
    .trim();
  return cleaned || null;
}

function firstSentence(value?: string | null) {
  const cleaned = cleanDisplayText(value);
  if (!cleaned) return null;
  const match = cleaned.match(/^(.{24,150}?[.!?])\s+/);
  if (match) return match[1].trim();
  return cleaned.length > 150 ? `${cleaned.slice(0, 147).trim()}...` : cleaned;
}

function disposalIcon(action: string, summary?: string | null): keyof typeof Ionicons.glyphMap {
  const value = `${action} ${summary ?? ''}`.toLocaleLowerCase();
  if (/donate|reuse|thrift|gift/.test(value)) return 'gift-outline';
  if (/compost|organics|green bin|yard waste/.test(value)) return 'leaf-outline';
  if (/trash|landfill|garbage/.test(value)) return 'trash-outline';
  if (/hazard|special|battery|chemical|paint|medicine|check local/.test(value)) return 'warning-outline';
  return 'refresh-outline';
}

function confidenceTone(value?: string | null) {
  const normalized = value?.toLocaleLowerCase() ?? '';
  if (normalized.includes('high')) {
    return { accent: '#2F8E6B', background: '#EEF9F3', icon: 'checkmark' as const };
  }
  return { accent: '#C77A1B', background: '#FFF5E6', icon: 'alert' as const };
}

function stepText(step: { body?: string; title: string }) {
  return [step.title, step.body].filter(Boolean).join(' ');
}

function meaningfulTerms(value?: string | null) {
  const ignored = new Set(['and', 'for', 'item', 'material', 'other', 'the', 'this', 'with']);
  return new Set(
    comparisonText(value ?? '')
      .split(' ')
      .filter((term) => term.length >= 4 && !ignored.has(term)),
  );
}

function warningApplies(warning: string, item: string, category?: string | null) {
  const warningTerms = meaningfulTerms(warning);
  const recognizedTerms = new Set([...meaningfulTerms(item), ...meaningfulTerms(category)]);
  if ([...recognizedTerms].some((term) => warningTerms.has(term))) return true;
  const commas = warning.match(/,/g)?.length ?? 0;
  const looksLikeUnrelatedList = commas >= 2 || /\b(such as|including|listed as)\b/i.test(warning);
  return !looksLikeUnrelatedList;
}

export function ConfidentResultScreen({
  bottomInset,
  children,
  feedbackToastVisible = false,
  onClose,
  onPrimaryAction,
  presentation,
  topInset,
}: ConfidentResultScreenProps) {
  const [referencesExpanded, setReferencesExpanded] = useState(false);
  const scrollRef = useRef<ScrollView>(null);
  const stepsY = useRef(0);

  useEffect(() => {
    setReferencesExpanded(false);
  }, [presentation.item]);

  const confidence = presentation.evidence?.rows.find(
    (row) => row.label.toLocaleLowerCase() === 'confidence',
  );
  const evidenceRows = presentation.evidence?.rows.filter(
    (row) => row !== confidence && row.label.toLocaleLowerCase() !== 'local route found',
  ) ?? [];
  const destination = cleanDisplayText(presentation.destinationLabel);
  const qualifier = firstSentence(presentation.keyQualifier);
  const methodIcon = disposalIcon(presentation.action, presentation.bestOption);
  const isRecycleAction = presentation.action.trim().toLocaleLowerCase() === 'recycle';
  const isDropOffAction = /drop\s*-?\s*off/i.test(presentation.action);
  const confidenceVisual = confidenceTone(confidence?.value);
  const category = presentation.status.find(
    (status) => status.label.toLocaleLowerCase() === 'category',
  )?.value;
  const location = presentation.status.find(
    (status) => status.label.toLocaleLowerCase() === 'location',
  )?.value.split(',')[0]?.trim();
  const metadata = [category, location].filter(Boolean) as string[];
  const preparationSteps = (presentation.preparationSteps ?? presentation.steps.filter(
    (step) => isPreparationInstruction(stepText(step)),
  )).filter((step) => ![step.title, step.body, stepText(step)].some((value) => repeats(value, qualifier)));
  const beforeYouGo = presentation.warnings
    .map(cleanDisplayText)
    .filter((value): value is string => Boolean(value))
    .filter((warning) => warningApplies(warning, presentation.item, category))
    .filter((warning) => ![
      presentation.action,
      presentation.bestOption,
      destination,
      qualifier,
    ].some((value) => repeats(warning, value)));
  const evidenceSummary = cleanDisplayText(presentation.evidence?.summary);

  const openReference = (url: string) => {
    Linking.openURL(url).catch(() => {
      Alert.alert('Unable to open source', 'Try opening the source in your browser.');
    });
  };

  const handlePrimaryAction = () => {
    if (presentation.primaryAction?.behavior === 'scroll_steps') {
      scrollRef.current?.scrollTo({ animated: true, y: Math.max(stepsY.current - 12, 0) });
      return;
    }
    onPrimaryAction?.();
  };

  return (
    <View style={styles.overlay} testID="confident-result-screen">
      <View style={[styles.safeAreaSpacer, { height: topInset }]} />
      <View style={styles.surface} testID="confident-result-surface">
        <ScrollView
          accessibilityLabel="Disposal guidance details"
          bounces={false}
          contentContainerStyle={[styles.content, { paddingBottom: bottomInset + 24 }]}
          ref={scrollRef}
          showsVerticalScrollIndicator={false}>
          <View style={styles.handle} />

          <View style={styles.headerRow}>
            <Text style={styles.pageTitle}>Disposal Details</Text>
            <View style={styles.headerActions}>
              <Pressable
                accessibilityLabel="Close scan result"
                accessibilityRole="button"
                hitSlop={6}
                onPress={onClose}
                style={({ pressed }) => [styles.headerButton, pressed && styles.pressed]}>
                <Ionicons color="#6F6A64" name="close" size={22} />
              </Pressable>
            </View>
          </View>

          <View style={styles.itemBlock}>
            <Text maxFontSizeMultiplier={1.25} selectable style={styles.itemName} testID="recognized-item">
              {presentation.item}
            </Text>
            {metadata.length ? (
              <Text maxFontSizeMultiplier={1.3} style={styles.itemMetadata} testID="compact-item-metadata">
                {metadata.join(' \u2022 ')}
              </Text>
            ) : null}
          </View>

          <View style={styles.summaryCard} testID="primary-summary-card">
            <View style={styles.summaryMain}>
              <View style={styles.methodIcon}>
                {isRecycleAction ? (
                  <MaterialCommunityIcons color="#11100F" name="recycle" size={28} />
                ) : isDropOffAction ? (
                  <MaterialCommunityIcons color="#11100F" name="package-variant-closed" size={27} />
                ) : (
                  <Ionicons color="#11100F" name={methodIcon} size={23} />
                )}
              </View>
              <Text maxFontSizeMultiplier={1.2} selectable style={styles.primaryAction} testID="summary-action">
                {presentation.action}
              </Text>
            </View>
            {destination ? (
              <Text
                maxFontSizeMultiplier={1.35}
                selectable
                style={styles.destinationLabel}
                testID="summary-destination">
                {destination}
              </Text>
            ) : null}
            {qualifier ? (
              <Text
                maxFontSizeMultiplier={1.4}
                selectable
                style={styles.summaryDescription}
                testID="summary-description">
                {qualifier}
              </Text>
            ) : null}
          </View>

          {preparationSteps.length ? (
            <View
              onLayout={({ nativeEvent }) => {
                stepsY.current = nativeEvent.layout.y;
              }}
              style={styles.section}
              testID="what-to-do-section">
              <Text style={styles.sectionHeading}>What to do</Text>
              <View style={styles.card}>
                {preparationSteps.map((step, index) => (
                  <View
                    key={`${step.title}-${index}`}
                    style={styles.stepRow}
                    testID={index === 0 ? 'first-guidance-step' : undefined}>
                    <View style={styles.stepNumber}>
                      <Text style={styles.stepNumberText}>{index + 1}</Text>
                    </View>
                    <View style={styles.stepCopy}>
                      <Text
                        maxFontSizeMultiplier={1.4}
                        selectable
                        style={[styles.stepTitle, !step.body && step.title.length > 64 && styles.stepLongText]}>
                        {cleanDisplayText(step.title)}
                      </Text>
                      {step.body ? (
                        <Text maxFontSizeMultiplier={1.45} selectable style={styles.stepBody}>
                          {cleanDisplayText(step.body)}
                        </Text>
                      ) : null}
                    </View>
                  </View>
                ))}
              </View>
            </View>
          ) : null}

          {!preparationSteps.length && presentation.noPreparationMessage ? (
            <View style={styles.section} testID="no-preparation-section">
              <Text style={styles.sectionHeading}>Preparation</Text>
              <View style={styles.card}>
                <Text maxFontSizeMultiplier={1.4} selectable style={styles.stepBody}>
                  {presentation.noPreparationMessage}
                </Text>
              </View>
            </View>
          ) : null}

          {beforeYouGo.length ? (
            <View style={styles.section}>
              <Text style={styles.sectionHeading}>Before you go</Text>
              <View style={styles.warningCard}>
                <View style={styles.warningIcon}>
                  <Ionicons color="#9B6B2D" name="warning-outline" size={17} />
                </View>
                <View style={styles.warningCopy}>
                  {beforeYouGo.map((warning, index) => (
                    <Text
                      key={`${warning}-${index}`}
                      maxFontSizeMultiplier={1.4}
                      selectable
                      style={styles.warningText}>
                      {warning}
                    </Text>
                  ))}
                </View>
              </View>
            </View>
          ) : null}

          {presentation.evidence ? (
            <View style={styles.section}>
              <Text style={styles.sectionHeading}>Why Green Bin recommends this</Text>
              <View style={styles.card}>
                {confidence ? (
                  <View style={styles.confidenceRow}>
                    <View
                      style={[
                        styles.confidenceRing,
                        {
                          backgroundColor: confidenceVisual.background,
                          borderColor: confidenceVisual.accent,
                        },
                      ]}>
                      <Ionicons color={confidenceVisual.accent} name={confidenceVisual.icon} size={16} />
                    </View>
                    <View>
                      <Text style={styles.confidenceLabel}>Confidence level</Text>
                      <Text style={[styles.confidenceValue, { color: confidenceVisual.accent }]}>
                        {cleanDisplayText(confidence.value)}
                      </Text>
                    </View>
                  </View>
                ) : null}
                {evidenceSummary ? (
                  <Text maxFontSizeMultiplier={1.4} selectable style={styles.evidenceSummary}>
                    {evidenceSummary}
                  </Text>
                ) : null}
                {evidenceRows.length ? (
                  <View style={styles.evidenceRows}>
                    {evidenceRows.map((row) => (
                      <View key={`${row.label}-${row.value}`} style={styles.evidenceRow}>
                        <Text style={styles.evidenceLabel}>{row.label}</Text>
                        <Text maxFontSizeMultiplier={1.35} selectable style={styles.evidenceValue}>
                          {cleanDisplayText(row.value)}
                        </Text>
                      </View>
                    ))}
                  </View>
                ) : null}
              </View>
            </View>
          ) : null}

          {presentation.references.length ? (
            <View style={styles.section}>
              <Text style={styles.sectionHeading}>References</Text>
              <Pressable
                accessibilityLabel="References"
                accessibilityRole="button"
                accessibilityState={{ expanded: referencesExpanded }}
                onPress={() => setReferencesExpanded((current) => !current)}
                style={({ pressed }) => [styles.referenceToggle, pressed && styles.pressed]}>
                <View style={styles.referencesAccent}>
                  <Ionicons color="#11100F" name="book-outline" size={18} />
                </View>
                <View style={styles.sourceIcons}>
                  {presentation.references.slice(0, 4).map((source, index) => (
                    <View
                      key={`${source.url}-${index}`}
                      style={[styles.sourceIcon, index > 0 && styles.sourceIconOverlap]}>
                      <Ionicons color="#11100F" name={roleIcon(source.role)} size={14} />
                    </View>
                  ))}
                </View>
                <Text style={styles.sourceCount}>
                  {presentation.references.length} {presentation.references.length === 1 ? 'source' : 'sources'}
                </Text>
                <Ionicons
                  color="#8C857D"
                  name={referencesExpanded ? 'chevron-up' : 'chevron-down'}
                  size={17}
                />
              </Pressable>
              {referencesExpanded ? (
                <View style={styles.referenceCards}>
                  {presentation.references.map((source) => (
                    <View key={source.url} style={styles.referenceCard}>
                      <Text selectable style={styles.referenceTitle}>{cleanDisplayText(source.title)}</Text>
                      <Text style={styles.referenceDomain}>{cleanDisplayText(source.domain)}</Text>
                      <Text style={styles.referenceRole}>{cleanDisplayText(source.role)}</Text>
                      {source.description ? (
                        <Text selectable style={styles.referenceDescription}>
                          {cleanDisplayText(source.description)}
                        </Text>
                      ) : null}
                      <Pressable
                        accessibilityLabel={`Open source: ${source.title}`}
                        accessibilityRole="link"
                        onPress={() => openReference(source.url)}
                        style={({ pressed }) => [styles.openSource, pressed && styles.pressed]}>
                        <Text style={styles.openSourceText}>Open Source</Text>
                        <Ionicons color="#11100F" name="open-outline" size={14} />
                      </Pressable>
                    </View>
                  ))}
                </View>
              ) : null}
            </View>
          ) : null}

          {children ? (
            <View style={styles.section}>
              {children}
            </View>
          ) : null}

          {presentation.primaryAction ? (
            <Pressable
              accessibilityRole="button"
              onPress={handlePrimaryAction}
              style={({ pressed }) => [styles.primaryButton, pressed && styles.pressed]}>
              <Text maxFontSizeMultiplier={1.2} style={styles.primaryButtonText}>
                {presentation.primaryAction.label}
              </Text>
            </Pressable>
          ) : null}
        </ScrollView>
        {feedbackToastVisible ? (
          <View
            accessibilityLiveRegion="polite"
            accessibilityRole="alert"
            pointerEvents="none"
            style={styles.feedbackToast}>
            <View style={styles.feedbackToastIcon}>
              <Ionicons color="#FFFFFF" name="checkmark" size={15} />
            </View>
            <Text style={styles.feedbackToastText}>Thank you for your feedback</Text>
          </View>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  overlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: '#050505',
    zIndex: 50,
  },
  safeAreaSpacer: {
    flexShrink: 0,
  },
  surface: {
    backgroundColor: '#FFFEFC',
    borderTopLeftRadius: 30,
    borderTopRightRadius: 30,
    flex: 1,
    overflow: 'hidden',
  },
  content: {
    paddingHorizontal: 20,
    paddingTop: 9,
  },
  handle: {
    alignSelf: 'center',
    backgroundColor: '#D8D2CB',
    borderRadius: 999,
    height: 5,
    width: 38,
  },
  headerRow: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 12,
    minHeight: 44,
  },
  pageTitle: {
    color: '#292725',
    flex: 1,
    fontSize: 16,
    lineHeight: 22,
    ...FONT.headingSemiBold,
  },
  headerActions: {
    flexDirection: 'row',
    gap: 8,
  },
  headerButton: {
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    borderColor: '#ECE6DF',
    borderRadius: 999,
    borderWidth: 1,
    height: 44,
    justifyContent: 'center',
    shadowColor: '#302B27',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.025,
    shadowRadius: 6,
    width: 44,
  },
  itemBlock: {
    marginTop: 18,
  },
  itemName: {
    color: '#11100F',
    fontSize: 26,
    lineHeight: 32,
    ...FONT.headingMedium,
  },
  itemMetadata: {
    color: '#8A847D',
    fontSize: 13,
    lineHeight: 18,
    marginTop: 5,
    ...FONT.bodyRegular,
  },
  summaryCard: {
    backgroundColor: '#FFFFFF',
    borderColor: '#E7E1D9',
    borderRadius: 23,
    borderWidth: 1,
    marginTop: 18,
    paddingHorizontal: 15,
    paddingVertical: 14,
    shadowColor: '#302B27',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.035,
    shadowRadius: 10,
  },
  summaryMain: {
    alignItems: 'center',
    gap: 5,
    justifyContent: 'center',
  },
  methodIcon: {
    alignItems: 'center',
    height: 31,
    justifyContent: 'center',
    width: 38,
  },
  primaryAction: {
    color: '#11100F',
    fontSize: 24,
    lineHeight: 30,
    ...FONT.headingSemiBold,
  },
  destinationLabel: {
    color: '#2F2C29',
    fontSize: 18,
    lineHeight: 24,
    marginTop: 10,
    textAlign: 'center',
    ...FONT.headingMedium,
  },
  summaryDescription: {
    color: '#77716A',
    fontSize: 13,
    lineHeight: 18,
    marginTop: 3,
    textAlign: 'center',
    ...FONT.bodyRegular,
  },
  section: {
    marginTop: 16,
  },
  sectionHeading: {
    color: '#817B74',
    fontSize: 16,
    lineHeight: 21,
    marginBottom: 10,
    ...FONT.headingMedium,
  },
  card: {
    backgroundColor: '#FFFFFF',
    borderColor: '#E7E1D9',
    borderRadius: 21,
    borderWidth: 1,
    gap: 10,
    padding: 13,
    shadowColor: '#302B27',
    shadowOffset: { width: 0, height: 3 },
    shadowOpacity: 0.02,
    shadowRadius: 8,
  },
  stepRow: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 10,
  },
  stepNumber: {
    alignItems: 'center',
    backgroundColor: '#F4F1EC',
    borderRadius: 999,
    height: 23,
    justifyContent: 'center',
    marginTop: 1,
    width: 23,
  },
  stepNumberText: {
    color: '#413D38',
    fontSize: 12,
    lineHeight: 16,
    ...FONT.bodyMedium,
  },
  stepCopy: {
    flex: 1,
  },
  stepTitle: {
    color: '#302D2A',
    fontSize: 13,
    lineHeight: 19,
    ...FONT.bodySemiBold,
  },
  stepLongText: {
    ...FONT.bodyRegular,
  },
  stepBody: {
    color: '#6C665F',
    fontSize: 13,
    lineHeight: 19,
    marginTop: 1,
    ...FONT.bodyRegular,
  },
  warningCard: {
    alignItems: 'flex-start',
    backgroundColor: '#FFF7EA',
    borderColor: '#E7C998',
    borderRadius: 21,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 8,
    padding: 13,
  },
  warningIcon: {
    paddingTop: 1,
  },
  warningCopy: {
    flex: 1,
    gap: 7,
  },
  warningText: {
    color: '#705533',
    fontSize: 13,
    lineHeight: 19,
    ...FONT.bodyRegular,
  },
  confidenceRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 10,
  },
  confidenceRing: {
    alignItems: 'center',
    borderColor: '#51A67C',
    borderRadius: 999,
    borderWidth: 2,
    height: 38,
    justifyContent: 'center',
    width: 38,
  },
  confidenceLabel: {
    color: '#928B84',
    fontSize: 12,
    lineHeight: 16,
    ...FONT.bodyRegular,
  },
  confidenceValue: {
    color: '#2F6B52',
    fontSize: 15,
    lineHeight: 20,
    textTransform: 'capitalize',
    ...FONT.bodySemiBold,
  },
  evidenceSummary: {
    color: '#3F3B37',
    fontSize: 14,
    lineHeight: 21,
    ...FONT.bodyRegular,
  },
  evidenceRows: {
    borderTopColor: '#ECE7E0',
    borderTopWidth: 1,
  },
  evidenceRow: {
    borderBottomColor: '#F1EDE8',
    borderBottomWidth: 1,
    gap: 2,
    paddingVertical: 7,
  },
  evidenceLabel: {
    color: '#928B84',
    fontSize: 12,
    lineHeight: 16,
    ...FONT.bodyRegular,
  },
  evidenceValue: {
    color: '#49443F',
    fontSize: 13,
    lineHeight: 19,
    ...FONT.bodyRegular,
  },
  referenceToggle: {
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    borderColor: '#E7E1D9',
    borderRadius: 22,
    borderWidth: 1,
    flexDirection: 'row',
    minHeight: 58,
    paddingHorizontal: 13,
  },
  referencesAccent: {
    alignItems: 'center',
    backgroundColor: '#FFFEFC',
    borderRadius: 999,
    height: 34,
    justifyContent: 'center',
    marginRight: 9,
    width: 34,
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
    height: 28,
    justifyContent: 'center',
    width: 28,
  },
  sourceIconOverlap: {
    marginLeft: -9,
  },
  sourceCount: {
    color: '#817B74',
    flex: 1,
    fontSize: 13,
    lineHeight: 18,
    marginLeft: 12,
    textAlign: 'right',
    ...FONT.bodyRegular,
  },
  referenceCards: {
    gap: 8,
    marginTop: 8,
  },
  referenceCard: {
    backgroundColor: '#FFFFFF',
    borderColor: '#E7E1D9',
    borderRadius: 18,
    borderWidth: 1,
    padding: 12,
  },
  referenceTitle: {
    color: '#302D2A',
    fontSize: 15,
    lineHeight: 21,
    ...FONT.bodySemiBold,
  },
  referenceDomain: {
    color: '#928B84',
    fontSize: 12,
    lineHeight: 16,
    marginTop: 2,
    ...FONT.bodyRegular,
  },
  referenceRole: {
    alignSelf: 'flex-start',
    backgroundColor: '#F3EFEA',
    borderRadius: 999,
    color: '#625D57',
    fontSize: 12,
    lineHeight: 16,
    marginTop: 7,
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 3,
    ...FONT.bodyMedium,
  },
  referenceDescription: {
    color: '#625D57',
    fontSize: 13,
    lineHeight: 19,
    marginTop: 6,
    ...FONT.bodyRegular,
  },
  openSource: {
    alignItems: 'center',
    alignSelf: 'flex-start',
    flexDirection: 'row',
    gap: 6,
    marginTop: 9,
    paddingVertical: 3,
  },
  openSourceText: {
    color: '#2F6B52',
    fontSize: 13,
    lineHeight: 18,
    ...FONT.bodySemiBold,
  },
  feedbackToast: {
    alignItems: 'center',
    alignSelf: 'center',
    backgroundColor: '#FFFEFC',
    borderColor: '#DDE9E1',
    borderRadius: 999,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 9,
    left: 20,
    paddingHorizontal: 14,
    paddingVertical: 10,
    position: 'absolute',
    right: 20,
    shadowColor: '#1D3529',
    shadowOffset: { width: 0, height: 5 },
    shadowOpacity: 0.16,
    shadowRadius: 14,
    top: 12,
    elevation: 8,
  },
  feedbackToastIcon: {
    alignItems: 'center',
    backgroundColor: '#2F8E6B',
    borderRadius: 999,
    height: 24,
    justifyContent: 'center',
    width: 24,
  },
  feedbackToastText: {
    color: '#2D4338',
    flex: 1,
    fontSize: 13,
    lineHeight: 18,
    ...FONT.bodySemiBold,
  },
  primaryButton: {
    alignItems: 'center',
    backgroundColor: '#11100F',
    borderRadius: 999,
    height: 52,
    justifyContent: 'center',
    marginTop: 24,
    paddingHorizontal: 18,
  },
  primaryButtonText: {
    color: '#FFFFFF',
    fontSize: 16,
    lineHeight: 20,
    textAlign: 'center',
    ...FONT.bodySemiBold,
  },
  pressed: {
    opacity: 0.78,
  },
});
