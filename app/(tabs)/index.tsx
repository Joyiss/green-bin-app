import { Ionicons } from '@expo/vector-icons';
import MaskedView from '@react-native-masked-view/masked-view';
import { CameraView, useCameraPermissions } from 'expo-camera';
import * as ImagePicker from 'expo-image-picker';
import { LinearGradient } from 'expo-linear-gradient';
import { useIsFocused } from '@react-navigation/native';
import { useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Animated,
  Image,
  Keyboard,
  LayoutChangeEvent,
  Linking,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
  useWindowDimensions,
} from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import Reanimated, {
  Easing,
  FadeIn,
  FadeOut,
  cancelAnimation,
  interpolate,
  useAnimatedStyle,
  useSharedValue,
  withDelay,
  withRepeat,
  withSequence,
  withTiming,
} from 'react-native-reanimated';

import {
  BOTTOM_NAV_BAR_HEIGHT,
  BOTTOM_NAV_BAR_MIN_BOTTOM_OFFSET,
  BOTTOM_NAV_BAR_TOTAL_HEIGHT,
} from '@/components/bottom-nav-bar';
import { ResultSheet } from '@/components/result-sheet';
import { ResultFeedback } from '@/components/result-feedback';
import { API_BASE_URL } from '@/constants/api';
import { getNearbyFallback, supportsNearbyDonationReuse } from '@/constants/nearby-search';
import {
  clearLastNearbyScanContext,
  setLastNearbyScanContext,
} from '@/constants/scan-session';
import {
  DEFAULT_REVIEW_SUMMARY,
  getRecognitionReviewSummary,
  resolvePredictionFlowStatus,
  type PredictionClarification,
} from '@/app/prediction-flow';
import {
  shouldShowGuidanceFeedback,
  type FeedbackUpdate,
} from '@/app/feedback-flow';
import {
  saveRecentScan,
  updateRecentScan,
  type RecentScan,
} from '../../storage/recentScans';
import {
  getInstallationId,
  saveScanUsageMetadata,
} from '../../storage/scanUsage';
import {
  enqueueFeedback,
  flushFeedbackQueue,
} from '../../storage/feedbackQueue';

const CAMERA_CONTROLS_NAV_CLEARANCE = 52;
const CAMERA_READY_FALLBACK_DELAY_MS = 450;
const CAMERA_LOADING_OVERLAY_DELAY_MS = 280;
const ANALYZING_STATUS_INTERVAL_MS = 1400;
const ANALYZING_STATUS_MESSAGES = [
  'Preparing image',
  'Checking for barcode or text',
  'Identifying the item',
  'Finding disposal guidance',
  'Building your result',
  'Almost ready',
] as const;
const LOADING_SHIMMER_BAND_WIDTH = 110;
const ANALYZING_PIXEL_COORDINATES = [
  { left: 2, size: 3, top: 1 },
  { left: 10, size: 4, top: 0 },
  { left: 20, size: 3, top: 4 },
  { left: 31, size: 4, top: 1 },
  { left: 42, size: 3, top: 5 },
  { left: 5, size: 4, top: 9 },
  { left: 16, size: 3, top: 11 },
  { left: 27, size: 4, top: 9 },
  { left: 38, size: 3, top: 13 },
  { left: 0, size: 3, top: 18 },
  { left: 9, size: 4, top: 19 },
  { left: 21, size: 3, top: 17 },
  { left: 33, size: 4, top: 20 },
  { left: 43, size: 3, top: 18 },
  { left: 4, size: 3, top: 28 },
  { left: 14, size: 4, top: 26 },
  { left: 25, size: 3, top: 30 },
  { left: 36, size: 4, top: 27 },
  { left: 1, size: 4, top: 36 },
  { left: 11, size: 3, top: 38 },
  { left: 22, size: 4, top: 35 },
  { left: 34, size: 3, top: 39 },
  { left: 43, size: 4, top: 34 },
] as const;
const RESULT_SHEET_NAV_GAP = 16;
const MAX_VISIBLE_CANDIDATES = 5;
const MANUAL_KEYBOARD_GAP = 12;
const MANUAL_SHEET_MIN_HEIGHT = 280;

type PredictionStatus = 'confident' | 'uncertain' | 'unknown';

type PredictionCandidate = {
  label: string;
  selectedItem: string;
  score?: number;
};

type RawPredictionCandidate =
  | string
  | {
      label?: unknown;
      name?: unknown;
      item_label?: unknown;
      selected_item?: unknown;
      selectedItem?: unknown;
      score?: unknown;
      confidence?: unknown;
      similarity?: unknown;
      guidance_supported?: unknown;
      guidanceSupported?: unknown;
    }
  | [unknown, unknown?];

type PredictionResponse = {
  request_id?: string;
  item: string;
  category: string;
  status: PredictionStatus;
  candidates?: RawPredictionCandidate[] | null;
  disposal_action: string | null;
  material_code: string | null;
  impact_level: string | null;
  summary?: string | null;
  steps: string[];
  guidance_source?: string;
  guidanceSource?: string;
  recognition_source?: string;
  recognitionSource?: string;
  recognition_confidence?: Record<string, unknown>;
  recognitionConfidence?: Record<string, unknown>;
  clarification?: PredictionClarification | null;
  guidance_confidence?: Record<string, unknown>;
  guidanceConfidence?: Record<string, unknown>;
  warnings?: string[];
  guidance_metadata?: Record<string, unknown>;
  guidanceMetadata?: Record<string, unknown>;
  daily_limit?: number;
  dailyLimit?: number;
  scans_remaining?: number;
  scansRemaining?: number;
  reset_at?: string;
  resetAt?: string;
  recognition_details?: {
    candidates?: RawPredictionCandidate[] | null;
    raw_item_label?: unknown;
    normalized?: {
      normalized_item?: unknown;
      disposal_category?: unknown;
      broad_category?: unknown;
      material_category?: unknown;
      item_label?: unknown;
      matched_supported_label?: unknown;
    } | null;
  } | null;
};

type SheetViewState = 'idle' | PredictionStatus;
type VisibleSheetState = Exclude<SheetViewState, 'idle'>;
type RequestState = 'idle' | 'loading';
type PredictionRequestSource = 'image' | 'selection';

type SupportedLabelsResponse = {
  labels: string[];
};

type ScannerResultData = {
  item: string;
  label: string;
  title: string;
  materialTag?: string | null;
  summary: string;
  steps: string[];
  warnings: string[];
  guidanceSource?: string;
  guidanceMetadata: Record<string, unknown>;
  showNearbyButton: boolean;
  normalizedItem: string | null;
  disposalCategory: string | null;
  broadCategory: string | null;
  materialCategory: string | null;
  disposalAction: string | null;
  requiresLocationCheck: boolean;
  supportsDonationReuse: boolean;
};

type NormalizedGuidanceMetadata = Record<string, unknown> & {
  requiresLocationCheck?: boolean;
  locationSearchRecommended?: boolean;
  sourceNames?: string[];
};

type ActiveScanSession = {
  id: string;
  imageUri: string;
  scannedAt: string;
  predictedItem: string | null;
  originalStatus: PredictionStatus;
  hasSavedRecord: boolean;
  originalRequestId: string | null;
};

