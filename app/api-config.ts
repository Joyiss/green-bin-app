const LOCAL_API_PORT = 8000;

function normalizeUrl(value: string) {
  try {
    const parsed = new URL(value);
    if (!parsed.hostname || (parsed.protocol !== 'https:' && parsed.protocol !== 'http:')) {
      return null;
    }
    return parsed.toString().replace(/\/+$/, '');
  } catch {
    return null;
  }
}

export function resolveApiBaseUrl({
  configuredUrl,
  developmentHost,
  isDevelopment,
}: {
  configuredUrl?: string | null;
  developmentHost?: string | null;
  isDevelopment: boolean;
}) {
  const normalizedConfiguredUrl = configuredUrl?.trim()
    ? normalizeUrl(configuredUrl.trim())
    : null;

  if (normalizedConfiguredUrl) {
    if (!isDevelopment && !normalizedConfiguredUrl.startsWith('https://')) {
      return null;
    }
    return normalizedConfiguredUrl;
  }

  if (!isDevelopment) {
    return null;
  }

  const host = developmentHost?.trim() || 'localhost';
  return `http://${host}:${LOCAL_API_PORT}`;
}

