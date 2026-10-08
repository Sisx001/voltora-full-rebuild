export function resolveApiConfiguration(value?: string) {
  const invalid = {root: '', error: 'Store connection is not configured. The owner must set REACT_APP_BACKEND_URL to the HTTPS API origin and rebuild the frontend.'};
  if (!value?.trim()) return invalid;
  try {
    const url = new URL(value.trim());
    if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash || !['', '/'].includes(url.pathname)) return invalid;
    return {root: url.origin + '/api', error: ''};
  } catch { return invalid; }
}

export type StoreFailure = {
  kind: 'configuration' | 'offline' | 'timeout' | 'network' | 'server' | 'invalid-response';
  reference: string;
  serverReference: boolean;
  status?: number;
  occurredAt: string;
};

export function storeFailure(error: any, online = true): StoreFailure {
  const rawReference = error?.response?.data?.correlation_id || error?.response?.headers?.['x-correlation-id'];
  const validReference = typeof rawReference === 'string' && /^[A-Za-z0-9_-]{6,80}$/.test(rawReference);
  const status = error?.response?.status;
  return {
    kind: error?.code === 'ERR_API_CONFIGURATION' ? 'configuration' : !online ? 'offline' : ['ECONNABORTED', 'ETIMEDOUT'].includes(error?.code) ? 'timeout' : error?.code === 'ERR_STORE_RESPONSE' ? 'invalid-response' : status ? 'server' : 'network',
    reference: validReference ? rawReference : 'LOCAL-' + (globalThis.crypto?.randomUUID?.() || Date.now().toString(36)).slice(0, 18),
    serverReference: validReference,
    status: typeof status === 'number' ? status : undefined,
    occurredAt: new Date().toISOString(),
  };
}

export function isStoreConfiguration(data: any): boolean {
  return !!(data && typeof data === 'object' && data.settings && typeof data.settings.features === 'object' && data.settings.features && data.theme && typeof data.theme === 'object' && data.home && Array.isArray(data.home.sections) && Array.isArray(data.categories) && Array.isArray(data.brands) && Array.isArray(data.settings.navigation) && Array.isArray(data.settings.payments));
}