async function sendFeedbackRequest(requestId: string, update: FeedbackUpdate) {
  const response = await fetch(`${API_BASE_URL}/feedback/${encodeURIComponent(requestId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(update),
  });
  if (!response.ok) {
    throw new Error(`Feedback request failed with status ${response.status}`);
  }
}

function getDisposalActionText(disposalAction: string | null) {
  return (disposalAction ?? 'follow local guidance').trim().toLowerCase();
}

function getImpactLevelText(impactLevel: string | null) {
  return (impactLevel ?? 'Local Guidance').trim();
}

function getMetadataObject(value: unknown) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null;
  }

  return value as Record<string, unknown>;
}

function getMetadataStringArray(
  metadata: Record<string, unknown> | null,
  ...keys: string[]
) {
  if (!metadata) {
    return [];
  }

  for (const key of keys) {
    const value = metadata[key];
    if (!Array.isArray(value)) {
      continue;
    }

    const normalizedValues = value
      .map((item) => (typeof item === 'string' ? item.trim() : ''))
      .filter(Boolean);

    if (normalizedValues.length) {
      return normalizedValues;
    }
  }

  return [];
}

function getMetadataBoolean(
  metadata: Record<string, unknown> | null,
  ...keys: string[]
) {
  if (!metadata) {
    return false;
  }

  return keys.some((key) => metadata[key] === true);
}

function getNormalizedGuidanceMetadata(
  value: PredictionResponse | ScannerResultData | Record<string, unknown> | null | undefined,
): NormalizedGuidanceMetadata {
  const record = getMetadataObject(value);
  if (!record) {
    return {};
  }

  const nestedMetadata =
    getMetadataObject(record.guidanceMetadata) ?? getMetadataObject(record.guidance_metadata);
  const metadata = nestedMetadata ?? record;
  const sourceNames = getMetadataStringArray(metadata, 'sourceNames', 'source_names');

  return {
    ...metadata,
    sourceNames,
    requiresLocationCheck: getMetadataBoolean(
      metadata,
      'requiresLocationCheck',
      'requires_location_check',
    ),
    locationSearchRecommended: getMetadataBoolean(
      metadata,
      'locationSearchRecommended',
      'location_search_recommended',
    ),
  };
}

function shortenImpactLabel(impactLevel: string | null) {
  const impact = getImpactLevelText(impactLevel);
  const normalizedImpact = impact.toLowerCase();

  if (normalizedImpact === 'high impact') {
    return 'High';
  }
  if (normalizedImpact === 'low impact') {
    return 'Low';
  }
  if (normalizedImpact === 'check local guidance') {
    return 'Check local';
  }
  if (
    normalizedImpact === 'trusted guidance unavailable'
    || normalizedImpact === 'low confidence guidance'
  ) {
    return 'Low confidence';
  }

  return impact;
}

function getCompactPillLabel(response: PredictionResponse) {
  const material = response.material_code?.trim()
    || (response.category && response.category !== 'Unknown' ? response.category.trim() : '');
  const impact = shortenImpactLabel(response.impact_level);

  if (material && impact) {
    return `${material} · ${impact}`;
  }
  if (material) {
    return material;
  }

  return impact;
}

function getNormalizedRecognitionValue(
  response: PredictionResponse,
  key: 'normalized_item' | 'disposal_category' | 'broad_category' | 'material_category',
) {
  const value = response.recognition_details?.normalized?.[key];
  if (typeof value !== 'string') {
    return null;
  }

  const normalizedValue = value.trim();
  return normalizedValue || null;
}

function getPredictionSummary(response: PredictionResponse) {
  const providedSummary = response.summary?.trim();
  if (providedSummary) {
    return providedSummary;
  }

  const action = getDisposalActionText(response.disposal_action);
  return `${response.item} is categorized as ${response.category.toLowerCase()} and should be handled through ${action} guidance in your area.`;
}

function shouldShowNearbyButton(response: PredictionResponse) {
  const normalizedAction = response.disposal_action?.trim().toLowerCase() ?? '';
  if (
    normalizedAction.includes('drop-off')
    || normalizedAction.includes('drop off')
    || normalizedAction.includes('hazardous')
    || normalizedAction.includes('e-waste')
    || normalizedAction.includes('check local')
    || normalizedAction.includes('take-back')
    || normalizedAction.includes('take back')
  ) {
    return true;
  }

  const metadata = getNormalizedGuidanceMetadata(response);
  if (metadata.requiresLocationCheck || metadata.locationSearchRecommended) {
    return true;
  }

  const guidanceText = [getPredictionSummary(response), ...response.steps]
    .join(' ')
    .toLowerCase();

  return [
    'drop-off',
    'drop off',
    'take-back',
    'take back',
    'facility',
    'recycling center',
    'local recycling program',
    'verify local',
    'verify the location',
    'location verification',
    'program availability',
    'local availability',
  ].some((term) => guidanceText.includes(term));
}

function getPredictedItemFromPrediction(prediction: PredictionResponse) {
  const formattedItem = prediction.item.trim();
  if (formattedItem) {
    return formattedItem;
  }

  const topCandidate = normalizePredictionCandidates(prediction)[0]?.label.trim();
  return topCandidate || null;
}

function getDisposalLabel(disposalAction: string | null) {
  const normalizedAction = disposalAction?.trim().toLowerCase() ?? '';

  if (normalizedAction.includes('recycle')) {
    return 'RECYCLE';
  }

  if (normalizedAction.includes('compost')) {
    return 'COMPOST';
  }

  if (normalizedAction.includes('donate')) {
    return 'DONATE';
  }

  if (
    normalizedAction.includes('drop-off') ||
    normalizedAction.includes('drop off') ||
    normalizedAction.includes('e-waste') ||
    normalizedAction.includes('bulky') ||
    normalizedAction.includes('specialist')
  ) {
    return 'DROP-OFF';
  }

  return 'TRASH';
}

function createActiveScanSession(imageUri: string): ActiveScanSession {
  const scannedAt = new Date().toISOString();

  return {
    id: `scan-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    imageUri,
    scannedAt,
    predictedItem: null,
    originalStatus: 'unknown',
    hasSavedRecord: false,
    originalRequestId: null,
  };
}

function toSheetData(response: PredictionResponse): ScannerResultData {
  const action = getDisposalActionText(response.disposal_action);
  const normalizedItem = getNormalizedRecognitionValue(response, 'normalized_item');
  const normalizedDisposalCategory = getNormalizedRecognitionValue(
    response,
    'disposal_category',
  );
  const disposalCategory = normalizedDisposalCategory
    ?? (getNearbyFallback(response.category) ? response.category : null);
  const broadCategory = getNormalizedRecognitionValue(response, 'broad_category');
  const materialCategory = getNormalizedRecognitionValue(response, 'material_category');
  const guidanceMetadata = getNormalizedGuidanceMetadata(response);

  return {
    item: response.item,
    label: `IDENTIFIED - ${response.item.toUpperCase()}`,
    title: `${action}.`,
    materialTag: getCompactPillLabel(response),
    summary: getPredictionSummary(response),
    steps: response.steps,
    warnings: Array.isArray(response.warnings) ? response.warnings : [],
    guidanceSource: response.guidanceSource ?? response.guidance_source,
    guidanceMetadata,
    showNearbyButton: shouldShowNearbyButton(response),
    normalizedItem,
    disposalCategory,
    broadCategory,
    materialCategory,
    disposalAction: response.disposal_action,
    requiresLocationCheck: guidanceMetadata.requiresLocationCheck === true,
    supportsDonationReuse: supportsNearbyDonationReuse({
      item: normalizedItem ?? response.item,
      disposalCategory,
      disposalAction: response.disposal_action,
      summary: response.summary,
      steps: response.steps,
    }),
  };
}

function normalizeLabelKey(value: string) {
  return value.trim().toLowerCase();
}

function isPredictionRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

async function readJsonResponse(response: Response) {
  try {
    return (await response.json()) as unknown;
  } catch {
    return null;
  }
}

function isDailyScanLimitResponse(value: unknown) {
  return (
    isPredictionRecord(value) &&
    value.error === 'daily_scan_limit_reached'
  );
}

function getCandidateLabel(value: unknown) {
  if (typeof value === 'string') {
    return value.trim();
  }

  if (Array.isArray(value)) {
    return getCandidateLabel(value[0]);
  }

  if (!isPredictionRecord(value)) {
    return null;
  }

  for (const key of ['label', 'name', 'item_label'] as const) {
    const label = value[key];
    if (typeof label === 'string' && label.trim()) {
      return label.trim();
    }
  }

  return null;
}

function getCandidateScore(value: unknown) {
  let score: unknown = null;

  if (Array.isArray(value)) {
    score = value[1];
  } else if (isPredictionRecord(value)) {
    score = value.score ?? value.confidence ?? value.similarity;
  }

  if (typeof score !== 'number' || !Number.isFinite(score)) {
    return undefined;
  }

  return score;
}

function getCandidateSelectedItem(value: unknown, label: string) {
  if (!isPredictionRecord(value)) {
    return label;
  }

  const selectedItem = value.selected_item ?? value.selectedItem;
  return typeof selectedItem === 'string' && selectedItem.trim() ? selectedItem.trim() : label;
}

function isGuidanceSupportedCandidate(value: unknown) {
  if (!isPredictionRecord(value)) {
    return true;
  }

  const guidanceSupported = value.guidance_supported ?? value.guidanceSupported;
  return guidanceSupported !== false;
}

function appendNormalizedCandidate(
  candidates: PredictionCandidate[],
  value: unknown,
) {
  if (!isGuidanceSupportedCandidate(value)) {
    return;
  }

  const label = getCandidateLabel(value);

  if (!label) {
    return;
  }

  const selectedItem = getCandidateSelectedItem(value, label);
  const normalizedLabel = normalizeLabelKey(label);
  const normalizedSelectedItem = normalizeLabelKey(selectedItem);
  if (
    !normalizedLabel ||
    !normalizedSelectedItem ||
    normalizedLabel === 'other' ||
    normalizedLabel === 'unknown' ||
    normalizedSelectedItem === 'other' ||
    normalizedSelectedItem === 'unknown'
  ) {
    return;
  }

  const score = getCandidateScore(value);
  const existingCandidate = candidates.find(
    (candidate) => normalizeLabelKey(candidate.selectedItem) === normalizedSelectedItem
  );

  if (existingCandidate) {
    if (existingCandidate.score === undefined && score !== undefined) {
      existingCandidate.score = score;
    }
    return;
  }

  candidates.push(
    score === undefined ? { label, selectedItem } : { label, selectedItem, score }
  );
}

function appendCandidateList(candidates: PredictionCandidate[], values: unknown) {
  if (!Array.isArray(values)) {
    return;
  }

  values.forEach((value) => appendNormalizedCandidate(candidates, value));
}

function normalizePredictionCandidates(
  prediction: PredictionResponse,
  fallbackCandidates: PredictionCandidate[] = []
) {
  const normalizedCandidates: PredictionCandidate[] = [];
  const recognitionDetails = prediction.recognition_details;
  const normalizedDetails = recognitionDetails?.normalized;

  appendNormalizedCandidate(normalizedCandidates, prediction.item);
  appendCandidateList(normalizedCandidates, prediction.candidates);
  appendCandidateList(normalizedCandidates, recognitionDetails?.candidates);
  appendNormalizedCandidate(normalizedCandidates, normalizedDetails?.item_label);
  appendNormalizedCandidate(normalizedCandidates, normalizedDetails?.matched_supported_label);
  appendNormalizedCandidate(normalizedCandidates, recognitionDetails?.raw_item_label);
  appendCandidateList(normalizedCandidates, fallbackCandidates);

  return normalizedCandidates.slice(0, MAX_VISIBLE_CANDIDATES);
}

