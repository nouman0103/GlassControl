const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');
let mainWindow;

app.on('ready', () => {
    mainWindow = new BrowserWindow({
        width: 800,
        height: 750,
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

    // Listen for toggle events from Python
    ipcMain.on('toggle-visibility', (_, action) => {
        if (action === 'hide') {
            mainWindow.hide();
        } else if (action === 'show') {
            mainWindow.show();
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
  });

    mainWindow.setTitle("GlassControl");
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