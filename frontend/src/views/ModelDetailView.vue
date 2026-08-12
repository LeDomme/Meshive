<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { RouterLink, useRoute, useRouter } from "vue-router"

import { ApiError, apiRequest } from "../api"
import FavoriteSaveDialog from "../components/FavoriteSaveDialog.vue"
import TagChip from "../components/TagChip.vue"
import {
  favoriteTargetsForModel,
  type FavoriteListSummary,
  type FavoriteMembershipList,
  type FavoriteModelMembership,
  type FavoriteTarget,
} from "../favorites"
import { useAuthStore } from "../stores/auth"

interface Tag { id: number; name: string; color: string | null; description: string | null }

interface ModelImage {
  id: number
  filename: string
  format: string
  size_bytes: number
  is_primary: boolean
  url: string
}

interface ArchiveEntry {
  path: string
  name: string
  is_directory: boolean
  size_bytes: number | null
  compressed_size_bytes: number | null
  modified_at: string | null
}

interface ModelArchive {
  id: number
  filename: string
  format: string
  size_bytes: number
  status: string
  entry_count: number
  uncompressed_size_bytes: number
  error_message: string | null
  download_url: string
  entries: ArchiveEntry[]
}

interface ModelDetail {
  id: number
  name: string
  variant: string | null
  creator: string | null
  creator_links: Array<{
    id: number
    kind: string
    label: string
    url: string
  }>
  franchise: string | null
  series: string | null
  collection: string | null
  status: string
  source_id: number
  source_name: string
  relative_path: string
  images: ModelImage[]
  archives: ModelArchive[]
  archive_bundle_download_url: string | null
  tags: Tag[]
}

interface ModelNavigationItem {
  id: number
  name: string
  variant: string | null
}

interface ModelNavigation {
  previous: ModelNavigationItem | null
  next: ModelNavigationItem | null
}

interface ArchiveTreeNode {
  key: string
  name: string
  depth: number
  isDirectory: boolean
  entry: ArchiveEntry | null
  children: ArchiveTreeNode[]
}

type CatalogueFilterKey =
  | "model"
  | "creator"
  | "franchise"
  | "series"
  | "collection"
  | "source_id"
  | "tag_id"

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const model = ref<ModelDetail | null>(null)
const availableTags = ref<Tag[]>([])
const selectedTagId = ref("")
const loading = ref(true)
const errorMessage = ref("")
const selectedImage = ref<ModelImage | null>(null)
const pictureNotice = ref("")
const rescanInProgress = ref(false)
const archiveFilter = ref("")
const selectedArchiveIndex = ref(0)
const collapsedFolders = ref<Set<string>>(new Set())
const lightboxOpen = ref(false)
const favoriteDialogOpen = ref(false)
const favoriteMemberships = ref<FavoriteMembershipList[]>([])
const lightboxMode = ref<"height" | "width" | "original">("height")
const detailImageButton = ref<HTMLButtonElement | null>(null)
const lightboxCloseButton = ref<HTMLButtonElement | null>(null)
const navigation = ref<ModelNavigation | null>(null)
const thumbnailStrip = ref<HTMLDivElement | null>(null)
let thumbnailDragStartX = 0
let thumbnailDragStartScrollLeft = 0
const thumbnailDragActive = ref(false)
let thumbnailDragMoved = false
let imageSwipeStartX = 0
let imageSwipeStartY = 0
const imageSwipeOffset = ref(0)
const imageSwipeActive = ref(false)
let suppressDetailImageClick = false

const modelFallbackUrl = computed(() => {
  if (!model.value) return ""
  const number = String(((model.value.id - 1) % 10) + 1).padStart(2, "0")
  return `/model-fallbacks/fallback-model-${number}.webp`
})

const imageFrameStyle = computed(() => ({
  "--detail-image": `url("${(selectedImage.value?.url || modelFallbackUrl.value).replaceAll('"', '\\"')}")`,
}))
const imageSwipeStyle = computed(() => ({
  "--image-swipe-offset": `${imageSwipeOffset.value}px`,
}))
const currentArchive = computed(
  () => model.value?.archives[selectedArchiveIndex.value] ?? null,
)
const favoriteDialogTargets = computed(() =>
  model.value ? favoriteTargetsForModel(model.value) : [],
)

