<script setup lang="ts">
import { computed } from "vue"
import { RouterView } from "vue-router"

import ParticleNetworkBackground from "./components/ParticleNetworkBackground.vue"
import { useAuthStore } from "./stores/auth"

const auth = useAuthStore()
const animatedBackgroundEnabled = computed(
  () => auth.initialized && (auth.user?.animated_background ?? true),
)
</script>

<template>
  <ParticleNetworkBackground v-if="animatedBackgroundEnabled" />
  <div class="meshive-app-content">
    <RouterView />
  </div>
</template>

<style scoped>
.meshive-app-content {
  position: relative;
  z-index: 1;
  min-height: 100vh;
}
</style>
