import Constants from 'expo-constants';
import { Platform } from 'react-native';

const API_HOST_OVERRIDE = '10.0.0.121';
const API_PORT = 8000;

export const DOWNTOWN_AUSTIN_COORDS = {
  lat: 30.2672,
  lon: -97.7431,
} as const;

export function getApiBaseUrl() {
  const expoHost = Constants.expoConfig?.hostUri?.split(':')[0];
  const host =
    API_HOST_OVERRIDE || (Platform.OS === 'web' ? 'localhost' : expoHost ?? 'localhost');

  return `http://${host}:${API_PORT}`;
}

export const API_BASE_URL = getApiBaseUrl();