const archiveTree = computed(() => {
  const root: ArchiveTreeNode = {
    key: "",
    name: "",
    depth: -1,
    isDirectory: true,
    entry: null,
    children: [],
  }
  const nodes = new Map<string, ArchiveTreeNode>([["", root]])

  for (const entry of currentArchive.value?.entries ?? []) {
    const parts = entry.path.replaceAll("\\", "/").split("/").filter(Boolean)
    let parent = root
    let path = ""
    parts.forEach((part, index) => {
      path = path ? `${path}/${part}` : part
      let node = nodes.get(path)
      const isLast = index === parts.length - 1
      if (!node) {
        node = {
          key: path,
          name: part,
          depth: index,
          isDirectory: !isLast || entry.is_directory,
          entry: isLast ? entry : null,
          children: [],
        }
        nodes.set(path, node)
        parent.children.push(node)
      } else if (isLast) {
        node.entry = entry
        node.isDirectory = entry.is_directory
      }
      parent = node
    })
  }

  const sortNodes = (nodesToSort: ArchiveTreeNode[]) => {
    nodesToSort.sort(
      (left, right) =>
        Number(right.isDirectory) - Number(left.isDirectory) ||
        left.name.localeCompare(right.name, undefined, { sensitivity: "base" }),
    )
    nodesToSort.forEach((node) => sortNodes(node.children))
  }
  sortNodes(root.children)
  return root.children
})

const visibleTreeRows = computed(() => {
  const search = archiveFilter.value.trim().toLocaleLowerCase()
  const rows: ArchiveTreeNode[] = []

  const hasMatch = (node: ArchiveTreeNode): boolean =>
    node.key.toLocaleLowerCase().includes(search) ||
    node.children.some((child) => hasMatch(child))

  const visit = (nodes: ArchiveTreeNode[]) => {
    for (const node of nodes) {
      if (search && !hasMatch(node)) continue
      rows.push(node)
      if (
        node.isDirectory &&
        (search || !collapsedFolders.value.has(node.key))
      ) {
        visit(node.children)
      }
    }
  }
  visit(archiveTree.value)
  return rows
})

function toggleFolder(path: string) {
  const next = new Set(collapsedFolders.value)
  if (next.has(path)) next.delete(path)
  else next.add(path)
  collapsedFolders.value = next
}

function selectAdjacentImage(direction: -1 | 1) {
  const images = model.value?.images ?? []
  if (images.length < 2) return
  const currentIndex = Math.max(
    0,
    images.findIndex((image) => image.id === selectedImage.value?.id),
  )
  selectedImage.value = images[(currentIndex + direction + images.length) % images.length]
}

function startImageSwipe(event: PointerEvent) {
  if (event.pointerType === "mouse" && event.button !== 0) return
  imageSwipeStartX = event.clientX
  imageSwipeStartY = event.clientY
  imageSwipeOffset.value = 0
  imageSwipeActive.value = true
}

function moveImageSwipe(event: PointerEvent) {
  if (!imageSwipeActive.value) return
  const horizontalDistance = event.clientX - imageSwipeStartX
  const verticalDistance = event.clientY - imageSwipeStartY
  if (Math.abs(verticalDistance) > Math.abs(horizontalDistance)) return
  imageSwipeOffset.value = Math.max(-96, Math.min(96, horizontalDistance))
}

function endImageSwipe(event: PointerEvent) {
  if (!imageSwipeActive.value) return
  const target = event.currentTarget as HTMLElement
  if (target.hasPointerCapture(event.pointerId)) target.releasePointerCapture(event.pointerId)
  const horizontalDistance = event.clientX - imageSwipeStartX
  const verticalDistance = event.clientY - imageSwipeStartY
  imageSwipeActive.value = false
  imageSwipeOffset.value = 0
  if (Math.abs(horizontalDistance) < 48 || Math.abs(horizontalDistance) <= Math.abs(verticalDistance)) return
  suppressDetailImageClick = true
  selectAdjacentImage(horizontalDistance < 0 ? 1 : -1)
  window.setTimeout(() => { suppressDetailImageClick = false }, 0)
}
function scrollThumbnailStrip(direction: -1 | 1) {
  thumbnailStrip.value?.scrollBy({ left: direction * 320, behavior: "smooth" })
}

