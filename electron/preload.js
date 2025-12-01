const { contextBridge } = require('electron');

/**
 * Preload script for secure context bridge between main and renderer process.
 * Only exposes safe, read-only configuration to the renderer.
 */

// CRITICAL: Use localhost (not 127.0.0.1) to match frontend origin for cookie sharing
// Frontend is at localhost:5173, so backend must also be localhost for same-origin cookies
const BACKEND_URL = 'http://localhost:8000';

contextBridge.exposeInMainWorld('electronAPI', {
    /**
     * Get the backend API base URL
     * @returns {string} The backend URL
     */
    getBackendUrl: () => BACKEND_URL,

    /**
     * Get application environment info
     * @returns {object} Environment information
     */
    getEnvInfo: () => ({
        platform: process.platform,
        isPackaged: process.env.NODE_ENV === 'production'
    })
});
