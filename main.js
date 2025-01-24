const { app, BrowserWindow, ipcMain, powerMonitor} = require('electron');
const path = require('path');
let mainWindow;

// Ensure single instance
const gotTheLock = app.requestSingleInstanceLock();

if (!gotTheLock) {
    // If we don't get the lock, quit immediately
    app.quit();
} else {
    app.on('ready', () => {
        mainWindow = new BrowserWindow({
            width: 800,
            height: 770,
            webPreferences: {
            preload: path.join(__dirname, 'preload.js'),  // Use preload script
            contextIsolation: true,  // Enable contextIsolation for security
            nodeIntegration: false  // Disable nodeIntegration for security
            },
            show: false,
            icon: __dirname + '/web/cmf.png',
        });
        mainWindow.setMenuBarVisibility(false)
        //mainWindow.loadFile('web/main.html'); // Adjust path if necessary
        mainWindow.loadURL('http://localhost:7999/main.html');
        windowVisible = false;
        // Listen for toggle events from Python
        ipcMain.on('toggle-visibility', () => {        
            try {
                if (windowVisible) {
                    mainWindow.hide();
                    windowVisible = false;
                } else {
                    mainWindow.show();
                    mainWindow.setAlwaysOnTop(true); // Force window to top
                    mainWindow.focus();
                    mainWindow.moveTop(); // Move to front of z-order
                    mainWindow.setAlwaysOnTop(false); // Reset always on top
                    windowVisible = true;
                }
            } catch (error) {
                console.error('Error toggling window visibility:', error);
            }
        });

        

        ipcMain.on("exit", () => {
            app.quit();
        });

        ipcMain.on("minimize", () => {
            mainWindow.minimize();
        });


        

        mainWindow.on('close', (event) => {
            event.preventDefault();  // Prevent the default close behavior
            mainWindow.hide();  // Hide the window
            windowVisible = false;
        });

        mainWindow.setTitle("GlassControl");
        // Power monitor events
        powerMonitor.on('suspend', () => {
            if (mainWindow) {
                mainWindow.destroy();
            }
        });

    });

    app.on('window-all-closed', () => {
        if (process.platform !== 'darwin') {
            app.quit();
        }
    });

    setInterval(async () => {
        try {
            const response = await Promise.race([
                mainWindow.webContents.executeJavaScript('electronPing()'),
                new Promise((_, reject) => setTimeout(() => reject('timeout'), 2000))
            ]);
            
            if (!response || response !== 'pong') {
                console.log('No response from renderer');
                destroyWindow();
            }
        } catch (error) {
            console.error('Error pinging renderer:', error);
            destroyWindow();
        }
    }, 3000);

    setInterval(() => {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 2000);
      
        fetch("http://localhost:7999", { signal: controller.signal })
          .then(res => {
            clearTimeout(timeoutId);
            // 404 means eel is still available
          })
          .catch(() => {
            // Timeout or network error => eel is unavailable
            if (mainWindow) {
                destroyWindow();
            }
          });
      }, 3000);
}

function destroyWindow() {
    if (mainWindow) {
        mainWindow.destroy(); // Force close the window
        mainWindow = null;
        app.quit(); // Quit the application completely
    }
}


if (process.platform === 'win32')
{
    app.setAppUserModelId(app.name);
}