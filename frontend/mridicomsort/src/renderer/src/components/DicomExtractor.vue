<template>
  <div class="dicom-extractor">
    <div class="card">
      <h2 class="section-title">DICOM Extraction Pipeline</h2>
      
      <!-- Input: Directory to Process -->
      <div class="form-group">
        <label>Input Directory (Root):</label>
        <p class="helper-text">Select the folder containing your MRI DICOM series.</p>
        <div class="picker-layout">
          <button @click="chooseFolder" class="btn-secondary" :disabled="isProcessing">
            📁 Browse Folder
          </button>
          <div class="path-display" :class="{ 'has-path': rootDir }">
            {{ rootDir || 'No input folder selected...' }}
          </div>
        </div>
      </div>

      <!-- Output: Save File Location -->
      <div class="form-group">
        <label>Output CSV Location:</label>
        <p class="helper-text">Choose where to save the generated metadata report.</p>
        <div class="picker-layout">
          <button @click="chooseSaveFile" class="btn-secondary" :disabled="isProcessing">
            💾 Choose Save Location
          </button>
          <div class="path-display" :class="{ 'has-path': outputFile }">
            {{ outputFile || 'No save location selected...' }}
          </div>
        </div>
      </div>

      <!-- Action Button -->
      <div class="action-bar">
        <button @click="startExtraction" class="btn-primary" :disabled="isProcessing || !rootDir || !outputFile">
          {{ isProcessing ? 'Processing Extractor...' : '🚀 Start Extraction' }}
        </button>
      </div>

      <!-- Error Display -->
      <div v-if="errorMessage" class="error-banner">{{ errorMessage }}</div>

      <!-- Enhanced Progress Bar -->
      <div v-if="total > 0" class="progress-section">
        <div class="progress-header">
          <span class="progress-title">Extraction Progress</span>
          <span class="progress-count">{{ completed }} / {{ total }} directories</span>
        </div>
        <progress class="large-progress" :value="completed" :max="total"></progress>
      </div>
    </div>

    <!-- Reusable Table Component (Only shows if there are results) -->
   <div class="card" v-if="results.length > 0">
      <!-- NEW: Table Header with Filter Button -->
      <div class="table-header-container">
        <h3 class="section-title">Extraction Results (Live Preview)</h3>
        <button class="btn-secondary" @click="isFilterModalOpen = true">
          ⚙️ Apply Pre-Filters
        </button>
      </div>
      
      <DicomMetadataTable :data="results" />
    </div>


    <FilterModal 
      :is-open="isFilterModalOpen" 
      :current-data="results"
      @close="isFilterModalOpen = false"
      @filtered="handleFilteredData"
    />


  </div>
</template>

<script setup>
import { ref, onUnmounted } from 'vue'
import DicomMetadataTable from './DicomMetadataTable.vue'
import FilterModal from './FilterModal.vue'

const isFilterModalOpen = ref(false)
const handleFilteredData = (filteredData) => {
  results.value = filteredData
}

const rootDir = ref('')
const outputFile = ref('')

const isProcessing = ref(false)
const total = ref(0)
const completed = ref(0)
const results = ref([])
const errorMessage = ref('')

let eventSource = null

const chooseFolder = async () => {
  const folderPath = await window.api.selectFolder()
  if (folderPath) rootDir.value = folderPath
}

const chooseSaveFile = async () => {
  const filePath = await window.api.saveFile()
  if (filePath) outputFile.value = filePath
}

const startExtraction = () => {
  isProcessing.value = true
  total.value = 0
  completed.value = 0
  results.value = []
  errorMessage.value = ''

  if (eventSource) eventSource.close()

  const baseUrl = 'http://localhost:8000'
  const url = `${baseUrl}/api/extract?root=${encodeURIComponent(rootDir.value)}&output=${encodeURIComponent(outputFile.value)}`

  eventSource = new EventSource(url)

  eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data)

    if (data.status === 'start') {
      total.value = data.total
    } else if (data.status === 'progress') {
      completed.value = data.completed
      results.value.push(data.row)
    } else if (data.status === 'done') {
      isProcessing.value = false
      eventSource.close()
      alert(data.message)
    } else if (data.status === 'error') {
      errorMessage.value = data.message
      isProcessing.value = false
      eventSource.close()
    }
  }

  eventSource.onerror = () => {
    errorMessage.value = "Lost connection to the backend server."
    isProcessing.value = false
    eventSource.close()
  }
}

