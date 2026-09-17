<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue"
import { ApiError, apiRequest } from "../../api"

const props = defineProps<{ profileId: number | null }>()
const emit = defineEmits<{ changed: [] }>()
type Alias = { id: number; alias: string; normalized_alias: string }
type Profile = { id: number; display_name: string; normalized_name: string; description: string | null; aliases: Alias[] }
type Preview = { favorite_count: number; duplicate_favorite_count: number; duplicate_link_ids: number[]; link_conflicts: Array<{ source_link_id: number; label: string }>; artwork_conflict: boolean }
type MergeHistory = { id: number; source_display_name: string; undone_at: string | null }
const profile = ref<Profile | null>(null); const name = ref(""); const description = ref(""); const alias = ref(""); const mergeSourceId = ref<number | null>(null); const profiles = ref<Profile[]>([]); const preview = ref<Preview | null>(null); const history = ref<MergeHistory[]>([]); const error = ref("")
const candidates = computed(() => profiles.value.filter(item => item.id !== props.profileId))
const activeMerges = computed(() => history.value.filter(item => !item.undone_at))
async function load() { preview.value = null; alias.value = ""; if (!props.profileId) { profile.value = null; profiles.value = []; history.value = []; return } try { const [all, mergeHistory] = await Promise.all([apiRequest<Profile[]>("/api/admin/creator-profiles"), apiRequest<MergeHistory[]>(`/api/admin/creator-profiles/${props.profileId}/merge-history`)]); profiles.value = all; profile.value = all.find(item => item.id === props.profileId) ?? null; name.value = profile.value?.display_name ?? ""; description.value = profile.value?.description ?? ""; history.value = mergeHistory } catch (cause) { error.value = cause instanceof ApiError ? cause.message : "Unable to load creator profile" } }
async function save() { if (!profile.value) return; await apiRequest(`/api/admin/creator-profiles/${profile.value.id}`, { method: "PUT", body: JSON.stringify({ display_name: name.value, description: description.value || null }) }); await load() }
async function addAlias() { if (!profile.value || !alias.value.trim()) return; await apiRequest(`/api/admin/creator-profiles/${profile.value.id}/aliases`, { method: "POST", body: JSON.stringify({ alias: alias.value }) }); await load() }
async function removeAlias(item: Alias) { if (!profile.value) return; await apiRequest(`/api/admin/creator-profiles/${profile.value.id}/aliases/${item.id}`, { method: "DELETE" }); await load() }
async function refreshAfterMergeMutation() { const scrollY = window.scrollY; await load(); await nextTick(); window.scrollTo({ top: scrollY }); emit("changed") }
async function getPreview() { if (!profile.value || !mergeSourceId.value) return; const mergePreview = await apiRequest<Preview>("/api/admin/creator-profiles/merge/preview", { method: "POST", body: JSON.stringify({ target_profile_id: profile.value.id, source_profile_ids: [mergeSourceId.value] }) }); if (!mergePreview.artwork_conflict && !mergePreview.link_conflicts.length) { await applyMerge(mergePreview); return } preview.value = mergePreview }
async function applyMerge(mergePreview: Preview | Event | null = preview.value) { const resolvedPreview = mergePreview instanceof Event ? preview.value : mergePreview; if (!profile.value || !mergeSourceId.value || !resolvedPreview) return; const artwork = resolvedPreview.artwork_conflict ? prompt(`Artwork: target or source:${mergeSourceId.value}`, "target") : null; if (resolvedPreview.artwork_conflict && artwork !== "target" && artwork !== `source:${mergeSourceId.value}`) return; const link_resolutions = resolvedPreview.link_conflicts.map(item => ({ source_link_id: item.source_link_id, action: confirm(`Keep source link ${item.label}?`) ? "keep_source" : "keep_target" })); await apiRequest("/api/admin/creator-profiles/merge", { method: "POST", body: JSON.stringify({ target_profile_id: profile.value.id, source_profile_ids: [mergeSourceId.value], artwork_resolution: artwork, link_resolutions }) }); await refreshAfterMergeMutation() }
async function undoMerge(id: number) { await apiRequest(`/api/admin/creator-profiles/merges/${id}/undo`, { method: "POST" }); await refreshAfterMergeMutation() }
watch(() => props.profileId, () => void load(), { immediate: true })
</script>
<template>
  <section v-if="profile" class="creator-metadata-section creator-profile-section">
    <div class="creator-management-grid"><div class="creator-management-controls"><p v-if="error" class="form-error">{{ error }}</p><form class="source-form" @submit.prevent="save"><label><span>Display name</span><input v-model="name" required></label><label><span>Aliases</span><div class="creator-inline-form"><input v-model="alias" placeholder="Add alias"><button type="submit" class="secondary-button" @click.stop="addAlias">Add alias</button></div></label><label><span>Merge</span><div class="creator-inline-form"><select v-model.number="mergeSourceId"><option :value="null">Choose source profile</option><option v-for="item in candidates" :key="item.id" :value="item.id">{{ item.display_name }}</option></select><button type="button" class="secondary-button" :disabled="!mergeSourceId" @click="getPreview">Merge</button></div></label><div v-if="preview" class="merge-preview"><p>{{ preview.favorite_count }} favorites; {{ preview.duplicate_favorite_count }} duplicates; {{ preview.duplicate_link_ids.length }} duplicate links.</p><p v-if="preview.link_conflicts.length || preview.artwork_conflict" class="form-error">Conflicts need an explicit choice.</p><button type="button" class="danger-button" @click="applyMerge">Apply merge</button></div><div class="row-actions"><button class="primary-button">Save profile</button></div></form></div><div class="creator-management-list"><label><span>Description</span><textarea v-model="description" /></label><div class="creator-alias-list"><span v-for="item in profile.aliases.filter(alias => !activeMerges.some(merge => merge.source_display_name === alias.alias))" :key="item.id" class="creator-alias-chip">{{ item.alias }} <em>Alias</em> <button type="button" v-if="item.normalized_alias !== profile.normalized_name" class="text-button icon-action" aria-label="Remove alias" title="Remove alias" @click="removeAlias(item)">⦸</button></span><span v-for="merge in activeMerges" :key="`merge-${merge.id}`" class="creator-alias-chip merged-creator">{{ merge.source_display_name }} <em>Merged</em> <button type="button" class="text-button icon-action" aria-label="Remove merge" title="Undo merge" @click="undoMerge(merge.id)">⦸</button></span></div></div></div>
  </section>
