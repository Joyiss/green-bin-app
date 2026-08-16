import { Ionicons } from '@expo/vector-icons';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AccessibilityInfo,
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
  onSave,
  visible,
}: {
  draft: CurbsideDraft;
  onChange: (draft: CurbsideDraft) => void;
  onDismiss: () => void;
  onSave: (draft: CurbsideDraft) => void;
  visible: boolean;
}) {
  const insets = useSafeAreaInsets();
  const progress = useRef(new Animated.Value(0)).current;
  const closingRef = useRef(false);
  const [reduceMotion, setReduceMotion] = useState(false);
  const providerVerifyProgress = useRef(new Animated.Value(0)).current;
  const providerVerifyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [providerVerifyVisible, setProviderVerifyVisible] = useState(false);

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
    }
  }, [resetProviderVerification, visible]);

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
        if (save) {
          onSave(cloneCurbsideDraft(draft));
        } else {
          onDismiss();
        }
      };

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
                  <Text style={styles.subtitle}>Temporary setup for this app session.</Text>
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
              <View style={styles.fieldGroup}>
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
              </View>

              <View style={styles.fieldGroup}>
                <Text style={styles.fieldLabel}>Provider name (optional)</Text>
                <View style={styles.providerRow}>
                  <View style={styles.providerInputContainer}>
                    <TextInput
                      accessibilityLabel="Curbside recycling provider name"
                      autoCapitalize="words"
                      onChangeText={handleProviderNameChange}
                      placeholder="Example: City sanitation"
                      placeholderTextColor="#9A948C"
                      style={styles.input}
                      value={draft.providerName}
                    />
                  </View>
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
                      accessibilityLabel="Verify provider name"
                      accessibilityRole="button"
                      onPress={() => undefined}
                      style={({ pressed }) => [
                        styles.verifyButton,
                        pressed && styles.verifyButtonPressed,
                      ]}
                    >
                      <Text style={styles.verifyButtonText}>Verify</Text>
                    </Pressable>
                  </Animated.View>
                </View>
              </View>

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

              <Pressable
                accessibilityRole="button"
                onPress={() => close(true)}
                style={({ pressed }) => [styles.saveButton, pressed && styles.savePressed]}
              >
                <Text style={styles.saveText}>Save</Text>
              </Pressable>
            </ScrollView>
          </Animated.View>
        </KeyboardAvoidingView>
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
  input: {
    backgroundColor: '#FFFFFF', borderColor: '#DDD8D1', borderRadius: 14,
    borderWidth: 1, color: '#171717', fontSize: 14, minHeight: 48,
    paddingHorizontal: 14, ...SECONDARY_TEXT_STYLES.regular,
  },
  verifyButtonContainer: { borderRadius: 14, height: 48, overflow: 'hidden' },
  verifyButton: {
    alignItems: 'center', backgroundColor: '#11100F', borderRadius: 14,
    height: 48, justifyContent: 'center', width: PROVIDER_VERIFY_BUTTON_WIDTH,
  },
  verifyButtonPressed: { backgroundColor: '#2B2927' },
  verifyButtonText: { color: '#FFFFFF', fontSize: 14, ...PRIMARY_TEXT_STYLES.button },
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
  pressed: { opacity: 0.8 },
});
