import { defineStore } from "pinia"

import { ApiError, apiRequest } from "../api"

export interface CurrentUser {
  id: number
  username: string
  email: string | null
  email_verified: boolean
  role: "admin" | "user"
  is_active: boolean
  must_change_password: boolean
  role_definition: RoleDefinition | null
  permissions: string[]
  source_access: SourceAccess
}

export interface RoleDefinition {
  id: number
  name: string
  is_system: boolean
  is_superuser: boolean
}

export interface SourceAccess {
  all_sources: boolean
  source_ids: number[]
}

interface SetupStatus {
  required: boolean
  enabled: boolean
}

export const useAuthStore = defineStore("auth", {
  state: () => ({
    user: null as CurrentUser | null,
    initialized: false,
    setupRequired: false,
    setupEnabled: false,
  }),

  actions: {
    can(permission: string): boolean {
      return this.user?.permissions?.includes(permission) ?? false
    },

    canForSource(permission: string, sourceId: number): boolean {
      return this.can(permission) && Boolean(
        this.user?.source_access?.all_sources || this.user?.source_access?.source_ids.includes(sourceId),
      )
    },
    async initialize() {
      if (this.initialized) return
      try {
        const setup = await apiRequest<SetupStatus>("/api/setup/status")
        this.setupRequired = setup.required
        this.setupEnabled = setup.enabled
        if (setup.required) {
          this.user = null
          return
        }
        this.user = await apiRequest<CurrentUser>("/api/auth/me")
      } catch (error) {
        if (!(error instanceof ApiError) || error.status !== 401) throw error
        this.user = null
      } finally {
        this.initialized = true
      }
    },

    async login(username: string, password: string) {
      this.user = await apiRequest<CurrentUser>("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      })
      this.initialized = true
    },

    async refreshUser() {
      this.user = await apiRequest<CurrentUser>("/api/auth/me")
      return this.user
    },

    async completeSetup(setupToken: string, username: string, password: string) {
      this.user = await apiRequest<CurrentUser>("/api/setup", {
        method: "POST",
        body: JSON.stringify({
          setup_token: setupToken,
          username,
          password,
        }),
      })
      this.setupRequired = false
      this.initialized = true
    },

    async logout() {
      await apiRequest<void>("/api/auth/logout", { method: "POST" })
      this.user = null
      this.initialized = true
    },

    clearLocalSession() {
      this.user = null
      this.initialized = true
    },

    async changePassword(currentPassword: string, newPassword: string) {
      this.user = await apiRequest<CurrentUser>("/api/auth/change-password", {
        method: "POST",
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      })
    },

    async changeRecoveryEmail(email: string, currentPassword: string) {
      this.user = await apiRequest<CurrentUser>("/api/auth/email", {
        method: "POST",
        body: JSON.stringify({ email, current_password: currentPassword }),
      })
    },
  },
})
