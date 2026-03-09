import os
import json
import asyncio
import logging
from typing import List, Dict, Any, Optional, Protocol
from openai import AsyncOpenAI
from src.models import SearchIntent, NeedsAnalysis, RecommendationReport, ProductEvaluation, WebSearchReport, CandidateProduct
from src.xhs_mcp_client import XhsMcpClient
from src.prompts import NEEDS_ANALYSIS_PROMPT, build_web_search_prompt, build_comprehensive_analysis_prompt
from src.deep_research_client import DeepResearchClient

logger = logging.getLogger(__name__)

class AgentCallback(Protocol):
    """定义 UI 与 Agent 交流的抽象回调接口"""
    def on_status_update(self, stage: str, message: str) -> None: ...
    def on_info(self, message: str) -> None: ...
    def on_warning(self, message: str) -> None: ...
    def on_question_asked(self, question: str, reason: str) -> None: ...
    def on_intent_confirmed(self, intent: 'SearchIntent') -> None: ...
    def on_recommendation_completed(self, intent: 'SearchIntent', web_report: 'WebSearchReport', final_report: 'RecommendationReport') -> None: ...
    async def request_user_input(self, prompt: str) -> str: ...

class DefaultCliCallback:
    """默认的命令行终端实现"""
    def on_status_update(self, stage: str, message: str) -> None:
        print(f"\n[{stage}] {message}")
        
    def on_info(self, message: str) -> None:
        print(message)
        
    def on_warning(self, message: str) -> None:
        print(f"⚠️ {message}")
        
    def on_question_asked(self, question: str, reason: str) -> None:
        reason_str = f"（{reason}）" if reason else ""
        print(f"\n🙋 顾问追问 {reason_str}：")
        print(f"   {question}")

    def on_intent_confirmed(self, intent: SearchIntent) -> None:
        """展示收集到的完整需求档案"""
        print("\n" + "=" * 50)
        print("📋 需求分析完成，以下是您的购买需求档案：")
        print("=" * 50)
        print(f"   🏷️  目标商品：{intent.category or '未指定'}")
        print(f"   💰 预算范围：{intent.budget or '未指定'}")
        print(f"   🎯 核心需求：{', '.join(intent.core_needs) if intent.core_needs else '未指定'}")
        if intent.user_profile: print(f"   👤 用户画像：{intent.user_profile}")
        if intent.usage_scenario: print(f"   📍 使用场景：{intent.usage_scenario}")
        if intent.brand_preference: print(f"   💎 品牌偏好：{intent.brand_preference}")
        if intent.pain_points: print(f"   ⚠️  过往痛点：{', '.join(intent.pain_points)}")
        print(f"   🔑 搜索关键词：{intent.keywords}")
        if intent.search_queries:
            print(f"   🔍 补充搜索角度：{' / '.join(intent.search_queries)}")
        print("=" * 50)
        
    def on_recommendation_completed(self, intent: SearchIntent, web_report: WebSearchReport, final_report: RecommendationReport) -> None:
        # 1. 打印意图
        print("\n" + "=" * 50)
        print("📋 需求分析完成，以下是您的购买需求档案：")
        print("=" * 50)
        print(f"   🏷️  目标商品：{intent.category or '未指定'}")
        print(f"   💰 预算范围：{intent.budget or '未指定'}")
        print(f"   🎯 核心需求：{', '.join(intent.core_needs) if intent.core_needs else '未指定'}")
        if intent.user_profile: print(f"   👤 用户画像：{intent.user_profile}")
        if intent.usage_scenario: print(f"   📍 使用场景：{intent.usage_scenario}")
        if intent.brand_preference: print(f"   💎 品牌偏好：{intent.brand_preference}")
        if intent.pain_points: print(f"   ⚠️  过往痛点：{', '.join(intent.pain_points)}")
        print(f"   🔑 搜索关键词：{intent.keywords}")
        print("=" * 50)

        # 2. 打印全网检索概况
        print(f"\n📊 全网市场概况: {web_report.market_summary[:100]}...")
        print(f"   共筛选出 {len(web_report.candidates)} 款候选商品：")
        for i, c in enumerate(web_report.candidates, 1):
            print(f"   {i}. {c.product_name} ({c.brand}) - 参考价: {c.price_range}")
            print(f"      亮点: {', '.join(c.highlights[:3])}")
        print("-" * 50)

        # 3. 打印最终榜单
        print("\n" + "=" * 55)
        print("🏆          最终商品推荐榜单          🏆")
        print("=" * 55)
        if not final_report.recommendations:
            print("抱歉，我未能找到合适的相关高质量商品。")
            
        for rank, item in enumerate(final_report.recommendations, 1):
            medal = ["🥇", "🥈", "🥉"][rank - 1] if rank <= 3 else f"#{rank}"
            confidence_icon = {"高": "🟢", "中": "🟡", "低": "🔴"}.get(item.confidence_level, "⚪")
            print(f"\n{medal} {item.product_name}")
            print(f"   🌟 推荐指数: {item.recommendation_index}/100  {confidence_icon} 置信度: {item.confidence_level}")
            print(f"   👍 好评度: {item.positive_rate}  |  👎 差评度: {item.negative_rate}")
            print(f"   💰 性价比: {item.cost_performance}/10")
            if item.needs_match_detail:
                print(f"   🎯 需求匹配: {item.needs_match_detail}")
            print(f"   ✅ 优点: {', '.join(item.pros)}")
            print(f"   ❌ 槽点: {', '.join(item.cons)}")
            print(f"   📝 建议: {item.summary}")
            print("-" * 55)

    async def request_user_input(self, prompt: str) -> str:
        # 由于内置 input 阻塞事件循环，使用 asyncio.to_thread 包装
        import asyncio
        return await asyncio.to_thread(input, prompt)

