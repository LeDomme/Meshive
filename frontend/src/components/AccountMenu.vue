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
      <RouterLink class="account-menu-item" to="/favorites" @click="closeMenu">
        Favorite lists
      </RouterLink>
      <button class="account-menu-item" type="button" @click="logout">Sign out</button>
    </div>
  </details>
</template>
