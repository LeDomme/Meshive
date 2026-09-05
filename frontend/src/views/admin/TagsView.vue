<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { apiRequest } from "../../api"
import AdminHeader from "../../components/AdminHeader.vue"
import TagChip from "../../components/TagChip.vue"
import { useAuthStore } from "../../stores/auth"

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
interface FolderNameRule { id: number; tag_id: number; tag_name: string; pattern: string; enabled: boolean; match_count: number }
interface FolderNamePreview { model_name: string; relative_path: string }
type RuleType = "folder_path" | "folder_name_regex" | "archive_entry_text"
interface RuleListItem {
  id: number
  type: RuleType
  tagId: number
  tagName: string
  summary: string
  enabled?: boolean
  matchCount?: number
}
interface EditingRule {
  id: number
  type: RuleType
  tagId: number
  sourceId?: number
  relativePath?: string
  recursive?: boolean
  pattern?: string
  enabled?: boolean
}

const tags = ref<Tag[]>([])
const sources = ref<Source[]>([])
const rules = ref<Rule[]>([])
const automaticRules = ref<AutomaticRule[]>([])
const folderNameRules = ref<FolderNameRule[]>([])
const ruleType = ref<RuleType>("folder_path")
const ruleTagId = ref("")
const rulePattern = ref("")
const folderNamePreview = ref<FolderNamePreview[]>([])
const ruleFeedback = ref("")
const ruleError = ref("")
const ruleWorking = ref(false)
const editingRule = ref<EditingRule | null>(null)
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
const path = ref("")
const recursive = ref(true)
const auth = useAuthStore()
const canManageTags = auth.can("tags.manage")
const canManageTagRules = auth.can("tag_rules.manage")
const canManageAnyRules = canManageTags || canManageTagRules
if (!canManageTags && canManageTagRules) ruleType.value = "archive_entry_text"
const sourcesById = computed(() => new Map(sources.value.map(source => [source.id, source.name])))
const tagRules = computed<RuleListItem[]>(() => [
  ...rules.value.map(rule => ({
    id: rule.id,
    type: "folder_path" as const,
    tagId: rule.tag_id,
    tagName: rule.tag_name,
    summary: `${sourcesById.value.get(rule.library_source_id) ?? "Source"} · ${rule.relative_path}${rule.recursive ? " · includes subfolders" : ""}`,
  })),
  ...folderNameRules.value.map(rule => ({
    id: rule.id,
    type: "folder_name_regex" as const,
    tagId: rule.tag_id,
    tagName: rule.tag_name,
    summary: rule.pattern,
    enabled: rule.enabled,
    matchCount: rule.match_count,
  })),
  ...automaticRules.value.map(rule => ({
    id: rule.id,
    type: "archive_entry_text" as const,
    tagId: rule.tag_id,
    tagName: rule.tag_name,
    summary: rule.pattern,
    enabled: rule.enabled,
    matchCount: rule.match_count,
  })),
])

