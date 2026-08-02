<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from "vue"
import { RouterLink, useRoute, useRouter } from "vue-router"

import { ApiError, apiRequest } from "../api"
import AccountMenu from "../components/AccountMenu.vue"
import BrandLogo from "../components/BrandLogo.vue"
import FavoriteSaveDialog from "../components/FavoriteSaveDialog.vue"
import SearchableFilter from "../components/SearchableFilter.vue"
import TagChip from "../components/TagChip.vue"
import {
  favoriteTargetsForModel,
  type FavoriteListSummary,
  type FavoriteMembershipList,
  type FavoriteModelMembership,
  type FavoriteTarget,
} from "../favorites"
import { useAuthStore } from "../stores/auth"

interface ModelSummary {
  id: number
  name: string
  variant: string | null
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

interface PaginationItem {
  key: string
  page: number
}

function buildPaginationItems(
  currentPage: number,
  pageCount: number,
  siblingCount: number,
): PaginationItem[] {
  const visiblePages = new Set([1, pageCount])
  for (
    let pageNumber = currentPage - siblingCount;
    pageNumber <= currentPage + siblingCount;
    pageNumber += 1
  ) {
    if (pageNumber >= 1 && pageNumber <= pageCount) visiblePages.add(pageNumber)
  }

  const edgeRange = siblingCount * 2 + 3
  if (currentPage <= siblingCount + 2) {
    for (let pageNumber = 1; pageNumber <= Math.min(pageCount, edgeRange); pageNumber += 1) {
      visiblePages.add(pageNumber)
    }
  }
  if (currentPage >= pageCount - siblingCount - 1) {
    for (
      let pageNumber = Math.max(1, pageCount - edgeRange + 1);
      pageNumber <= pageCount;
      pageNumber += 1
    ) {
      visiblePages.add(pageNumber)
    }
  }

  const orderedPages = [...visiblePages].sort((left, right) => left - right)
  const items: PaginationItem[] = []
  orderedPages.forEach((pageNumber, index) => {
    const previousPage = orderedPages[index - 1]
    if (previousPage !== undefined && pageNumber - previousPage === 2) {
      items.push({ key: `page-${previousPage + 1}`, page: previousPage + 1 })
    } else if (previousPage !== undefined && pageNumber - previousPage > 2) {
      items.push({ key: `ellipsis-${previousPage}-${pageNumber}`, page: 0 })
    }
    items.push({ key: `page-${pageNumber}`, page: pageNumber })
  })
  return items
}

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const loading = ref(true)
const errorMessage = ref("")
const page = ref<ModelPage>({ items: [], total: 0, page: 1, page_size: 48 })
const favoriteModel = ref<ModelSummary | null>(null)
const favoriteDialogTargets = computed(() =>
  favoriteModel.value ? favoriteTargetsForModel(favoriteModel.value) : [],
)
const favoriteMemberships = ref<Record<number, FavoriteMembershipList[]>>({})
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
const catalogueQueryKeys = Object.keys(defaultQuery) as Array<
  keyof typeof defaultQuery
>
const routeDefinesCatalogueState =
  catalogueQueryKeys.some((key) => typeof route.query[key] === "string") ||
  typeof route.query.page === "string"
for (const key of catalogueQueryKeys) {
  const storedValue = routeDefinesCatalogueState
    ? undefined
    : storedState.query?.[key]
  if (typeof storedValue === "string") Object.assign(query, { [key]: storedValue })
  const value = route.query[key]
  if (typeof value === "string") Object.assign(query, { [key]: value })
}
if (query.sort === "newest") query.sort = "meshive_newest"
if (query.sort === "oldest") query.sort = "meshive_oldest"
const catalogueSearchOpen = ref(Boolean(query.search))
const catalogueSearchInput = ref<HTMLInputElement | null>(null)
const initialPage = Number(route.query.page || storedState.page || 1)
const totalPages = computed(() =>
  Math.max(1, Math.ceil(page.value.total / page.value.page_size)),
)
const paginationItems = computed(() =>
  buildPaginationItems(page.value.page, totalPages.value, 2),
)
const compactPaginationItems = computed(() =>
  buildPaginationItems(page.value.page, totalPages.value, 1),
)
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
    await loadFavoriteMemberships(page.value.items.map((model) => model.id))
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
  catalogueSearchOpen.value = false
}