function selectThumbnail(image: ModelImage) {
  if (thumbnailDragMoved) return
  selectedImage.value = image
  void nextTick(() => {
    thumbnailStrip.value?.querySelector<HTMLElement>(`[data-image-id="${image.id}"]`)
      ?.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "nearest" })
  })
}

function startThumbnailDrag(event: PointerEvent) {
  if (!thumbnailStrip.value || event.button !== 0) return
  thumbnailDragStartX = event.clientX
  thumbnailDragStartScrollLeft = thumbnailStrip.value.scrollLeft
  thumbnailDragActive.value = true
  thumbnailDragMoved = false
  thumbnailStrip.value.setPointerCapture(event.pointerId)
}

function moveThumbnailDrag(event: PointerEvent) {
  if (!thumbnailDragActive.value || !thumbnailStrip.value) return
  const distance = event.clientX - thumbnailDragStartX
  if (Math.abs(distance) > 4) {
    thumbnailDragMoved = true
    if (!thumbnailStrip.value.hasPointerCapture(event.pointerId)) {
      thumbnailStrip.value.setPointerCapture(event.pointerId)
    }
    event.preventDefault()
  }
  thumbnailStrip.value.scrollLeft = thumbnailDragStartScrollLeft - distance
}

function endThumbnailDrag(event: PointerEvent) {
  if (!thumbnailDragActive.value || !thumbnailStrip.value) return
  thumbnailDragActive.value = false
  if (thumbnailStrip.value.hasPointerCapture(event.pointerId)) {
    thumbnailStrip.value.releasePointerCapture(event.pointerId)
  }
  window.setTimeout(() => { thumbnailDragMoved = false }, 0)
}
async function setPrimaryImage(image: ModelImage) {
  if (!model.value || image.is_primary) return
  errorMessage.value = ""
  pictureNotice.value = ""
  try {
    await apiRequest(`/api/admin/models/${model.value.id}/images/${image.id}/primary`, {
      method: "PUT",
    })
    model.value.images.forEach((candidate) => {
      candidate.is_primary = candidate.id === image.id
    })
    selectedImage.value = image
    pictureNotice.value = "Primary picture saved."
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : "Unable to save primary picture"
  }
}

async function resetPictures() {
  if (!model.value) return
  if (!window.confirm("Reset all Meshive picture records for this model? Re-scan the source to rebuild them.")) {
    return
  }
  errorMessage.value = ""
  pictureNotice.value = ""
  try {
    const result = await apiRequest<{ deleted: number }>(
      `/api/admin/models/${model.value.id}/images`,
      { method: "DELETE" },
    )
    model.value.images = []
    selectedImage.value = null
    pictureNotice.value = `${result.deleted} picture record${result.deleted === 1 ? "" : "s"} reset. Re-scan the source to rebuild previews.`
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : "Unable to reset pictures"
  }
}

async function rescanCurrentModel(forceImageRebuild = false) {
  if (!model.value || rescanInProgress.value) return
  if (
    forceImageRebuild
    && !window.confirm(
      "Rebuild all Meshive archive images for this model? The source library remains read-only.",
    )
  ) {
    return
  }

  errorMessage.value = ""
  pictureNotice.value = ""
  rescanInProgress.value = true
  try {
    const action = forceImageRebuild ? "rebuild-images" : "rescan"
    await apiRequest(`/api/admin/models/${model.value.id}/${action}`, { method: "POST" })
    await loadModel()
    pictureNotice.value = forceImageRebuild
      ? "Archive images rebuilt for this model."
      : "Model rescan completed."
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : "Unable to rescan model"
  } finally {
    rescanInProgress.value = false
  }
}
function selectArchive(index: number) {
  selectedArchiveIndex.value = index
  archiveFilter.value = ""
  collapsedFolders.value = new Set()
}

