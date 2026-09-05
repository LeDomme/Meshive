<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from "vue"
import { apiRequest } from "../../api"
import AdminHeader from "../../components/AdminHeader.vue"
import TagChip from "../../components/TagChip.vue"
import { useAuthStore } from "../../stores/auth"

interface Tag { id:number; name:string; color:string|null; description:string|null }
interface Source { id:number; name:string }
interface Target { target_type:string; folder_segment:boolean }
interface Rule { id:number; library_source_id:number|null; legacy_kind:string|null; match_mode:"contains"|"regex"|"path_relation"; pattern:string|null; path_value:string|null; path_relation:"direct_child"|"self_or_descendant"|null; enabled:boolean; targets:Target[]; match_count:number }
interface Preview { model_name:string; relative_path:string }

const auth = useAuthStore()
const canTags = auth.can("tags.manage")
const canRules = auth.can("tag_rules.manage") && Boolean(auth.user?.source_access.all_sources)
const tags = ref<Tag[]>([]), sources = ref<Source[]>([]), rules = ref<Rule[]>([])
const selectedId = ref<number|null>(null), editingRule = ref<number|null>(null)
const tagMode = ref<"view"|"create"|"edit">("view"), busyAction = ref<string|null>(null)
const errorMessage = ref(""), successMessage = ref(""), preview = ref<Preview[]>([]), previewAttempted = ref(false)
const selected = computed(() => tags.value.find((tag) => tag.id === selectedId.value) ?? null)
const textMode = computed(() => ruleForm.match_mode !== "path_relation")
const targetOptions = [["model_relative_path", "Model relative path"], ["archive_filename", "Archive filename"], ["archive_entry_path", "Archive entry path"], ["archive_entry_name", "Archive entry filename"]] as const
const tagForm = reactive({ name:"", color:"#5eead4", description:"" })
const ruleForm = reactive({ match_mode:"contains" as Rule["match_mode"], pattern:"", path_value:"", path_relation:"self_or_descendant", library_source_id:"", enabled:true, targets:["archive_entry_path"] as string[], folder_segment:false })

