import AsyncStorage from '@react-native-async-storage/async-storage';

import {
  flushQueuedFeedbackEntries,
  mergeQueuedFeedback,
  pruneQueuedFeedback,
  sanitizeFeedbackUpdate,
  type FeedbackUpdate,
  type QueuedFeedback,
} from '@/app/feedback-flow';

const FEEDBACK_QUEUE_STORAGE_KEY = 'green-bin:closed-test-feedback-queue';

function normalizeQueuedFeedback(value: unknown): QueuedFeedback | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null;
  }
  const entry = value as Partial<QueuedFeedback>;
  const valid = (
    typeof entry.requestId === 'string' &&
    !!entry.requestId.trim() &&
    typeof entry.queuedAt === 'number' &&
    !!entry.update &&
    typeof entry.update === 'object' &&
    !Array.isArray(entry.update)
  );
  if (!valid) {
    return null;
  }
  const update = sanitizeFeedbackUpdate(entry.update);
  return Object.keys(update).length
    ? {
        requestId: entry.requestId!.trim(),
        queuedAt: entry.queuedAt!,
        update,
      }
    : null;
}

async function readQueue() {
  try {
    const stored = await AsyncStorage.getItem(FEEDBACK_QUEUE_STORAGE_KEY);
    const parsed = stored ? (JSON.parse(stored) as unknown) : [];
    return Array.isArray(parsed)
      ? pruneQueuedFeedback(
          parsed
            .map(normalizeQueuedFeedback)
            .filter((entry): entry is QueuedFeedback => entry !== null),
        )
      : [];
  } catch {
    return [];
  }
}

async function writeQueue(entries: QueuedFeedback[]) {
  await AsyncStorage.setItem(
    FEEDBACK_QUEUE_STORAGE_KEY,
    JSON.stringify(pruneQueuedFeedback(entries)),
  );
}

export async function enqueueFeedback(
  requestId: string,
  update: FeedbackUpdate,
) {
  const now = Date.now();
  const queue = await readQueue();
  const sanitizedUpdate = sanitizeFeedbackUpdate(update);
  if (!Object.keys(sanitizedUpdate).length) {
    return;
  }
  try {
    await writeQueue(
      mergeQueuedFeedback(
        queue,
        { requestId, update: sanitizedUpdate, queuedAt: now },
        now,
      ),
    );
  } catch {
    // Feedback is optional and must never interrupt the scan flow.
  }
}

export async function flushFeedbackQueue(
  send: (requestId: string, update: FeedbackUpdate) => Promise<void>,
) {
  const queue = await readQueue();
  const remaining = await flushQueuedFeedbackEntries(queue, send);
  try {
    await writeQueue(remaining);
  } catch {
    // A storage failure should not surface as a scan or correction failure.
  }
}
