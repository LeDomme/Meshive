<script setup lang="ts">
import { RouterLink } from "vue-router"
import AccountMenu from "./AccountMenu.vue"
import BrandLogo from "./BrandLogo.vue"

defineProps<{ title: string }>()
</script>

<template>
  <header class="admin-header">
    <div class="admin-brand">
      <p class="eyebrow">Administration</p>
      <div class="admin-title-row">
        <BrandLogo />
        <h1 class="admin-title">{{ title }}</h1>
      </div>
    </div>
    <nav class="admin-nav" aria-label="Administration">
      <RouterLink class="text-link" to="/">Back to Meshive</RouterLink>
      <RouterLink class="text-link" to="/admin/sources">Library sources</RouterLink>
      <RouterLink class="text-link" to="/admin/metadata">Metadata</RouterLink>
      <RouterLink class="text-link" to="/admin/tags">Tags</RouterLink>
      <RouterLink class="text-link" to="/admin/users">Users</RouterLink>
      <RouterLink class="text-link" to="/admin/backups">Backups</RouterLink>
      <AccountMenu />
    </nav>
  </header>
</template>
