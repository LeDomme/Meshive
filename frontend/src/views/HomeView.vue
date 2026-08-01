<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue"
import { RouterLink, useRoute, useRouter } from "vue-router"

import { ApiError, apiRequest } from "../api"
import AccountMenu from "../components/AccountMenu.vue"
import BrandLogo from "../components/BrandLogo.vue"
import SearchableFilter from "../components/SearchableFilter.vue"
import { useAuthStore } from "../stores/auth"

interface ModelSummary {
  id: number
  name: string
  creator: string | null
  franchise: string | null
  series: string | null
  collection: string | null
  status: string
  source_id: number
  source_name: string
  archive_format: string | null
  archive_size_bytes: number | null
  archive_count: number
  thumbnail_url: string | null
  tags: Tag[]
}
interface Tag { id: number; name: string; color: string | null; description: string | null }

interface ModelPage {
  items: ModelSummary[]
  total: number
  page: number
  page_size: number
}

interface FilterOption {
  value: string
  count: number
}

interface SourceOption {
  id: number
  name: string
  count: number
}

interface CatalogueFilters {
  models: FilterOption[]
  creators: FilterOption[]
  franchises: FilterOption[]
  series: FilterOption[]
  collections: FilterOption[]
  sources: SourceOption[]
  statuses: FilterOption[]
  tags: Tag[]
}

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const loading = ref(true)
const errorMessage = ref("")
const page = ref<ModelPage>({ items: [], total: 0, page: 1, page_size: 48 })
const filters = ref<CatalogueFilters>({
  models: [],
  creators: [],
  franchises: [],
  series: [],
  collections: [],
  sources: [],
  statuses: [],
  tags: [],
})
const defaultQuery = {
  search: "",
  model: "",
  creator: "",
  franchise: "",
  series: "",
  collection: "",
  source_id: "",
  tag_id: "",
  sort: "name_asc",
}
const storedState = (() => {
  try {
    return JSON.parse(sessionStorage.getItem("meshive-catalogue-state") || "{}")
  } catch {
    return {}
  }
})()
const query = reactive({ ...defaultQuery })
for (const key of Object.keys(defaultQuery) as Array<keyof typeof defaultQuery>) {
  const storedValue = storedState.query?.[key]
  if (typeof storedValue === "string") Object.assign(query, { [key]: storedValue })
  const value = route.query[key]
  if (typeof value === "string") Object.assign(query, { [key]: value })
}
if (query.sort === "newest") query.sort = "meshive_newest"
if (query.sort === "oldest") query.sort = "meshive_oldest"
const initialPage = Number(route.query.page || storedState.page || 1)
const missingCount = computed(
  () => filters.value.statuses.find((item) => item.value === "missing")?.count ?? 0,
)
const sourceOptions = computed(() =>
  filters.value.sources.map((item) => ({
    value: String(item.id),
    label: item.name,
    count: item.count,
  })),
)
const tagOptions = computed(() =>
  filters.value.tags.map((tag) => ({ value: String(tag.id), label: tag.name })),
)
const sortOptions = [
  { value: "meshive_newest", label: "Meshive: newest added" },
  { value: "meshive_oldest", label: "Meshive: oldest added" },
  { value: "files_newest", label: "Files: newest modified" },
  { value: "files_oldest", label: "Files: oldest modified" },
  { value: "name_asc", label: "Name: A–Z" },
  { value: "name_desc", label: "Name: Z–A" },
  { value: "creator_asc", label: "Creator: A–Z" },
  { value: "creator_desc", label: "Creator: Z–A" },
]

async function loadCatalogue(targetPage = 1) {
  loading.value = true
  errorMessage.value = ""
  const parameters = new URLSearchParams({
    page: String(targetPage),
    page_size: "48",
  })
  for (const [key, value] of Object.entries(query)) {
    if (value) parameters.set(key, value)
  }
  sessionStorage.setItem(
    "meshive-catalogue-state",
    JSON.stringify({ query: { ...query }, page: targetPage }),
  )
  const locationQuery = Object.fromEntries(parameters.entries())
  delete locationQuery.page_size
  if (targetPage === 1) delete locationQuery.page
  void router.replace({ query: locationQuery })
  try {
    page.value = await apiRequest<ModelPage>(`/api/models?${parameters}`)
  } catch (error) {
    errorMessage.value =
      error instanceof ApiError ? error.message : "Unable to load the catalogue"
  } finally {
    loading.value = false
  }
}

let filterRequest = 0
type FacetKey =
  | "model"
  | "creator"
  | "franchise"
  | "series"
  | "collection"
  | "source_id"
  | "tag_id"
let lastChangedFacet: FacetKey | null = null

function facetChanged(key: FacetKey) {
  lastChangedFacet = key
}

