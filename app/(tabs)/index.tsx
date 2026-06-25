import { Ionicons } from '@expo/vector-icons';
import { CameraView, useCameraPermissions } from 'expo-camera';
import * as ImagePicker from 'expo-image-picker';
import { useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Animated,
  Image,
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

import { BOTTOM_NAV_BAR_HEIGHT } from '@/components/bottom-nav-bar';
import { ResultSheet } from '@/components/result-sheet';
import { API_BASE_URL } from '@/constants/api';
import { setLastScannedItem } from '@/constants/scan-session';
import {
  saveRecentScan,
  updateRecentScan,
  type RecentScan,
} from '../../storage/recentScans';

const CAMERA_CONTROLS_NAV_CLEARANCE = 52;

type PredictionStatus = 'confident' | 'uncertain' | 'unknown';

type PredictionCandidate = {
  label: string;
  score: number;
};

type PredictionResponse = {
  item: string;
  category: string;
  status: PredictionStatus;
  candidates: PredictionCandidate[];
  disposal_action: string | null;
  material_code: string | null;
  impact_level: string | null;
  summary?: string | null;
  steps: string[];
  guidance_source?: string;
  guidanceSource?: string;
  warnings?: string[];
  guidance_metadata?: Record<string, unknown>;
  guidanceMetadata?: Record<string, unknown>;
};

type SheetViewState = 'idle' | PredictionStatus;
type VisibleSheetState = Exclude<SheetViewState, 'idle'>;
type RequestState = 'idle' | 'loading';
type PredictionRequestSource = 'image' | 'selection';
type CorrectionSheetMode = 'candidate-list' | 'manual-entry';

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
};

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

  const topCandidate = prediction.candidates[0]?.label?.trim();
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
  };
}

function toSheetData(response: PredictionResponse): ScannerResultData {
  const action = getDisposalActionText(response.disposal_action);

  return {
    item: response.item,
    label: `IDENTIFIED - ${response.item.toUpperCase()}`,
    title: `${action}.`,
    materialTag: getCompactPillLabel(response),
    summary: getPredictionSummary(response),
    steps: response.steps,
    warnings: Array.isArray(response.warnings) ? response.warnings : [],
    guidanceSource: response.guidanceSource ?? response.guidance_source,
    guidanceMetadata: getNormalizedGuidanceMetadata(response),
    showNearbyButton: shouldShowNearbyButton(response),
  };
}

function formatCandidateScore(score: number) {
  return `${Math.round(score * 100)}% similarity`;
}

