<script setup lang="ts">
import { onMounted, ref } from "vue"
import { RouterLink, useRoute, useRouter } from "vue-router"

import { ApiError, apiRequest } from "../api"
import BrandLogo from "../components/BrandLogo.vue"
import { useAuthStore } from "../stores/auth"

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const token = ref(readRouteToken())
const loading = ref(true)
const errorMessage = ref("")
const successMessage = ref("")

function readRouteToken(): string {
  if (!route.hash.startsWith("#token=")) return ""
  try {
    return decodeURIComponent(route.hash.slice(7))
  } catch {
    return ""
  }
}

onMounted(async () => {
  if (route.hash) await router.replace({ name: "verify-email" })
  if (!token.value) {
    errorMessage.value = "This verification link is incomplete."
    loading.value = false
    return
  }
  try {
    const result = await apiRequest<{ message: string }>("/api/auth/email/verify", {
      method: "POST",
      body: JSON.stringify({ token: token.value }),
    })
    successMessage.value = result.message
    token.value = ""
    if (auth.user) await auth.refreshUser()
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : "Unable to verify the email address"
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <main class="shell">
    <section class="login-card">
      <BrandLogo class="login-brand-icon" />
      <p class="eyebrow">Recovery email</p>
      <h1 class="login-title">Verify your email</h1>
      <p v-if="loading" class="login-intro">Verifying the link…</p>
      <p v-if="errorMessage" class="form-error error-panel" role="alert">{{ errorMessage }}</p>
      <p v-if="successMessage" class="success-panel" role="status">{{ successMessage }}</p>
      <RouterLink class="primary-link verification-link" :to="auth.user ? '/account' : '/login'">
        {{ auth.user ? "Return to account" : "Continue to sign in" }}
      </RouterLink>
    </section>
  </main>
</template>
