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
const cataloguePreferences = ref<CataloguePreferences>({ filter_order: [], action_order: [], navigation_mode: "pagination" })
const cataloguePreferencesLoading = ref(true)
const cataloguePreferencesSubmitting = ref(false)
const cataloguePreferencesError = ref("")
const cataloguePreferencesMessage = ref("")
const savedViews = ref<SavedView[]>([])
const savedViewsLoading = ref(true)
const savedViewsActionId = ref<number | null>(null)
const savedViewsError = ref("")

const defaultFilterOrder = ["model", "variant", "creator", "franchise", "series", "source", "tag", "status", "sort"]
const defaultActionOrder = ["selection", "saved_views", "navigation"]

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

interface CataloguePreferences {
  filter_order: string[]
  action_order: string[]
  navigation_mode: "pagination" | "infinite"
}

interface SavedView {
  id: number
  name: string
  created_at: string
  updated_at: string
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

async function loadCataloguePreferences() {
  cataloguePreferencesLoading.value = true
  cataloguePreferencesError.value = ""
  try {
    cataloguePreferences.value = await apiRequest<CataloguePreferences>("/api/auth/catalogue-preferences")
  } catch (error) {
    cataloguePreferencesError.value = error instanceof ApiError ? error.message : "Unable to load catalogue preferences"
  } finally {
    cataloguePreferencesLoading.value = false
  }
}

async function saveCataloguePreferences(preferences: CataloguePreferences, message: string) {
  cataloguePreferencesSubmitting.value = true
  cataloguePreferencesError.value = ""
  cataloguePreferencesMessage.value = ""
  try {
    cataloguePreferences.value = await apiRequest<CataloguePreferences>("/api/auth/catalogue-preferences", {
      method: "PUT",
      body: JSON.stringify(preferences),
    })
    cataloguePreferencesMessage.value = message
  } catch (error) {
    cataloguePreferencesError.value = error instanceof ApiError ? error.message : "Unable to save catalogue preferences"
  } finally {
    cataloguePreferencesSubmitting.value = false
  }
}

function resetCatalogueLayout() {
  void saveCataloguePreferences({
    filter_order: [...defaultFilterOrder],
    action_order: [...defaultActionOrder],
    navigation_mode: cataloguePreferences.value.navigation_mode,
  }, "Catalogue layout reset.")
}

async function loadSavedViews() {
  savedViewsLoading.value = true
  savedViewsError.value = ""
  try {
    savedViews.value = await apiRequest<SavedView[]>("/api/saved-views")
  } catch (error) {
    savedViewsError.value = error instanceof ApiError ? error.message : "Unable to load saved views"
  } finally {
    savedViewsLoading.value = false
  }
}

async function renameSavedView(view: SavedView) {
  const name = window.prompt("Rename saved view", view.name)?.trim()
  if (!name || name === view.name) return
  savedViewsActionId.value = view.id
  savedViewsError.value = ""
  try {
    const renamed = await apiRequest<SavedView>(`/api/saved-views/${view.id}`, {
      method: "PUT",
      body: JSON.stringify({ name }),
    })
    savedViews.value = savedViews.value.map((item) => item.id === renamed.id ? { ...item, ...renamed } : item)
  } catch (error) {
    savedViewsError.value = error instanceof ApiError ? error.message : "Unable to rename this saved view"
  } finally {
    savedViewsActionId.value = null
  }
}

async function deleteSavedView(view: SavedView) {
  if (!window.confirm(`Delete saved view "${view.name}"?`)) return
  savedViewsActionId.value = view.id
  savedViewsError.value = ""
  try {
    await apiRequest<void>(`/api/saved-views/${view.id}`, { method: "DELETE" })
    savedViews.value = savedViews.value.filter((item) => item.id !== view.id)
  } catch (error) {
    savedViewsError.value = error instanceof ApiError ? error.message : "Unable to delete this saved view"
  } finally {
    savedViewsActionId.value = null
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

onMounted(() => {
  void loadSessions()
  void loadCataloguePreferences()
  void loadSavedViews()
})
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
    <p class="account-intro">Manage your profile, recovery email, password, catalogue preferences and signed-in devices.</p>

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

        <section class="panel account-catalogue-preferences" aria-labelledby="catalogue-preferences-heading">
          <div class="panel-heading"><div><h2 id="catalogue-preferences-heading">Catalogue preferences</h2><p class="panel-copy">Restore your default catalogue control layout.</p></div></div>
          <p v-if="cataloguePreferencesLoading" class="panel-copy account-panel-content">Loading catalogue preferences…</p>
          <template v-else>
            <div class="catalogue-layout-setting account-panel-content">
              <div>
                <h3>Catalogue layout</h3>
                <p>Restore the default filter and catalogue action order.</p>
              </div>
              <button class="text-button" type="button" :disabled="cataloguePreferencesSubmitting" @click="resetCatalogueLayout">Reset</button>
            </div>
            <p v-if="cataloguePreferencesError" class="form-error" role="alert">{{ cataloguePreferencesError }}</p>
            <p v-if="cataloguePreferencesMessage" class="success-panel" role="status">{{ cataloguePreferencesMessage }}</p>
          </template>
        </section>

        <section class="panel account-saved-views" aria-labelledby="saved-views-heading">
          <div class="panel-heading"><div><h2 id="saved-views-heading">Saved views</h2><p class="panel-copy">Rename or remove your saved catalogue views.</p></div></div>
          <p v-if="savedViewsLoading" class="panel-copy account-panel-content">Loading saved views…</p>
          <p v-else-if="savedViews.length === 0 && !savedViewsError" class="panel-copy account-panel-content">No saved views yet.</p>
          <div v-else class="saved-view-list account-panel-content">
            <article v-for="view in savedViews" :key="view.id" class="saved-view-item">
              <h3>{{ view.name }}</h3>
              <div class="saved-view-actions">
                <button class="text-button" type="button" :disabled="savedViewsActionId !== null" @click="renameSavedView(view)">Rename</button>
                <button class="text-button danger-text-button" type="button" :disabled="savedViewsActionId !== null" @click="deleteSavedView(view)">Delete</button>
              </div>
            </article>
          </div>
          <p v-if="savedViewsError" class="form-error" role="alert">{{ savedViewsError }}</p>
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
