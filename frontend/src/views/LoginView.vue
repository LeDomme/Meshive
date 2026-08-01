<script setup lang="ts">
import { onMounted, ref } from "vue"
import { RouterLink, useRoute, useRouter } from "vue-router"

import { ApiError, apiRequest } from "../api"
import BrandLogo from "../components/BrandLogo.vue"
import { useAuthStore } from "../stores/auth"

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const username = ref("")
const password = ref("")
const errorMessage = ref("")
const submitting = ref(false)
const recoveryEnabled = ref(false)

onMounted(async () => {
  try {
    const status = await apiRequest<{ enabled: boolean }>("/api/auth/password-recovery/status")
    recoveryEnabled.value = status.enabled
  } catch {
    recoveryEnabled.value = false
  }
})

async function submit() {
  errorMessage.value = ""
  submitting.value = true
  try {
    await auth.login(username.value, password.value)
    if (auth.user?.must_change_password) {
      await router.replace({ name: "account" })
      return
    }
    const redirect =
      typeof route.query.redirect === "string" ? route.query.redirect : "/"
    await router.replace(redirect)
  } catch (error) {
    errorMessage.value =
      error instanceof ApiError ? error.message : "Unable to sign in"
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <main class="shell">
    <section class="login-card">
      <BrandLogo class="login-brand-icon" />
      <p class="eyebrow">Private archive</p>
      <h1 class="login-title">Sign in to Meshive</h1>
      <p class="login-intro">
        Accounts are created by a Meshive administrator. Public registration is
        not available.
      </p>

      <form class="login-form" @submit.prevent="submit">
        <label>
          <span>Username</span>
          <input
            v-model="username"
            name="username"
            autocomplete="username"
            required
            autofocus
          >
        </label>

        <label>
          <span>Password</span>
          <input
            v-model="password"
            name="password"
            type="password"
            autocomplete="current-password"
            required
          >
        </label>

        <p v-if="errorMessage" class="form-error" role="alert">
          {{ errorMessage }}
        </p>

        <button class="primary-button" type="submit" :disabled="submitting">
          {{ submitting ? "Signing in…" : "Sign in" }}
        </button>
        <RouterLink v-if="recoveryEnabled" class="text-link login-secondary-link" to="/forgot-password">
          Forgot password?
        </RouterLink>
      </form>
    </section>
  </main>
</template>
