/**
 * Centralized API client with timeout, retry, and error handling.
 * All components should use this client instead of direct axios/fetch calls.
 */
import axios from 'axios';

// API base URL - prefer electronAPI if available, then env variable, then default
const getBaseUrl = () => {
    if (typeof window !== 'undefined' && window.electronAPI?.getBackendUrl) {
        return window.electronAPI.getBackendUrl();
    }
    return import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';
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

/**
 * Create axios instance with default configuration
 */
export const apiClient = axios.create({
    baseURL: API_BASE,
    timeout: DEFAULT_TIMEOUT,
    withCredentials: true, // CRITICAL: Include session cookies in requests
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
 * Response interceptor for retry logic
 */
apiClient.interceptors.response.use(
    (response) => response,
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

/**
 * Request interceptor to add session headers
 */
apiClient.interceptors.request.use(
    (config) => {
        // Add session ID from cookie if available
        // The backend handles this via cookies, but we can add headers if needed
        return config;
    },
    (error) => Promise.reject(error)
);

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
