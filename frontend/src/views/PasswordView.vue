<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { RouterLink, useRouter } from "vue-router"
import { ApiError, apiRequest } from "../api"
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
const sessions = ref<UserSession[]>([])
const sessionsLoading = ref(true)
const sessionActionId = ref("")
const sessionError = ref("")
const sessionMessage = ref("")

interface UserSession {
  id: string
  created_at: string
  last_used_at: string
  expires_at: string
  browser: string | null
  operating_system: string | null
  device_type: string | null
  is_current: boolean
}

interface SessionRevocationResult {
  revoked_count: number
}

const hasOtherSessions = computed(() => sessions.value.some((item) => !item.is_current))

function asDate(value: string): Date {
  const hasTimezone = /(?:Z|[+-]\d{2}:\d{2})$/.test(value)
  return new Date(hasTimezone ? value : `${value}Z`)
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(asDate(value))
}

function sessionTitle(item: UserSession): string {
  return item.browser ?? "Unknown browser"
}

function sessionDetails(item: UserSession): string {
  return [item.operating_system, item.device_type].filter(Boolean).join(" · ") || "Unknown device"
}

async function loadSessions() {
  sessionsLoading.value = true
  sessionError.value = ""
  try {
    sessions.value = await apiRequest<UserSession[]>("/api/auth/sessions")
  } catch (error) {
    sessionError.value = error instanceof ApiError ? error.message : "Unable to load active sessions"
  } finally {
    sessionsLoading.value = false
  }
}

async function revokeSession(item: UserSession) {
  const prompt = item.is_current
    ? "Sign out this session?"
    : `Revoke the session for ${sessionTitle(item)}?`
  if (!window.confirm(prompt)) return

  sessionActionId.value = item.id
  sessionError.value = ""
  sessionMessage.value = ""
  try {
    await apiRequest<void>(`/api/auth/sessions/${item.id}`, { method: "DELETE" })
    if (item.is_current) {
      auth.clearLocalSession()
      await router.replace("/login")
      return
    }
    sessions.value = sessions.value.filter((candidate) => candidate.id !== item.id)
    sessionMessage.value = "The session has been revoked."
  } catch (error) {
    sessionError.value = error instanceof ApiError ? error.message : "Unable to revoke the session"
  } finally {
    sessionActionId.value = ""
  }
}

async function revokeOtherSessions() {
  if (!window.confirm("Sign out all other sessions?")) return
  sessionActionId.value = "others"
  sessionError.value = ""
  sessionMessage.value = ""
  try {
    const result = await apiRequest<SessionRevocationResult>("/api/auth/sessions/others", {
      method: "DELETE",
    })
    sessions.value = sessions.value.filter((item) => item.is_current)
    sessionMessage.value = result.revoked_count === 1
      ? "1 other session has been signed out."
      : `${result.revoked_count} other sessions have been signed out.`
  } catch (error) {
    sessionError.value = error instanceof ApiError ? error.message : "Unable to revoke other sessions"
  } finally {
    sessionActionId.value = ""
  }
}

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

onMounted(loadSessions)
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

      <section class="account-sessions" aria-labelledby="sessions-heading">
        <div class="account-section-heading">
          <div>
            <h2 id="sessions-heading">Active sessions</h2>
            <p class="panel-copy">Review the devices signed in to your account and revoke access you no longer use.</p>
          </div>
          <button
            v-if="hasOtherSessions"
            class="danger-button"
            type="button"
            :disabled="Boolean(sessionActionId)"
            @click="revokeOtherSessions"
          >
            {{ sessionActionId === "others" ? "Signing out…" : "Sign out all others" }}
          </button>
        </div>

        <p v-if="sessionsLoading" class="panel-copy">Loading active sessions…</p>
        <p v-else-if="sessions.length === 0 && !sessionError" class="panel-copy">No active sessions found.</p>
        <div v-if="!sessionsLoading && sessions.length > 0" class="session-list">
          <article v-for="item in sessions" :key="item.id" class="session-item">
            <div class="session-summary">
              <div class="session-title-row">
                <h3>{{ sessionTitle(item) }}</h3>
                <span v-if="item.is_current" class="session-current">Current session</span>
              </div>
              <p>{{ sessionDetails(item) }}</p>
              <dl>
                <div><dt>Last used</dt><dd>{{ formatDate(item.last_used_at) }}</dd></div>
                <div><dt>Signed in</dt><dd>{{ formatDate(item.created_at) }}</dd></div>
                <div><dt>Expires</dt><dd>{{ formatDate(item.expires_at) }}</dd></div>
              </dl>
            </div>
            <button
              :class="item.is_current ? 'secondary-button' : 'danger-button'"
              type="button"
              :disabled="Boolean(sessionActionId)"
              @click="revokeSession(item)"
            >
              {{ sessionActionId === item.id ? "Working…" : (item.is_current ? "Sign out" : "Revoke") }}
            </button>
          </article>
        </div>
        <p v-if="sessionError" class="form-error" role="alert">{{ sessionError }}</p>
        <p v-if="sessionMessage" class="success-panel" role="status">{{ sessionMessage }}</p>
      </section>
    </section>
  </main>
</template>
