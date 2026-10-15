<script setup lang="ts">
import { RouterView } from "vue-router"

import ParticleNetworkBackground from "./components/ParticleNetworkBackground.vue"
</script>

<template>
  <ParticleNetworkBackground />
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
