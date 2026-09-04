<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { RouterLink, useRouter } from "vue-router"
import AccountMenu from "./AccountMenu.vue"
import BrandLogo from "./BrandLogo.vue"
import { useAuthStore } from "../stores/auth"

defineProps<{ title: string }>()
const auth = useAuthStore()
const hasAdministrationEntry = computed(() => auth.can("sources.manage") || auth.can("scans.view") || auth.can("scans.start") || auth.can("scans.control") || (auth.can("users.manage") && Boolean(auth.user?.source_access?.all_sources)) || (auth.can("roles.manage") && Boolean(auth.user?.source_access?.all_sources)) || (auth.can("backups.manage") && Boolean(auth.user?.source_access?.all_sources)) || (auth.can("diagnostics.view") && Boolean(auth.user?.source_access?.all_sources)))
const router = useRouter()
const menu = ref<HTMLDetailsElement | null>(null)
function closeMenu() { menu.value?.removeAttribute("open") }
function closeOutside(event: PointerEvent) { if (menu.value && !menu.value.contains(event.target as Node)) closeMenu() }
function closeEscape(event: KeyboardEvent) { if (event.key === "Escape") closeMenu() }
onMounted(() => { document.addEventListener("pointerdown", closeOutside); document.addEventListener("keydown", closeEscape) })
onBeforeUnmount(() => { document.removeEventListener("pointerdown", closeOutside); document.removeEventListener("keydown", closeEscape) })
watch(() => router.currentRoute.value.fullPath, closeMenu)
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
      <details v-if="hasAdministrationEntry" ref="menu" class="administration-menu"><summary aria-label="Administration menu">Administration <span aria-hidden="true">⌄</span></summary><div class="administration-menu-popover" role="menu">
        <RouterLink v-if="auth.can('sources.manage')" to="/admin/sources" @click="closeMenu">Library sources</RouterLink>
        <RouterLink v-if="auth.can('scans.view') || auth.can('scans.start') || auth.can('scans.control')" to="/admin/scans" @click="closeMenu">Scans</RouterLink>
        <RouterLink v-if="auth.can('users.manage') && auth.user?.source_access?.all_sources" to="/admin/users" @click="closeMenu">Users</RouterLink>
        <RouterLink v-if="auth.can('roles.manage') && auth.user?.source_access?.all_sources" to="/admin/roles" @click="closeMenu">Roles</RouterLink>
        <RouterLink v-if="auth.can('backups.manage') && auth.user?.source_access?.all_sources" to="/admin/backups" @click="closeMenu">Backups</RouterLink>
        <RouterLink v-if="auth.can('diagnostics.view') && auth.user?.source_access?.all_sources" to="/admin/diagnostics" @click="closeMenu">Diagnostics</RouterLink>
      </div></details>
      <AccountMenu />
    </nav>
  </header>
</template>

<style scoped>
.administration-menu { position: relative; }.administration-menu summary { cursor: pointer; white-space: nowrap; }.administration-menu-popover { position: absolute; right: 0; top: calc(100% + .4rem); z-index: 10; display: grid; min-width: 11rem; padding: .4rem; background: var(--panel); border: 1px solid var(--line); border-radius: .5rem; box-shadow: 0 .5rem 1.5rem rgb(0 0 0 / .15); }.administration-menu-popover a { padding: .45rem .6rem; border-radius: .3rem; white-space: nowrap; }.administration-menu-popover a:focus-visible { outline: 2px solid var(--accent); }
</style>
