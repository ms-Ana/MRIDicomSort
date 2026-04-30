import { contextBridge, ipcRenderer } from 'electron'

// Custom APIs for renderer
const api = {
  selectFolder: () => ipcRenderer.invoke('dialog:openDirectory'),
  saveFile: () => ipcRenderer.invoke('dialog:saveFile')
}

// Use `contextBridge` APIs to expose Electron APIs to
// renderer only if context isolation is enabled, otherwise
// just add to the DOM global.
if (process.contextIsolated) {
  try {
    // Expose only your custom api
    contextBridge.exposeInMainWorld('api', api)
  } catch (error) {
    console.error(error)
  }
} else {
  // @ts-ignore (define in dts)
  window.api = api
}