async function openLightbox() {
  if (!selectedImage.value || suppressDetailImageClick) return
  lightboxMode.value = "height"
  lightboxOpen.value = true
  document.documentElement.style.overflow = "hidden"
  await nextTick()
  lightboxCloseButton.value?.focus()
}

function closeLightbox() {
  lightboxOpen.value = false
  document.documentElement.style.overflow = ""
  nextTick(() => detailImageButton.value?.focus())
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === "Escape" && lightboxOpen.value) closeLightbox()
  if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return
  const target = event.target as HTMLElement | null
  if (!lightboxOpen.value && target?.matches("input, select, textarea")) return
  if ((model.value?.images.length ?? 0) < 2) return
  event.preventDefault()
  selectAdjacentImage(event.key === "ArrowLeft" ? -1 : 1)
}

function formatBytes(value: number | null) {
  if (value === null) return "—"
  const units = ["B", "KB", "MB", "GB", "TB"]
  let size = value
  let unit = 0
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024
    unit += 1
  }
  return `${size.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`
}

function catalogueFilterLink(
  key: CatalogueFilterKey,
  value: string | number | null,
) {
  return {
    name: "home",
    query: { [key]: String(value) },
  }
}

function navigationParameters() {
  const parameters = new URLSearchParams()
  for (const key of [
    "search",
    "model",
    "creator",
    "franchise",
    "series",
    "collection",
    "tag_id",
    "source_id",
    "status",
    "sort",
  ]) {
    const value = route.query[key]
    if (typeof value === "string" && value) parameters.set(key, value)
  }
  return parameters
}

function navigationRoute(modelId: number) {
  return {
    name: "model-detail",
    params: { id: modelId },
    query: route.query,
  }
}

function navigateModel(target: ModelNavigationItem | null) {
  if (target) void router.push(navigationRoute(target.id))
}

async function loadNavigation(modelId: number) {
  const parameters = navigationParameters()
  const suffix = parameters.size ? `?${parameters}` : ""
  navigation.value = await apiRequest<ModelNavigation>(
    `/api/models/${modelId}/navigation${suffix}`,
  )
}

function favoriteButtonLabel() {
  if (!favoriteMemberships.value.length) return "Save to favorites"
  if (favoriteMemberships.value.length === 1) {
    return `Saved in ${favoriteMemberships.value[0].name}`
  }
  return `Saved in ${favoriteMemberships.value.length} lists`
}

async function loadFavoriteMemberships(modelId: number) {
  try {
    const result = await apiRequest<FavoriteModelMembership[]>(
      `/api/favorite-lists/model-memberships?model_ids=${modelId}`,
    )
    favoriteMemberships.value = result[0]?.lists ?? []
  } catch {
    favoriteMemberships.value = []
  }
}

function favoriteSaved(
  list: FavoriteListSummary,
  target: FavoriteTarget,
  itemId: number,
) {
  if (target.entity_type !== "model") return
  if (favoriteMemberships.value.some((membership) => membership.id === list.id)) return
  favoriteMemberships.value = [
    ...favoriteMemberships.value,
    { id: list.id, name: list.name, item_id: itemId },
  ]
}

function favoriteRemoved(list: FavoriteMembershipList, target: FavoriteTarget) {
  if (target.entity_type !== "model") return
  favoriteMemberships.value = favoriteMemberships.value.filter(
    (membership) => membership.id !== list.id,
  )
}

async function handleFavoriteClick() {
  const membership = favoriteMemberships.value[0]
  if (favoriteMemberships.value.length !== 1 || !membership?.item_id || !model.value) {
    favoriteDialogOpen.value = true
    return
  }
  errorMessage.value = ""
  try {
    await apiRequest<void>(
      `/api/favorite-lists/${membership.id}/items/${membership.item_id}`,
      { method: "DELETE" },
    )
    favoriteMemberships.value = []
  } catch (error) {
    errorMessage.value =
      error instanceof ApiError ? error.message : "Unable to remove the favorite"
  }
}

