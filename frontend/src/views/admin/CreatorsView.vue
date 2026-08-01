<script setup lang="ts">
import { computed, onMounted, ref } from "vue"

import { ApiError, apiRequest } from "../../api"
import AdminHeader from "../../components/AdminHeader.vue"

interface CreatorLink {
  name: string
  url: string | null
  model_count: number
}

interface CreatorLinkRow extends CreatorLink {
  draft_url: string
}

const creators = ref<CreatorLinkRow[]>([])
const search = ref("")
const loading = ref(true)
const savingCreator = ref("")
const errorMessage = ref("")
const successMessage = ref("")

const filteredCreators = computed(() => {
  const value = search.value.trim().toLocaleLowerCase()
  if (!value) return creators.value
  return creators.value.filter((creator) =>
    creator.name.toLocaleLowerCase().includes(value),
  )
})

async function loadCreators() {
  loading.value = true
  errorMessage.value = ""
  try {
    const result = await apiRequest<CreatorLink[]>("/api/admin/creator-links")
    creators.value = result.map((creator) => ({
      ...creator,
      draft_url: creator.url || "",
    }))
  } catch (error) {
    errorMessage.value =
      error instanceof ApiError ? error.message : "Unable to load creators"
  } finally {
    loading.value = false
  }
}

async function saveCreatorLink(creator: CreatorLinkRow) {
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
          <h2>Creator pages</h2>
          <p class="muted">{{ creators.length }} creators found</p>
        </div>
        <label class="creator-search">
          <span class="sr-only">Search creators</span>
          <input v-model="search" type="search" placeholder="Search creators">
        </label>
      </div>

      <p v-if="loading" class="muted">Loading…</p>
      <p v-else-if="!filteredCreators.length" class="muted">No creators found.</p>
      <div v-else class="creator-link-list">
        <form
          v-for="creator in filteredCreators"
          :key="creator.name"
          class="creator-link-row"
          @submit.prevent="saveCreatorLink(creator)"
        >
          <div class="creator-link-name">
            <strong>{{ creator.name }}</strong>
            <span class="muted">
              {{ creator.model_count }}
              {{ creator.model_count === 1 ? "model" : "models" }}
            </span>
          </div>
          <label>
            <span class="sr-only">Public page for {{ creator.name }}</span>
            <input
              v-model="creator.draft_url"
              type="url"
              inputmode="url"
              placeholder="https://example.com/creator"
            >
          </label>
          <button
            class="secondary-button"
            type="submit"
            :disabled="savingCreator === creator.name"
          >
            {{ savingCreator === creator.name ? "Saving…" : "Save" }}
          </button>
        </form>
      </div>
    </section>
  </main>
</template>