function busy(action:string) { return busyAction.value === action }
function clearMessages() { errorMessage.value = ""; successMessage.value = "" }
function showError(error:unknown, fallback:string) { errorMessage.value = error instanceof Error ? error.message : fallback }
function resetTagForm() { Object.assign(tagForm, { name:"", color:"#5eead4", description:"" }) }
function resetRule() { Object.assign(ruleForm, { match_mode:"contains", pattern:"", path_value:"", path_relation:"self_or_descendant", library_source_id:"", enabled:true, targets:["archive_entry_path"], folder_segment:false }); editingRule.value = null; preview.value = []; previewAttempted.value = false }
async function run(action:string, task:() => Promise<void>, fallback:string) {
  if (busyAction.value) return
  clearMessages(); busyAction.value = action
  try { await task() } catch (error) { showError(error, fallback) } finally { busyAction.value = null }
}
async function loadRules() { rules.value = canRules && selectedId.value ? await apiRequest<Rule[]>(`/api/admin/tags/${selectedId.value}/assignment-rules`) : [] }
async function load() { tags.value = await apiRequest<Tag[]>("/api/admin/tags"); if (!selected.value) selectedId.value = tags.value[0]?.id ?? null; if (canRules) sources.value = await apiRequest<Source[]>("/api/admin/tags/library-sources"); await loadRules() }
function selectTag(id:number) { selectedId.value = id; tagMode.value = "view"; resetTagForm(); resetRule(); clearMessages(); void loadRules().catch((error) => showError(error, "Unable to load assignment rules")) }
function startCreate() { resetTagForm(); resetRule(); tagMode.value = "create"; clearMessages() }
function startEditTag() { if (!selected.value) return; Object.assign(tagForm, selected.value); tagMode.value = "edit"; clearMessages() }
function cancelTagEditor() { tagMode.value = "view"; resetTagForm(); clearMessages() }
async function saveTag() {
  const updating = tagMode.value === "edit"
  await run("tag", async () => { const saved = await apiRequest<Tag>(updating ? `/api/admin/tags/${selectedId.value}` : "/api/admin/tags", { method:updating ? "PUT" : "POST", body:JSON.stringify({ ...tagForm, description:tagForm.description || null }) }); selectedId.value = saved.id; tagMode.value = "view"; await load(); successMessage.value = `Tag ${updating ? "updated" : "created"}.`; await nextTick() }, "Unable to save tag")
}
async function deleteTag() {
  if (!selected.value || !window.confirm(`Delete tag “${selected.value.name}”?`)) return
  const tagName = selected.value.name
  await run("delete-tag", async () => { await apiRequest(`/api/admin/tags/${selected.value!.id}`, { method:"DELETE" }); selectedId.value = null; tagMode.value = "view"; await load(); successMessage.value = `Tag “${tagName}” deleted.` }, "Unable to delete tag")
}
function rulePayload() { const library_source_id = ruleForm.library_source_id ? Number(ruleForm.library_source_id) : null; return ruleForm.match_mode === "path_relation" ? { match_mode:"path_relation", path_value:ruleForm.path_value, path_relation:ruleForm.path_relation, library_source_id, enabled:ruleForm.enabled, targets:[{ target_type:"model_relative_path", folder_segment:false }] } : { match_mode:ruleForm.match_mode, pattern:ruleForm.pattern, library_source_id, enabled:ruleForm.enabled, targets:ruleForm.targets.map((target_type) => ({ target_type, folder_segment:target_type === "model_relative_path" && ruleForm.folder_segment })) } }
function payloadForRule(rule:Rule) { return rule.match_mode === "path_relation" ? { match_mode:rule.match_mode, path_value:rule.path_value, path_relation:rule.path_relation, library_source_id:rule.library_source_id, enabled:rule.enabled, targets:[{ target_type:"model_relative_path", folder_segment:false }] } : { match_mode:rule.match_mode, pattern:rule.pattern, library_source_id:rule.library_source_id, enabled:rule.enabled, targets:rule.targets } }
async function saveRule() { if (!selectedId.value) return; const updating = editingRule.value !== null; await run("rule", async () => { await apiRequest(updating ? `/api/admin/tag-assignment-rules/${editingRule.value}` : `/api/admin/tags/${selectedId.value}/assignment-rules`, { method:updating ? "PUT" : "POST", body:JSON.stringify(rulePayload()) }); resetRule(); await loadRules(); successMessage.value = `Assignment rule ${updating ? "updated" : "added"}.` }, "Unable to save assignment rule") }
async function previewRule() { previewAttempted.value = true; await run("preview", async () => { preview.value = await apiRequest<Preview[]>("/api/admin/tag-assignment-rules/preview", { method:"POST", body:JSON.stringify({ ...rulePayload(), limit:25 }) }) }, "Unable to preview assignment rule") }
function editRule(rule:Rule) { editingRule.value = rule.id; Object.assign(ruleForm, { match_mode:rule.match_mode, pattern:rule.pattern ?? "", path_value:rule.path_value ?? "", path_relation:rule.path_relation ?? "self_or_descendant", library_source_id:rule.library_source_id ? String(rule.library_source_id) : "", enabled:rule.enabled, targets:rule.targets.map((target) => target.target_type), folder_segment:rule.targets.some((target) => target.target_type === "model_relative_path" && target.folder_segment) }); preview.value = []; previewAttempted.value = false; clearMessages() }
async function setRuleEnabled(rule:Rule) { await run(`enabled-${rule.id}`, async () => { await apiRequest(`/api/admin/tag-assignment-rules/${rule.id}`, { method:"PUT", body:JSON.stringify({ ...payloadForRule(rule), enabled:!rule.enabled }) }); await loadRules(); successMessage.value = `Assignment rule ${rule.enabled ? "disabled" : "enabled"}.` }, "Unable to update assignment rule") }
async function reevaluate(rule:Rule) { await run(`reevaluate-${rule.id}`, async () => { await apiRequest(`/api/admin/tag-assignment-rules/${rule.id}/re-evaluate`, { method:"POST" }); await loadRules(); successMessage.value = "Assignment rule re-evaluated." }, "Unable to re-evaluate assignment rule") }
async function removeRule(rule:Rule) { if (!window.confirm(`Delete ${modeLabel(rule).toLowerCase()} assignment rule for tag “${selected.value?.name ?? "this tag"}”?`)) return; await run(`delete-${rule.id}`, async () => { await apiRequest(`/api/admin/tag-assignment-rules/${rule.id}`, { method:"DELETE" }); if (editingRule.value === rule.id) resetRule(); await loadRules(); successMessage.value = "Assignment rule deleted." }, "Unable to delete assignment rule") }
function modeLabel(rule:Rule) { return rule.match_mode === "path_relation" ? "Folder path" : rule.match_mode === "regex" ? "Regular expression" : "Text contains" }
function targetLabels(rule:Rule) { return rule.targets.map((target) => targetOptions.find(([value]) => value === target.target_type)?.[1] ?? target.target_type).join(", ") }
watch(() => ruleForm.match_mode, () => { if (ruleForm.match_mode === "path_relation") ruleForm.targets = ["model_relative_path"] })
onMounted(() => load().catch((error) => showError(error, "Unable to load tags")))
</script>

