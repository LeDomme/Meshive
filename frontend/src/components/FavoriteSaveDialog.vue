<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from "vue"

import { ApiError, apiRequest } from "../api"
import type { FavoriteListItem, FavoriteListSummary, FavoriteTarget } from "../favorites"

const props = defineProps<{
  open: boolean
  targets: FavoriteTarget[]
}>()
const emit = defineEmits<{
  close: []
  saved: [list: FavoriteListSummary]
}>()

const lists = ref<FavoriteListSummary[]>([])
const selectedListId = ref(0)
const selectedTargetKey = ref("")
const newListName = ref("")
const loading = ref(false)
const saving = ref(false)
const errorMessage = ref("")
const dialog = ref<HTMLElement | null>(null)

async function loadLists() {
  loading.value = true
  errorMessage.value = ""
  try {
    lists.value = await apiRequest<FavoriteListSummary[]>("/api/favorite-lists")
    if (!lists.value.some((item) => item.id === selectedListId.value)) {
      selectedListId.value = lists.value[0]?.id ?? 0
    }
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : "Unable to load favorite lists"
  } finally {
    loading.value = false
  }
}

async function createList() {
  const name = newListName.value.trim()
  if (!name) return
  saving.value = true
  errorMessage.value = ""
  try {
    const created = await apiRequest<FavoriteListSummary>("/api/favorite-lists", {
      method: "POST",
      body: JSON.stringify({ name }),
    })
    lists.value.unshift(created)
    selectedListId.value = created.id
    newListName.value = ""
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : "Unable to create the list"
  } finally {
    saving.value = false
  }
}

async function save() {
  const target = props.targets.find((item) => item.key === selectedTargetKey.value)
  const list = lists.value.find((item) => item.id === selectedListId.value)
  if (!target || !list) return

  saving.value = true
  errorMessage.value = ""
  try {
    await apiRequest<FavoriteListItem>(`/api/favorite-lists/${list.id}/items`, {
      method: "POST",
      body: JSON.stringify({
        entity_type: target.entity_type,
        model_id: target.model_id,
        tag_id: target.tag_id,
        value: target.value,
      }),
    })
    list.item_count += 1
    emit("saved", list)
    close()
  } catch (error) {
    errorMessage.value = error instanceof ApiError ? error.message : "Unable to save the favorite"
  } finally {
    saving.value = false
  }
}

function close() {
  if (!saving.value) emit("close")
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === "Escape" && props.open) close()
}

watch(
  () => props.open,
  async (open) => {
    document.documentElement.style.overflow = open ? "hidden" : ""
    if (!open) return
    selectedTargetKey.value = props.targets[0]?.key ?? ""
    await loadLists()
    await nextTick()
    dialog.value?.focus()
  },
)

document.addEventListener("keydown", handleKeydown)
onBeforeUnmount(() => {
  document.removeEventListener("keydown", handleKeydown)
  document.documentElement.style.overflow = ""
})
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="favorite-dialog-backdrop" @click.self="close">
      <section
        ref="dialog"
        class="favorite-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="favorite-dialog-title"
        tabindex="-1"
      >
        <div class="favorite-dialog-heading">
          <div>
            <p class="eyebrow">Private to your account</p>
            <h2 id="favorite-dialog-title">Save to favorites</h2>
          </div>
          <button class="favorite-dialog-close" type="button" aria-label="Close" @click="close">
            &times;
          </button>
        </div>

        <p v-if="loading" class="panel-copy">Loading favorite lists...</p>
        <form v-else class="favorite-dialog-form" @submit.prevent="save">
          <label>
            <span>Save</span>
            <select v-model="selectedTargetKey" required>
              <option v-for="target in targets" :key="target.key" :value="target.key">
                {{ target.label }}
              </option>
            </select>
          </label>
          <label v-if="lists.length">
            <span>To list</span>
            <select v-model="selectedListId" required>
              <option v-for="list in lists" :key="list.id" :value="list.id">
                {{ list.name }} ({{ list.item_count }})
              </option>
            </select>
          </label>

          <div class="favorite-create-row">
            <label>
              <span>{{ lists.length ? "Or create a new list" : "Create your first list" }}</span>
              <input v-model="newListName" maxlength="120" placeholder="For example: Print next">
            </label>
            <button
              class="secondary-button"
              type="button"
              :disabled="saving || !newListName.trim()"
              @click="createList"
            >
              Create list
            </button>
          </div>

          <p v-if="errorMessage" class="form-error" role="alert">{{ errorMessage }}</p>
          <div class="favorite-dialog-actions">
            <RouterLink class="text-link" to="/favorites" @click="close">Manage lists</RouterLink>
            <button class="primary-button" type="submit" :disabled="saving || !lists.length">
              {{ saving ? "Saving..." : "Save" }}
            </button>
          </div>
        </form>
      </section>
    </div>
  </Teleport>
</template>
