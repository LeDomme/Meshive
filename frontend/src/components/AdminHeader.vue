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
      <AccountMenu />
    </nav>
  </header>
</template>
