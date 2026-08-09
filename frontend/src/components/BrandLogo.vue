<script setup lang="ts">
withDefaults(defineProps<{ variant?: "icon" | "wordmark" }>(), {
  variant: "icon",
})
</script>

<template>
  <span v-if="variant === 'icon'" class="brand-icon" aria-hidden="true">
    <img src="/meshhive_logo_borderless.webp" alt="">
  </span>
  <img
    v-else
    class="brand-wordmark"
    src="/meshhive_with_name.webp"
    alt="Meshive"
  >
</template>