onUnmounted(() => {
  if (eventSource) eventSource.close()
})
</script>

<style>

:root {
  --primary-color: #2563eb; /* Professional Blue */
  --primary-hover: #1d4ed8;
  --surface-color: #ffffff;
  --bg-color: #f8fafc; /* Very light slate */
  --text-main: #0f172a; /* Dark slate */
  --text-muted: #64748b;
  --border-color: #e2e8f0;
  --table-header-bg: #f1f5f9;
}

body {
  background-color: var(--bg-color);
  color: var(--text-main);
}
</style>

<style scoped>
.dicom-extractor {
  font-family: system-ui, -apple-system, sans-serif;
  max-width: 1400px;
  margin: 0 auto;
}

.card {
  background: var(--surface-color);
  padding: 28px;
  border-radius: 8px;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
  margin-bottom: 24px;
  border: 1px solid var(--border-color);
}

.section-title {
  margin-top: 0;
  color: var(--text-main);
  font-weight: 600;
  margin-bottom: 24px;
}

.form-group {
  margin-bottom: 24px;
}

label {
  display: block;
  margin-bottom: 4px;
  font-weight: 600;
  font-size: 14px;
}

.helper-text {
  font-size: 13px;
  color: var(--text-muted);
  margin-top: 0;
  margin-bottom: 10px;
}

/* Picker Layout */
.picker-layout {
  display: flex;
  align-items: center;
  gap: 12px;
}

.path-display {
  flex-grow: 1;
  padding: 10px 14px;
  background-color: var(--bg-color);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  font-size: 13px;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.path-display.has-path {
  background-color: #f0f9ff;
  border-color: #bae6fd;
  color: #0369a1;
  font-family: monospace;
}

/* Buttons */
.btn-secondary {
  background: var(--surface-color);
  color: #334155;
  border: 1px solid #cbd5e1;
  padding: 10px 16px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.2s;
  white-space: nowrap;
}

.btn-secondary:hover:not(:disabled) {
  background: #f1f5f9;
  border-color: #94a3b8;
}

.action-bar {
  margin-top: 32px;
  padding-top: 24px;
  border-top: 1px solid var(--border-color);
}

.btn-primary {
  background: var(--primary-color);
  color: white;
  border: none;
  padding: 12px 28px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 15px;
  font-weight: 600;
  transition: background 0.2s;
  width: 100%;
}

.btn-primary:hover:not(:disabled) {
  background: var(--primary-hover);
}

.btn-primary:disabled, .btn-secondary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Enhanced Progress Bar */
.progress-section {
  margin-top: 24px;
  background: var(--bg-color);
  padding: 20px;
  border-radius: 8px;
  border: 1px solid var(--border-color);
}

.progress-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 12px;
  font-size: 14px;
  font-weight: 600;
}

.progress-count {
  color: var(--primary-color);
}

.large-progress {
  width: 100%;
  height: 28px; /* Thicker, more professional size */
  border-radius: 6px;
  overflow: hidden;
}

/* Styling the native progress bar for cross-browser consistency */
progress::-webkit-progress-bar { background-color: #e2e8f0; }
progress::-webkit-progress-value { background-color: var(--primary-color); transition: width 0.3s ease; }
progress::-moz-progress-bar { background-color: var(--primary-color); }

.error-banner {
  background-color: #fef2f2;
  color: #991b1b;
  border: 1px solid #fecaca;
  padding: 16px;
  border-radius: 6px;
  margin-top: 20px;
  font-weight: 500;
  font-size: 14px;
}

.table-header-container {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
.table-header-container .section-title {
  margin-bottom: 0; /* Remove bottom margin to align with button */
}

</style>