function normalizeLabelKey(value: string) {
  return value.trim().toLowerCase();
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

type CameraAreaProps = {
  cameraRef: React.RefObject<CameraView | null>;
  cameraPreviewKey: number;
  capturedImageUri: string | null;
  bottomInset: number;
  isLoading: boolean;
  isTorchOn: boolean;
  topInset: number;
  onClose: () => void;
  onToggleTorch: () => void;
  onPickImage: () => void;
  onTakePhoto: () => void;
};

function CameraArea({
  cameraRef,
  cameraPreviewKey,
  bottomInset,
  capturedImageUri,
  isLoading,
  isTorchOn,
  topInset,
  onClose,
  onToggleTorch,
  onPickImage,
  onTakePhoto,
}: CameraAreaProps) {
  return (
    <View style={styles.cameraCard}>
      {capturedImageUri ? (
        <Image source={{ uri: capturedImageUri }} style={StyleSheet.absoluteFillObject} />
      ) : (
        <CameraView
          active
          enableTorch={isTorchOn}
          facing="back"
          key={cameraPreviewKey}
          mode="picture"
          ref={cameraRef}
          style={StyleSheet.absoluteFillObject}
        />
      )}

      <View style={styles.cameraOverlay}>
        <View style={[styles.backdropTopBar, { paddingTop: topInset + 16 }]}>
          <Pressable onPress={onToggleTorch} style={styles.headerIconButton}>
            <Ionicons color="#F3F6F9" name={isTorchOn ? 'flash' : 'flash-outline'} size={20} />
          </Pressable>
          <Pressable onPress={onClose} style={styles.closeButton}>
            <Ionicons color="#F3F6F9" name="close" size={20} />
          </Pressable>
        </View>

        <View pointerEvents="none" style={styles.scanFrameWrap}>
          <View style={styles.scanFrame}>
            <View style={styles.targetRing}>
              <View style={styles.targetDot} />
            </View>
          </View>
        </View>

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
            disabled={isLoading}
            onPress={onTakePhoto}
            style={[styles.shutterButton, isLoading && styles.buttonDisabled]}>
            <View style={styles.shutterInner} />
          </Pressable>

          <View style={styles.iconActionSpacer} />
        </View>

        {capturedImageUri && isLoading ? (
          <View style={styles.loadingOverlay}>
            <ActivityIndicator color="#FFFFFF" size="large" />
            <Text style={styles.loadingText}>Analyzing...</Text>
          </View>
        ) : null}
      </View>
    </View>
  );
}

export default function ScannerScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { height: windowHeight } = useWindowDimensions();
  const cameraRef = useRef<CameraView | null>(null);
  const predictRequestRef = useRef(0);
  const activeScanSessionRef = useRef<ActiveScanSession | null>(null);
  const [permission, requestPermission] = useCameraPermissions();
  const [requestState, setRequestState] = useState<RequestState>('idle');
  const [sheetState, setSheetState] = useState<SheetViewState>('idle');
  const [visibleSheetState, setVisibleSheetState] = useState<VisibleSheetState | 'idle'>('idle');
  const [capturedImageUri, setCapturedImageUri] = useState<string | null>(null);
  const [cameraPreviewKey, setCameraPreviewKey] = useState(0);
  const [isTorchOn, setIsTorchOn] = useState(false);
  const [result, setResult] = useState<ScannerResultData | null>(null);
  const [candidates, setCandidates] = useState<PredictionCandidate[]>([]);
  const [correctionSheetMode, setCorrectionSheetMode] =
    useState<CorrectionSheetMode>('candidate-list');
  const [materialLabels, setMaterialLabels] = useState<string[] | null>(null);
  const [isLoadingMaterialLabels, setIsLoadingMaterialLabels] = useState(false);
  const [materialLabelsError, setMaterialLabelsError] = useState<string | null>(null);
  const [manualEntryText, setManualEntryText] = useState('');
  const [selectedManualLabel, setSelectedManualLabel] = useState<string | null>(null);
  const [sheetHeight, setSheetHeight] = useState(0);
  const sheetAnimation = useRef(new Animated.Value(windowHeight)).current;
  const bottomNavOffset = Math.max(insets.bottom, 12);
  const resultSheetBottomOffset = bottomNavOffset + BOTTOM_NAV_BAR_HEIGHT + 20;
  const hiddenSheetOffset = Math.max(sheetHeight + resultSheetBottomOffset + 24, windowHeight);

  useEffect(() => {
    requestPermission();
  }, [requestPermission]);

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

  const clearActiveScanSession = () => {
    activeScanSessionRef.current = null;
  };

  const resetManualEntry = () => {
    setCorrectionSheetMode('candidate-list');
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
    resetManualEntry();
    setVisibleSheetState('uncertain');
    setSheetState('uncertain');
  };

  const handleOpenManualEntry = () => {
    setCorrectionSheetMode('manual-entry');
    setManualEntryText('');
    setSelectedManualLabel(null);

    if (!materialLabels && !isLoadingMaterialLabels) {
      void loadMaterialLabels();
    }
  };

  const handleManualEntryBack = () => {
    resetManualEntry();
  };

  const handleRetryMaterialLabels = () => {
    if (!isLoadingMaterialLabels) {
      void loadMaterialLabels();
    }
  };

  const resetScanner = () => {
    predictRequestRef.current += 1;
    clearActiveScanSession();
    restoreCameraPreview();
    setRequestState('idle');
    setSheetState('idle');
    resetManualEntry();

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
      status: activeSession.originalStatus,
      scannedAt: activeSession.scannedAt,
      updatedAt: new Date().toISOString(),
      materialTag: getCompactPillLabel(prediction),
      summary: getPredictionSummary(prediction),
      steps: prediction.steps,
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
    const nextCandidates =
      prediction.candidates.length > 0 ? prediction.candidates : fallbackCandidates;

    resetManualEntry();
    setResult(null);
    setCandidates(nextCandidates);

    if (requestSource === 'image' && activeScanSessionRef.current) {
      activeScanSessionRef.current = {
        ...activeScanSessionRef.current,
        predictedItem: getPredictedItemFromPrediction(prediction),
        originalStatus: prediction.status,
      };
    }

    if (prediction.status === 'confident' && prediction.item) {
      const nextResult = toSheetData(prediction);
      setLastScannedItem(prediction.item);
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

    if (prediction.status === 'uncertain') {
      setVisibleSheetState('uncertain');
      setSheetState('uncertain');
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
    const requestId = predictRequestRef.current + 1;
    predictRequestRef.current = requestId;

    if (imageUri) {
      activeScanSessionRef.current = createActiveScanSession(imageUri);
      setCapturedImageUri(imageUri);
      setResult(null);
      setCandidates([]);
      setSheetState('idle');
    }

    setRequestState('loading');

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
      const response = await fetch(`${API_BASE_URL}/predict`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`Request failed with status ${response.status}`);
      }

      const prediction = (await response.json()) as PredictionResponse;
      if (requestId !== predictRequestRef.current) {
        return;
      }

      await applyPrediction(prediction, requestSource, fallbackCandidates);
    } catch {
      if (requestId !== predictRequestRef.current) {
        return;
      }

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
      if (requestId === predictRequestRef.current) {
        setRequestState('idle');
      }
    }
  };

  const handleTakePhoto = async () => {
    if (!cameraRef.current || requestState === 'loading') {
      return;
    }

    try {
      const photo = await cameraRef.current.takePictureAsync({
        quality: 0.7,
        base64: false,
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
  const filteredCandidates = candidates.filter(
    (candidate) => normalizeLabelKey(candidate.label) !== normalizedCurrentPredictedLabel
  );
  const visibleCandidateKeys = new Set(
    filteredCandidates.map((candidate) => normalizeLabelKey(candidate.label))
  );
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
            !visibleCandidateKeys.has(normalizedLabel) &&
            normalizedLabel.includes(normalizedManualEntry)
          );
        })
        .slice(0, 6)
    : [];
  const canSubmitManualEntry =
    !!manualSelectionLabel && requestState !== 'loading' && !materialLabelsError;
  const isShowingManualEntry = correctionSheetMode === 'manual-entry';
  const canShowCandidateChoices = filteredCandidates.length > 0;

  const handleManualEntryChange = (value: string) => {
    setManualEntryText(value);
    setSelectedManualLabel(null);
  };

  const handleManualSuggestionPress = (label: string) => {
    setManualEntryText(label);
    setSelectedManualLabel(label);
  };

  const handleManualSubmit = () => {
    if (!manualSelectionLabel || requestState === 'loading') {
      return;
    }

    void sendPredictionRequest({ selectedItem: manualSelectionLabel });
  };

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
            isLoading={requestState === 'loading'}
            isTorchOn={isTorchOn}
            topInset={insets.top}
            onClose={resetScanner}
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
                  bottom: resultSheetBottomOffset,
                  maxHeight: Math.min(
                    windowHeight * 0.78,
                    windowHeight - insets.top - resultSheetBottomOffset - 72,
                  ),
                  transform: [{ translateY: sheetAnimation }],
                },
              ]}>
              {visibleSheetState === 'confident' && result ? (
                <ResultSheet
                  buttonIconName="location-outline"
                  buttonLabel={result.showNearbyButton ? 'Find Nearby Locations' : undefined}
                  condenseGuidance
                  guidanceMetadata={result.guidanceMetadata}
                  guidanceSource={result.guidanceSource}
                  label={result.label}
                  materialTag={result.materialTag}
                  onButtonPress={
                    result.showNearbyButton
                      ? () =>
                          router.navigate({
                            pathname: '/(tabs)/nearby',
                            params: { item: result.item },
                          })
                      : undefined
                  }
                  onClose={resetScanner}
                  secondaryButtonIconName="swap-horizontal-outline"
                  secondaryButtonLabel="Change Item"
                  onSecondaryButtonPress={handleChangeItem}
                  steps={result.steps}
                  summary={result.summary}
                  title={result.title}
                  warnings={result.warnings}
                />
              ) : null}

              {visibleSheetState === 'uncertain' ? (
                <ResultSheet
                  buttonIconName="camera-outline"
                  buttonLabel="Retake Photo"
                  label="REVIEW NEEDED"
                  materialTag="Multiple Plausible Matches"
                  onButtonPress={resetScanner}
                  onClose={resetScanner}
                  steps={[]}
                  summary={
                    isShowingManualEntry
                      ? 'Search for the supported item label that best matches this object, then continue to load the right disposal guidance.'
                      : candidates.length > 0
                        ? "Pick the best match below, or choose Other to search the full supported item list."
                        : "We couldn't load alternate matches for this scan, but you can still search the supported item list or retake the photo."
                  }
                  title="Which item is this?">
                  {isShowingManualEntry ? (
                    <View style={styles.manualEntrySection}>
                        <Text style={styles.manualEntryPrompt}>What item is this?</Text>
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
                                  key={label}
                                  onPress={() => handleManualSuggestionPress(label)}
                                  style={({ pressed }) => [
                                    styles.manualSuggestionButton,
                                    isSelected && styles.manualSuggestionButtonSelected,
                                    pressed && styles.buttonPressed,
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
                            onPress={handleManualEntryBack}
                            style={({ pressed }) => [
                              styles.manualBackButton,
                              pressed && styles.buttonPressed,
                            ]}>
                            <Text style={styles.manualBackButtonText}>Back</Text>
                          </Pressable>
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
                    ) : (
                      <View style={styles.choiceButtonGroup}>
                        {canShowCandidateChoices ? (
                          filteredCandidates.map((candidate) => (
                            <Pressable
                              disabled={requestState === 'loading'}
                              key={candidate.label}
                              onPress={() => sendPredictionRequest({ selectedItem: candidate.label })}
                              style={({ pressed }) => [
                                styles.choiceButton,
                                pressed && styles.choiceButtonPressed,
                                requestState === 'loading' && styles.buttonDisabled,
                              ]}>
                              <Text numberOfLines={2} style={styles.choiceButtonLabel}>
                                {candidate.label}
                              </Text>
                              <View style={styles.choiceButtonMeta}>
                                <Ionicons color="#5B6470" name="sparkles-outline" size={13} />
                                <Text style={styles.choiceButtonMetaText}>
                                  {formatCandidateScore(candidate.score)}
                                </Text>
                              </View>
                            </Pressable>
                          ))
                        ) : (
                          <View style={styles.choiceFallback}>
                            <Ionicons color="#5B6470" name="information-circle-outline" size={18} />
                            <Text style={styles.choiceFallbackText}>
                              No alternate candidate buttons are available, but you can search the
                              supported item list below.
                            </Text>
                          </View>
                        )}
                        <Pressable
                          disabled={requestState === 'loading'}
                          onPress={handleOpenManualEntry}
                          style={({ pressed }) => [
                            styles.choiceButton,
                            styles.otherChoiceButton,
                            pressed && styles.choiceButtonPressed,
                            requestState === 'loading' && styles.buttonDisabled,
                          ]}>
                          <Text numberOfLines={1} style={styles.choiceButtonLabel}>
                            Other
                          </Text>
                        </Pressable>
                    </View>
                  )}
                </ResultSheet>
              ) : null}

              {visibleSheetState === 'unknown' ? (
                <ResultSheet
                  buttonIconName="camera-outline"
                  buttonLabel="Retake Photo"
                  label="UNIDENTIFIED"
                  materialTag="No Strong Match"
                  onButtonPress={resetScanner}
                  onClose={resetScanner}
                  steps={[]}
                  summary="We couldn't identify this clearly without risking the wrong disposal guidance. Retake the photo with brighter light, a simpler background, or a closer crop."
                  title="We couldn't identify this clearly"
                />
              ) : null}
            </Animated.View>
          ) : null}
        </View>
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
  cameraCard: {
    flex: 1,
    overflow: 'hidden',
  },
  cameraOverlay: {
    ...StyleSheet.absoluteFillObject,
    paddingHorizontal: 18,
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
    backgroundColor: 'rgba(5, 5, 5, 0.36)',
    bottom: 0,
    justifyContent: 'center',
    left: 0,
    position: 'absolute',
    right: 0,
    top: 0,
  },
  loadingText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '700',
    marginTop: 12,
  },
  sheetWrap: {
    left: 16,
    overflow: 'visible',
    position: 'absolute',
    right: 16,
    zIndex: 20,
  },
  choiceButtonGroup: {
    gap: 10,
    marginTop: -2,
  },
  choiceButton: {
    alignItems: 'center',
    backgroundColor: '#F7F4EF',
    borderColor: '#E8E2DA',
    borderRadius: 22,
    borderWidth: 1,
    gap: 6,
    minHeight: 58,
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  choiceButtonPressed: {
    opacity: 0.88,
  },
  otherChoiceButton: {
    borderStyle: 'dashed',
  },
  choiceButtonLabel: {
    color: '#050505',
    fontSize: 19,
    fontWeight: '800',
    letterSpacing: -0.4,
    lineHeight: 24,
    textAlign: 'center',
  },
  choiceButtonMeta: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 6,
  },
  choiceButtonMetaText: {
    color: '#5B6470',
    fontSize: 12,
    fontWeight: '700',
  },
  choiceFallback: {
    alignItems: 'center',
    backgroundColor: '#F7F4EF',
    borderColor: '#E8E2DA',
    borderRadius: 22,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 10,
    paddingHorizontal: 16,
    paddingVertical: 14,
  },
  choiceFallbackText: {
    color: '#66605B',
    flex: 1,
    fontSize: 14,
    fontWeight: '600',
    lineHeight: 20,
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
