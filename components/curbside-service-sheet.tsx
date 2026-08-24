import { Ionicons } from '@expo/vector-icons';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AccessibilityInfo,
  ActivityIndicator,
  Animated,
  KeyboardAvoidingView,
  Modal,
  PanResponder,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { PRIMARY_TEXT_STYLES, SECONDARY_TEXT_STYLES } from '@/constants/typography';
import type { ProviderVerificationResult } from '@/api/contracts';

export type PickupDay =
  | 'Monday'
  | 'Tuesday'
  | 'Wednesday'
  | 'Thursday'
  | 'Friday'
  | 'Saturday'
  | 'Sunday';

export type CurbsideDraft = {
  hasCurbsideRecycling: boolean | null;
  providerName: string;
  recyclingPickupDay: PickupDay | null;
  remindersEnabled: boolean;
  trashPickupDay: PickupDay | null;
};

export const EMPTY_CURBSIDE_DRAFT: CurbsideDraft = {
  hasCurbsideRecycling: null,
  providerName: '',
  recyclingPickupDay: null,
  remindersEnabled: false,
  trashPickupDay: null,
};

const PICKUP_DAYS: PickupDay[] = [
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
];

const PROVIDER_VERIFY_DELAY_MS = 600;
const PROVIDER_VERIFY_ANIMATION_MS = 220;
const PROVIDER_VERIFY_BUTTON_WIDTH = 88;
const PROVIDER_VERIFY_BUTTON_GAP = 8;
// Reusable pickup-day and reminder UI is intentionally preserved for a later
// release. Closed-testing builds must not expose or activate notifications.
export const PICKUP_SCHEDULE_AND_NOTIFICATIONS_ENABLED = false;

export function cloneCurbsideDraft(draft: CurbsideDraft): CurbsideDraft {
  return { ...draft };
}

