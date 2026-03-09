<script setup>
import { defineProps, computed } from 'vue';

const props = defineProps({
  score: {
    type: Number,
    required: true,
  },
  label: {
    type: String,
    required: true,
  },
  size: {
    type: Number,
    default: 64,
  },
  strokeWidth: {
    type: Number,
    default: 5,
  },
  colorClass: {
    type: String,
    default: 'text-indigo-600',
  },
  className: {
    type: String,
    default: '',
  },
});

const radius = computed(() => (props.size - props.strokeWidth) / 2);
const circumference = computed(() => 2 * Math.PI * radius.value);
const offset = computed(() => circumference.value - (props.score / 10) * circumference.value);
</script>

<template>
  <div class="flex flex-col items-center justify-center" :class="className">
    <div class="relative flex items-center justify-center" :style="{ width: `${size}px`, height: `${size}px` }">
      <!-- Background Circle -->
      <svg class="transform -rotate-90 w-full h-full">
        <circle
          class="text-slate-100"
          stroke="currentColor"
          fill="transparent"
          :stroke-width="strokeWidth"
          :r="radius"
          :cx="size / 2"
          :cy="size / 2"
        />
        <!-- Progress Circle -->
        <circle
          :class="colorClass"
          stroke="currentColor"
          fill="transparent"
          :stroke-width="strokeWidth"
          stroke-linecap="round"
          :stroke-dasharray="circumference"
          :stroke-dashoffset="offset"
          :r="radius"
          :cx="size / 2"
          :cy="size / 2"
          style="transition: stroke-dashoffset 1s ease-out;"
        />
      </svg>
      <div class="absolute inset-0 flex items-center justify-center">
        <span class="text-lg font-bold text-slate-700">{{ score }}</span>
      </div>
    </div>
    <span class="text-xs font-medium text-slate-500 mt-2">{{ label }}</span>
  </div>
</template>