function reconcileFacets(result: CatalogueFilters) {
  if (!lastChangedFacet) return
  const validValues: Record<FacetKey, Set<string>> = {
    model: new Set(result.models.map((item) => item.value)),
    creator: new Set(result.creators.map((item) => item.value)),
    franchise: new Set(result.franchises.map((item) => item.value)),
    series: new Set(result.series.map((item) => item.value)),
    collection: new Set(result.collections.map((item) => item.value)),
    source_id: new Set(result.sources.map((item) => String(item.id))),
    tag_id: new Set(result.tags.map((item) => String(item.id))),
  }
  for (const key of Object.keys(validValues) as FacetKey[]) {
    if (key !== lastChangedFacet && query[key] && !validValues[key].has(query[key])) {
      query[key] = ""
    }
  }
  lastChangedFacet = null
}

async function loadFilterOptions() {
  const request = ++filterRequest
  const parameters = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (key !== "sort" && value) parameters.set(key, value)
  }
  try {
    const result = await apiRequest<CatalogueFilters>(
      `/api/models/filters?${parameters}`,
    )
    if (request === filterRequest) {
      filters.value = result
      reconcileFacets(result)
    }
  } catch (error) {
    if (request === filterRequest) {
      errorMessage.value =
        error instanceof ApiError ? error.message : "Unable to load filters"
    }
  }
}

function clearFilters() {
  Object.assign(query, {
    search: "",
    model: "",
    creator: "",
    franchise: "",
    series: "",
    collection: "",
    source_id: "",
    tag_id: "",
  })
}

async function deleteMissingModel(model: ModelSummary) {
  if (
    !window.confirm(
      `Delete "${model.name}" from the Meshive database? No files will be deleted.`,
    )
  ) {
    return
  }
  errorMessage.value = ""
  try {
    await apiRequest<void>(`/api/admin/models/${model.id}`, { method: "DELETE" })
    await loadFilterOptions()
    const targetPage =
      page.value.items.length === 1 && page.value.page > 1
        ? page.value.page - 1
        : page.value.page
    await loadCatalogue(targetPage)
  } catch (error) {
    errorMessage.value =
      error instanceof ApiError ? error.message : "Unable to delete the model"
  }
}

async function deleteAllMissingModels() {
  if (
    !window.confirm(
      `Permanently delete all ${missingCount.value} missing models from the Meshive database? No source files will be deleted.`,
    )
  ) {
    return
  }
  errorMessage.value = ""
  try {
    await apiRequest<{ deleted: number }>("/api/admin/models/missing", {
      method: "DELETE",
    })
    await loadFilterOptions()
    await loadCatalogue(1)
  } catch (error) {
    errorMessage.value =
      error instanceof ApiError
        ? error.message
        : "Unable to delete missing models"
  }
}

function formatBytes(value: number | null) {
  if (value === null) return ""
  const units = ["B", "KB", "MB", "GB", "TB"]
  let size = value
  let unit = 0
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024
    unit += 1
  }
  return `${size.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`
}

let filterTimer: ReturnType<typeof setTimeout> | undefined
watch(
  query,
  () => {
    clearTimeout(filterTimer)
    filterTimer = setTimeout(
      () => void Promise.all([loadCatalogue(1), loadFilterOptions()]),
      250,
    )
  },
  { deep: true },
)

onMounted(async () => {
  await Promise.all([
    loadFilterOptions(),
    loadCatalogue(Number.isFinite(initialPage) && initialPage > 0 ? initialPage : 1),
  ])
})
</script>

