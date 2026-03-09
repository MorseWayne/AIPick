<script setup>
import { defineProps, defineEmits, ref, onMounted, nextTick } from 'vue';
import { Send, Bot, Clock, PlusCircle, Search, FileText, Brain, ClipboardList } from 'lucide-vue-next';

const props = defineProps({
  activeSession: Object,
  sessionId: String,
});

const emit = defineEmits([
  'searchComplete',
  'toggleHistory',
  'sessionsChange',
  'resetSession',
  'sendMessage'
]);

const messages = ref([]);
const input = ref('');
const isTyping = ref(false);
const messagesEndRef = ref(null);
const currentStepIndex = ref(0);
const steps = [
  { id: 1, label: '描述需求' },
  { id: 2, label: '明确预算' },
  { id: 3, label: '确认偏好' },
  { id: 4, label: '全网分析' },
];

const WELCOME_MESSAGE = {
  id: 'msg-welcome',
  role: 'bot',
  text: '欢迎使用【AIPick 商品意向分析助手】\n\n您可以输入您的自然语言需求，例如：\n\n"我想买适用中年女性的护肤品，目的是抗衰老，祛斑，体质是油性皮肤"\n\n"我想买台手机，预算五千左右，拍照要好"',
};

const scrollToBottom = () => {
  nextTick(() => {
    messagesEndRef.value?.scrollIntoView({ behavior: 'smooth' });
  });
};

const extractOptionsFromText = (text) => {
  const raw = String(text || '');
  const cueMatch = raw.match(/(?:比如|例如|如)\s*[:：]?\s*([^\n]+)/);
  const segment = cueMatch ? cueMatch[1] : '';
  const splitTarget = segment || raw;
  const parts = splitTarget
    .replace(/还是/g, '、')
    .replace(/或者/g, '、')
    .replace(/或/g, '、')
    .split(/[、，,\/]/)
    .map((item) => item.trim())
    .filter(Boolean);
  const unique = Array.from(new Set(parts));
  return unique.length >= 2 ? unique : [];
};

const normalizeOptions = (options, text) => {
  const list = Array.isArray(options) ? options : [];
  const normalized = list
    .map((item) => {
      if (typeof item === 'string') return { label: item, value: item };
      if (!item || typeof item !== 'object') return null;
      const value = item.value || item.label;
      const label = item.label || item.value;
      if (!value || !label) return null;
      return { label, value };
    })
    .filter(Boolean);
  if (normalized.length) return normalized;
  return extractOptionsFromText(text).map((item) => ({ label: item, value: item }));
};

const statusToneMap = {
  plan: { bg: 'bg-blue-50', text: 'text-blue-600', ring: 'ring-blue-100' },
  search: { bg: 'bg-indigo-50', text: 'text-indigo-600', ring: 'ring-indigo-100' },
  report: { bg: 'bg-emerald-50', text: 'text-emerald-600', ring: 'ring-emerald-100' },
  analyze: { bg: 'bg-violet-50', text: 'text-violet-600', ring: 'ring-violet-100' },
  deep: { bg: 'bg-sky-50', text: 'text-sky-600', ring: 'ring-sky-100' },
  info: { bg: 'bg-slate-100', text: 'text-slate-600', ring: 'ring-slate-200' },
};

const statusIconMap = {
  plan: ClipboardList,
  search: Search,
  report: FileText,
  analyze: Brain,
  deep: Search,
  info: Clock,
};

const stripStatusDecorations = (text) => {
  return String(text || '')
    .replace(/\[Deep Research\]/gi, '')
    .replace(/Deep Research/gi, '')
    .replace(/[🧠🔍📋📝🤔⏳📱]+/g, '')
    .replace(/^[\s•·]+/, '')
    .trim();
};

