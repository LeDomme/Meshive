<script setup lang="ts">
import { computed, onMounted, ref } from "vue"

import { ApiError, apiRequest } from "../../api"
import AdminHeader from "../../components/AdminHeader.vue"
import SearchableFilter from "../../components/SearchableFilter.vue"

type MetadataEntityType = "creator" | "franchise" | "collection"
type CreatorLinkKind =
  | "website"
  | "patreon"
  | "cults3d"
  | "myminifactory"
  | "cgtrader"
  | "gumroad"
  | "etsy"
  | "other"

interface MetadataEntity {
  entity_type: MetadataEntityType
  value: string
  model_count: number
  artwork_url: string | null
}

interface MetadataArtwork {
  id: number
  entity_type: MetadataEntityType
  value: string
  artwork_url: string
  width: number
  height: number
}

interface CreatorMetadataLink {
  id: number
  kind: CreatorLinkKind
  label: string
  url: string
}

interface CreatorMetadataLinkRow extends CreatorMetadataLink {
  draft_kind: CreatorLinkKind
  draft_label: string
  draft_url: string
}

interface Creator {
  name: string
  model_count: number
  links: CreatorMetadataLinkRow[]
}

interface CreatorRead {
  name: string
  model_count: number
  links: CreatorMetadataLink[]
}

const linkTypeOptions: Array<{ value: CreatorLinkKind; label: string }> = [
  { value: "website", label: "Website" },
  { value: "patreon", label: "Patreon" },
  { value: "cults3d", label: "Cults3D" },
  { value: "myminifactory", label: "MyMiniFactory" },
  { value: "cgtrader", label: "CGTrader" },
  { value: "gumroad", label: "Gumroad" },
  { value: "etsy", label: "Etsy" },
  { value: "other", label: "Other" },
]

const creators = ref<Creator[]>([])
const metadataEntities = ref<MetadataEntity[]>([])
const selectedEntityType = ref<MetadataEntityType>("creator")
const selectedEntityTypeValue = computed({
  get: () => selectedEntityType.value,
  set: (value: string) => {
    selectedEntityType.value = value as MetadataEntityType
  },
})
const selectedEntityValue = ref("")
const artworkFile = ref<File | null>(null)
const artworkInput = ref<HTMLInputElement | null>(null)
const newLinkKind = ref<CreatorLinkKind>("website")
const newLinkLabel = ref("")
const newLinkUrl = ref("")
const loading = ref(true)
const uploadingArtwork = ref(false)
const addingLink = ref(false)
const savingLinkId = ref<number | null>(null)
const errorMessage = ref("")
const successMessage = ref("")
const metadataTypeOptions = [
  { value: "creator", label: "Creator" },
  { value: "franchise", label: "Franchise" },
  { value: "collection", label: "Collection" },
]

const entityOptions = computed(() => {
  const options = metadataEntities.value
    .filter((entity) => entity.entity_type === selectedEntityType.value)
    .map((entity) => ({ value: entity.value, label: entity.value, count: entity.model_count }))
  if (selectedEntityType.value === "creator") {
    for (const creator of creators.value) {
      if (!options.some((option) => option.value === creator.name)) {
        options.push({ value: creator.name, label: creator.name, count: creator.model_count })
      }
    }
  }
  return options.sort((left, right) => left.label.localeCompare(right.label))
})
const selectedEntity = computed<MetadataEntity | undefined>(() => {
  const stored = metadataEntities.value.find(
    (entity) =>
      entity.entity_type === selectedEntityType.value &&
      entity.value === selectedEntityValue.value,
  )
  if (stored) return stored
  const creator = selectedEntityType.value === "creator"
    ? creators.value.find((item) => item.name === selectedEntityValue.value)
    : undefined
  return creator
    ? {
        entity_type: "creator",
        value: creator.name,
        model_count: creator.model_count,
        artwork_url: null,
      }
    : undefined
})
const selectedCreator = computed(() =>
  selectedEntityType.value === "creator"
    ? creators.value.find((creator) => creator.name === selectedEntityValue.value)
    : undefined,
)
const entityTypeLabel = computed(() =>
  selectedEntityType.value === "creator"
    ? "Creator"
    : selectedEntityType.value === "franchise"
      ? "Franchise"
      : "Collection",
)
const artworkPreview = computed(() =>
  selectedEntity.value?.artwork_url ??
  `/favorite-fallbacks/favorite-${selectedEntityType.value}.webp`,
)
const availableNewLinkTypeOptions = computed(() =>
  linkTypeOptions.filter(
    (option) =>
      option.value === "other" ||
      !selectedCreator.value?.links.some((link) => link.kind === option.value),
  ),
)