async function toggleCatalogueSearch() {
  catalogueSearchOpen.value = !catalogueSearchOpen.value
  if (catalogueSearchOpen.value) {
    await nextTick()
    catalogueSearchInput.value?.focus()
  }
}

async function clearCatalogueSearch() {
  query.search = ""
  await nextTick()
  catalogueSearchInput.value?.focus()
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

async function loadFavoriteMemberships(modelIds: number[]) {
  if (!modelIds.length) {
    favoriteMemberships.value = {}
    return
  }
  const parameters = new URLSearchParams()
  modelIds.forEach((modelId) => parameters.append("model_ids", String(modelId)))
  try {
    const result = await apiRequest<FavoriteModelMembership[]>(
      `/api/favorite-lists/model-memberships?${parameters}`,
    )
    favoriteMemberships.value = Object.fromEntries(
      result.map((membership) => [membership.model_id, membership.lists]),
    )
  } catch {
    favoriteMemberships.value = {}
  }
}

function openFavoriteDialog(model: ModelSummary) {
  favoriteModel.value = model
}

function favoriteSaved(
  list: FavoriteListSummary,
  target: FavoriteTarget,
  itemId: number,
) {
  if (target.entity_type !== "model" || !target.model_id) return
  const memberships = favoriteMemberships.value[target.model_id] ?? []
  if (memberships.some((membership) => membership.id === list.id)) return
  favoriteMemberships.value = {
    ...favoriteMemberships.value,
    [target.model_id]: [...memberships, { ...list, item_id: itemId }],
  }
}

function favoriteRemoved(list: FavoriteMembershipList, target: FavoriteTarget) {
  if (target.entity_type !== "model" || !target.model_id) return
  favoriteMemberships.value = {
    ...favoriteMemberships.value,
    [target.model_id]: (favoriteMemberships.value[target.model_id] ?? []).filter(
      (membership) => membership.id !== list.id,
    ),
  }
}

async function handleFavoriteClick(model: ModelSummary) {
  const memberships = favoriteMemberships.value[model.id] ?? []
  if (memberships.length !== 1 || !memberships[0].item_id) {
    openFavoriteDialog(model)
    return
  }
  errorMessage.value = ""
  try {
    await apiRequest<void>(
      `/api/favorite-lists/${memberships[0].id}/items/${memberships[0].item_id}`,
      { method: "DELETE" },
    )
    favoriteRemoved(memberships[0], {
      key: `model:${model.id}`,
      label: model.name,
      entity_type: "model",
      model_id: model.id,
    })
  } catch (error) {
    errorMessage.value =
      error instanceof ApiError ? error.message : "Unable to remove the favorite"
  }
}

function favoriteButtonLabel(modelId: number) {
  const memberships = favoriteMemberships.value[modelId] ?? []
  if (!memberships.length) return "Save"
  if (memberships.length === 1) return memberships[0].name
  return `${memberships.length} lists`
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
      <div
        class="catalogue-search"
        :class="{
          'catalogue-search--open': catalogueSearchOpen,
          'catalogue-search--active': Boolean(query.search),
        }"
      >
        <button
          class="catalogue-search-toggle"
          type="button"
          :aria-expanded="catalogueSearchOpen"
          :aria-label="catalogueSearchOpen ? 'Close catalogue search' : 'Open catalogue search'"
          title="Search catalogue"
          @click="toggleCatalogueSearch"
        >
          <svg aria-hidden="true" viewBox="0 0 24 24">
            <circle cx="10.75" cy="10.75" r="6.75" />
            <path d="m16 16 4 4" />
          </svg>
        </button>
        <label v-if="catalogueSearchOpen" class="catalogue-search-field">
          <span class="sr-only">Search catalogue</span>
          <input
            ref="catalogueSearchInput"
            v-model="query.search"
            type="search"
            placeholder="Search catalogue"
            @keydown.esc="catalogueSearchOpen = false"
          >
        </label>
        <button
          v-if="catalogueSearchOpen && query.search"
          class="catalogue-search-clear"
          type="button"
          aria-label="Clear catalogue search"
          title="Clear catalogue search"
          @click="clearCatalogueSearch"
        >
          &times;
        </button>
      </div>

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
          <p v-if="model.variant" class="model-variant">
            Variant · {{ model.variant }}
          </p>
          <p class="model-creator">{{ model.creator || "Unknown creator" }}</p>
          <div v-if="model.tags.length" class="tag-list">
            <TagChip
              v-for="tag in model.tags"
              :key="tag.id"
              :color="tag.color"
              :description="tag.description"
            >{{ tag.name }}</TagChip>
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
            class="secondary-button model-favorite-button"
            :class="{
              'favorite-active': favoriteMemberships[model.id]?.length,
              'favorite-direct-remove': favoriteMemberships[model.id]?.length === 1,
            }"
            type="button"
            :title="favoriteMemberships[model.id]?.map((list) => list.name).join(', ')"
            @click="handleFavoriteClick(model)"
          >
            <span aria-hidden="true">
              {{ favoriteMemberships[model.id]?.length ? "♥" : "♡" }}
            </span>
            <span class="favorite-button-label">{{ favoriteButtonLabel(model.id) }}</span>
            <span
              v-if="favoriteMemberships[model.id]?.length === 1"
              class="favorite-button-hover-label"
            >Remove from list</span>
          </button>
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

    <nav v-if="totalPages > 1" class="pagination" aria-label="Catalogue pages">
      <span class="sr-only" aria-live="polite">
        Page {{ page.page }} of {{ totalPages }}
      </span>

      <div class="pagination-controls pagination-controls--previous">
        <button
          class="secondary-button pagination-button"
          type="button"
          :disabled="page.page <= 1"
          aria-label="Go to first page"
          title="First page"
          @click="loadCatalogue(1)"
        >
          <span aria-hidden="true">&laquo;</span>
        </button>
        <button
          class="secondary-button pagination-button"
          type="button"
          :disabled="page.page <= 1"
          aria-label="Go to previous page"
          title="Previous page"
          @click="loadCatalogue(page.page - 1)"
        >
          <span aria-hidden="true">&lsaquo;</span>
        </button>
      </div>

      <div class="pagination-pages pagination-pages--wide">
        <template v-for="item in paginationItems" :key="item.key">
          <button
            v-if="item.page"
            class="secondary-button pagination-button"
            :class="{ 'pagination-page--current': item.page === page.page }"
            type="button"
            :disabled="item.page === page.page"
            :aria-current="item.page === page.page ? 'page' : undefined"
            :aria-label="`Go to page ${item.page}`"
            @click="loadCatalogue(item.page)"
          >
            {{ item.page }}
          </button>
          <span v-else class="pagination-ellipsis" aria-hidden="true">&hellip;</span>
        </template>
      </div>

      <div class="pagination-pages pagination-pages--compact">
        <template v-for="item in compactPaginationItems" :key="item.key">
          <button
            v-if="item.page"
            class="secondary-button pagination-button"
            :class="{ 'pagination-page--current': item.page === page.page }"
            type="button"
            :disabled="item.page === page.page"
            :aria-current="item.page === page.page ? 'page' : undefined"
            :aria-label="`Go to page ${item.page}`"
            @click="loadCatalogue(item.page)"
          >
            {{ item.page }}
          </button>
          <span v-else class="pagination-ellipsis" aria-hidden="true">&hellip;</span>
        </template>
      </div>

      <div class="pagination-controls pagination-controls--next">
        <button
          class="secondary-button pagination-button"
          type="button"
          :disabled="page.page >= totalPages"
          aria-label="Go to next page"
          title="Next page"
          @click="loadCatalogue(page.page + 1)"
        >
          <span aria-hidden="true">&rsaquo;</span>
        </button>
        <button
          class="secondary-button pagination-button"
          type="button"
          :disabled="page.page >= totalPages"
          aria-label="Go to last page"
          title="Last page"
          @click="loadCatalogue(totalPages)"
        >
          <span aria-hidden="true">&raquo;</span>
        </button>
      </div>
    </nav>

    <FavoriteSaveDialog
      :open="Boolean(favoriteModel)"
      :targets="favoriteDialogTargets"
      :existing-model-lists="favoriteModel ? favoriteMemberships[favoriteModel.id] : []"
      @close="favoriteModel = null"
      @saved="favoriteSaved"
      @removed="favoriteRemoved"
    />
  </main>
</template>
