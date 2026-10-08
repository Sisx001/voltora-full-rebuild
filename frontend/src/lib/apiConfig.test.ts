import { resolveApiConfiguration, storeFailure, isStoreConfiguration } from './apiConfig';

describe('resolveApiConfiguration', () => {
  const invalidResult = {
    root: '',
    error: 'Store connection is not configured. The owner must set REACT_APP_BACKEND_URL to the HTTPS API origin and rebuild the frontend.',
  };

  it('should return error for missing value', () => {
    expect(resolveApiConfiguration()).toEqual(invalidResult);
    expect(resolveApiConfiguration('')).toEqual(invalidResult);
    expect(resolveApiConfiguration('   ')).toEqual(invalidResult);
  });

  it('should return error for invalid URL', () => {
    expect(resolveApiConfiguration('not-a-url')).toEqual(invalidResult);
    expect(resolveApiConfiguration('ftp://example.com')).toEqual(invalidResult);
  });

  it('should return error for non-HTTPS protocol', () => {
    expect(resolveApiConfiguration('http://example.com')).toEqual(invalidResult);
  });

  it('should return error for URL with credentials', () => {
    expect(resolveApiConfiguration('https://user:pass@example.com')).toEqual(invalidResult);
    expect(resolveApiConfiguration('https://user@example.com')).toEqual(invalidResult);
  });

  it('should return error for URL with query string', () => {
    expect(resolveApiConfiguration('https://example.com?key=value')).toEqual(invalidResult);
  });

  it('should return error for URL with hash', () => {
    expect(resolveApiConfiguration('https://example.com#section')).toEqual(invalidResult);
  });

  it('should return error for URL with non-root pathname', () => {
    expect(resolveApiConfiguration('https://example.com/path')).toEqual(invalidResult);
    expect(resolveApiConfiguration('https://example.com/api')).toEqual(invalidResult);
  });

  it('should accept valid HTTPS origin', () => {
    expect(resolveApiConfiguration('https://example.com')).toEqual({
      root: 'https://example.com/api',
      error: '',
    });
  });

  it('should accept valid HTTPS origin with trailing slash', () => {
    expect(resolveApiConfiguration('https://example.com/')).toEqual({
      root: 'https://example.com/api',
      error: '',
    });
  });

  it('should handle whitespace in URL', () => {
    expect(resolveApiConfiguration('  https://example.com  ')).toEqual({
      root: 'https://example.com/api',
      error: '',
    });
  });

  it('should preserve port in origin', () => {
    expect(resolveApiConfiguration('https://example.com:8443')).toEqual({
      root: 'https://example.com:8443/api',
      error: '',
    });
  });
});

