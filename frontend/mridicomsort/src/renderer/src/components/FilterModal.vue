<template>
  <div v-if="isOpen" class="modal-overlay" @click.self="closeModal">
    <div class="modal-content">
      <header class="modal-header">
        <h2>Configure Pre-Filters</h2>
        <button class="close-btn" @click="closeModal">&times;</button>
      </header>

      <div class="modal-tabs">
        <button :class="{ active: activeTab === 'editor' }" @click="activeTab = 'editor'">YAML Editor</button>
        <button :class="{ active: activeTab === 'instructions' }" @click="activeTab = 'instructions'">Instructions</button>
      </div>

      <div class="modal-body">
        <!-- EDITOR TAB -->
        <div v-if="activeTab === 'editor'" class="tab-content">
          <div class="editor-toolbar">
            <button class="btn-secondary small" @click="loadFromFile">📁 Load Existing .yaml</button>
          </div>
          <!-- Added specific class to guarantee interactivity -->
          <textarea 
            v-model="yamlContent" 
            class="yaml-editor interactive-field" 
            placeholder="Paste or write your YAML configuration here..."
            spellcheck="false"
          ></textarea>
        </div>

        <!-- INSTRUCTIONS TAB -->
        <div v-if="activeTab === 'instructions'" class="tab-content instructions">
          <h3>How to write a Filter Config</h3>
          <p>The configuration uses YAML syntax to define filtering rules. The root key must be <code>PRE-FILTERS:</code>.</p>
          
          <h4>Rule Structure</h4>
          <ul>
            <li><code>parameter</code>: The exact name of the DICOM metadata column.</li>
            <li><code>include</code>: Keeps rows that match these values exactly (or fall within a numeric range).</li>
            <li><code>exclude</code>: Drops rows containing these strings.</li>
          </ul>

          <h4>Numeric Ranges (Min/Max)</h4>
          <pre><code>SLICE_COUNT_FILTER:
  parameter: NumberOfSlices
  include:
    - min: 10
    - max: 500</code></pre>

          <h4>Text Matching</h4>
          <pre><code>IMAGE_TYPE_FILTER:
  parameter: ImageType
  exclude: ["SECONDARY", "COMPOSED", "MIP"]

MODALITY_FILTER:
  parameter: Modality
  include: ["MR"]</code></pre>
        </div>
      </div>

      <footer class="modal-footer">
        <button class="btn-secondary" @click="closeModal">Cancel</button>
        <button class="btn-primary" @click="applyFilter" :disabled="isApplying || !yamlContent">
          {{ isApplying ? 'Applying...' : 'Apply Filters' }}
        </button>
      </footer>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({
  isOpen: Boolean,
  currentData: Array
})

const emit = defineEmits(['close', 'filtered'])

const activeTab = ref('editor')
const yamlContent = ref('PRE-FILTERS:\n  ')
const isApplying = ref(false)

const closeModal = () => {
  emit('close')
}

const loadFromFile = async () => {
  const content = await window.api.openYamlFile()
  if (content) {
    yamlContent.value = content
  }
}

const applyFilter = async () => {
  isApplying.value = true
  try {
    const response = await fetch('http://localhost:8000/api/filter', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        config_yaml: yamlContent.value,
        data: props.currentData
      })
    })

    const result = await response.json()
    
    if (result.error) {
      alert(result.error)
    } else {
      emit('filtered', result.data)
      closeModal()
    }
  } catch (error) {
    alert("Failed to connect to backend: " + error.message)
  } finally {
    isApplying.value = false
  }
}
</script>

<style scoped>
/* --------------------------------------
   BUTTON STYLES (Copied from Main App)
--------------------------------------- */
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

.btn-primary {
  background: var(--primary-color);
  color: white;
  border: none;
  padding: 10px 24px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 15px;
  font-weight: 600;
  transition: background 0.2s;
}

.btn-primary:hover:not(:disabled) {
  background: var(--primary-hover);
}

.btn-primary:disabled, .btn-secondary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.small { 
  padding: 6px 12px; 
  font-size: 13px; 
}

/* --------------------------------------
   MODAL LAYOUT STYLES
--------------------------------------- */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  background: rgba(15, 23, 42, 0.6);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
  backdrop-filter: blur(2px);
}

.modal-content {
  background: var(--surface-color);
  width: 700px;
  max-width: 90vw;
  border-radius: 8px;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.modal-header {
  padding: 16px 24px;
  border-bottom: 1px solid var(--border-color);
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: var(--bg-color);
}

.modal-header h2 {
  margin: 0;
  font-size: 18px;
  color: var(--text-main);
}

.close-btn {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: var(--text-muted);
}

.close-btn:hover { color: var(--text-main); }

.modal-tabs {
  display: flex;
  background: var(--bg-color);
  border-bottom: 1px solid var(--border-color);
  padding: 0 16px;
}

.modal-tabs button {
  background: transparent;
  border: none;
  padding: 12px 16px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-muted);
  cursor: pointer;
  border-bottom: 2px solid transparent;
}

.modal-tabs button.active {
  color: var(--primary-color);
  border-bottom: 2px solid var(--primary-color);
}

.modal-body {
  padding: 20px 24px;
  height: 400px;
  overflow-y: auto;
}

.editor-toolbar { margin-bottom: 12px; }

/* --------------------------------------
   TEXTAREA / EDITOR FIXES
--------------------------------------- */
.yaml-editor {
  width: 100%;
  height: 320px;
  font-family: 'Courier New', Courier, monospace;
  font-size: 14px;
  padding: 12px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background: #f8fafc;
  resize: none;
}

/* 
   CRITICAL: These overrides force Electron/Vue to allow user interaction
   in the text area, overriding any global app-level restrictions.
*/
.interactive-field {
  user-select: text !important;
  -webkit-user-select: text !important;
  -moz-user-select: text !important;
  pointer-events: auto !important;
  -webkit-app-region: no-drag !important;
}

.yaml-editor:focus {
  outline: none;
  border-color: var(--primary-color);
  background: #ffffff;
}

/* --------------------------------------
   INSTRUCTIONS TYPOGRAPHY
--------------------------------------- */
.instructions h3 { margin-top: 0; color: var(--text-main); }
.instructions h4 { margin: 16px 0 8px 0; color: var(--primary-color); }
.instructions pre {
  background: #1e293b;
  color: #f8fafc;
  padding: 12px;
  border-radius: 6px;
  overflow-x: auto;
}
.instructions code { font-family: monospace; }

.modal-footer {
  padding: 16px 24px;
  border-top: 1px solid var(--border-color);
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  background: var(--bg-color);
}
</style>