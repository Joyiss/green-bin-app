let lastScannedItem: string | null = null;

export function setLastScannedItem(item: string) {
  lastScannedItem = item;
}

export function getLastScannedItem() {
  return lastScannedItem;
}