function CameraPermissionNotice() {
  return (
    <View style={styles.permissionState}>
      <Text style={styles.permissionTitle}>Camera access is required to scan items.</Text>
      <Pressable onPress={() => Linking.openSettings()} style={styles.permissionButton}>
        <Text style={styles.permissionButtonText}>Open Settings</Text>
      </Pressable>
    </View>
  );
}

function DailyScanLimitWarning({
  bottomInset,
  maxHeight,
  onDismiss,
}: {
  bottomInset: number;
  maxHeight: number;
  onDismiss: () => void;
}) {
  return (
    <View
      accessibilityViewIsModal
      pointerEvents="auto"
      style={styles.rateLimitOverlay}
    >
      <Pressable
        accessibilityLabel="Dismiss daily scan limit warning"
        onPress={onDismiss}
        style={StyleSheet.absoluteFill}
      />

      <View
        accessibilityRole="alert"
        style={[
          styles.rateLimitCard,
          {
            marginBottom: bottomInset + BOTTOM_NAV_BAR_TOTAL_HEIGHT + 20,
            maxHeight,
          },
        ]}
      >
        <View style={styles.rateLimitIcon}>
          <Ionicons color="#15311A" name="time-outline" size={24} />
        </View>

        <View style={styles.rateLimitTextBlock}>
          <Text style={styles.rateLimitEyebrow}>Daily Limit</Text>
          <Text style={styles.rateLimitTitle}>You’re out of scans for today</Text>
          <Text style={styles.rateLimitMessage}>
            You’ve used all 40 scans for today. Your scans reset tomorrow.
          </Text>
        </View>

        <Pressable
          accessibilityRole="button"
          onPress={onDismiss}
          style={({ pressed }) => [
            styles.rateLimitButton,
            pressed && styles.buttonPressed,
          ]}
        >
          <Text style={styles.rateLimitButtonText}>Got it</Text>
        </Pressable>
      </View>
    </View>
  );
}

function AnalyzingImageAnimation() {
  const scanProgress = useSharedValue(0);

  useEffect(() => {
    scanProgress.value = withRepeat(
      withTiming(1, {
        duration: 1800,
        easing: Easing.inOut(Easing.cubic),
      }),
      -1,
      true,
    );

    return () => {
      cancelAnimation(scanProgress);
      scanProgress.value = 0;
    };
  }, [scanProgress]);

  const beamAnimatedStyle = useAnimatedStyle(() => ({
    transform: [{ translateX: interpolate(scanProgress.value, [0, 1], [-26, 26]) }],
  }));
  const mountainRevealAnimatedStyle = useAnimatedStyle(() => ({
    width: interpolate(scanProgress.value, [0, 1], [0, 52]),
  }));
  const pixelRevealAnimatedStyle = useAnimatedStyle(() => ({
    width: interpolate(scanProgress.value, [0, 1], [52, 0]),
  }));

  return (
    <View
      accessible
      accessibilityLabel="Analyzing image"
      accessibilityRole="progressbar"
      style={styles.analyzingImageFrame}>
      <View style={styles.analyzingGlyph}>
        <View style={styles.analyzingGlyphOutline} />
        <Reanimated.View
          style={[styles.analyzingMountainReveal, mountainRevealAnimatedStyle]}>
          <View style={styles.analyzingMountainCanvas}>
            <View style={styles.analyzingSun} />
            <View style={styles.analyzingMountainFirst} />
            <View style={styles.analyzingMountainSecond} />
          </View>
        </Reanimated.View>
        <Reanimated.View style={[styles.analyzingPixelReveal, pixelRevealAnimatedStyle]}>
          <View style={styles.analyzingPixelField}>
            {ANALYZING_PIXEL_COORDINATES.map((pixel, index) => (
              <View
                key={`${pixel.left}-${pixel.top}-${index}`}
                style={[
                  styles.analyzingPixel,
                  {
                    height: pixel.size,
                    left: pixel.left,
                    top: pixel.top,
                    width: pixel.size,
                  },
                ]}
              />
            ))}
          </View>
        </Reanimated.View>
      </View>
      <Reanimated.View style={[styles.analyzingScanBeam, beamAnimatedStyle]}>
        <View style={styles.analyzingScanLine} />
        <View style={styles.analyzingScanCapTop} />
        <View style={styles.analyzingScanCapBottom} />
      </Reanimated.View>
    </View>
  );
}

function ShimmerLoadingText({ children }: { children: string }) {
  const [textWidth, setTextWidth] = useState(0);
  const shimmerProgress = useSharedValue(0);

  useEffect(() => {
    shimmerProgress.value = withRepeat(
      withSequence(
        withTiming(1, {
          duration: 2200,
          easing: Easing.bezier(0.4, 0, 0.2, 1),
        }),
        withDelay(750, withTiming(0, { duration: 0 })),
      ),
      -1,
      false,
    );

    return () => {
      cancelAnimation(shimmerProgress);
      shimmerProgress.value = 0;
    };
  }, [shimmerProgress]);

  const shimmerBandStyle = useAnimatedStyle(() => {
    const translateX = interpolate(
      shimmerProgress.value,
      [0, 1],
      [-LOADING_SHIMMER_BAND_WIDTH, textWidth],
    );

    return {
      opacity: interpolate(shimmerProgress.value, [0, 0.12, 0.88, 1], [0, 1, 1, 0]),
      transform: [{ translateX }],
    };
  });

  return (
    <View
      onLayout={({ nativeEvent }) => setTextWidth(nativeEvent.layout.width)}
      style={styles.loadingShimmerTextWrap}>
      <Text numberOfLines={1} style={styles.loadingText}>
        {children}
      </Text>
      {textWidth > 0 ? (
        <MaskedView
          maskElement={
            <Text numberOfLines={1} style={styles.loadingShimmerMaskText}>
              {children}
            </Text>
          }
          pointerEvents="none"
          style={[styles.loadingShimmerMask, { width: textWidth }]}>
          <Reanimated.View style={[styles.loadingShimmerGradientBand, shimmerBandStyle]}>
            <LinearGradient
              colors={[
                'rgba(18,18,18,0)',
                'rgba(18,18,18,0.12)',
                'rgba(5,5,5,0.62)',
                'rgba(18,18,18,0.12)',
                'rgba(18,18,18,0)',
              ]}
              locations={[0, 0.22, 0.5, 0.78, 1]}
              start={{ x: 0, y: 0.5 }}
              end={{ x: 1, y: 0.5 }}
              style={StyleSheet.absoluteFillObject}
            />
          </Reanimated.View>
        </MaskedView>
      ) : null}
    </View>
  );
}

type CameraAreaProps = {
  cameraRef: React.RefObject<CameraView | null>;
  cameraPreviewKey: number;
  capturedImageUri: string | null;
  bottomInset: number;
  isCameraActive: boolean;
  isCameraReady: boolean;
  showCameraLoadingOverlay: boolean;
  isLoading: boolean;
  isTorchOn: boolean;
  topInset: number;
  onCameraReady: () => void;
  onClose?: () => void;
  onToggleTorch: () => void;
  onPickImage: () => void;
  onTakePhoto: () => void;
};

