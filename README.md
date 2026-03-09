# AIPick — 智能购买意向分析与多渠道商品推荐系统

AIPick 是一个基于大语言模型（LLM）和 MCP (Model Context Protocol) 协议驱动的智能商品选购 Agent。系统通过多轮自然语言交互精准捕捉用户的购买意图，从各内容平台抓取真实的图文测评及评论，经过 AI 深度分析（提取优缺点、过滤水军、量化好差评率和性价比），最终输出结构化的多维度商品推荐榜单。

> **📌 MVP 阶段说明**
> 当前版本率先接入 **小红书** 渠道进行内容分析（通过 `xiaohongshu-mcp` 服务对接）。后续规划将逐步扩展至更多内容平台，形成更完整的多渠道数据聚合体系。

## 系统特性 (Features)

1. **自然语言意图提取与多轮交互追问**：利用 LLM 作为实体抽取器结构化提取"商品类目"、"预算"及"核心诉求"。若信息不足，系统将基于固化的状态机机制主动追问用户。
2. **小红书渠道真实数据支撑（MVP）**：通过对接 `xiaohongshu-mcp` HTTP 服务，自动搜索热点笔记、提取测评正文及下方高赞评论数据。
3. **结构化深度评估**：通过 Pydantic 结合大模型的 Structured Outputs 特性，稳定输出结构化的评价报告。
4. **多维度打分看板**：自动统计商品的优缺点、估算好差评比率、计算性价比并提供全局的评分卡片。
5. **实时进度可视化 Web 界面**：提供基于 Vue 3 + WebSocket 的 Web 交互界面，实时展示分析阶段进度条、结构化需求确认卡片及商品推荐榜单。
6. **多渠道扩展预留（规划中）**：架构已为接入更多平台（如抖音、京东等）预留扩展点。

## 目录结构 (Directory Structure)

```text
AIPick/
├── docs/                                  # 系统架构与设计相关文档
│   ├── design.md                          # 核心系统设计思路与流程详细说明
│   └── xhs_mcp.md                         # 小红书 MCP 服务能力说明
├── frontend/                              # Vue 3 Web 前端（对话式交互界面）
│   ├── src/
│   │   ├── App.vue                        # 根组件：布局、WebSocket 消息处理、会话管理
│   │   └── components/
│   │       ├── Sidebar.vue                # 左侧对话侧栏：消息列表、进度卡片、输入框
│   │       ├── ProductCard.vue            # 商品推荐卡片：多维评分与优缺点展示
│   │       ├── HistoryPanel.vue           # 历史会话抽屉
│   │       └── ScoreRing.vue             # 环形评分可视化组件
│   └── README.md                          # 前端开发文档
├── src/                                   # 系统核心源码模块
│   ├── models.py                          # 意图分析与推荐榜单的 Pydantic 数据模型
│   ├── xhs_mcp_client.py                  # 小红书 MCP SSE 客户端的通讯封装类
│   └── agent.py                           # AI 大管家，串联意图提取、工具调用与结果分析
├── web.py                                 # Web 服务入口（FastAPI + WebSocket）
├── main.py                                # 终端交互程序入口（CLI 模式）
├── requirements.txt                       # 运行依赖项
├── .env.example                           # 环境变量参考模板
└── README.md                              # 本说明文档
```

## 运行环境准备 (Setup & Installation)

推荐使用现代的 Python 包和环境管理器工具 **`uv`** 来运行本项目，以实现极速的依赖隔离安装。

### 1. 克隆代码并进入目录

```bash
git clone https://github.com/MorseWayne/AIPick.git
cd AIPick
```

### 2. 配置并启动小红书 MCP 服务（前置依赖）

本项目 MVP 阶段依赖 **`xiaohongshu-mcp`** 提供小红书数据接入能力，请参照以下步骤配置：

