const { app, BrowserWindow } = require('electron');
const path = require('path');
const { spawn } = require('child_process');

let pythonProcess;

function startPython() {
    const isDev = !app.isPackaged;
    // In Dev: Run python script. In Prod: Run the compiled .exe
    const exePath = isDev
        ? 'python'
        : path.join(process.resourcesPath, 'backend_dist', 'api.exe');

    const args = isDev ? ['backend/api.py'] : [];
    console.log(`Starting Python process: ${exePath} ${args.join(' ')}`);

    pythonProcess = spawn(exePath, args);

    pythonProcess.stdout.on('data', (data) => {
        console.log(`Python stdout: ${data}`);
    });

    pythonProcess.stderr.on('data', (data) => {
        console.error(`Python stderr: ${data}`);
    });
}

function createWindow() {
    const win = new BrowserWindow({
        width: 1280,
        height: 900,
        webPreferences: {
            nodeIntegration: true,
            contextIsolation: false // Simplified for local tool; consider enabling for security in public apps
        }
    });

    // In Dev: Load local Vite server. In Prod: Load built files.
    const isDev = !app.isPackaged;
    const startUrl = isDev
        ? 'http://localhost:5173'
        : `file://${path.join(__dirname, '../dist/index.html')}`;

    console.log(`Loading URL: ${startUrl}`);
    win.loadURL(startUrl);

    // Open DevTools and log console messages to terminal
    win.webContents.openDevTools();
    win.webContents.on('console-message', (event, level, message, line, sourceId) => {
        console.log(`[Console]: ${message} (${sourceId}:${line})`);
    });
}

app.whenReady().then(() => {
    startPython();
    createWindow();
});

app.on('will-quit', () => {
    if (pythonProcess) {
        console.log('Killing Python process...');
        pythonProcess.kill();
    }
});

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
        app.quit();
    }
});