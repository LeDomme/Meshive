<script setup lang="ts">
import { computed, onMounted, ref } from "vue"

import { ApiError, apiRequest } from "../../api"
import AdminHeader from "../../components/AdminHeader.vue"
import SearchableFilter from "../../components/SearchableFilter.vue"

type CreatorLinkKind =
  | "website"
  | "patreon"
  | "cults3d"
  | "myminifactory"
  | "cgtrader"
  | "gumroad"
  | "etsy"
  | "other"

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
const selectedCreatorName = ref("")
const newLinkKind = ref<CreatorLinkKind>("website")
const newLinkLabel = ref("")
const newLinkUrl = ref("")
const loading = ref(true)
const addingLink = ref(false)
const savingLinkId = ref<number | null>(null)
const errorMessage = ref("")
const successMessage = ref("")

const creatorOptions = computed(() =>
  creators.value.map((creator) => ({
    value: creator.name,
    label: creator.name,
    count: creator.model_count,
  })),
)
const selectedCreator = computed(() =>
  creators.value.find((creator) => creator.name === selectedCreatorName.value),
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

async function loadCreators() {
  loading.value = true
  errorMessage.value = ""
  try {
    const result = await apiRequest<CreatorRead[]>("/api/admin/creator-links")
    creators.value = result.map((creator) => ({
      ...creator,
      links: creator.links.map(editableLink),
    }))
    if (
      selectedCreatorName.value &&
      !creators.value.some((creator) => creator.name === selectedCreatorName.value)
    ) {
      selectedCreatorName.value = ""
    }
  } catch (error) {
    errorMessage.value =
      error instanceof ApiError ? error.message : "Unable to load creators"
  } finally {
    loading.value = false
  }
}

function creatorChanged() {
  errorMessage.value = ""
  successMessage.value = ""
  creators.value.forEach((creator) => {
    creator.links = creator.links.map(editableLink)
  })
  resetNewLink()
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
    successMessage.value = `Added ${link.label} for ${creator.name}`
    resetNewLink()
  } catch (error) {
    errorMessage.value =
      error instanceof ApiError ? error.message : "Unable to add creator metadata"
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
    successMessage.value = `Saved ${updated.label} for ${creator.name}`
  } catch (error) {
    errorMessage.value =
      error instanceof ApiError ? error.message : "Unable to save creator metadata"
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
    await apiRequest<void>(`/api/admin/creator-links/${link.id}`, {
      method: "DELETE",
    })
    creator.links = creator.links.filter((item) => item.id !== link.id)
    successMessage.value = `Removed ${link.label} from ${creator.name}`
  } catch (error) {
    errorMessage.value =
      error instanceof ApiError ? error.message : "Unable to remove creator metadata"
  }
}

onMounted(loadCreators)
</script>

<template>
  <main class="admin-shell">
    <AdminHeader title="Creators" />
    <p class="admin-intro">
      Manage optional metadata for creators discovered in the catalogue. These values
      are stored by Meshive and never change files in your libraries.
    </p>

    <p v-if="errorMessage" class="form-error error-panel" role="alert">
      {{ errorMessage }}
    </p>
    <p v-if="successMessage" class="success-panel" role="status">
      {{ successMessage }}
    </p>

    <section class="panel creator-links-panel">
      <div class="creator-links-heading">
        <h2>Creator metadata</h2>
        <p class="muted">{{ creators.length }} creators found</p>
      </div>

      <p v-if="loading" class="muted">Loading…</p>
      <p v-else-if="!creators.length" class="muted">No creators found.</p>
      <template v-else>
        <div class="creator-selector">
          <SearchableFilter
            v-model="selectedCreatorName"
            label="Creator"
            all-label="Select a creator"
            search-placeholder="Search creators"
            :options="creatorOptions"
            @change="creatorChanged"
          />
        </div>

        <div v-if="selectedCreator" class="creator-metadata-editor">
          <div class="creator-metadata-heading">
            <div>
              <p class="eyebrow">Selected creator</p>
              <h3>{{ selectedCreator.name }}</h3>
            </div>
            <span class="muted">
              {{ selectedCreator.model_count }}
              {{ selectedCreator.model_count === 1 ? "model" : "models" }}
            </span>
          </div>

          <section class="creator-metadata-section">
            <h4>Links</h4>
            <p v-if="!selectedCreator.links.length" class="muted">
              No links have been added yet.
            </p>
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
                      >
                        {{ option.label }}
                      </option>
                    </select>
                  </label>
                  <label v-if="link.draft_kind === 'other'">
                    <span>Label</span>
                    <input v-model="link.draft_label" required maxlength="80">
                  </label>
                  <label class="creator-metadata-url">
                    <span>URL</span>
                    <input
                      v-model="link.draft_url"
                      type="url"
                      inputmode="url"
                      required
                    >
                  </label>
                </div>
                <div class="row-actions">
                  <button
                    class="secondary-button"
                    type="submit"
                    :disabled="savingLinkId === link.id"
                  >
                    {{ savingLinkId === link.id ? "Saving…" : "Save" }}
                  </button>
                  <button
                    class="danger-button"
                    type="button"
                    @click="deleteCreatorLink(link)"
                  >
                    Delete
                  </button>
                </div>
              </form>
            </div>
          </section>

          <form class="source-form creator-metadata-add" @submit.prevent="addCreatorLink">
            <h4>Add metadata</h4>
            <div class="creator-metadata-fields">
              <label>
                <span>Type</span>
                <select v-model="newLinkKind">
                  <option
                    v-for="option in availableNewLinkTypeOptions"
                    :key="option.value"
                    :value="option.value"
                  >
                    {{ option.label }}
                  </option>
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
              {{ addingLink ? "Adding…" : "Add metadata" }}
            </button>
          </form>
        </div>
        <p v-else class="creator-selection-hint muted">
          Select a creator to edit its metadata.
        </p>
      </template>
    </section>
  </main>
</template>