function editableLink(link: CreatorMetadataLink): CreatorMetadataLinkRow {
  return {
    ...link,
    draft_kind: link.kind,
    draft_label: link.label,
    draft_url: link.url,
  }
}

function linkTypeOptionsFor(link: CreatorMetadataLinkRow) {
  return linkTypeOptions.filter(
    (option) =>
      option.value === "other" ||
      option.value === link.kind ||
      !selectedCreator.value?.links.some(
        (otherLink) => otherLink.id !== link.id && otherLink.kind === option.value,
      ),
  )
}

function resetNewLink() {
  newLinkKind.value = availableNewLinkTypeOptions.value[0]?.value ?? "other"
  newLinkLabel.value = ""
  newLinkUrl.value = ""
}

function resetEditor() {
  errorMessage.value = ""
  successMessage.value = ""
  artworkFile.value = null
  if (artworkInput.value) artworkInput.value.value = ""
  creators.value.forEach((creator) => {
    creator.links = creator.links.map(editableLink)
  })
  resetNewLink()
}

function entityTypeChanged() {
  selectedEntityValue.value = ""
  resetEditor()
}

function artworkSelected(event: Event) {
  artworkFile.value = (event.target as HTMLInputElement).files?.[0] ?? null
}

async function loadMetadata() {
  loading.value = true
  errorMessage.value = ""
  try {
    const [creatorResult, entityResult] = await Promise.all([
      apiRequest<CreatorRead[]>("/api/admin/creator-links"),
      apiRequest<MetadataEntity[]>("/api/admin/metadata"),
    ])
    creators.value = creatorResult.map((creator) => ({
      ...creator,
      links: creator.links.map(editableLink),
    }))
    metadataEntities.value = entityResult
    if (
      selectedEntityValue.value &&
      !metadataEntities.value.some(
        (entity) =>
          entity.entity_type === selectedEntityType.value &&
          entity.value === selectedEntityValue.value,
      )
    ) {
      selectedEntityValue.value = ""
    }
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : "Unable to load metadata"
  } finally {
    loading.value = false
  }
}

async function uploadArtwork() {
  const entity = selectedEntity.value
  if (!entity || !artworkFile.value) return
  uploadingArtwork.value = true
  errorMessage.value = ""
  successMessage.value = ""
  try {
    const body = new FormData()
    body.set("entity_type", entity.entity_type)
    body.set("value", entity.value)
    body.set("image", artworkFile.value)
    const result = await apiRequest<MetadataArtwork>("/api/admin/metadata/artwork", {
      method: "PUT",
      body,
    })
    entity.artwork_url = result.artwork_url
    artworkFile.value = null
    if (artworkInput.value) artworkInput.value.value = ""
    successMessage.value = `Saved custom artwork for ${entity.value}.`
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : "Unable to upload artwork"
  } finally {
    uploadingArtwork.value = false
  }
}

async function removeArtwork() {
  const entity = selectedEntity.value
  if (!entity?.artwork_url || !window.confirm(`Remove custom artwork for ${entity.value}?`)) return
  uploadingArtwork.value = true
  errorMessage.value = ""
  successMessage.value = ""
  try {
    const parameters = new URLSearchParams({
      entity_type: entity.entity_type,
      value: entity.value,
    })
    await apiRequest<void>(`/api/admin/metadata/artwork?${parameters}`, {
      method: "DELETE",
    })
    entity.artwork_url = null
    successMessage.value = `Removed custom artwork for ${entity.value}.`
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : "Unable to remove artwork"
  } finally {
    uploadingArtwork.value = false
  }
}