async function load() {
  const [loadedTags, loadedSources, loadedRules, loadedAutomaticRules, loadedFolderNameRules] = await Promise.all([
    apiRequest<Tag[]>("/api/admin/tags"),
    canManageTags ? apiRequest<Source[]>("/api/admin/tags/library-sources") : Promise.resolve([]),
    canManageTags ? apiRequest<Rule[]>("/api/admin/folder-tag-rules") : Promise.resolve([]),
    canManageTagRules
      ? apiRequest<AutomaticRule[]>("/api/admin/automatic-tag-rules")
      : Promise.resolve([]),
    canManageTagRules
      ? apiRequest<FolderNameRule[]>("/api/admin/folder-name-tag-rules")
      : Promise.resolve([]),
  ])
  tags.value = loadedTags
  sources.value = loadedSources
  rules.value = loadedRules
  automaticRules.value = loadedAutomaticRules
  folderNameRules.value = loadedFolderNameRules
}
function setRuleType(type: RuleType) {
  ruleType.value = type
  folderNamePreview.value = []
  ruleError.value = ""
}
async function previewFolderNameRule(pattern = rulePattern.value) {
  ruleError.value = ""
  folderNamePreview.value = []
  try {
    folderNamePreview.value = await apiRequest<FolderNamePreview[]>("/api/admin/folder-name-tag-rules/preview", {
      method: "POST", body: JSON.stringify({ pattern, limit: 25 }),
    })
  } catch (error) {
    ruleError.value = error instanceof Error ? error.message : "Unable to preview rule"
  }
}
async function createTagRule() {
  ruleWorking.value = true
  ruleError.value = ""
  ruleFeedback.value = ""
  try {
    if (ruleType.value === "folder_path") {
      await apiRequest("/api/admin/folder-tag-rules", {
        method: "POST",
        body: JSON.stringify({ library_source_id: Number(sourceId.value), relative_path: path.value, tag_id: Number(ruleTagId.value), recursive: recursive.value }),
      })
    } else if (ruleType.value === "folder_name_regex") {
      await apiRequest("/api/admin/folder-name-tag-rules", {
        method: "POST",
        body: JSON.stringify({ tag_id: Number(ruleTagId.value), pattern: rulePattern.value, enabled: true }),
      })
    } else {
      await apiRequest("/api/admin/automatic-tag-rules", {
        method: "POST",
        body: JSON.stringify({ tag_id: Number(ruleTagId.value), pattern: rulePattern.value, enabled: true }),
      })
    }
    path.value = ""
    rulePattern.value = ""
    folderNamePreview.value = []
    ruleFeedback.value = "Rule saved."
    await load()
  } catch (error) {
    ruleError.value = error instanceof Error ? error.message : "Unable to save rule"
  } finally {
    ruleWorking.value = false
  }
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
function ruleTypeLabel(type: RuleType) {
  return { folder_path: "Folder path", folder_name_regex: "Folder name regex", archive_entry_text: "Archive entry text" }[type]
}
function startEditingRule(item: RuleListItem) {
  if (item.type === "folder_path") {
    const rule = rules.value.find(candidate => candidate.id === item.id)
    if (!rule) return
    editingRule.value = { id: rule.id, type: item.type, tagId: rule.tag_id, sourceId: rule.library_source_id, relativePath: rule.relative_path, recursive: rule.recursive }
  } else if (item.type === "folder_name_regex") {
    const rule = folderNameRules.value.find(candidate => candidate.id === item.id)
    if (!rule) return
    editingRule.value = { id: rule.id, type: item.type, tagId: rule.tag_id, pattern: rule.pattern, enabled: rule.enabled }
  } else {
    const rule = automaticRules.value.find(candidate => candidate.id === item.id)
    if (!rule) return
    editingRule.value = { id: rule.id, type: item.type, tagId: rule.tag_id, pattern: rule.pattern, enabled: rule.enabled }
  }
  folderNamePreview.value = []
  ruleError.value = ""
}
async function saveEditingRule() {
  const rule = editingRule.value
  if (!rule) return
  ruleWorking.value = true
  ruleError.value = ""
  ruleFeedback.value = ""
  try {
    if (rule.type === "folder_path") {
      await apiRequest(`/api/admin/folder-tag-rules/${rule.id}`, { method: "PUT", body: JSON.stringify({ library_source_id: Number(rule.sourceId), relative_path: rule.relativePath, tag_id: Number(rule.tagId), recursive: rule.recursive }) })
    } else if (rule.type === "folder_name_regex") {
      await apiRequest(`/api/admin/folder-name-tag-rules/${rule.id}`, { method: "PUT", body: JSON.stringify({ tag_id: Number(rule.tagId), pattern: rule.pattern, enabled: rule.enabled }) })
    } else {
      await apiRequest(`/api/admin/automatic-tag-rules/${rule.id}`, { method: "PUT", body: JSON.stringify({ tag_id: Number(rule.tagId), pattern: rule.pattern, enabled: rule.enabled }) })
    }
    editingRule.value = null
    folderNamePreview.value = []
    ruleFeedback.value = "Rule updated."
    await load()
  } catch (error) {
    ruleError.value = error instanceof Error ? error.message : "Unable to update rule"
  } finally {
    ruleWorking.value = false
  }
}
async function deleteTagRule(item: RuleListItem) {
  const endpoint = item.type === "folder_path"
    ? `/api/admin/folder-tag-rules/${item.id}`
    : item.type === "folder_name_regex"
      ? `/api/admin/folder-name-tag-rules/${item.id}`
      : `/api/admin/automatic-tag-rules/${item.id}`
  if (!confirm(`Delete this ${ruleTypeLabel(item.type).toLowerCase()} rule?`)) return
  ruleWorking.value = true
  ruleError.value = ""
  try {
    await apiRequest(endpoint, { method: "DELETE" })
    if (editingRule.value?.id === item.id && editingRule.value.type === item.type) editingRule.value = null
    ruleFeedback.value = "Rule deleted."
    await load()
  } catch (error) {
    ruleError.value = error instanceof Error ? error.message : "Unable to delete rule"
  } finally {
    ruleWorking.value = false
  }
}
async function reevaluateAutomaticRules() {
  ruleWorking.value = true
  ruleFeedback.value = ""
  ruleError.value = ""
  try {
    const result = await apiRequest<AutomaticEvaluation>(
      "/api/admin/automatic-tag-rules/re-evaluate",
      { method: "POST" },
    )
    ruleFeedback.value = `${result.models_evaluated} models evaluated · ${result.matches} matches · ${result.assignments_added} tags added · ${result.assignments_removed} tags removed.`
    await load()
  } catch (error) {
    ruleError.value = error instanceof Error ? error.message : "Unable to re-evaluate archive entry text rules"
  } finally {
    ruleWorking.value = false
  }
}
onMounted(load)
</script>

<template>
  <main class="admin-shell">
    <AdminHeader title="Tags" />
    <section class="admin-grid">
      <div v-if="canManageTags" class="panel">
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
      <div v-if="canManageAnyRules" class="panel tag-rules-panel">
        <div class="panel-heading">
          <div>
            <h2>Tag rules</h2>
            <p class="panel-copy">Create and maintain path, folder-name, and archive-entry tagging rules in one place.</p>
          </div>
          <button
            v-if="canManageTagRules"
            class="secondary-button"
            type="button"
            :disabled="ruleWorking"
            @click="reevaluateAutomaticRules"
          >Re-evaluate archive entry text rules</button>
        </div>
        <p v-if="ruleFeedback" class="success-panel" aria-live="polite">{{ ruleFeedback }}</p>
        <p v-if="ruleError" class="form-error" role="alert">{{ ruleError }}</p>

        <form class="source-form tag-rule-form" @submit.prevent="createTagRule">
          <label>
            <span>Rule type</span>
            <select :value="ruleType" @change="setRuleType(($event.target as HTMLSelectElement).value as RuleType)">
              <option v-if="canManageTags" value="folder_path">Folder path</option>
              <option v-if="canManageTagRules" value="folder_name_regex">Folder name regex</option>
              <option v-if="canManageTagRules" value="archive_entry_text">Archive entry text</option>
            </select>
          </label>
          <p v-if="ruleType === 'folder_path'" class="rule-help">Match an exact folder or a folder structure, optionally including its subfolders.</p>
          <p v-else-if="ruleType === 'folder_name_regex'" class="rule-help">Match individual folder names with case-insensitive RE2. Example: <code>_p[12]$</code>.</p>
          <p v-else class="rule-help">Match text in file names or paths inside an archive. Matching is case-insensitive.</p>
          <div class="tag-rule-fields">
            <template v-if="ruleType === 'folder_path'">
              <label><span>Source</span><select v-model="sourceId" required><option value="">Select a source</option><option v-for="source in sources" :key="source.id" :value="String(source.id)">{{ source.name }}</option></select></label>
              <label><span>Relative folder</span><input v-model="path" required placeholder="Franchise/Series"></label>
              <label class="inline-check"><input v-model="recursive" type="checkbox"> Include subfolders</label>
            </template>
            <label v-else><span>{{ ruleType === 'folder_name_regex' ? 'Folder name regex' : 'Archive entry text' }}</span><input v-model="rulePattern" required maxlength="255" :placeholder="ruleType === 'folder_name_regex' ? '_p[12]$' : 'Bust'"></label>
            <label><span>Assign tag</span><select v-model="ruleTagId" required><option value="">Select a tag</option><option v-for="tag in tags" :key="tag.id" :value="String(tag.id)">{{ tag.name }}</option></select></label>
          </div>
          <div class="row-actions">
            <button v-if="ruleType === 'folder_name_regex'" class="secondary-button" type="button" @click="previewFolderNameRule()">Preview</button>
            <button class="primary-button" :disabled="ruleWorking">Add rule</button>
          </div>
        </form>
        <div v-if="folderNamePreview.length" class="source-list rule-preview" aria-live="polite">
          <div v-for="match in folderNamePreview" :key="`${match.model_name}:${match.relative_path}`" class="source-row"><span>{{ match.model_name }} · {{ match.relative_path }}</span></div>
        </div>

        <div class="source-list tag-rule-list">
          <p v-if="!tagRules.length" class="panel-copy">No tag rules configured.</p>
          <article v-for="item in tagRules" :key="`${item.type}:${item.id}`" class="tag-rule-row">
            <template v-if="editingRule?.id === item.id && editingRule.type === item.type">
              <form class="source-form tag-rule-edit-form" @submit.prevent="saveEditingRule">
                <span class="rule-type-badge" :class="`rule-type-${item.type}`">{{ ruleTypeLabel(item.type) }}</span>
                <template v-if="editingRule.type === 'folder_path'">
                  <label><span>Source</span><select v-model="editingRule.sourceId" required><option v-for="source in sources" :key="source.id" :value="source.id">{{ source.name }}</option></select></label>
                  <label><span>Relative folder</span><input v-model="editingRule.relativePath" required></label>
                  <label class="inline-check"><input v-model="editingRule.recursive" type="checkbox"> Include subfolders</label>
                </template>
                <template v-else>
                  <label><span>{{ editingRule.type === 'folder_name_regex' ? 'Folder name regex' : 'Archive entry text' }}</span><input v-model="editingRule.pattern" required maxlength="255"></label>
                  <label class="inline-check"><input v-model="editingRule.enabled" type="checkbox"> Enabled</label>
                </template>
                <label><span>Assign tag</span><select v-model="editingRule.tagId" required><option v-for="tag in tags" :key="tag.id" :value="tag.id">{{ tag.name }}</option></select></label>
                <div class="row-actions"><button v-if="editingRule.type === 'folder_name_regex'" class="secondary-button" type="button" @click="previewFolderNameRule(editingRule.pattern)">Preview</button><button class="primary-button" :disabled="ruleWorking">Save</button><button class="secondary-button" type="button" :disabled="ruleWorking" @click="editingRule = null">Cancel</button></div>
              </form>
            </template>
            <template v-else>
              <span class="rule-type-badge" :class="`rule-type-${item.type}`">{{ ruleTypeLabel(item.type) }}</span>
              <div class="tag-rule-summary"><strong>{{ item.summary }}</strong><small>Assigns {{ item.tagName }}<template v-if="item.matchCount !== undefined"> · {{ item.matchCount }} models matched</template><template v-if="item.enabled === false"> · Disabled</template></small></div>
              <div class="row-actions"><button class="secondary-button" type="button" :disabled="ruleWorking" @click="startEditingRule(item)">Edit</button><button class="danger-button" type="button" :disabled="ruleWorking" @click="deleteTagRule(item)">Delete</button></div>
            </template>
          </article>
        </div>
      </div>
    </section>
  </main>
</template>

<style scoped>
.tag-rules-panel {
  grid-column: 1 / -1;
}

.tag-rule-form,
.tag-rule-edit-form {
  gap: 1rem;
}

.rule-help {
  margin: 0;
  color: #a9b8cc;
}

.tag-rule-fields {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1rem;
  align-items: end;
}

.tag-rule-list {
  margin-top: 1.25rem;
}

.tag-rule-row {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 1rem;
  align-items: center;
  padding: 1rem 0;
  border-top: 1px solid #28364b;
}

.tag-rule-summary {
  display: grid;
  gap: .25rem;
  min-width: 0;
}

.tag-rule-summary strong,
.tag-rule-summary small {
  overflow-wrap: anywhere;
}

.tag-rule-summary small {
  color: #a9b8cc;
}

.rule-type-badge {
  display: inline-flex;
  width: fit-content;
  border: 1px solid #40608a;
  border-radius: 999px;
  padding: .2rem .5rem;
  color: #c7dcff;
  font-size: .78rem;
  font-weight: 700;
  line-height: 1.2;
  white-space: nowrap;
}

.rule-type-folder_name_regex { border-color: #7c5bb3; color: #dcc8ff; }
.rule-type-archive_entry_text { border-color: #277a75; color: #a7f3d0; }

.tag-rule-edit-form {
  display: grid;
  grid-column: 1 / -1;
  grid-template-columns: auto repeat(3, minmax(0, 1fr)) auto;
  align-items: end;
}

.rule-preview {
  margin-top: 1rem;
}

@media (max-width: 800px) {
  .tag-rule-fields,
  .tag-rule-edit-form {
    grid-template-columns: 1fr;
  }

  .tag-rule-row {
    grid-template-columns: 1fr;
    gap: .75rem;
  }
}
</style>
