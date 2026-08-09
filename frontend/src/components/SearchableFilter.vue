<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  useId,
} from "vue"

interface SearchableFilterOption {
  value: string
  label?: string
  count?: number
}

const props = withDefaults(
  defineProps<{
    modelValue: string
    label: string
    allLabel: string
    options: SearchableFilterOption[]
    searchPlaceholder?: string
    align?: "start" | "end"
    showAllOption?: boolean
  }>(),
  {
    searchPlaceholder: "Search options",
    align: "start",
    showAllOption: true,
  },
)

const emit = defineEmits<{
  "update:modelValue": [value: string]
  change: [value: string]
}>()

const root = ref<HTMLElement | null>(null)
const trigger = ref<HTMLButtonElement | null>(null)
const searchInput = ref<HTMLInputElement | null>(null)
const optionList = ref<HTMLElement | null>(null)
const isOpen = ref(false)
const search = ref("")
const optionScrollTop = ref(0)
const listboxId = `searchable-filter-${useId()}`

function optionLabel(option: SearchableFilterOption) {
  return option.label ?? option.value
}

const selectedLabel = computed(() => {
  if (!props.modelValue) return props.allLabel
  const selected = props.options.find((option) => option.value === props.modelValue)
  return selected ? optionLabel(selected) : props.modelValue
})

const filteredOptions = computed(() => {
  const term = search.value.trim().toLocaleLowerCase()
  if (!term) return props.options
  return props.options.filter((option) =>
    optionLabel(option).toLocaleLowerCase().includes(term),
  )
})

async function open() {
  isOpen.value = true
  await nextTick()
  searchInput.value?.focus()
  if (optionScrollTop.value > 0) {
    optionList.value?.scrollTo({ top: optionScrollTop.value })
  } else {
    optionList.value
      ?.querySelector<HTMLButtonElement>(".searchable-filter-option.selected")
      ?.scrollIntoView({ block: "nearest" })
  }
}

function close() {
  isOpen.value = false
  search.value = ""
}

function toggle() {
  if (isOpen.value) close()
  else void open()
}

function selectOption(value: string) {
  if (value !== props.modelValue) {
    emit("update:modelValue", value)
    emit("change", value)
  }
  close()
  trigger.value?.focus()
}

function closeAndFocus() {
  close()
  trigger.value?.focus()
}

function rememberOptionScroll(event: Event) {
  optionScrollTop.value = (event.currentTarget as HTMLElement).scrollTop
}

function resetOptionScroll() {
  optionScrollTop.value = 0
  if (optionList.value) optionList.value.scrollTop = 0
}

function focusFirstOption() {
  optionList.value?.querySelector<HTMLButtonElement>("button")?.focus()
}

function handleDocumentPointerDown(event: PointerEvent) {
  if (isOpen.value && !root.value?.contains(event.target as Node)) close()
}

onMounted(() => {
  document.addEventListener("pointerdown", handleDocumentPointerDown)
  window.addEventListener("meshive:reset-filter-scroll", resetOptionScroll)
})
onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", handleDocumentPointerDown)
  window.removeEventListener("meshive:reset-filter-scroll", resetOptionScroll)
})
</script>

<template>
  <div
    ref="root"
    class="searchable-filter"
    :class="{ 'searchable-filter--align-end': align === 'end' }"
    @keydown.esc.stop.prevent="closeAndFocus"
  >
    <button
      ref="trigger"
      class="searchable-filter-trigger"
      type="button"
      :aria-label="label"
      aria-haspopup="listbox"
      :aria-expanded="isOpen"
      :aria-controls="listboxId"
      @click="toggle"
    >
      <span
        v-if="$attrs.draggable === 'true'"
        class="searchable-filter-drag-grip"
        aria-hidden="true"
      ></span>
      <span>{{ selectedLabel }}</span>
      <span class="searchable-filter-chevron" aria-hidden="true">⌄</span>
    </button>

    <div v-if="isOpen" class="searchable-filter-panel">
      <label class="searchable-filter-search">
        <span class="sr-only">Search {{ label.toLocaleLowerCase() }}</span>
        <input
          ref="searchInput"
          v-model="search"
          type="search"
          :placeholder="searchPlaceholder"
          autocomplete="off"
          @keydown.down.prevent="focusFirstOption"
        >
      </label>

      <div
        :id="listboxId"
        ref="optionList"
        class="searchable-filter-options"
        role="listbox"
        :aria-label="label"
        @scroll.passive="rememberOptionScroll"
      >
        <button
          v-if="showAllOption"
          class="searchable-filter-option"
          :class="{ selected: modelValue === '' }"
          type="button"
          role="option"
          :aria-selected="modelValue === ''"
          @click="selectOption('')"
        >
          <span>{{ allLabel }}</span>
        </button>

        <button
          v-for="option in filteredOptions"
          :key="option.value"
          class="searchable-filter-option"
          :class="{ selected: modelValue === option.value }"
          type="button"
          role="option"
          :aria-selected="modelValue === option.value"
          @click="selectOption(option.value)"
        >
          <span>{{ optionLabel(option) }}</span>
          <small v-if="option.count !== undefined">{{ option.count }}</small>
        </button>

        <p v-if="filteredOptions.length === 0" class="searchable-filter-empty">
          No matching options
        </p>
      </div>
    </div>
  </div>
</template>
