<script setup lang="ts">
import { ref } from "vue"
import { RouterLink } from "vue-router"

import { ApiError, apiRequest } from "../api"
import BrandLogo from "../components/BrandLogo.vue"

const identifier = ref("")
const errorMessage = ref("")
const successMessage = ref("")
const submitting = ref(false)

async function submit() {
  errorMessage.value = ""
  successMessage.value = ""
  submitting.value = true
  try {
    const result = await apiRequest<{ message: string }>(
      "/api/auth/password-recovery/request",
      {
        method: "POST",
        body: JSON.stringify({ identifier: identifier.value }),
      },
    )
    successMessage.value = result.message
    identifier.value = ""
  } catch (error) {
    errorMessage.value = error instanceof ApiError
      ? error.message
      : "Unable to request a password reset"
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
      <h1 class="login-title">Forgot your password?</h1>
      <p class="login-intro">
        Enter your username or verified recovery email. If the account is eligible,
        Meshive will send a reset link.
      </p>
      <form class="login-form" @submit.prevent="submit">
        <label>
          <span>Username or email</span>
          <input v-model="identifier" autocomplete="username" required autofocus>
        </label>
        <p v-if="errorMessage" class="form-error" role="alert">{{ errorMessage }}</p>
        <p v-if="successMessage" class="success-panel" role="status">{{ successMessage }}</p>
        <button class="primary-button" type="submit" :disabled="submitting">
          {{ submitting ? "Sending…" : "Send reset link" }}
        </button>
        <RouterLink class="text-link login-secondary-link" to="/login">Back to sign in</RouterLink>
      </form>
    </section>
  </main>
</template>
