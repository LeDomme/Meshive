<script setup lang="ts">
import { onMounted, ref } from "vue"
import { apiRequest } from "../../api"
import AdminHeader from "../../components/AdminHeader.vue"

const diagnostics = ref<Record<string, unknown> | null>(null)
const errorMessage = ref("")

async function load() {
  errorMessage.value = ""
  try {
    diagnostics.value = await apiRequest<Record<string, unknown>>("/api/admin/diagnostics")
  } catch {
    errorMessage.value = "Diagnostics could not be loaded."
  }
}

onMounted(load)
</script>

<template>
  <main class="admin-shell">
    <AdminHeader title="Diagnostics" />
    <section class="admin-content">
      <div class="panel-heading">
        <div>
          <p class="eyebrow">System status</p>
          <h2>Diagnostics</h2>
          <p class="panel-copy">Lightweight status checks only; no library or cache traversal is performed.</p>
        </div>
        <button class="secondary-button" type="button" @click="load">Refresh</button>
      </div>
      <p v-if="errorMessage" class="error-message">{{ errorMessage }}</p>
      <pre v-else-if="diagnostics" class="diagnostics-output">{{ JSON.stringify(diagnostics, null, 2) }}</pre>
      <p v-else class="muted">Loading diagnostics…</p>
    </section>
  </main>
</template>
