<script setup lang="ts">
import { computed, ref } from "vue"
import { useRouter } from "vue-router"

import { ApiError } from "../api"
import BrandLogo from "../components/BrandLogo.vue"
import { useAuthStore } from "../stores/auth"

const auth = useAuthStore()
const router = useRouter()

const setupToken = ref("")
const username = ref("")
const password = ref("")
const confirmation = ref("")
const errorMessage = ref("")
const submitting = ref(false)
const passwordsMatch = computed(() => password.value === confirmation.value)

async function submit() {
  errorMessage.value = ""
  if (!passwordsMatch.value) {
    errorMessage.value = "Passwords do not match"
    return
  }
  submitting.value = true
  try {
    await auth.completeSetup(setupToken.value, username.value, password.value)
    await router.replace({ name: "home" })
  } catch (error) {
    errorMessage.value =
      error instanceof ApiError ? error.message : "Unable to complete setup"
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <main class="shell">
    <section class="login-card">
      <BrandLogo class="login-brand-icon" />
      <p class="eyebrow">First run</p>
      <h1 class="login-title">Set up Meshive</h1>
      <p class="login-intro">
        Create the first administrator. This page is permanently disabled as
        soon as an account exists.
      </p>

      <div v-if="!auth.setupEnabled" class="setup-warning" role="alert">
        Browser setup is disabled. Configure
        <code>MESHIVE_SETUP_TOKEN</code> and restart the container, or create
        the administrator from the container console.
      </div>

      <form v-else class="login-form" @submit.prevent="submit">
        <label>
          <span>Setup token</span>
          <input
            v-model="setupToken"
            name="setup-token"
            type="password"
            autocomplete="off"
            required
            autofocus
          >
        </label>

        <label>
          <span>Administrator username</span>
          <input v-model="username" name="username" autocomplete="username" required>
        </label>

        <label>
          <span>Password</span>
          <input
            v-model="password"
            name="password"
            type="password"
            minlength="12"
            autocomplete="new-password"
            required
          >
        </label>

        <label>
          <span>Confirm password</span>
          <input
            v-model="confirmation"
            name="confirmation"
            type="password"
            minlength="12"
            autocomplete="new-password"
            required
          >
        </label>

        <p v-if="errorMessage" class="form-error" role="alert">
          {{ errorMessage }}
        </p>

        <button class="primary-button" type="submit" :disabled="submitting">
          {{ submitting ? "Creating administrator…" : "Complete setup" }}
        </button>
      </form>
    </section>
  </main>
</template>
