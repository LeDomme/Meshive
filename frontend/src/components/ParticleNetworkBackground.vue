<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue"

type Particle = {
  x: number
  y: number
  vx: number
  vy: number
  size: number
}

const CONNECTION_DISTANCE = 145
const CURSOR_RADIUS = 180
const FRAME_INTERVAL = 1000 / 30
const MAX_PARTICLES = 48
const canvas = ref<HTMLCanvasElement | null>(null)
const motionState = ref<"active" | "paused" | "reduced">("paused")

const particles: Particle[] = []
const pointer = { x: 0, y: 0, active: false }
let context: CanvasRenderingContext2D | null = null
let animationFrame = 0
let lastFrameTime = 0
let viewportWidth = 0
let viewportHeight = 0
let particleColor = "#36e7ff"
let networkColor = "#087cff"
let motionQuery: MediaQueryList | null = null

function targetParticleCount(width: number, height: number) {
  const area = width * height
  if (width < 640) return Math.min(12, Math.max(6, Math.round(area / 55_000)))
  return Math.min(MAX_PARTICLES, Math.max(24, Math.round(area / 85_000)))
}

function createParticle(): Particle {
  const angle = Math.random() * Math.PI * 2
  const speed = 6 + Math.random() * 8
  return {
    x: Math.random() * viewportWidth,
    y: Math.random() * viewportHeight,
    vx: Math.cos(angle) * speed,
    vy: Math.sin(angle) * speed,
    size: 2 + Math.random() * 1.5,
  }
}

function syncParticleCount() {
  const target = targetParticleCount(viewportWidth, viewportHeight)
  while (particles.length < target) particles.push(createParticle())
  if (particles.length > target) particles.length = target
}

function resizeCanvas() {
  if (!canvas.value) return

  const previousWidth = viewportWidth
  const previousHeight = viewportHeight
  viewportWidth = window.innerWidth
  viewportHeight = window.innerHeight
  const pixelRatio = Math.min(window.devicePixelRatio || 1, 2)

  canvas.value.width = Math.ceil(viewportWidth * pixelRatio)
  canvas.value.height = Math.ceil(viewportHeight * pixelRatio)
  context = canvas.value.getContext("2d")
  context?.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0)

  if (previousWidth && previousHeight) {
    for (const particle of particles) {
      particle.x = particle.x / previousWidth * viewportWidth
      particle.y = particle.y / previousHeight * viewportHeight
    }
  }

  const styles = getComputedStyle(document.documentElement)
  particleColor = styles.getPropertyValue("--meshive-cyan").trim() || particleColor
  networkColor = styles.getPropertyValue("--meshive-blue").trim() || networkColor
  syncParticleCount()
}

function updateParticles(deltaSeconds: number) {
  for (const particle of particles) {
    if (pointer.active) {
      const dx = particle.x - pointer.x
      const dy = particle.y - pointer.y
      const distance = Math.hypot(dx, dy)
      if (distance > 0 && distance < CURSOR_RADIUS) {
        const influence = 1 - distance / CURSOR_RADIUS
        particle.vx += dx / distance * influence * 12 * deltaSeconds
        particle.vy += dy / distance * influence * 12 * deltaSeconds
      }
    }

    const speed = Math.hypot(particle.vx, particle.vy)
    if (speed > 22) {
      particle.vx = particle.vx / speed * 22
      particle.vy = particle.vy / speed * 22
    }

    particle.x += particle.vx * deltaSeconds
    particle.y += particle.vy * deltaSeconds

    if (particle.x < -particle.size) particle.x = viewportWidth + particle.size
    else if (particle.x > viewportWidth + particle.size) particle.x = -particle.size
    if (particle.y < -particle.size) particle.y = viewportHeight + particle.size
    else if (particle.y > viewportHeight + particle.size) particle.y = -particle.size
  }
}