function PickupDayPicker({
  label,
  onChange,
  value,
}: {
  label: string;
  onChange: (day: PickupDay) => void;
  value: PickupDay | null;
}) {
  return (
    <View style={styles.fieldGroup}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <View style={styles.dayOptions}>
        {PICKUP_DAYS.map((day) => {
          const selected = value === day;
          return (
            <Pressable
              accessibilityLabel={`${label}, ${day}`}
              accessibilityRole="radio"
              accessibilityState={{ checked: selected }}
              key={day}
              onPress={() => onChange(day)}
              style={({ pressed }) => [
                styles.dayOption,
                selected && styles.dayOptionSelected,
                pressed && styles.pressed,
              ]}
            >
              <Text style={[styles.dayOptionText, selected && styles.dayOptionTextSelected]}>
                {day.slice(0, 3)}
              </Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

export function CurbsideServiceSheet({
  draft,
  onChange,
  onDismiss,
  onConfirm = async () => false,
  onSave,
  onVerify = () => undefined,
  providerError = null,
  providerLocked = false,
  providerLockRetryAt = null,
  providerResult = null,
  providerStatus = 'idle',
  locationLabel = null,
  saveDisabled = false,
  saving = false,
  visible,
}: {
  draft: CurbsideDraft;
  onChange: (draft: CurbsideDraft) => void;
  onDismiss: () => void;
  onConfirm?: () => Promise<boolean>;
  onSave: (draft: CurbsideDraft) => void | boolean | Promise<void | boolean>;
  onVerify?: () => void;
  providerError?: string | null;
  providerLocked?: boolean;
  providerLockRetryAt?: string | null;
  providerResult?: ProviderVerificationResult | null;
  providerStatus?: 'idle' | 'loading' | 'verified' | 'not_verified' | 'uncertain' | 'cooldown' | 'failure';
  locationLabel?: string | null;
  saveDisabled?: boolean;
  saving?: boolean;
  visible: boolean;
}) {
  const insets = useSafeAreaInsets();
  const progress = useRef(new Animated.Value(0)).current;
  const closingRef = useRef(false);
  const [reduceMotion, setReduceMotion] = useState(false);
  const providerVerifyProgress = useRef(new Animated.Value(0)).current;
  const providerVerifyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const providerInputRef = useRef<TextInput>(null);
  const lastPromptedResultRef = useRef<ProviderVerificationResult | null>(null);
  const [providerVerifyVisible, setProviderVerifyVisible] = useState(false);
  const [providerConfirmationVisible, setProviderConfirmationVisible] = useState(false);
  const [providerCooldownVisible, setProviderCooldownVisible] = useState(false);

  const clearProviderVerifyTimer = useCallback(() => {
    if (providerVerifyTimerRef.current !== null) {
      clearTimeout(providerVerifyTimerRef.current);
      providerVerifyTimerRef.current = null;
    }
  }, []);

  const resetProviderVerification = useCallback(() => {
    clearProviderVerifyTimer();
    setProviderVerifyVisible(false);
    providerVerifyProgress.stopAnimation();
    providerVerifyProgress.setValue(0);
  }, [clearProviderVerifyTimer, providerVerifyProgress]);

  useEffect(() => {
    void AccessibilityInfo.isReduceMotionEnabled().then(setReduceMotion);
    const subscription = AccessibilityInfo.addEventListener('reduceMotionChanged', setReduceMotion);
    return () => subscription.remove();
  }, []);

  useEffect(() => {
    const targetValue = providerVerifyVisible ? 1 : 0;

    providerVerifyProgress.stopAnimation();
    if (reduceMotion) {
      providerVerifyProgress.setValue(targetValue);
      return;
    }

    Animated.timing(providerVerifyProgress, {
      duration: PROVIDER_VERIFY_ANIMATION_MS,
      toValue: targetValue,
      useNativeDriver: false,
    }).start();

    return () => providerVerifyProgress.stopAnimation();
  }, [providerVerifyProgress, providerVerifyVisible, reduceMotion]);

  useEffect(() => {
    if (!visible) {
      resetProviderVerification();
      setProviderConfirmationVisible(false);
      setProviderCooldownVisible(false);
    }
  }, [resetProviderVerification, visible]);

  useEffect(() => {
    if (!providerResult) {
      lastPromptedResultRef.current = null;
      setProviderConfirmationVisible(false);
      return;
    }
    if (
      visible &&
      !providerLocked &&
      providerResult.status === 'verified' &&
      (providerResult.location_match === 'regional' || providerResult.location_match === 'unknown') &&
      lastPromptedResultRef.current !== providerResult
    ) {
      lastPromptedResultRef.current = providerResult;
      setProviderConfirmationVisible(true);
    }
  }, [providerLocked, providerResult, visible]);

  useEffect(() => {
    if (providerLocked) resetProviderVerification();
  }, [providerLocked, resetProviderVerification]);

  useEffect(
    () => () => {
      clearProviderVerifyTimer();
      providerVerifyProgress.stopAnimation();
    },
    [clearProviderVerifyTimer, providerVerifyProgress],
  );

  useEffect(() => {
    if (!visible) {
      progress.setValue(0);
      closingRef.current = false;
      return;
    }

    closingRef.current = false;
    if (reduceMotion) {
      progress.setValue(1);
      return;
    }

    Animated.spring(progress, {
      damping: 22,
      mass: 0.85,
      stiffness: 210,
      toValue: 1,
      useNativeDriver: true,
    }).start();
  }, [progress, reduceMotion, visible]);

  const close = useCallback(
    (save: boolean) => {
      if (closingRef.current) {
        return;
      }
      closingRef.current = true;
      resetProviderVerification();

      const finish = () => {
        if (!save) onDismiss();
      };

      if (save) {
        void Promise.resolve(onSave(cloneCurbsideDraft(draft))).then((saved) => {
          if (saved === false) {
            closingRef.current = false;
          }
        });
        closingRef.current = false;
        return;
      }

      if (reduceMotion) {
        progress.setValue(0);
        finish();
        return;
      }

      Animated.timing(progress, {
        duration: 190,
        toValue: 0,
        useNativeDriver: true,
      }).start(({ finished }) => {
        if (finished) {
          finish();
        }
      });
    },
    [draft, onDismiss, onSave, progress, reduceMotion, resetProviderVerification],
  );

  const handleProviderNameChange = useCallback(
    (providerName: string) => {
      clearProviderVerifyTimer();
      setProviderVerifyVisible(false);
      onChange({ ...draft, providerName });

      if (providerName.trim().length > 0) {
        providerVerifyTimerRef.current = setTimeout(() => {
          providerVerifyTimerRef.current = null;
          setProviderVerifyVisible(true);
        }, PROVIDER_VERIFY_DELAY_MS);
      }
    },
    [clearProviderVerifyTimer, draft, onChange],
  );

  const panResponder = useMemo(
    () =>
      PanResponder.create({
        onMoveShouldSetPanResponder: (_, gestureState) =>
          gestureState.dy > 6 && Math.abs(gestureState.dy) > Math.abs(gestureState.dx),
        onPanResponderMove: (_, gestureState) => {
          if (gestureState.dy > 0) {
            progress.setValue(Math.max(0, 1 - gestureState.dy / 420));
          }
        },
        onPanResponderRelease: (_, gestureState) => {
          if (gestureState.dy > 110 || gestureState.vy > 0.85) {
            close(false);
            return;
          }
          Animated.spring(progress, {
            damping: 22,
            stiffness: 220,
            toValue: 1,
            useNativeDriver: true,
          }).start();
        },
        onPanResponderTerminate: () => {
          Animated.spring(progress, {
            damping: 22,
            stiffness: 220,
            toValue: 1,
            useNativeDriver: true,
          }).start();
        },
      }),
    [close, progress],
  );

  const backdropOpacity = progress.interpolate({
    inputRange: [0, 1],
    outputRange: [0, 0.42],
  });
  const sheetTranslateY = progress.interpolate({
    inputRange: [0, 1],
    outputRange: [700, 0],
  });
  const providerVerifyWidth = providerVerifyProgress.interpolate({
    inputRange: [0, 1],
    outputRange: [0, PROVIDER_VERIFY_BUTTON_WIDTH],
  });
  const providerVerifyMarginLeft = providerVerifyProgress.interpolate({
    inputRange: [0, 1],
    outputRange: [0, PROVIDER_VERIFY_BUTTON_GAP],
  });
  const exactMatch = providerResult?.status === 'verified' && providerResult.location_match === 'exact';
  const retryResult = Boolean(
    providerResult && (
      providerResult.status === 'not_verified' ||
      providerResult.status === 'uncertain' ||
      providerResult.location_match === 'outside'
    )
  );
  const providerIcon = providerLocked
    ? 'lock-closed'
    : exactMatch
      ? 'checkmark-circle'
      : retryResult
        ? 'alert-circle'
        : null;
  const providerHelper = exactMatch
    ? 'Provider found for your area. Confirming locks changes for 24 hours.'
    : retryResult
      ? 'We couldn’t confirm this residential curbside provider. Check the name and try again.'
      : providerLocked
        ? 'Provider confirmed. Changes are locked for 24 hours.'
        : null;
  const providerActionLabel = exactMatch ? 'Confirm' : retryResult ? 'Retry' : 'Verify';
  const providerRetryText = providerLockRetryAt && !Number.isNaN(Date.parse(providerLockRetryAt))
    ? new Date(providerLockRetryAt).toLocaleString()
    : 'the 24-hour lock expires';

  const handleProviderAction = useCallback(() => {
    if (exactMatch) {
      void onConfirm();
      return;
    }
    onVerify();
  }, [exactMatch, onConfirm, onVerify]);

  const handleRegionalConfirm = useCallback(async () => {
    const confirmed = await onConfirm();
    if (confirmed) setProviderConfirmationVisible(false);
  }, [onConfirm]);

  const handleRegionalEdit = useCallback(() => {
    setProviderConfirmationVisible(false);
    providerInputRef.current?.focus();
  }, []);
  const providerInputField = (
    <View style={styles.providerInputFrame}>
      <TextInput
        accessibilityLabel="Curbside recycling provider name"
        autoCapitalize="words"
        editable={!providerLocked}
        onChangeText={handleProviderNameChange}
        placeholder="Example: City sanitation"
        placeholderTextColor="#9A948C"
        pointerEvents={providerLocked ? 'none' : 'auto'}
        ref={providerInputRef}
        style={[
          styles.input,
          exactMatch && styles.inputVerified,
          retryResult && styles.inputRejected,
          providerLocked && styles.inputLocked,
          providerIcon && styles.inputWithIcon,
        ]}
        value={draft.providerName}
      />
      {providerIcon ? (
        <Ionicons
          accessibilityElementsHidden
          color={providerLocked ? '#77716B' : exactMatch ? '#2E7D4F' : '#B44436'}
          name={providerIcon}
          size={20}
          style={styles.providerStateIcon}
        />
      ) : null}
    </View>
  );

  return (
    <Modal
      animationType="none"
      onRequestClose={() => close(false)}
      statusBarTranslucent
      transparent
      visible={visible}
    >
      <View accessibilityViewIsModal style={styles.modalRoot}>
        <Animated.View
          pointerEvents="none"
          style={[styles.backdrop, { opacity: backdropOpacity }]}
        />
        <Pressable
          accessibilityLabel="Dismiss curbside service settings"
          onPress={() => close(false)}
          style={StyleSheet.absoluteFill}
        />
        <KeyboardAvoidingView
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
          pointerEvents="box-none"
          style={styles.keyboardAvoider}
        >
          <Animated.View
            style={[
              styles.sheet,
              {
                paddingBottom: Math.max(insets.bottom, 16) + 12,
                transform: [{ translateY: sheetTranslateY }],
              },
            ]}
          >
            <View {...panResponder.panHandlers} style={styles.dragRegion}>
              <View accessibilityLabel="Drag down to close" style={styles.handle} />
              <View style={styles.header}>
                <View style={styles.headingText}>
                  <Text style={styles.title}>Curbside Service</Text>
                  <Text style={styles.subtitle}>Verify your service for the current location.</Text>
                </View>
                <Pressable
                  accessibilityLabel="Close curbside service settings"
                  accessibilityRole="button"
                  hitSlop={8}
                  onPress={() => close(false)}
                  style={({ pressed }) => [styles.closeButton, pressed && styles.pressed]}
                >
                  <Ionicons color="#242220" name="close" size={21} />
                </Pressable>
              </View>
            </View>

            <ScrollView
              contentContainerStyle={styles.content}
              keyboardShouldPersistTaps="handled"
              showsVerticalScrollIndicator={false}
            >
              {PICKUP_SCHEDULE_AND_NOTIFICATIONS_ENABLED ? <View style={styles.fieldGroup}>
                <Text style={styles.fieldLabel}>Do you have curbside recycling?</Text>
                <View style={styles.binaryOptions}>
                  {[
                    { label: 'Yes', value: true },
                    { label: 'No', value: false },
                  ].map((option) => {
                    const selected = draft.hasCurbsideRecycling === option.value;
                    return (
                      <Pressable
                        accessibilityRole="radio"
                        accessibilityState={{ checked: selected }}
                        key={option.label}
                        onPress={() => onChange({ ...draft, hasCurbsideRecycling: option.value })}
                        style={({ pressed }) => [
                          styles.binaryOption,
                          selected && styles.binaryOptionSelected,
                          pressed && styles.pressed,
                        ]}
                      >
                        <Text
                          style={[
                            styles.binaryOptionText,
                            selected && styles.binaryOptionTextSelected,
                          ]}
                        >
                          {option.label}
                        </Text>
                      </Pressable>
                    );
                  })}
                </View>
              </View> : null}

              <View style={styles.fieldGroup}>
                <Text style={styles.fieldLabel}>Provider name (required)</Text>
                <Text style={styles.locationCaption}>
                  {locationLabel ? `Verifying for ${locationLabel}` : 'Current location is unavailable.'}
                </Text>
                <View style={styles.providerRow}>
                  {providerLocked ? (
                    <Pressable
                      accessibilityLabel="Locked curbside provider field"
                      accessibilityRole="button"
                      onPress={() => setProviderCooldownVisible(true)}
                      style={styles.providerInputContainer}
                    >
                      {providerInputField}
                    </Pressable>
                  ) : (
                    <View style={styles.providerInputContainer}>{providerInputField}</View>
                  )}
                  <Animated.View
                    accessibilityElementsHidden={!providerVerifyVisible}
                    importantForAccessibility={
                      providerVerifyVisible ? 'auto' : 'no-hide-descendants'
                    }
                    pointerEvents={providerVerifyVisible ? 'auto' : 'none'}
                    style={[
                      styles.verifyButtonContainer,
                      {
                        marginLeft: providerVerifyMarginLeft,
                        opacity: providerVerifyProgress,
                        width: providerVerifyWidth,
                      },
                    ]}
                  >
                    <Pressable
                      accessibilityLabel={`${providerActionLabel} provider name`}
                      accessibilityRole="button"
                      disabled={providerStatus === 'loading' || saving || !locationLabel || !draft.providerName.trim()}
                      onPress={handleProviderAction}
                      style={({ pressed }) => [
                        styles.verifyButton,
                        (providerStatus === 'loading' || saving || !locationLabel) && styles.buttonDisabled,
                        pressed && styles.verifyButtonPressed,
                      ]}
                    >
                      {providerStatus === 'loading' || (saving && exactMatch) ? (
                        <ActivityIndicator color="#FFFFFF" size="small" />
                      ) : (
                        <Text style={styles.verifyButtonText}>{providerActionLabel}</Text>
                      )}
                    </Pressable>
                  </Animated.View>
                </View>
                {providerHelper ? (
                  <View accessibilityLiveRegion="polite" style={styles.providerHelperRow}>
                    <Ionicons
                      color={retryResult ? '#B44436' : providerLocked ? '#77716B' : '#2E7D4F'}
                      name={retryResult ? 'alert-circle-outline' : providerLocked ? 'lock-closed-outline' : 'checkmark-circle-outline'}
                      size={16}
                    />
                    <Text style={[
                      styles.providerHelperText,
                      retryResult && styles.providerHelperError,
                    ]}>
                      {providerHelper}
                    </Text>
                  </View>
                ) : null}
              </View>

              {providerError ? (
                <View accessibilityLiveRegion="polite" style={styles.errorCard}>
                  <Text style={styles.errorText}>{providerError}</Text>
                </View>
              ) : null}

              {PICKUP_SCHEDULE_AND_NOTIFICATIONS_ENABLED ? <>
                <PickupDayPicker
                  label="Trash pickup day"
                  onChange={(trashPickupDay) => onChange({ ...draft, trashPickupDay })}
                  value={draft.trashPickupDay}
                />
                <PickupDayPicker
                  label="Recycling pickup day"
                  onChange={(recyclingPickupDay) => onChange({ ...draft, recyclingPickupDay })}
                  value={draft.recyclingPickupDay}
                />
                <View style={styles.reminderRow}>
                <View style={styles.reminderText}>
                  <Text style={styles.fieldLabel}>Pickup reminders</Text>
                  <Text style={styles.reminderCaption}>
                    Visual preview only. No notifications are scheduled.
                  </Text>
                </View>
                <Switch
                  accessibilityLabel="Pickup reminders"
                  onValueChange={(remindersEnabled) => onChange({ ...draft, remindersEnabled })}
                  thumbColor="#FFFFFF"
                  trackColor={{ false: '#D7D2CB', true: '#11100F' }}
                  value={draft.remindersEnabled}
                />
                </View>
              </> : null}

              <Pressable
                accessibilityState={{ disabled: saveDisabled || saving }}
                accessibilityRole="button"
                disabled={saveDisabled || saving}
                onPress={() => close(true)}
                style={({ pressed }) => [
                  styles.saveButton,
                  (saveDisabled || saving) && styles.buttonDisabled,
                  pressed && styles.savePressed,
                ]}
              >
                {saving ? <ActivityIndicator color="#FFFFFF" /> : <Text style={styles.saveText}>Confirm & Save</Text>}
              </Pressable>
            </ScrollView>
          </Animated.View>
        </KeyboardAvoidingView>
        {providerConfirmationVisible && providerResult ? (
          <View
            accessibilityLabel="Provider confirmation popup"
            accessibilityViewIsModal
            style={[
              styles.popupOverlay,
              { paddingBottom: Math.max(insets.bottom, 16) + 16 },
            ]}
          >
            <Pressable
              accessibilityLabel="Close provider confirmation"
              onPress={handleRegionalEdit}
              style={StyleSheet.absoluteFill}
            />
            <View accessibilityRole="alert" style={styles.popupCard}>
              <View style={styles.popupIcon}>
                <Ionicons color="#15311A" name="help-circle-outline" size={25} />
              </View>
              <View style={styles.popupTextBlock}>
                <Text style={styles.popupEyebrow}>Provider confirmation</Text>
                <Text style={styles.popupTitle}>Is this your provider?</Text>
                <Text style={styles.popupMessage}>
                  We found {providerResult.name}, but couldn’t confirm service in your exact city. Is this the curbside provider you use?
                </Text>
                <Text style={styles.popupLockNote}>
                  After confirmation, this provider cannot be changed for 24 hours.
                </Text>
              </View>
              <View style={styles.popupActions}>
                <Pressable
                  accessibilityRole="button"
                  disabled={saving}
                  onPress={handleRegionalEdit}
                  style={({ pressed }) => [styles.popupSecondaryButton, pressed && styles.pressed]}
                >
                  <Text style={styles.popupSecondaryText}>No, edit</Text>
                </Pressable>
                <Pressable
                  accessibilityRole="button"
                  disabled={saving}
                  onPress={() => void handleRegionalConfirm()}
                  style={({ pressed }) => [
                    styles.popupPrimaryButton,
                    saving && styles.buttonDisabled,
                    pressed && styles.verifyButtonPressed,
                  ]}
                >
                  {saving ? <ActivityIndicator color="#FFFFFF" size="small" /> : (
                    <Text style={styles.popupPrimaryText}>Yes, confirm</Text>
                  )}
                </Pressable>
              </View>
            </View>
          </View>
        ) : null}
        {providerCooldownVisible && providerLocked ? (
          <View
            accessibilityLabel="Provider cooldown popup"
            accessibilityViewIsModal
            style={[
              styles.popupOverlay,
              { paddingBottom: Math.max(insets.bottom, 16) + 16 },
            ]}
          >
            <Pressable
              accessibilityLabel="Dismiss provider cooldown"
              onPress={() => setProviderCooldownVisible(false)}
              style={StyleSheet.absoluteFill}
            />
            <View accessibilityRole="alert" style={styles.popupCard}>
              <View style={styles.popupIcon}>
                <Ionicons color="#15311A" name="time-outline" size={25} />
              </View>
              <View style={styles.popupTextBlock}>
                <Text style={styles.popupEyebrow}>Provider locked</Text>
                <Text style={styles.popupTitle}>Changes are paused for 24 hours</Text>
                <Text style={styles.popupMessage}>
                  Your confirmed provider can be changed after {providerRetryText}.
                </Text>
              </View>
              <Pressable
                accessibilityRole="button"
                onPress={() => setProviderCooldownVisible(false)}
                style={({ pressed }) => [
                  styles.popupPrimaryButton,
                  styles.popupPrimaryButtonFull,
                  pressed && styles.verifyButtonPressed,
                ]}
              >
                <Text style={styles.popupPrimaryText}>Got it</Text>
              </Pressable>
            </View>
          </View>
        ) : null}
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  modalRoot: { flex: 1, justifyContent: 'flex-end' },
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: '#11110F' },
  keyboardAvoider: { flex: 1, justifyContent: 'flex-end' },
  sheet: {
    backgroundColor: '#F8F6F2',
    borderTopLeftRadius: 30,
    borderTopRightRadius: 30,
    maxHeight: '88%',
    overflow: 'hidden',
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: -8 },
    shadowOpacity: 0.14,
    shadowRadius: 24,
  },
  dragRegion: { paddingHorizontal: 18, paddingTop: 10 },
  handle: {
    alignSelf: 'center', backgroundColor: '#CBC6BF', borderRadius: 999,
    height: 5, marginBottom: 10, width: 44,
  },
  header: { alignItems: 'center', flexDirection: 'row', gap: 12, paddingBottom: 12 },
  headingText: { flex: 1, gap: 3 },
  title: { color: '#111111', fontSize: 22, letterSpacing: -0.5, ...PRIMARY_TEXT_STYLES.title },
  subtitle: { color: '#7B7670', fontSize: 12, ...SECONDARY_TEXT_STYLES.regular },
  closeButton: {
    alignItems: 'center', backgroundColor: '#EDE9E3', borderRadius: 999,
    height: 36, justifyContent: 'center', width: 36,
  },
  content: { gap: 18, paddingHorizontal: 18, paddingTop: 6 },
  fieldGroup: { gap: 9 },
  fieldLabel: { color: '#242220', fontSize: 13, ...PRIMARY_TEXT_STYLES.label },
  locationCaption: { color: '#817C76', fontSize: 11, ...SECONDARY_TEXT_STYLES.regular },
  binaryOptions: { flexDirection: 'row', gap: 8 },
  binaryOption: {
    alignItems: 'center', backgroundColor: '#FFFFFF', borderColor: '#DDD8D1',
    borderRadius: 14, borderWidth: 1, flex: 1, justifyContent: 'center', minHeight: 44,
  },
  binaryOptionSelected: { backgroundColor: '#11100F', borderColor: '#11100F' },
  binaryOptionText: { color: '#615D58', fontSize: 14, ...PRIMARY_TEXT_STYLES.button },
  binaryOptionTextSelected: { color: '#FFFFFF' },
  providerRow: { alignItems: 'stretch', flexDirection: 'row' },
  providerInputContainer: { flex: 1 },
  providerInputFrame: { position: 'relative' },
  input: {
    backgroundColor: '#FFFFFF', borderColor: '#DDD8D1', borderRadius: 14,
    borderWidth: 1, color: '#171717', fontSize: 14, minHeight: 48,
    paddingHorizontal: 14, ...SECONDARY_TEXT_STYLES.regular,
  },
  inputVerified: { borderColor: '#4F9A68', borderWidth: 2 },
  inputRejected: { borderColor: '#C75B4B', borderWidth: 2 },
  inputLocked: { backgroundColor: '#E8E5E0', borderColor: '#D1CCC5', color: '#625D57' },
  inputWithIcon: { paddingRight: 42 },
  providerStateIcon: { position: 'absolute', right: 13, top: 14 },
  providerHelperRow: { alignItems: 'flex-start', flexDirection: 'row', gap: 7 },
  providerHelperText: { color: '#356849', flex: 1, fontSize: 12, lineHeight: 17, ...SECONDARY_TEXT_STYLES.regular },
  providerHelperError: { color: '#993D31' },
  verifyButtonContainer: { borderRadius: 14, height: 48, overflow: 'hidden' },
  verifyButton: {
    alignItems: 'center', backgroundColor: '#11100F', borderRadius: 14,
    height: 48, justifyContent: 'center', width: PROVIDER_VERIFY_BUTTON_WIDTH,
  },
  verifyButtonPressed: { backgroundColor: '#2B2927' },
  verifyButtonText: { color: '#FFFFFF', fontSize: 14, ...PRIMARY_TEXT_STYLES.button },
  buttonDisabled: { opacity: 0.45 },
  errorCard: { backgroundColor: '#FFF0ED', borderColor: '#F0C8C0', borderRadius: 14, borderWidth: 1, padding: 12 },
  errorText: { color: '#8A3528', fontSize: 12, lineHeight: 17, ...SECONDARY_TEXT_STYLES.regular },
  dayOptions: { flexDirection: 'row', flexWrap: 'wrap', gap: 7 },
  dayOption: {
    alignItems: 'center', backgroundColor: '#FFFFFF', borderColor: '#DDD8D1',
    borderRadius: 12, borderWidth: 1, justifyContent: 'center', minHeight: 38, minWidth: 42,
  },
  dayOptionSelected: { backgroundColor: '#11100F', borderColor: '#11100F' },
  dayOptionText: { color: '#68635E', fontSize: 12, ...PRIMARY_TEXT_STYLES.button },
  dayOptionTextSelected: { color: '#FFFFFF' },
  reminderRow: {
    alignItems: 'center', backgroundColor: '#FFFFFF', borderColor: '#E3DED7',
    borderRadius: 16, borderWidth: 1, flexDirection: 'row', gap: 12,
    paddingHorizontal: 14, paddingVertical: 12,
  },
  reminderText: { flex: 1, gap: 3 },
  reminderCaption: { color: '#817C76', fontSize: 11, lineHeight: 15, ...SECONDARY_TEXT_STYLES.regular },
  saveButton: {
    alignItems: 'center', backgroundColor: '#11100F', borderRadius: 16,
    justifyContent: 'center', minHeight: 50,
  },
  savePressed: { backgroundColor: '#2B2927', transform: [{ scale: 0.99 }] },
  saveText: { color: '#FFFFFF', fontSize: 15, ...PRIMARY_TEXT_STYLES.button },
  popupOverlay: {
    ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(4, 8, 9, 0.42)',
    justifyContent: 'flex-end', paddingBottom: 20, paddingHorizontal: 16, zIndex: 50,
  },
  popupCard: {
    alignSelf: 'center', backgroundColor: '#FFFFFF', borderColor: '#E9E5DF',
    borderRadius: 24, borderWidth: 1, gap: 14, padding: 18,
    shadowColor: '#111827', shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.18, shadowRadius: 24, width: '100%',
  },
  popupIcon: {
    alignItems: 'center', backgroundColor: '#F4F1EC', borderRadius: 18,
    height: 48, justifyContent: 'center', width: 48,
  },
  popupTextBlock: { gap: 7 },
  popupEyebrow: {
    color: '#807B75', fontSize: 10, letterSpacing: 2.4,
    textTransform: 'uppercase', ...PRIMARY_TEXT_STYLES.label,
  },
  popupTitle: { color: '#111111', fontSize: 22, lineHeight: 27, ...PRIMARY_TEXT_STYLES.header },
  popupMessage: { color: '#66605B', fontSize: 15, lineHeight: 22, ...SECONDARY_TEXT_STYLES.regular },
  popupLockNote: { color: '#625D57', fontSize: 12, lineHeight: 17, ...SECONDARY_TEXT_STYLES.semiBold },
  popupActions: { flexDirection: 'row', gap: 9 },
  popupPrimaryButton: {
    alignItems: 'center', backgroundColor: '#111111', borderRadius: 999,
    flex: 1, justifyContent: 'center', minHeight: 48, paddingHorizontal: 16,
  },
  popupPrimaryButtonFull: { flex: 0, width: '100%' },
  popupPrimaryText: { color: '#FFFFFF', fontSize: 14, ...PRIMARY_TEXT_STYLES.button },
  popupSecondaryButton: {
    alignItems: 'center', backgroundColor: '#F1EEE9', borderRadius: 999,
    flex: 1, justifyContent: 'center', minHeight: 48, paddingHorizontal: 16,
  },
  popupSecondaryText: { color: '#302D2A', fontSize: 14, ...PRIMARY_TEXT_STYLES.button },
  pressed: { opacity: 0.8 },
});
