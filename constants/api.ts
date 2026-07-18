import Constants from 'expo-constants';
import { Platform } from 'react-native';

import { resolveApiBaseUrl } from '@/app/api-config';

const API_HOST_OVERRIDE = process.env.EXPO_PUBLIC_API_HOST_OVERRIDE?.trim();
const API_BASE_URL_OVERRIDE = process.env.EXPO_PUBLIC_API_BASE_URL?.trim();

export function getApiBaseUrl() {
  const expoHost = Constants.expoConfig?.hostUri?.split(':')[0];
  const developmentHost =
    API_HOST_OVERRIDE || (Platform.OS === 'web' ? 'localhost' : expoHost ?? 'localhost');

  return resolveApiBaseUrl({
    configuredUrl: API_BASE_URL_OVERRIDE,
    developmentHost,
    isDevelopment: __DEV__,
  });
}

export const API_BASE_URL = getApiBaseUrl();
