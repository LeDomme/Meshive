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
const newPassword = ref("")
const confirmation = ref("")
const errorMessage = ref(token.value ? "" : "This reset link is incomplete.")
const successMessage = ref("")
const submitting = ref(false)

function readRouteToken(): string {
  if (typeof route.query.token === "string") return route.query.token
  if (!route.hash.startsWith("#token=")) return ""
  try {
    return decodeURIComponent(route.hash.slice(7))
  } catch {
    return ""
  }
}

onMounted(() => {
  if (route.query.token || route.hash) void router.replace({ name: "reset-password" })
})

async function submit() {
  errorMessage.value = ""
  successMessage.value = ""
  if (!token.value) {
    errorMessage.value = "This reset link is incomplete."
    return
  }
  if (newPassword.value !== confirmation.value) {
    errorMessage.value = "The new passwords do not match"
    return
  }
  submitting.value = true
  try {
    const result = await apiRequest<{ message: string }>(
      "/api/auth/password-recovery/reset",
      {
        method: "POST",
        body: JSON.stringify({ token: token.value, new_password: newPassword.value }),
      },
    )
    successMessage.value = result.message
    auth.clearLocalSession()
    newPassword.value = ""
    confirmation.value = ""
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : "Unable to reset the password"
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <main class="shell">
    <section class="login-card">
      <BrandLogo class="login-brand-icon" />
      <p class="eyebrow">Account recovery</p>
      <h1 class="login-title">Choose a new password</h1>
      <p class="login-intro">The new password must contain at least 12 characters.</p>
      <form v-if="!successMessage" class="login-form" @submit.prevent="submit">
        <label><span>New password</span><input v-model="newPassword" type="password" autocomplete="new-password" minlength="12" required></label>
        <label><span>Confirm new password</span><input v-model="confirmation" type="password" autocomplete="new-password" minlength="12" required></label>
        <p v-if="errorMessage" class="form-error" role="alert">{{ errorMessage }}</p>
        <button class="primary-button" type="submit" :disabled="submitting || !token">
          {{ submitting ? "Resetting…" : "Reset password" }}
        </button>
      </form>
      <div v-else class="login-form">
        <p class="success-panel" role="status">{{ successMessage }}</p>
        <RouterLink class="primary-link" to="/login">Continue to sign in</RouterLink>
      </div>
    </section>
  </main>
</template>
