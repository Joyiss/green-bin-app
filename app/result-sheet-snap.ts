export const RESULT_SHEET_EXPANDED = 0 as const;
export const RESULT_SHEET_COLLAPSED = 1 as const;
export const RESULT_SHEET_HIDDEN = 2 as const;

export type ResultSheetSnapState =
  | typeof RESULT_SHEET_EXPANDED
  | typeof RESULT_SHEET_COLLAPSED
  | typeof RESULT_SHEET_HIDDEN;

type ResolveResultSheetSnapTargetArgs = {
  collapsedOffset: number;
  hiddenOffset: number;
  state: ResultSheetSnapState;
  translationY: number;
  velocityY: number;
};

const VELOCITY_PROJECTION_SECONDS = 0.18;

export function resolveResultSheetSnapTarget({
  collapsedOffset,
  hiddenOffset,
  state,
  translationY,
  velocityY,
}: ResolveResultSheetSnapTargetArgs): ResultSheetSnapState {
  'worklet';

  if (state === RESULT_SHEET_HIDDEN) {
    return RESULT_SHEET_HIDDEN;
  }

  const projectedDelta = translationY + velocityY * VELOCITY_PROJECTION_SECONDS;

  // A result that starts expanded always stops at collapsed first, even after a long fling.
  if (state === RESULT_SHEET_EXPANDED) {
    return projectedDelta >= collapsedOffset / 2
      ? RESULT_SHEET_COLLAPSED
      : RESULT_SHEET_EXPANDED;
  }

  const projectedOffset = Math.min(
    Math.max(collapsedOffset + projectedDelta, 0),
    hiddenOffset,
  );
  const expandedDistance = projectedOffset;
  const collapsedDistance = Math.abs(projectedOffset - collapsedOffset);
  const hiddenDistance = Math.abs(projectedOffset - hiddenOffset);

  if (expandedDistance < collapsedDistance && expandedDistance <= hiddenDistance) {
    return RESULT_SHEET_EXPANDED;
  }
  if (hiddenDistance < collapsedDistance && hiddenDistance < expandedDistance) {
    return RESULT_SHEET_HIDDEN;
  }
  return RESULT_SHEET_COLLAPSED;
}
