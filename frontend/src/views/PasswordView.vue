<script setup lang="ts">
import { ref } from "vue"
import { RouterLink, useRouter } from "vue-router"
import { ApiError } from "../api"
import BrandLogo from "../components/BrandLogo.vue"
import { useAuthStore } from "../stores/auth"

const auth = useAuthStore()
const router = useRouter()
const currentPassword = ref("")
const newPassword = ref("")
const confirmation = ref("")
const errorMessage = ref("")
const successMessage = ref("")
const submitting = ref(false)

async function submit() {
  errorMessage.value = ""
  successMessage.value = ""
  if (newPassword.value !== confirmation.value) {
    errorMessage.value = "The new passwords do not match"
    return
  }
  submitting.value = true
  try {
    const wasForced = Boolean(auth.user?.must_change_password)
    await auth.changePassword(currentPassword.value, newPassword.value)
    currentPassword.value = ""
    newPassword.value = ""
    confirmation.value = ""
    if (wasForced) {
      await router.replace("/")
    } else {
      successMessage.value = "Your password has been changed successfully."
    }
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : "Unable to change password"
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <main class="account-shell">
    <RouterLink v-if="!auth.user?.must_change_password" class="text-link" to="/">
      ← Back to catalogue
    </RouterLink>
    <section class="account-card">
      <header class="account-heading">
        <BrandLogo class="account-brand-icon" />
        <div>
          <p class="eyebrow">Your Meshive account</p>
          <h1>Account settings</h1>
        </div>
      </header>

      <section class="account-profile" aria-labelledby="profile-heading">
        <h2 id="profile-heading">Profile</h2>
        <dl>
          <div><dt>Username</dt><dd>{{ auth.user?.username }}</dd></div>
          <div><dt>Role</dt><dd class="role-value">{{ auth.user?.role }}</dd></div>
        </dl>
      </section>

      <section class="account-security" aria-labelledby="security-heading">
        <h2 id="security-heading">Change password</h2>
        <p class="panel-copy">
          {{ auth.user?.must_change_password
            ? "You must replace your initial password before continuing."
            : "Choose a new password for your Meshive account." }}
        </p>
        <form class="login-form" @submit.prevent="submit">
          <label><span>Current password</span><input v-model="currentPassword" type="password" autocomplete="current-password" required></label>
          <label><span>New password</span><input v-model="newPassword" type="password" autocomplete="new-password" minlength="12" required></label>
          <label><span>Confirm new password</span><input v-model="confirmation" type="password" autocomplete="new-password" minlength="12" required></label>
          <p v-if="errorMessage" class="form-error">{{ errorMessage }}</p>
          <p v-if="successMessage" class="success-panel" role="status">{{ successMessage }}</p>
          <button class="primary-button" type="submit" :disabled="submitting">
            {{ submitting ? "Changing password…" : "Change password" }}
          </button>
        </form>
      </section>
    </section>
  </main>
</template>
