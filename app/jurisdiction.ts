export const FORSYTH_COUNTY_JURISDICTION_ID = 'forsyth_county_ga';

export type ReverseGeocodedAddress = {
  city?: string | null;
  country?: string | null;
  isoCountryCode?: string | null;
  region?: string | null;
  subregion?: string | null;
  district?: string | null;
};

export type CoarseDisposalLocation = {
  city?: string;
  county?: string;
  state?: string;
  country?: string;
  wasteProvider?: string;
};

function normalize(value: string | null | undefined) {
  return (value ?? '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

export function detectJurisdiction(
  addresses: ReverseGeocodedAddress[],
): string | null {
  for (const address of addresses) {
    const country = normalize(address.isoCountryCode || address.country);
    const state = normalize(address.region);
    const countyValues = [normalize(address.subregion), normalize(address.district)];
    const isUnitedStates =
      country === 'us' || country === 'usa' || country === 'united states';
    const isGeorgia = state === 'ga' || state === 'georgia';
    const isForsythCounty = countyValues.some(
      (value) => value === 'forsyth' || value === 'forsyth county',
    );

    if (isUnitedStates && isGeorgia && isForsythCounty) {
      return FORSYTH_COUNTY_JURISDICTION_ID;
    }
  }

  return null;
}

function safeCoarseText(value: string | null | undefined) {
  const text = (value ?? '').replace(/\s+/g, ' ').trim();
  if (!text || text.includes('@') || text.includes('://')) {
    return null;
  }
  return text.slice(0, 120);
}

export function extractCoarseDisposalLocation(
  addresses: ReverseGeocodedAddress[],
): CoarseDisposalLocation | null {
  for (const address of addresses) {
    const city = safeCoarseText(address.city);
    const county =
      safeCoarseText(address.subregion) ?? safeCoarseText(address.district);
    const state = safeCoarseText(address.region);
    const country =
      safeCoarseText(address.country) ?? safeCoarseText(address.isoCountryCode);
    const location = {
      ...(city ? { city } : {}),
      ...(county ? { county } : {}),
      ...(state ? { state } : {}),
      ...(country ? { country } : {}),
    };
    if (Object.keys(location).length) {
      return location;
    }
  }
  return null;
}

export async function resolveJurisdictionForPrediction(
  getLocationContext: () => Promise<{ jurisdictionId: string | null }>,
) {
  try {
    const context = await getLocationContext();
    return context.jurisdictionId;
  } catch {
    return null;
  }
}

export function appendJurisdictionId(
  formData: { append(name: string, value: string): void },
  jurisdictionId: string | null,
) {
  if (jurisdictionId) {
    formData.append('jurisdiction_id', jurisdictionId);
  }
}

export function appendCoarseDisposalLocation(
  formData: { append(name: string, value: string): void },
  location: CoarseDisposalLocation | null,
) {
  if (!location) {
    return;
  }
  const fields: [string, string | undefined][] = [
    ['city', location.city],
    ['county', location.county],
    ['state', location.state],
    ['country', location.country],
    ['waste_provider', location.wasteProvider],
  ];
  for (const [name, value] of fields) {
    const safeValue = safeCoarseText(value);
    if (safeValue) {
      formData.append(name, safeValue);
    }
  }
}
