const { contextBridge, ipcRenderer } = require('electron');

// Expose the toggleVisibility function to the renderer process safely
contextBridge.exposeInMainWorld('electron', {
    toggleVisibility: (action) => ipcRenderer.send('toggle-visibility', action)
});
