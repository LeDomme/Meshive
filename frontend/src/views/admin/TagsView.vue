<script setup lang="ts">
import { onMounted, ref } from "vue"
import { apiRequest } from "../../api"
import AdminHeader from "../../components/AdminHeader.vue"
import TagChip from "../../components/TagChip.vue"

interface Tag { id: number; name: string; color: string | null; description: string | null }
interface Source { id: number; name: string }
interface Rule { id: number; library_source_id: number; relative_path: string; tag_id: number; recursive: boolean; tag_name: string }
interface AutomaticRule {
  id: number
  tag_id: number
  tag_name: string
  pattern: string
  enabled: boolean
  match_count: number
  created_at: string
  updated_at: string
}
interface AutomaticEvaluation {
  models_evaluated: number
  matches: number
  assignments_added: number
  assignments_removed: number
}

const tags = ref<Tag[]>([])
const sources = ref<Source[]>([])
const rules = ref<Rule[]>([])
const automaticRules = ref<AutomaticRule[]>([])
const name = ref("")
const color = ref("#5eead4")
const description = ref("")
const editingTagId = ref<number | null>(null)
const editTagName = ref("")
const editTagColor = ref("#5eead4")
const editTagDescription = ref("")
const tagFeedback = ref("")
const tagError = ref("")
const tagWorking = ref(false)
const sourceId = ref("")
const tagId = ref("")
const path = ref("")
const recursive = ref(true)
const automaticTagId = ref("")
const automaticPattern = ref("")
const automaticFeedback = ref("")
const automaticError = ref("")
const automaticWorking = ref(false)

async function load() {
  ;[tags.value, sources.value, rules.value, automaticRules.value] = await Promise.all([
    apiRequest<Tag[]>("/api/tags"),
    apiRequest<Source[]>("/api/admin/library-sources"),
    apiRequest<Rule[]>("/api/admin/folder-tag-rules"),
    apiRequest<AutomaticRule[]>("/api/admin/automatic-tag-rules"),
  ])
}
async function createTag() {
  tagWorking.value = true
  tagFeedback.value = ""
  tagError.value = ""
  try {
    await apiRequest("/api/admin/tags", {
      method: "POST",
      body: JSON.stringify({
        name: name.value,
        color: color.value,
        description: description.value || null,
      }),
    })
    name.value = ""
    description.value = ""
    tagFeedback.value = "Tag created."
    await load()
  } catch (error) {
    tagError.value = error instanceof Error ? error.message : "Unable to create tag"
  } finally {
    tagWorking.value = false
  }
}
function editTag(tag: Tag) {
  editingTagId.value = tag.id
  editTagName.value = tag.name
  editTagColor.value = tag.color || "#5eead4"
  editTagDescription.value = tag.description || ""
  tagFeedback.value = ""
  tagError.value = ""
}
function cancelTagEdit() {
  editingTagId.value = null
}
async function saveTag(tagId: number) {
  tagWorking.value = true
  tagFeedback.value = ""
  tagError.value = ""
  try {
    await apiRequest(`/api/admin/tags/${tagId}`, {
      method: "PUT",
      body: JSON.stringify({
        name: editTagName.value,
        color: editTagColor.value,
        description: editTagDescription.value || null,
      }),
    })
    editingTagId.value = null
    tagFeedback.value = "Tag updated. Existing assignments and rules were preserved."
    await load()
  } catch (error) {
    tagError.value = error instanceof Error ? error.message : "Unable to update tag"
  } finally {
    tagWorking.value = false
  }
}
async function deleteTag(id: number) {
  if (!confirm("Delete this tag and all its assignments?")) return
  tagWorking.value = true
  tagFeedback.value = ""
  tagError.value = ""
  try {
    await apiRequest(`/api/admin/tags/${id}`, { method: "DELETE" })
    if (editingTagId.value === id) editingTagId.value = null
    tagFeedback.value = "Tag and its assignments were deleted."
    await load()
  } catch (error) {
    tagError.value = error instanceof Error ? error.message : "Unable to delete tag"
  } finally {
    tagWorking.value = false
  }
}
async function createRule() {
  await apiRequest("/api/admin/folder-tag-rules", { method: "POST", body: JSON.stringify({
    library_source_id: Number(sourceId.value), relative_path: path.value,
    tag_id: Number(tagId.value), recursive: recursive.value,
  }) })
  path.value = ""
  await load()
}
async function deleteRule(id: number) {
  await apiRequest(`/api/admin/folder-tag-rules/${id}`, { method: "DELETE" })
  await load()
}
async function createAutomaticRule() {
  automaticWorking.value = true
  automaticFeedback.value = ""
  automaticError.value = ""
  try {
    await apiRequest("/api/admin/automatic-tag-rules", {
      method: "POST",
      body: JSON.stringify({
        tag_id: Number(automaticTagId.value),
        pattern: automaticPattern.value,
        enabled: true,
      }),
    })
    automaticPattern.value = ""
    automaticFeedback.value = "Rule saved and existing models re-evaluated."
    await load()
  } catch (error) {
    automaticError.value = error instanceof Error ? error.message : "Unable to save rule"
  } finally {
    automaticWorking.value = false
  }
}
async function saveAutomaticRule(rule: AutomaticRule) {
  automaticWorking.value = true
  automaticFeedback.value = ""
  automaticError.value = ""
  try {
    await apiRequest(`/api/admin/automatic-tag-rules/${rule.id}`, {
      method: "PUT",
      body: JSON.stringify({
        tag_id: rule.tag_id,
        pattern: rule.pattern,
        enabled: rule.enabled,
      }),
    })
    automaticFeedback.value = "Rule updated and existing models re-evaluated."
    await load()
  } catch (error) {
    automaticError.value = error instanceof Error ? error.message : "Unable to update rule"
  } finally {
    automaticWorking.value = false
  }
}
async function deleteAutomaticRule(rule: AutomaticRule) {
  if (!confirm(`Delete the automatic rule “${rule.pattern}”?`)) return
  automaticWorking.value = true
  automaticFeedback.value = ""
  automaticError.value = ""
  try {
    await apiRequest(`/api/admin/automatic-tag-rules/${rule.id}`, { method: "DELETE" })
    automaticFeedback.value = "Rule deleted and derived tags re-evaluated."
    await load()
  } catch (error) {
    automaticError.value = error instanceof Error ? error.message : "Unable to delete rule"
  } finally {
    automaticWorking.value = false
  }
}
async function reevaluateAutomaticRules() {
  automaticWorking.value = true
  automaticFeedback.value = ""
  automaticError.value = ""
  try {
    const result = await apiRequest<AutomaticEvaluation>(
      "/api/admin/automatic-tag-rules/re-evaluate",
      { method: "POST" },
    )
    automaticFeedback.value = `${result.models_evaluated} models evaluated · ${result.matches} matches · ${result.assignments_added} tags added · ${result.assignments_removed} tags removed.`
    await load()
  } catch (error) {
    automaticError.value = error instanceof Error ? error.message : "Unable to re-evaluate rules"
  } finally {
    automaticWorking.value = false
  }
}
onMounted(load)
</script>