async function addTag() {
  if (!model.value || !selectedTagId.value) return
  await apiRequest<void>(
    `/api/admin/models/${model.value.id}/tags/${selectedTagId.value}`,
    { method: "PUT" },
  )
  model.value = await apiRequest<ModelDetail>(`/api/models/${route.params.id}`)
  selectedTagId.value = ""
}

async function removeTag(tag: Tag) {
  if (!model.value) return
  await apiRequest<void>(`/api/admin/models/${model.value.id}/tags/${tag.id}`, {
    method: "DELETE",
  })
  model.value = await apiRequest<ModelDetail>(`/api/models/${route.params.id}`)
}

async function loadModel() {
  loading.value = true
  errorMessage.value = ""
  navigation.value = null
  try {
    const modelId = String(route.params.id)
    const [detail, tags] = await Promise.all([
      apiRequest<ModelDetail>(`/api/models/${modelId}`),
      apiRequest<Tag[]>("/api/tags"),
    ])
    model.value = detail
    availableTags.value = tags
    selectedImage.value = model.value.images[0] ?? null
    await Promise.all([
      loadFavoriteMemberships(model.value.id),
      loadNavigation(model.value.id),
    ])
  } catch (error) {
    errorMessage.value =
      error instanceof ApiError ? error.message : "Unable to load the model"
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  window.addEventListener("keydown", handleKeydown)
  void loadModel()
})

watch(() => route.params.id, () => void loadModel())

onBeforeUnmount(() => {
  window.removeEventListener("keydown", handleKeydown)
  document.documentElement.style.overflow = ""
})
</script>

