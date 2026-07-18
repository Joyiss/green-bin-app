export type ApiErrorKind =
  | 'configuration'
  | 'network'
  | 'timeout'
  | 'rate_limit'
  | 'unavailable'
  | 'invalid_response'
  | 'request';

export class ApiError extends Error {
  readonly body: unknown;
  readonly kind: ApiErrorKind;
  readonly retryable: boolean;
  readonly status: number | null;

  constructor(
    kind: ApiErrorKind,
    {
      cause,
      body = null,
      message,
      retryable = false,
      status = null,
    }: {
      cause?: unknown;
      body?: unknown;
      message?: string;
      retryable?: boolean;
      status?: number | null;
    } = {},
  ) {
    super(message ?? `API request failed: ${kind}`, { cause });
    this.name = 'ApiError';
    this.body = body;
    this.kind = kind;
    this.retryable = retryable;
    this.status = status;
  }
}

type RequestJsonOptions<T> = {
  fetchImpl?: typeof fetch;
  init?: RequestInit;
  retryCount?: number;
  retryDelayMs?: number;
  signal?: AbortSignal;
  timeoutMs: number;
  validate: (value: unknown) => T;
};

export type RequestLock = { current: boolean };

export function acquireRequestLock(lock: RequestLock) {
  if (lock.current) {
    return false;
  }
  lock.current = true;
  return true;
}

export function releaseRequestLock(lock: RequestLock) {
  lock.current = false;
}

function errorForStatus(status: number, body: unknown) {
  if (status === 429) {
    return new ApiError('rate_limit', { body, retryable: true, status });
  }
  if (status === 408) {
    return new ApiError('timeout', { body, retryable: true, status });
  }
  if (status === 425 || status === 502 || status === 503 || status === 504) {
    return new ApiError('unavailable', { body, retryable: true, status });
  }
  if (status >= 500) {
    return new ApiError('unavailable', { body, retryable: true, status });
  }
  return new ApiError('request', { body, status });
}

function canRetryAutomatically(error: ApiError) {
  return error.kind === 'network' || error.kind === 'timeout' || error.kind === 'unavailable';
}

function wait(milliseconds: number, signal?: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    if (signal?.aborted) {
      reject(new ApiError('request', { message: 'Request was cancelled.' }));
      return;
    }
    const timeout = setTimeout(() => {
      signal?.removeEventListener('abort', cancel);
      resolve();
    }, milliseconds);
    const cancel = () => {
      clearTimeout(timeout);
      reject(new ApiError('request', { message: 'Request was cancelled.' }));
    };
    signal?.addEventListener('abort', cancel, { once: true });
  });
}

async function readResponseJson(response: Response) {
  try {
    return (await response.json()) as unknown;
  } catch {
    return null;
  }
}

export async function requestJson<T>(
  url: string,
  {
    fetchImpl = fetch,
    init,
    retryCount = 0,
    retryDelayMs = 750,
    signal,
    timeoutMs,
    validate,
  }: RequestJsonOptions<T>,
): Promise<T> {
  let attempt = 0;

  while (true) {
    const controller = new AbortController();
    let timedOut = false;
    const abortFromCaller = () => controller.abort();
    if (signal?.aborted) {
      throw new ApiError('request', { message: 'Request was cancelled.' });
    }
    signal?.addEventListener('abort', abortFromCaller, { once: true });
    const timeout = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, timeoutMs);

    try {
      const response = await fetchImpl(url, {
        ...init,
        signal: controller.signal,
      });
      const body = await readResponseJson(response);
      if (!response.ok) {
        throw errorForStatus(response.status, body);
      }
      try {
        return validate(body);
      } catch (error) {
        throw new ApiError('invalid_response', { cause: error });
      }
    } catch (error) {
      const apiError =
        error instanceof ApiError
          ? error
          : timedOut
            ? new ApiError('timeout', { cause: error, retryable: true })
            : signal?.aborted
              ? new ApiError('request', { cause: error, message: 'Request was cancelled.' })
              : new ApiError('network', { cause: error, retryable: true });

      if (!canRetryAutomatically(apiError) || attempt >= retryCount || signal?.aborted) {
        throw apiError;
      }
      attempt += 1;
      if (retryDelayMs > 0) {
        await wait(retryDelayMs, signal);
      }
    } finally {
      clearTimeout(timeout);
      signal?.removeEventListener('abort', abortFromCaller);
    }
  }
}

export function getApiErrorMessage(error: unknown, action: 'scan' | 'nearby' | 'labels') {
  const apiError = error instanceof ApiError ? error : null;

  if (apiError?.kind === 'configuration') {
    return 'This build is missing its production service configuration.';
  }
  if (apiError?.kind === 'timeout') {
    return action === 'scan'
      ? 'Green Bin took too long to respond. Your photo is still ready to retry.'
      : 'Green Bin took too long to respond. Please try again.';
  }
  if (apiError?.kind === 'network') {
    return 'You appear to be offline. Check your connection and try again.';
  }
  if (apiError?.kind === 'rate_limit') {
    return 'Too many requests were sent. Please wait and try again.';
  }
  if (apiError?.kind === 'invalid_response') {
    return 'Green Bin received an unexpected server response. Please try again.';
  }
  if (apiError?.kind === 'unavailable') {
    return 'The Green Bin service is unavailable right now. Please try again shortly.';
  }
  return action === 'scan'
    ? 'Green Bin could not analyze this image. Please try again.'
    : 'Green Bin could not complete this request. Please try again.';
}
