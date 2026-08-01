<script setup lang="ts">
import { computed, onMounted, ref } from "vue"

import { ApiError, apiRequest } from "../../api"
import AdminHeader from "../../components/AdminHeader.vue"
import SearchableFilter from "../../components/SearchableFilter.vue"

interface CreatorLink {
  name: string
  url: string | null
  model_count: number
}

interface CreatorLinkRow extends CreatorLink {
  draft_url: string
}

const creators = ref<CreatorLinkRow[]>([])
const selectedCreatorName = ref("")
const loading = ref(true)
const savingCreator = ref("")
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

async function loadCreators() {
  loading.value = true
  errorMessage.value = ""
  try {
    const result = await apiRequest<CreatorLink[]>("/api/admin/creator-links")
    creators.value = result.map((creator) => ({
      ...creator,
      draft_url: creator.url || "",
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
    creator.draft_url = creator.url || ""
  })
}

async function saveCreatorLink() {
  const creator = selectedCreator.value
  if (!creator) return
  savingCreator.value = creator.name
  errorMessage.value = ""
  successMessage.value = ""
  const url = creator.draft_url.trim()
  try {
    await apiRequest<void>("/api/admin/creator-links", {
      method: "PUT",
      body: JSON.stringify({
        creator_name: creator.name,
        url: url || null,
      }),
    })
    creator.url = url || null
    creator.draft_url = url
    successMessage.value = url
      ? `Saved the link for ${creator.name}`
      : `Removed the link for ${creator.name}`
  } catch (error) {
    errorMessage.value =
      error instanceof ApiError ? error.message : "Unable to save the creator link"
  } finally {
    savingCreator.value = ""
  }
}

onMounted(loadCreators)
</script>

<template>
  <main class="admin-shell">
    <AdminHeader title="Creators" />
    <p class="admin-intro">
      Add an optional public HTTP or HTTPS page for creators discovered in the catalogue.
      Creator links are Meshive metadata and do not change any library files.
    </p>

    <p v-if="errorMessage" class="form-error error-panel" role="alert">
      {{ errorMessage }}
    </p>
    <p v-if="successMessage" class="success-panel" role="status">
      {{ successMessage }}
    </p>

    <section class="panel creator-links-panel">
      <div class="creator-links-heading">
        <div>
          <h2>Creator metadata</h2>
          <p class="muted">{{ creators.length }} creators found</p>
        </div>
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

        <form
          v-if="selectedCreator"
          class="source-form creator-metadata-form"
          @submit.prevent="saveCreatorLink"
        >
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
          <label>
            <span>Public creator page</span>
            <input
              v-model="selectedCreator.draft_url"
              type="url"
              inputmode="url"
              placeholder="https://example.com/creator"
            >
            <small>
              Shown as an external link on model details. Leave empty to remove it.
            </small>
          </label>
          <button
            class="primary-button"
            type="submit"
            :disabled="savingCreator === selectedCreator.name"
          >
            {{ savingCreator === selectedCreator.name ? "Saving…" : "Save metadata" }}
          </button>
        </form>
        <p v-else class="creator-selection-hint muted">
          Select a creator to edit its metadata.
        </p>
      </template>
    </section>
  </main>
</template>
