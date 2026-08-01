import { defineStore } from "pinia"

import { ApiError, apiRequest } from "../api"

export interface CurrentUser {
  id: number
  username: string
  role: "admin" | "user"
  is_active: boolean
  must_change_password: boolean
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
  },
})