const buildStatusCard = (text) => {
  const raw = String(text || '');
  const shouldStyle = /Phase\s*\d+|Deep Research|研究|搜索|报告|小红书|计划|步骤|多轮/.test(raw);
  if (!shouldStyle) return null;
  let stage = '';
  let body = raw;
  if (raw.includes(' · ')) {
    const parts = raw.split(' · ');
    stage = (parts.shift() || '').trim();
    body = parts.join(' · ').trim();
  }
  const cleaned = stripStatusDecorations(body);
  if (!cleaned) return null;
  let type = 'info';
  if (/研究计划|规划/.test(cleaned)) type = 'plan';
  else if (/搜索|全网|小红书/.test(cleaned)) type = 'search';
  else if (/报告|生成/.test(cleaned)) type = 'report';
  else if (/深入研究/.test(cleaned)) type = 'deep';
  else if (/研究方向/.test(cleaned)) type = 'analyze';
  let chip = '';
  if (stage && /Phase\s*\d+/i.test(stage)) {
    chip = stage;
  } else if (/Deep Research/i.test(raw)) {
    chip = 'Deep Research';
  } else if (/流程|步骤|多轮/.test(cleaned)) {
    chip = '流程说明';
  }
  return {
    title: cleaned,
    detail: stage && !/Phase\s*\d+/i.test(stage) ? stage : '',
    type,
    chip,
    tone: statusToneMap[type] || statusToneMap.info,
    icon: statusIconMap[type] || Clock,
  };
};

const addMessage = (msg) => {
  const normalized = { ...msg };
  if (normalized.role === 'bot') {
    normalized.options = normalizeOptions(normalized.options, normalized.text);
    normalized.selectedOptions = [];
    normalized.customInput = '';
    normalized.confirmed = false;
  }
  if (normalized.role === 'system') {
    normalized.statusCard = buildStatusCard(normalized.text);
  }
  messages.value.push(normalized);
  scrollToBottom();
};

const setStepIndex = (index) => {
  const next = Math.max(0, Math.min(steps.length - 1, index));
  currentStepIndex.value = next;
};

const syncStepByStatus = (stage) => {
  if (stage === 'Phase 0') {
    setStepIndex(0);
    return;
  }
  if (stage === 'Phase 1' || stage === 'Phase 2' || stage === 'Phase 3') {
    setStepIndex(3);
  }
};

const detectQuestionStep = (text) => {
  const value = (text || '').toLowerCase();
  const isBudget = /预算|价位|价格|价钱|多少钱|范围|档位/.test(value);
  const isPreference = /偏好|喜欢|品牌|颜色|外观|风格|口味|材质|系统|配置|尺寸|重量|便携|款式/.test(value);
  if (isPreference) return 2;
  if (isBudget) return 1;
  return null;
};

const syncStepByQuestion = (questionText) => {
  const target = detectQuestionStep(questionText);
  if (target !== null) {
    setStepIndex(target);
    return;
  }
  if (currentStepIndex.value < 1) {
    setStepIndex(1);
  }
};

const syncStepByIntent = () => {
  setStepIndex(3);
};

const syncStepByCompleted = () => {
  setStepIndex(3);
};

const syncStepByNewQuery = () => {
  setStepIndex(0);
};

const sendOption = (value) => {
  if (!value) return;
  addMessage({ id: Date.now(), role: 'user', text: value });
  emit('sendMessage', value);
};

const isSelected = (msg, option) => {
  return Array.isArray(msg.selectedOptions) && msg.selectedOptions.includes(option.value);
};

const toggleOption = (msg, option) => {
  if (msg.confirmed) return;
  const value = option.value;
  const current = Array.isArray(msg.selectedOptions) ? msg.selectedOptions : [];
  msg.selectedOptions = current.includes(value)
    ? current.filter((item) => item !== value)
    : [...current, value];
};

const updateCustomInput = (msg, value) => {
  msg.customInput = value;
};

