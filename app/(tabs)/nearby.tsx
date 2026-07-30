import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect } from '@react-navigation/native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert,
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
import { LocationCardSkeletonList } from '@/components/location-card-skeleton';
import { fetchNearbyLocations as fetchNearbyLocationsApi } from '@/api/client';
import { getApiErrorMessage } from '@/api/request';
import { getNearbyFallback, supportsNearbyDonationReuse } from '@/constants/nearby-search';
import { getLastNearbyScanContext, getLastScannedItem } from '@/constants/scan-session';
import {
  getAppLocationContext,
  LocationPermissionError,
  LocationUnavailableError,
  type AppCoordinates,
} from '@/app/location-context';

type NearbyLocation = LocationCardProps & {
  id: string;
  directionsUrl?: string | null;
};

type EmptySearchScope = 'exact' | 'broader';

type NearbySearchContext = {
  normalizedItem?: string | null;
  broadCategory?: string | null;
  disposalCategory?: string | null;
  materialCategory?: string | null;
  jurisdictionId?: string | null;
  localRuleId?: string | null;
};

type NearbyRouteParams = {
  autoSearch?: string | string[];
  item?: string | string[];
  normalizedItem?: string | string[];
  disposalCategory?: string | string[];
  broadCategory?: string | string[];
  materialCategory?: string | string[];
  disposalAction?: string | string[];
  requiresLocationCheck?: string | string[];
  scanSessionId?: string | string[];
  supportsDonationReuse?: string | string[];
  jurisdictionId?: string | string[];
  localRuleId?: string | string[];
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

async function fetchNearbyLocations(
  item: string,
  coordinates: AppCoordinates,
  context: NearbySearchContext = {},
  signal?: AbortSignal,
) {
  const query = new URLSearchParams({
    item,
    lat: String(coordinates.latitude),
    lon: String(coordinates.longitude),
  });
  if (context.normalizedItem) {
    query.set('normalized_item', context.normalizedItem);
  }
  if (context.broadCategory) {
    query.set('broad_category', context.broadCategory);
  }
  if (context.disposalCategory) {
    query.set('disposal_category', context.disposalCategory);
  }
  if (context.materialCategory) {
    query.set('material_category', context.materialCategory);
  }
  if (context.jurisdictionId && context.localRuleId) {
    query.set('jurisdiction_id', context.jurisdictionId);
    query.set('local_rule_id', context.localRuleId);
  }
  return fetchNearbyLocationsApi(query, signal);
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
  const [, refreshOnFocus] = useState(0);
  const routeParams = useLocalSearchParams<NearbyRouteParams>();

  useFocusEffect(
    useCallback(() => {
      refreshOnFocus((current) => current + 1);
    }, []),
  );

  const sessionContext = getLastNearbyScanContext();
  const routeAutoSearch = routeBoolean(getRouteValue(routeParams.autoSearch), false);
  const routeItem = getRouteValue(routeParams.item);
  const routeScanSessionId = getRouteValue(routeParams.scanSessionId);
  const routeMatchesCurrentScan =
    !!sessionContext?.scanSessionId && routeScanSessionId === sessionContext.scanSessionId;
  const routeReferencesCurrentScan = routeScanSessionId
    ? routeMatchesCurrentScan
    : !!sessionContext;
  const canUseRouteParams = routeReferencesCurrentScan;
  const selectedItem =
    sessionContext?.item ?? (canUseRouteParams ? routeItem : null) ?? getLastScannedItem();
  const normalizedItem =
    sessionContext?.normalizedItem ??
    (canUseRouteParams ? getRouteValue(routeParams.normalizedItem) : null);
  const displayItem = normalizedItem ?? selectedItem;
  const disposalCategory =
    sessionContext?.disposalCategory ??
    (canUseRouteParams ? getRouteValue(routeParams.disposalCategory) : null);
  const broadCategory =
    sessionContext?.broadCategory ??
    (canUseRouteParams ? getRouteValue(routeParams.broadCategory) : null);
  const materialCategory =
    sessionContext?.materialCategory ??
    (canUseRouteParams ? getRouteValue(routeParams.materialCategory) : null);
  const disposalAction =
    sessionContext?.disposalAction ??
    (canUseRouteParams ? getRouteValue(routeParams.disposalAction) : null);
  const requiresLocationCheck = routeBoolean(
    canUseRouteParams ? getRouteValue(routeParams.requiresLocationCheck) : null,
    sessionContext?.requiresLocationCheck ?? false,
  );
  const supportsDonationReuse = routeBoolean(
    canUseRouteParams ? getRouteValue(routeParams.supportsDonationReuse) : null,
    sessionContext?.supportsDonationReuse ??
      supportsNearbyDonationReuse({
        item: displayItem ?? '',
        disposalCategory,
        disposalAction,
      }),
  );
  const jurisdictionId =
    sessionContext?.jurisdictionId ??
    (canUseRouteParams ? getRouteValue(routeParams.jurisdictionId) : null);
  const localRuleId =
    sessionContext?.localRuleId ??
    (canUseRouteParams ? getRouteValue(routeParams.localRuleId) : null);
  const shouldAutoSearch =
    routeAutoSearch && routeReferencesCurrentScan && !!selectedItem;
  const activeNearbyKey =
    sessionContext?.scanSessionId ?? (canUseRouteParams ? routeScanSessionId ?? selectedItem : null);
  const broaderFallback = localRuleId ? null : getNearbyFallback(disposalCategory);
  const nearbyAbortControllerRef = useRef<AbortController | null>(null);
  const broaderAbortControllerRef = useRef<AbortController | null>(null);
  const broaderSearchLockRef = useRef(false);

  const [locations, setLocations] = useState<NearbyLocation[]>([]);
  const [searchStateNearbyKey, setSearchStateNearbyKey] = useState<string | null>(null);
  const [coordinates, setCoordinates] = useState<AppCoordinates | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [errorAction, setErrorAction] = useState<
    'retry' | 'retry_broader' | 'settings' | null
  >(null);
  const [retryKey, setRetryKey] = useState(0);
  const [emptySearchScope, setEmptySearchScope] = useState<EmptySearchScope | null>(null);
  const [broaderSearchTerm, setBroaderSearchTerm] = useState<string | null>(null);
  const [isUnsupportedMaterial, setIsUnsupportedMaterial] = useState(false);

  useEffect(() => {
    // Nearby is a persistent tab, so clear the previous search state when the active scan changes.
    setLocations([]);
    setSearchStateNearbyKey(null);
    setCoordinates(null);
    setSearchQuery('');
    setIsLoading(false);
    setErrorMessage(null);
    setErrorAction(null);
    setRetryKey(0);
    setEmptySearchScope(null);
    setBroaderSearchTerm(null);
    setIsUnsupportedMaterial(false);
    nearbyAbortControllerRef.current?.abort();
    broaderAbortControllerRef.current?.abort();
    broaderSearchLockRef.current = false;
  }, [selectedItem, sessionContext?.scanSessionId]);

  useEffect(() => {
    let isActive = true;
    const controller = new AbortController();
    nearbyAbortControllerRef.current?.abort();
    nearbyAbortControllerRef.current = controller;

    async function loadLocations() {
      if (!selectedItem || !shouldAutoSearch) {
        return;
      }

      setIsLoading(true);
      setSearchStateNearbyKey(activeNearbyKey);
      setErrorMessage(null);
      setErrorAction(null);
      setEmptySearchScope(null);
      setBroaderSearchTerm(null);
      setIsUnsupportedMaterial(false);

      try {
        const locationContext = await getAppLocationContext();
        const nextCoordinates = locationContext.coordinates;
        const data = await fetchNearbyLocations(selectedItem, nextCoordinates, {
          broadCategory,
          disposalCategory,
          jurisdictionId,
          localRuleId,
          materialCategory,
          normalizedItem,
        }, controller.signal);
        if (!isActive || controller.signal.aborted) {
          return;
        }

        const nextLocations = data.locations ?? [];
        setCoordinates(nextCoordinates);
        setLocations(nextLocations);
        if (data.reason === 'unsupported_material') {
          setIsUnsupportedMaterial(true);
          setEmptySearchScope(null);
        } else {
          setIsUnsupportedMaterial(false);
          setEmptySearchScope(nextLocations.length ? null : 'exact');
        }
      } catch (error) {
        if (!isActive || controller.signal.aborted) {
          return;
        }

        setLocations([]);
        setSearchStateNearbyKey(activeNearbyKey);
        setEmptySearchScope(null);
        setIsUnsupportedMaterial(false);
        if (error instanceof LocationPermissionError) {
          setErrorMessage('Location access is required to load nearby recycling sites.');
          setErrorAction(error.openSettings ? 'settings' : 'retry');
        } else if (error instanceof LocationUnavailableError) {
          setErrorMessage('Your location could not be determined right now.');
          setErrorAction('retry');
        } else {
          setErrorMessage(getApiErrorMessage(error, 'nearby'));
          setErrorAction('retry');
        }
      } finally {
        if (isActive && !controller.signal.aborted) {
          setIsLoading(false);
        }
        if (nearbyAbortControllerRef.current === controller) {
          nearbyAbortControllerRef.current = null;
        }
      }
    }

    loadLocations();

    return () => {
      isActive = false;
      controller.abort();
      if (nearbyAbortControllerRef.current === controller) {
        nearbyAbortControllerRef.current = null;
      }
    };
  }, [
    activeNearbyKey,
    broadCategory,
    disposalCategory,
    jurisdictionId,
    localRuleId,
    materialCategory,
    normalizedItem,
    selectedItem,
    shouldAutoSearch,
    retryKey,
  ]);

  async function tryBroaderSearch() {
    if (!broaderFallback || !coordinates || broaderSearchLockRef.current) {
      return;
    }

    broaderSearchLockRef.current = true;
    broaderAbortControllerRef.current?.abort();
    const controller = new AbortController();
    broaderAbortControllerRef.current = controller;
    setIsLoading(true);
    setErrorMessage(null);
    setErrorAction(null);
    setEmptySearchScope(null);
    setIsUnsupportedMaterial(false);
    setSearchQuery('');
    setBroaderSearchTerm(broaderFallback.searchTerm);

    try {
      const data = await fetchNearbyLocations(
        broaderFallback.searchTerm,
        coordinates,
        {},
        controller.signal,
      );
      if (controller.signal.aborted) {
        return;
      }
      const nextLocations = data.locations ?? [];
      setLocations(nextLocations);
      setSearchStateNearbyKey(activeNearbyKey);
      setBroaderSearchTerm(broaderFallback.searchTerm);
      if (data.reason === 'unsupported_material') {
        setIsUnsupportedMaterial(true);
        setEmptySearchScope(null);
      } else {
        setIsUnsupportedMaterial(false);
        setEmptySearchScope(nextLocations.length ? null : 'broader');
      }
    } catch (error) {
      if (controller.signal.aborted) {
        return;
      }
      setLocations([]);
      setSearchStateNearbyKey(activeNearbyKey);
      setBroaderSearchTerm(null);
      setIsUnsupportedMaterial(false);
      setErrorMessage(getApiErrorMessage(error, 'nearby'));
      setErrorAction('retry_broader');
    } finally {
      if (!controller.signal.aborted) {
        setIsLoading(false);
      }
      if (broaderAbortControllerRef.current === controller) {
        broaderAbortControllerRef.current = null;
      }
      broaderSearchLockRef.current = false;
    }
  }

  async function openLocationSettings() {
    try {
      await Linking.openSettings();
      setErrorAction('retry');
    } catch {
      Alert.alert(
        'Unable to open Settings',
        'Open Android Settings and allow location access for Green Bin.',
      );
    }
  }

  function retryNearbySearch() {
    setRetryKey((value) => value + 1);
  }

  const subtitle = displayItem
    ? `Find approved drop-off and recycling sites near you for ${displayItem.toLowerCase()}.`
    : 'Find approved drop-off and recycling sites near you.';
  const normalizedSearchQuery = normalizeSearchText(searchQuery);
  const hasCurrentNearbyState =
    !!selectedItem && !!activeNearbyKey && searchStateNearbyKey === activeNearbyKey;
  const currentLocations =
    hasCurrentNearbyState ? locations : [];
  const currentErrorMessage = hasCurrentNearbyState ? errorMessage : null;
  const currentErrorAction = hasCurrentNearbyState ? errorAction : null;
  const currentEmptySearchScope = hasCurrentNearbyState ? emptySearchScope : null;
  const currentBroaderSearchTerm = hasCurrentNearbyState ? broaderSearchTerm : null;
  const isCurrentLoading = hasCurrentNearbyState && isLoading;
  const isCurrentUnsupportedMaterial = hasCurrentNearbyState && isUnsupportedMaterial;
  const filteredLocations = normalizedSearchQuery
    ? currentLocations.filter((location) =>
        getLocationSearchText(location).includes(normalizedSearchQuery)
      )
    : currentLocations;
  const showEmptySearchState =
    !isCurrentLoading &&
    !currentErrorMessage &&
    !isCurrentUnsupportedMaterial &&
    !!normalizedSearchQuery &&
    filteredLocations.length === 0;
  const showBroaderNotice =
    !isCurrentLoading &&
    !currentErrorMessage &&
    !!currentBroaderSearchTerm &&
    currentLocations.length > 0;
  const showNoItemState = !isCurrentLoading && !currentErrorMessage && !selectedItem;
  const showReadyState =
    !isCurrentLoading &&
    !currentErrorMessage &&
    !!selectedItem &&
    !shouldAutoSearch &&
    !currentEmptySearchScope &&
    !isCurrentUnsupportedMaterial &&
    currentLocations.length === 0;
  const canTryBroaderSearch = currentEmptySearchScope === 'exact' && !!broaderFallback;
  const unsupportedMaterialMessage =
    "We couldn't find nearby drop-off locations for this item. This item may not be supported by our location database yet. Check your city or county's disposal rules for the most accurate guidance.";
  const noResultsExplanation =
    currentEmptySearchScope === 'broader' && broaderFallback
      ? `We couldn’t find nearby listings using ${broaderFallback.searchTerm}, either.`
      : `We couldn’t find a nearby listing specifically for ${displayItem ?? 'this item'}.`;
  const guidanceOnlyText = requiresLocationCheck
    ? 'This item still needs a local acceptance check. Follow its disposal guidance or scan another item.'
    : 'No approved broader search is available for this item. Follow its disposal guidance or scan another item.';

  return (
    <SafeAreaView edges={['top']} style={styles.page}>
      <View style={styles.header}>
        <View>
          <Text style={styles.title}>nearby.</Text>
          <Text style={styles.subtitle}>{subtitle}</Text>
        </View>
      </View>

      <View style={styles.searchBar}>
        <Ionicons color="#B4AEA8" name="search-outline" size={18} />
        <TextInput
          accessibilityLabel="Search nearby facilities"
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
        {isCurrentLoading ? (
          <LocationCardSkeletonList />
        ) : null}

        {!isCurrentLoading && currentErrorMessage ? (
          <View style={styles.stateCard}>
            <Text selectable style={styles.stateText}>{currentErrorMessage}</Text>
            {currentErrorAction ? (
              <Pressable
                accessibilityRole="button"
                onPress={
                  currentErrorAction === 'settings'
                    ? openLocationSettings
                    : currentErrorAction === 'retry_broader'
                      ? tryBroaderSearch
                      : retryNearbySearch
                }
                style={styles.primaryButton}>
                <Text style={styles.primaryButtonText}>
                  {currentErrorAction === 'settings' ? 'Open Settings' : 'Try Again'}
                </Text>
              </Pressable>
            ) : null}
          </View>
        ) : null}

        {showNoItemState ? (
          <View style={styles.stateCard}>
            <View style={styles.stateIcon}>
              <Ionicons color="#5F5A54" name="camera-outline" size={22} />
            </View>
            <Text selectable style={styles.stateTitle}>Scan an item first</Text>
            <Text selectable style={styles.stateText}>
              Scan something on the Scan tab, then open Nearby when you want location results.
            </Text>
            <Pressable
              accessibilityRole="button"
              onPress={() => router.navigate('/(tabs)')}
              style={styles.primaryButton}>
              <Text style={styles.primaryButtonText}>Go to Scan</Text>
              <Ionicons color="#FFFFFF" name="camera-outline" size={16} />
            </Pressable>
          </View>
        ) : null}

        {showReadyState ? (
          <View style={styles.stateCard}>
            <View style={styles.stateIcon}>
              <Ionicons color="#5F5A54" name="location-outline" size={22} />
            </View>
            <Text selectable style={styles.stateTitle}>Ready when you are</Text>
            <Text selectable style={styles.stateText}>
              {`Nearby results for ${displayItem ?? selectedItem} have not been loaded yet.`}
            </Text>
            <Text selectable style={styles.guidanceText}>
              Go back to the Scan tab and tap Find Nearby Locations to search for this item.
            </Text>
            <Pressable
              accessibilityRole="button"
              onPress={() => router.navigate('/(tabs)')}
              style={styles.primaryButton}>
              <Text style={styles.primaryButtonText}>Go to Scan</Text>
              <Ionicons color="#FFFFFF" name="camera-outline" size={16} />
            </Pressable>
          </View>
        ) : null}

        {!isCurrentLoading && !currentErrorMessage && currentEmptySearchScope ? (
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

        {!isCurrentLoading && !currentErrorMessage && isCurrentUnsupportedMaterial ? (
          <View style={styles.stateCard}>
            <View style={styles.stateIcon}>
              <Ionicons color="#5F5A54" name="information-circle-outline" size={22} />
            </View>
            <Text selectable style={styles.stateTitle}>No supported material match</Text>
            <Text selectable style={styles.stateText}>{unsupportedMaterialMessage}</Text>
            <Pressable
              accessibilityRole="button"
              onPress={() => router.navigate('/(tabs)')}
              style={styles.primaryButton}>
              <Text style={styles.primaryButtonText}>Scan another item</Text>
              <Ionicons color="#FFFFFF" name="camera-outline" size={16} />
            </Pressable>
          </View>
        ) : null}

        {showBroaderNotice ? (
          <View style={styles.broaderNotice}>
            <View style={styles.noticeTitleRow}>
              <Ionicons color="#5F5A54" name="information-circle-outline" size={18} />
              <Text selectable style={styles.noticeTitle}>Broader match</Text>
            </View>
            <Text selectable style={styles.noticeText}>
              Found using: {currentBroaderSearchTerm}{'\n'}
              Not verified specifically for: {displayItem ?? selectedItem}
            </Text>
            <Text selectable style={styles.noticeWarning}>
              Check accepted items before going.
            </Text>
          </View>
        ) : null}

        {!isCurrentLoading &&
          !currentErrorMessage &&
          filteredLocations.map((location) => (
            <LocationCard
              key={location.id}
              {...location}
              onPress={() => {
                if (location.directionsUrl) {
                  Linking.openURL(location.directionsUrl).catch(() => {
                    Alert.alert(
                      'Unable to open directions',
                      'Try opening this location in your maps app.',
                    );
                  });
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