</template>

<style scoped>
.creator-alias-list, .creator-inline-form { display: flex; flex-wrap: wrap; gap: .5rem; align-items: center; }
.creator-alias-list { margin: .5rem 0; }
.creator-alias-chip { display: inline-flex; align-items: center; gap: .35rem; padding: .25rem .5rem; border: 1px solid var(--meshive-border); border-radius: .5rem; }
.creator-inline-form { margin: .5rem 0 1rem; }
.creator-inline-form input, .creator-inline-form select { min-width: min(100%, 16rem); }
.creator-alias-chip em { color: var(--meshive-cyan); font-size: .8em; font-style: normal; }
.creator-management-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(16rem, 1fr); gap: 1rem; align-items: start; }
.creator-management-controls .source-form { max-width: 22rem; }
.creator-management-list { display: grid; gap: .75rem; }
.creator-management-list textarea { min-height: 5rem; max-width: 34rem; }
.creator-management-list .creator-alias-list { max-height: min(18rem, 100%); overflow: auto; align-content: start; padding: .6rem; border: 1px solid var(--meshive-border); border-radius: .6rem; scrollbar-color: var(--meshive-cyan) var(--meshive-ink); scrollbar-width: thin; }
.creator-management-list .creator-alias-list::-webkit-scrollbar { width: .55rem; }
.creator-management-list .creator-alias-list::-webkit-scrollbar-track { background: var(--meshive-ink); }
.creator-management-list .creator-alias-list::-webkit-scrollbar-thumb { background: var(--meshive-cyan); border-radius: 1rem; }
.icon-action { font-size: 1.1rem; line-height: 1; }
@media (max-width: 600px) { .creator-inline-form > * { width: 100%; } }
@media (max-width: 760px) { .creator-management-grid { grid-template-columns: 1fr; } }
</style>
