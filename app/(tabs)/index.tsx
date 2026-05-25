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
  Linking,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
  useWindowDimensions,
} from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';

import { BOTTOM_NAV_BAR_HEIGHT } from '@/components/bottom-nav-bar';
import { ResultSheet } from '@/components/result-sheet';
import { API_BASE_URL } from '@/constants/api';
import { setLastScannedItem } from '@/constants/scan-session';

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
  steps: string[];
};

type SheetViewState = 'idle' | PredictionStatus;
type RequestState = 'idle' | 'loading';

type ScannerResultData = {
  item: string;
  label: string;
  title: string;
  materialTag?: string | null;
  summary: string;
  steps: string[];
  buttonLabel: string;
  buttonIconName: keyof typeof Ionicons.glyphMap;
};

function toSheetData(response: PredictionResponse): ScannerResultData {
  const action = (response.disposal_action ?? 'follow local guidance').trim().toLowerCase();
  const impact = (response.impact_level ?? 'Local Guidance').trim();
  const materialTag = response.material_code ? `${response.material_code} - ${impact}` : impact;

  return {
    item: response.item,
    label: `IDENTIFIED - ${response.item.toUpperCase()}`,
    title: `${action}.`,
    materialTag,
    summary: `${response.item} is categorized as ${response.category.toLowerCase()} and should be handled through ${action} guidance in your area.`,
    steps: response.steps,
    buttonLabel: 'Find Nearby Locations',
    buttonIconName: 'location-outline',
  };
}

function formatCandidateScore(score: number) {
  return `${Math.round(score * 100)}% similarity`;
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
          enableTorch={isTorchOn}
          facing="back"
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

        <View style={[styles.cameraControls, { bottom: bottomInset + BOTTOM_NAV_BAR_HEIGHT + 28 }]}>
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
  const [permission, requestPermission] = useCameraPermissions();
  const [requestState, setRequestState] = useState<RequestState>('idle');
  const [sheetState, setSheetState] = useState<SheetViewState>('idle');
  const [capturedImageUri, setCapturedImageUri] = useState<string | null>(null);
  const [isTorchOn, setIsTorchOn] = useState(false);
  const [result, setResult] = useState<ScannerResultData | null>(null);
  const [candidates, setCandidates] = useState<PredictionCandidate[]>([]);
  const sheetAnimation = useRef(new Animated.Value(360)).current;
  const resultSheetBottomOffset = insets.bottom + BOTTOM_NAV_BAR_HEIGHT - 10;

  useEffect(() => {
    requestPermission();
  }, [requestPermission]);

  useEffect(() => {
    Animated.spring(sheetAnimation, {
      damping: 18,
      mass: 0.8,
      stiffness: 170,
      toValue: sheetState === 'idle' ? 360 : -resultSheetBottomOffset,
      useNativeDriver: true,
    }).start();
  }, [resultSheetBottomOffset, sheetAnimation, sheetState]);

  const resetScanner = () => {
    predictRequestRef.current += 1;
    setCapturedImageUri(null);
    setResult(null);
    setCandidates([]);
    setRequestState('idle');
    setSheetState('idle');
  };

  const applyPrediction = (prediction: PredictionResponse) => {
    setResult(null);
    setCandidates([]);

    if (prediction.status === 'confident' && prediction.item) {
      const nextResult = toSheetData(prediction);
      setLastScannedItem(prediction.item);
      setResult(nextResult);
      setSheetState('confident');
      return;
    }

    if (prediction.status === 'uncertain' && prediction.candidates.length) {
      setCandidates(prediction.candidates);
      setSheetState('uncertain');
      return;
    }

    setSheetState('unknown');
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

    const requestId = predictRequestRef.current + 1;
    predictRequestRef.current = requestId;

    if (imageUri) {
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

      applyPrediction(prediction);
    } catch {
      if (requestId !== predictRequestRef.current) {
        return;
      }

      if (selectedItem) {
        Alert.alert('Could not confirm that selection. Please try again.');
      } else {
        setCapturedImageUri(null);
        setResult(null);
        setCandidates([]);
        setSheetState('idle');
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

  return (
    <SafeAreaView edges={[]} style={styles.page}>
      <StatusBar style="light" />
      <View style={styles.shell}>
        {permissionDenied ? (
          <CameraPermissionNotice />
        ) : permission?.granted ? (
          <CameraArea
            cameraRef={cameraRef}
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

        <Animated.View
          style={[
            styles.sheetWrap,
            {
              maxHeight: windowHeight - insets.top - 28,
              transform: [{ translateY: sheetAnimation }],
            },
          ]}>
          {sheetState !== 'idle' ? (
            <ScrollView
              bounces={false}
              contentContainerStyle={styles.sheetContent}
              showsVerticalScrollIndicator={false}>
              {sheetState === 'confident' && result ? (
                <ResultSheet
                  buttonIconName={result.buttonIconName}
                  buttonLabel={result.buttonLabel}
                  label={result.label}
                  materialTag={result.materialTag}
                  onButtonPress={() =>
                    router.navigate({
                      pathname: '/(tabs)/nearby',
                      params: { item: result.item },
                    })
                  }
                  steps={result.steps}
                  summary={result.summary}
                  title={result.title}
                />
              ) : null}

              {sheetState === 'uncertain' ? (
                <ResultSheet
                  buttonIconName="camera-outline"
                  buttonLabel="Retake Photo"
                  label="REVIEW NEEDED"
                  materialTag="Multiple Plausible Matches"
                  onButtonPress={resetScanner}
                  steps={[]}
                  summary="We found a few plausible waste-item matches for this image. Pick the best option below and we'll load the correct disposal guidance on this page."
                  title="Which item is this?">
                  <View style={styles.choiceButtonGroup}>
                    {candidates.map((candidate) => (
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
                    ))}
                  </View>
                </ResultSheet>
              ) : null}

              {sheetState === 'unknown' ? (
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
            </ScrollView>
          ) : null}
        </Animated.View>
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
    marginHorizontal: 16,
    marginTop: -34,
    paddingBottom: 24,
  },
  sheetContent: {
    gap: 14,
    paddingBottom: 20,
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
