<script setup>
import { defineProps } from 'vue';
import { ShieldAlert, CheckCircle2, TrendingUp, Filter, ThumbsUp, ThumbsDown, MessageSquare, ChevronRight, BarChart3 } from 'lucide-vue-next';
import ScoreRing from './ScoreRing.vue';

const props = defineProps({
  product: {
    type: Object,
    required: true,
  },
  rank: {
    type: Number,
    required: true,
  },
});

const emit = defineEmits(['viewDetails']);
</script>

<template>
  <div 
    class="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden mb-6 flex flex-col md:flex-row hover:shadow-md transition-shadow relative"
  >
    <!-- Rank Badge -->
    <div class="absolute top-4 left-4 z-10 bg-indigo-600 text-white w-8 h-8 rounded-full flex items-center justify-center font-bold shadow-md ring-4 ring-white">
      {{ rank }}
    </div>

    <!-- Image & Basic Info (Left/Top section) -->
    <div class="w-full md:w-1/3 relative bg-slate-50 border-b md:border-b-0 md:border-r border-slate-100 p-6 flex flex-col items-center justify-center">
      <div class="relative w-48 h-48 rounded-xl overflow-hidden shadow-sm mb-4 bg-white p-2">
        <img 
          :src="product.imageUrl" 
          :alt="product.name" 
          class="w-full h-full object-cover rounded-lg"
        />
      </div>
      <div class="text-center w-full">
        <span class="text-xs font-semibold text-indigo-600 uppercase tracking-wider mb-1 block">
          {{ product.category }}
        </span>
        <h3 class="text-xl font-bold text-slate-800 leading-tight mb-1">{{ product.name }}</h3>
        <p class="text-sm text-slate-500 mb-3">{{ product.brand }}</p>
        <div class="text-2xl font-black text-slate-900">{{ product.price }}</div>
      </div>
    </div>

    <!-- Analysis Section (Right/Bottom section) -->
    <div class="flex-1 p-6 flex flex-col justify-between">
      <div>
        <!-- Header & Badges -->
        <div class="flex flex-wrap items-center gap-2 mb-4">
          <div class="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
            <CheckCircle2 class="w-3.5 h-3.5 mr-1" />
            AI 推荐首选
          </div>
          <div class="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-blue-50 text-blue-700 border border-blue-200" title="我们通过语义分析过滤了异常集中的好评与差评">
            <Filter class="w-3.5 h-3.5 mr-1" />
            已过滤 {{ product.reviewAnalysis.shillFiltered }} 条水军/无效评论
          </div>
          <div class="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-indigo-50 text-indigo-700 border border-indigo-200">
            <MessageSquare class="w-3.5 h-3.5 mr-1" />
            分析 {{ product.reviewAnalysis.totalAnalyzed }}+ 真实图文
          </div>
        </div>

        <p class="text-sm text-slate-600 mb-6 leading-relaxed bg-slate-50 p-4 rounded-xl border border-slate-100">
          <strong class="text-indigo-700 font-semibold mr-2">AI 深度分析:</strong> 
          {{ product.aiSummary }}
        </p>

        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
          <!-- Pros/Cons List -->
          <div class="space-y-4">
            <div>
              <h4 class="flex items-center text-sm font-semibold text-emerald-700 mb-2">
                <ThumbsUp class="w-4 h-4 mr-1.5" /> 核心优点
              </h4>
              <ul class="space-y-1.5">
                <li v-for="(pro, idx) in product.reviewAnalysis.keyPros" :key="idx" class="text-xs text-slate-600 flex items-start">
                  <span class="text-emerald-500 mr-2 mt-0.5">•</span>
                  <span>{{ pro }}</span>
                </li>
              </ul>
            </div>
            <div>
              <h4 class="flex items-center text-sm font-semibold text-rose-700 mb-2">
                <ThumbsDown class="w-4 h-4 mr-1.5" /> 真实痛点
              </h4>
              <ul class="space-y-1.5">
                <li v-for="(con, idx) in product.reviewAnalysis.keyCons" :key="idx" class="text-xs text-slate-600 flex items-start">
                  <span class="text-rose-500 mr-2 mt-0.5">•</span>
                  <span>{{ con }}</span>
                </li>
              </ul>
            </div>
          </div>

          <!-- Metrics -->
          <div class="bg-white rounded-xl border border-slate-100 p-4 shadow-sm flex flex-col justify-center">
            <h4 class="flex items-center text-sm font-semibold text-slate-700 mb-4">
              <BarChart3 class="w-4 h-4 mr-1.5 text-indigo-500" /> 多维量化指标
            </h4>
            <div class="flex items-center justify-between mb-4 px-2">
              <!-- Using plain div or custom component for ScoreRing if not imported -->
              <!-- Reusing ScoreRing component -->
              <div class="flex flex-col items-center">
                 <div class="relative w-14 h-14 flex items-center justify-center rounded-full border-4 border-indigo-100 text-indigo-600 font-bold text-lg">
                   {{ product.score.overall }}
                 </div>
                 <span class="text-xs text-slate-500 mt-2">综合推荐</span>
              </div>
              
              <div class="flex flex-col items-center">
                 <div class="relative w-12 h-12 flex items-center justify-center rounded-full border-4 border-emerald-100 text-emerald-500 font-bold text-base">
                   {{ product.score.valueForMoney }}
                 </div>
                 <span class="text-xs text-slate-500 mt-2">性价比</span>
              </div>

              <div class="flex flex-col items-center">
                 <div class="relative w-12 h-12 flex items-center justify-center rounded-full border-4 border-blue-100 text-blue-500 font-bold text-base">
                   {{ product.score.reliability }}
                 </div>
                 <span class="text-xs text-slate-500 mt-2">可靠性</span>
              </div>
            </div>
            <div class="space-y-3">
              <div class="flex items-center gap-2">
                <span class="text-xs font-medium text-slate-500 w-12">好评率</span>
                <div class="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden flex">
                  <div 
                    class="bg-emerald-500 h-full rounded-l-full transition-all duration-1000" 
                    :style="{ width: `${product.reviewAnalysis.realPositiveRate}%` }"
                  ></div>
                  <div 
                    class="bg-rose-400 h-full rounded-r-full transition-all duration-1000" 
                    :style="{ width: `${product.reviewAnalysis.realNegativeRate}%` }"
                  ></div>
                </div>
                <span class="text-xs font-bold text-slate-700 w-8 text-right">{{ product.reviewAnalysis.realPositiveRate }}%</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Footer Actions -->
      <div class="flex justify-end pt-4 border-t border-slate-100">
        <button 
          @click="$emit('viewDetails')"
          class="flex items-center text-sm font-semibold text-indigo-600 hover:text-indigo-800 transition-colors bg-indigo-50 hover:bg-indigo-100 px-4 py-2 rounded-lg"
        >
          查看来源与详细图文 <ChevronRight class="w-4 h-4 ml-1" />
        </button>
      </div>
    </div>
  </div>
</template>