class RecommendationAgent:
    def __init__(self, mcp_url: Optional[str] = None):
        # 优先级：传入参数 > 环境变量 > 默认本地地址
        if not mcp_url:
            mcp_url = os.getenv("XHS_MCP_URL", "http://localhost:18060/mcp")
            
        # 读取模型相关的配置
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        model = os.getenv("LLM_MODEL", "gpt-4o")
        
        self.llm = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.mcp_client = XhsMcpClient(mcp_url)
        
        # 检测是否为 DashScope/阿里云百炼渠道
        self._is_dashscope = "dashscope" in base_url or "aliyuncs" in base_url
        
        # 注意：enable_thinking 与 response_format（结构化输出）不兼容
        # Qwen3 开启 thinking 后，content 会为空，所有内容在 reasoning_content 中
        # 因此只在非结构化调用场景使用 thinking
        if self._is_dashscope:
            self._extra_body_thinking = {"enable_thinking": True}  # 用于非结构化调用
            logger.info("DashScope detected, thinking available for non-structured calls")
        else:
            self._extra_body_thinking = {}
        
        # Deep Research 配置（可选）
        self.research_model = os.getenv("RESEARCH_MODEL", "").strip()
        if self.research_model:
            self.deep_research = DeepResearchClient(api_key=api_key, model=self.research_model)
            logger.info(f"Deep Research enabled with model: {self.research_model}")
        else:
            self.deep_research = None
            logger.info("Deep Research not configured, using LLM + enable_search fallback")

    def _safe_parse_response(self, response, model_class):
        """
        安全解析 LLM 结构化输出。
        当启用 enable_thinking 时，Qwen3 的思考内容可能导致 response.parsed 为 None，
        此时从 message.content 中手动提取 JSON 并解析。
        """
        message = response.choices[0].message
        
        # 优先使用 SDK 自动解析的结果
        if message.parsed is not None:
            return message.parsed
        
        # 回退：从 content 中手动提取 JSON
        content = message.content or ""
        logger.warning(f"Structured parse returned None, attempting manual JSON extraction from content (len={len(content)})")
        
        import re
        # 尝试提取 ```json ... ``` 代码块
        json_match = re.search(r'```json\s*\n(.*?)\n\s*```', content, re.DOTALL)
        if json_match:
            json_str = json_match.group(1).strip()
        else:
            # 尝试查找最外层的 { ... } JSON 对象
            json_match = re.search(r'(\{.*\})', content, re.DOTALL)
            if json_match:
                json_str = json_match.group(1).strip()
            else:
                raise ValueError(f"Cannot extract JSON from LLM response content")
        
        return model_class.model_validate_json(json_str)

    # ========================= 需求深度分析 =========================
    MAX_CLARIFICATION_ROUNDS = 5  # 最多追问轮数

    async def analyze_needs(self, history: List[Dict[str, str]]) -> NeedsAnalysis:
        """
        LLM 驱动的深度需求分析。
        从对话上下文中提取结构化需求信息，并智能判断是否需要继续追问。
        """
        sys_prompt = NEEDS_ANALYSIS_PROMPT

        messages = [{"role": "system", "content": sys_prompt}]
        messages.extend(history)

        response = await self.llm.beta.chat.completions.parse(
            model=self.model,
            messages=messages,
            response_format=NeedsAnalysis,
        )
        analysis = self._safe_parse_response(response, NeedsAnalysis)
        logger.info(f"LLM needs analysis: sufficient={analysis.is_sufficient}, "
                    f"category={analysis.category}, budget={analysis.budget}, "
                    f"needs={analysis.core_needs}, profile={analysis.user_profile}")
        return analysis

    def _build_search_intent(self, analysis: NeedsAnalysis) -> SearchIntent:
        """从 NeedsAnalysis 构建 SearchIntent"""
        return SearchIntent(
            keywords=analysis.keywords or "",
            category=analysis.category,
            budget=analysis.budget,
            core_needs=analysis.core_needs,
            user_profile=analysis.user_profile,
            usage_scenario=analysis.usage_scenario,
            brand_preference=analysis.brand_preference,
            pain_points=analysis.pain_points,
            search_queries=getattr(analysis, 'search_queries', []) or [],
        )

    # ========================= Phase 1: LLM 联网搜索 =========================
    def _build_user_context(self, search_intent: SearchIntent) -> str:
        """构建丰富的用户画像上下文字符串"""
        user_context_parts = [
            f"- 商品类目：{search_intent.category}",
            f"- 预算范围：{search_intent.budget}",
            f"- 核心需求：{', '.join(search_intent.core_needs) if search_intent.core_needs else '无特殊偏好'}",
        ]
        if search_intent.user_profile:
            user_context_parts.append(f"- 用户画像：{search_intent.user_profile}")
        if search_intent.usage_scenario:
            user_context_parts.append(f"- 使用场景：{search_intent.usage_scenario}")
        if search_intent.brand_preference:
            user_context_parts.append(f"- 品牌偏好：{search_intent.brand_preference}")
        if search_intent.pain_points:
            user_context_parts.append(f"- 过往痛点：{', '.join(search_intent.pain_points)}")
        return '\n'.join(user_context_parts)

    async def web_search_candidates(self, search_intent: SearchIntent, callback=None) -> WebSearchReport:
        """
        Phase 1: 从全网搜索符合用户需求的候选商品。
        如果配置了 RESEARCH_MODEL（如 qwen-deep-research），则使用深度搜索获取更详尽的报告；
        否则回退到 LLM + enable_search 模式。
        """
        logger.info(f"[Phase1] Web search for candidates: {search_intent.keywords}")
        user_context = self._build_user_context(search_intent)

        if self.deep_research:
            return await self._web_search_deep_research(search_intent, user_context, callback)
        else:
            return await self._web_search_enable_search(search_intent, user_context)

    async def _web_search_deep_research(self, search_intent: SearchIntent, user_context: str, callback=None) -> WebSearchReport:
        """
        使用 Qwen Deep Research 进行深度全网搜索。
        流程：Deep Research 生成 markdown 研究报告 → 普通 LLM 结构化提取 WebSearchReport
        """
        logger.info(f"[Phase1] Using Deep Research model: {self.research_model}")

        # 构建 Deep Research 查询
        pain_point_hint = ""
        if search_intent.pain_points:
            pain_point_hint = f"\n\n特别注意：用户有以下过往痛点，推荐时请务必避开类似问题的产品：{', '.join(search_intent.pain_points)}"

        research_query = f"""请深入研究并对比当前市场上符合以下用户需求的商品，生成一份详细的商品调研报告。

用户需求画像：
{user_context}

搜索关键词：{search_intent.keywords}

请重点调研以下方面：
1. 该品类在各大电商平台（京东、天猫、拼多多）的销量排行榜 TOP 商品
2. 每款候选商品的具体销量数据、用户评价数量、好评率和差评率
3. 专业评测网站（什么值得买、中关村在线等）的评分和评测结论
4. 同价位段竞品的性价比横向对比
5. 各候选商品在用户差评中频繁出现的问题

最终请筛选出 5~8 款最值得推荐的候选商品，对每款商品列出：
- 具体商品名称和品牌
- 参考价格区间
- 核心卖点（不超过5条）
- 销量和市场热度信息
- 适合该商品在小红书上搜索的精准关键词（2~4个词，如"品牌名 产品型号"）{pain_point_hint}"""

        # 状态回调
        def on_research_status(phase: str, status: str):
            if callback:
                phase_names = {
                    "ResearchPlanning": "📋 正在制定研究计划...",
                    "WebResearch": f"🔍 {status}" if status else "🔍 正在深度搜索全网信息...",
                    "answer": "📝 正在生成研究报告...",
                }
                display = phase_names.get(phase, f"⏳ {phase}: {status}")
                callback.on_info(f"   • [Deep Research] {display}")

        # 调用 Deep Research
        raw_report = await self.deep_research.research(
            query=research_query,
            on_status=on_research_status,
        )

        if not raw_report.strip():
            logger.warning("[Phase1] Deep Research returned empty report, falling back to enable_search")
            if callback:
                callback.on_warning("Deep Research 未返回有效报告，正在回退到普通搜索模式...")
            return await self._web_search_enable_search(search_intent, user_context)

        logger.info(f"[Phase1] Deep Research report length: {len(raw_report)} chars")

        # 保存 Deep Research 原始报告到本地文件
        self._save_deep_research_report(raw_report, search_intent)

        # 使用普通 LLM 将 markdown 研究报告结构化为 WebSearchReport
        structurize_prompt = f"""你是一个数据提取专家。下面是一份商品调研报告（markdown 格式），请从中提取结构化信息。

⚠️ 重要：请从报告中提取以下信息，严格按照 WebSearchReport 格式输出 JSON：
- market_summary: 市场概况简述
- candidates: 提取报告中推荐的所有候选商品（每款包含 product_name, brand, price_range, highlights, sales_info, search_keyword_for_xhs）
- raw_search_evidence: 报告中提到的所有具体数据点（销量数据、好评率、评测评分、价格信息等），原样保留

关于 search_keyword_for_xhs 字段（如果报告中未明确提供，请根据商品名称自行生成）：
- 必须简短精准，2~4 个词，不超过 10 个汉字
- 格式："品牌名 产品型号"，如 "珀莱雅红宝石套装"、"ThinkPad X1 Carbon"
- 不加"测评""推荐"等后缀

请以 JSON 格式输出。"""

        # 截断过长的报告以控制 token
        max_report_len = 15000
        report_for_parse = raw_report[:max_report_len] if len(raw_report) > max_report_len else raw_report

        try:
            response = await self.llm.beta.chat.completions.parse(
                model=self.model,
                messages=[
                    {"role": "system", "content": structurize_prompt},
                    {"role": "user", "content": f"以下是调研报告：\n\n{report_for_parse}"}
                ],
                response_format=WebSearchReport,
                temperature=0.1,
                max_tokens=3000,
            )
            report = self._safe_parse_response(response, WebSearchReport)
        except Exception as e:
            logger.error(f"[Phase1] Failed to structurize deep research report: {e}")
            logger.info("[Phase1] Falling back to enable_search mode")
            if callback:
                callback.on_warning(f"深度搜索报告结构化失败: {e}，正在回退到普通搜索模式...")
            return await self._web_search_enable_search(search_intent, user_context)

        # 如果结构化提取没有保留原始证据，则把整个报告作为证据
        if not report.raw_search_evidence:
            report.raw_search_evidence = report_for_parse[:5000]

        logger.info(f"[Phase1] Deep Research found {len(report.candidates)} candidates")
        return report

    async def _web_search_enable_search(self, search_intent: SearchIntent, user_context: str) -> WebSearchReport:
        """
        回退方案：使用普通 LLM + enable_search 参数进行联网搜索。
        """
        logger.info(f"[Phase1] Using LLM + enable_search fallback")

        sys_prompt = build_web_search_prompt(user_context, search_intent.pain_points)
        user_prompt = f"请联网搜索关键词「{search_intent.keywords}」相关的商品信息，结合各大榜单和专业评测，输出候选商品报告。"

        # 兼容不同大模型渠道的搜索参数策略
        if self._is_dashscope:
            api_kwargs = {"extra_body": {"enable_search": True}}
        else:
            api_kwargs = {}  # 其他模型渠道不加非标参数

        try:
            response = await self.llm.beta.chat.completions.parse(
                model=self.model,
                messages=[
                    {"role": "system", "content": sys_prompt.strip()},
                    {"role": "user", "content": user_prompt}
                ],
                response_format=WebSearchReport,
                temperature=0.2,
                max_tokens=2048,
                **api_kwargs
            )
            report = self._safe_parse_response(response, WebSearchReport)
        except Exception as e:
            logger.error(f"[Phase1] WebSearch parsing failed: {e}")
            raise ValueError(f"全网搜索结果反序列化失败: {e}")

        logger.info(f"[Phase1] Web search found {len(report.candidates)} candidates")
        return report

    # ========================= Phase 2: 小红书二次搜索验证 =========================
    def _generate_fallback_keywords(self, candidate: CandidateProduct) -> list[str]:
        """
        为候选商品生成多级降级关键词列表，从精准到宽泛：
        Level 0: Phase1 生成的原始关键词（如 "珀莱雅红宝石套装 中年抗老实测"）
        Level 1: 仅商品名称（如 "珀莱雅红宝石套装"）
        Level 2: 品牌 + 简短品类词（如 "珀莱雅 抗老"）
        Level 3: 仅品牌名（如 "珀莱雅"）
        """
        keywords = []
        
        # Level 0: 原始关键词
        original = candidate.search_keyword_for_xhs.strip()
        if original:
            keywords.append(original)
        
        # Level 1: 仅商品名称（去掉评测/实测等后缀词）
        product_name = candidate.product_name.strip()
        if product_name and product_name != original:
            keywords.append(product_name)
        
        # Level 2: 品牌 + 商品名中的核心型号词（取前几个字避免过长）
        brand = candidate.brand.strip()
        # 从 product_name 中提取去掉品牌后的核心短语
        short_name = product_name.replace(brand, "").strip()
        # 截取前 6 个字符作为核心型号/系列词
        if short_name and len(short_name) > 6:
            short_name = short_name[:6]
        if brand and short_name:
            level2 = f"{brand} {short_name}"
            if level2 not in keywords:
                keywords.append(level2)
        
        # Level 3: 仅品牌名
        if brand and brand not in keywords:
            keywords.append(brand)
        
        return keywords

    def _parse_feeds_response(self, search_res) -> list:
        """
        从 MCP search_feeds 的返回中正确解析 feed 列表。
        兼容两种返回格式:
        - {"feeds": [{...}, ...]}  (dict 包装)
        - [{...}, ...]             (裸 list)
        """
        raw_text = None
        
        # search_res 是 MCP content list
        if isinstance(search_res, list) and len(search_res) > 0 and hasattr(search_res[0], "text"):
            raw_text = search_res[0].text
        elif isinstance(search_res, str):
            raw_text = search_res
        
        if not raw_text:
            return []
        
        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError as e:
            logger.warning(f"[Parse] JSON decode error: {e}")
            return []
        
        # 兼容 dict 和 list 两种结构
        if isinstance(data, dict) and "feeds" in data:
            feeds = data["feeds"]
        elif isinstance(data, list):
            feeds = data
        else:
            logger.warning(f"[Parse] Unexpected data type: {type(data)}, keys={list(data.keys()) if isinstance(data, dict) else 'N/A'}")
            return []
        
        if not isinstance(feeds, list):
            return []
        
        return feeds

    def _extract_feed_id_and_token(self, feed: dict) -> tuple:
        """
        从 feed 字典中提取 feed_id 和 xsec_token，兼容 camelCase 和 snake_case。
        """
        feed_id = feed.get("id") or feed.get("feed_id")
        xsec_token = feed.get("xsecToken") or feed.get("xsec_token")
        return feed_id, xsec_token

    def _filter_relevant_feeds(self, feeds: list, candidate: CandidateProduct, max_count: int = 3) -> list:
        """
        根据 displayTitle 与候选商品的相关性过滤和排序 feeds。
        优先取标题包含品牌/产品名的笔记，并结合互动量质量信号排序。
        """
        brand = candidate.brand.strip().lower()
        product_keywords = [w for w in candidate.product_name.lower().split() if len(w) > 1]
        # 从产品名中提取核心词（去掉品牌名后的部分）
        product_core = candidate.product_name.replace(candidate.brand, "").strip().lower()
        
        scored_feeds = []
        for feed in feeds:
            feed_id, xsec_token = self._extract_feed_id_and_token(feed)
            if not feed_id or not xsec_token:
                continue
            
            title = ""
            note_card = feed.get("noteCard", {})
            if isinstance(note_card, dict):
                title = (note_card.get("displayTitle") or "").lower()
            
            # 计算相关性分数
            score = 0
            if brand and brand in title:
                score += 2
            if product_core and product_core in title:
                score += 3
            for kw in product_keywords:
                if kw in title:
                    score += 1
            
            # ===== 优化项2: 加入互动量质量信号 =====
            interact_info = {}
            if isinstance(note_card, dict):
                interact_info = note_card.get("interactInfo", {})
                if not isinstance(interact_info, dict):
                    interact_info = {}
            
            liked_count = 0
            comment_count = 0
            collected_count = 0
            view_count = 0
            try:
                liked_count = int(interact_info.get("likedCount", 0) or 0)
            except (ValueError, TypeError):
                pass
            try:
                comment_count = int(interact_info.get("commentCount", 0) or 0)
            except (ValueError, TypeError):
                pass
            try:
                collected_count = int(interact_info.get("collectedCount", 0) or 0)
            except (ValueError, TypeError):
                pass
            try:
                view_count = int(interact_info.get("viewCount", 0) or note_card.get("viewCount", 0) or 0)
            except (ValueError, TypeError):
                pass
            
            # 最低门槛过滤：浏览、点赞、收藏、评论都极低的笔记直接跳过
            total_signals = liked_count + collected_count + comment_count
            if total_signals < 5 and view_count < 100:
                logger.debug(f"[Phase2] Skipping low-engagement feed: liked={liked_count}, collected={collected_count}, comments={comment_count}, views={view_count}")
                continue
            
            # 互动量加权：高互动量的笔记更可能包含有价值的内容
            # 评论权重最高（有讨论价值），收藏次之（用户觉得有参考价值），点赞再次
            total_engagement = liked_count + collected_count * 2 + comment_count * 3
            if total_engagement > 1000:
                score += 4
            elif total_engagement > 300:
                score += 3
            elif total_engagement > 100:
                score += 2
            elif total_engagement > 30:
                score += 1
            
            scored_feeds.append((score, feed))
        
        # 按相关性分数降序排序，取前 max_count 条
        scored_feeds.sort(key=lambda x: x[0], reverse=True)
        result = [f for _, f in scored_feeds[:max_count]]
        
        relevant_count = sum(1 for s, _ in scored_feeds if s > 0)
        logger.info(f"[Phase2] Feed filter: {len(feeds)} total, {len(scored_feeds)} passed min threshold, {relevant_count} relevant, taking top {len(result)}")
        return result

    async def _search_xhs_with_fallback(self, candidate: CandidateProduct, session=None) -> tuple[list, str]:
        """
        带降级重试的小红书搜索，返回 (feed_list, 实际使用的关键词)。
        从精准关键词开始，逐级降级直到搜到结果。
        """
        fallback_keywords = self._generate_fallback_keywords(candidate)
        
        for level, keyword in enumerate(fallback_keywords):
            logger.info(f"[Phase2] XHS search attempt level={level}, keyword='{keyword}'")
            
            try:
                search_res = await self.mcp_client.search_feeds(keywords=keyword, session=session)
            except Exception as e:
                logger.error(f"[Phase2] MCP search_feeds error for keyword '{keyword}': {e}")
                continue
            
            all_feeds = self._parse_feeds_response(search_res)
            
            if not all_feeds:
                logger.info(f"[Phase2] No results at level={level}, keyword='{keyword}', trying next...")
                continue
            
            # 按相关性过滤，取 top 3
            feed_list = self._filter_relevant_feeds(all_feeds, candidate, max_count=3)
            
            if feed_list:
                if level > 0:
                    logger.info(f"[Phase2] Fallback succeeded at level={level}, keyword='{keyword}', found {len(feed_list)} feeds")
                return feed_list, keyword
            else:
                logger.info(f"[Phase2] Feeds found but none relevant at level={level}, keyword='{keyword}', trying next...")
        
        return [], fallback_keywords[0] if fallback_keywords else ""

    async def xhs_verify_candidate(self, candidate: CandidateProduct, search_intent: SearchIntent, session=None) -> str:
        """
        Phase 2: 对单个候选商品，在小红书上进行二次搜索，抓取真实用户反馈。
        支持关键词降级重试：如果精准关键词搜不到，会自动简化关键词重新搜索。
        复用传入的 session 避免多次握手。返回该商品在小红书上的拼接文本（笔记正文 + 评论）。
        """
        logger.info(f"[Phase2] XHS search for candidate: {candidate.product_name}")
        
        # 带降级重试的搜索
        feed_list, used_keyword = await self._search_xhs_with_fallback(candidate, session=session)
        
        if used_keyword != candidate.search_keyword_for_xhs:
            print(f"      ↳ 原始关键词无结果，降级为 '{used_keyword}'")
        
        if not feed_list:
            return ""

        raw_details = []
        for feed in feed_list:
            feed_id, xsec_token = self._extract_feed_id_and_token(feed)
            if not feed_id or not xsec_token:
                continue
            
            detail_text = await self.mcp_client.get_feed_detail(feed_id, xsec_token, max_comments=30, session=session)
            raw_details.append(detail_text)

        # ===== 优化项3: 评论预处理，提升信噪比 =====
        combined_text = "\n-----\n".join(raw_details)
        combined_text = self._preprocess_feedback_text(combined_text)
            
        return f"【{candidate.product_name}】的小红书真实用户反馈:\n{combined_text}" if combined_text.strip() else ""

    def _preprocess_feedback_text(self, raw_text: str) -> str:
        """
        对小红书原始反馈文本进行预处理，提升信噪比：
        1. 分离笔记正文和评论
        2. 过滤低质量短评论（< 15 字）
        3. 优先保留高质量长评论
        4. 控制总长度
        """
        MAX_TEXT_LEN_PER_PRODUCT = 6000  # 预处理后可适当增加限额
        
        lines = raw_text.split("\n")
        note_content_lines = []  # 笔记正文部分
        comment_lines = []       # 评论部分
        
        in_comments = False
        current_comment = ""
        
        for line in lines:
            stripped = line.strip()
            # 检测评论区域标识（常见的分隔标记）
            if any(marker in stripped for marker in ["评论", "comment", "回复", "---"]):
                in_comments = True
            
            if in_comments and stripped:
                # 收集单条评论
                if stripped.startswith(("@", "💬", "🗣", "用户")) or len(current_comment) > 200:
                    if current_comment.strip():
                        comment_lines.append(current_comment.strip())
                    current_comment = stripped
                else:
                    current_comment += " " + stripped
            elif stripped:
                note_content_lines.append(stripped)
        
        # 处理最后一条评论
        if current_comment.strip():
            comment_lines.append(current_comment.strip())
        
        # 过滤低质量评论：长度 < 15 字的评论大概率是"好看""求链接"等无意义内容
        quality_comments = [c for c in comment_lines if len(c) >= 15]
        low_quality_count = len(comment_lines) - len(quality_comments)
        if low_quality_count > 0:
            logger.info(f"[Preprocess] Filtered out {low_quality_count} low-quality short comments")
        
        # 按长度降序排序，优先保留信息量大的评论
        quality_comments.sort(key=len, reverse=True)
        
        # 重新组装
        result_parts = []
        
        # 笔记正文部分
        note_text = "\n".join(note_content_lines)
        if note_text.strip():
            result_parts.append("【笔记正文】")
            result_parts.append(note_text)
        
        # 高质量评论部分
        if quality_comments:
            result_parts.append("\n【精选用户评论】")
            result_parts.extend(quality_comments)
        
        result = "\n".join(result_parts)
        
        # 最终长度控制
        if len(result) > MAX_TEXT_LEN_PER_PRODUCT:
            result = result[:MAX_TEXT_LEN_PER_PRODUCT] + "\n...[内容过长已截断]"
        
        return result

    # ========================= Phase 3: 综合分析 =========================
    async def comprehensive_analysis(
        self, 
        search_intent: SearchIntent,
        web_report: WebSearchReport,
        xhs_feedbacks: Dict[str, str]
    ) -> RecommendationReport:
        """
        Phase 3: 综合 Phase1 的全网信息与 Phase2 的小红书真实用户反馈，
        由 LLM 进行最终的多维度打分和排名输出。
        """
        logger.info("[Phase3] Comprehensive analysis started")
        
        # 组装分析上下文
        context_parts = []
        
        # Part A: 全网搜索概况
        context_parts.append("===== 全网搜索市场概况 =====")
        context_parts.append(web_report.market_summary)
        
        for c in web_report.candidates:
            context_parts.append(f"\n--- 候选商品: {c.product_name} ({c.brand}) ---")
            context_parts.append(f"参考价格: {c.price_range}")
            context_parts.append(f"核心卖点: {', '.join(c.highlights)}")
            if c.sales_info:
                context_parts.append(f"市场热度: {c.sales_info}")
        
        # ===== 优化项1: 传递原始搜索证据，避免信息断层 =====
        if web_report.raw_search_evidence:
            context_parts.append("\n===== 全网搜索原始数据证据 =====")
            context_parts.append(web_report.raw_search_evidence)
        
        # Part B: 小红书真实反馈
        context_parts.append("\n\n===== 小红书真实用户反馈 =====")
        for product_name, feedback in xhs_feedbacks.items():
            if feedback.strip():
                context_parts.append(f"\n{feedback}")
            else:
                context_parts.append(f"\n【{product_name}】: 小红书上未搜索到足够的相关笔记。"
                                     f"请基于全网搜索数据进行评估，并将 confidence_level 设为 '低'。")
        
        all_context = "\n".join(context_parts)
        
        # 构建丰富的用户上下文供分析使用
        user_summary_parts = [
            f"核心诉求: {', '.join(search_intent.core_needs) if search_intent.core_needs else '无特殊偏好'}",
            f"预算: {search_intent.budget}",
        ]
        if search_intent.user_profile:
            user_summary_parts.append(f"用户画像: {search_intent.user_profile}")
        if search_intent.usage_scenario:
            user_summary_parts.append(f"使用场景: {search_intent.usage_scenario}")
        if search_intent.brand_preference:
            user_summary_parts.append(f"品牌偏好: {search_intent.brand_preference}")
        if search_intent.pain_points:
            user_summary_parts.append(f"过往痛点: {', '.join(search_intent.pain_points)}")
        user_summary = '\n'.join(user_summary_parts)

        sys_prompt = build_comprehensive_analysis_prompt(user_summary)

        try:
            response = await self.llm.beta.chat.completions.parse(
                model=self.model,
                messages=[
                    {"role": "system", "content": sys_prompt.strip()},
                    {"role": "user", "content": all_context}
                ],
                response_format=RecommendationReport,
                temperature=0.1,
                max_tokens=3000,
            )
            report = self._safe_parse_response(response, RecommendationReport)
        except Exception as e:
            logger.error(f"[Phase3] Final analysis parsing failed: {e}")
            raise ValueError(f"由于大模型返回的反序列化失败，未能生成有效榜单。错误详情: {e}")
        logger.info(f"[Phase3] Generated recommendation report containing {len(report.recommendations)} products.")
        return report

    async def run_pipeline(self, initial_query: str, callback: Optional[AgentCallback] = None):
        """
        开始推荐主流程，支持通过传入不同 callback 适配多端交互
        """
        if callback is None:
            callback = DefaultCliCallback()

        logger.info(f"Starting new interaction pipeline with query: {initial_query}")
        history = [{"role": "user", "content": initial_query}]

        # ==================== 阶段 0: LLM 驱动的深度需求分析 ====================
        callback.on_status_update("Phase 0", "🔍 正在深度分析您的需求...")
        
        intent = None
        for round_num in range(self.MAX_CLARIFICATION_ROUNDS):
            analysis = await self.analyze_needs(history)
            
            if analysis.is_sufficient:
                # 信息足够，构建最终 SearchIntent
                intent = self._build_search_intent(analysis)
                break
            else:
                # 信息不足，LLM 生成智能追问
                question = analysis.follow_up_question
                if not question:
                    # 安全兜底：如果 LLM 没给出问题但标记为不足
                    intent = self._build_search_intent(analysis)
                    break
                
                reason = analysis.follow_up_reason or ""
                callback.on_question_asked(question, reason)
                history.append({"role": "assistant", "content": question})
                
                user_reply = await callback.request_user_input("\n> 回答 (输入 'q' 取消, 's' 跳过此问题): ")
                if user_reply.strip().lower() in ['q', 'quit', 'exit']:
                    callback.on_info("已取消本次推荐。\n")
                    return
                if user_reply.strip().lower() == 's':
                    history.append({"role": "user", "content": "跳过这个问题，我没有特别的偏好"})
                else:
                    history.append({"role": "user", "content": user_reply})
        else:
            # 达到最大追问轮数，用已有信息继续
            logger.info("Max clarification rounds reached, proceeding with available info")
            analysis = await self.analyze_needs(history)
            intent = self._build_search_intent(analysis)

        if intent is None:
            return

        # 补全 keywords（兜底）
        if not intent.keywords:
            parts = [intent.budget or "", intent.category or ""]
            if intent.core_needs:
                parts.append(intent.core_needs[0])
            intent.keywords = " ".join(filter(bool, parts))

        # ===== 优化项6: 通过 callback 展示需求档案，而非直接 print =====
        callback.on_intent_confirmed(intent)

        # ==================== Phase 1: LLM 联网全网搜索 ====================
        if self.deep_research:
            callback.on_status_update("Phase 1", "🧠 启用 Deep Research 深度搜索，从全网深入调研商品...")
            callback.on_info("   • 自动规划研究步骤、多轮搜索、信息整合...")
        else:
            callback.on_status_update("Phase 1", "🌐 启用 LLM 联网搜索，从全网检索优质商品...")
            callback.on_info("   • 参考电商销量排行榜、专业评测、性价比对比...")
        
        web_report = await self.web_search_candidates(intent, callback=callback)
        
        # ==================== Phase 2: 小红书二次搜索验证 ====================
        callback.on_status_update("Phase 2", "📱 在小红书上对候选商品进行二次搜索，获取真实用户反馈...")
        
        # 并行搜索所有候选商品的小红书反馈
        # 加入并发控制，防止请求过多遭到 API 限流或服务端拥堵
        semaphore = asyncio.Semaphore(2)
        
        async def _verify_one(i: int, candidate: CandidateProduct, session):
            async with semaphore:
                callback.on_info(f"   [{i}/{len(web_report.candidates)}] 搜索 '{candidate.search_keyword_for_xhs}' 的小红书反馈...")
                feedback = await self.xhs_verify_candidate(candidate, intent, session=session)
                if feedback.strip():
                    callback.on_info(f"      ✅ [{candidate.product_name}] 已获取相关笔记和评论")
                else:
                    callback.on_warning(f"     ⚠️ [{candidate.product_name}] 未搜索到足够相关内容")
                return candidate.product_name, feedback
        
        async with self.mcp_client.batch_session() as sess:
            results = await asyncio.gather(
                *[_verify_one(i, c, sess) for i, c in enumerate(web_report.candidates, 1)],
                return_exceptions=True
            )
        
        xhs_feedbacks: Dict[str, str] = {}
        for r in results:
            if isinstance(r, Exception):
                logger.error(f"[Phase2] Parallel verify error: {r}")
                continue
            name, feedback = r
            xhs_feedbacks[name] = feedback
        
        # ==================== Phase 3: 综合分析打分 ====================
        callback.on_status_update("Phase 3", "🧠 综合全网评测 + 小红书真实反馈，进行多维度深度分析...")
        
        report = await self.comprehensive_analysis(intent, web_report, xhs_feedbacks)
        
        # ==================== 保存推荐清单到本地 ====================
        md_path = self._save_recommendation_report(intent, web_report, report)
        if md_path:
            callback.on_info(f"\n📄 推荐清单已保存到: {md_path}")
        
        # ==================== 输出最终推荐榜单 ====================
        callback.on_recommendation_completed(intent, web_report, report)

    def _save_deep_research_report(self, raw_report: str, intent: SearchIntent) -> str:
        """保存 Deep Research 原始报告到本地"""
        from datetime import datetime
        import re
        output_dir = "output"
        os.makedirs(output_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_keywords = re.sub(r'[^\w\-]', '_', intent.keywords)[:20]
        filename = f"deep_research_{safe_keywords}_{timestamp}.md"
        filepath = os.path.join(output_dir, filename)
        
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"# Deep Research 报告: {intent.keywords}\n\n")
                f.write(raw_report)
            return filepath
        except Exception as e:
            logger.error(f"Failed to save deep research report: {e}")
            return ""

    def _save_recommendation_report(self, intent: SearchIntent, web_report: WebSearchReport, final_report: RecommendationReport) -> str:
        """生成并保存最终的 Markdown 推荐清单"""
        from datetime import datetime
        import re
        output_dir = "output"
        os.makedirs(output_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_keywords = re.sub(r'[^\w\-]', '_', intent.keywords)[:20]
        filename = f"recommendation_{safe_keywords}_{timestamp}.md"
        filepath = os.path.join(output_dir, filename)
        
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"# AIPick 商品推荐清单: {intent.keywords}\n\n")
                f.write(f"**生成时间:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                
                f.write("## 🎯 需求档案\n")
                f.write(f"- **目标商品**: {intent.category}\n")
                f.write(f"- **预算范围**: {intent.budget}\n")
                f.write(f"- **核心需求**: {', '.join(intent.core_needs)}\n")
                f.write(f"- **用户画像**: {intent.user_profile}\n")
                if intent.usage_scenario:
                    f.write(f"- **使用场景**: {intent.usage_scenario}\n")
                if intent.pain_points:
                    f.write(f"- **过往痛点**: {', '.join(intent.pain_points)}\n")
                f.write("\n")
                
                f.write("## 📊 市场概况\n")
                f.write(f"{web_report.market_summary}\n\n")
                
                f.write("## 🏆 推荐商品榜单\n\n")
                
                medals = ["🥇", "🥈", "🥉", "🏅", "🏅", "🏅", "🏅", "🏅"]
                
                # 按总分降序排序
                sorted_recs = sorted(final_report.recommendations, key=lambda x: x.final_score, reverse=True)
                
                for i, rec in enumerate(sorted_recs):
                    medal = medals[i] if i < len(medals) else "🏅"
                    f.write(f"### {medal} Top {i+1}: {rec.product_name}\n")
                    f.write(f"- **得分**: {rec.final_score}/100\n")
                    if rec.confidence_level:
                        f.write(f"- **置信度**: {rec.confidence_level} (基于小红书数据量)\n")
                    f.write(f"- **性价比**: {rec.value_for_money_score}/10\n")
                    
                    if rec.needs_match_detail:
                        f.write(f"- **需求匹配度**: {rec.needs_match_detail}\n")
                        
                    f.write(f"\n**✅ 核心优势**\n")
                    for pro in rec.pros:
                        f.write(f"- {pro}\n")
                        
                    f.write(f"\n**❌ 潜在槽点**\n")
                    for con in rec.cons:
                        f.write(f"- {con}\n")
                        
                    f.write(f"\n**💡 购买建议**\n{rec.purchase_advice}\n\n")
                    f.write("---\n\n")
                    
            return filepath
        except Exception as e:
            logger.error(f"Failed to save recommendation report: {e}")
            return ""
