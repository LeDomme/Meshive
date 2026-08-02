<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, useId } from "vue"

const props = withDefaults(defineProps<{
  color: string | null
  description: string | null
  focusable?: boolean
}>(), {
  focusable: true,
})

const root = ref<HTMLElement | null>(null)
const tooltip = ref<HTMLElement | null>(null)
const visible = ref(false)
const positioned = ref(false)
const hovered = ref(false)
const focusedWithin = ref(false)
const tooltipPosition = ref({ left: "0px", top: "0px" })
const tooltipId = `tag-description-${useId()}`
const tooltipText = computed(() => props.description?.trim() || "")

function updatePosition() {
  if (!root.value || !tooltip.value) return

  const anchor = root.value.getBoundingClientRect()
  const bubble = tooltip.value.getBoundingClientRect()
  const margin = 12
  const gap = 8
  const maximumLeft = Math.max(margin, window.innerWidth - margin - bubble.width)
  const left = Math.min(
    maximumLeft,
    Math.max(margin, anchor.left + anchor.width / 2 - bubble.width / 2),
  )
  let top = anchor.top - bubble.height - gap

  if (top < margin) top = anchor.bottom + gap
  if (top + bubble.height > window.innerHeight - margin) {
    top = Math.max(margin, window.innerHeight - margin - bubble.height)
  }

  tooltipPosition.value = { left: `${left}px`, top: `${top}px` }
  positioned.value = true
}

function startTracking() {
  window.addEventListener("resize", updatePosition)
  window.addEventListener("scroll", updatePosition, true)
}

function stopTracking() {
  window.removeEventListener("resize", updatePosition)
  window.removeEventListener("scroll", updatePosition, true)
}

async function showTooltip() {
  if (!tooltipText.value || visible.value) return
  visible.value = true
  positioned.value = false
  startTracking()
  await nextTick()
  updatePosition()
}

function hideTooltip() {
  visible.value = false
  positioned.value = false
  stopTracking()
}

function handlePointerEnter() {
  hovered.value = true
  void showTooltip()
}

function handlePointerLeave() {
  hovered.value = false
  if (!focusedWithin.value) hideTooltip()
}

function handleFocusIn() {
  focusedWithin.value = true
  void showTooltip()
}

function handleFocusOut(event: FocusEvent) {
  if (root.value?.contains(event.relatedTarget as Node | null)) return
  focusedWithin.value = false
  if (!hovered.value) hideTooltip()
}

onBeforeUnmount(stopTracking)
</script>

<template>
  <span
    ref="root"
    class="tag-chip"
    :style="{ '--tag-color': color || '#5eead4' }"
    :tabindex="tooltipText && focusable ? 0 : undefined"
    :aria-describedby="visible ? tooltipId : undefined"
    @pointerenter="handlePointerEnter"
    @pointerleave="handlePointerLeave"
    @focusin="handleFocusIn"
    @focusout="handleFocusOut"
    @keydown.esc="hideTooltip"
  >
    <slot />
  </span>
  <Teleport to="body">
    <div
      v-if="visible"
      :id="tooltipId"
      ref="tooltip"
      class="tag-description-tooltip"
      :class="{ 'tag-description-tooltip-positioned': positioned }"
      :style="{
        '--tag-color': color || '#5eead4',
        left: tooltipPosition.left,
        top: tooltipPosition.top,
      }"
      role="tooltip"
    >
      {{ tooltipText }}
    </div>
  </Teleport>
</template>
