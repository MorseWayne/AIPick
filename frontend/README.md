# AIPick Web Frontend

基于 **Vue 3 + Vite + TailwindCSS** 构建的 AIPick Web 交互界面，通过 WebSocket 与后端实时通讯，提供流式的分析进度展示与结构化商品推荐榜单。

## 技术栈

- **框架**: Vue 3 (Composition API / `<script setup>`)
- **构建工具**: Vite
- **样式**: TailwindCSS
- **图标库**: `lucide-vue-next`
- **WebSocket 封装**: `@vueuse/core` 的 `useWebSocket`

## 目录结构

```text
frontend/
├── src/
│   ├── App.vue              # 根组件：布局、WebSocket 消息处理、会话管理
│   └── components/
│       ├── Sidebar.vue      # 左侧对话侧栏：消息列表、输入框、步骤指示器
│       ├── ProductCard.vue  # 商品推荐卡片：多维评分、优缺点展示
│       ├── HistoryPanel.vue # 历史会话抽屉：浏览与切换历史对话
│       └── ScoreRing.vue    # 环形评分可视化组件
├── index.html
├── vite.config.js
└── package.json
```

## 核心组件说明

### `App.vue` — 根组件

负责全局状态管理与 WebSocket 通讯。

**核心职责：**
- 建立并维护与后端的 WebSocket 长连接（支持自动重连）
- 根据收到的消息类型分发到 `Sidebar` 组件的对应方法
- 管理商品推荐数据 (`currentProducts`) 与用户意图 (`userIntent`)
- 协调历史会话的加载、切换与删除

**发送消息格式：**
| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | `"query"` \| `"answer"` | 首次提问为 `query`，追问回答为 `answer` |
| `content` | `string` | 用户输入的文本内容 |

---

### `Sidebar.vue` — 对话侧栏

左侧的核心交互区域，包含步骤进度条、消息列表、输入框。

**对外暴露方法（通过 `defineExpose`）：**

| 方法 | 参数 | 说明 |
|------|------|------|
| `addMessage(msg)` | `{ id, role, text, type?, options?, isAnalyzing? }` | 向消息列表追加一条消息 |
| `updateAnalyzing(text, stage)` | `string, string` | 更新/创建「分析进度卡片」，根据 `stage` 更新进度条 |
| `clearAnalyzing()` | — | 移除「分析进度卡片」，重置进度 |
| `setTyping(bool)` | `boolean` | 控制打字动画的显示/隐藏 |
| `clearMessages()` | — | 重置消息列表（保留欢迎消息） |
| `syncStepByStatus(stage)` | `string` | 根据后端 `stage` 更新步骤指示器 |
| `syncStepByQuestion(text)` | `string` | 切换到「追问用户」步骤 |
| `syncStepByIntent()` | — | 切换到「意图确认」步骤 |
| `syncStepByCompleted()` | — | 切换到「分析完成」步骤 |
| `syncStepByNewQuery()` | — | 重置步骤为初始状态 |

**消息类型（`msg.role` / `msg.type`）：**

| role | type / isAnalyzing | 渲染样式 |
|------|--------------------|----------|
| `bot` | `isAnalyzing: true` | 分析进度卡片（旋转 Loader + 进度条） |
| `bot` | `type: 'intent-summary'` | 需求确认卡片（绿色渐变，结构化展示意图） |
| `bot` | _(无特殊字段)_ | 普通 Bot 消息气泡（白底圆角卡片） |
| `user` | — | 用户消息气泡（右对齐，靛蓝背景） |
| `system` | — | 系统提示行（灰色小字，居中对齐） |

**分析进度映射 (`stageProgressMap`)：**

| 后端 `stage` | 进度条百分比 |
|-------------|-------------|
| `Phase 0` | 15% |
| `Phase 1` | 40% |
| `Phase 2` | 65% |
| `Phase 3` | 85% |
| 其他/未知 | 累加 +8%（上限 90%） |

---

### `ProductCard.vue` — 商品推荐卡片

展示单款商品的推荐数据，包括：
- AI 综合评分（环形图，`ScoreRing` 组件）
- 好评率 / 差评率
- 性价比得分
- 核心优点与缺点列表
- AI 总结性购买建议

---

### `HistoryPanel.vue` — 历史会话抽屉

从右侧滑入的历史会话面板，支持：
- 浏览所有历史对话列表
- 点击切换到对应历史会话
- 删除历史记录

---

## WebSocket 消息协议（后端 → 前端）

后端通过 WebSocket 推送 JSON 格式消息，`App.vue` 根据 `type` 字段分派处理：

| `type` | 关键字段 | 前端行为 |
|--------|----------|----------|
| `status` | `stage`, `message` | 更新/创建「分析进度卡片」，同步步骤进度 |
| `question` | `question`, `options?` | 展示追问气泡，进入等待回答状态 |
| `intent` | `data` (含 category/budget/core_needs) | 展示「需求确认卡片」，自动生成搜索词 |
| `completed` | `final_report` | 移除进度卡片，展示完成消息，渲染商品推荐榜单 |
| `error` | `message` | 移除进度卡片，展示错误消息 |
| `pipeline_end` | — | 移除进度卡片，终止等待状态 |
| `info` / `warning` | `message` | 展示系统提示消息 |

**`intent` 消息的 `data` 字段结构（`SearchIntent`）：**
```json
{
  "category": "手机",
  "budget": "5000左右",
  "core_needs": ["拍照要好看", "续航强"]
}
```

**`completed` 消息的 `final_report` 字段结构（`RecommendationReport`）：**
```json
{
  "recommendations": [
    {
      "product_name": "华为 Pura 70 Pro",
      "recommendation_index": 94,
      "pros": ["徕卡联合调色", "人像虚化出色"],
      "cons": ["售价偏高", "发热明显"],
      "cost_performance": 8.5,
      "positive_rate": "88%",
      "negative_rate": "8%",
      "summary": "拍照需求强烈且预算充足的首选"
    }
  ]
}
```

## 开发环境启动

```bash
# 安装依赖
cd frontend
npm install

# 启动开发服务器（需配置代理转发 /ws 和 /api 到后端）
npm run dev
```

Vite 开发服务器默认在 `http://localhost:5173` 运行。确保后端 (`web.py`) 已启动，WebSocket 代理配置参见 `vite.config.js`。

## 生产构建

```bash
npm run build
```

构建产物输出到 `frontend/dist/`，后端 `web.py` 通过 `StaticFiles` 挂载该目录提供服务。