<template>
  <main class="catalogue-shell">
    <header class="catalogue-header">
      <div class="catalogue-brand">
        <p class="eyebrow">Your 3D archive, indexed</p>
        <div class="catalogue-title-row">
          <BrandLogo />
          <h1 class="catalogue-title">Meshive</h1>
        </div>
      </div>
      <nav class="catalogue-nav">
        <RouterLink
          v-if="auth.user?.role === 'admin'"
          class="text-link"
          to="/admin/sources"
        >
          Administration
        </RouterLink>
        <RouterLink
          v-if="auth.user?.role === 'admin'"
          class="text-link"
          to="/admin/tags"
        >
          Tags
        </RouterLink>
        <AccountMenu />
      </nav>
    </header>

    <div class="catalogue-filters">
      <label class="search-field">
        <span class="sr-only">Search models</span>
        <input
          v-model="query.search"
          type="search"
          placeholder="Search"
        >
      </label>

      <SearchableFilter
        v-model="query.model"
        label="Model"
        all-label="All models"
        search-placeholder="Search models"
        :options="filters.models"
        @change="facetChanged('model')"
      />

      <SearchableFilter
        v-model="query.creator"
        label="Creator"
        all-label="All creators"
        search-placeholder="Search creators"
        :options="filters.creators"
        @change="facetChanged('creator')"
      />

      <SearchableFilter
        v-model="query.franchise"
        label="Franchise"
        all-label="All franchises"
        search-placeholder="Search franchises"
        :options="filters.franchises"
        @change="facetChanged('franchise')"
      />

      <SearchableFilter
        v-model="query.series"
        label="Series"
        all-label="All series"
        search-placeholder="Search series"
        :options="filters.series"
        @change="facetChanged('series')"
      />

      <SearchableFilter
        v-model="query.collection"
        label="Collection"
        all-label="All collections"
        search-placeholder="Search collections"
        :options="filters.collections"
        @change="facetChanged('collection')"
      />

      <SearchableFilter
        v-model="query.source_id"
        label="Library source"
        all-label="All sources"
        search-placeholder="Search sources"
        align="end"
        :options="sourceOptions"
        @change="facetChanged('source_id')"
      />

      <SearchableFilter
        v-model="query.tag_id"
        label="Tag"
        all-label="All tags"
        search-placeholder="Search tags"
        align="end"
        :options="tagOptions"
        @change="facetChanged('tag_id')"
      />

      <SearchableFilter
        v-model="query.sort"
        label="Sort models"
        all-label="Default sorting"
        search-placeholder="Search sorting"
        align="end"
        :show-all-option="false"
        :options="sortOptions"
      />

      <button class="secondary-button" type="button" @click="clearFilters">Clear</button>
    </div>

    <div class="catalogue-meta">
      <p>{{ page.total }} {{ page.total === 1 ? "model" : "models" }}</p>
      <button
        v-if="auth.user?.role === 'admin' && missingCount > 0"
        class="danger-button"
        type="button"
        @click="deleteAllMissingModels"
      >
        Delete all missing ({{ missingCount }})
      </button>
      <p v-if="loading">Loading…</p>
    </div>

    <p v-if="errorMessage" class="form-error error-panel" role="alert">
      {{ errorMessage }}
    </p>

    <section v-if="page.items.length" class="model-grid">
      <article v-for="model in page.items" :key="model.id" class="model-card">
        <RouterLink
          class="thumbnail-frame"
          :to="{ name: 'model-detail', params: { id: model.id } }"
        >
          <img
            v-if="model.thumbnail_url"
            :src="model.thumbnail_url"
            :alt="model.name"
            loading="lazy"
          >
          <div v-else class="thumbnail-placeholder">No preview</div>
          <span v-if="model.status !== 'available'" class="model-status">
            {{ model.status }}
          </span>
        </RouterLink>
        <div class="model-card-body">
          <p class="model-franchise">
            {{ [model.franchise || model.collection, model.series]
              .filter((value, index, values) => value && values.indexOf(value) === index)
              .join(" · ") || model.source_name }}
          </p>
          <h2>
            <RouterLink
              class="model-title-link"
              :to="{ name: 'model-detail', params: { id: model.id } }"
            >
              {{ model.name }}
            </RouterLink>
          </h2>
          <p class="model-creator">{{ model.creator || "Unknown creator" }}</p>
          <div v-if="model.tags.length" class="tag-list">
            <span
              v-for="tag in model.tags"
              :key="tag.id"
              class="tag-chip"
              :style="{ '--tag-color': tag.color || '#5eead4' }"
            >{{ tag.name }}</span>
          </div>
          <p class="archive-meta">
            <span v-if="model.archive_count > 1">
              {{ model.archive_count }} archives
            </span>
            <span v-else-if="model.archive_format">
              {{ model.archive_format.toUpperCase() }}
            </span>
            <span v-if="model.archive_size_bytes">
              {{ formatBytes(model.archive_size_bytes) }}
            </span>
          </p>
          <button
            v-if="auth.user?.role === 'admin' && model.status === 'missing'"
            class="danger-button model-delete-button"
            type="button"
            @click="deleteMissingModel(model)"
          >
            Delete from database
          </button>
        </div>
      </article>
    </section>

    <section v-else-if="!loading" class="empty-catalogue">
      <h2>No models found</h2>
      <p>Run a source scan or adjust the active filters.</p>
    </section>

    <nav v-if="page.total > page.page_size" class="pagination" aria-label="Pagination">
      <button
        class="secondary-button"
        type="button"
        :disabled="page.page <= 1"
        @click="loadCatalogue(page.page - 1)"
      >
        Previous
      </button>
      <span>Page {{ page.page }}</span>
      <button
        class="secondary-button"
        type="button"
        :disabled="page.page * page.page_size >= page.total"
        @click="loadCatalogue(page.page + 1)"
      >
        Next
      </button>
    </nav>
  </main>
</template>
