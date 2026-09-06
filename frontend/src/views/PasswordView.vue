<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { RouterLink, useRouter } from "vue-router"
import { ApiError, apiRequest } from "../api"
import AccountMenu from "../components/AccountMenu.vue"
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
const recoveryEmail = ref(auth.user?.email ?? "")
const emailPassword = ref("")
const emailError = ref("")
const emailMessage = ref("")
const emailSubmitting = ref(false)

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
const roleLabel = computed(() => auth.user?.role_definition?.name ?? auth.user?.role ?? "")

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

async function saveRecoveryEmail() {
  emailError.value = ""
  emailMessage.value = ""
  emailSubmitting.value = true
  try {
    await auth.changeRecoveryEmail(recoveryEmail.value, emailPassword.value)
    emailPassword.value = ""
    emailMessage.value = "Recovery email saved. Check your inbox for the verification link."
  } catch (error) {
    emailError.value = error instanceof ApiError ? error.message : "Unable to save the recovery email"
    await auth.refreshUser().catch(() => undefined)
    recoveryEmail.value = auth.user?.email ?? recoveryEmail.value
  } finally {
    emailSubmitting.value = false
  }
}

async function resendVerification() {
  emailError.value = ""
  emailMessage.value = ""
  emailSubmitting.value = true
  try {
    const result = await apiRequest<{ message: string }>("/api/auth/email/resend", {
      method: "POST",
    })
    emailMessage.value = result.message
  } catch (error) {
    emailError.value = error instanceof ApiError ? error.message : "Unable to send the verification email"
  } finally {
    emailSubmitting.value = false
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
    <header class="account-page-header">
      <div class="admin-brand">
        <p class="eyebrow">Your Meshive account</p>
        <div class="admin-title-row">
          <BrandLogo />
          <h1 class="admin-title">Account settings</h1>
        </div>
      </div>
      <nav v-if="!auth.user?.must_change_password" class="admin-nav" aria-label="Account navigation">
        <RouterLink class="text-link" to="/">Back to Meshive</RouterLink>
        <AccountMenu />
      </nav>
    </header>
    <p class="account-intro">Manage your profile, recovery email, password and signed-in devices.</p>

    <section class="account-layout">
      <aside class="panel account-profile" aria-labelledby="profile-heading">
        <div class="panel-heading">
          <div>
            <h2 id="profile-heading">Profile</h2>
            <p class="panel-copy">Your current Meshive account details.</p>
          </div>
        </div>

        <dl>
          <div><dt>Username</dt><dd>{{ auth.user?.username }}</dd></div>
          <div><dt>Role</dt><dd class="role-value">{{ roleLabel }}</dd></div>
          <div>
            <dt>Recovery email</dt>
            <dd>
              {{ auth.user?.email || "Not configured" }}
              <span v-if="auth.user?.email" :class="auth.user.email_verified ? 'email-verified' : 'email-unverified'">
                {{ auth.user.email_verified ? "Verified" : "Not verified" }}
              </span>
            </dd>
          </div>
        </dl>
      </aside>

      <div class="account-content">
        <section class="panel account-email" aria-labelledby="email-heading">
          <div class="panel-heading"><div><h2 id="email-heading">Recovery email</h2><p class="panel-copy">A verified address lets you reset a forgotten password. Changing it requires your current password.</p></div></div>
          <form class="account-form" @submit.prevent="saveRecoveryEmail">
            <label><span>Email address</span><input v-model="recoveryEmail" type="email" autocomplete="email" required></label>
            <label><span>Current password</span><input v-model="emailPassword" type="password" autocomplete="current-password" required></label>
            <p v-if="emailError" class="form-error" role="alert">{{ emailError }}</p>
            <p v-if="emailMessage" class="success-panel" role="status">{{ emailMessage }}</p>
            <div class="account-email-actions">
              <button class="primary-button" type="submit" :disabled="emailSubmitting">{{ emailSubmitting ? "Saving…" : "Save and verify email" }}</button>
              <button v-if="auth.user?.email && !auth.user.email_verified" class="secondary-button" type="button" :disabled="emailSubmitting" @click="resendVerification">Resend verification</button>
            </div>
          </form>
        </section>

        <section class="panel account-security" aria-labelledby="security-heading">
          <div class="panel-heading"><div><h2 id="security-heading">Change password</h2><p class="panel-copy">{{ auth.user?.must_change_password ? "You must replace your initial password before continuing." : "Choose a new password for your Meshive account." }}</p></div></div>
          <form class="account-form" @submit.prevent="submit">
            <label><span>Current password</span><input v-model="currentPassword" type="password" autocomplete="current-password" required></label>
            <label><span>New password</span><input v-model="newPassword" type="password" autocomplete="new-password" minlength="12" required></label>
            <label><span>Confirm new password</span><input v-model="confirmation" type="password" autocomplete="new-password" minlength="12" required></label>
            <p v-if="errorMessage" class="form-error">{{ errorMessage }}</p>
            <p v-if="successMessage" class="success-panel" role="status">{{ successMessage }}</p>
            <button class="primary-button" type="submit" :disabled="submitting">{{ submitting ? "Changing password…" : "Change password" }}</button>
          </form>
        </section>

        <section class="panel account-sessions" aria-labelledby="sessions-heading">
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
      </div>
    </section>
  </main>
</template>
