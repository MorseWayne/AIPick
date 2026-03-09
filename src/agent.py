import os
import json
import asyncio
import logging
from typing import List, Dict, Any
from openai import AsyncOpenAI
from src.models import SearchIntent, NeedsAnalysis, RecommendationReport, ProductEvaluation, WebSearchReport, CandidateProduct
from src.xhs_mcp_client import XhsMcpClient

logger = logging.getLogger(__name__)

class RecommendationAgent:
    def __init__(self, mcp_url: str = "http://10.10.131.118:18060/mcp"):
        # 读取模型相关的配置
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        model = os.getenv("LLM_MODEL", "gpt-4o")
        
        self.llm = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.mcp_client = XhsMcpClient(mcp_url)

    # ========================= 需求深度分析 =========================
    MAX_CLARIFICATION_ROUNDS = 5  # 最多追问轮数

    async def analyze_needs(self, history: List[Dict[str, str]]) -> NeedsAnalysis:
        """
        LLM 驱动的深度需求分析。
        从对话上下文中提取结构化需求信息，并智能判断是否需要继续追问。
        """
        sys_prompt = """你是一个经验丰富的购物顾问，擅长通过自然的对话深度挖掘用户的真实购买需求。
你的任务是分析当前对话上下文，提取用户的购买意图，并判断是否需要进一步追问。

### 你需要尝试了解以下维度的信息（不需要全部收集齐，但越丰富推荐越精准）：

1. **商品类目** - 用户想买什么类型的商品
2. **预算范围** - 大致的价格区间
3. **核心需求** - 最重要的功能/特性要求（尽量挖掘 2~4 个具体需求）
4. **用户画像** - 年龄段、性别、个人特征（如肤质、体型、职业等），这些信息有助于精准匹配
5. **使用场景** - 在什么场景下使用（日常/送礼/特定活动）
6. **品牌偏好** - 是否有品牌倾向或排斥
7. **过往痛点** - 之前用过什么同类产品，有什么不满意的地方

### 追问策略（非常重要）：
- **每次只问一个问题**，保持对话轻松自然，不要给用户压迫感
- **问题要有针对性**：根据用户已经透露的信息，推断此刻最有价值的下一个追问方向
  - 例如用户说"买护肤品"，优先问肤质而非品牌偏好
  - 例如用户说"送妈妈"，优先问妈妈的年龄和皮肤状况
- **给出追问理由**：用一句话解释为什么需要这个信息（让用户感到被专业对待），放在 follow_up_reason 中
- **避免重复追问**已经回答过的信息
- **问题风格**：像朋友聊天一样自然亲切，可以适当使用 emoji，避免生硬的表单式提问
- **引导性提问**：给出具体的选项示例帮助用户回答，如"您是油皮、干皮还是混合皮呢？"

### is_sufficient 判断标准：
- 至少明确了【类目】+【预算范围（哪怕是模糊的）】+【2个以上核心需求】
- 如果用户首次输入就包含了丰富的细节描述，可以在 1-2 轮追问后就标为 true
- 如果关键信息（如类目）完全缺失，必须追问
- 追问总轮数不宜过多，在 2~4 轮追问内尽量收集足够信息
- 当信息已经比较丰富时，即使个别维度缺失也可以标为 true 并在 keywords 中合理补充

### keywords 生成：
- 即使信息还不完整也尝试生成搜索关键词
- 关键词应该简洁精准，反映用户的核心搜索意图"""

        messages = [{"role": "system", "content": sys_prompt}]
        messages.extend(history)

        response = await self.llm.beta.chat.completions.parse(
            model=self.model,
            messages=messages,
            response_format=NeedsAnalysis
        )
        analysis = response.choices[0].message.parsed
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
        )

    # ========================= Phase 1: LLM 联网搜索 =========================
    async def web_search_candidates(self, search_intent: SearchIntent) -> WebSearchReport:
        """
        Phase 1: 通过 LLM 联网搜索能力，从全网搜索符合用户需求的候选商品。
        结合销量排行榜、产品深度评测等信息，筛选出最佳候选。
        使用 DashScope OpenAI 兼容接口的 enable_search 参数启用联网搜索。
        """
        logger.info(f"[Phase1] Web search for candidates: {search_intent.keywords}")
        
        # 构建丰富的用户画像上下文
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
        user_context = '\n'.join(user_context_parts)

        sys_prompt = f"""你是一个专业的商品调研分析师，擅长从全网信息中筛选出最适合用户需求的商品。

用户需求深度画像：
{user_context}

请你联网搜索当前市场上符合以上需求的商品，重点参考以下维度的信息：
1. **销量排行榜**：各大电商平台（京东、天猫、拼多多等）的销量排名
2. **专业评测**：科技媒体的深度评测结论（如什么值得买、中关村在线、ZEALER等）
3. **性价比分析**：同价位段竞品对比
4. **用户口碑概况**：主流电商平台的好评率和普遍反馈

请特别注意用户的画像特征和使用场景，筛选出真正适合该用户的 3~5 款商品（而非泛泛的热销品）。
{('注意：用户有以下过往痛点，推荐时请务必避开类似问题的产品：' + ', '.join(search_intent.pain_points)) if search_intent.pain_points else ''}

⚠️ 关于 search_keyword_for_xhs 字段的特别要求：
该关键词将用于小红书站内搜索，请务必遵循以下规则：
- 关键词必须**简短精准**，总共 2~4 个词，不要超过 10 个汉字
- 格式参考："品牌名 产品型号/系列名"，例如 "珀莱雅红宝石套装"、"ThinkPad X1 Carbon"
- 不要加 "测评"、"推荐"、"实测" 等后缀，也不要加用户人群词（如 "中年"、"学生"）
- 不要放价格信息
- 目标是让小红书搜索能精准命中该商品的真实用户笔记"""

        user_prompt = f"请联网搜索关键词「{search_intent.keywords}」相关的商品信息，结合各大榜单和专业评测，输出候选商品报告。"

        response = await self.llm.beta.chat.completions.parse(
            model=self.model,
            messages=[
                {"role": "system", "content": sys_prompt.strip()},
                {"role": "user", "content": user_prompt}
            ],
            response_format=WebSearchReport,
            extra_body={"enable_search": True}
        )
        
        report = response.choices[0].message.parsed
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
        优先取标题包含品牌/产品名的笔记，其次按原始顺序取。
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
            
            scored_feeds.append((score, feed))
        
        # 按相关性分数降序排序，取前 max_count 条
        scored_feeds.sort(key=lambda x: x[0], reverse=True)
        result = [f for _, f in scored_feeds[:max_count]]
        
        relevant_count = sum(1 for s, _ in scored_feeds if s > 0)
        logger.info(f"[Phase2] Feed filter: {len(feeds)} total, {relevant_count} relevant, taking top {len(result)}")
        return result

    async def _search_xhs_with_fallback(self, candidate: CandidateProduct) -> tuple[list, str]:
        """
        带降级重试的小红书搜索，返回 (feed_list, 实际使用的关键词)。
        从精准关键词开始，逐级降级直到搜到结果。
        """
        fallback_keywords = self._generate_fallback_keywords(candidate)
        
        for level, keyword in enumerate(fallback_keywords):
            logger.info(f"[Phase2] XHS search attempt level={level}, keyword='{keyword}'")
            
            try:
                search_res = await self.mcp_client.search_feeds(keywords=keyword)
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

    async def xhs_verify_candidate(self, candidate: CandidateProduct, search_intent: SearchIntent) -> str:
        """
        Phase 2: 对单个候选商品，在小红书上进行二次搜索，抓取真实用户反馈。
        支持关键词降级重试：如果精准关键词搜不到，会自动简化关键词重新搜索。
        返回该商品在小红书上的拼接文本（笔记正文 + 评论）。
        """
        logger.info(f"[Phase2] XHS search for candidate: {candidate.product_name}")
        
        # 带降级重试的搜索
        feed_list, used_keyword = await self._search_xhs_with_fallback(candidate)
        
        if used_keyword != candidate.search_keyword_for_xhs:
            print(f"      ↳ 原始关键词无结果，降级为 '{used_keyword}'")
        
        if not feed_list:
            return ""

        raw_details = []
        for feed in feed_list:
            feed_id, xsec_token = self._extract_feed_id_and_token(feed)
            if not feed_id or not xsec_token:
                continue
            
            detail_text = await self.mcp_client.get_feed_detail(feed_id, xsec_token, max_comments=30)
            raw_details.append(detail_text)

        combined_text = "\n-----\n".join(raw_details)
        return f"【{candidate.product_name}】的小红书真实用户反馈:\n{combined_text}" if combined_text.strip() else ""

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
        
        # Part B: 小红书真实反馈
        context_parts.append("\n\n===== 小红书真实用户反馈 =====")
        for product_name, feedback in xhs_feedbacks.items():
            if feedback.strip():
                context_parts.append(f"\n{feedback}")
            else:
                context_parts.append(f"\n【{product_name}】: 小红书上未搜索到足够的相关笔记。")
        
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

        sys_prompt = f"""你是一个精通全网商品测评的数据分析师，以客观、专业著称。

用户深度画像：
{user_summary}

下面是两部分数据：
1. 【全网搜索结果】：来自各大电商平台、专业评测网站的综合信息（销量排行、专业评测、性价比对比）。
2. 【小红书真实反馈】：来自小红书的真实用户笔记和评论（更贴近真实使用体验）。

请综合两部分信息进行分析，严格遵循以下要求：

### 分析原则
- 全网信息作为"硬实力基准"（参数配置、价格竞争力、专业评测成绩）
- 小红书反馈作为"软实力验证"（真实使用体验、用户满意度、隐藏槽点）
- **忽略水军特征明显的评论**：内容过短（如仅"好用""推荐"）、高度雷同、广告痕迹重的评论
- **侧重有具体描述的长评论**：包含使用时长、肤质/体验细节、前后对比的评论权重更高

### 输出质量要求
- pros 和 cons 中应引用小红书真实用户的具体反馈（如："多位用户反映用了两周后斑淡了"），而不是泛泛的描述
- 如果某商品在小红书上缺少真实反馈数据，请在 summary 中明确标注"该商品在小红书上的真实用户反馈较少，推荐置信度有限"
- positive_rate 和 negative_rate 应基于实际收集到的评论样本估算，不要凭空编造
- cost_performance 应结合实际价格与同类竞品做横向对比
- recommendation_index 应综合考虑全网评测 (40%) + 小红书好评度 (30%) + 性价比 (20%) + 需求匹配度 (10%)

请输出符合 RecommendationReport 格式的综合推荐报告。"""

        response = await self.llm.beta.chat.completions.parse(
            model=self.model,
            messages=[
                {"role": "system", "content": sys_prompt.strip()},
                {"role": "user", "content": all_context}
            ],
            response_format=RecommendationReport
        )
        report = response.choices[0].message.parsed
        logger.info(f"[Phase3] Generated recommendation report containing {len(report.recommendations)} products.")
        return report

    async def run_pipeline(self, initial_query: str):
        logger.info(f"Starting new interaction pipeline with query: {initial_query}")
        history = [{"role": "user", "content": initial_query}]

        # ==================== 阶段 0: LLM 驱动的深度需求分析 ====================
        print("\n\U0001f50d 正在深度分析您的需求...")
        
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
                
                reason = f"（{analysis.follow_up_reason}）" if analysis.follow_up_reason else ""
                print(f"\n\U0001f64b 顾问追问 {reason}：")
                print(f"   {question}")
                history.append({"role": "assistant", "content": question})
                
                user_reply = input("\n> 回答 (输入 'q' 取消, 's' 跳过此问题): ")
                if user_reply.strip().lower() in ['q', 'quit', 'exit']:
                    print("已取消本次推荐。\n")
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

        # 展示收集到的完整需求档案
        print("\n" + "=" * 50)
        print("\U0001f4cb 需求分析完成，以下是您的购买需求档案：")
        print("=" * 50)
        print(f"   \U0001f3f7\ufe0f  目标商品：{intent.category or '未指定'}")
        print(f"   \U0001f4b0 预算范围：{intent.budget or '未指定'}")
        print(f"   \U0001f3af 核心需求：{', '.join(intent.core_needs) if intent.core_needs else '未指定'}")
        if intent.user_profile:
            print(f"   \U0001f464 用户画像：{intent.user_profile}")
        if intent.usage_scenario:
            print(f"   \U0001f4cd 使用场景：{intent.usage_scenario}")
        if intent.brand_preference:
            print(f"   \U0001f48e 品牌偏好：{intent.brand_preference}")
        if intent.pain_points:
            print(f"   \u26a0\ufe0f  过往痛点：{', '.join(intent.pain_points)}")
        print(f"   \U0001f511 搜索关键词：{intent.keywords}")
        print("=" * 50)

        # ==================== Phase 1: LLM 联网全网搜索 ====================
        print("\n\U0001f310 Phase 1: 启用 LLM 联网搜索，从全网检索符合条件的优质商品...")
        print("   \u2022 参考电商销量排行榜、专业评测、性价比对比...")
        
        web_report = await self.web_search_candidates(intent)
        
        print(f"\n\U0001f4ca 全网市场概况: {web_report.market_summary[:100]}...")
        print(f"   共筛选出 {len(web_report.candidates)} 款候选商品：")
        for i, c in enumerate(web_report.candidates, 1):
            print(f"   {i}. {c.product_name} ({c.brand}) - 参考价: {c.price_range}")
            print(f"      亮点: {', '.join(c.highlights[:3])}")
        print("-" * 50)
        
        # ==================== Phase 2: 小红书二次搜索验证 ====================
        print("\n\U0001f4f1 Phase 2: 在小红书上对候选商品进行二次搜索，获取真实用户反馈...")
        
        # 并行搜索所有候选商品的小红书反馈
        async def _verify_one(i: int, candidate: CandidateProduct):
            print(f"   [{i}/{len(web_report.candidates)}] 搜索 '{candidate.search_keyword_for_xhs}' 的小红书用户评价...")
            feedback = await self.xhs_verify_candidate(candidate, intent)
            if feedback.strip():
                print(f"      \u2705 [{candidate.product_name}] 已获取相关笔记和评论")
            else:
                print(f"      \u26a0\ufe0f [{candidate.product_name}] 未搜索到足够相关内容")
            return candidate.product_name, feedback
        
        results = await asyncio.gather(
            *[_verify_one(i, c) for i, c in enumerate(web_report.candidates, 1)],
            return_exceptions=True
        )
        
        xhs_feedbacks: Dict[str, str] = {}
        for r in results:
            if isinstance(r, Exception):
                logger.error(f"[Phase2] Parallel verify error: {r}")
                continue
            name, feedback = r
            xhs_feedbacks[name] = feedback
        print("-" * 50)
        
        # ==================== Phase 3: 综合分析打分 ====================
        print("\n\U0001f9e0 Phase 3: 综合全网评测 + 小红书真实反馈，进行多维度深度分析...")
        
        report = await self.comprehensive_analysis(intent, web_report, xhs_feedbacks)
        
        # ==================== 输出最终推荐榜单 ====================
        print("\n" + "=" * 55)
        print("\U0001f3c6          最终商品推荐榜单          \U0001f3c6")
        print("=" * 55)
        if not report.recommendations:
            print("抱歉，我未能找到合适的相关高质量商品。")
            
        for rank, item in enumerate(report.recommendations, 1):
            medal = ["\U0001f947", "\U0001f948", "\U0001f949"][rank - 1] if rank <= 3 else f"#{rank}"
            print(f"\n{medal} {item.product_name}")
            print(f"   \U0001f31f 推荐指数: {item.recommendation_index}/100")
            print(f"   \U0001f44d 好评度: {item.positive_rate}  |  \U0001f44e 差评度: {item.negative_rate}")
            print(f"   \U0001f4b0 性价比: {item.cost_performance}/10")
            print(f"   \u2705 优点: {', '.join(item.pros)}")
            print(f"   \u274c 槽点: {', '.join(item.cons)}")
            print(f"   \U0001f4dd 建议: {item.summary}")
            print("-" * 55)