<template>
  <main class="admin-shell tags-admin">
    <AdminHeader title="Tags" />
    <p class="admin-intro">Organise tags and define assignment rules using model and archive metadata.</p>
    <p v-if="errorMessage" class="form-error error-panel" role="alert">{{ errorMessage }}</p>
    <p v-if="successMessage" class="success-panel" role="status">{{ successMessage }}</p>

    <div class="management-layout tags-management-layout">
      <section class="panel role-list-panel tag-list-panel">
        <div class="panel-heading"><div><h2>Tags</h2><p class="panel-copy">Select a tag to view its details and rules.</p></div></div>
        <button v-if="canTags" class="secondary-button new-role-button" type="button" :disabled="busyAction !== null" @click="startCreate">Create tag</button>
        <div v-if="tags.length" class="tag-master-list">
          <button v-for="tag in tags" :key="tag.id" class="role-card tag-card" :class="{ selected:tag.id === selectedId && tagMode === 'view' }" type="button" :aria-pressed="tag.id === selectedId" :disabled="busyAction !== null" @click="selectTag(tag.id)"><span><strong><span class="tag-colour" :style="{ backgroundColor:tag.color ?? 'var(--muted-text-color)' }" aria-hidden="true"></span>{{ tag.name }}</strong><small>{{ tag.description || "No description" }}</small></span><span class="role-card-meta"><TagChip :color="tag.color" :description="tag.description">Tag</TagChip></span></button>
        </div>
        <div v-else class="empty-state"><strong>No tags yet</strong><p>Create a tag to start organising your library.</p></div>
      </section>

      <section class="panel tag-detail-panel">
        <form v-if="tagMode !== 'view'" class="tag-management-form" @submit.prevent="saveTag">
          <div class="panel-heading"><div><h2>{{ tagMode === 'create' ? 'Create tag' : 'Edit tag' }}</h2><p class="panel-copy">{{ tagMode === 'create' ? 'Give the tag a clear name and optional description.' : `Update “${selected?.name}”.` }}</p></div></div>
          <fieldset><legend>Tag details</legend><label><span>Name</span><input v-model="tagForm.name" required maxlength="80" :disabled="busy('tag')"></label><label><span>Colour</span><input v-model="tagForm.color" type="color" :disabled="busy('tag')"></label><label><span>Description</span><textarea v-model="tagForm.description" maxlength="1000" :disabled="busy('tag')"></textarea></label></fieldset>
          <div class="user-actions"><button class="primary-button" :disabled="busyAction !== null" type="submit">{{ busy('tag') ? 'Saving…' : tagMode === 'create' ? 'Create tag' : 'Save changes' }}</button><button class="secondary-button" :disabled="busyAction !== null" type="button" @click="cancelTagEditor">Cancel</button></div>
        </form>

        <template v-else-if="selected">
          <div class="panel-heading tag-detail-heading"><div><h2>{{ selected.name }}</h2><p class="panel-copy">{{ selected.description || 'No description. Add one to help your team use this tag consistently.' }}</p></div><div v-if="canTags" class="user-actions"><button class="secondary-button" :disabled="busyAction !== null" type="button" @click="startEditTag">Edit tag</button><button class="danger-button" :disabled="busyAction !== null" type="button" @click="deleteTag">{{ busy('delete-tag') ? 'Deleting…' : 'Delete tag' }}</button></div></div>

          <section v-if="canRules" class="assignment-rules-section" aria-labelledby="assignment-rules-heading">
            <div class="section-heading"><div><h2 id="assignment-rules-heading">Assignment rules</h2><p class="panel-copy">A rule assigns this tag when any selected target matches.</p></div></div>
            <form class="rule-management-form" @submit.prevent="saveRule">
              <fieldset><legend>{{ editingRule ? 'Edit assignment rule' : 'Add assignment rule' }}</legend>
                <div class="rule-grid"><label><span>Match mode</span><select v-model="ruleForm.match_mode" :disabled="busyAction !== null"><option value="contains">Text contains</option><option value="regex">Regular expression</option><option value="path_relation">Folder path</option></select></label><label><span>Source scope</span><select v-model="ruleForm.library_source_id" :disabled="busyAction !== null"><option value="">All sources</option><option v-for="source in sources" :key="source.id" :value="String(source.id)">{{ source.name }}</option></select></label><label v-if="textMode" class="wide"><span>{{ ruleForm.match_mode === 'regex' ? 'Regular expression' : 'Text to match' }}</span><input v-model="ruleForm.pattern" required :disabled="busyAction !== null" :placeholder="ruleForm.match_mode === 'regex' ? '(_P|P\\.)[2-9]' : 'Search text'"><small v-if="ruleForm.match_mode === 'regex'">Case-insensitive RE2 search. Example: <code>(_P|P\.)[2-9]</code></small></label><label v-else class="wide"><span>Folder path</span><input v-model="ruleForm.path_value" required :disabled="busyAction !== null"><small>Matches the selected folder and the configured relation.</small></label><label v-if="!textMode"><span>Include</span><select v-model="ruleForm.path_relation" :disabled="busyAction !== null"><option value="self_or_descendant">Folder and subfolders</option><option value="direct_child">Direct children only</option></select></label><fieldset v-if="textMode" class="wide target-picker"><legend>Search targets</legend><label v-for="[target, label] in targetOptions" :key="target" class="checkbox-row"><input v-model="ruleForm.targets" type="checkbox" :value="target" :disabled="busyAction !== null"> {{ label }}</label><label v-if="ruleForm.targets.includes('model_relative_path')" class="checkbox-row"><input v-model="ruleForm.folder_segment" type="checkbox" :disabled="busyAction !== null"> Match individual folder names</label></fieldset><label class="checkbox-row enabled-choice"><input v-model="ruleForm.enabled" type="checkbox" :disabled="busyAction !== null"> Enabled</label></div>
                <div class="user-actions"><button class="primary-button" :disabled="busyAction !== null" type="submit">{{ busy('rule') ? 'Saving…' : editingRule ? 'Save rule' : 'Add rule' }}</button><button v-if="textMode" class="secondary-button" :disabled="busyAction !== null" type="button" @click="previewRule">{{ busy('preview') ? 'Loading preview…' : 'Preview matches' }}</button><button v-if="editingRule" class="secondary-button" :disabled="busyAction !== null" type="button" @click="resetRule">Cancel edit</button></div>
              </fieldset>
            </form>
            <div v-if="previewAttempted" class="preview-panel" aria-live="polite"><strong>Preview</strong><span v-if="busy('preview')">Finding matches…</span><template v-else-if="preview.length"><p>Showing up to {{ preview.length }} matching models.</p><ul><li v-for="model in preview" :key="model.relative_path">{{ model.model_name }} · {{ model.relative_path }}</li></ul></template><p v-else>No matching models found. Preview does not save this rule.</p></div>

            <div class="rule-list"><article v-for="rule in rules" :key="rule.id" class="rule-card"><div class="rule-card-main"><div class="rule-badges"><span class="status-badge custom">{{ modeLabel(rule) }}</span><span v-if="rule.legacy_kind" class="status-badge migrated">Migrated</span><span class="status-badge" :class="rule.enabled ? 'active' : 'disabled'">{{ rule.enabled ? 'Enabled' : 'Disabled' }}</span><span class="status-badge system">{{ rule.match_count }} matches</span></div><strong>{{ targetLabels(rule) }}</strong><small>{{ rule.library_source_id ? 'Limited to one library source' : 'All library sources' }}</small></div><div class="rule-actions"><button class="secondary-button" :disabled="busyAction !== null" type="button" @click="editRule(rule)">Edit</button><button class="secondary-button" :disabled="busyAction !== null" type="button" @click="setRuleEnabled(rule)">{{ busy(`enabled-${rule.id}`) ? 'Saving…' : rule.enabled ? 'Disable' : 'Enable' }}</button><button class="secondary-button" :disabled="busyAction !== null" type="button" @click="reevaluate(rule)">{{ busy(`reevaluate-${rule.id}`) ? 'Evaluating…' : 'Re-evaluate' }}</button><button class="danger-button" :disabled="busyAction !== null" type="button" @click="removeRule(rule)">{{ busy(`delete-${rule.id}`) ? 'Deleting…' : 'Delete' }}</button></div></article><div v-if="!rules.length" class="empty-state"><strong>No assignment rules</strong><p>Add a rule to assign this tag from indexed model or archive metadata.</p></div></div>
          </section>
          <section v-else class="assignment-rules-section"><h2>Assignment rules</h2><p class="panel-copy">You can view tag details, but assignment rules are unavailable for this account.</p></section>
        </template>
        <div v-else class="empty-state detail-empty"><strong>Choose a tag</strong><p>Select a tag from the list to view details and assignment rules.</p></div>
      </section>
    </div>
  </main>
