<script setup>
import { defineProps, defineEmits, computed } from 'vue';
import { Trash2, MessageSquare, Plus, Clock, Search } from 'lucide-vue-next';

const props = defineProps({
  isOpen: Boolean,
  sessions: Array,
  activeSessionId: String,
});

const emit = defineEmits(['close', 'loadSession', 'deleteSession', 'newSession']);

const formatDate = (ts) => {
  const date = new Date(ts);
  return `${date.getMonth() + 1}/${date.getDate()} ${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`;
};
</script>

<template>
  <!-- Backdrop -->
  <div 
    v-if="isOpen" 
    class="fixed inset-0 bg-black/20 backdrop-blur-sm z-40 transition-opacity"
    @click="$emit('close')"
  ></div>

  <!-- Panel -->
  <div 
    class="fixed inset-y-0 left-0 w-80 bg-white shadow-2xl z-50 transform transition-transform duration-300 ease-in-out flex flex-col"
    :class="isOpen ? 'translate-x-0' : '-translate-x-full'"
  >
    <div class="p-6 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
      <h2 class="text-lg font-bold text-slate-800 flex items-center">
        <Clock class="w-5 h-5 mr-2 text-indigo-600" />
        历史会话
      </h2>
      <button 
        @click="$emit('newSession'); $emit('close')"
        class="p-2 hover:bg-white rounded-lg text-slate-500 hover:text-indigo-600 transition-all border border-transparent hover:border-slate-200 shadow-sm"
        title="开启新会话"
      >
        <Plus class="w-5 h-5" />
      </button>
    </div>

    <div class="flex-1 overflow-y-auto p-4 space-y-3">
      <div v-if="sessions.length === 0" class="text-center py-12 text-slate-400">
        <MessageSquare class="w-12 h-12 mx-auto mb-3 opacity-20" />
        <p class="text-sm">暂无历史记录</p>
      </div>

      <div 
        v-for="session in sessions" 
        :key="session.id"
        class="group relative rounded-xl border transition-all duration-200 hover:shadow-md cursor-pointer overflow-hidden"
        :class="activeSessionId === session.id 
          ? 'bg-indigo-50 border-indigo-200 ring-1 ring-indigo-200' 
          : 'bg-white border-slate-100 hover:border-indigo-100'"
        @click="$emit('loadSession', session); $emit('close')"
      >
        <div class="p-4">
          <div class="flex justify-between items-start mb-1">
            <h3 class="font-semibold text-slate-800 text-sm line-clamp-1 pr-6">
              {{ session.query || '未命名会话' }}
            </h3>
            <button 
              @click.stop="$emit('deleteSession', session.id)"
              class="absolute top-3 right-3 p-1.5 rounded-md text-slate-400 hover:text-rose-500 hover:bg-rose-50 opacity-0 group-hover:opacity-100 transition-all"
            >
              <Trash2 class="w-4 h-4" />
            </button>
          </div>
          <div class="flex items-center text-xs text-slate-500 mt-2 space-x-2">
            <span class="bg-slate-100 px-1.5 py-0.5 rounded text-[10px] font-medium tracking-wide text-slate-600">
              {{ formatDate(session.timestamp * 1000) }}
            </span>
            <span v-if="session.intent?.product" class="flex items-center">
              <Search class="w-3 h-3 mr-1" /> {{ session.intent.product }}
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
