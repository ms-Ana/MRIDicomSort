<template>
  <div class="excel-table-container" @scroll="onScroll">
    <table>
      <thead>
        <tr>
          <th v-for="col in columns" :key="col">{{ formatHeader(col) }}</th>
        </tr>
      </thead>
      <tbody>
        <!-- TOP SPACER: Pushes the visible rows down so the scrollbar matches your position -->
        <tr v-if="topSpacerHeight > 0" :style="{ height: topSpacerHeight + 'px' }">
          <td :colspan="columns.length" class="spacer-cell"></td>
        </tr>

        <!-- VISIBLE ROWS: We only render the rows currently in the viewport + a small buffer -->
        <tr 
          v-for="row in visibleData" 
          :key="row.DirectoryPath" 
          :class="getRowClass(row)"
        >
          <td v-for="col in columns" :key="col">
            <template v-if="col === 'DirectoryPath'">
              {{ row[col] ? row[col].split(/[/\\]/).pop() : '' }}
            </template>
            <template v-else>
              {{ row[col] }}
            </template>
          </td>
        </tr>

        <!-- BOTTOM SPACER: Creates the illusion of thousands of rows below -->
        <tr v-if="bottomSpacerHeight > 0" :style="{ height: bottomSpacerHeight + 'px' }">
          <td :colspan="columns.length" class="spacer-cell"></td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  data: {
    type: Array,
    required: true,
    default: () => []
  }
})

// --- VIRTUAL SCROLL LOGIC ---
const scrollTop = ref(0)
const rowHeight = 37 // The exact pixel height of one row (padding + font + border)
const containerHeight = 500 // Must match the CSS max-height of the container
const bufferRows = 10 // Render a few invisible rows above/below so scrolling feels smooth

// Update scroll position when user scrolls the div
const onScroll = (event) => {
  scrollTop.value = event.target.scrollTop
}

// Calculate which row index we should start drawing at
const startIndex = computed(() => {
  const start = Math.floor(scrollTop.value / rowHeight) - bufferRows
  return Math.max(0, start) // Never go below index 0
})

// Calculate how many rows fit on screen
const visibleItemCount = computed(() => {
  return Math.ceil(containerHeight / rowHeight) + (bufferRows * 2)
})

// Calculate the last row index we should draw
const endIndex = computed(() => {
  return Math.min(props.data.length, startIndex.value + visibleItemCount.value)
})

// Slice the massive array down to just the ~35 rows we need right now
const visibleData = computed(() => {
  return props.data.slice(startIndex.value, endIndex.value)
})

// Calculate the heights for our invisible spacer blocks
const topSpacerHeight = computed(() => {
  return startIndex.value * rowHeight
})

const bottomSpacerHeight = computed(() => {
  return Math.max(0, (props.data.length - endIndex.value) * rowHeight)
})
// ----------------------------

// Dynamically extract column headers
const columns = computed(() => {
  if (props.data.length === 0) return []
  return Object.keys(props.data[0])
})

const formatHeader = (text) => {
  if (!text) return ''
  return text.replace(/([A-Z])/g, ' $1').trim()
}

const getRowClass = (row) => {
  // 1. If filters have been applied, color based on the 'Action' column
  if (row.Action) {
    if (row.Action === 'include') return 'row-success'     // Green
    if (row.Action === 'check') return 'row-warning'       // Yellow/Orange
    if (row.Action === 'exclude') return 'row-error'       // Red
  }

  // 2. Fallback: Before filtering, color based on the raw 'Status' column
  const status = row.Status
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