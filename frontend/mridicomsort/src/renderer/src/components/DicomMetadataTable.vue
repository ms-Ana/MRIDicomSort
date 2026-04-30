<template>
  <div class="excel-table-container">
    <table>
      <thead>
        <tr>
          <!-- Dynamically generate headers based on the keys of the first data object -->
          <th v-for="col in columns" :key="col">{{ formatHeader(col) }}</th>
        </tr>
      </thead>
      <tbody>
        <tr 
          v-for="(row, index) in data" 
          :key="index" 
          :class="getRowClass(row.Status)"
        >
          <td v-for="col in columns" :key="col">
            <!-- Special rule to just show the folder name instead of the huge absolute path -->
            <template v-if="col === 'DirectoryPath'">
              {{ row[col].split(/[/\\]/).pop() }}
            </template>
            <template v-else>
              {{ row[col] }}
            </template>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  data: {
    type: Array,
    required: true,
    default: () => []
  }
})

// Dynamically extract column headers from the first item in the array
const columns = computed(() => {
  if (props.data.length === 0) return []
  return Object.keys(props.data[0])
})

// Adds spaces to CamelCase words for better readability (e.g. "PatientID" -> "Patient ID")
const formatHeader = (text) => {
  return text.replace(/([A-Z])/g, ' $1').trim()
}

// Map the status to our professional color classes
const getRowClass = (status) => {
  if (status === 'ok') return 'row-success'
  if (status && status.includes('check')) return 'row-warning'
  if (status === 'error') return 'row-error'
  return ''
}
</script>

<style scoped>
.excel-table-container {
  max-height: 500px; /* Fixed max size */
  overflow: auto; /* Scrollable in both directions */
  border: 1px solid var(--border-color);
  border-radius: 4px;
  background: var(--surface-color);
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  white-space: nowrap; /* Keep it looking like Excel */
}

th, td {
  border: 1px solid var(--border-color);
  padding: 8px 12px;
  text-align: left;
}

th {
  background-color: var(--table-header-bg);
  color: var(--text-main);
  position: sticky;
  top: 0;
  z-index: 2;
  font-weight: 600;
  box-shadow: 0 1px 0 var(--border-color); /* Prevents scroll bleed under sticky header */
}

/* Status Row Colors (Professional Palette) */
.row-success { background-color: #ecfdf5; color: #065f46; } /* Soft Mint Green */
.row-warning { background-color: #fffbeb; color: #92400e; } /* Soft Amber/Orange */
.row-error { background-color: #fef2f2; color: #991b1b; }   /* Soft Rose/Red */

/* Subtle hover effect for rows */
tbody tr:hover {
  filter: brightness(0.97);
}
</style>