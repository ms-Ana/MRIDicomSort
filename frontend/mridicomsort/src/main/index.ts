import { app, BrowserWindow, ipcMain, dialog } from 'electron'
import { spawn } from 'child_process'
import path from 'path'

let pythonProcess: ReturnType<typeof spawn> | null = null

ipcMain.handle('dialog:openDirectory', async () => {
  const { canceled, filePaths } = await dialog.showOpenDialog({
    properties: ['openDirectory']
  })
  
  if (canceled) {
    return null
  } else {
    return filePaths[0] // Return the selected absolute path string
  }
})

ipcMain.handle('dialog:saveFile', async () => {
  const { canceled, filePath } = await dialog.showSaveDialog({
    title: 'Save DICOM Metadata CSV',
    defaultPath: 'dicom_metadata.csv',
    filters: [
      { name: 'CSV Files', extensions: ['csv'] },
      { name: 'All Files', extensions: ['*'] }
    ]
  })
  
  if (canceled) {
    return null
  } else {
    return filePath // Returns the absolute path where the user wants to save
  }
})

function startPythonBackend() {
  let backendPath;

  if (app.isPackaged) {
    backendPath = path.join(process.resourcesPath, 'python-backend', 'main')
  } else {
    backendPath = path.join(__dirname, '../../../../backend/dist/main/main')
  }

  console.log('Starting Python backend at:', backendPath)

  // Start the Python process
  pythonProcess = spawn(backendPath)

  pythonProcess.stdout.on('data', (data) => {
    console.log(`[Python]: ${data}`)
  })

  pythonProcess.stderr.on('data', (data) => {
    console.error(`[Python Error]: ${data}`)
  })
}

app.whenReady().then(() => {
  startPythonBackend()
  
  // Create your Vue window
  const mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    webPreferences: {
      preload: path.join(__dirname, '../preload/index.js'),
      nodeIntegration: false,
      contextIsolation: true
    }
  })
  
  // Load Vue
  mainWindow.loadURL('http://localhost:5173') // Dev URL
})

// CRITICAL: Kill the Python server when Electron closes
app.on('will-quit', () => {
  if (pythonProcess) {
    pythonProcess.kill()
  }
})