import asyncio
import os
from dotenv import load_dotenv
from openai import AsyncOpenAI
from src.models import WebSearchReport

async def main():
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = os.getenv("LLM_MODEL", "gpt-4o")
    
    llm = AsyncOpenAI(api_key=api_key, base_url=base_url)
    
    with open("output/deep_research_中年女性_温和抗老_祛斑_晚间修护_油皮_20260309_215758.md", "r", encoding="utf-8") as f:
        raw_report = f.read()
    
    structurize_prompt = """你是一个数据提取专家。下面是一份商品调研报告（markdown 格式），请从中提取结构化信息。

⚠️ 重要：请从报告中提取以下信息，严格按照 WebSearchReport 格式输出 JSON：
- market_summary: 市场概况简述
- candidates: 3~5 款候选商品（每款包含 product_name, brand, price_range, highlights, sales_info, search_keyword_for_xhs）
- raw_search_evidence: 报告中提到的所有具体数据点（销量数据、好评率、评测评分、价格信息等），原样保留

关于 search_keyword_for_xhs 字段：
- 必须简短精准，2~4 个词，不超过 10 个汉字
- 格式："品牌名 产品型号"，如 "珀莱雅红宝石套装"、"ThinkPad X1 Carbon"
- 不加"测评""推荐"等后缀

请以 JSON 格式输出。"""

    report_for_parse = raw_report[:15000]

    print("Sending request to LLM...")
    try:
        response = await llm.beta.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system", "content": structurize_prompt},
                {"role": "user", "content": f"以下是调研报告：\n\n{report_for_parse}"}
            ],
            response_format=WebSearchReport,
            temperature=0.1,
            max_tokens=3000,
        )
        print("Raw content:")
        print(response.choices[0].message.content)
        
        print("\nParsed:")
        print(response.choices[0].message.parsed)
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(main())
