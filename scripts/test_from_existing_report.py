import asyncio
import os
import logging
import sys
from dotenv import load_dotenv

# 确保能导入 src 模块
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agent import RecommendationAgent, DefaultCliCallback
from src.models import SearchIntent, WebSearchReport

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_from_file(file_path: str):
    load_dotenv()
    agent = RecommendationAgent()
    callback = DefaultCliCallback()

    # 1. 读取现有的 Deep Research 报告
    if not os.path.exists(file_path):
        print(f"错误: 文件 {file_path} 不存在")
        return

    with open(file_path, "r", encoding="utf-8") as f:
        raw_report = f.read()

    print(f"\n--- 📄 已加载报告: {file_path} (长度: {len(raw_report)}) ---")

    # 2. 构造一个模拟的 SearchIntent (用于后续 XHS 搜索和报告生成)
    intent = SearchIntent(
        keywords="中年女性 温和抗老 祛斑 晚间修护 油皮",
        category="护肤品",
        budget="不限",
        core_needs=["温和抗老", "祛斑", "晚间修护", "控油"],
        user_profile="中年女性, 油性皮肤"
    )

    # 3. 结构化报告 (调用 agent 内部的提取逻辑)
    print("\n[Step 1] 正在从 Markdown 报告中提取结构化数据 (LLM Structurize)...")
    structurize_prompt = """你是一个高精度的护肤品数据提取专家。
    请阅读下面的调研报告，并从中提取出【精选候选商品深度评测】章节中提到的所有具体商品。
    
    ⚠️ 重要规范：
    1. 严格按照 WebSearchReport 格式输出 JSON。
    2. candidates 列表不能为空，必须包含报告中详细评测的 5 款商品。
    3. search_keyword_for_xhs 必须简洁（品牌+型号），例如 "珀莱雅红宝石精华"、"薇诺娜修护精华"。
    4. raw_search_evidence 请摘录报告中提到的销量、好评率或实验数据。
    """

    try:
        # 不再截断，或者给一个足够大的上限
        report_content = raw_report[:40000] 
        
        response = await agent.llm.beta.chat.completions.parse(
            model=agent.model,
            messages=[
                {"role": "system", "content": structurize_prompt},
                {"role": "user", "content": f"以下是调研报告：\n\n{report_content}"}
            ],
            response_format=WebSearchReport,
        )
        web_report = agent._safe_parse_response(response, WebSearchReport)
        
        if not web_report or not web_report.candidates:
             raise ValueError("未能在报告中找到候选商品列表")
        
        print(f"✅ 提取成功，找到 {len(web_report.candidates)} 个候选商品：")
        for i, c in enumerate(web_report.candidates, 1):
            print(f"   {i}. {c.product_name} ({c.brand}) -> XHS关键词: {c.search_keyword_for_xhs}")
            
    except Exception as e:
        print(f"❌ 结构化解析失败: {e}")
        return

    # 4. 进入 Phase 2: 小红书验证
    print("\n[Step 2] 正在进行小红书二次验证 (Phase 2)...")
    xhs_feedbacks = {}
    async with agent.mcp_client.batch_session() as sess:
        for i, candidate in enumerate(web_report.candidates, 1):
            print(f"   [{i}/{len(web_report.candidates)}] 搜索 '{candidate.search_keyword_for_xhs}' 的反馈...")
            try:
                feedback = await agent.xhs_verify_candidate(candidate, intent, session=sess)
                xhs_feedbacks[candidate.product_name] = feedback
                if feedback.strip():
                    print(f"      ✅ 已获取相关笔记和评论")
                else:
                    print(f"      ⚠️ 未搜索到足够相关内容")
            except Exception as e:
                print(f"      ❌ 搜索出错: {e}")
                xhs_feedbacks[candidate.product_name] = ""

    # 5. 进入 Phase 3: 综合分析
    print("\n[Step 3] 正在生成最终推荐榜单 (Phase 3)...")
    try:
        final_report = await agent.comprehensive_analysis(intent, web_report, xhs_feedbacks)
        # 6. 输出结果
        callback.on_recommendation_completed(intent, web_report, final_report)
    except Exception as e:
        print(f"❌ 综合分析失败: {e}")

if __name__ == "__main__":
    # 指定文件路径
    TARGET_FILE = "output/deep_research_中年女性_温和抗老_祛斑_晚间修护_油皮_20260309_215758.md"
    asyncio.run(test_from_file(TARGET_FILE))
