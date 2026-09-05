<script setup lang="ts">
import AccountMenu from "../components/AccountMenu.vue"
</script>

<template>
  <main class="status-page">
    <header class="status-page-header">
      <h1>Access denied</h1>
      <AccountMenu />
    </header>
    <p class="muted">
      Your account does not have permission to view the catalogue.
    </p>
  </main>
</template>
