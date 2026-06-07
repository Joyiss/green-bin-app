import Constants from 'expo-constants';
import { Platform } from 'react-native';

const API_HOST_OVERRIDE = process.env.EXPO_PUBLIC_API_HOST_OVERRIDE?.trim();
const API_BASE_URL_OVERRIDE = process.env.EXPO_PUBLIC_API_BASE_URL?.trim();
const API_PORT = 8000;

export function getApiBaseUrl() {
  if (API_BASE_URL_OVERRIDE) {
    return API_BASE_URL_OVERRIDE;
  }

  const expoHost = Constants.expoConfig?.hostUri?.split(':')[0];
  const host =
    API_HOST_OVERRIDE || (Platform.OS === 'web' ? 'localhost' : expoHost ?? 'localhost');

  return `http://${host}:${API_PORT}`;
}

export const API_BASE_URL = getApiBaseUrl();