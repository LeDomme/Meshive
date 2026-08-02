<script setup lang="ts">
import { onMounted, reactive, ref } from "vue"

import { ApiError, apiRequest } from "../../api"
import AdminHeader from "../../components/AdminHeader.vue"
import { useAuthStore } from "../../stores/auth"

interface User {
  id: number
  username: string
  email: string | null
  email_verified: boolean
  role: "admin" | "user"
  is_active: boolean
  created_at: string
  last_login_at: string | null
  must_change_password: boolean
}

const auth = useAuthStore()
const users = ref<User[]>([])
const passwords = reactive<Record<number, string>>({})
const savedEmails = reactive<Record<number, string | null>>({})
const errorMessage = ref("")
const successMessage = ref("")
const busyUserId = ref<number | null>(null)
const form = reactive({
  username: "",
  email: "",
  password: "",
  role: "user" as "admin" | "user",
  is_active: true,
  must_change_password: true,
})

async function loadUsers() {
  const loadedUsers = await apiRequest<User[]>("/api/admin/users")
  users.value = loadedUsers
  for (const key of Object.keys(savedEmails)) delete savedEmails[Number(key)]
  for (const user of loadedUsers) savedEmails[user.id] = user.email
}

function displayedEmailIsVerified(user: User): boolean {
  const displayed = user.email?.trim().toLocaleLowerCase() || null
  const saved = savedEmails[user.id]?.trim().toLocaleLowerCase() || null
  return user.email_verified && displayed === saved
}

async function createUser() {
  errorMessage.value = ""
  successMessage.value = ""
  try {
    await apiRequest<User>("/api/admin/users", {
      method: "POST",
      body: JSON.stringify({ ...form, email: form.email.trim() || null }),
    })
    Object.assign(form, { username: "", email: "", password: "", role: "user", is_active: true, must_change_password: true })
    await loadUsers()
    successMessage.value = "User created successfully."
  } catch (error) {
    showError(error)
  }
}

async function saveUser(user: User) {
  errorMessage.value = ""
  successMessage.value = ""
  busyUserId.value = user.id
  try {
    const temporaryPassword = passwords[user.id] || null
    const saved = await apiRequest<User>(`/api/admin/users/${user.id}`, {
      method: "PUT",
      body: JSON.stringify({
        username: user.username,
        email: user.email?.trim() || null,
        password: temporaryPassword,
        role: user.role,
        is_active: user.is_active,
        must_change_password:
          temporaryPassword && user.id !== auth.user?.id
            ? true
            : user.must_change_password,
      }),
    })
    passwords[user.id] = ""
    await loadUsers()
    if (user.id === auth.user?.id) {
      auth.user.username = saved.username
      auth.user.email = saved.email
      auth.user.email_verified = saved.email_verified
      auth.user.role = saved.role
      auth.user.is_active = saved.is_active
      auth.user.must_change_password = saved.must_change_password
    }
    successMessage.value = temporaryPassword
      ? `User "${user.username}" updated. The temporary password must be changed at next login.`
      : `User "${user.username}" updated successfully.`
  } catch (error) {
    showError(error)
    await loadUsers()
  } finally {
    busyUserId.value = null
  }
}

async function sendVerification(user: User) {
  errorMessage.value = ""
  successMessage.value = ""
  busyUserId.value = user.id
  try {
    const result = await apiRequest<{ message: string }>(
      `/api/admin/users/${user.id}/email-verification`,
      {
        method: "POST",
        body: JSON.stringify({ email: user.email }),
      },
    )
    await loadUsers()
    successMessage.value = result.message
  } catch (error) {
    showError(error)
  } finally {
    busyUserId.value = null
  }
}

async function deleteUser(user: User) {
  if (!window.confirm(`Delete user "${user.username}" permanently?`)) return
  errorMessage.value = ""
  successMessage.value = ""
  busyUserId.value = user.id
  try {
    await apiRequest(`/api/admin/users/${user.id}`, { method: "DELETE" })
    delete passwords[user.id]
    await loadUsers()
    successMessage.value = `User "${user.username}" deleted successfully.`
  } catch (error) {
    showError(error)
  } finally {
    busyUserId.value = null
  }
}

