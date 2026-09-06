<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"

const props = defineProps<{ modelValue:string; disabled?:boolean; label?:string }>()
const emit = defineEmits<{ "update:modelValue":[value:string] }>()
const open = ref(false), value = ref(props.modelValue), error = ref(""), root = ref<HTMLElement|null>(null), hexInput = ref<HTMLInputElement|null>(null)
const colours = ["#5eead4", "#38bdf8", "#818cf8", "#c084fc", "#f472b6", "#fb7185", "#f59e0b", "#a3e635"]
const swatchStyle = computed(() => ({ backgroundColor: valid(props.modelValue) ? props.modelValue : "#64748b" }))
function valid(value:string) { return /^#[0-9a-f]{6}$/i.test(value) }
function commit(candidate:string) { const normalized = candidate.trim().toUpperCase(); if (!valid(normalized)) { error.value = "Use a six-digit HEX colour, for example #38BDF8."; return }; error.value = ""; value.value = normalized; emit("update:modelValue", normalized) }
function toggle() { if (props.disabled) return; open.value = !open.value; if (open.value) nextTick(() => hexInput.value?.focus()) }
function close() { open.value = false; error.value = ""; value.value = props.modelValue }
function choose(colour:string) { value.value = colour; commit(colour) }
function outside(event:MouseEvent) { if (open.value && root.value && !root.value.contains(event.target as Node)) close() }
function keydown(event:KeyboardEvent) { if (event.key === "Escape") close() }
watch(() => props.modelValue, (next) => { value.value = next })
onMounted(() => { document.addEventListener("mousedown", outside); document.addEventListener("keydown", keydown) })
onBeforeUnmount(() => { document.removeEventListener("mousedown", outside); document.removeEventListener("keydown", keydown) })
</script>

<template><div ref="root" class="colour-picker"><span class="colour-picker-label">{{ label ?? "Colour" }}</span><button class="colour-trigger" type="button" :disabled="disabled" :aria-expanded="open" aria-haspopup="dialog" @click="toggle"><span class="colour-swatch" :style="swatchStyle" aria-hidden="true"></span><span>{{ modelValue.toUpperCase() }}</span></button><section v-if="open" class="colour-popover" role="dialog" :aria-label="`${label ?? 'Colour'} picker`"><label><span>HEX colour</span><input ref="hexInput" v-model="value" inputmode="text" maxlength="7" spellcheck="false" @change="commit(value)" @keydown.enter.prevent="commit(value)"></label><p v-if="error" class="form-error" role="alert">{{ error }}</p><div class="colour-options" aria-label="Suggested colours"><button v-for="colour in colours" :key="colour" type="button" class="colour-option" :class="{ selected:modelValue.toUpperCase() === colour.toUpperCase() }" :style="{ backgroundColor:colour }" :aria-label="`Use ${colour}`" :aria-pressed="modelValue.toUpperCase() === colour.toUpperCase()" @click="choose(colour)"></button></div><button class="secondary-button" type="button" @click="close">Done</button></section></div></template>

<style scoped>.colour-picker{position:relative;display:grid;gap:.35rem}.colour-picker-label{font-weight:650}.colour-trigger{display:flex;align-items:center;gap:.6rem;min-height:2.8rem;padding:.45rem .7rem;border:1px solid #334155;border-radius:.6rem;color:#f8fafc;background:#0b1220;font:inherit;text-align:left}.colour-trigger:hover:not(:disabled){border-color:#475569}.colour-swatch{width:1.25rem;height:1.25rem;border:1px solid rgb(255 255 255 / 35%);border-radius:.35rem}.colour-popover{position:absolute;z-index:10;top:calc(100% + .4rem);left:0;display:grid;gap:.7rem;width:min(18rem,calc(100vw - 3rem));padding:1rem;border:1px solid var(--meshive-border);border-radius:.75rem;background:var(--meshive-panel);box-shadow:0 16px 36px rgb(0 0 0 / 28%)}.colour-popover label{display:grid;gap:.35rem}.colour-options{display:grid;grid-template-columns:repeat(4,1fr);gap:.5rem}.colour-option{width:100%;aspect-ratio:1;border:2px solid transparent;border-radius:.45rem}.colour-option.selected{border-color:#f8fafc;box-shadow:0 0 0 2px var(--meshive-cyan)}.form-error{margin:0;font-size:.85rem}</style>