function CameraArea({
  cameraRef,
  cameraPreviewKey,
  bottomInset,
  capturedImageUri,
  isCameraActive,
  isCameraReady,
  showCameraLoadingOverlay,
  isLoading,
  isTorchOn,
  topInset,
  onCameraReady,
  onClose,
  onToggleTorch,
  onPickImage,
  onTakePhoto,
}: CameraAreaProps) {
  const cameraWarmupOpacity = useRef(new Animated.Value(1)).current;
  const [analyzingStatusIndex, setAnalyzingStatusIndex] = useState(0);
  const shouldHideCameraUi = isCameraActive && !capturedImageUri && !isCameraReady;
  const shouldShowCaptureGuide =
    isCameraActive && isCameraReady && !capturedImageUri && !isLoading;
  const isCaptureDisabled = isLoading || !isCameraActive || !isCameraReady;
  const [renderCameraWarmupOverlay, setRenderCameraWarmupOverlay] = useState(shouldHideCameraUi);

  useEffect(() => {
    if (shouldHideCameraUi) {
      setRenderCameraWarmupOverlay(true);
      cameraWarmupOpacity.setValue(1);
      return;
    }

    Animated.timing(cameraWarmupOpacity, {
      duration: 180,
      toValue: 0,
      useNativeDriver: true,
    }).start(({ finished }) => {
      if (finished) {
        setRenderCameraWarmupOverlay(false);
      }
    });
  }, [cameraWarmupOpacity, shouldHideCameraUi]);

  useEffect(() => {
    if (!isLoading) {
      setAnalyzingStatusIndex(0);
      return;
    }

    if (analyzingStatusIndex === ANALYZING_STATUS_MESSAGES.length - 1) {
      return;
    }

    const statusTimeout = setTimeout(() => {
      setAnalyzingStatusIndex((currentIndex) => currentIndex + 1);
    }, ANALYZING_STATUS_INTERVAL_MS);

    return () => clearTimeout(statusTimeout);
  }, [analyzingStatusIndex, isLoading]);

  return (
    <View style={styles.cameraCard}>
      {capturedImageUri ? (
        <Image source={{ uri: capturedImageUri }} style={StyleSheet.absoluteFillObject} />
      ) : (
        <CameraView
          active={isCameraActive}
          enableTorch={isTorchOn}
          facing="back"
          key={cameraPreviewKey}
          mode="picture"
          onCameraReady={onCameraReady}
          ref={cameraRef}
          style={StyleSheet.absoluteFillObject}
        />
      )}

      <View style={styles.cameraOverlay}>
        {renderCameraWarmupOverlay ? (
          <Animated.View
            pointerEvents="auto"
            style={[styles.cameraWarmupOverlay, { opacity: cameraWarmupOpacity }]}>
            {showCameraLoadingOverlay ? (
              <View style={styles.cameraWarmupFrame}>
                <ActivityIndicator color="#F3F6F9" size="small" />
                <Text style={styles.cameraWarmupTitle}>Starting camera...</Text>
              </View>
            ) : null}
          </Animated.View>
        ) : null}

        {!shouldHideCameraUi ? (
          <>
            <View style={[styles.backdropTopBar, { paddingTop: topInset + 16 }]}>
              <Pressable onPress={onToggleTorch} style={styles.headerIconButton}>
                <Ionicons color="#F3F6F9" name={isTorchOn ? 'flash' : 'flash-outline'} size={20} />
              </Pressable>
              {onClose ? (
                <Pressable onPress={onClose} style={styles.closeButton}>
                  <Ionicons color="#F3F6F9" name="close" size={20} />
                </Pressable>
              ) : (
                <View style={styles.headerIconSpacer} />
              )}
            </View>

            {shouldShowCaptureGuide ? (
              <View pointerEvents="none" style={styles.scanFrameWrap}>
                <View style={styles.scanFrame}>
                  <View style={styles.targetRing}>
                    <View style={styles.targetDot} />
                  </View>
                </View>
              </View>
            ) : null}

            <View
              style={[
                styles.cameraControls,
                { bottom: bottomInset + BOTTOM_NAV_BAR_HEIGHT + CAMERA_CONTROLS_NAV_CLEARANCE },
              ]}>
              <Pressable
                disabled={isLoading}
                onPress={onPickImage}
                style={[styles.iconActionButton, isLoading && styles.buttonDisabled]}>
                <Ionicons color="#FFFFFF" name="images-outline" size={22} />
              </Pressable>

              <Pressable
                disabled={isCaptureDisabled}
                onPress={onTakePhoto}
                style={[styles.shutterButton, isCaptureDisabled && styles.buttonDisabled]}>
                <View style={styles.shutterInner} />
              </Pressable>

              <View style={styles.iconActionSpacer} />
            </View>
          </>
        ) : null}

        {capturedImageUri && isLoading ? (
          <Reanimated.View
            entering={FadeIn.duration(180)}
            exiting={FadeOut.duration(160)}
            style={styles.loadingOverlay}>
            <AnalyzingImageAnimation />
            <ShimmerLoadingText>
              {ANALYZING_STATUS_MESSAGES[analyzingStatusIndex]}
            </ShimmerLoadingText>
          </Reanimated.View>
        ) : null}
      </View>
    </View>
  );
}

