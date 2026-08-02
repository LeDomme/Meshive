<script setup lang="ts">
import { onMounted, ref } from "vue"
import { RouterLink } from "vue-router"

import { ApiError, apiRequest } from "../api"
import BrandLogo from "../components/BrandLogo.vue"
import type { FavoriteListDetail, FavoriteListSummary } from "../favorites"

const lists = ref<FavoriteListSummary[]>([])
const selected = ref<FavoriteListDetail | null>(null)
const selectedListId = ref(0)
const newListName = ref("")
const renameValue = ref("")
const loading = ref(true)
const working = ref(false)
const errorMessage = ref("")
const successMessage = ref("")

async function loadLists(preferredId?: number) {
  lists.value = await apiRequest<FavoriteListSummary[]>("/api/favorite-lists")
  const requestedId = preferredId || selectedListId.value
  const targetId = lists.value.some((item) => item.id === requestedId)
    ? requestedId
    : lists.value[0]?.id
  if (targetId) {
    await selectList(targetId)
  } else {
    selectedListId.value = 0
    selected.value = null
  }
}

async function selectList(id: number) {
  selectedListId.value = id
  errorMessage.value = ""
  try {
    selected.value = await apiRequest<FavoriteListDetail>(`/api/favorite-lists/${id}`)
    renameValue.value = selected.value.name
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : "Unable to load the list"
  }
}

async function createList() {
  working.value = true
  errorMessage.value = ""
  successMessage.value = ""
  try {
    const created = await apiRequest<FavoriteListSummary>("/api/favorite-lists", {
      method: "POST",
      body: JSON.stringify({ name: newListName.value }),
    })
    newListName.value = ""
    await loadLists(created.id)
    successMessage.value = `Created ${created.name}.`
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : "Unable to create the list"
  } finally {
    working.value = false
  }
}

async function renameList() {
  if (!selected.value) return
  working.value = true
  errorMessage.value = ""
  successMessage.value = ""
  try {
    const updated = await apiRequest<FavoriteListSummary>(
      `/api/favorite-lists/${selected.value.id}`,
      { method: "PUT", body: JSON.stringify({ name: renameValue.value }) },
    )
    await loadLists(updated.id)
    successMessage.value = "Favorite list renamed."
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : "Unable to rename the list"
  } finally {
    working.value = false
  }
}

async function deleteList() {
  if (!selected.value || !window.confirm(`Delete "${selected.value.name}"?`)) return
  working.value = true
  errorMessage.value = ""
  successMessage.value = ""
  try {
    await apiRequest<void>(`/api/favorite-lists/${selected.value.id}`, { method: "DELETE" })
    await loadLists()
    successMessage.value = "Favorite list deleted."
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : "Unable to delete the list"
  } finally {
    working.value = false
  }
}

async function removeItem(itemId: number) {
  if (!selected.value) return
  working.value = true
  errorMessage.value = ""
  try {
    await apiRequest<void>(
      `/api/favorite-lists/${selected.value.id}/items/${itemId}`,
      { method: "DELETE" },
    )
    await loadLists(selected.value.id)
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : "Unable to remove the entry"
  } finally {
    working.value = false
  }
}

onMounted(async () => {
  try {
    await loadLists()
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : "Unable to load favorite lists"
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <main class="favorites-shell">
    <RouterLink class="text-link" to="/">&larr; Back to catalogue</RouterLink>
    <header class="favorites-header">
      <BrandLogo class="account-brand-icon" />
      <div>
        <p class="eyebrow">Private to your account</p>
        <h1>Favorite lists</h1>
      </div>
    </header>

    <p class="panel-copy">
      Organize models and catalogue categories into personal lists. Other users cannot see them.
    </p>
    <p v-if="errorMessage" class="form-error error-panel" role="alert">{{ errorMessage }}</p>
    <p v-if="successMessage" class="success-panel" role="status">{{ successMessage }}</p>

    <section class="favorites-layout">
      <aside class="panel favorites-sidebar">
        <h2>Your lists</h2>
        <form class="favorite-new-form" @submit.prevent="createList">
          <label class="standalone-field">
            <span>New list name</span>
            <input v-model="newListName" maxlength="120" placeholder="Print next" required>
          </label>
          <button class="primary-button" type="submit" :disabled="working">Create list</button>
        </form>
        <p v-if="loading" class="panel-copy">Loading...</p>
        <nav v-else-if="lists.length" class="favorite-list-nav" aria-label="Favorite lists">
          <button
            v-for="list in lists"
            :key="list.id"
            type="button"
            :class="{ selected: list.id === selectedListId }"
            @click="selectList(list.id)"
          >
            <span>{{ list.name }}</span><small>{{ list.item_count }}</small>
          </button>
        </nav>
        <p v-else class="panel-copy">No favorite lists yet.</p>
      </aside>

      <section class="panel favorites-detail">
        <template v-if="selected">
          <div class="favorites-detail-heading">
            <div>
              <p class="eyebrow">{{ selected.item_count }} entries</p>
              <h2>{{ selected.name }}</h2>
            </div>
            <button class="danger-button" type="button" :disabled="working" @click="deleteList">
              Delete list
            </button>
          </div>
          <form class="favorite-rename-form" @submit.prevent="renameList">
            <label class="standalone-field">
              <span>List name</span>
              <input v-model="renameValue" maxlength="120" required>
            </label>
            <button class="secondary-button" type="submit" :disabled="working">Rename</button>
          </form>

          <div v-if="selected.items.length" class="favorite-items">
            <article v-for="item in selected.items" :key="item.id" class="favorite-item">
              <div>
                <span class="favorite-item-type">{{ item.entity_type }}</span>
                <RouterLink v-if="item.url" class="favorite-item-link" :to="item.url">
                  {{ item.label }}
                </RouterLink>
                <span v-else class="favorite-item-unavailable">{{ item.label }}</span>
                <small v-if="!item.is_available">No longer in the catalogue</small>
              </div>
              <button
                class="secondary-button"
                type="button"
                :disabled="working"
                @click="removeItem(item.id)"
              >
                Remove
              </button>
            </article>
          </div>
          <p v-else class="panel-copy favorite-empty-list">
            This list is empty. Use the Save button on a model card or detail page.
          </p>
        </template>
        <div v-else class="favorite-empty-list">
          <h2>Select a list</h2>
          <p class="panel-copy">Create a list to start organizing your catalogue.</p>
        </div>
      </section>
    </section>
  </main>
</template>
