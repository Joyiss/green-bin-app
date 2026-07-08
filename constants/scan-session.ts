let lastScannedItem: string | null = null;

export type NearbyScanContext = {
  item: string;
  normalizedItem: string | null;
  disposalCategory: string | null;
  materialCategory: string | null;
  disposalAction: string | null;
  requiresLocationCheck: boolean;
  supportsDonationReuse: boolean;
};

let lastNearbyScanContext: NearbyScanContext | null = null;

export function setLastScannedItem(item: string) {
  lastScannedItem = item;
}

export function setLastNearbyScanContext(context: NearbyScanContext) {
  lastScannedItem = context.item;
  lastNearbyScanContext = context;
}

export function getLastScannedItem() {
  return lastScannedItem;
}

export function getLastNearbyScanContext() {
  return lastNearbyScanContext;
}
