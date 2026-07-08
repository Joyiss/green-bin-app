import { Ionicons } from '@expo/vector-icons';
import * as Location from 'expo-location';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Linking,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';

import { BOTTOM_NAV_BAR_HEIGHT } from '@/components/bottom-nav-bar';
import { LocationCard, type LocationCardProps } from '@/components/location-card';
import { API_BASE_URL } from '@/constants/api';
import { getNearbyFallback, supportsNearbyDonationReuse } from '@/constants/nearby-search';
import { getLastNearbyScanContext, getLastScannedItem } from '@/constants/scan-session';

type NearbyLocation = LocationCardProps & {
  id: string;
  directionsUrl?: string | null;
};

type NearbyLocationsResponse = {
  item: string;
  material_id: number | null;
  locations: NearbyLocation[];
};

type Coordinates = {
  latitude: number;
  longitude: number;
};

type EmptySearchScope = 'exact' | 'broader';

type NearbyRouteParams = {
  item?: string | string[];
  normalizedItem?: string | string[];
  disposalCategory?: string | string[];
  materialCategory?: string | string[];
  disposalAction?: string | string[];
  requiresLocationCheck?: string | string[];
  supportsDonationReuse?: string | string[];
};

function getRouteValue(value: string | string[] | undefined) {
  if (typeof value === 'string') {
    return value;
  }

  if (Array.isArray(value)) {
    return value[0];
  }

  return null;
}

function normalizeSearchText(value: string) {
  return value.trim().toLowerCase();
}

function getLocationSearchText(location: NearbyLocation) {
  return [
    location.name,
    location.address,
    location.type,
    location.status,
    location.distance,
  ]
    .join(' ')
    .toLowerCase();
}