const addCustomOption = (msg) => {
  if (msg.confirmed) return;
  const value = String(msg.customInput || '').trim();
  if (!value) return;
  if (!Array.isArray(msg.options)) {
    msg.options = [];
  }
  const exists = msg.options.some((item) => item.value === value || item.label === value);
  if (!exists) {
    msg.options.push({ label: value, value });
  }
  msg.customInput = '';
  const current = Array.isArray(msg.selectedOptions) ? msg.selectedOptions : [];
  msg.selectedOptions = Array.from(new Set([...current, value]));
};

const confirmOptions = (msg) => {
  if (msg.confirmed) return;
  const selected = Array.isArray(msg.selectedOptions) ? msg.selectedOptions.filter(Boolean) : [];
  if (!selected.length) return;
  msg.confirmed = true;
  sendOption(selected.join('、'));
};

const handleSend = () => {
  if (!input.value.trim()) return;
  
  const text = input.value.trim();
  input.value = '';
  
  
  emit('sendMessage', text);
};

defineExpose({
  addMessage,
  setTyping: (val) => isTyping.value = val,
  clearMessages: () => {
    messages.value = [WELCOME_MESSAGE];
    setStepIndex(0);
  },
  syncStepByStatus,
  syncStepByQuestion,
  syncStepByIntent,
  syncStepByCompleted,
  syncStepByNewQuery,
});

onMounted(() => {
  messages.value = [WELCOME_MESSAGE];
});

</script>

