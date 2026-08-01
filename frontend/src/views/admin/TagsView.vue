<script setup lang="ts">
import { onMounted, ref } from "vue"
import { apiRequest } from "../../api"
import AdminHeader from "../../components/AdminHeader.vue"

interface Tag { id: number; name: string; color: string | null; description: string | null }
interface Source { id: number; name: string }
interface Rule { id: number; library_source_id: number; relative_path: string; tag_id: number; recursive: boolean; tag_name: string }

const tags = ref<Tag[]>([])
const sources = ref<Source[]>([])
const rules = ref<Rule[]>([])
const name = ref("")
const color = ref("#5eead4")
const sourceId = ref("")
const tagId = ref("")
const path = ref("")
const recursive = ref(true)

async function load() {
  ;[tags.value, sources.value, rules.value] = await Promise.all([
    apiRequest<Tag[]>("/api/tags"),
    apiRequest<Source[]>("/api/admin/library-sources"),
    apiRequest<Rule[]>("/api/admin/folder-tag-rules"),
  ])
}
async function createTag() {
  await apiRequest("/api/admin/tags", { method: "POST", body: JSON.stringify({ name: name.value, color: color.value, description: null }) })
  name.value = ""
  await load()
}
async function deleteTag(id: number) {
  if (!confirm("Delete this tag and all its assignments?")) return
  await apiRequest(`/api/admin/tags/${id}`, { method: "DELETE" })
  await load()
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
onMounted(load)
</script>

<template>
  <main class="admin-shell">
    <AdminHeader title="Tags" />
    <section class="admin-grid">
      <div class="panel">
        <h2>Tags</h2>
        <form class="source-form" @submit.prevent="createTag">
          <label><span>Name</span><input v-model="name" required></label>
          <label><span>Colour</span><input v-model="color" type="color"></label>
          <button class="primary-button">Create tag</button>
        </form>
        <div class="source-list">
          <div v-for="tag in tags" :key="tag.id" class="source-row">
            <span class="tag-chip" :style="{ '--tag-color': tag.color || '#5eead4' }">{{ tag.name }}</span>
            <button class="danger-button" @click="deleteTag(tag.id)">Delete</button>
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
    </section>
  </main>
</template>
