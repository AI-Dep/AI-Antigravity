/**
 * Centralized API client with timeout, retry, and error handling.
 * All components should use this client instead of direct axios/fetch calls.
 *
 * SCALABILITY: Uses client-side session ID generation to ensure:
 * - Consistent session across all requests (no race conditions)
 * - Works with load balancing (all requests have same session ID)
 * - Session persists across page refreshes (localStorage)
 */
import axios from 'axios';

// API base URL - detect environment and use appropriate URL
const getBaseUrl = () => {
    // 1. Electron mode - use electronAPI
    if (typeof window !== 'undefined' && window.electronAPI?.getBackendUrl) {
        return window.electronAPI.getBackendUrl();
    }

    // 2. Environment variable override
    if (import.meta.env.VITE_API_URL) {
        return import.meta.env.VITE_API_URL;
    }

    // 3. Web deployment mode - use relative /api/ path (nginx proxies to backend)
    // Detect if running in production web mode (not localhost dev server)
    if (typeof window !== 'undefined') {
        const isLocalDev = window.location.hostname === 'localhost' && window.location.port === '5173';
        if (!isLocalDev) {
            // Production web mode - use relative path for nginx proxy
            return '/api';
        }
    }

    // 4. Local development - direct backend connection
    return 'http://localhost:8000';
};

export const API_BASE = getBaseUrl();

// Default timeout for API requests (30 seconds)
const DEFAULT_TIMEOUT = 30000;

// Maximum retry attempts for failed requests
const MAX_RETRIES = 2;

// Delay between retries (in ms)
const RETRY_DELAY = 1000;

// HTTP status codes that should trigger a retry
const RETRYABLE_STATUS_CODES = [408, 429, 500, 502, 503, 504];

// Storage key for session ID persistence
const SESSION_STORAGE_KEY = 'fa_cs_session_id';

// ==============================================================================
// CLIENT-SIDE SESSION ID GENERATION (Scalability Feature)
// ==============================================================================

/**
 * Generate a UUID v4 for session identification.
 * This ensures unique session IDs without server round-trip.
 * @returns {string} UUID v4 string
 */
const generateUUID = () => {
    // Use crypto.randomUUID if available (modern browsers)
    if (typeof crypto !== 'undefined' && crypto.randomUUID) {
        return crypto.randomUUID();
    }
    // Fallback for older browsers
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
        const r = Math.random() * 16 | 0;
        const v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
};

/**
 * Get or create session ID.
 * - First checks memory (fastest)
 * - Then checks localStorage (persists across refreshes)
 * - Finally generates new UUID if needed
 * @returns {string} Session ID
 */
const getOrCreateSessionId = () => {
    // Check memory first (already initialized)
    if (_sessionId) {
        return _sessionId;
    }

    // Check localStorage for existing session (persists across page refreshes)
    if (typeof localStorage !== 'undefined') {
        const stored = localStorage.getItem(SESSION_STORAGE_KEY);
        if (stored) {
            _sessionId = stored;
            return _sessionId;
        }
    }

    // Generate new session ID (client-side - no server round-trip needed)
    _sessionId = generateUUID();

    // Persist to localStorage
    if (typeof localStorage !== 'undefined') {
        try {
            localStorage.setItem(SESSION_STORAGE_KEY, _sessionId);
        } catch (e) {
            // localStorage might be full or disabled - continue without persistence
            console.warn('Could not persist session ID to localStorage:', e);
        }
    }

    console.log(`[Session] Generated new session ID: ${_sessionId.substring(0, 8)}...`);
    return _sessionId;
};

// Session ID storage - initialized immediately to avoid race conditions
let _sessionId = null;

// Initialize session ID immediately on module load
// This ensures all requests have a session ID from the start
if (typeof window !== 'undefined') {
    _sessionId = getOrCreateSessionId();
}

/**
 * Get the current session ID
 * @returns {string} Current session ID
 */
export const getSessionId = () => {
    if (!_sessionId) {
        _sessionId = getOrCreateSessionId();
    }
    return _sessionId;
};

/**
 * Clear the session (for logout, starting fresh, etc.)
 * Removes from both memory and localStorage.
 */
export const clearSession = () => {
    _sessionId = null;
    if (typeof localStorage !== 'undefined') {
        try {
            localStorage.removeItem(SESSION_STORAGE_KEY);
        } catch (e) {
            // Ignore localStorage errors
        }
    }
    console.log('[Session] Session cleared');
};

/**
 * Force new session (for testing or user-requested reset)
 * Generates a new session ID and persists it.
 * @returns {string} New session ID
 */
export const newSession = () => {
    clearSession();
    _sessionId = generateUUID();
    if (typeof localStorage !== 'undefined') {
        try {
            localStorage.setItem(SESSION_STORAGE_KEY, _sessionId);
        } catch (e) {
            // Ignore localStorage errors
        }
    }
    console.log(`[Session] Created new session: ${_sessionId.substring(0, 8)}...`);
    return _sessionId;
};

