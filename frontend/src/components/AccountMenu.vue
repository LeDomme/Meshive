<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue"
import { RouterLink, useRouter } from "vue-router"

import { useAuthStore } from "../stores/auth"

const auth = useAuthStore()
const router = useRouter()
const menu = ref<HTMLDetailsElement | null>(null)

function closeMenu() {
  menu.value?.removeAttribute("open")
}

function closeOutside(event: PointerEvent) {
  if (menu.value && !menu.value.contains(event.target as Node)) closeMenu()
}

function closeOnEscape(event: KeyboardEvent) {
  if (event.key === "Escape") closeMenu()
}

onMounted(() => {
  document.addEventListener("pointerdown", closeOutside)
  document.addEventListener("keydown", closeOnEscape)
})

onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", closeOutside)
  document.removeEventListener("keydown", closeOnEscape)
})

async function logout() {
  closeMenu()
  await auth.logout()
  await router.push({ name: "login" })
}
</script>

<template>
  <details ref="menu" class="account-menu">
    <summary class="account-menu-trigger">
      <span>{{ auth.user?.username }}</span>
      <span class="account-menu-icon" aria-hidden="true">☰</span>
    </summary>
    <div class="account-menu-popover">
      <div class="account-menu-identity">
        <strong>{{ auth.user?.username }}</strong>
        <span>{{ auth.user?.role }}</span>
      </div>
      <RouterLink class="account-menu-item" to="/account" @click="closeMenu">
        Account settings
      </RouterLink>
      <RouterLink v-if="auth.can('favorites.manage')" class="account-menu-item" to="/favorites" @click="closeMenu">
        Favorite lists
      </RouterLink>
      <div v-if="auth.can('sources.manage') || auth.can('scans.view') || auth.can('scans.start') || auth.can('scans.control') || ((auth.can('metadata.manage') || auth.can('tags.manage') || auth.can('tag_rules.manage') || auth.can('users.manage') || auth.can('roles.manage') || auth.can('backups.manage') || auth.can('diagnostics.view')) && auth.user?.source_access?.all_sources)" class="account-menu-section">
        <span>Administration</span>
      </div>
      <RouterLink v-if="auth.can('sources.manage')" class="account-menu-item" to="/admin/sources" @click="closeMenu">Library sources</RouterLink>
      <RouterLink v-if="auth.can('scans.view') || auth.can('scans.start') || auth.can('scans.control')" class="account-menu-item" to="/admin/scans" @click="closeMenu">Scans</RouterLink>
      <RouterLink v-if="auth.can('metadata.manage') && auth.user?.source_access?.all_sources" class="account-menu-item" to="/admin/metadata" @click="closeMenu">Metadata</RouterLink>
      <RouterLink v-if="(auth.can('tags.manage') || auth.can('tag_rules.manage')) && auth.user?.source_access?.all_sources" class="account-menu-item" to="/admin/tags" @click="closeMenu">Tags</RouterLink>
      <RouterLink v-if="auth.can('users.manage') && auth.user?.source_access?.all_sources" class="account-menu-item" to="/admin/users" @click="closeMenu">Users</RouterLink>
      <RouterLink v-if="auth.can('roles.manage') && auth.user?.source_access?.all_sources" class="account-menu-item" to="/admin/roles" @click="closeMenu">Roles</RouterLink>
      <RouterLink v-if="auth.can('backups.manage') && auth.user?.source_access?.all_sources" class="account-menu-item" to="/admin/backups" @click="closeMenu">Backups</RouterLink>
      <RouterLink v-if="auth.can('diagnostics.view') && auth.user?.source_access?.all_sources" class="account-menu-item" to="/admin/diagnostics" @click="closeMenu">Diagnostics</RouterLink>
      <div class="account-menu-signout"><button class="account-menu-item" type="button" @click="logout">Sign out</button></div>
    </div>
  </details>
</template>