async function addCreatorLink() {
  const creator = selectedCreator.value
  if (!creator) return
  addingLink.value = true
  errorMessage.value = ""
  successMessage.value = ""
  try {
    const link = await apiRequest<CreatorMetadataLink>("/api/admin/creator-links", {
      method: "POST",
      body: JSON.stringify({
        creator_name: creator.name,
        kind: newLinkKind.value,
        label: newLinkKind.value === "other" ? newLinkLabel.value : null,
        url: newLinkUrl.value.trim(),
      }),
    })
    creator.links.push(editableLink(link))
    creator.links.sort((left, right) => left.label.localeCompare(right.label))
    successMessage.value = `Added ${link.label} for ${creator.name}.`
    resetNewLink()
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : "Unable to add creator metadata"
  } finally {
    addingLink.value = false
  }
}

async function saveCreatorLink(link: CreatorMetadataLinkRow) {
  const creator = selectedCreator.value
  if (!creator) return
  savingLinkId.value = link.id
  errorMessage.value = ""
  successMessage.value = ""
  try {
    const updated = await apiRequest<CreatorMetadataLink>(
      `/api/admin/creator-links/${link.id}`,
      {
        method: "PUT",
        body: JSON.stringify({
          kind: link.draft_kind,
          label: link.draft_kind === "other" ? link.draft_label : null,
          url: link.draft_url.trim(),
        }),
      },
    )
    Object.assign(link, editableLink(updated))
    creator.links.sort((left, right) => left.label.localeCompare(right.label))
    successMessage.value = `Saved ${updated.label} for ${creator.name}.`
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : "Unable to save creator metadata"
  } finally {
    savingLinkId.value = null
  }
}

async function deleteCreatorLink(link: CreatorMetadataLinkRow) {
  const creator = selectedCreator.value
  if (!creator || !window.confirm(`Remove ${link.label} from ${creator.name}?`)) return
  errorMessage.value = ""
  successMessage.value = ""
  try {
    await apiRequest<void>(`/api/admin/creator-links/${link.id}`, { method: "DELETE" })
    creator.links = creator.links.filter((item) => item.id !== link.id)
    successMessage.value = `Removed ${link.label} from ${creator.name}.`
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : "Unable to remove creator metadata"
  }
}

onMounted(loadMetadata)
</script>

