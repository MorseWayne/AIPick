import os
import json
import asyncio
from typing import List, Dict, Any
from openai import AsyncOpenAI
from src.models import SearchIntent, RecommendationReport, ProductEvaluation
from src.xhs_mcp_client import XhsMcpClient

class RecommendationAgent:
    def __init__(self, mcp_url: str = "http://10.10.131.118:18060/mcp"):
        # 读取模型相关的配置
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        model = os.getenv("LLM_MODEL", "gpt-4o")
        
        self.llm = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.mcp_client = XhsMcpClient(mcp_url)

    async def evaluate_intent(self, history: List[Dict[str, str]]) -> SearchIntent:
        """持续从当前对话上下文中提取出用户的搜索意图(包含品类、预算、需求)"""
        sys_prompt = "你是一个智能购物顾问的数据提取模型。请根据截止到目前的对话，提取出用户想买的【商品类目】、【预算范围】和【核心需求/偏好】。如果未提及某项，则相关字段置为 null/None或空数组。如果信息已基本完备，可以基于这些信息合成一句用于小红书搜索的【keywords】。"
        
        messages = [{"role": "system", "content": sys_prompt}]
        messages.extend(history)

        response = await self.llm.beta.chat.completions.parse(
            model=self.model,
            messages=messages,
            response_format=SearchIntent
        )
        return response.choices[0].message.parsed

    async def fetch_and_analyze(self, search_intent: SearchIntent) -> RecommendationReport:
        """结合MCP结果与LLM对商品进行多维度分析"""
        print(f"1. 提取到搜索关键词：{search_intent.keywords}")
        print(f"2. 开始从MCP拉取关于 '{search_intent.keywords}' 的小红书前排笔记...")
        
        # 1. 调用 MCP 搜索工具
        # 在实际中这里会返回一个能够被反序列化为 JSON 的字符串或直接是 dict list
        search_res = await self.mcp_client.search_feeds(keywords=search_intent.keywords)
        # 假设我们通过正则或 JSON 提取到 feed_id 和 xsec_token (这里简化逻辑为尝试解析前5条)
        feed_list = []
        try:
            if isinstance(search_res, list) and hasattr(search_res[0], "text"):
                # 如果是 MCP Text Content
                data = json.loads(search_res[0].text)
                feed_list = data[:3] # 取前三条
            elif isinstance(search_res, str):
                data = json.loads(search_res)
                feed_list = data[:3]
        except Exception as e:
            print("搜索结果解析告警, 请按照实际 MCP 返回格式修改:", e)
            feed_list = [] # 模拟用的 fallback 或返回错误

        raw_details = []
        for feed in feed_list:
            feed_id = feed.get("id") or feed.get("feed_id")
            xsec_token = feed.get("xsec_token")
            if not feed_id or not xsec_token:
                continue
                
            print(f"3. 正在拉取笔记详情及评论 (ID: {feed_id}) ...")
            detail_text = await self.mcp_client.get_feed_detail(feed_id, xsec_token, max_comments=30)
            raw_details.append(detail_text)

        # 把数据组装成字符串传给推断模型
        all_context = "\n-----\n".join(raw_details)
        if not all_context.strip():
            print("未能获取到有效的笔记和评论，可能是检索失败或结构改变。")
            return RecommendationReport(recommendations=[])

        print("4. 已抓取评论全文，交由大模型进行情感分析与商品多维度打分汇总...")
        sys_prompt = f"""
        你是一个精通全网商品测评的数据分析师。
        用户核心诉求: {search_intent.core_needs}
        用户预算: {search_intent.budget}
        
        下面是来自小红书的多篇测评笔记的正文以及真实评论数据。请忽略无效水军刷单评论，并根据真实买家的正负面评价，输出符合 Pydantic Model (RecommendationReport) 中规定的对该产品的推荐报告卡片。
        如果涉及多款同类竞品，可输出多个候选对象的卡片。
        """

        response = await self.llm.beta.chat.completions.parse(
            model=self.model,
            messages=[
                {"role": "system", "content": sys_prompt.strip()},
                {"role": "user", "content": all_context}
            ],
            response_format=RecommendationReport
        )
        report = response.choices[0].message.parsed
        return report

    async def run_pipeline(self, initial_query: str):
        history = [{"role": "user", "content": initial_query}]
        
        while True:
            print("\n🤖 顾问分析需求中...")
            # 从上下文中解析已有意图
            intent = await self.evaluate_intent(history)
            
            # 建立固定的询问逻辑
            missing_info_question = None
            if not intent.category:
                missing_info_question = "好的，请问您具体想买什么类目的商品呢？（例如：手机、轻薄本、美容仪、扫地机器人等）"
            elif not intent.budget:
                missing_info_question = f"了解您想看 [{intent.category}]！请问您的大致购买预算是多少呢？（例如：3000以内、5000左右等）"
            elif not intent.core_needs or len(intent.core_needs) == 0:
                missing_info_question = f"关于 [{intent.category}]，您有什么比较在意的核心需求或偏好吗？（例如：看重续航、拍照要好、适合送人等）"
                
            if missing_info_question is None:
                # 所有必要信息都收集齐了
                print("\n✅ 用户需求已明确：")
                print(f"   [目标商品] {intent.category}")
                print(f"   [预算范围] {intent.budget}")
                print(f"   [重点侧重] {', '.join(intent.core_needs)}")
                print(f"   [生成的搜索词] {intent.keywords}")
                print("-" * 50)
                
                # 开始执行后续检索和分析
                if not intent.keywords:
                    intent.keywords = f"{intent.budget} {intent.category} {intent.core_needs[0]}"
                
                report = await self.fetch_and_analyze(intent)
                
                print("\n================== 最终商品推荐榜单 ==================")
                if not report.recommendations:
                    print("抱歉，我未能找到合适的相关高质量商品。")
                    
                for item in report.recommendations:
                    print(f"📦 商品名称: {item.product_name}")
                    print(f"🌟 推荐指数: {item.recommendation_index}/100")
                    print(f"👍 好评度估算: {item.positive_rate}  |  💣 差评度: {item.negative_rate}")
                    print(f"💰 性价比得分: {item.cost_performance}/10")
                    print(f"✅ 核心优点: {', '.join(item.pros)}")
                    print(f"❌ 不足槽点: {', '.join(item.cons)}")
                    print(f"📝 选购建议: {item.summary}")
                    print("-" * 50)
                break
                
            else:
                # 信息不足，发起固化的反问
                print(f"\n🙋 顾问追问: {missing_info_question}")
                history.append({"role": "assistant", "content": missing_info_question})
                
                user_reply = input("\n> 回答 (输入 'q' 取消): ")
                if user_reply.strip().lower() in ['q', 'quit', 'exit']:
                    print("已取消本次推荐。\n")
                    break
                
                history.append({"role": "user", "content": user_reply})
