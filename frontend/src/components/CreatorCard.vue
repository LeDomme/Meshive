<script setup lang="ts">
import { onMounted, ref, watch } from "vue"
import { RouterLink } from "vue-router"
import { apiRequest } from "../api"

interface CreatorLink { id: number; label: string; url: string }
interface Creator { id: number; display_name: string; description: string | null; model_count: number; artwork: { url: string } | null; links: CreatorLink[]; primary_link: CreatorLink | null }
const props = defineProps<{ creatorProfileId: number }>()
const creator = ref<Creator | null>(null)
function safeUrl(value: string): string | null { try { const url = new URL(value); return ["https:", "http:"].includes(url.protocol) ? url.href : null } catch { return null } }
async function load() { creator.value = null; try { creator.value = await apiRequest<Creator>(`/api/creators/${props.creatorProfileId}`) } catch { /* The model remains usable when the profile is unavailable. */ } }
onMounted(() => void load())
watch(() => props.creatorProfileId, () => void load())
</script>

<template>
  <section v-if="creator" class="creator-card" aria-label="Creator">
    <div class="creator-card-top"><RouterLink class="creator-artwork" :to="{ name: 'creator-detail', params: { id: creator.id } }"><img :src="creator.artwork?.url || '/favorite-fallbacks/favorite-creator.webp'" :alt="creator.artwork ? `${creator.display_name} artwork` : ''"></RouterLink><div class="creator-card-content"><p class="eyebrow">Creator</p><RouterLink class="creator-name" :to="{ name: 'creator-detail', params: { id: creator.id } }">{{ creator.display_name }}</RouterLink><p v-if="creator.description" class="creator-description">{{ creator.description }}</p><div class="creator-card-actions"><span>{{ creator.model_count }} {{ creator.model_count === 1 ? "model" : "models" }}</span><RouterLink :to="{ name: 'creator-detail', params: { id: creator.id } }">View all models</RouterLink></div></div></div>
    <div v-if="creator.links.length" class="creator-card-links"><a v-for="link in creator.links" :key="link.id" v-show="safeUrl(link.url)" :href="safeUrl(link.url)!" target="_blank" rel="noopener noreferrer">{{ link.label }} ↗</a></div>
  </section>
</template>
