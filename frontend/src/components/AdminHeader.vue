<script setup lang="ts">
import { RouterLink } from "vue-router"
import AccountMenu from "./AccountMenu.vue"
import BrandLogo from "./BrandLogo.vue"
import { useAuthStore } from "../stores/auth"

defineProps<{ title: string }>()
const auth = useAuthStore()
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
      <RouterLink v-if="auth.can('catalogue.view')" class="text-link" to="/">Back to Meshive</RouterLink>
      <RouterLink v-if="auth.can('sources.manage') && auth.user?.source_access?.all_sources" class="text-link" to="/admin/sources">Library sources</RouterLink>
      <RouterLink class="text-link" to="/admin/metadata">Metadata</RouterLink>
      <RouterLink class="text-link" to="/admin/tags">Tags</RouterLink>
      <RouterLink v-if="auth.can('users.manage') && auth.user?.source_access?.all_sources !== false" class="text-link" to="/admin/users">Users</RouterLink>
      <RouterLink v-if="auth.can('roles.manage') && auth.user?.source_access?.all_sources !== false" class="text-link" to="/admin/roles">Roles</RouterLink>
      <RouterLink class="text-link" to="/admin/backups">Backups</RouterLink>
      <RouterLink class="text-link" to="/admin/diagnostics">Diagnostics</RouterLink>
      <AccountMenu />
    </nav>
  </header>
</template>