<template>
  <main class="detail-shell">
    <RouterLink
      class="text-link detail-back"
      :to="{ name: 'home', query: route.query }"
    >← Back to catalogue</RouterLink>

    <p v-if="loading" class="muted">Loading…</p>
    <p v-else-if="errorMessage" class="form-error error-panel" role="alert">
      {{ errorMessage }}
    </p>

    <template v-else-if="model">
      <header class="detail-header">
        <div>
          <p class="eyebrow">{{ model.source_name }}</p>
          <h1>{{ model.name }}</h1>
          <p v-if="model.variant" class="detail-variant">
            Variant · {{ model.variant }}
          </p>
          <p class="detail-taxonomy">
            {{ [model.franchise, model.series, model.collection]
              .filter((value, index, values) => value && values.indexOf(value) === index)
              .join(" · ") || "Uncategorised" }}
          </p>
        </div>
        <div class="detail-header-actions">
          <nav
            v-if="navigation"
            class="detail-model-navigation"
            aria-label="Catalogue model navigation"
          >
            <button
              class="detail-model-navigation-button"
              type="button"
              :disabled="!navigation.previous"
              :title="navigation.previous ? `Previous: ${navigation.previous.name}` : 'No previous model'"
              aria-label="Previous model"
              @click="navigateModel(navigation.previous)"
            >&#8249;</button>
            <button
              class="detail-model-navigation-button"
              type="button"
              :disabled="!navigation.next"
              :title="navigation.next ? `Next: ${navigation.next.name}` : 'No next model'"
              aria-label="Next model"
              @click="navigateModel(navigation.next)"
            >&#8250;</button>
          </nav>
          <span v-if="model.status !== 'available'" class="detail-status">
            {{ model.status }}
          </span>
          <button
            class="secondary-button detail-favorite-button"
            :class="{
              'favorite-add-ready': !favoriteMemberships.length,
              'favorite-active': favoriteMemberships.length,
              'favorite-direct-remove': favoriteMemberships.length === 1,
            }"
            type="button"
            :title="favoriteMemberships.map((list) => list.name).join(', ')"
            @click="handleFavoriteClick"
          >
            <span aria-hidden="true">{{ favoriteMemberships.length ? "♥" : "♡" }}</span>
            <span class="favorite-button-label">{{ favoriteButtonLabel() }}</span>
            <span
              v-if="!favoriteMemberships.length"
              class="favorite-button-hover-label"
            >Choose a list</span>
            <span
              v-else-if="favoriteMemberships.length === 1"
              class="favorite-button-hover-label"
            >Remove from list</span>
          </button>
        </div>
      </header>
      <section class="detail-grid">
        <div class="panel image-gallery">
          <div class="detail-image-frame" :class="{ 'is-swiping': imageSwipeActive }" :style="[imageFrameStyle, imageSwipeStyle]" @pointerdown="startImageSwipe" @pointermove="moveImageSwipe" @pointerup="endImageSwipe" @pointercancel="endImageSwipe">
            <button
              v-if="model.images.length > 1"
              class="gallery-nav gallery-nav-previous"
              type="button"
              aria-label="Previous picture"
              @click.stop="selectAdjacentImage(-1)"
            >
              ‹
            </button>
            <button
              v-if="selectedImage"
              ref="detailImageButton"
              class="detail-image-button"
              type="button"
              aria-label="Open image viewer"
              @click="openLightbox"
            >
              <img
                :src="selectedImage.url"
                :alt="`${model.name} — ${selectedImage.filename}`"
              >
              <span class="image-open-hint">View full image</span>
            </button>
            <button
              v-if="model.images.length > 1"
              class="gallery-nav gallery-nav-next"
              type="button"
              aria-label="Next picture"
              @click.stop="selectAdjacentImage(1)"
            >
              ›
            </button>
            <div v-else class="thumbnail-placeholder">Fallback preview</div>
          </div>
          <div v-if="auth.user?.role === 'admin'" class="image-admin-controls">
            <p v-if="pictureNotice" class="form-success" role="status">{{ pictureNotice }}</p>
            <button
              class="secondary-button"
              type="button"
              :disabled="!selectedImage || selectedImage.is_primary"
              @click="selectedImage && setPrimaryImage(selectedImage)"
            >
              {{ selectedImage?.is_primary ? "Primary picture" : "Use as primary" }}
            </button>
            <button
              class="secondary-button"
              type="button"
              :disabled="rescanInProgress"
              @click="rescanCurrentModel()"
            >
              {{ rescanInProgress ? "Rescanning…" : "Rescan model" }}
            </button>
            <button
              class="danger-button"
              type="button"
              :disabled="rescanInProgress"
              @click="rescanCurrentModel(true)"
            >
              Rebuild archive images
            </button>
            <button class="danger-button" type="button" @click="resetPictures">Reset pictures</button>
          </div>
          <div v-if="model.images.length > 1" class="thumbnail-carousel">
            <button class="thumbnail-carousel-nav thumbnail-carousel-nav-previous" type="button" aria-label="Show earlier pictures" @click="scrollThumbnailStrip(-1)">‹</button>
            <div
              ref="thumbnailStrip"
              :class="{ 'is-dragging': thumbnailDragActive }"
              class="image-strip"
              aria-label="Model pictures"
              @pointerdown.capture="startThumbnailDrag"
              @pointermove.capture="moveThumbnailDrag"
              @pointerup="endThumbnailDrag"
              @pointercancel="endThumbnailDrag"
            >
              <button
                v-for="image in model.images"
                :key="image.id"
                :data-image-id="image.id"
                type="button"
                :class="{ selected: selectedImage?.id === image.id }"
                @dragstart.prevent
                @click="selectThumbnail(image)"
              >
                <img :src="image.url" :alt="image.filename" loading="lazy" draggable="false">
              </button>
            </div>
            <button class="thumbnail-carousel-nav thumbnail-carousel-nav-next" type="button" aria-label="Show later pictures" @click="scrollThumbnailStrip(1)">›</button>
          </div>
        </div>

        <aside class="panel model-facts">
          <h2>Details</h2>
          <dl>
            <dt>Model</dt>
            <dd>
              <RouterLink
                class="model-fact-link"
                :to="catalogueFilterLink('model', model.name)"
              >
                {{ model.name }}
              </RouterLink>
            </dd>
            <template v-if="model.variant">
              <dt>Variant</dt>
              <dd>{{ model.variant }}</dd>
            </template>
            <template v-if="model.creator">
              <dt>Creator</dt>
              <dd>
                <RouterLink
                  class="model-fact-link"
                  :to="catalogueFilterLink('creator', model.creator)"
                >
                  {{ model.creator }}
                </RouterLink>
              </dd>
            </template>
            <template v-if="model.creator_links.length">
              <dt>Creator links</dt>
              <dd class="model-fact-external-links">
                <a
                  v-for="link in model.creator_links"
                  :key="link.id"
                  class="model-fact-link"
                  :href="link.url"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {{ link.label }} <span aria-hidden="true">↗</span>
                </a>
              </dd>
            </template>
            <template v-if="model.franchise">
              <dt>Franchise</dt>
              <dd>
                <RouterLink
                  class="model-fact-link"
                  :to="catalogueFilterLink('franchise', model.franchise)"
                >
                  {{ model.franchise }}
                </RouterLink>
              </dd>
            </template>
            <template v-if="model.series">
              <dt>Series</dt>
              <dd>
                <RouterLink
                  class="model-fact-link"
                  :to="catalogueFilterLink('series', model.series)"
                >
                  {{ model.series }}
                </RouterLink>
              </dd>
            </template>
            <template v-if="model.collection">
              <dt>Collection</dt>
              <dd>
                <RouterLink
                  class="model-fact-link"
                  :to="catalogueFilterLink('collection', model.collection)"
                >
                  {{ model.collection }}
                </RouterLink>
              </dd>
            </template>
            <dt>Source</dt>
            <dd>
              <RouterLink
                class="model-fact-link"
                :to="catalogueFilterLink('source_id', model.source_id)"
              >
                {{ model.source_name }}
              </RouterLink>
            </dd>
            <dt>Tags</dt>
            <dd class="model-fact-tags">
              <div v-if="model.tags.length" class="tag-list">
                <TagChip
                  v-for="tag in model.tags"
                  :key="tag.id"
                  :color="tag.color"
                  :description="tag.description"
                  :focusable="false"
                >
                  <RouterLink
                    class="tag-chip-link"
                    :to="catalogueFilterLink('tag_id', tag.id)"
                  >
                    {{ tag.name }}
                  </RouterLink>
                  <button
                    v-if="auth.user?.role === 'admin'"
                    type="button"
                    :aria-label="`Remove ${tag.name} tag`"
                    @click="removeTag(tag)"
                  >×</button>
                </TagChip>
              </div>
              <span v-else class="muted">None</span>
            </dd>
            <dt>Folder</dt><dd class="path-value">{{ model.relative_path }}</dd>
          </dl>
          <form
            v-if="auth.user?.role === 'admin' && availableTags.length"
            class="tag-assignment model-fact-tag-assignment"
            @submit.prevent="addTag"
          >
            <select v-model="selectedTagId" required aria-label="Tag to add">
              <option value="">Add tag…</option>
              <option v-for="tag in availableTags" :key="tag.id" :value="String(tag.id)">
                {{ tag.name }}
              </option>
            </select>
            <button class="secondary-button" type="submit">Add</button>
          </form>
        </aside>
      </section>

      <section class="panel archive-panel">
        <div v-if="model.archives.length > 1" class="archive-tabs">
          <button
            v-for="(archive, index) in model.archives"
            :key="archive.filename"
            class="secondary-button"
            :class="{ active: selectedArchiveIndex === index }"
            type="button"
            @click="selectArchive(index)"
          >
            {{ archive.filename }}
          </button>
        </div>
        <div class="archive-heading">
          <div>
            <p class="eyebrow">Archive contents</p>
            <h2>{{ currentArchive?.filename || "No archive indexed" }}</h2>
          </div>
          <p v-if="currentArchive" class="archive-summary">
            {{ currentArchive.entry_count }} entries ·
            {{ formatBytes(currentArchive.size_bytes) }} compressed ·
            {{ formatBytes(currentArchive.uncompressed_size_bytes) }} unpacked
          </p>
        </div>

        <div v-if="currentArchive" class="archive-downloads">
          <a
            class="primary-link archive-download"
            :href="currentArchive.download_url"
            :download="currentArchive.filename"
          >
            Download archive
          </a>
          <a
            v-if="model.archive_bundle_download_url"
            class="secondary-button archive-download"
            :href="model.archive_bundle_download_url"
            download
          >
            Download all archives (.tar)
          </a>
        </div>
        <p v-if="currentArchive?.error_message" class="form-error">
          {{ currentArchive.error_message }}
        </p>
        <template v-if="currentArchive?.entries.length">
          <label class="archive-search">
            <span class="sr-only">Filter archive contents</span>
            <input v-model="archiveFilter" type="search" placeholder="Filter archive contents…">
          </label>
          <div class="archive-table-wrap">
            <table class="archive-table">
              <thead>
                <tr><th>Name</th><th>Size</th><th>Modified</th></tr>
              </thead>
              <tbody>
                <tr v-for="node in visibleTreeRows" :key="node.key">
                  <td class="tree-name-cell">
                    <span
                      class="tree-indent"
                      :style="{ width: `${node.depth * 1.25}rem` }"
                    />
                    <button
                      v-if="node.isDirectory"
                      class="tree-toggle"
                      type="button"
                      :aria-expanded="Boolean(archiveFilter.trim()) || !collapsedFolders.has(node.key)"
                      @click="toggleFolder(node.key)"
                    >
                      <span class="tree-chevron">
                        {{ collapsedFolders.has(node.key) ? "▶" : "▼" }}
                      </span>
                      <span>📁</span>
                      <span>{{ node.name }}</span>
                    </button>
                    <span v-else class="tree-file path-value">
                      <span>📄</span>
                      <span>{{ node.name }}</span>
                    </span>
                  </td>
                  <td>
                    {{ node.isDirectory ? "—" : formatBytes(node.entry?.size_bytes ?? null) }}
                  </td>
                  <td>{{ node.entry?.modified_at || "—" }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
      </section>

      <div
        v-if="lightboxOpen && selectedImage"
        class="image-lightbox"
        role="dialog"
        aria-modal="true"
        :aria-label="selectedImage.filename"
        @click.self="closeLightbox"
      >
        <div class="lightbox-toolbar">
          <span>{{ selectedImage.filename }}</span>
          <div>
            <button
              class="secondary-button"
              :class="{ active: lightboxMode === 'height' }"
              type="button"
              @click="lightboxMode = 'height'"
            >
              Fit height
            </button>
            <button
              class="secondary-button"
              :class="{ active: lightboxMode === 'width' }"
              type="button"
              @click="lightboxMode = 'width'"
            >
              Fit width
            </button>
            <button
              class="secondary-button"
              :class="{ active: lightboxMode === 'original' }"
              type="button"
              @click="lightboxMode = 'original'"
            >
              Original
            </button>
            <button
              ref="lightboxCloseButton"
              class="secondary-button"
              type="button"
              @click="closeLightbox"
            >
              Close
            </button>
          </div>
        </div>
        <div
          class="lightbox-image-area"
          :class="[`mode-${lightboxMode}`, { 'is-swiping': imageSwipeActive }]"
          :style="imageSwipeStyle"
          @click.self="closeLightbox"
          @pointerdown="startImageSwipe"
          @pointermove="moveImageSwipe"
          @pointerup="endImageSwipe"
          @pointercancel="endImageSwipe"
        >
          <button
            v-if="model.images.length > 1"
            class="gallery-nav gallery-nav-previous"
            type="button"
            aria-label="Previous picture"
            @click.stop="selectAdjacentImage(-1)"
          >
            ‹
          </button>
          <img
            :src="selectedImage.url"
            :alt="`${model.name} — ${selectedImage.filename}`"
          >
          <button
            v-if="model.images.length > 1"
            class="gallery-nav gallery-nav-next"
            type="button"
            aria-label="Next picture"
            @click.stop="selectAdjacentImage(1)"
          >
            ›
          </button>
        </div>
      </div>

      <FavoriteSaveDialog
        :open="favoriteDialogOpen"
        :targets="favoriteDialogTargets"
        :existing-model-lists="favoriteMemberships"
        @close="favoriteDialogOpen = false"
        @saved="favoriteSaved"
        @removed="favoriteRemoved"
      />
    </template>
  </main>
</template>
