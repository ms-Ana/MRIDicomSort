<template>
  <div class="start-page">
    <header class="page-header">
      <h1>MRI Sorting Dashboard</h1>
      <p>Manage and extract metadata from your MRI DICOM series.</p>
    </header>

    <main class="page-content">
      <DicomExtractor />
    </main>
  </div>
</template>

<script setup>
import DicomExtractor from '../components/DicomExtractor.vue'
</script>

<style scoped>
.start-page {
  min-height: 100vh;
  background-color: #f8f9fa; /* Light, neutral background for the whole page */
  padding: 2rem;
  font-family: system-ui, -apple-system, sans-serif;
}

.page-header {
  max-width: 1200px;
  margin: 0 auto 2rem auto;
  text-align: center;
}

.page-header h1 {
  color: #2c3e50;
  margin-bottom: 0.5rem;
  font-size: 2.2rem;
  font-weight: 700;
}

.page-header p {
  color: #6c757d;
  font-size: 1.1rem;
  margin: 0;
}

.page-content {
  max-width: 1200px;
  margin: 0 auto;
}
</style>