<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { RouterLink } from "vue-router"

import { ApiError, apiRequest } from "../api"
import AccountMenu from "../components/AccountMenu.vue"
import BrandLogo from "../components/BrandLogo.vue"
import SearchableFilter from "../components/SearchableFilter.vue"
import type {
  FavoriteEntityType,
  FavoriteListDetail,
  FavoriteListItem,
  FavoriteListSummary,
} from "../favorites"

type DirectFavoriteType = "creator" | "franchise" | "series" | "collection" | "tag"
interface FilterOption { value: string; count: number }
interface TagOption { id: number; name: string }
interface CatalogueFilters {
  creators: FilterOption[]
  franchises: FilterOption[]
  series: FilterOption[]
  collections: FilterOption[]
  tags: TagOption[]
}

const lists = ref<FavoriteListSummary[]>([])
const selected = ref<FavoriteListDetail | null>(null)
const selectedListId = ref(0)
const newListName = ref("")
const renameValue = ref("")
const loading = ref(true)
const working = ref(false)
const errorMessage = ref("")
const successMessage = ref("")
const catalogueFilters = ref<CatalogueFilters>({
  creators: [],
  franchises: [],
  series: [],
  collections: [],
  tags: [],
})
const directFavoriteType = ref<DirectFavoriteType>("creator")
const directFavoriteTypeValue = computed({
  get: () => directFavoriteType.value,
  set: (value: string) => {
    directFavoriteType.value = value as DirectFavoriteType
  },
})
const directFavoriteValue = ref("")
const directFavoriteTypeOptions = [
  { value: "creator", label: "Creator" },
  { value: "franchise", label: "Franchise" },
  { value: "series", label: "Series" },
  { value: "collection", label: "Collection" },
  { value: "tag", label: "Tag" },
]

const directFavoriteOptions = computed(() => {
  if (directFavoriteType.value === "tag") {
    return catalogueFilters.value.tags.map((tag) => ({
      value: String(tag.id),
      label: tag.name,
    }))
  }
  const key: "creators" | "franchises" | "series" | "collections" =
    directFavoriteType.value === "series"
      ? "series"
      : `${directFavoriteType.value}s` as
          | "creators"
          | "franchises"
          | "collections"
  return catalogueFilters.value[key]
})

const directFavoriteLabel = computed(() =>
  directFavoriteType.value === "series"
    ? "Series"
    : `${directFavoriteType.value[0].toUpperCase()}${directFavoriteType.value.slice(1)}`,
)

function favoritePreview(item: FavoriteListItem) {
  if (item.thumbnail_url) return item.thumbnail_url
  if (item.artwork_url) return item.artwork_url
  if (["creator", "franchise", "series", "collection", "tag"].includes(item.entity_type)) {
    return `/favorite-fallbacks/favorite-${item.entity_type}.webp`
  }
  return null
}

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

function directFavoriteTypeChanged() {
  directFavoriteValue.value = ""
}

async function addDirectFavorite() {
  if (!selected.value || !directFavoriteValue.value) return
  working.value = true
  errorMessage.value = ""
  successMessage.value = ""
  try {
    const payload: {
      entity_type: FavoriteEntityType
      value?: string
      tag_id?: number
    } = { entity_type: directFavoriteType.value }
    if (directFavoriteType.value === "tag") {
      payload.tag_id = Number(directFavoriteValue.value)
    } else {
      payload.value = directFavoriteValue.value
    }
    await apiRequest<FavoriteListItem>(
      `/api/favorite-lists/${selected.value.id}/items`,
      { method: "POST", body: JSON.stringify(payload) },
    )
    const selectedOption = directFavoriteOptions.value.find(
      (option) => option.value === directFavoriteValue.value,
    )
    const label = selectedOption && "label" in selectedOption
      ? selectedOption.label
      : selectedOption?.value ?? directFavoriteValue.value
    directFavoriteValue.value = ""
    await loadLists(selected.value.id)
    successMessage.value = `Added ${label} to ${selected.value.name}.`
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : "Unable to add the entry"
  } finally {
    working.value = false
  }
}