function showError(error: unknown) {
  errorMessage.value =
    error instanceof ApiError ? error.message : "The request could not be completed"
}

onMounted(loadUsers)
</script>

<template>
  <main class="admin-shell">
    <AdminHeader title="Users" />
    <p class="admin-intro">
      Accounts are created locally. There is no public registration.
    </p>
    <p v-if="errorMessage" class="form-error error-panel" role="alert">
      {{ errorMessage }}
    </p>
    <p v-if="successMessage" class="success-panel" role="status">
      {{ successMessage }}
    </p>

    <section class="panel user-create-panel">
      <h2>Create user</h2>
      <form class="user-form" @submit.prevent="createUser">
        <label><span>Username</span><input v-model="form.username" required></label>
        <label><span>Recovery email</span><input v-model="form.email" type="email" autocomplete="off" placeholder="Optional"></label>
        <label><span>Password</span><input v-model="form.password" type="password" minlength="12" required></label>
        <label><span>Role</span><select v-model="form.role"><option value="user">User</option><option value="admin">Admin</option></select></label>
        <label class="inline-check"><input v-model="form.is_active" type="checkbox"> Active</label>
        <label class="inline-check"><input v-model="form.must_change_password" type="checkbox"> Require password change</label>
        <button class="primary-button" type="submit">Create user</button>
      </form>
    </section>

    <section class="panel user-list-panel">
      <h2>Existing users</h2>
      <div class="admin-user-list">
        <article v-for="user in users" :key="user.id" class="admin-user-card">
          <label class="admin-user-field">
            <span>Username</span>
            <input v-model="user.username">
          </label>

          <div class="admin-user-field admin-user-email">
            <label :for="`user-email-${user.id}`">Recovery email</label>
            <input
              :id="`user-email-${user.id}`"
              v-model="user.email"
              type="email"
              autocomplete="off"
              placeholder="Not configured"
            >
            <div v-if="user.email" class="admin-user-email-status">
              <span :class="displayedEmailIsVerified(user) ? 'email-verified' : 'email-unverified'">
                {{ displayedEmailIsVerified(user) ? "Verified" : "Not verified" }}
              </span>
              <button
                v-if="!displayedEmailIsVerified(user)"
                class="text-button"
                type="button"
                :disabled="busyUserId === user.id"
                @click="sendVerification(user)"
              >
                Send verification
              </button>
            </div>
            <span v-else class="admin-user-email-empty">No recovery email configured</span>
          </div>

          <label class="admin-user-field">
            <span>Role</span>
            <select v-model="user.role"><option value="user">User</option><option value="admin">Admin</option></select>
          </label>

          <label class="admin-user-field">
            <span>Temporary password</span>
            <input
              v-model="passwords[user.id]"
              type="password"
              minlength="12"
              autocomplete="new-password"
              placeholder="Leave unchanged"
              title="Setting a temporary password requires the user to change it at next login"
            >
          </label>

          <div class="admin-user-options">
            <label class="inline-check">
              <input v-model="user.is_active" type="checkbox" :disabled="user.id === auth.user?.id">
              Active
            </label>
            <label class="inline-check">
              <input v-model="user.must_change_password" type="checkbox">
              Require password change
            </label>
          </div>

          <div class="admin-user-last-login">
            <span>Last login</span>
            <strong>{{ user.last_login_at ? new Date(user.last_login_at).toLocaleString() : "Never" }}</strong>
          </div>

          <div class="user-actions admin-user-actions">
            <button class="secondary-button" type="button" :disabled="busyUserId === user.id" @click="saveUser(user)">
              {{ busyUserId === user.id ? "Saving…" : "Save changes" }}
            </button>
            <button class="danger-button" type="button" :disabled="user.id === auth.user?.id || busyUserId === user.id" @click="deleteUser(user)">
              Delete
            </button>
          </div>
        </article>
      </div>
    </section>
  </main>
</template>