// ==============================================================================
// AXIOS CLIENT CONFIGURATION
// ==============================================================================

/**
 * Create axios instance with default configuration
 */
export const apiClient = axios.create({
    baseURL: API_BASE,
    timeout: DEFAULT_TIMEOUT,
    withCredentials: true, // Also keep cookies as backup
    headers: {
        'Content-Type': 'application/json'
    }
});

/**
 * Sleep helper for retry delays
 * @param {number} ms - Milliseconds to sleep
 */
const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

/**
 * Check if an error is retryable
 * @param {Error} error - Axios error
 * @returns {boolean} - Whether the request should be retried
 */
const isRetryable = (error) => {
    // Network errors (no response)
    if (!error.response) {
        return true;
    }

    // Specific HTTP status codes
    if (RETRYABLE_STATUS_CODES.includes(error.response.status)) {
        return true;
    }

    return false;
};

/**
 * Request interceptor to add session ID header
 * CRITICAL: This runs BEFORE every request, ensuring session ID is always sent.
 */
apiClient.interceptors.request.use(
    (config) => {
        // Always include session ID - generated client-side, always available
        const sessionId = getSessionId();
        config.headers['X-Session-ID'] = sessionId;
        return config;
    },
    (error) => Promise.reject(error)
);

/**
 * Response interceptor for retry logic and session sync
 */
apiClient.interceptors.response.use(
    (response) => {
        // Sync session ID from server response (in case server needs to override)
        // This handles edge cases like session migration or server-side session management
        const serverSessionId = response.headers['x-session-id'];
        if (serverSessionId && serverSessionId !== _sessionId) {
            // Server returned different session ID - sync to it
            // This can happen if server migrated the session or has authoritative session management
            console.log(`[Session] Syncing to server session: ${serverSessionId.substring(0, 8)}...`);
            _sessionId = serverSessionId;
            if (typeof localStorage !== 'undefined') {
                try {
                    localStorage.setItem(SESSION_STORAGE_KEY, serverSessionId);
                } catch (e) {
                    // Ignore localStorage errors
                }
            }
        }
        return response;
    },
    async (error) => {
        const config = error.config;

        // Initialize retry count
        if (!config.__retryCount) {
            config.__retryCount = 0;
        }

        // Check if we should retry
        if (config.__retryCount < MAX_RETRIES && isRetryable(error)) {
            config.__retryCount += 1;

            console.warn(
                `API request failed, retrying (${config.__retryCount}/${MAX_RETRIES}):`,
                config.url
            );

            // Wait before retrying
            await sleep(RETRY_DELAY * config.__retryCount);

            return apiClient(config);
        }

        // Format error for consistent handling
        const formattedError = {
            message: error.response?.data?.message || error.message || 'Unknown error',
            code: error.response?.data?.error || 'NETWORK_ERROR',
            status: error.response?.status || 0,
            details: error.response?.data?.details || null
        };

        return Promise.reject(formattedError);
    }
);

// ==============================================================================
// API HELPER FUNCTIONS
// ==============================================================================

/**
 * GET request helper
 * @param {string} url - Endpoint URL
 * @param {object} config - Optional axios config
 * @returns {Promise} - Response data
 */
export const apiGet = async (url, config = {}) => {
    const response = await apiClient.get(url, config);
    return response.data;
};

/**
 * POST request helper
 * @param {string} url - Endpoint URL
 * @param {object} data - Request body
 * @param {object} config - Optional axios config
 * @returns {Promise} - Response data
 */
export const apiPost = async (url, data = {}, config = {}) => {
    const response = await apiClient.post(url, data, config);
    return response.data;
};

/**
 * DELETE request helper
 * @param {string} url - Endpoint URL
 * @param {object} config - Optional axios config
 * @returns {Promise} - Response data
 */
export const apiDelete = async (url, config = {}) => {
    const response = await apiClient.delete(url, config);
    return response.data;
};

/**
 * Upload file helper with progress tracking
 * @param {string} url - Endpoint URL
 * @param {FormData} formData - Form data with file
 * @param {function} onProgress - Progress callback (0-100)
 * @returns {Promise} - Response data
 */
export const apiUpload = async (url, formData, onProgress = null) => {
    const response = await apiClient.post(url, formData, {
        headers: {
            'Content-Type': 'multipart/form-data'
        },
        timeout: 120000, // 2 minute timeout for uploads
        onUploadProgress: (progressEvent) => {
            if (onProgress && progressEvent.total) {
                const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
                onProgress(percent);
            }
        }
    });
    return response.data;
};

/**
 * Download file helper
 * @param {string} url - Endpoint URL
 * @returns {Promise<Blob>} - File blob
 */
export const apiDownload = async (url) => {
    const response = await apiClient.get(url, {
        responseType: 'blob',
        timeout: 120000 // 2 minute timeout for downloads
    });
    return response.data;
};

export default apiClient;
