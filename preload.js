const { contextBridge, ipcRenderer } = require('electron');

// Expose the toggleVisibility function to the renderer process safely
contextBridge.exposeInMainWorld('electron', {
    toggleVisibility: () => ipcRenderer.send('toggle-visibility'),
    exit: () => ipcRenderer.send('exit'),
});