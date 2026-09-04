import { createRouter, createWebHistory } from "vue-router"

import { useAuthStore } from "./stores/auth"
import AccessDeniedView from "./views/AccessDeniedView.vue"
import HomeView from "./views/HomeView.vue"
import ForgotPasswordView from "./views/ForgotPasswordView.vue"
import FavoriteListsView from "./views/FavoriteListsView.vue"
import LoginView from "./views/LoginView.vue"
import ModelDetailView from "./views/ModelDetailView.vue"
import NotFoundView from "./views/NotFoundView.vue"
import PasswordView from "./views/PasswordView.vue"
import ResetPasswordView from "./views/ResetPasswordView.vue"
import SetupView from "./views/SetupView.vue"
import VerifyEmailView from "./views/VerifyEmailView.vue"
import SourcesView from "./views/admin/SourcesView.vue"
import TagsView from "./views/admin/TagsView.vue"
import UsersView from "./views/admin/UsersView.vue"
import BackupsView from "./views/admin/BackupsView.vue"
import CreatorsView from "./views/admin/CreatorsView.vue"
import DiagnosticsView from "./views/admin/DiagnosticsView.vue"
import RolesView from "./views/admin/RolesView.vue"
import ScansView from "./views/admin/ScansView.vue"

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      name: "home",
      component: HomeView,
      meta: { requiresAuth: true, requiredPermission: "catalogue.view" },
    },
    {
      path: "/access-denied",
      name: "access-denied",
      component: AccessDeniedView,
      meta: { requiresAuth: true },
    },
    {
      path: "/account",
      alias: "/account/password",
      name: "account",
      component: PasswordView,
      meta: { requiresAuth: true, allowsPasswordChange: true },
    },
    {
      path: "/favorites",
      name: "favorite-lists",
      component: FavoriteListsView,
      meta: { requiresAuth: true, requiredPermission: "favorites.manage" },
    },
    {
      path: "/models/:id",
      name: "model-detail",
      component: ModelDetailView,
      meta: { requiresAuth: true, requiredPermission: "catalogue.view" },
    },
    {
      path: "/login",
      name: "login",
      component: LoginView,
    },
    {
      path: "/forgot-password",
      name: "forgot-password",
      component: ForgotPasswordView,
    },
    {
      path: "/reset-password",
      name: "reset-password",
      component: ResetPasswordView,
      meta: { allowsPasswordChange: true },
    },
    {
      path: "/verify-email",
      name: "verify-email",
      component: VerifyEmailView,
      meta: { allowsPasswordChange: true },
    },
    {
      path: "/setup",
      name: "setup",
      component: SetupView,
    },
    {
      path: "/admin/backups",
      name: "backups",
      component: BackupsView,
      meta: { requiresAuth: true, requiredPermission: "backups.manage", requiresAllSources: true },
    },
    {
      path: "/admin/users",
      name: "users",
      component: UsersView,
      meta: { requiresAuth: true, requiredPermission: "users.manage", requiresAllSources: true },
    },
    {
      path: "/admin/roles",
      name: "roles",
      component: RolesView,
      meta: { requiresAuth: true, requiredPermission: "roles.manage", requiresAllSources: true },
    },
    {
      path: "/admin/scans",
      name: "scans",
      component: ScansView,
      meta: {
        requiresAuth: true,
        requiredAnyPermission: ["scans.view", "scans.start", "scans.control"],
      },
    },
    {
      path: "/admin/metadata",
      name: "metadata",
      component: CreatorsView,
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      path: "/admin/creators",
      redirect: "/admin/metadata",
    },
    {
      path: "/admin/tags",
      name: "tags",
      component: TagsView,
      meta: { requiresAuth: true, requiresAdmin: true },
    },
    {
      path: "/admin/sources",
      name: "sources",
      component: SourcesView,
      meta: { requiresAuth: true, requiredPermission: "sources.manage", requiresAllSources: true },
    },
    {
      path: "/admin/diagnostics",
      name: "diagnostics",
      component: DiagnosticsView,
      meta: { requiresAuth: true, requiredPermission: "diagnostics.view", requiresAllSources: true },
    },
    {
      path: "/:pathMatch(.*)*",
      name: "not-found",
      component: NotFoundView,
      meta: { requiresAuth: true },
    },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  await auth.initialize()

  if (auth.setupRequired && to.name !== "setup") {
    return { name: "setup" }
  }
  if (!auth.setupRequired && to.name === "setup") {
    return { name: auth.user ? "home" : "login" }
  }
  if (to.meta.requiresAuth && !auth.user) {
    return { name: "login", query: { redirect: to.fullPath } }
  }
  if (
    auth.user?.must_change_password &&
    !to.meta.allowsPasswordChange &&
    to.name !== "login"
  ) {
    return { name: "account" }
  }
  if (
    to.name === "account" &&
    auth.user &&
    !auth.user.must_change_password &&
    to.query.forced === "true"
  ) {
    return { name: "home" }
  }
  if (to.meta.requiresAdmin && auth.user?.role !== "admin") {
    return { name: "home" }
  }
  if (typeof to.meta.requiredPermission === "string" && !auth.can(to.meta.requiredPermission)) {
    if (to.meta.requiredPermission === "catalogue.view") {
      return { name: "access-denied" }
    }
    return { name: "home" }
  }
  if (
    Array.isArray(to.meta.requiredAnyPermission)
    && !to.meta.requiredAnyPermission.some((permission) => auth.can(permission))
  ) {
    return { name: "home" }
  }
  if (to.meta.requiresAllSources && !auth.user?.source_access?.all_sources) {
    return { name: "home" }
  }
  if (to.name === "login" && auth.user) {
    return { name: "home" }
  }
  return true
})
