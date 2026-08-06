import { Ionicons } from '@expo/vector-icons';
import FontAwesome from '@expo/vector-icons/FontAwesome';
import * as Clipboard from 'expo-clipboard';
import { useMemo, useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  Share,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { sendScanFeedback } from '@/api/client';
import type {
  ScanFeedbackRating,
  ScanFeedbackReason,
} from '@/app/feedback-flow';
import type { ResultSheetPresentation } from '@/app/result-sheet-model';
import { FREDOKA_TEXT_STYLES, INTER_TEXT_STYLES } from '@/constants/typography';

const FEEDBACK_REASONS: { label: string; value: ScanFeedbackReason }[] = [
  { label: 'Item identified incorrectly', value: 'item_identified_incorrectly' },
  { label: 'Disposal guidance was incorrect', value: 'disposal_guidance_incorrect' },
  { label: 'Local information was inaccurate', value: 'local_information_inaccurate' },
  { label: 'Missing important information', value: 'missing_important_information' },
  { label: 'Other', value: 'other' },
];

type ResultFeedbackProps = {
  disabled?: boolean;
  onFeedbackSuccess?: () => void;
  presentation: ResultSheetPresentation;
  requestId: string | null;
};

function factLines(label: string, rows: { label: string; value: string }[]) {
  if (!rows.length) return [];
  return [label, ...rows.map((row) => `${row.label}: ${row.value}`)];
}

export function formatResultForSharing(presentation: ResultSheetPresentation) {
  const lines = [
    presentation.item,
    `Recommendation: ${presentation.action}`,
    presentation.destinationLabel ? `Where: ${presentation.destinationLabel}` : null,
    presentation.keyQualifier ? `Note: ${presentation.keyQualifier}` : null,
    presentation.bestOption ? `Guidance: ${presentation.bestOption}` : null,
    ...factLines('Status', presentation.status),
    ...(presentation.preparationSteps?.length
      ? [
          'Preparation',
          ...presentation.preparationSteps.map((step, index) =>
            `${index + 1}. ${[step.title, step.body].filter(Boolean).join(' ')}`,
          ),
        ]
      : presentation.noPreparationMessage
        ? ['Preparation', presentation.noPreparationMessage]
        : []),
    ...(presentation.steps.length
      ? [
          'Disposal steps',
          ...presentation.steps.map((step, index) =>
            `${index + 1}. ${[step.title, step.body].filter(Boolean).join(' ')}`,
          ),
        ]
      : []),
    ...(presentation.warnings.length
      ? ['Important notes', ...presentation.warnings.map((warning) => `• ${warning}`)]
      : []),
    ...(presentation.evidence
      ? [
          'Why Green Bin recommends this',
          presentation.evidence.summary ?? null,
          ...presentation.evidence.rows.map((row) => `${row.label}: ${row.value}`),
        ]
      : []),
    ...factLines('Details', presentation.facts),
    ...(presentation.references.length
      ? [
          'References',
          ...presentation.references.map((reference) =>
            `${reference.title} (${reference.role}): ${reference.url}`,
          ),
        ]
      : []),
  ].filter((line): line is string => Boolean(line));

  return lines.join('\n');
}

export function ResultFeedback({
  disabled,
  onFeedbackSuccess,
  presentation,
  requestId,
}: ResultFeedbackProps) {
  const [dialogVisible, setDialogVisible] = useState(false);
  const [selectedReasons, setSelectedReasons] = useState<ScanFeedbackReason[]>([]);
  const [details, setDetails] = useState('');
  const [submittingRating, setSubmittingRating] = useState<ScanFeedbackRating | null>(null);
  const [savedRating, setSavedRating] = useState<ScanFeedbackRating | null>(null);
  const [feedbackError, setFeedbackError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const shareText = useMemo(() => formatResultForSharing(presentation), [presentation]);
  const location = presentation.status.find(
    (row) => row.label.toLocaleLowerCase() === 'location',
  )?.value ?? null;
  const isSubmitting = submittingRating !== null;

  const submitFeedback = async (
    rating: ScanFeedbackRating,
    reasons: ScanFeedbackReason[],
    optionalDetails: string,
  ) => {
    if (disabled || isSubmitting) return;
    if (!requestId?.trim()) {
      setFeedbackError('This scan is missing its request ID. Your feedback was not submitted.');
      return;
    }

    setSubmittingRating(rating);
    setFeedbackError(null);
    try {
      await sendScanFeedback({
        request_id: requestId.trim(),
        item_name: presentation.item,
        location,
        guidance: { ...presentation },
        rating,
        reasons: rating === 'positive' ? [] : reasons,
        details: rating === 'positive' ? null : optionalDetails.trim() || null,
      });
      setSavedRating(rating);
      if (rating === 'negative') {
        setDialogVisible(false);
      }
      onFeedbackSuccess?.();
    } catch {
      setFeedbackError('Couldn’t submit feedback. Your selections are still here—please try again.');
    } finally {
      setSubmittingRating(null);
    }
  };

  const handleCopy = async () => {
    try {
      await Clipboard.setStringAsync(shareText);
      setActionMessage('Result copied');
    } catch {
      setActionMessage('Couldn’t copy the result');
    }
  };

  const handleShare = async () => {
    try {
      await Share.share({ message: shareText, title: `${presentation.item} disposal guidance` });
      setActionMessage(null);
    } catch {
      setActionMessage('Couldn’t open the share menu');
    }
  };

  const toggleReason = (reason: ScanFeedbackReason) => {
    setSelectedReasons((current) =>
      current.includes(reason)
        ? current.filter((value) => value !== reason)
        : [...current, reason],
    );
  };

  const actions: {
    icon: keyof typeof FontAwesome.glyphMap | keyof typeof Ionicons.glyphMap;
    iconSet: 'fontAwesome' | 'ionicons';
    label: string;
    onPress: () => void;
    rating?: ScanFeedbackRating;
  }[] = [
    {
      icon: 'copy-outline',
      iconSet: 'ionicons',
      label: 'Copy',
      onPress: () => void handleCopy(),
    },
    {
      icon: 'share-outline',
      iconSet: 'ionicons',
      label: 'Share',
      onPress: () => void handleShare(),
    },
    {
      icon: savedRating === 'positive' ? 'thumbs-up' : 'thumbs-o-up',
      iconSet: 'fontAwesome',
      label: 'Thumbs Up',
      onPress: () => void submitFeedback('positive', [], ''),
      rating: 'positive',
    },
    {
      icon: savedRating === 'negative' ? 'thumbs-down' : 'thumbs-o-down',
      iconSet: 'fontAwesome',
      label: 'Thumbs Down',
      onPress: () => {
        setFeedbackError(null);
        setDialogVisible(true);
      },
      rating: 'negative',
    },
  ];

  return (
    <>
      <View style={styles.container} testID="result-action-row">
        {actions.map((action) => {
          const selected = action.rating === savedRating;
          const loading = action.rating === submittingRating;
          return (
            <Pressable
              accessibilityLabel={action.label}
              accessibilityRole="button"
              accessibilityState={{ disabled: disabled || isSubmitting, selected }}
              disabled={disabled || isSubmitting}
              key={action.label}
              onPress={action.onPress}
              style={({ pressed }) => [
                styles.action,
                selected && styles.actionSelected,
                pressed && styles.actionPressed,
                (disabled || isSubmitting) && styles.actionDisabled,
              ]}>
              {loading ? (
                <ActivityIndicator color="#11100F" size="small" />
              ) : action.iconSet === 'fontAwesome' ? (
                <FontAwesome
                  color="#11100F"
                  name={action.icon as keyof typeof FontAwesome.glyphMap}
                  size={20}
                />
              ) : (
                <Ionicons
                  color="#11100F"
                  name={action.icon as keyof typeof Ionicons.glyphMap}
                  size={20}
                />
              )}
            </Pressable>
          );
        })}
      </View>
      {actionMessage ? <Text style={styles.inlineMessage}>{actionMessage}</Text> : null}
      {feedbackError && !dialogVisible ? (
        <Text accessibilityRole="alert" style={styles.errorText}>{feedbackError}</Text>
      ) : null}

      <Modal
        animationType="fade"
        onRequestClose={() => !isSubmitting && setDialogVisible(false)}
        statusBarTranslucent
        transparent
        visible={dialogVisible}>
        <KeyboardAvoidingView
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
          style={styles.modalRoot}>
          <Pressable
            accessibilityLabel="Close feedback dialog"
            disabled={isSubmitting}
            onPress={() => setDialogVisible(false)}
            style={styles.backdrop}
          />
          <View accessibilityViewIsModal style={styles.dialog}>
            <View style={styles.dialogHeader}>
              <Text style={styles.dialogTitle}>Share feedback</Text>
              <Pressable
                accessibilityLabel="Close feedback dialog"
                accessibilityRole="button"
                disabled={isSubmitting}
                hitSlop={8}
                onPress={() => setDialogVisible(false)}
                style={({ pressed }) => [styles.closeButton, pressed && styles.actionPressed]}>
                <Ionicons color="#242220" name="close" size={21} />
              </Pressable>
            </View>

            <Text style={styles.dialogPrompt}>What could be improved? Select all that apply.</Text>
            <View style={styles.chips}>
              {FEEDBACK_REASONS.map((reason) => {
                const selected = selectedReasons.includes(reason.value);
                return (
                  <Pressable
                    accessibilityRole="button"
                    accessibilityState={{ selected }}
                    disabled={isSubmitting}
                    key={reason.value}
                    onPress={() => toggleReason(reason.value)}
                    style={({ pressed }) => [
                      styles.chip,
                      selected && styles.chipSelected,
                      pressed && styles.actionPressed,
                    ]}>
                    <Text style={[styles.chipText, selected && styles.chipTextSelected]}>
                      {reason.label}
                    </Text>
                  </Pressable>
                );
              })}
            </View>

            <TextInput
              accessibilityLabel="Feedback details"
              editable={!isSubmitting}
              maxLength={2000}
              multiline
              onChangeText={setDetails}
              placeholder="Share details (optional)"
              placeholderTextColor="#96918B"
              style={styles.detailsInput}
              textAlignVertical="top"
              value={details}
            />

            {feedbackError ? (
              <Text accessibilityRole="alert" style={styles.dialogError}>{feedbackError}</Text>
            ) : null}

            <Pressable
              accessibilityRole="button"
              disabled={isSubmitting}
              onPress={() => void submitFeedback('negative', selectedReasons, details)}
              style={({ pressed }) => [
                styles.submitButton,
                pressed && styles.submitPressed,
                isSubmitting && styles.actionDisabled,
              ]}>
              {submittingRating === 'negative' ? (
                <ActivityIndicator color="#FFFFFF" size="small" />
              ) : (
                <Text style={styles.submitText}>Submit</Text>
              )}
            </Pressable>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  action: {
    alignItems: 'center',
    borderRadius: 999,
    height: 36,
    justifyContent: 'center',
    width: 36,
  },
  actionDisabled: { opacity: 0.5 },
  actionPressed: { opacity: 0.68 },
  actionSelected: { backgroundColor: '#EEEAE4' },
  backdrop: { ...StyleSheet.absoluteFillObject },
  chip: {
    borderColor: '#DED9D2',
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: 12,
    paddingVertical: 9,
  },
  chipSelected: { backgroundColor: '#11100F', borderColor: '#11100F' },
  chipText: {
    color: '#34312E',
    fontSize: 12,
    lineHeight: 16,
    ...INTER_TEXT_STYLES.regular,
    fontWeight: '400',
  },
  chipTextSelected: { color: '#FFFFFF' },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  closeButton: { alignItems: 'center', height: 32, justifyContent: 'center', width: 32 },
  container: {
    alignSelf: 'flex-start',
    flexDirection: 'row',
    gap: 2,
  },
  detailsInput: {
    borderColor: '#DED9D2',
    borderRadius: 14,
    borderWidth: 1,
    color: '#302D2A',
    fontSize: 13,
    height: 92,
    lineHeight: 19,
    padding: 12,
    ...INTER_TEXT_STYLES.regular,
    fontWeight: '400',
  },
  dialog: {
    backgroundColor: '#FFFEFC',
    borderColor: '#DED9D2',
    borderRadius: 20,
    borderWidth: 1,
    gap: 14,
    maxWidth: 520,
    padding: 18,
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.2,
    shadowRadius: 24,
    width: '92%',
    elevation: 12,
  },
  dialogError: {
    color: '#A0443B',
    fontSize: 12,
    lineHeight: 17,
    ...INTER_TEXT_STYLES.regular,
    fontWeight: '400',
  },
  dialogHeader: { alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between' },
  dialogPrompt: {
    color: '#716B65',
    fontSize: 12,
    lineHeight: 17,
    ...INTER_TEXT_STYLES.regular,
    fontWeight: '400',
  },
  dialogTitle: {
    color: '#242220',
    fontSize: 19,
    lineHeight: 24,
    ...FREDOKA_TEXT_STYLES.medium,
    fontWeight: '500',
  },
  errorText: {
    color: '#A0443B',
    fontSize: 12,
    lineHeight: 17,
    marginTop: 7,
    ...INTER_TEXT_STYLES.regular,
    fontWeight: '400',
  },
  inlineMessage: {
    color: '#2F6B52',
    fontSize: 11,
    lineHeight: 15,
    marginTop: 6,
    textAlign: 'center',
    ...INTER_TEXT_STYLES.medium,
    fontWeight: '500',
  },
  modalRoot: {
    alignItems: 'center',
    backgroundColor: 'rgba(18, 17, 16, 0.38)',
    flex: 1,
    justifyContent: 'center',
    paddingHorizontal: 18,
    paddingVertical: 32,
  },
  submitButton: {
    alignItems: 'center',
    alignSelf: 'flex-end',
    backgroundColor: '#11100F',
    borderRadius: 999,
    height: 44,
    justifyContent: 'center',
    minWidth: 104,
    paddingHorizontal: 20,
  },
  submitPressed: { backgroundColor: '#33302D' },
  submitText: {
    color: '#FFFFFF',
    fontSize: 14,
    lineHeight: 18,
    ...INTER_TEXT_STYLES.semiBold,
    fontWeight: '600',
  },
});
