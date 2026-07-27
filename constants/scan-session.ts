let lastScannedItem: string | null = null;

export type NearbyScanContext = {
  scanSessionId: string;
  item: string;
  normalizedItem: string | null;
  disposalCategory: string | null;
  broadCategory: string | null;
  materialCategory: string | null;
  disposalAction: string | null;
  requiresLocationCheck: boolean;
  supportsDonationReuse: boolean;
  jurisdictionId: string | null;
  localRuleId: string | null;
};

let lastNearbyScanContext: NearbyScanContext | null = null;

export function setLastScannedItem(item: string) {
  lastScannedItem = item;
}

export function setLastNearbyScanContext(context: NearbyScanContext) {
  lastScannedItem = context.item;
  lastNearbyScanContext = context;
}

export function clearLastNearbyScanContext() {
  lastScannedItem = null;
  lastNearbyScanContext = null;
}

export function getLastScannedItem() {
  return lastScannedItem;
}

export function getLastNearbyScanContext() {
  return lastNearbyScanContext;
}
