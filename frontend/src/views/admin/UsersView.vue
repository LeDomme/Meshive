<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { ApiError, apiRequest } from "../../api";
import AdminHeader from "../../components/AdminHeader.vue";
import { useAuthStore } from "../../stores/auth";

interface Role {
  id: number;
  name: string;
  is_system: boolean;
  is_superuser: boolean;
}
interface Source {
  id: number;
  name: string;
}
interface User {
  id: number;
  username: string;
  email: string | null;
  email_verified: boolean;
  role: "admin" | "user";
  role_definition: Role | null;
  all_sources: boolean;
  source_ids: number[];
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
  must_change_password: boolean;
}
const auth = useAuthStore();
const users = ref<User[]>([]);
const roles = ref<Role[]>([]);
const sources = ref<Source[]>([]);
const passwords = reactive<Record<number, string>>({});
const errorMessage = ref("");
const successMessage = ref("");
const busyUserId = ref<number | null>(null);
const form = reactive({
  username: "",
  email: "",
  password: "",
  role_id: 0,
  all_sources: true,
  source_ids: [] as number[],
  is_active: true,
  must_change_password: true,
});
function sourceSummary(user: User) {
  return user.all_sources
    ? "All sources"
    : user.source_ids.length
      ? `Selected sources (${user.source_ids.length})`
      : "No library access";
}
function showError(error: unknown) {
  errorMessage.value =
    error instanceof ApiError
      ? error.message
      : "The request could not be completed";
}
function accessPayload(value: { all_sources: boolean; source_ids: number[] }) {
  return {
    all_sources: value.all_sources,
    source_ids: value.all_sources ? [] : value.source_ids,
  };
}
async function load() {
  [users.value, roles.value, sources.value] = await Promise.all([
    apiRequest<User[]>("/api/admin/users"),
    apiRequest<Role[]>("/api/admin/roles"),
    apiRequest<Source[]>("/api/admin/users/library-sources"),
  ]);
  form.role_id ||=
    roles.value.find((role) => role.name === "Member")?.id ??
    roles.value[0]?.id ??
    0;
}
async function createUser() {
  errorMessage.value = "";
  try {
    await apiRequest<User>("/api/admin/users", {
      method: "POST",
      body: JSON.stringify({
        username: form.username,
        email: form.email.trim() || null,
        password: form.password,
        role_id: form.role_id,
        ...accessPayload(form),
        is_active: form.is_active,
        must_change_password: form.must_change_password,
      }),
    });
    Object.assign(form, {
      username: "",
      email: "",
      password: "",
      all_sources: true,
      source_ids: [],
      is_active: true,
      must_change_password: true,
    });
    await load();
    successMessage.value = "User created successfully.";
  } catch (error) {
    showError(error);
  }
}
async function saveUser(user: User) {
  errorMessage.value = "";
  busyUserId.value = user.id;
  try {
    const temporaryPassword = passwords[user.id] || null;
    const saved = await apiRequest<User>(`/api/admin/users/${user.id}`, {
      method: "PUT",
      body: JSON.stringify({
        username: user.username,
        email: user.email?.trim() || null,
        password: temporaryPassword,
        role_id: user.role_definition?.id,
        ...accessPayload(user),
        is_active: user.is_active,
        must_change_password:
          temporaryPassword && user.id !== auth.user?.id
            ? true
            : user.must_change_password,
      }),
    });
    passwords[user.id] = "";
    await load();
    if (user.id === auth.user?.id) await auth.refreshUser();
    successMessage.value = `User "${saved.username}" updated successfully.`;
  } catch (error) {
    showError(error);
    await load();
  } finally {
    busyUserId.value = null;
  }
}
async function sendVerification(user: User) {
  busyUserId.value = user.id;
  try {
    const result = await apiRequest<{ message: string }>(
      `/api/admin/users/${user.id}/email-verification`,
      { method: "POST", body: JSON.stringify({ email: user.email }) },
    );
    successMessage.value = result.message;
    await load();
  } catch (error) {
    showError(error);
  } finally {
    busyUserId.value = null;
  }
}
async function deleteUser(user: User) {
  if (!window.confirm(`Delete user "${user.username}" permanently?`)) return;
  busyUserId.value = user.id;
  try {
    await apiRequest(`/api/admin/users/${user.id}`, { method: "DELETE" });
    await load();
    successMessage.value = `User "${user.username}" deleted successfully.`;
  } catch (error) {
    showError(error);
  } finally {
    busyUserId.value = null;
  }
}
onMounted(() => {
  load().catch(showError);
});
</script>
<template>
  <main class="admin-shell">
    <AdminHeader title="Users" />
    <p class="admin-intro">
      Accounts are created locally. Source access is granted explicitly.
    </p>
    <p v-if="errorMessage" class="form-error error-panel" role="alert">
      {{ errorMessage }}
    </p>
    <p v-if="successMessage" class="success-panel" role="status">
      {{ successMessage }}
    </p>
    <section class="panel user-create-panel">
      <div class="panel-heading">
        <div>
          <h2>Create user</h2>
          <p class="panel-copy">
            Create an account, then choose its role and library access.
          </p>
        </div>
      </div>
      <form class="user-management-form" @submit.prevent="createUser">
        <fieldset>
          <legend>Account details</legend>
          <label
            ><span>Username</span
            ><input v-model="form.username" required /></label
          ><label
            ><span>Recovery email</span
            ><input v-model="form.email" type="email" /></label
          ><label
            ><span>Password</span
            ><input
              v-model="form.password"
              type="password"
              minlength="12"
              required
          /></label>
        </fieldset>
        <fieldset>
          <legend>Role & source access</legend>
          <label
            ><span>Role</span
            ><select v-model.number="form.role_id">
              <option v-for="role in roles" :key="role.id" :value="role.id">
                {{ role.name }}
              </option>
            </select></label
          ><label class="inline-check"
            ><input v-model="form.all_sources" type="checkbox" /> All current
            and future sources</label
          >
          <div v-if="!form.all_sources" class="source-picker">
            <strong>Selected sources</strong>
            <p v-if="!form.source_ids.length" class="form-error">
              No library access
            </p>
            <label
              v-for="source in sources"
              :key="source.id"
              class="inline-check"
              ><input
                v-model="form.source_ids"
                type="checkbox"
                :value="source.id"
              />
              {{ source.name }}</label
            >
          </div>
        </fieldset>
        <fieldset>
          <legend>Security</legend>
          <label class="inline-check"
            ><input v-model="form.is_active" type="checkbox" /> Active</label
          ><label class="inline-check"
            ><input v-model="form.must_change_password" type="checkbox" />
            Require password change</label
          >
        </fieldset>
        <div class="user-actions">
          <button class="primary-button" type="submit">Create user</button>
        </div>
      </form>
    </section>
    <section class="panel user-list-panel">
      <div class="panel-heading">
        <div>
          <h2>Existing users</h2>
          <p class="panel-copy">Changes are applied per user.</p>
        </div>
      </div>
      <div class="admin-user-list">
        <article
          v-for="user in users"
          :key="user.id"
          class="user-management-card"
        >
          <header>
            <strong>{{ user.username }}</strong
            ><span
              class="status-badge"
              :class="user.is_active ? 'active' : 'disabled'"
              >{{ user.is_active ? "Active" : "Disabled" }}</span
            ><span class="status-badge custom">{{
              user.role_definition?.name
            }}</span>
          </header>
          <div class="user-card-grid">
            <fieldset>
              <legend>Account details</legend>
              <label
                ><span>Username</span><input v-model="user.username" /></label
              ><label
                ><span>Recovery email</span
                ><input v-model="user.email" type="email"
              /></label>
              <p>
                {{ user.email_verified ? "Verified" : "Not verified" }}
                <button
                  v-if="user.email && !user.email_verified"
                  class="text-button"
                  type="button"
                  @click="sendVerification(user)"
                >
                  Send verification
                </button>
              </p>
            </fieldset>
            <fieldset>
              <legend>Access</legend>
              <label
                ><span>Role</span
                ><select v-model="user.role_definition!.id">
                  <option v-for="role in roles" :key="role.id" :value="role.id">
                    {{ role.name }}
                  </option>
                </select></label
              ><label class="inline-check"
                ><input v-model="user.all_sources" type="checkbox" /> All
                current and future sources</label
              >
              <div v-if="!user.all_sources" class="source-picker">
                <strong>Selected sources</strong>
                <p v-if="!user.source_ids.length" class="form-error">
                  No library access
                </p>
                <label
                  v-for="source in sources"
                  :key="source.id"
                  class="inline-check"
                  ><input
                    v-model="user.source_ids"
                    type="checkbox"
                    :value="source.id"
                  />
                  {{ source.name }}</label
                >
              </div>
              <p><strong>Access:</strong> {{ sourceSummary(user) }}</p>
            </fieldset>
            <fieldset>
              <legend>Security</legend>
              <label
                ><span>Temporary password</span
                ><input
                  v-model="passwords[user.id]"
                  type="password"
                  minlength="12"
                  placeholder="Leave unchanged" /></label
              ><label class="inline-check"
                ><input
                  v-model="user.is_active"
                  type="checkbox"
                  :disabled="user.id === auth.user?.id"
                />
                Active</label
              ><label class="inline-check"
                ><input v-model="user.must_change_password" type="checkbox" />
                Require password change</label
              >
            </fieldset>
          </div>
          <footer class="user-actions">
            <button
              class="secondary-button"
              type="button"
              :disabled="busyUserId === user.id"
              @click="saveUser(user)"
            >
              Save changes</button
            ><button
              class="danger-button"
              type="button"
              :disabled="user.id === auth.user?.id || busyUserId === user.id"
              @click="deleteUser(user)"
            >
              Delete
            </button>
          </footer>
        </article>
      </div>
    </section>
  </main>
</template>