<template>
  <main class="admin-shell">
    <AdminHeader title="Tags" />
    <section class="admin-grid">
      <div class="panel">
        <h2>Tags</h2>
        <p v-if="tagFeedback" class="success-panel" aria-live="polite">
          {{ tagFeedback }}
        </p>
        <p v-if="tagError" class="form-error" role="alert">{{ tagError }}</p>
        <form class="source-form" @submit.prevent="createTag">
          <label><span>Name</span><input v-model="name" required></label>
          <label><span>Colour</span><input v-model="color" type="color"></label>
          <label>
            <span>Description</span>
            <textarea
              v-model="description"
              maxlength="1000"
              rows="2"
              placeholder="Optional description"
            ></textarea>
          </label>
          <button class="primary-button" :disabled="tagWorking">Create tag</button>
        </form>
        <div class="source-list tag-admin-list">
          <div v-for="tag in tags" :key="tag.id" class="tag-admin-item">
            <form
              v-if="editingTagId === tag.id"
              class="source-form tag-edit-form"
              @submit.prevent="saveTag(tag.id)"
            >
              <label>
                <span>Name</span>
                <input v-model="editTagName" required maxlength="80">
              </label>
              <label>
                <span>Colour</span>
                <input v-model="editTagColor" type="color">
              </label>
              <label class="tag-edit-description">
                <span>Description</span>
                <textarea
                  v-model="editTagDescription"
                  maxlength="1000"
                  rows="2"
                  placeholder="Optional description"
                ></textarea>
              </label>
              <div class="row-actions tag-edit-actions">
                <button class="primary-button" :disabled="tagWorking">Save changes</button>
                <button
                  class="secondary-button"
                  type="button"
                  :disabled="tagWorking"
                  @click="cancelTagEdit"
                >Cancel</button>
              </div>
            </form>
            <div v-else class="source-row tag-admin-row">
              <div class="tag-admin-summary">
                <TagChip
                  :color="tag.color"
                  :description="tag.description"
                >{{ tag.name }}</TagChip>
                <small v-if="tag.description">{{ tag.description }}</small>
              </div>
              <div class="row-actions">
                <button
                  class="secondary-button"
                  type="button"
                  :disabled="tagWorking"
                  @click="editTag(tag)"
                >Edit</button>
                <button
                  class="danger-button"
                  type="button"
                  :disabled="tagWorking"
                  @click="deleteTag(tag.id)"
                >Delete</button>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div class="panel">
        <h2>Folder tag rules</h2>
        <form class="source-form" @submit.prevent="createRule">
          <label><span>Source</span><select v-model="sourceId" required><option value="">Select…</option><option v-for="source in sources" :key="source.id" :value="String(source.id)">{{ source.name }}</option></select></label>
          <label><span>Relative folder</span><input v-model="path" required placeholder="Franchise/Series"></label>
          <label><span>Tag</span><select v-model="tagId" required><option value="">Select…</option><option v-for="tag in tags" :key="tag.id" :value="String(tag.id)">{{ tag.name }}</option></select></label>
          <label><input v-model="recursive" type="checkbox"> Include subfolders</label>
          <button class="primary-button">Add rule</button>
        </form>
        <div class="source-list">
          <div v-for="rule in rules" :key="rule.id" class="source-row">
            <span>{{ rule.relative_path }} → {{ rule.tag_name }}{{ rule.recursive ? " (recursive)" : "" }}</span>
            <button class="danger-button" @click="deleteRule(rule.id)">Delete</button>
          </div>
        </div>
      </div>
      <div class="panel automatic-tag-panel">
        <div class="panel-heading">
          <div>
            <h2>Automatic tag rules</h2>
            <p class="panel-copy">
              Match text anywhere in an archive entry name or its full path. Matching is
              case-insensitive and never removes manually assigned tags.
            </p>
          </div>
          <button
            class="secondary-button"
            type="button"
            :disabled="automaticWorking"
            @click="reevaluateAutomaticRules"
          >Re-evaluate all models</button>
        </div>

        <p v-if="automaticFeedback" class="success-panel" aria-live="polite">
          {{ automaticFeedback }}
        </p>
        <p v-if="automaticError" class="form-error" role="alert">
          {{ automaticError }}
        </p>

        <form class="source-form automatic-rule-form" @submit.prevent="createAutomaticRule">
          <label>
            <span>Text to match</span>
            <input v-model="automaticPattern" required maxlength="255" placeholder="Bust">
          </label>
          <label>
            <span>Assign tag</span>
            <select v-model="automaticTagId" required>
              <option value="">Select a tag</option>
              <option v-for="tag in tags" :key="tag.id" :value="String(tag.id)">
                {{ tag.name }}
              </option>
            </select>
          </label>
          <button class="primary-button" :disabled="automaticWorking">Add rule</button>
        </form>

        <div class="source-list automatic-rule-list">
          <p v-if="!automaticRules.length" class="panel-copy">No automatic rules configured.</p>
          <div v-for="rule in automaticRules" :key="rule.id" class="automatic-rule-row">
            <label>
              <span>Text to match</span>
              <input v-model="rule.pattern" maxlength="255" required>
            </label>
            <label>
              <span>Tag</span>
              <select v-model="rule.tag_id">
                <option v-for="tag in tags" :key="tag.id" :value="tag.id">
                  {{ tag.name }}
                </option>
              </select>
            </label>
            <label class="automatic-rule-enabled">
              <input v-model="rule.enabled" type="checkbox">
              Enabled
            </label>
            <span class="automatic-rule-matches">{{ rule.match_count }} models matched</span>
            <div class="row-actions">
              <button
                class="secondary-button"
                type="button"
                :disabled="automaticWorking"
                @click="saveAutomaticRule(rule)"
              >Save</button>
              <button
                class="danger-button"
                type="button"
                :disabled="automaticWorking"
                @click="deleteAutomaticRule(rule)"
              >Delete</button>
            </div>
          </div>
        </div>
      </div>
    </section>
  </main>
</template>
