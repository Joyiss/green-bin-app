import { Ionicons } from '@expo/vector-icons';
import { Pressable, StyleSheet, Text, View } from 'react-native';

type FeedbackAnswer = boolean | null;

type ResultFeedbackProps = {
  disabled?: boolean;
  guidanceAnswer: FeedbackAnswer;
  itemAnswer: FeedbackAnswer;
  onGuidanceAnswer: (answer: boolean) => void;
  onItemAnswer: (answer: boolean) => void;
  showGuidanceQuestion: boolean;
};

function AnswerButtons({
  answer,
  disabled,
  label,
  onAnswer,
}: {
  answer: FeedbackAnswer;
  disabled?: boolean;
  label: string;
  onAnswer: (answer: boolean) => void;
}) {
  return (
    <View style={styles.actions}>
      {[true, false].map((value) => {
        const selected = answer === value;
        const icon = value ? 'thumbs-up' : 'thumbs-down';
        return (
          <Pressable
            accessibilityLabel={`${label}: ${value ? 'yes' : 'no'}`}
            accessibilityRole="button"
            accessibilityState={{ disabled, selected }}
            disabled={disabled}
            key={String(value)}
            onPress={() => onAnswer(value)}
            style={({ pressed }) => [
              styles.iconButton,
              selected && styles.iconButtonSelected,
              pressed && !disabled && styles.iconButtonPressed,
              disabled && styles.iconButtonDisabled,
            ]}>
            <Ionicons
              color={selected ? '#FFFFFF' : '#333333'}
              name={selected ? icon : `${icon}-outline`}
              size={18}
            />
          </Pressable>
        );
      })}
    </View>
  );
}

export function ResultFeedback({
  disabled,
  guidanceAnswer,
  itemAnswer,
  onGuidanceAnswer,
  onItemAnswer,
  showGuidanceQuestion,
}: ResultFeedbackProps) {
  return (
    <View style={styles.container}>
      <View style={styles.row}>
        <Text style={styles.question}>Was the item identified correctly?</Text>
        <AnswerButtons
          answer={itemAnswer}
          disabled={disabled}
          label="Item identified correctly"
          onAnswer={onItemAnswer}
        />
      </View>
      {showGuidanceQuestion ? (
        <View style={styles.row}>
          <Text style={styles.question}>Was this disposal guidance helpful?</Text>
          <AnswerButtons
            answer={guidanceAnswer}
            disabled={disabled}
            label="Disposal guidance helpful"
            onAnswer={onGuidanceAnswer}
          />
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  actions: {
    flexDirection: 'row',
    gap: 8,
  },
  container: {
    borderTopColor: '#E8E4DE',
    borderTopWidth: 1,
    gap: 10,
    marginTop: 4,
    paddingTop: 14,
  },
  iconButton: {
    alignItems: 'center',
    backgroundColor: '#F4F1EC',
    borderColor: '#E3DED6',
    borderRadius: 18,
    borderWidth: 1,
    height: 44,
    justifyContent: 'center',
    width: 44,
  },
  iconButtonDisabled: {
    opacity: 0.55,
  },
  iconButtonPressed: {
    opacity: 0.72,
  },
  iconButtonSelected: {
    backgroundColor: '#050505',
    borderColor: '#050505',
  },
  question: {
    color: '#333333',
    flex: 1,
    fontSize: 13,
    fontWeight: '700',
    lineHeight: 18,
  },
  row: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 12,
    justifyContent: 'space-between',
  },
});