describe('storeFailure', () => {
  beforeEach(() => {
    jest.spyOn(Date.prototype, 'toISOString').mockReturnValue('2025-01-01T00:00:00.000Z');
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('should detect configuration error', () => {
    const error = { code: 'ERR_API_CONFIGURATION' };
    const result = storeFailure(error, true);
    expect(result.kind).toBe('configuration');
    expect(result.serverReference).toBe(false);
    expect(result.reference).toMatch(/^LOCAL-/);
  });

  it('should detect offline error', () => {
    const error = { code: 'ERR_NETWORK' };
    const result = storeFailure(error, false);
    expect(result.kind).toBe('offline');
    expect(result.serverReference).toBe(false);
  });

  it('should detect timeout error', () => {
    const error = { code: 'ECONNABORTED' };
    const result = storeFailure(error, true);
    expect(result.kind).toBe('timeout');
    expect(result.serverReference).toBe(false);
  });

  it('should detect timeout error with ETIMEDOUT', () => {
    const error = { code: 'ETIMEDOUT' };
    const result = storeFailure(error, true);
    expect(result.kind).toBe('timeout');
  });

  it('should detect invalid response error', () => {
    const error = { code: 'ERR_STORE_RESPONSE' };
    const result = storeFailure(error, true);
    expect(result.kind).toBe('invalid-response');
    expect(result.serverReference).toBe(false);
  });

  it('should detect server error with status', () => {
    const error = { response: { status: 503 } };
    const result = storeFailure(error, true);
    expect(result.kind).toBe('server');
    expect(result.status).toBe(503);
    expect(result.serverReference).toBe(false);
  });

  it('should detect network error without status', () => {
    const error = { code: 'ERR_NETWORK' };
    const result = storeFailure(error, true);
    expect(result.kind).toBe('network');
    expect(result.status).toBeUndefined();
  });

  it('should extract valid correlation_id from response data', () => {
    const error = {
      response: {
        status: 500,
        data: { correlation_id: 'abc123XYZ-_456789' },
      },
    };
    const result = storeFailure(error, true);
    expect(result.reference).toBe('abc123XYZ-_456789');
    expect(result.serverReference).toBe(true);
  });

  it('should extract valid correlation_id from response headers', () => {
    const error = {
      response: {
        status: 500,
        headers: { 'x-correlation-id': 'header-correlation-123' },
      },
    };
    const result = storeFailure(error, true);
    expect(result.reference).toBe('header-correlation-123');
    expect(result.serverReference).toBe(true);
  });

  it('should prefer data correlation_id over header', () => {
    const error = {
      response: {
        status: 500,
        data: { correlation_id: 'data-id' },
        headers: { 'x-correlation-id': 'header-id' },
      },
    };
    const result = storeFailure(error, true);
    expect(result.reference).toBe('data-id');
  });

  it('should reject invalid correlation_id format', () => {
    const error = {
      response: {
        status: 500,
        data: { correlation_id: 'invalid!@#$%' },
      },
    };
    const result = storeFailure(error, true);
    expect(result.reference).toMatch(/^LOCAL-/);
    expect(result.serverReference).toBe(false);
  });

  it('should reject too short correlation_id', () => {
    const error = {
      response: {
        status: 500,
        data: { correlation_id: 'abc' },
      },
    };
    const result = storeFailure(error, true);
    expect(result.reference).toMatch(/^LOCAL-/);
    expect(result.serverReference).toBe(false);
  });

  it('should reject non-string correlation_id', () => {
    const error = {
      response: {
        status: 500,
        data: { correlation_id: 12345 },
      },
    };
    const result = storeFailure(error, true);
    expect(result.reference).toMatch(/^LOCAL-/);
    expect(result.serverReference).toBe(false);
  });

  it('should include occurredAt timestamp', () => {
    const error = { code: 'ERR_NETWORK' };
    const result = storeFailure(error, true);
    expect(result.occurredAt).toBe('2025-01-01T00:00:00.000Z');
  });

  it('should generate local reference when no server reference', () => {
    const error = { code: 'ERR_NETWORK' };
    const result = storeFailure(error, true);
    expect(result.reference).toMatch(/^LOCAL-/);
    expect(result.reference.length).toBeGreaterThan(7);
  });
});

describe('isStoreConfiguration', () => {
  const validConfig = {
    settings: {
      features: { analytics: true },
      navigation: [],
      payments: [],
    },
    theme: { id: 'test' },
    home: { sections: [] },
    categories: [],
    brands: [],
  };

  it('should return true for valid configuration', () => {
    expect(isStoreConfiguration(validConfig)).toBe(true);
  });

  it('should return false for null', () => {
    expect(isStoreConfiguration(null)).toBe(false);
  });

  it('should return false for undefined', () => {
    expect(isStoreConfiguration(undefined)).toBe(false);
  });

  it('should return false for non-object', () => {
    expect(isStoreConfiguration('string')).toBe(false);
    expect(isStoreConfiguration(123)).toBe(false);
    expect(isStoreConfiguration(true)).toBe(false);
  });

  it('should return false for missing settings', () => {
    const config = { ...validConfig };
    delete config.settings;
    expect(isStoreConfiguration(config)).toBe(false);
  });

  it('should return false for missing settings.features', () => {
    const config = { ...validConfig, settings: {} };
    expect(isStoreConfiguration(config)).toBe(false);
  });

  it('should return false for non-object settings.features', () => {
    const config = { ...validConfig, settings: { features: null } };
    expect(isStoreConfiguration(config)).toBe(false);
  });

  it('should return false for missing theme', () => {
    const config = { ...validConfig };
    delete config.theme;
    expect(isStoreConfiguration(config)).toBe(false);
  });

  it('should return false for non-object theme', () => {
    const config = { ...validConfig, theme: null };
    expect(isStoreConfiguration(config)).toBe(false);
  });

  it('should return false for missing home', () => {
    const config = { ...validConfig };
    delete config.home;
    expect(isStoreConfiguration(config)).toBe(false);
  });

  it('should return false for non-array home.sections', () => {
    const config = { ...validConfig, home: { sections: null } };
    expect(isStoreConfiguration(config)).toBe(false);
  });

  it('should return false for missing categories', () => {
    const config = { ...validConfig };
    delete config.categories;
    expect(isStoreConfiguration(config)).toBe(false);
  });

  it('should return false for non-array categories', () => {
    const config = { ...validConfig, categories: null };
    expect(isStoreConfiguration(config)).toBe(false);
  });

  it('should return false for missing brands', () => {
    const config = { ...validConfig };
    delete config.brands;
    expect(isStoreConfiguration(config)).toBe(false);
  });

  it('should return false for non-array brands', () => {
    const config = { ...validConfig, brands: null };
    expect(isStoreConfiguration(config)).toBe(false);
  });

  it('should return false for missing settings.navigation', () => {
    const config = { ...validConfig, settings: { features: {}, payments: [] } };
    expect(isStoreConfiguration(config)).toBe(false);
  });

  it('should return false for non-array settings.navigation', () => {
    const config = { ...validConfig, settings: { ...validConfig.settings, navigation: null } };
    expect(isStoreConfiguration(config)).toBe(false);
  });

  it('should return false for missing settings.payments', () => {
    const config = { ...validConfig, settings: { features: {}, navigation: [] } };
    expect(isStoreConfiguration(config)).toBe(false);
  });

  it('should return false for non-array settings.payments', () => {
    const config = { ...validConfig, settings: { ...validConfig.settings, payments: null } };
    expect(isStoreConfiguration(config)).toBe(false);
  });
});

describe('API interceptor prevention', () => {
  it('should prevent requests when API_CONFIGURATION_ERROR is set', async () => {
    // Save original env
    const originalEnv = process.env.REACT_APP_BACKEND_URL;
    
    // Set invalid URL to trigger configuration error
    process.env.REACT_APP_BACKEND_URL = 'invalid-url';
    
    // Reset modules to reload api.ts with new env
    jest.resetModules();
    
    // Import fresh api module
    const { api, API_CONFIGURATION_ERROR } = require('./api');
    
    // Verify configuration error is set
    expect(API_CONFIGURATION_ERROR).toBeTruthy();
    expect(API_CONFIGURATION_ERROR).toContain('not configured');
    
    // Create a spy on the axios adapter to verify it's never called
    const adapterSpy = jest.fn();
    api.defaults.adapter = adapterSpy;
    
    // Attempt to make a request
    try {
      await api.get('/test');
      fail('Request should have been rejected');
    } catch (error: any) {
      // Verify the error is ERR_API_CONFIGURATION
      expect(error.code).toBe('ERR_API_CONFIGURATION');
      expect(error.message).toContain('not configured');
      
      // Verify the adapter was NEVER called (request intercepted before network)
      expect(adapterSpy).not.toHaveBeenCalled();
    }
    
    // Restore original env
    process.env.REACT_APP_BACKEND_URL = originalEnv;
    jest.resetModules();
  });
  
  it('should allow requests when API configuration is valid', async () => {
    // Set valid URL
    process.env.REACT_APP_BACKEND_URL = 'https://example.com';
    
    // Reset modules
    jest.resetModules();
    
    // Import fresh api module
    const { api, API_CONFIGURATION_ERROR } = require('./api');
    
    // Verify no configuration error
    expect(API_CONFIGURATION_ERROR).toBe('');
    
    // Mock adapter to simulate successful request
    const mockAdapter = jest.fn().mockResolvedValue({
      data: { test: 'data' },
      status: 200,
      statusText: 'OK',
      headers: {},
      config: {},
    });
    
    api.defaults.adapter = mockAdapter;
    
    // Make request
    const response = await api.get('/test');
    
    // Verify adapter was called (request not intercepted)
    expect(mockAdapter).toHaveBeenCalled();
    expect(response.data).toEqual({ test: 'data' });
    
    jest.resetModules();
  });
});
