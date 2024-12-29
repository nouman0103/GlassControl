const { app, BrowserWindow, ipcMain, powerMonitor} = require('electron');
const path = require('path');
let mainWindow;

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
    mainWindow.loadURL('http://localhost:8000/main.html');
    windowVisible = false;
    // Listen for toggle events from Python
    ipcMain.on('toggle-visibility', () => {        
        try {
            if (windowVisible) {
                mainWindow.hide();
                windowVisible = false;
            } else {
                mainWindow.show();
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
    windowDestroyed = false;
    // Power monitor events
    powerMonitor.on('suspend', () => {
        if (mainWindow) {
            mainWindow.destroy();
            windowDestroyed = true;
        }
    });

});

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
        app.quit();
    }
});


if (process.platform === 'win32')
{
    app.setAppUserModelId(app.name);
}