async function fetchNearbyLocations(item: string, coordinates: Coordinates) {
  const query = new URLSearchParams({
    item,
    lat: String(coordinates.latitude),
    lon: String(coordinates.longitude),
  });
  const response = await fetch(`${API_BASE_URL}/nearby_locations?${query.toString()}`);

  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`);
  }

  return (await response.json()) as NearbyLocationsResponse;
}

function routeBoolean(value: string | null, fallback: boolean) {
  if (value === 'true') {
    return true;
  }
  if (value === 'false') {
    return false;
  }
  return fallback;
}

export default function NearbyScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const routeParams = useLocalSearchParams<NearbyRouteParams>();
  const sessionContext = getLastNearbyScanContext();
  const routeItem = getRouteValue(routeParams.item);
  const selectedItem = routeItem ?? sessionContext?.item ?? getLastScannedItem();
  const sessionMatchesItem =
    !!selectedItem &&
    !!sessionContext?.item &&
    normalizeSearchText(selectedItem) === normalizeSearchText(sessionContext.item);
  const normalizedItem =
    getRouteValue(routeParams.normalizedItem) ??
    (sessionMatchesItem ? sessionContext?.normalizedItem : null);
  const displayItem = normalizedItem ?? selectedItem;
  const disposalCategory =
    getRouteValue(routeParams.disposalCategory) ??
    (sessionMatchesItem ? sessionContext?.disposalCategory : null);
  const disposalAction =
    getRouteValue(routeParams.disposalAction) ??
    (sessionMatchesItem ? sessionContext?.disposalAction : null);
  const requiresLocationCheck = routeBoolean(
    getRouteValue(routeParams.requiresLocationCheck),
    sessionMatchesItem ? (sessionContext?.requiresLocationCheck ?? false) : false,
  );
  const supportsDonationReuse = routeBoolean(
    getRouteValue(routeParams.supportsDonationReuse),
    sessionMatchesItem
      ? (sessionContext?.supportsDonationReuse ?? false)
      : supportsNearbyDonationReuse({
          item: displayItem ?? '',
          disposalCategory,
          disposalAction,
        }),
  );
  const broaderFallback = getNearbyFallback(disposalCategory);

  const [locations, setLocations] = useState<NearbyLocation[]>([]);
  const [coordinates, setCoordinates] = useState<Coordinates | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [emptySearchScope, setEmptySearchScope] = useState<EmptySearchScope | null>(null);
  const [broaderSearchTerm, setBroaderSearchTerm] = useState<string | null>(null);

  useEffect(() => {
    let isActive = true;

    async function loadLocations() {
      if (!selectedItem) {
        setLocations([]);
        setEmptySearchScope(null);
        setErrorMessage('Scan an item to load real drop-off locations.');
        return;
      }

      setIsLoading(true);
      setErrorMessage(null);
      setEmptySearchScope(null);
      setBroaderSearchTerm(null);

      try {
        const permission = await Location.requestForegroundPermissionsAsync();
        if (permission.status !== 'granted') {
          throw new Error('Location permission denied');
        }

        const currentPosition = await Location.getCurrentPositionAsync({
          accuracy: Location.Accuracy.Balanced,
        });
        const lastKnownPosition = await Location.getLastKnownPositionAsync();
        const position = currentPosition ?? lastKnownPosition;

        if (!position) {
          throw new Error('Location unavailable');
        }

        const nextCoordinates = {
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
        };
        const data = await fetchNearbyLocations(selectedItem, nextCoordinates);
        if (!isActive) {
          return;
        }

        const nextLocations = data.locations ?? [];
        setCoordinates(nextCoordinates);
        setLocations(nextLocations);
        setEmptySearchScope(nextLocations.length ? null : 'exact');
      } catch (error) {
        if (!isActive) {
          return;
        }

        setLocations([]);
        setEmptySearchScope(null);
        if (error instanceof Error && error.message === 'Location permission denied') {
          setErrorMessage('Location access is required to load nearby recycling sites.');
        } else if (error instanceof Error && error.message === 'Location unavailable') {
          setErrorMessage('Your location could not be determined right now.');
        } else {
          setErrorMessage('Could not load nearby locations right now.');
        }
      } finally {
        if (isActive) {
          setIsLoading(false);
        }
      }
    }

    loadLocations();

    return () => {
      isActive = false;
    };
  }, [selectedItem]);

  async function tryBroaderSearch() {
    if (!broaderFallback || !coordinates) {
      return;
    }

    setIsLoading(true);
    setErrorMessage(null);
    setEmptySearchScope(null);
    setSearchQuery('');
    setBroaderSearchTerm(broaderFallback.searchTerm);

    try {
      const data = await fetchNearbyLocations(broaderFallback.searchTerm, coordinates);
      const nextLocations = data.locations ?? [];
      setLocations(nextLocations);
      setBroaderSearchTerm(broaderFallback.searchTerm);
      setEmptySearchScope(nextLocations.length ? null : 'broader');
    } catch {
      setLocations([]);
      setBroaderSearchTerm(null);
      setErrorMessage('Could not load broader nearby results right now.');
    } finally {
      setIsLoading(false);
    }
  }

  const subtitle = displayItem
    ? `Find approved drop-off and recycling sites near you for ${displayItem.toLowerCase()}.`
    : 'Find approved drop-off and recycling sites near you.';
  const normalizedSearchQuery = normalizeSearchText(searchQuery);
  const filteredLocations = normalizedSearchQuery
    ? locations.filter((location) =>
        getLocationSearchText(location).includes(normalizedSearchQuery)
      )
    : locations;
  const showEmptySearchState =
    !isLoading && !errorMessage && !!normalizedSearchQuery && filteredLocations.length === 0;
  const showBroaderNotice =
    !isLoading && !errorMessage && !!broaderSearchTerm && locations.length > 0;
  const canTryBroaderSearch = emptySearchScope === 'exact' && !!broaderFallback;
  const noResultsExplanation =
    emptySearchScope === 'broader' && broaderFallback
      ? `We couldn’t find nearby listings using ${broaderFallback.searchTerm}, either.`
      : `We couldn’t find a nearby listing specifically for ${displayItem ?? 'this item'}.`;
  const guidanceOnlyText = requiresLocationCheck
    ? 'This item still needs a local acceptance check. Follow its disposal guidance or scan another item.'
    : 'No approved broader search is available for this item. Follow its disposal guidance or scan another item.';

  return (
    <SafeAreaView edges={['top']} style={styles.page}>
      <StatusBar style="dark" />
      <View style={styles.header}>
        <View>
          <Text style={styles.title}>nearby.</Text>
          <Text style={styles.subtitle}>{subtitle}</Text>
        </View>
        <View style={styles.filterButton}>
          <Ionicons color="#9C968F" name="options-outline" size={18} />
        </View>
      </View>

      <View style={styles.searchBar}>
        <Ionicons color="#B4AEA8" name="search-outline" size={18} />
        <TextInput
          autoCapitalize="none"
          autoCorrect={false}
          onChangeText={setSearchQuery}
          placeholder="Search facilities..."
          placeholderTextColor="#B4AEA8"
          returnKeyType="search"
          style={styles.searchInput}
          value={searchQuery}
        />
      </View>

      <ScrollView
        contentContainerStyle={[
          styles.list,
          { paddingBottom: insets.bottom + BOTTOM_NAV_BAR_HEIGHT + 18 },
        ]}
        showsVerticalScrollIndicator={false}
        style={styles.cards}>
        {isLoading ? (
          <View style={styles.stateCard}>
            <ActivityIndicator color="#050505" size="small" />
            <Text style={styles.stateText}>
              {broaderSearchTerm ? 'Loading broader Earth911 locations...' : 'Loading Earth911 locations...'}
            </Text>
          </View>
        ) : null}

        {!isLoading && errorMessage ? (
          <View style={styles.stateCard}>
            <Text selectable style={styles.stateText}>{errorMessage}</Text>
          </View>
        ) : null}

        {!isLoading && !errorMessage && emptySearchScope ? (
          <View style={styles.stateCard}>
            <View style={styles.stateIcon}>
              <Ionicons color="#5F5A54" name="location-outline" size={22} />
            </View>
            <Text selectable style={styles.stateTitle}>No verified local match found</Text>
            <Text selectable style={styles.stateText}>{noResultsExplanation}</Text>

            {supportsDonationReuse ? (
              <Text selectable style={styles.guidanceText}>
                If it’s clean and usable, donation or reuse may be a better option than disposal.
              </Text>
            ) : null}

            {canTryBroaderSearch ? (
              <>
                <View style={styles.warningBox}>
                  <Ionicons color="#8A6419" name="alert-circle-outline" size={18} />
                  <Text selectable style={styles.warningText}>
                    Broader results may not accept this exact item. Check accepted items before going.
                  </Text>
                </View>
                <Text selectable style={styles.fallbackHint}>
                  Search term: {broaderFallback.searchTerm}
                </Text>
                <Pressable
                  accessibilityRole="button"
                  onPress={tryBroaderSearch}
                  style={styles.primaryButton}>
                  <Text style={styles.primaryButtonText}>Try {broaderFallback.label}</Text>
                  <Ionicons color="#FFFFFF" name="search-outline" size={16} />
                </Pressable>
              </>
            ) : (
              <>
                <Text selectable style={styles.guidanceText}>{guidanceOnlyText}</Text>
                <Pressable
                  accessibilityRole="button"
                  onPress={() => router.navigate('/(tabs)')}
                  style={styles.primaryButton}>
                  <Text style={styles.primaryButtonText}>Scan another item</Text>
                  <Ionicons color="#FFFFFF" name="camera-outline" size={16} />
                </Pressable>
              </>
            )}
          </View>
        ) : null}

        {showBroaderNotice ? (
          <View style={styles.broaderNotice}>
            <View style={styles.noticeTitleRow}>
              <Ionicons color="#5F5A54" name="information-circle-outline" size={18} />
              <Text selectable style={styles.noticeTitle}>Broader match</Text>
            </View>
            <Text selectable style={styles.noticeText}>
              Found using: {broaderSearchTerm}{'\n'}
              Not verified specifically for: {displayItem ?? selectedItem}
            </Text>
            <Text selectable style={styles.noticeWarning}>
              Check accepted items before going.
            </Text>
          </View>
        ) : null}

        {!isLoading &&
          !errorMessage &&
          filteredLocations.map((location) => (
            <LocationCard
              key={location.id}
              {...location}
              onPress={() => {
                if (location.directionsUrl) {
                  Linking.openURL(location.directionsUrl);
                }
              }}
            />
          ))}

        {showEmptySearchState ? (
          <View style={styles.stateCard}>
            <Text selectable style={styles.stateText}>No locations match your search.</Text>
          </View>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  page: {
    backgroundColor: '#F3F1EE',
    flex: 1,
    paddingHorizontal: 18,
  },
  header: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingTop: 12,
  },
  title: {
    color: '#050505',
    fontSize: 34,
    fontWeight: '900',
    letterSpacing: -1.3,
  },
  subtitle: {
    color: '#9D9791',
    fontSize: 14,
    lineHeight: 20,
    marginTop: 4,
    maxWidth: 260,
  },
  filterButton: {
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    borderColor: '#E7E4DE',
    borderRadius: 999,
    borderWidth: 1,
    height: 36,
    justifyContent: 'center',
    marginTop: 10,
    width: 36,
  },
  searchBar: {
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    borderColor: '#E7E4DE',
    borderRadius: 999,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 10,
    marginTop: 18,
    paddingHorizontal: 14,
    paddingVertical: 14,
  },
  searchInput: {
    color: '#B4AEA8',
    flex: 1,
    fontSize: 14,
    fontWeight: '600',
    padding: 0,
  },
  cards: {
    flex: 1,
    marginTop: 18,
  },
  list: {
    gap: 18,
  },
  stateCard: {
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    borderColor: '#E6E3DE',
    borderRadius: 28,
    borderWidth: 1,
    gap: 12,
    paddingHorizontal: 24,
    paddingVertical: 28,
  },
  stateIcon: {
    alignItems: 'center',
    backgroundColor: '#F3F1EE',
    borderRadius: 999,
    height: 44,
    justifyContent: 'center',
    width: 44,
  },
  stateTitle: {
    color: '#171717',
    fontSize: 19,
    fontWeight: '800',
    lineHeight: 24,
    textAlign: 'center',
  },
  stateText: {
    color: '#78726C',
    fontSize: 14,
    fontWeight: '600',
    lineHeight: 20,
    textAlign: 'center',
  },
  guidanceText: {
    color: '#5F6858',
    fontSize: 13,
    fontWeight: '600',
    lineHeight: 19,
    textAlign: 'center',
  },
  warningBox: {
    alignItems: 'flex-start',
    alignSelf: 'stretch',
    backgroundColor: '#FFF8E8',
    borderColor: '#F0DEB5',
    borderRadius: 16,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 9,
    padding: 13,
  },
  warningText: {
    color: '#78591D',
    flex: 1,
    fontSize: 12,
    fontWeight: '700',
    lineHeight: 18,
  },
  fallbackHint: {
    color: '#9D9791',
    fontSize: 12,
    fontWeight: '600',
  },
  primaryButton: {
    alignItems: 'center',
    alignSelf: 'stretch',
    backgroundColor: '#050505',
    borderRadius: 999,
    flexDirection: 'row',
    gap: 8,
    justifyContent: 'center',
    paddingHorizontal: 18,
    paddingVertical: 14,
  },
  primaryButtonText: {
    color: '#FFFFFF',
    fontSize: 14,
    fontWeight: '800',
  },
  broaderNotice: {
    backgroundColor: '#FFFFFF',
    borderColor: '#E6E3DE',
    borderRadius: 20,
    borderWidth: 1,
    gap: 7,
    padding: 16,
  },
  noticeTitleRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 7,
  },
  noticeTitle: {
    color: '#38342F',
    fontSize: 14,
    fontWeight: '800',
  },
  noticeText: {
    color: '#78726C',
    fontSize: 13,
    fontWeight: '600',
    lineHeight: 19,
  },
  noticeWarning: {
    color: '#8A6419',
    fontSize: 12,
    fontWeight: '700',
    lineHeight: 18,
  },
});
