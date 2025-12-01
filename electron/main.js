const { app, BrowserWindow } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const http = require('http');

const BACKEND_URL = 'http://127.0.0.1:8000';
const BACKEND_HEALTH_ENDPOINT = '/api/v1/';

let pythonProcess;
let mainWindow;

/**
 * Wait for backend to be ready before loading UI
 * @param {number} maxRetries - Maximum number of retry attempts
 * @param {number} delayMs - Delay between retries in milliseconds
 * @returns {Promise<boolean>} - True if backend is ready
 */
async function waitForBackend(maxRetries = 30, delayMs = 500) {
    for (let i = 0; i < maxRetries; i++) {
        try {
            const isReady = await new Promise((resolve) => {
                const req = http.get(`${BACKEND_URL}${BACKEND_HEALTH_ENDPOINT}`, (res) => {
                    resolve(res.statusCode === 200);
                });
                req.on('error', () => resolve(false));
                req.setTimeout(2000, () => {
                    req.destroy();
                    resolve(false);
                });
            });

            if (isReady) {
                console.log(`Backend ready after ${i + 1} attempts`);
                return true;
            }
        } catch (error) {
            // Ignore errors, retry
        }

        if (i < maxRetries - 1) {
            console.log(`Waiting for backend... attempt ${i + 1}/${maxRetries}`);
            await new Promise(resolve => setTimeout(resolve, delayMs));
        }
    }

    console.error('Backend failed to start within timeout');
    return false;
}

function startPython() {
    if (!app.isPackaged) {
        console.log('In development mode: Skipping Python spawn (assume running separately)');
        return;
    }

    const exePath = path.join(process.resourcesPath, 'backend_dist', 'api.exe');
    const args = [];
    console.log(`Starting Python process: ${exePath}`);

    pythonProcess = spawn(exePath, args);

    pythonProcess.stdout.on('data', (data) => {
        console.log(`Python stdout: ${data}`);
    });

    pythonProcess.stderr.on('data', (data) => {
        console.error(`Python stderr: ${data}`);
    });

    pythonProcess.on('error', (error) => {
        console.error(`Failed to start Python process: ${error.message}`);
    });

    pythonProcess.on('exit', (code, signal) => {
        console.log(`Python process exited with code ${code}, signal ${signal}`);
        pythonProcess = null;
    });
}

function createWindow() {
    mainWindow = new BrowserWindow({
        width: 1280,
        height: 900,
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
            preload: path.join(__dirname, 'preload.js')
        }
    });

    const isDev = !app.isPackaged;
    const startUrl = isDev
        ? 'http://localhost:5173'
        : `file://${path.join(__dirname, '../dist/index.html')}`;

    console.log(`Loading URL: ${startUrl}`);
    mainWindow.loadURL(startUrl);

    // Log console messages to terminal
    mainWindow.webContents.on('console-message', (event, level, message, line, sourceId) => {
        console.log(`[Console]: ${message} (${sourceId}:${line})`);
    });

    mainWindow.on('closed', () => {
        mainWindow = null;
    });
}

/**
 * Gracefully kill Python process with fallback to SIGKILL
 */
function killPythonProcess() {
    if (!pythonProcess) return;

    console.log('Killing Python process...');

    // First try graceful termination
    pythonProcess.kill('SIGTERM');

    // Force kill after 5 seconds if still running
    const forceKillTimeout = setTimeout(() => {
        if (pythonProcess && !pythonProcess.killed) {
            console.log('Force killing Python process...');
            pythonProcess.kill('SIGKILL');
        }
    }, 5000);

    pythonProcess.on('exit', () => {
        clearTimeout(forceKillTimeout);
    });
}

// Main startup sequence
app.whenReady().then(async () => {
    startPython();

    // Wait for backend to be ready (skip in dev mode if backend runs separately)
    const isDev = !app.isPackaged;
    if (!isDev) {
        const backendReady = await waitForBackend();
        if (!backendReady) {
            console.error('Cannot start application: backend not available');
            app.quit();
            return;
        }
    }

    createWindow();
});

app.on('will-quit', () => {
    killPythonProcess();
});

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
        app.quit();
    }
});

// Handle crashes - ensure Python process is cleaned up
process.on('uncaughtException', (error) => {
    console.error('Uncaught exception:', error);
    killPythonProcess();
    app.quit();
});

process.on('unhandledRejection', (reason, promise) => {
    console.error('Unhandled rejection at:', promise, 'reason:', reason);
});
