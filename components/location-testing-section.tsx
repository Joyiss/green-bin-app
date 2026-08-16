import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect } from '@react-navigation/native';
import { useCallback, useState } from 'react';
import { Alert, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import {
  createDevelopmentLocationOverride,
  DEFAULT_DEVELOPMENT_LOCATION_SETTINGS,
  DEVELOPMENT_LOCATION_PRESETS,
  getDevelopmentLocationPresetId,
  loadDevelopmentLocationSettings,
  saveDevelopmentLocationSettings,
  type DevelopmentLocationPreset,
  type DevelopmentLocationSettings,
} from '@/app/development-location';
import { PRIMARY_TEXT_STYLES, SECONDARY_TEXT_STYLES } from '@/constants/typography';

export function LocationTestingSection() {
  const [settings, setSettings] = useState<DevelopmentLocationSettings>(
    DEFAULT_DEVELOPMENT_LOCATION_SETTINGS,
  );
  const [selectedPreset, setSelectedPreset] =
    useState<DevelopmentLocationPreset['id']>('real');
  const [customCity, setCustomCity] = useState('');
  const [customCounty, setCustomCounty] = useState('');
  const [customState, setCustomState] = useState('');
  const [customCountry, setCustomCountry] = useState('United States');
  const customOverride = createDevelopmentLocationOverride(
    customCity,
    customCounty,
    customState,
    customCountry,
  );

  useFocusEffect(
    useCallback(() => {
      let isActive = true;
      void loadDevelopmentLocationSettings().then((storedSettings) => {
        if (!isActive) {
          return;
        }
        setSettings(storedSettings);
        const presetId = getDevelopmentLocationPresetId(storedSettings.location);
        setSelectedPreset(presetId);
        if (presetId === 'custom') {
          setCustomCity(storedSettings.location.city);
          setCustomCounty(storedSettings.location.county ?? '');
          setCustomState(storedSettings.location.state);
          setCustomCountry(storedSettings.location.country);
        }
      });
      return () => {
        isActive = false;
      };
    }, []),
  );

  const persistSettings = useCallback(
    async (nextSettings: DevelopmentLocationSettings) => {
      try {
        const storedSettings = await saveDevelopmentLocationSettings(nextSettings);
        setSettings(storedSettings);
      } catch {
        Alert.alert('Could not save testing location', 'Try selecting the location again.');
      }
    },
    [],
  );

  const handlePresetPress = useCallback(
    (preset: DevelopmentLocationPreset) => {
      setSelectedPreset(preset.id);
      if (preset.id === 'custom' || !preset.location) {
        return;
      }
      void persistSettings({ location: preset.location });
    },
    [persistSettings],
  );

  const handleApplyCustomLocation = useCallback(() => {
    if (!customOverride) {
      return;
    }
    void persistSettings({ location: customOverride });
  }, [customOverride, persistSettings]);

  const selectedLocationLabel = settings.location.enabled
    ? [
        settings.location.city,
        settings.location.county,
        settings.location.state,
        settings.location.country,
      ]
        .filter(Boolean)
        .join(', ')
    : 'Automatic device location';

  return (
    <View style={styles.devSection}>
      <View style={styles.devHeadingRow}>
        <View style={styles.devIcon}>
          <Ionicons color="#7A4E00" name="construct-outline" size={19} />
        </View>
        <View style={styles.devHeadingText}>
          <Text style={styles.devTitle}>Location Testing</Text>
          <Text style={styles.devDescription}>
            Development-only override for testing local Tavily guidance.
          </Text>
        </View>
      </View>

      <View style={styles.devCurrentLocation}>
        <Text style={styles.devCurrentLocationLabel}>Currently selected</Text>
        <Text style={styles.devCurrentLocationValue}>{selectedLocationLabel}</Text>
      </View>

      <View style={styles.devPresetList}>
        {DEVELOPMENT_LOCATION_PRESETS.map((preset) => {
          const selected = selectedPreset === preset.id;
          return (
            <Pressable
              accessibilityRole="radio"
              accessibilityState={{ checked: selected }}
              key={preset.id}
              onPress={() => handlePresetPress(preset)}
              style={({ pressed }) => [
                styles.devPreset,
                selected && styles.devPresetSelected,
                pressed && styles.cardPressed,
              ]}
            >
              <Ionicons
                color={selected ? '#2E6B47' : '#9A948C'}
                name={selected ? 'radio-button-on' : 'radio-button-off'}
                size={18}
              />
              <Text style={[styles.devPresetText, selected && styles.devPresetTextSelected]}>
                {preset.label}
              </Text>
            </Pressable>
          );
        })}
      </View>

      {selectedPreset === 'custom' ? (
        <View style={styles.devCustomFields}>
          <TextInput
            accessibilityLabel="Custom test city"
            autoCapitalize="words"
            onChangeText={setCustomCity}
            placeholder="City"
            placeholderTextColor="#9A948C"
            style={styles.devInput}
            value={customCity}
          />
          <TextInput
            accessibilityLabel="Custom test county"
            autoCapitalize="words"
            onChangeText={setCustomCounty}
            placeholder="County (optional)"
            placeholderTextColor="#9A948C"
            style={styles.devInput}
            value={customCounty}
          />
          <TextInput
            accessibilityLabel="Custom test state"
            autoCapitalize="words"
            onChangeText={setCustomState}
            placeholder="State"
            placeholderTextColor="#9A948C"
            style={styles.devInput}
            value={customState}
          />
          <TextInput
            accessibilityLabel="Custom test country"
            autoCapitalize="words"
            onChangeText={setCustomCountry}
            placeholder="Country"
            placeholderTextColor="#9A948C"
            style={styles.devInput}
            value={customCountry}
          />
          <Pressable
            accessibilityRole="button"
            disabled={!customOverride}
            onPress={handleApplyCustomLocation}
            style={({ pressed }) => [
              styles.devApplyButton,
              !customOverride && styles.devApplyButtonDisabled,
              pressed && customOverride && styles.cardPressed,
            ]}
          >
            <Text style={styles.devApplyButtonText}>Use Custom Location</Text>
          </Pressable>
        </View>
      ) : null}

      <Text style={styles.devNote}>
        This changes only the coarse location sent with prediction requests. Precise device
        coordinates are never included.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  cardPressed: { opacity: 0.86 },
  devSection: {
    backgroundColor: '#FFF9ED', borderColor: '#EBCF96', borderRadius: 24,
    borderWidth: 1, gap: 14, padding: 16,
  },
  devHeadingRow: { alignItems: 'flex-start', flexDirection: 'row', gap: 12 },
  devIcon: {
    alignItems: 'center', backgroundColor: '#FBE7BC', borderRadius: 14,
    height: 40, justifyContent: 'center', width: 40,
  },
  devHeadingText: { flex: 1, gap: 4 },
  devTitle: { color: '#4F3200', fontSize: 16, ...PRIMARY_TEXT_STYLES.title },
  devDescription: {
    color: '#765A26', fontSize: 12, lineHeight: 17, ...SECONDARY_TEXT_STYLES.regular,
  },
  devCurrentLocation: {
    backgroundColor: '#FBEFD3', borderRadius: 12, gap: 3,
    paddingHorizontal: 12, paddingVertical: 10,
  },
  devCurrentLocationLabel: {
    color: '#80683B', fontSize: 10, letterSpacing: 1, textTransform: 'uppercase',
    ...SECONDARY_TEXT_STYLES.extraBold,
  },
  devCurrentLocationValue: {
    color: '#4F3200', fontSize: 13, lineHeight: 18, ...SECONDARY_TEXT_STYLES.extraBold,
  },
  devPresetList: { gap: 7 },
  devPreset: {
    alignItems: 'center', backgroundColor: '#FFFFFF', borderColor: '#E8DFD0',
    borderRadius: 14, borderWidth: 1, flexDirection: 'row', gap: 10,
    minHeight: 44, paddingHorizontal: 12, paddingVertical: 10,
  },
  devPresetSelected: { backgroundColor: '#F1F8EF', borderColor: '#76A882' },
  devPresetText: { color: '#5F5A54', flex: 1, fontSize: 13, ...PRIMARY_TEXT_STYLES.button },
  devPresetTextSelected: { color: '#234C31' },
  devCustomFields: { gap: 8 },
  devInput: {
    backgroundColor: '#FFFFFF', borderColor: '#DDD4C5', borderRadius: 12,
    borderWidth: 1, color: '#171717', fontSize: 14, minHeight: 44,
    paddingHorizontal: 12, ...SECONDARY_TEXT_STYLES.regular,
  },
  devApplyButton: {
    alignItems: 'center', backgroundColor: '#2E6B47', borderRadius: 12,
    justifyContent: 'center', minHeight: 42, paddingHorizontal: 14,
  },
  devApplyButtonDisabled: { backgroundColor: '#AFA89E', opacity: 0.65 },
  devApplyButtonText: { color: '#FFFFFF', fontSize: 13, ...PRIMARY_TEXT_STYLES.button },
  devNote: {
    color: '#765A26', fontSize: 11, lineHeight: 16, ...SECONDARY_TEXT_STYLES.semiBold,
  },
});