1. 访问 [https://github.com/xpzouying/xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp) 查阅完整的安装与部署文档。
2. 按照其文档完成服务启动，并记录好 MCP 服务的访问地址（默认一般为 `http://localhost:PORT/mcp`）。
3. 首次运行需扫码登录小红书账号，待 Cookie 持久化后方可正常调用。

> **提示**：确保 `xiaohongshu-mcp` 服务处于运行状态后，再执行后续步骤。

### 3. 使用 `uv` 构建虚拟环境并安装依赖

```bash
# 使用 uv 创建虚拟环境并安装核心跨平台依赖
uv venv
uv pip install -r requirements.txt
```

### 4. 配置环境变量

在你的项目根目录下复制 `.env.example` 并重命名为 `.env`：

```bash
cp .env.example .env
```

随后编辑 `.env` 文件，填入 LLM API 密钥并将 MCP 服务地址替换为你实际部署的地址：

```ini
# .env 文件示例
OPENAI_API_KEY=sk-xxxxxx...
OPENAI_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o

# 替换为你本地运行的 xiaohongshu-mcp 服务地址
XHS_MCP_URL=http://localhost:18060/mcp
```

## 运行与使用 (Usage)

### 方式一：Web 界面模式（推荐）

启动后端 Web 服务：

```bash
uv run python web.py
```

启动前端开发服务器（另开一个终端）：

```bash
cd frontend
npm install
npm run dev
```

访问 `http://localhost:5173` 即可进入 Web 交互界面。Web 模式支持：
- 📊 **实时分析进度卡片**：每个后端处理阶段（Phase 0~3）自动展示带进度条的分析状态
- ✅ **需求确认卡片**：用户意图明确后，以绿色结构化卡片展示目标商品、预算、核心诉求及生成的搜索词
- 🎯 **结构化商品榜单**：分析完成后渲染多维评分卡片，支持历史会话管理

### 方式二：终端 CLI 模式

在终端中使用 `uv run` 启动入口文件：

```bash
uv run python main.py
```

### 交互示例对话

```text
欢迎使用【AIPick 商品意向分析助手】
您可以输入您的自然语言需求，例如：
   我想买适用用中年女性的护肤品，目的是抗衰老，祛斑，体质是油性皮肤，容易长痘，看看买什么合适

> 请出题 (输入 'q' 退出): 我想买台手机

🤖 顾问分析需求中...

🙋 顾问追问: 了解您想看 [手机]！请问您的大致购买预算是多少呢？（例如：3000以内、5000左右等）

> 回答 (输入 'q' 取消): 五千左右

🤖 顾问分析需求中...

🙋 顾问追问: 关于 [手机]，您有什么比较在意的核心需求或偏好吗？（例如：看重续航、拍照要好、适合送人等）

> 回答 (输入 'q' 取消): 拍照要好看

🤖 顾问分析需求中...

✅ 用户需求已明确：
   [目标商品] 手机
   [预算范围] 5000左右
   [重点侧重] 拍照要好看
   [生成的搜索词] 5000左右 手机 拍照要好看
--------------------------------------------------

================== 最终商品推荐榜单 ==================
📦 商品名称: 华为 Pura 70 Pro
🌟 推荐指数: 94/100
👍 好评度估算: 88%  |  💣 差评度: 8%
💰 性价比得分: 8.5/10
✅ 核心优点: 徕卡联合调色、人像虚化出色、屏幕观感顶级
❌ 不足槽点: 售价偏高、部分用户反映发热明显
📝 选购建议: 拍照需求强烈且预算充足的用户首选，5000左右综合体验极为出色。
--------------------------------------------------
```

## 常见问题与后续扩展

- **xiaohongshu-mcp 未启动**：运行时报连接失败时，首先确认 `xiaohongshu-mcp` 服务处于运行状态，并核对 `.env` 中的 `XHS_MCP_URL` 地址是否正确。访问 [https://github.com/xpzouying/xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp) 了解服务部署详情。
- **MCP 解析结构变动**：由于小红书组件和 MCP 服务器返回值可能随版本调整，如遇 JSON 解析失败，请前往 `src/agent.py` 和 `src/xhs_mcp_client.py` 修正反序列化逻辑。
- **登录鉴权重定向**：本项目暂未集成自动拉取二维码的能力，请确保 `xiaohongshu-mcp` 服务节点的 Cookie 保持活跃有效。
- **Token 限流策略**：大范围抓取评论（如单次 100 条长评）会急剧增大 LLM 上下文窗口，推荐使用大视窗模型（如 GPT-4o、Claude 3.5 Sonnet、智谱 GLM-4 Long 等）。
- **多渠道扩展（规划中）**：当前 MVP 仅接入小红书渠道。后续可按照 `src/xhs_mcp_client.py` 的结构封装其他平台（如抖音、京东）的 MCP 客户端，在 `agent.py` 中统一聚合多来源数据。
