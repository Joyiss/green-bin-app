export const FORSYTH_COUNTY_JURISDICTION_ID = 'forsyth_county_ga';

export type ReverseGeocodedAddress = {
  country?: string | null;
  isoCountryCode?: string | null;
  region?: string | null;
  subregion?: string | null;
  district?: string | null;
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
