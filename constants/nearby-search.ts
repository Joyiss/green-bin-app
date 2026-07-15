export const NEARBY_CATEGORY_FALLBACKS = {
  Textiles: { searchTerm: 'textiles', label: 'textile search' },
  Electronics: { searchTerm: 'electronics', label: 'electronics search' },
  Battery: { searchTerm: 'batteries', label: 'battery search' },
  Appliances: { searchTerm: 'appliances', label: 'appliance search' },
  Metal: { searchTerm: 'scrap metal', label: 'scrap metal search' },
  Glass: { searchTerm: 'glass', label: 'glass search' },
  Cardboard: { searchTerm: 'cardboard', label: 'cardboard search' },
  Paper: { searchTerm: 'paper', label: 'paper search' },
} as const;

export type ApprovedNearbyCategory = keyof typeof NEARBY_CATEGORY_FALLBACKS;

export type NearbyFallback = (typeof NEARBY_CATEGORY_FALLBACKS)[ApprovedNearbyCategory];

const DONATION_DENYLIST = [
  'unknown',
  'battery',
  'batteries',
  'hazardous',
  'food waste',
  'food scrap',
  'food packaging',
  'organic waste',
  'dirty container',
  'soiled container',
  'food-soiled',
  'food soiled',
  'broken glass',
  'wrapper',
  'scraps',
];

function normalizeValue(value: string | null | undefined) {
  return value?.trim().toLowerCase() ?? '';
}

export function getNearbyFallback(
  disposalCategory: string | null | undefined,
): NearbyFallback | null {
  const normalizedCategory = disposalCategory?.trim();
  if (!normalizedCategory || !(normalizedCategory in NEARBY_CATEGORY_FALLBACKS)) {
    return null;
  }

  return NEARBY_CATEGORY_FALLBACKS[normalizedCategory as ApprovedNearbyCategory];
}

type DonationSupportInput = {
  item: string;
  disposalCategory?: string | null;
  disposalAction?: string | null;
  summary?: string | null;
  steps?: string[] | null;
};

export function supportsNearbyDonationReuse({
  item,
  disposalCategory,
  disposalAction,
  summary,
  steps,
}: DonationSupportInput) {
  const category = normalizeValue(disposalCategory);
  const guidanceText = [disposalAction, summary, ...(steps ?? [])]
    .filter((value): value is string => typeof value === 'string')
    .join(' ')
    .toLowerCase();
  const safetyText = `${normalizeValue(item)} ${category} ${guidanceText}`;

  if (DONATION_DENYLIST.some((term) => safetyText.includes(term))) {
    return false;
  }

  if (category === 'textiles') {
    return true;
  }

  const explicitlySupportsDonation =
    guidanceText.includes('donate') ||
    guidanceText.includes('donation') ||
    guidanceText.includes('reuse');
  if (!explicitlySupportsDonation) {
    return false;
  }

  if (category === 'electronics') {
    return guidanceText.includes('working') || guidanceText.includes('usable');
  }

  return true;
}