function drawNetwork() {
  if (!context) return
  context.clearRect(0, 0, viewportWidth, viewportHeight)
  context.lineWidth = 0.55
  context.strokeStyle = networkColor

  for (let firstIndex = 0; firstIndex < particles.length; firstIndex += 1) {
    const first = particles[firstIndex]
    for (let secondIndex = firstIndex + 1; secondIndex < particles.length; secondIndex += 1) {
      const second = particles[secondIndex]
      const distance = Math.hypot(first.x - second.x, first.y - second.y)
      if (distance >= CONNECTION_DISTANCE) continue
      context.globalAlpha = (1 - distance / CONNECTION_DISTANCE) * 0.16
      context.beginPath()
      context.moveTo(first.x, first.y)
      context.lineTo(second.x, second.y)
      context.stroke()
    }

    if (pointer.active) {
      const pointerDistance = Math.hypot(first.x - pointer.x, first.y - pointer.y)
      if (pointerDistance < CURSOR_RADIUS) {
        context.globalAlpha = (1 - pointerDistance / CURSOR_RADIUS) * 0.11
        context.beginPath()
        context.moveTo(first.x, first.y)
        context.lineTo(pointer.x, pointer.y)
        context.stroke()
      }
    }
  }

  context.fillStyle = particleColor
  context.globalAlpha = 0.42
  for (const particle of particles) {
    context.fillRect(
      Math.round(particle.x - particle.size / 2),
      Math.round(particle.y - particle.size / 2),
      particle.size,
      particle.size,
    )
  }
  context.globalAlpha = 1
}

function animate(timestamp: number) {
  const elapsed = lastFrameTime ? timestamp - lastFrameTime : FRAME_INTERVAL
  if (elapsed >= FRAME_INTERVAL) {
    lastFrameTime = timestamp
    updateParticles(Math.min(elapsed / 1000, 0.05))
    drawNetwork()
  }
  animationFrame = requestAnimationFrame(animate)
}

function stopAnimation(state: "paused" | "reduced") {
  if (animationFrame) cancelAnimationFrame(animationFrame)
  animationFrame = 0
  lastFrameTime = 0
  motionState.value = state
  context?.clearRect(0, 0, viewportWidth, viewportHeight)
}

function startAnimation() {
  if (animationFrame || document.hidden || motionQuery?.matches) return
  motionState.value = "active"
  animationFrame = requestAnimationFrame(animate)
}

function handleMotionPreference() {
  if (motionQuery?.matches) stopAnimation("reduced")
  else startAnimation()
}

function handleVisibilityChange() {
  if (document.hidden) stopAnimation("paused")
  else handleMotionPreference()
}

function handlePointerMove(event: PointerEvent) {
  pointer.x = event.clientX
  pointer.y = event.clientY
  pointer.active = event.pointerType !== "touch"
}

function handlePointerOut(event: PointerEvent) {
  if (!event.relatedTarget) pointer.active = false
}

function clearPointer() {
  pointer.active = false
}

onMounted(() => {
  motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)")
  motionQuery.addEventListener("change", handleMotionPreference)
  window.addEventListener("resize", resizeCanvas)
  window.addEventListener("pointermove", handlePointerMove, { passive: true })
  window.addEventListener("pointerout", handlePointerOut)
  window.addEventListener("blur", clearPointer)
  document.addEventListener("visibilitychange", handleVisibilityChange)
  resizeCanvas()
  handleMotionPreference()
})

onBeforeUnmount(() => {
  stopAnimation("paused")
  motionQuery?.removeEventListener("change", handleMotionPreference)
  window.removeEventListener("resize", resizeCanvas)
  window.removeEventListener("pointermove", handlePointerMove)
  window.removeEventListener("pointerout", handlePointerOut)
  window.removeEventListener("blur", clearPointer)
  document.removeEventListener("visibilitychange", handleVisibilityChange)
})
</script>

<template>
  <canvas
    ref="canvas"
    class="particle-network-background"
    aria-hidden="true"
    data-testid="particle-network-background"
    :data-motion-state="motionState"
  ></canvas>
</template>

<style scoped>
.particle-network-background {
  position: fixed;
  z-index: 0;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}

@media (prefers-reduced-motion: reduce) {
  .particle-network-background {
    display: none;
  }
}
</style>