<template>
  <main class="admin-shell">
    <AdminHeader title="Metadata" />
    <p class="admin-intro">
      Manage catalogue artwork and creator links stored by Meshive. Library files are never changed.
    </p>

    <p v-if="errorMessage" class="form-error error-panel" role="alert">{{ errorMessage }}</p>
    <p v-if="successMessage" class="success-panel" role="status">{{ successMessage }}</p>

    <section class="panel creator-links-panel metadata-panel">
      <div class="creator-links-heading">
        <h2>Catalogue metadata</h2>
        <p class="muted">Custom artwork is used on favorite lists.</p>
      </div>

      <p v-if="loading" class="muted">Loading...</p>
      <template v-else>
        <div class="metadata-selectors">
          <div class="matched-dropdown-field">
            <span>Type</span>
            <SearchableFilter
              v-model="selectedEntityTypeValue"
              label="Metadata type"
              all-label="Select a type"
              search-placeholder="Search types"
              :options="metadataTypeOptions"
              :show-all-option="false"
              @change="entityTypeChanged"
            />
          </div>
          <div class="matched-dropdown-field">
            <span>{{ entityTypeLabel }}</span>
            <SearchableFilter
              v-model="selectedEntityValue"
              :label="entityTypeLabel"
              :all-label="`Select a ${entityTypeLabel.toLocaleLowerCase()}`"
              :search-placeholder="`Search ${entityTypeLabel.toLocaleLowerCase()}s`"
              :options="entityOptions"
              @change="resetEditor"
            />
          </div>
        </div>

        <div v-if="selectedEntity" class="creator-metadata-editor">
          <div class="creator-metadata-heading">
            <div>
              <p class="eyebrow">Selected {{ entityTypeLabel.toLocaleLowerCase() }}</p>
              <h3>{{ selectedEntity.value }}</h3>
            </div>
            <span class="muted">
              {{ selectedEntity.model_count }}
              {{ selectedEntity.model_count === 1 ? "model" : "models" }}
            </span>
          </div>

          <section class="creator-metadata-section metadata-artwork-section">
            <div class="metadata-artwork-preview">
              <img :src="artworkPreview" :alt="`${selectedEntity.value} artwork`">
              <span>{{ selectedEntity.artwork_url ? "Custom artwork" : "Meshive fallback" }}</span>
            </div>
            <form class="metadata-artwork-form" @submit.prevent="uploadArtwork">
              <div>
                <h4>Artwork</h4>
                <p class="muted">
                  JPEG, PNG, WebP, or another Pillow-compatible image up to 12 MB.
                  Meshive stores an optimized WebP copy in its database.
                </p>
              </div>
              <label>
                <span>Image file</span>
                <input
                  ref="artworkInput"
                  type="file"
                  accept="image/*"
                  required
                  @change="artworkSelected"
                >
              </label>
              <div class="row-actions">
                <button
                  class="primary-button"
                  type="submit"
                  :disabled="uploadingArtwork || !artworkFile || selectedEntity.model_count === 0"
                >{{ uploadingArtwork ? "Saving..." : "Save artwork" }}</button>
                <button
                  v-if="selectedEntity.artwork_url"
                  class="danger-button"
                  type="button"
                  :disabled="uploadingArtwork"
                  @click="removeArtwork"
                >Use fallback</button>
              </div>
              <p v-if="selectedEntity.model_count === 0" class="muted">
                Artwork can be uploaded again after this value returns to the catalogue.
              </p>
            </form>
          </section>

          <template v-if="selectedCreator">
            <section class="creator-metadata-section">
              <h4>Creator links</h4>
              <p v-if="!selectedCreator.links.length" class="muted">No links have been added yet.</p>
              <div v-else class="creator-metadata-list">
                <form
                  v-for="link in selectedCreator.links"
                  :key="link.id"
                  class="source-form creator-metadata-link"
                  @submit.prevent="saveCreatorLink(link)"
                >
                  <div class="creator-metadata-fields">
                    <label>
                      <span>Type</span>
                      <select v-model="link.draft_kind">
                        <option
                          v-for="option in linkTypeOptionsFor(link)"
                          :key="option.value"
                          :value="option.value"
                        >{{ option.label }}</option>
                      </select>
                    </label>
                    <label v-if="link.draft_kind === 'other'">
                      <span>Label</span>
                      <input v-model="link.draft_label" required maxlength="80">
                    </label>
                    <label class="creator-metadata-url">
                      <span>URL</span>
                      <input v-model="link.draft_url" type="url" inputmode="url" required>
                    </label>
                  </div>
                  <div class="row-actions">
                    <button class="secondary-button" type="submit" :disabled="savingLinkId === link.id">
                      {{ savingLinkId === link.id ? "Saving..." : "Save" }}
                    </button>
                    <button class="danger-button" type="button" @click="deleteCreatorLink(link)">Delete</button>
                  </div>
                </form>
              </div>
            </section>

            <form class="source-form creator-metadata-add" @submit.prevent="addCreatorLink">
              <h4>Add creator link</h4>
              <div class="creator-metadata-fields">
                <label>
                  <span>Type</span>
                  <select v-model="newLinkKind">
                    <option
                      v-for="option in availableNewLinkTypeOptions"
                      :key="option.value"
                      :value="option.value"
                    >{{ option.label }}</option>
                  </select>
                </label>
                <label v-if="newLinkKind === 'other'">
                  <span>Label</span>
                  <input v-model="newLinkLabel" required maxlength="80">
                </label>
                <label class="creator-metadata-url">
                  <span>URL</span>
                  <input
                    v-model="newLinkUrl"
                    type="url"
                    inputmode="url"
                    placeholder="https://example.com/creator"
                    required
                  >
                </label>
              </div>
              <button class="primary-button" type="submit" :disabled="addingLink">
                {{ addingLink ? "Adding..." : "Add link" }}
              </button>
            </form>
          </template>
        </div>
        <p v-else class="creator-selection-hint muted">
          Select a catalogue entry to edit its metadata.
        </p>
      </template>
    </section>
  </main>
</template>