</template>

<style scoped>
.tags-management-layout { align-items:start; }
.tag-list-panel { min-width:0; }
.tag-master-list { display:grid; gap:.5rem; margin-top:.8rem; }
.tag-card { min-height:4.5rem; }
.tag-card strong { display:flex; align-items:center; gap:.5rem; }
.tag-colour { width:.7rem; height:.7rem; border:1px solid var(--border-color); border-radius:50%; flex:0 0 auto; }
.tag-card.selected { box-shadow:inset .25rem 0 var(--accent-color); }
.tag-detail-panel { min-width:0; }
.tag-detail-heading { padding-bottom:1rem; border-bottom:1px solid var(--border-color); }
.tag-management-form fieldset, .rule-management-form fieldset { display:grid; gap:.9rem; margin:1rem 0; }
.tag-management-form label, .rule-grid > label { display:grid; gap:.35rem; }
.rule-management-form > fieldset { padding:1rem; border:1px solid var(--border-color); border-radius:.5rem; }
.rule-management-form legend { padding:0 .35rem; font-weight:600; }
.rule-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:.85rem; }
.wide { grid-column:1 / -1; }
.rule-grid small { color:var(--muted-text-color); }
.target-picker { display:flex !important; flex-wrap:wrap; gap:.55rem 1.2rem; margin:0; padding:.8rem; }
.enabled-choice { align-self:end; }
.assignment-rules-section { margin-top:1.5rem; }
.section-heading { margin-bottom:.5rem; }
.section-heading h2 { margin:0; }
.preview-panel { display:grid; gap:.35rem; margin:1rem 0; padding:1rem; border-left:3px solid var(--accent-color); background:var(--muted-background); }
.preview-panel p, .preview-panel ul { margin:.15rem 0; }
.preview-panel ul { padding-left:1.25rem; }
.rule-list { display:grid; gap:.7rem; margin-top:1rem; }
.rule-card { display:grid; grid-template-columns:minmax(0,1fr) auto; gap:1rem; align-items:center; padding:1rem; border:1px solid var(--border-color); border-radius:.5rem; background:var(--panel-background); }
.rule-card-main { display:grid; gap:.45rem; min-width:0; }
.rule-card-main small { color:var(--muted-text-color); }
.rule-badges { display:flex; flex-wrap:wrap; gap:.4rem; }
.status-badge.migrated { background:var(--muted-background); color:var(--muted-text-color); }
.rule-actions { display:flex; flex-wrap:wrap; justify-content:flex-end; gap:.45rem; }
.empty-state { padding:1.2rem; margin-top:.8rem; border:1px dashed var(--border-color); border-radius:.5rem; background:var(--muted-background); text-align:center; color:var(--muted-text-color); }
.empty-state p { margin:.35rem 0 0; }
.detail-empty { margin:0; }
@media (max-width: 900px) { .rule-card { grid-template-columns:1fr; } .rule-actions { justify-content:flex-start; } }
@media (max-width: 700px) { .rule-grid { grid-template-columns:1fr; } .wide { grid-column:auto; } .target-picker { display:grid !important; } .tag-detail-heading { gap:.8rem; } }
</style>