onMounted(async () => {
  try {
    const [, filterResult] = await Promise.all([
      loadLists(),
      apiRequest<CatalogueFilters>("/api/models/filters"),
    ])
    catalogueFilters.value = filterResult
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : "Unable to load favorite lists"
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <main class="favorites-shell">
    <header class="account-page-header favorites-header">
      <div class="admin-brand">
        <p class="eyebrow">Private to your account</p>
        <div class="admin-title-row">
          <BrandLogo />
          <h1 class="admin-title">Favorite lists</h1>
        </div>
      </div>
      <nav class="admin-nav" aria-label="Favorite list navigation">
        <RouterLink class="text-link" to="/">Back to Meshive</RouterLink>
        <AccountMenu />
      </nav>
    </header>

    <p class="favorites-intro">
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

          <form class="favorite-direct-add" @submit.prevent="addDirectFavorite">
            <div>
              <h3>Add catalogue entry</h3>
              <p class="panel-copy">
                Add a creator, franchise, series, collection, or tag without opening a model first.
              </p>
            </div>
            <div class="favorite-direct-add-fields">
              <div class="matched-dropdown-field">
                <span>Type</span>
                <SearchableFilter
                  v-model="directFavoriteTypeValue"
                  label="Favorite type"
                  all-label="Select a type"
                  search-placeholder="Search types"
                  :options="directFavoriteTypeOptions"
                  :show-all-option="false"
                  @change="directFavoriteTypeChanged"
                />
              </div>
              <div class="matched-dropdown-field">
                <span>{{ directFavoriteLabel }}</span>
                <SearchableFilter
                  v-model="directFavoriteValue"
                  :label="directFavoriteLabel"
                  :all-label="`Select ${directFavoriteLabel.toLocaleLowerCase()}`"
                  :search-placeholder="`Search ${directFavoriteLabel.toLocaleLowerCase()}`"
                  :options="directFavoriteOptions"
                />
              </div>
              <button
                class="primary-button"
                type="submit"
                :disabled="working || !directFavoriteValue"
              >Add</button>
            </div>
          </form>

          <div v-if="selected.items.length" class="favorite-items">
            <article
              v-for="item in selected.items"
              :key="item.id"
              class="favorite-item"
              :class="{ 'favorite-item--model': item.entity_type === 'model' }"
            >
              <RouterLink
                v-if="item.url"
                class="favorite-item-preview"
                :to="item.url"
                :aria-label="`Open ${item.label}`"
              >
                <img
                  v-if="favoritePreview(item)"
                  class="favorite-item-preview-backdrop"
                  :src="favoritePreview(item) || ''"
                  alt=""
                  aria-hidden="true"
                  loading="lazy"
                >
                <img
                  v-if="favoritePreview(item)"
                  class="favorite-item-preview-image"
                  :src="favoritePreview(item) || ''"
                  :alt="item.label"
                  loading="lazy"
                >
                <span v-else class="favorite-item-symbol" aria-hidden="true">
                  {{ item.entity_type === "model" ? "♡" : item.entity_type[0].toUpperCase() }}
                </span>
                <span v-if="item.status && item.status !== 'available'" class="model-status">
                  {{ item.status }}
                </span>
              </RouterLink>
              <div v-else class="favorite-item-preview favorite-item-preview--unavailable">
                <img
                  v-if="favoritePreview(item)"
                  class="favorite-item-preview-backdrop"
                  :src="favoritePreview(item) || ''"
                  alt=""
                  aria-hidden="true"
                  loading="lazy"
                >
                <img
                  v-if="favoritePreview(item)"
                  class="favorite-item-preview-image"
                  :src="favoritePreview(item) || ''"
                  :alt="item.label"
                  loading="lazy"
                >
                <span v-else class="favorite-item-symbol" aria-hidden="true">&#9825;</span>
              </div>

              <div class="favorite-item-body">
                <span class="favorite-item-type">{{ item.entity_type }}</span>
                <RouterLink v-if="item.url" class="favorite-item-link" :to="item.url">
                  {{ item.label }}
                </RouterLink>
                <span v-else class="favorite-item-unavailable">{{ item.label }}</span>
                <span v-if="item.entity_type === 'model' && item.creator" class="favorite-item-meta">
                  {{ item.creator }}
                </span>
                <span
                  v-if="item.entity_type === 'model' && (item.franchise || item.series || item.collection)"
                  class="favorite-item-meta"
                >
                  {{ [item.franchise, item.series, item.collection]
                    .filter((value, index, values) => value && values.indexOf(value) === index)
                    .join(" · ") }}
                </span>
                <small v-if="!item.is_available">No longer in the catalogue</small>
              </div>
              <button
                class="secondary-button favorite-item-remove favorite-active favorite-direct-remove"
                type="button"
                :disabled="working"
                @click="removeItem(item.id)"
              >
                <span aria-hidden="true">&#9829;</span>
                <span class="favorite-button-label">Saved</span>
                <span class="favorite-button-hover-label">Remove from list</span>
              </button>
            </article>
          </div>
          <p v-else class="panel-copy favorite-empty-list">
            This list is empty. Add a catalogue entry above or use Save on a model.
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
