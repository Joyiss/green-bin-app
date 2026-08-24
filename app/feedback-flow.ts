export const SCAN_FEEDBACK_REASON_VALUES = [
  'item_identified_incorrectly',
  'disposal_guidance_incorrect',
  'local_information_inaccurate',
  'missing_important_information',
  'other',
] as const;

export type ScanFeedbackReason = (typeof SCAN_FEEDBACK_REASON_VALUES)[number];
export type ScanFeedbackRating = 'positive' | 'negative';

export type ScanFeedbackSubmission = {
  request_id: string;
  item_name: string;
  location: string | null;
  guidance: Record<string, unknown>;
  rating: ScanFeedbackRating;
  reasons: ScanFeedbackReason[];
  details: string | null;
};

export function shouldShowGuidanceFeedback({
  disposalAction,
  guidanceSource,
  clarificationRequired,
}: {
  disposalAction: string | null;
  guidanceSource?: string | null;
  clarificationRequired: boolean;
}) {
  if (clarificationRequired || !disposalAction) {
    return false;
  }
  return ![
    'recognition_clarification_required',
    'safe_fallback',
  ].includes((guidanceSource ?? '').trim().toLowerCase());
}