export default function ScannerScreen() {
  const router = useRouter();
  const isScreenFocused = useIsFocused();
  const insets = useSafeAreaInsets();
  const { height: windowHeight } = useWindowDimensions();
  const cameraRef = useRef<CameraView | null>(null);
  const cameraReadyTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cameraLoadingOverlayTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const predictRequestRef = useRef(0);
  const predictInFlightCountRef = useRef(0);
  const activeScanSessionRef = useRef<ActiveScanSession | null>(null);
  const [permission, requestPermission] = useCameraPermissions();
  const [requestState, setRequestState] = useState<RequestState>('idle');
  const [sheetState, setSheetState] = useState<SheetViewState>('idle');
  const [visibleSheetState, setVisibleSheetState] = useState<VisibleSheetState | 'idle'>('idle');
  const [capturedImageUri, setCapturedImageUri] = useState<string | null>(null);
  const [cameraPreviewKey, setCameraPreviewKey] = useState(0);
  const [isCameraReady, setIsCameraReady] = useState(false);
  const [showCameraLoadingOverlay, setShowCameraLoadingOverlay] = useState(false);
  const [isTorchOn, setIsTorchOn] = useState(false);
  const [result, setResult] = useState<ScannerResultData | null>(null);
  const [candidates, setCandidates] = useState<PredictionCandidate[]>([]);
  const [reviewSummary, setReviewSummary] = useState(DEFAULT_REVIEW_SUMMARY);
  const [materialLabels, setMaterialLabels] = useState<string[] | null>(null);
  const [isLoadingMaterialLabels, setIsLoadingMaterialLabels] = useState(false);
  const [materialLabelsError, setMaterialLabelsError] = useState<string | null>(null);
  const [manualEntryText, setManualEntryText] = useState('');
  const [selectedManualLabel, setSelectedManualLabel] = useState<string | null>(null);
  const [manualKeyboardOffset, setManualKeyboardOffset] = useState(0);
  const [sheetHeight, setSheetHeight] = useState(0);
  const [isRateLimitWarningVisible, setIsRateLimitWarningVisible] = useState(false);
  const [itemFeedback, setItemFeedback] = useState<boolean | null>(null);
  const [guidanceFeedback, setGuidanceFeedback] = useState<boolean | null>(null);
  const sheetAnimation = useRef(new Animated.Value(windowHeight)).current;
  const bottomNavOffset = Math.max(insets.bottom, BOTTOM_NAV_BAR_MIN_BOTTOM_OFFSET);
  const resultSheetBottomOffset =
    bottomNavOffset + BOTTOM_NAV_BAR_TOTAL_HEIGHT + RESULT_SHEET_NAV_GAP;
  const hiddenSheetOffset = Math.max(sheetHeight + resultSheetBottomOffset + 24, windowHeight);

  useEffect(() => {
    requestPermission();
  }, [requestPermission]);

  useEffect(() => {
    void flushFeedbackQueue(sendFeedbackRequest);
  }, []);

  useEffect(() => {
    if (visibleSheetState !== 'uncertain') {
      setManualKeyboardOffset(0);
      return;
    }

    const handleKeyboardShow = (event: {
      endCoordinates?: { height?: number; screenY?: number };
    }) => {
      const keyboardTop = event.endCoordinates?.screenY;
      const keyboardHeight = event.endCoordinates?.height ?? 0;
      const keyboardOverlap =
        typeof keyboardTop === 'number' && keyboardTop > 0
          ? Math.max(0, windowHeight - keyboardTop)
          : keyboardHeight;

      setManualKeyboardOffset(
        Math.max(0, keyboardOverlap - resultSheetBottomOffset + MANUAL_KEYBOARD_GAP),
      );
    };

    const handleKeyboardHide = () => {
      setManualKeyboardOffset(0);
    };

    const showSubscription = Keyboard.addListener('keyboardDidShow', handleKeyboardShow);
    const hideSubscription = Keyboard.addListener('keyboardDidHide', handleKeyboardHide);

    return () => {
      showSubscription.remove();
      hideSubscription.remove();
      setManualKeyboardOffset(0);
    };
  }, [resultSheetBottomOffset, visibleSheetState, windowHeight]);

  useEffect(() => {
    const shouldWarmCamera = isScreenFocused && permission?.granted && !capturedImageUri;

    if (cameraReadyTimeoutRef.current) {
      clearTimeout(cameraReadyTimeoutRef.current);
      cameraReadyTimeoutRef.current = null;
    }

    if (cameraLoadingOverlayTimeoutRef.current) {
      clearTimeout(cameraLoadingOverlayTimeoutRef.current);
      cameraLoadingOverlayTimeoutRef.current = null;
    }

    if (!shouldWarmCamera) {
      setIsCameraReady(false);
      setShowCameraLoadingOverlay(false);
      return;
    }

    setIsCameraReady(false);
    setShowCameraLoadingOverlay(false);
    cameraLoadingOverlayTimeoutRef.current = setTimeout(() => {
      setShowCameraLoadingOverlay(true);
      cameraLoadingOverlayTimeoutRef.current = null;
    }, CAMERA_LOADING_OVERLAY_DELAY_MS);
    // Keep the overlay from sticking if Android skips or delays the ready callback.
    cameraReadyTimeoutRef.current = setTimeout(() => {
      setIsCameraReady(true);
      cameraReadyTimeoutRef.current = null;
    }, CAMERA_READY_FALLBACK_DELAY_MS);

    return () => {
      if (cameraReadyTimeoutRef.current) {
        clearTimeout(cameraReadyTimeoutRef.current);
        cameraReadyTimeoutRef.current = null;
      }

      if (cameraLoadingOverlayTimeoutRef.current) {
        clearTimeout(cameraLoadingOverlayTimeoutRef.current);
        cameraLoadingOverlayTimeoutRef.current = null;
      }
    };
  }, [cameraPreviewKey, capturedImageUri, isScreenFocused, permission?.granted]);

  useEffect(() => {
    if (visibleSheetState === 'idle') {
      sheetAnimation.setValue(hiddenSheetOffset);
      return;
    }

    Animated.spring(sheetAnimation, {
      damping: 18,
      mass: 0.8,
      stiffness: 170,
      toValue: sheetState === 'idle' ? hiddenSheetOffset : 0,
      useNativeDriver: true,
    }).start(({ finished }) => {
      if (!finished || sheetState !== 'idle') {
        return;
      }

      setVisibleSheetState('idle');
      setResult(null);
      setCandidates([]);
      setSheetHeight(0);
    });
  }, [hiddenSheetOffset, sheetAnimation, sheetState, visibleSheetState]);

  const handleSheetLayout = ({ nativeEvent }: LayoutChangeEvent) => {
    const nextHeight = nativeEvent.layout.height;

    if (Math.abs(nextHeight - sheetHeight) > 1) {
      setSheetHeight(nextHeight);
    }
  };

  const restoreCameraPreview = () => {
    setCapturedImageUri(null);
    setCameraPreviewKey((current) => current + 1);
  };

  const handleCameraReady = () => {
    if (cameraReadyTimeoutRef.current) {
      clearTimeout(cameraReadyTimeoutRef.current);
      cameraReadyTimeoutRef.current = null;
    }

    if (cameraLoadingOverlayTimeoutRef.current) {
      clearTimeout(cameraLoadingOverlayTimeoutRef.current);
      cameraLoadingOverlayTimeoutRef.current = null;
    }

    setIsCameraReady(true);
    setShowCameraLoadingOverlay(false);
  };

  const clearActiveScanSession = () => {
    activeScanSessionRef.current = null;
  };

  const resetManualEntry = () => {
    setManualEntryText('');
    setSelectedManualLabel(null);
    setMaterialLabelsError(null);
  };

  const loadMaterialLabels = async () => {
    if (materialLabels || isLoadingMaterialLabels) {
      return;
    }

    setIsLoadingMaterialLabels(true);
    setMaterialLabelsError(null);

    try {
      const response = await fetch(`${API_BASE_URL}/material_labels`);

      if (!response.ok) {
        throw new Error(`Request failed with status ${response.status}`);
      }

      const data = (await response.json()) as SupportedLabelsResponse;
      setMaterialLabels(Array.isArray(data.labels) ? data.labels : []);
    } catch {
      setMaterialLabelsError('Could not load supported items right now. Please try again.');
    } finally {
      setIsLoadingMaterialLabels(false);
    }
  };

  const handleChangeItem = () => {
    setManualEntryText('');
    setSelectedManualLabel(null);
    setMaterialLabelsError(null);
    setReviewSummary(DEFAULT_REVIEW_SUMMARY);
    setVisibleSheetState('uncertain');
    setSheetState('uncertain');

    if (!materialLabels && !isLoadingMaterialLabels) {
      void loadMaterialLabels();
    }
  };

  const submitFeedbackUpdate = async (update: FeedbackUpdate) => {
    const requestId = activeScanSessionRef.current?.originalRequestId;
    if (!requestId) {
      return;
    }
    try {
      await sendFeedbackRequest(requestId, update);
    } catch {
      await enqueueFeedback(requestId, update);
    }
  };

  const handleItemFeedback = (answer: boolean) => {
    setItemFeedback(answer);
    void submitFeedbackUpdate({ item_correct: answer });
    if (!answer) {
      handleChangeItem();
    }
  };

  const handleGuidanceFeedback = (answer: boolean) => {
    setGuidanceFeedback(answer);
    void submitFeedbackUpdate({ guidance_helpful: answer });
  };

  const handleRetryMaterialLabels = () => {
    if (!isLoadingMaterialLabels) {
      void loadMaterialLabels();
    }
  };

  const resetScanner = () => {
    predictRequestRef.current += 1;
    clearLastNearbyScanContext();
    clearActiveScanSession();
    restoreCameraPreview();
    setRequestState('idle');
    setSheetState('idle');
    setIsRateLimitWarningVisible(false);
    setReviewSummary(DEFAULT_REVIEW_SUMMARY);
    resetManualEntry();
    setItemFeedback(null);
    setGuidanceFeedback(null);

    if (visibleSheetState === 'idle') {
      setResult(null);
      setCandidates([]);
      setSheetHeight(0);
      return;
    }
  };

  const persistConfidentRecentScan = async (
    prediction: PredictionResponse,
    requestSource: PredictionRequestSource
  ) => {
    const activeSession = activeScanSessionRef.current;
    if (!activeSession || prediction.status !== 'confident' || !prediction.item) {
      return;
    }

    const finalItem = prediction.item;
    const predictedItem = activeSession.predictedItem;
    const wasCorrected =
      requestSource === 'selection' ||
      (predictedItem !== null &&
        normalizeLabelKey(predictedItem) !== normalizeLabelKey(finalItem));
    const resultSnapshot = toSheetData(prediction);
    const nextRecentScan: RecentScan = {
      id: activeSession.id,
      predictedItem,
      finalItem,
      wasCorrected,
      imageUri: activeSession.imageUri,
      category: prediction.category || null,
      disposalLabel: getDisposalLabel(prediction.disposal_action),
      disposalAction: prediction.disposal_action,
      materialCode: prediction.material_code,
      impactLevel: prediction.impact_level,
      recognitionStatus: activeSession.originalStatus,
      disposalStatus: 'needs_action',
      createdAt: activeSession.scannedAt,
      scannedAt: activeSession.scannedAt,
      updatedAt: new Date().toISOString(),
      materialTag: getCompactPillLabel(prediction),
      summary: resultSnapshot.summary,
      steps: prediction.steps,
      guidanceSnapshot: {
        itemName: finalItem,
        category: prediction.category || null,
        disposalAction: prediction.disposal_action,
        materialCode: prediction.material_code,
        impactLevel: prediction.impact_level,
        summary: resultSnapshot.summary,
        steps: resultSnapshot.steps,
        warnings: resultSnapshot.warnings,
        guidanceSource: prediction.guidanceSource ?? prediction.guidance_source ?? null,
        guidanceMetadata: resultSnapshot.guidanceMetadata,
        recognitionSource: prediction.recognitionSource ?? prediction.recognition_source ?? null,
        imageUri: activeSession.imageUri,
        createdAt: activeSession.scannedAt,
        normalizedItem: resultSnapshot.normalizedItem,
        disposalCategory: resultSnapshot.disposalCategory,
        broadCategory: resultSnapshot.broadCategory,
        materialCategory: resultSnapshot.materialCategory,
        requiresLocationCheck: resultSnapshot.requiresLocationCheck,
        supportsDonationReuse: resultSnapshot.supportsDonationReuse,
      },
    };

    if (activeSession.hasSavedRecord) {
      await updateRecentScan(activeSession.id, nextRecentScan);
    } else {
      await saveRecentScan(nextRecentScan);
    }

    if (activeScanSessionRef.current?.id === activeSession.id) {
      activeScanSessionRef.current = {
        ...activeScanSessionRef.current,
        hasSavedRecord: true,
      };
    }
  };

  const applyPrediction = async (
    prediction: PredictionResponse,
    requestSource: PredictionRequestSource,
    fallbackCandidates: PredictionCandidate[] = []
  ) => {
    const nextCandidates = normalizePredictionCandidates(prediction, fallbackCandidates);
    const nextFlowStatus = resolvePredictionFlowStatus(prediction);

    resetManualEntry();
    setResult(null);
    setCandidates(nextCandidates);
    setReviewSummary(getRecognitionReviewSummary(prediction));

    if (requestSource === 'image' && activeScanSessionRef.current) {
      activeScanSessionRef.current = {
        ...activeScanSessionRef.current,
        predictedItem: getPredictedItemFromPrediction(prediction),
        originalStatus: prediction.status,
        originalRequestId: prediction.request_id ?? null,
      };
    }

    if (nextFlowStatus === 'confident' && prediction.item) {
      const nextResult = toSheetData(prediction);
      setLastNearbyScanContext({
        scanSessionId:
          activeScanSessionRef.current?.id ?? `scan-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        item: prediction.item,
        normalizedItem: nextResult.normalizedItem,
        disposalCategory: nextResult.disposalCategory,
        broadCategory: nextResult.broadCategory,
        materialCategory: nextResult.materialCategory,
        disposalAction: nextResult.disposalAction,
        requiresLocationCheck: nextResult.requiresLocationCheck,
        supportsDonationReuse: nextResult.supportsDonationReuse,
      });
      setResult(nextResult);
      setVisibleSheetState('confident');
      setSheetState('confident');

      try {
        await persistConfidentRecentScan(prediction, requestSource);
      } catch (error) {
        console.warn('Could not save recent scan.', error);
      }
      return;
    }

    if (nextFlowStatus === 'uncertain') {
      setVisibleSheetState('uncertain');
      setSheetState('uncertain');
      if (!materialLabels && !isLoadingMaterialLabels) {
        void loadMaterialLabels();
      }
      return;
    }

    setVisibleSheetState('unknown');
    setSheetState('unknown');

    if (requestSource === 'image') {
      clearActiveScanSession();
    }
  };

  const sendPredictionRequest = async ({
    imageUri,
    selectedItem,
  }: {
    imageUri?: string;
    selectedItem?: string;
  }) => {
    if (!imageUri && !selectedItem) {
      return;
    }

    const requestSource: PredictionRequestSource = selectedItem ? 'selection' : 'image';
    const fallbackCandidates = requestSource === 'selection' ? candidates : [];
    const originalRequestId =
      requestSource === 'selection'
        ? activeScanSessionRef.current?.originalRequestId ?? null
        : null;
    const requestId = predictRequestRef.current + 1;
    predictRequestRef.current = requestId;
    const backendRequestId = `mobile-${Date.now()}-${requestId}`;
    const requestStartedAt = Date.now();
    setIsRateLimitWarningVisible(false);

    if (imageUri) {
      clearLastNearbyScanContext();
      activeScanSessionRef.current = createActiveScanSession(imageUri);
      setCapturedImageUri(imageUri);
      setResult(null);
      setCandidates([]);
      setSheetState('idle');
      setItemFeedback(null);
      setGuidanceFeedback(null);
    }

    setRequestState('loading');
    predictInFlightCountRef.current += 1;
    console.log(
      '[predict] start',
      JSON.stringify({
        requestId: backendRequestId,
        localRequestId: requestId,
        source: requestSource,
        hasImage: !!imageUri,
        selectedItem: !!selectedItem,
        inFlight: predictInFlightCountRef.current,
        overlapping: predictInFlightCountRef.current > 1,
      })
    );

    const formData = new FormData();
    if (selectedItem) {
      formData.append('selected_item', selectedItem);
    }
    if (imageUri) {
      formData.append('file', {
        uri: imageUri,
        name: 'photo.jpg',
        type: 'image/jpeg',
      } as unknown as Blob);
    }

    try {
      const installationId = await getInstallationId();
      const headers: Record<string, string> = {
        'X-Request-ID': backendRequestId,
        'X-GreenBin-Client-Id': installationId,
      };
      if (originalRequestId) {
        headers['X-Original-Request-ID'] = originalRequestId;
      }
      const response = await fetch(`${API_BASE_URL}/predict`, {
        method: 'POST',
        headers,
        body: formData,
      });
      const responseBody = await readJsonResponse(response);
      console.log(
        '[predict] response',
        JSON.stringify({
          requestId: backendRequestId,
          status: response.status,
          ok: response.ok,
          durationMs: Date.now() - requestStartedAt,
        })
      );

      if (response.status === 429 && isDailyScanLimitResponse(responseBody)) {
        await saveScanUsageMetadata(responseBody);
        if (requestId !== predictRequestRef.current) {
          return;
        }

        clearLastNearbyScanContext();
        clearActiveScanSession();
        restoreCameraPreview();
        resetManualEntry();
        setResult(null);
        setCandidates([]);
        setVisibleSheetState('idle');
        setSheetState('idle');
        setSheetHeight(0);
        setIsRateLimitWarningVisible(true);
        return;
      }

      if (!response.ok) {
        throw new Error(`Request failed with status ${response.status}`);
      }

      const prediction = {
        ...(responseBody as PredictionResponse),
        request_id:
          typeof (responseBody as PredictionResponse).request_id === 'string'
            ? (responseBody as PredictionResponse).request_id
            : backendRequestId,
      };
      if (requestId !== predictRequestRef.current) {
        return;
      }

      await saveScanUsageMetadata(prediction);
      await applyPrediction(prediction, requestSource, fallbackCandidates);
      if (selectedItem && originalRequestId && prediction.request_id) {
        setItemFeedback(false);
        void submitFeedbackUpdate({
          item_correct: false,
          prediction_changed: true,
          corrected_item: prediction.item || selectedItem,
          correction_request_id: prediction.request_id,
        });
      }
      void flushFeedbackQueue(sendFeedbackRequest);
    } catch (error) {
      if (requestId !== predictRequestRef.current) {
        return;
      }

      console.warn(
        '[predict] failed',
        JSON.stringify({
          requestId: backendRequestId,
          durationMs: Date.now() - requestStartedAt,
          message: error instanceof Error ? error.message : String(error),
        })
      );

      if (selectedItem) {
        Alert.alert('Could not confirm that selection. Please try again.');
      } else {
        clearActiveScanSession();
        restoreCameraPreview();
        setResult(null);
        setCandidates([]);
        setVisibleSheetState('idle');
        setSheetState('idle');
        setSheetHeight(0);
        Alert.alert('Could not analyze image. Please try again.');
      }
    } finally {
      predictInFlightCountRef.current = Math.max(0, predictInFlightCountRef.current - 1);
      console.log(
        '[predict] finish',
        JSON.stringify({
          requestId: backendRequestId,
          localRequestId: requestId,
          active: requestId === predictRequestRef.current,
          durationMs: Date.now() - requestStartedAt,
          inFlight: predictInFlightCountRef.current,
        })
      );
      if (requestId === predictRequestRef.current) {
        setRequestState('idle');
      }
    }
  };

  const handleTakePhoto = async () => {
    if (!cameraRef.current || requestState === 'loading' || !isCameraReady || !isScreenFocused) {
      return;
    }

    try {
      const camera = cameraRef.current;
      const photo = await camera.takePictureAsync({
        quality: 0.7,
        base64: false,
        skipProcessing: false,
      });

      if (!photo?.uri) {
        return;
      }

      await sendPredictionRequest({ imageUri: photo.uri });
    } catch {
      Alert.alert('Could not analyze image. Please try again.');
      resetScanner();
    }
  };

  const handlePickImage = async () => {
    if (requestState === 'loading') {
      return;
    }

    const permissionResult = await ImagePicker.requestMediaLibraryPermissionsAsync();

    if (!permissionResult.granted) {
      Alert.alert('Please allow photo library access in your settings.');
      return;
    }

    const selection = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      quality: 0.7,
    });

    if (selection.canceled || !selection.assets[0]?.uri) {
      return;
    }

    await sendPredictionRequest({ imageUri: selection.assets[0].uri });
  };

  const permissionDenied = permission && !permission.granted;
  const currentPredictedLabel = result?.item ?? candidates[0]?.label ?? null;
  const normalizedCurrentPredictedLabel = normalizeLabelKey(currentPredictedLabel ?? '');
  const normalizedManualEntry = normalizeLabelKey(manualEntryText);
  const exactSupportedLabel =
    materialLabels?.find((label) => {
      const normalizedLabel = normalizeLabelKey(label);
      return (
        normalizedLabel === normalizedManualEntry &&
        normalizedLabel !== normalizedCurrentPredictedLabel
      );
    }) ?? null;
  const manualSelectionLabel = exactSupportedLabel ?? selectedManualLabel;
  const manualSuggestions = normalizedManualEntry
    ? (materialLabels ?? [])
        .filter((label) => {
          const normalizedLabel = normalizeLabelKey(label);
          return (
            normalizedLabel !== normalizedCurrentPredictedLabel &&
            normalizedLabel.includes(normalizedManualEntry)
          );
        })
        .slice(0, 6)
    : [];
  const canSubmitManualEntry =
    !!manualSelectionLabel && requestState !== 'loading' && !materialLabelsError;

  const handleManualEntryChange = (value: string) => {
    setManualEntryText(value);
    setSelectedManualLabel(null);
  };

  const handleManualSuggestionPress = (label: string) => {
    if (requestState === 'loading') {
      return;
    }

    Keyboard.dismiss();
    setManualEntryText(label);
    setSelectedManualLabel(label);
    void sendPredictionRequest({ selectedItem: label });
  };

  const handleManualSubmit = () => {
    if (!manualSelectionLabel || requestState === 'loading') {
      return;
    }

    Keyboard.dismiss();
    void sendPredictionRequest({ selectedItem: manualSelectionLabel });
  };

  const isManualCorrectionVisible = visibleSheetState === 'uncertain';
  const activeSheetBottomOffset = isManualCorrectionVisible
    ? resultSheetBottomOffset + manualKeyboardOffset
    : resultSheetBottomOffset;
  const normalSheetMaxHeight = Math.min(
    windowHeight * 0.78,
    windowHeight - insets.top - resultSheetBottomOffset - 72,
  );
  const manualSheetMaxHeight = Math.max(
    MANUAL_SHEET_MIN_HEIGHT,
    Math.min(
      windowHeight * 0.86,
      windowHeight - insets.top - activeSheetBottomOffset - 24,
    ),
  );
  const activeSheetMaxHeight = isManualCorrectionVisible
    ? manualSheetMaxHeight
    : normalSheetMaxHeight;
  const rateLimitWarningMaxHeight = Math.max(
    260,
    windowHeight - insets.top - insets.bottom - BOTTOM_NAV_BAR_TOTAL_HEIGHT - 64,
  );

  return (
    <SafeAreaView edges={[]} style={styles.page}>
      <StatusBar style="light" />
      <View style={styles.shell}>
        {permissionDenied ? (
          <CameraPermissionNotice />
        ) : permission?.granted ? (
          <CameraArea
            cameraRef={cameraRef}
            cameraPreviewKey={cameraPreviewKey}
            bottomInset={insets.bottom}
            capturedImageUri={capturedImageUri}
            isCameraActive={isScreenFocused && !capturedImageUri}
            isCameraReady={isCameraReady}
            showCameraLoadingOverlay={showCameraLoadingOverlay}
            isLoading={requestState === 'loading'}
            isTorchOn={isTorchOn}
            topInset={insets.top}
            onCameraReady={handleCameraReady}
            onClose={visibleSheetState !== 'idle' ? resetScanner : undefined}
            onToggleTorch={() => setIsTorchOn((current) => !current)}
            onPickImage={handlePickImage}
            onTakePhoto={handleTakePhoto}
          />
        ) : (
          <View style={styles.permissionState}>
            <ActivityIndicator color="#FFFFFF" size="small" />
          </View>
        )}

        <View pointerEvents="box-none" style={styles.sheetOverlay}>
          {visibleSheetState !== 'idle' ? (
            <Animated.View
              onLayout={handleSheetLayout}
              pointerEvents={sheetState === 'idle' ? 'none' : 'auto'}
              style={[
                styles.sheetWrap,
                {
                  bottom: activeSheetBottomOffset,
                  maxHeight: activeSheetMaxHeight,
                  transform: [{ translateY: sheetAnimation }],
                },
              ]}>
              {visibleSheetState === 'confident' && result ? (
                <ResultSheet
                  buttonIconName="location-outline"
                  buttonLabel={result.showNearbyButton ? 'Find Nearby Locations' : undefined}
                  displayMode="expandable"
                  guidanceMetadata={result.guidanceMetadata}
                  guidanceSource={result.guidanceSource}
                  label={result.label}
                  materialTag={result.materialTag}
                  onButtonPress={
                    result.showNearbyButton
                      ? () =>
                          router.navigate({
                            pathname: '/(tabs)/nearby',
                            params: {
                              autoSearch: 'true',
                              item: result.item,
                              normalizedItem: result.normalizedItem ?? undefined,
                              disposalCategory: result.disposalCategory ?? undefined,
                              broadCategory: result.broadCategory ?? undefined,
                              materialCategory: result.materialCategory ?? undefined,
                              disposalAction: result.disposalAction ?? undefined,
                              requiresLocationCheck: String(result.requiresLocationCheck),
                              scanSessionId: activeScanSessionRef.current?.id ?? undefined,
                              supportsDonationReuse: String(result.supportsDonationReuse),
                            },
                          })
                      : undefined
                  }
                  secondaryButtonIconName="swap-horizontal-outline"
                  secondaryButtonLabel="Change Item"
                  onSecondaryButtonPress={handleChangeItem}
                  steps={result.steps}
                  summary={result.summary}
                  title={result.title}
                  warnings={result.warnings}
                >
                  <ResultFeedback
                    disabled={requestState === 'loading'}
                    guidanceAnswer={guidanceFeedback}
                    itemAnswer={itemFeedback}
                    onGuidanceAnswer={handleGuidanceFeedback}
                    onItemAnswer={handleItemFeedback}
                    showGuidanceQuestion={shouldShowGuidanceFeedback({
                      disposalAction: result.disposalAction,
                      guidanceSource: result.guidanceSource,
                      clarificationRequired: false,
                    })}
                  />
                </ResultSheet>
              ) : null}

              {visibleSheetState === 'uncertain' ? (
                <ResultSheet
                  buttonIconName="camera-outline"
                  buttonLabel="Retake Photo"
                  label="REVIEW NEEDED"
                  materialTag="Correct Item"
                  onButtonPress={resetScanner}
                  steps={[]}
                  summary={reviewSummary}
                  title="Search for the correct item"
                  keyboardShouldPersistTaps="handled">
                  <View style={styles.manualEntrySection}>
                    <Text style={styles.manualEntryPrompt}>Supported item label</Text>
                    <TextInput
                      autoCapitalize="words"
                      autoCorrect={false}
                      editable={requestState !== 'loading'}
                      onChangeText={handleManualEntryChange}
                      placeholder="Search supported items"
                      placeholderTextColor="#9A948C"
                      style={styles.manualEntryInput}
                      value={manualEntryText}
                    />

                    {isLoadingMaterialLabels ? (
                      <View style={styles.manualStateRow}>
                        <ActivityIndicator color="#050505" size="small" />
                        <Text style={styles.manualStateText}>Loading supported items...</Text>
                      </View>
                    ) : null}

                    {materialLabelsError ? (
                      <View style={styles.manualStateBlock}>
                        <Text style={styles.manualErrorText}>{materialLabelsError}</Text>
                        <Pressable
                          disabled={isLoadingMaterialLabels}
                          onPress={handleRetryMaterialLabels}
                          style={({ pressed }) => [
                            styles.manualRetryButton,
                            pressed && styles.buttonPressed,
                            isLoadingMaterialLabels && styles.buttonDisabled,
                          ]}>
                          <Text style={styles.manualRetryButtonText}>Try Again</Text>
                        </Pressable>
                      </View>
                    ) : null}

                    {!isLoadingMaterialLabels && !materialLabelsError && !normalizedManualEntry ? (
                      <Text style={styles.manualHintText}>
                        Start typing to search supported item labels.
                      </Text>
                    ) : null}

                    {!isLoadingMaterialLabels &&
                    !materialLabelsError &&
                    !!normalizedManualEntry &&
                    !manualSuggestions.length &&
                    !exactSupportedLabel ? (
                      <Text style={styles.manualHintText}>
                        No supported items match that search yet.
                      </Text>
                    ) : null}

                    {!materialLabelsError && manualSuggestions.length ? (
                      <View style={styles.manualSuggestionsGroup}>
                        {manualSuggestions.map((label) => {
                          const isSelected =
                            normalizeLabelKey(label) ===
                            normalizeLabelKey(manualSelectionLabel ?? '');

                          return (
                            <Pressable
                              disabled={requestState === 'loading'}
                              key={label}
                              onPress={() => handleManualSuggestionPress(label)}
                              style={({ pressed }) => [
                                styles.manualSuggestionButton,
                                isSelected && styles.manualSuggestionButtonSelected,
                                pressed && requestState !== 'loading' && styles.buttonPressed,
                                requestState === 'loading' && styles.buttonDisabled,
                              ]}>
                              <Text
                                style={[
                                  styles.manualSuggestionText,
                                  isSelected && styles.manualSuggestionTextSelected,
                                ]}>
                                {label}
                              </Text>
                            </Pressable>
                          );
                        })}
                      </View>
                    ) : null}

                    <View style={styles.manualActionRow}>
                      <Pressable
                        disabled={!canSubmitManualEntry}
                        onPress={handleManualSubmit}
                        style={({ pressed }) => [
                          styles.manualContinueButton,
                          pressed && canSubmitManualEntry && styles.buttonPressed,
                          !canSubmitManualEntry && styles.buttonDisabled,
                        ]}>
                        <Text style={styles.manualContinueButtonText}>Continue</Text>
                      </Pressable>
                    </View>
                  </View>
                </ResultSheet>
              ) : null}

              {visibleSheetState === 'unknown' ? (
                <ResultSheet
                  buttonIconName="camera-outline"
                  buttonLabel="Retake Photo"
                  label="UNIDENTIFIED"
                  materialTag="No Strong Match"
                  onButtonPress={resetScanner}
                  steps={[]}
                  summary="We couldn't identify this clearly without risking the wrong disposal guidance. Retake the photo with brighter light, a simpler background, or a closer crop."
                  title="We couldn't identify this clearly"
                />
              ) : null}
            </Animated.View>
          ) : null}
        </View>

        {isRateLimitWarningVisible ? (
          <DailyScanLimitWarning
            bottomInset={bottomNavOffset}
            maxHeight={rateLimitWarningMaxHeight}
            onDismiss={() => setIsRateLimitWarningVisible(false)}
          />
        ) : null}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  page: {
    backgroundColor: '#070707',
    flex: 1,
  },
  shell: {
    flex: 1,
  },
  sheetOverlay: {
    ...StyleSheet.absoluteFillObject,
    zIndex: 20,
  },
  rateLimitOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(4, 8, 9, 0.42)',
    justifyContent: 'flex-end',
    paddingHorizontal: 16,
    zIndex: 40,
  },
  rateLimitCard: {
    alignSelf: 'center',
    backgroundColor: '#FFFFFF',
    borderColor: '#E9E5DF',
    borderRadius: 24,
    borderWidth: 1,
    gap: 14,
    overflow: 'hidden',
    padding: 18,
    shadowColor: '#111827',
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.18,
    shadowRadius: 24,
    width: '100%',
  },
  rateLimitIcon: {
    alignItems: 'center',
    backgroundColor: '#F4F1EC',
    borderRadius: 18,
    height: 48,
    justifyContent: 'center',
    width: 48,
  },
  rateLimitTextBlock: {
    gap: 7,
  },
  rateLimitEyebrow: {
    color: '#807B75',
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 2.4,
    textTransform: 'uppercase',
  },
  rateLimitTitle: {
    color: '#111111',
    fontSize: 22,
    fontWeight: '900',
    lineHeight: 27,
  },
  rateLimitMessage: {
    color: '#66605B',
    fontSize: 15,
    lineHeight: 22,
  },
  rateLimitButton: {
    alignItems: 'center',
    backgroundColor: '#111111',
    borderRadius: 999,
    justifyContent: 'center',
    marginTop: 2,
    minHeight: 48,
    paddingHorizontal: 18,
    paddingVertical: 13,
  },
  rateLimitButtonText: {
    color: '#FFFFFF',
    fontSize: 15,
    fontWeight: '900',
  },
  cameraCard: {
    flex: 1,
    overflow: 'hidden',
  },
  cameraOverlay: {
    ...StyleSheet.absoluteFillObject,
    paddingHorizontal: 18,
  },
  cameraWarmupOverlay: {
    ...StyleSheet.absoluteFillObject,
    alignItems: 'center',
    backgroundColor: '#0B1218',
    justifyContent: 'center',
    paddingHorizontal: 30,
  },
  cameraWarmupFrame: {
    alignItems: 'center',
    gap: 10,
    paddingHorizontal: 28,
    paddingVertical: 20,
  },
  cameraWarmupTitle: {
    color: '#F3F6F9',
    fontSize: 15,
    fontWeight: '600',
    letterSpacing: -0.1,
    textAlign: 'center',
  },
  backdropTopBar: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    elevation: 50,
    zIndex: 50,
  },
  headerIconButton: {
    alignItems: 'center',
    backgroundColor: 'rgba(17, 24, 39, 0.22)',
    borderColor: 'rgba(255,255,255,0.35)',
    borderRadius: 999,
    borderWidth: 1,
    height: 34,
    justifyContent: 'center',
    width: 34,
  },
  headerIconSpacer: {
    height: 34,
    width: 34,
  },
  closeButton: {
    alignItems: 'center',
    backgroundColor: 'rgba(17, 24, 39, 0.22)',
    borderColor: 'rgba(255,255,255,0.35)',
    borderRadius: 999,
    borderWidth: 1,
    height: 34,
    justifyContent: 'center',
    width: 34,
  },
  scanFrame: {
    alignSelf: 'center',
    borderColor: 'rgba(255,255,255,0.5)',
    borderRadius: 26,
    borderStyle: 'dashed',
    borderWidth: 2,
    height: 250,
    width: 250,
  },
  scanFrameWrap: {
    flex: 1,
    justifyContent: 'center',
    marginBottom: 200,
  },
  targetRing: {
    alignItems: 'center',
    borderColor: 'rgba(255,255,255,0.4)',
    borderRadius: 999,
    borderWidth: 1,
    height: 42,
    justifyContent: 'center',
    left: 104,
    position: 'absolute',
    top: 104,
    width: 42,
  },
  targetDot: {
    backgroundColor: 'rgba(255,255,255,0.85)',
    borderRadius: 999,
    height: 8,
    width: 8,
  },
  cameraControls: {
    alignItems: 'center',
    bottom: 24,
    flexDirection: 'row',
    justifyContent: 'space-between',
    left: 18,
    position: 'absolute',
    right: 18,
  },
  iconActionButton: {
    alignItems: 'center',
    backgroundColor: 'rgba(12, 14, 18, 0.42)',
    borderColor: 'rgba(255,255,255,0.35)',
    borderRadius: 999,
    borderWidth: 1,
    height: 52,
    justifyContent: 'center',
    width: 52,
  },
  iconActionSpacer: {
    width: 52,
  },
  shutterButton: {
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    borderRadius: 999,
    height: 82,
    justifyContent: 'center',
    width: 82,
  },
  shutterInner: {
    borderColor: '#050505',
    borderRadius: 999,
    borderWidth: 4,
    height: 68,
    width: 68,
  },
  buttonDisabled: {
    opacity: 0.55,
  },
  buttonPressed: {
    opacity: 0.82,
  },
  loadingOverlay: {
    alignItems: 'center',
    backgroundColor: 'rgba(4, 8, 9, 0.52)',
    bottom: 0,
    gap: 18,
    justifyContent: 'center',
    left: 0,
    position: 'absolute',
    right: 0,
    top: 0,
  },
  analyzingImageFrame: {
    alignItems: 'center',
    height: 86,
    justifyContent: 'center',
    width: 92,
  },
  analyzingGlyph: {
    height: 52,
    position: 'relative',
    width: 58,
  },
  analyzingGlyphOutline: {
    borderColor: '#FFFFFF',
    borderRadius: 7,
    borderWidth: 3,
    bottom: 3,
    left: 3,
    position: 'absolute',
    right: 3,
    top: 3,
  },
  analyzingMountainReveal: {
    bottom: 3,
    left: 3,
    overflow: 'hidden',
    position: 'absolute',
    top: 3,
  },
  analyzingMountainCanvas: {
    height: 46,
    left: 0,
    position: 'absolute',
    top: 0,
    width: 52,
  },
  analyzingSun: {
    borderColor: '#FFFFFF',
    borderRadius: 999,
    borderWidth: 3,
    height: 11,
    left: 12,
    position: 'absolute',
    top: 11,
    width: 11,
  },
  analyzingMountainFirst: {
    backgroundColor: '#FFFFFF',
    bottom: 12,
    height: 3,
    left: 2,
    position: 'absolute',
    transform: [{ rotate: '-42deg' }],
    width: 30,
  },
  analyzingMountainSecond: {
    backgroundColor: '#FFFFFF',
    bottom: 12,
    height: 3,
    left: 24,
    position: 'absolute',
    transform: [{ rotate: '43deg' }],
    width: 28,
  },
  analyzingPixelReveal: {
    bottom: 3,
    overflow: 'hidden',
    position: 'absolute',
    right: 3,
    top: 3,
  },
  analyzingPixelField: {
    height: 46,
    position: 'absolute',
    right: 0,
    top: 0,
    width: 52,
  },
  analyzingScanBeam: {
    alignItems: 'center',
    bottom: 12,
    justifyContent: 'center',
    left: 44,
    position: 'absolute',
    top: 12,
    width: 4,
  },
  analyzingScanLine: {
    backgroundColor: '#FFFFFF',
    borderRadius: 999,
    height: '100%',
    width: 3,
  },
  analyzingScanCapTop: {
    backgroundColor: '#FFFFFF',
    borderRadius: 999,
    height: 3,
    left: -3,
    position: 'absolute',
    top: 0,
    width: 10,
  },
  analyzingScanCapBottom: {
    backgroundColor: '#FFFFFF',
    borderRadius: 999,
    bottom: 0,
    height: 3,
    left: -3,
    position: 'absolute',
    width: 10,
  },
  analyzingPixel: {
    backgroundColor: '#FFFFFF',
    position: 'absolute',
  },
  loadingShimmerTextWrap: {
    alignSelf: 'center',
    position: 'relative',
  },
  loadingText: {
    color: '#A9A9A9',
    fontSize: 16,
    fontWeight: '700',
    lineHeight: 22,
    textAlign: 'center',
  },
  loadingShimmerMask: {
    bottom: 0,
    left: 0,
    overflow: 'hidden',
    position: 'absolute',
    top: 0,
  },
  loadingShimmerMaskText: {
    color: '#000000',
    fontSize: 16,
    fontWeight: '700',
    lineHeight: 22,
    textAlign: 'center',
  },
  loadingShimmerGradientBand: {
    height: 22,
    width: LOADING_SHIMMER_BAND_WIDTH,
  },
  sheetWrap: {
    left: 16,
    overflow: 'visible',
    position: 'absolute',
    right: 16,
    zIndex: 20,
  },
  manualEntrySection: {
    gap: 12,
  },
  manualEntryPrompt: {
    color: '#66605B',
    fontSize: 14,
    fontWeight: '700',
    textAlign: 'center',
  },
  manualEntryInput: {
    backgroundColor: '#F7F4EF',
    borderColor: '#E8E2DA',
    borderRadius: 18,
    borderWidth: 1,
    color: '#050505',
    fontSize: 16,
    fontWeight: '600',
    paddingHorizontal: 16,
    paddingVertical: 14,
  },
  manualStateRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 10,
    justifyContent: 'center',
  },
  manualStateText: {
    color: '#66605B',
    fontSize: 13,
    fontWeight: '600',
  },
  manualStateBlock: {
    alignItems: 'center',
    gap: 10,
  },
  manualErrorText: {
    color: '#9B3D33',
    fontSize: 13,
    fontWeight: '700',
    lineHeight: 18,
    textAlign: 'center',
  },
  manualHintText: {
    color: '#8B857F',
    fontSize: 13,
    fontWeight: '600',
    lineHeight: 18,
    textAlign: 'center',
  },
  manualRetryButton: {
    alignItems: 'center',
    backgroundColor: '#F4F1EC',
    borderColor: '#E3DED6',
    borderRadius: 999,
    borderWidth: 1,
    justifyContent: 'center',
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  manualRetryButtonText: {
    color: '#333333',
    fontSize: 14,
    fontWeight: '800',
  },
  manualSuggestionsGroup: {
    gap: 8,
  },
  manualSuggestionButton: {
    backgroundColor: '#F7F4EF',
    borderColor: '#E8E2DA',
    borderRadius: 18,
    borderWidth: 1,
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  manualSuggestionButtonSelected: {
    backgroundColor: '#050505',
    borderColor: '#050505',
  },
  manualSuggestionText: {
    color: '#050505',
    fontSize: 15,
    fontWeight: '700',
  },
  manualSuggestionTextSelected: {
    color: '#FFFFFF',
  },
  manualActionRow: {
    flexDirection: 'row',
    gap: 10,
  },
  manualBackButton: {
    alignItems: 'center',
    backgroundColor: '#F4F1EC',
    borderColor: '#E3DED6',
    borderRadius: 999,
    borderWidth: 1,
    flex: 1,
    justifyContent: 'center',
    paddingVertical: 12,
  },
  manualBackButtonText: {
    color: '#333333',
    fontSize: 14,
    fontWeight: '800',
  },
  manualContinueButton: {
    alignItems: 'center',
    backgroundColor: '#050505',
    borderRadius: 999,
    flex: 1,
    justifyContent: 'center',
    paddingVertical: 12,
  },
  manualContinueButtonText: {
    color: '#FFFFFF',
    fontSize: 14,
    fontWeight: '800',
  },
  permissionState: {
    alignItems: 'center',
    backgroundColor: '#111827',
    borderTopLeftRadius: 34,
    borderTopRightRadius: 34,
    flex: 1,
    gap: 14,
    justifyContent: 'center',
    paddingHorizontal: 28,
  },
  permissionTitle: {
    color: '#FFFFFF',
    fontSize: 20,
    fontWeight: '800',
    lineHeight: 28,
    textAlign: 'center',
  },
  permissionButton: {
    backgroundColor: '#FFFFFF',
    borderRadius: 999,
    paddingHorizontal: 18,
    paddingVertical: 12,
  },
  permissionButtonText: {
    color: '#050505',
    fontSize: 15,
    fontWeight: '800',
  },
});
