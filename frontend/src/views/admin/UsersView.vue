<script setup lang="ts">
import { onMounted, reactive, ref } from "vue"

import { ApiError, apiRequest } from "../../api"
import AdminHeader from "../../components/AdminHeader.vue"
import { useAuthStore } from "../../stores/auth"

interface User {
  id: number
  username: string
  role: "admin" | "user"
  is_active: boolean
  created_at: string
  last_login_at: string | null
  must_change_password: boolean
}

const auth = useAuthStore()
const users = ref<User[]>([])
const passwords = reactive<Record<number, string>>({})
const errorMessage = ref("")
const successMessage = ref("")
const busyUserId = ref<number | null>(null)
const form = reactive({
  username: "",
  password: "",
  role: "user" as "admin" | "user",
  is_active: true,
  must_change_password: true,
})

async function loadUsers() {
  users.value = await apiRequest<User[]>("/api/admin/users")
}

async function createUser() {
  errorMessage.value = ""
  successMessage.value = ""
  try {
    await apiRequest<User>("/api/admin/users", {
      method: "POST",
      body: JSON.stringify(form),
    })
    Object.assign(form, { username: "", password: "", role: "user", is_active: true, must_change_password: true })
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
        <label><span>Password</span><input v-model="form.password" type="password" minlength="12" required></label>
        <label><span>Role</span><select v-model="form.role"><option value="user">User</option><option value="admin">Admin</option></select></label>
        <label class="inline-check"><input v-model="form.is_active" type="checkbox"> Active</label>
        <label class="inline-check"><input v-model="form.must_change_password" type="checkbox"> Require password change</label>
        <button class="primary-button" type="submit">Create user</button>
      </form>
    </section>

    <section class="panel user-list-panel">
      <h2>Existing users</h2>
      <div class="user-table-wrap">
        <table class="user-table">
          <thead><tr><th>Username</th><th>Role</th><th>Temporary password</th><th>Active</th><th>Require change</th><th>Last login</th><th></th></tr></thead>
          <tbody>
            <tr v-for="user in users" :key="user.id">
              <td><input v-model="user.username"></td>
              <td><select v-model="user.role"><option value="user">User</option><option value="admin">Admin</option></select></td>
              <td><input v-model="passwords[user.id]" type="password" minlength="12" autocomplete="new-password" placeholder="Leave unchanged" title="Setting a temporary password requires the user to change it at next login"></td>
              <td><input v-model="user.is_active" type="checkbox" :disabled="user.id === auth.user?.id"></td>
              <td><input v-model="user.must_change_password" type="checkbox"></td>
              <td>{{ user.last_login_at ? new Date(user.last_login_at).toLocaleString() : "Never" }}</td>
              <td class="user-actions">
                <button class="secondary-button" type="button" :disabled="busyUserId === user.id" @click="saveUser(user)">
                  {{ busyUserId === user.id ? "Saving…" : "Save" }}
                </button>
                <button class="danger-button" type="button" :disabled="user.id === auth.user?.id || busyUserId === user.id" @click="deleteUser(user)">
                  Delete
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </main>
</template>