<template>
  <aside class="w-full md:w-[400px] bg-white border-r border-slate-200 flex flex-col h-full shadow-xl z-20 relative">
    <!-- Header -->
    <div class="h-16 flex-shrink-0 border-b border-slate-100 flex items-center justify-between px-6 bg-slate-50/50">
      <div class="flex items-center space-x-2 font-bold text-slate-700">
        <div class="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center shadow-md">
          <Bot class="w-5 h-5 text-white" />
        </div>
        <div>
          <h1 class="text-sm font-extrabold text-slate-900 leading-tight">AIPick 意向分析助手 <span class="text-indigo-500">✨</span></h1>
          <p class="text-[10px] text-slate-400 font-medium tracking-wide">ANTI-SHILL ENGINE V2.4</p>
        </div>
      </div>
      <div class="flex items-center space-x-1">
        <button 
          @click="$emit('toggleHistory')"
          class="p-2 hover:bg-slate-100 rounded-full text-slate-400 hover:text-indigo-600 transition-colors"
          title="历史记录"
        >
          <Clock class="w-4 h-4" />
        </button>
        <button 
          @click="$emit('resetSession')"
          class="p-2 hover:bg-slate-100 rounded-full text-slate-400 hover:text-indigo-600 transition-colors"
          title="新会话"
        >
          <PlusCircle class="w-4 h-4" />
        </button>
      </div>
    </div>

    <!-- Step Indicator (Visual Only for now as backend drives state) -->
    <div class="px-6 py-3 bg-slate-50/30 border-b border-slate-100 flex items-center justify-between relative">
       <div v-for="(s, idx) in steps" :key="s.id" class="flex flex-col items-center relative z-10 w-16">
         <div 
           class="w-4 h-4 rounded-full border-2 flex items-center justify-center transition-all duration-300 bg-white"
           :class="idx <= currentStepIndex ? 'bg-indigo-600 border-indigo-600' : 'bg-white border-slate-300'"
         >
           <div v-if="idx === currentStepIndex" class="w-1.5 h-1.5 bg-white rounded-full"></div>
         </div>
         <span 
           class="text-[10px] mt-1 font-medium transition-colors duration-300 whitespace-nowrap"
           :class="idx <= currentStepIndex ? 'text-indigo-600' : 'text-slate-400'"
         >
           {{ s.label }}
         </span>
       </div>
       <!-- Connecting Line -->
       <div class="absolute top-[20px] left-10 right-10 h-0.5 bg-slate-200 z-0">
          <div 
            class="h-full bg-indigo-600 transition-all duration-500" 
            :style="{ width: `${(currentStepIndex / (steps.length - 1)) * 100}%` }"
          ></div>
       </div>
    </div>

    <!-- Chat Area -->
    <div class="flex-1 overflow-y-auto p-4 space-y-6 bg-[#F8FAFC]">
      <div v-for="msg in messages" :key="msg.id" class="flex flex-col space-y-2" :class="msg.role === 'user' ? 'items-end' : 'items-start'">
        
        <!-- Bot Message -->
        <div v-if="msg.role === 'bot'" class="flex items-start max-w-[90%] group">
          <div class="w-8 h-8 rounded-full bg-white border border-slate-200 flex items-center justify-center flex-shrink-0 mr-3 shadow-sm mt-1 text-indigo-600">
             <Bot class="w-4 h-4" />
          </div>
          <div class="bg-white p-4 rounded-2xl rounded-tl-none shadow-[0_2px_8px_rgba(0,0,0,0.04)] border border-slate-100 text-slate-700 text-sm leading-relaxed whitespace-pre-wrap">
            {{ msg.text }}
            
            <div v-if="msg.options?.length" class="mt-3">
              <div class="text-[11px] text-slate-400 font-medium mb-2">点击选择您在意的偏好（可多选）：</div>
              <ul class="space-y-2">
                <li v-for="opt in msg.options" :key="opt.value">
                  <button
                    :disabled="msg.confirmed"
                    @click="toggleOption(msg, opt)"
                    class="w-full px-3 py-2.5 rounded-xl border text-xs font-medium transition-colors flex items-center gap-3 text-left"
                    :class="isSelected(msg, opt) ? 'bg-indigo-50 border-indigo-300 text-indigo-600' : 'bg-white border-slate-200 text-slate-600 hover:bg-indigo-50 hover:text-indigo-600 hover:border-indigo-200'"
                  >
                    <span class="w-4 h-4 rounded-full border flex items-center justify-center flex-shrink-0" :class="isSelected(msg, opt) ? 'border-indigo-400' : 'border-slate-300'">
                      <span class="w-2 h-2 rounded-full bg-indigo-500" :class="isSelected(msg, opt) ? 'opacity-100' : 'opacity-0'"></span>
                    </span>
                    <span class="flex-1 text-left">{{ opt.label }}</span>
                  </button>
                </li>
              </ul>
              <div class="mt-3 flex items-center gap-2">
                <input
                  :value="msg.customInput"
                  @input="updateCustomInput(msg, $event.target.value)"
                  :disabled="msg.confirmed"
                  type="text"
                  placeholder="输入自定义偏好..."
                  class="flex-1 bg-slate-50 border border-slate-200 text-slate-700 text-xs rounded-full px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-indigo-500/10 focus:border-indigo-500"
                />
                <button
                  @click="addCustomOption(msg)"
                  :disabled="msg.confirmed || !String(msg.customInput || '').trim()"
                  class="w-10 h-10 rounded-full border border-slate-200 text-slate-500 hover:text-indigo-600 hover:border-indigo-200 hover:bg-indigo-50 transition-colors flex items-center justify-center"
                >
                  +
                </button>
              </div>
              <button
                @click="confirmOptions(msg)"
                :disabled="msg.confirmed || !msg.selectedOptions?.length"
                class="mt-3 w-full py-2.5 rounded-xl text-xs font-semibold transition-colors"
                :class="msg.confirmed || !msg.selectedOptions?.length ? 'bg-slate-100 text-slate-400 border border-slate-200' : 'bg-indigo-600 text-white hover:bg-indigo-500'"
              >
                {{ msg.selectedOptions?.length ? '确认选择' : '请至少选择一项偏好' }}
              </button>
            </div>
          </div>
        </div>

        <!-- User Message -->
        <div v-else-if="msg.role === 'user'" class="flex items-start justify-end max-w-[90%]">
          <div class="bg-indigo-600 text-white p-3 rounded-2xl rounded-tr-none shadow-md text-sm">
            {{ msg.text }}
          </div>
        </div>
        
        <!-- System/Status Message -->
        <div v-else-if="msg.role === 'system'" class="w-full flex justify-center my-2">
          <div v-if="msg.statusCard" class="w-full max-w-[90%] bg-white border border-slate-200 rounded-2xl px-4 py-3 shadow-sm">
            <div class="flex items-start gap-3">
              <div class="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0 ring-1" :class="[msg.statusCard.tone.bg, msg.statusCard.tone.text, msg.statusCard.tone.ring]">
                <component :is="msg.statusCard.icon" class="w-4 h-4" />
              </div>
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-2">
                  <span v-if="msg.statusCard.chip" class="text-[10px] font-semibold px-2 py-0.5 rounded-full border border-slate-200 bg-slate-50 text-slate-600">
                    {{ msg.statusCard.chip }}
                  </span>
                  <span class="text-xs font-semibold text-slate-700">{{ msg.statusCard.title }}</span>
                </div>
                <p v-if="msg.statusCard.detail" class="text-[11px] text-slate-500 mt-1 leading-relaxed">{{ msg.statusCard.detail }}</p>
              </div>
            </div>
          </div>
          <span v-else class="bg-slate-100 text-slate-500 text-[10px] px-3 py-1 rounded-full border border-slate-200">
            {{ msg.text }}
          </span>
        </div>

      </div>

      <!-- Typing Indicator -->
      <div v-if="isTyping" class="flex items-start max-w-[90%]">
        <div class="bg-indigo-50 px-4 py-3 rounded-full border border-indigo-100 flex items-center space-x-2 shadow-sm">
          <div class="w-6 h-6 rounded-md bg-white flex items-center justify-center flex-shrink-0 shadow-sm border border-indigo-100">
             <Bot class="w-4 h-4 text-indigo-600" />
          </div>
          <span class="text-indigo-600 text-sm font-medium animate-pulse">顾问分析需求中...</span>
        </div>
      </div>
      
      <div ref="messagesEndRef"></div>
    </div>

    <!-- Input Area -->
    <div class="p-4 bg-white border-t border-slate-100">
      <div class="relative flex items-center group">
        <input 
          v-model="input"
          @keydown.enter="handleSend"
          type="text" 
          placeholder="输入您的购物需求..." 
          class="w-full bg-slate-50 border border-slate-200 text-slate-800 text-sm rounded-2xl pl-4 pr-12 py-3.5 focus:outline-none focus:ring-2 focus:ring-indigo-500/10 focus:border-indigo-500 transition-all shadow-inner placeholder:text-slate-400"
        />
        <button 
          @click="handleSend"
          :disabled="!input.trim()"
          class="absolute right-2 p-2 text-indigo-600 hover:bg-indigo-50 rounded-xl disabled:opacity-30 disabled:hover:bg-transparent transition-all"
        >
          <Send class="w-5 h-5" />
        </button>
      </div>
      
      <!-- Quick Tags (Visual Mockup for now) -->
      <div class="mt-3 flex flex-wrap gap-2 justify-center">
         <button @click="input='我想买台手机'; handleSend()" class="text-[10px] bg-slate-100 hover:bg-indigo-50 hover:text-indigo-600 text-slate-500 px-3 py-1.5 rounded-full transition-colors">
           我想买台手机
         </button>
         <button @click="input='两三千入门级微单'; handleSend()" class="text-[10px] bg-slate-100 hover:bg-indigo-50 hover:text-indigo-600 text-slate-500 px-3 py-1.5 rounded-full transition-colors">
           两三千入门级微单
         </button>
         <button @click="input='学生党高性价比笔记本'; handleSend()" class="text-[10px] bg-slate-100 hover:bg-indigo-50 hover:text-indigo-600 text-slate-500 px-3 py-1.5 rounded-full transition-colors">
           学生党高性价比笔记本
         </button>
      </div>
    </div>
  </aside>
</template>
