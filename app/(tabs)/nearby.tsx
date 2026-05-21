import { Ionicons } from '@expo/vector-icons';
import * as Location from 'expo-location';
import { useLocalSearchParams } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Linking, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { LocationCard, type LocationCardProps } from '@/components/location-card';
import { SearchChip } from '@/components/search-chip';
import { API_BASE_URL } from '@/constants/api';
import { locationFilters } from '@/constants/mock-data';
import { getLastScannedItem } from '@/constants/scan-session';

type NearbyLocation = LocationCardProps & {
  id: string;
  directionsUrl?: string | null;
};

type NearbyLocationsResponse = {
  item: string;
  material_id: number | null;
  locations: NearbyLocation[];
};

function getRouteItem(value: string | string[] | undefined) {
  if (typeof value === 'string') {
    return value;
  }

  if (Array.isArray(value)) {
    return value[0];
  }

  return null;
}

export default function NearbyScreen() {
  const { item } = useLocalSearchParams<{ item?: string | string[] }>();
  const selectedItem = getRouteItem(item) ?? getLastScannedItem();
  const [locations, setLocations] = useState<NearbyLocation[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    let isActive = true;

    async function loadLocations() {
      if (!selectedItem) {
        setLocations([]);
        setErrorMessage('Scan an item to load real drop-off locations.');
        return;
      }

      setIsLoading(true);
      setErrorMessage(null);

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

        const query = new URLSearchParams({
          item: selectedItem,
          lat: String(position.coords.latitude),
          lon: String(position.coords.longitude),
        });
        const response = await fetch(`${API_BASE_URL}/nearby_locations?${query.toString()}`);

        if (!response.ok) {
          throw new Error(`Request failed with status ${response.status}`);
        }

        const data = (await response.json()) as NearbyLocationsResponse;
        if (!isActive) {
          return;
        }

        setLocations(data.locations ?? []);
        setErrorMessage(
          data.locations?.length
            ? null
            : `No Earth911 locations were found for ${selectedItem.toLowerCase()}.`
        );
      } catch (error) {
        if (!isActive) {
          return;
        }

        setLocations([]);
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

  const subtitle = selectedItem
    ? `Find approved drop-off and recycling sites near you for ${selectedItem.toLowerCase()}.`
    : 'Find approved drop-off and recycling sites near you.';

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
        <Text style={styles.searchText}>Search facilities...</Text>
      </View>

      <ScrollView
        contentContainerStyle={styles.scrollContent}
        horizontal
        showsHorizontalScrollIndicator={false}
        style={styles.filtersRow}>
        {locationFilters.map((filter, index) => (
          <SearchChip key={filter.id} isActive={index === 0} label={filter.label} />
        ))}
      </ScrollView>

      <ScrollView
        contentContainerStyle={styles.list}
        showsVerticalScrollIndicator={false}
        style={styles.cards}>
        {isLoading ? (
          <View style={styles.stateCard}>
            <ActivityIndicator color="#050505" size="small" />
            <Text style={styles.stateText}>Loading Earth911 locations...</Text>
          </View>
        ) : null}

        {!isLoading && errorMessage ? (
          <View style={styles.stateCard}>
            <Text style={styles.stateText}>{errorMessage}</Text>
          </View>
        ) : null}

        {!isLoading &&
          !errorMessage &&
          locations.map((location) => (
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
  searchText: {
    color: '#B4AEA8',
    fontSize: 14,
    fontWeight: '600',
  },
  filtersRow: {
    marginTop: 16,
    maxHeight: 48,
  },
  scrollContent: {
    gap: 10,
    paddingRight: 10,
  },
  cards: {
    flex: 1,
    marginTop: 18,
  },
  list: {
    gap: 18,
    paddingBottom: 28,
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
  stateText: {
    color: '#78726C',
    fontSize: 14,
    fontWeight: '600',
    lineHeight: 20,
    textAlign: 'center',
  },
});
