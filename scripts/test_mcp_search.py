#!/usr/bin/env python3
"""
测试 MCP search_feeds 返回值结构，用于确认如何正确解析笔记列表。
用法: uv run python scripts/test_mcp_search.py [关键词]
"""
import os
import sys
import json
import asyncio
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("test_mcp_search")


async def main():
    keyword = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "护肤品推荐"
    
    mcp_url = os.getenv("XHS_MCP_URL", "http://127.0.0.1:18060/mcp")
    
    # 免代理
    from urllib.parse import urlparse
    host = urlparse(mcp_url).hostname or ""
    no_proxy = os.environ.get("NO_PROXY", "")
    os.environ["NO_PROXY"] = ",".join(filter(bool, [no_proxy, "127.0.0.1", "localhost", host]))
    os.environ["no_proxy"] = os.environ["NO_PROXY"]
    
    print(f"🔍 测试 MCP search_feeds")
    print(f"   MCP URL  : {mcp_url}")
    print(f"   关键词    : {keyword}")
    print("-" * 60)
    
    from mcp.client.streamable_http import streamablehttp_client
    from mcp.client.session import ClientSession
    
    async with streamablehttp_client(mcp_url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            print("✅ MCP Session 已建立\n")
            
            print("📡 调用 search_feeds...")
            result = await session.call_tool("search_feeds", arguments={
                "keyword": keyword
            })
            
            print(f"\n📦 返回结果:")
            print(f"   type(result)         = {type(result).__name__}")
            print(f"   result.isError       = {getattr(result, 'isError', 'N/A')}")
            print(f"   len(result.content)  = {len(result.content) if result.content else 0}")
            
            if not result.content:
                print("   ⚠️  content 为空!")
                return
            
            for i, item in enumerate(result.content):
                print(f"\n   === content[{i}] ===")
                print(f"   type       : {type(item).__name__}")
                item_type = getattr(item, "type", "unknown")
                print(f"   .type      : {item_type}")
                
                if item_type == "text" and hasattr(item, "text"):
                    text = item.text
                    print(f"   .text 长度  : {len(text)} chars")
                    
                    # 尝试 JSON 解析
                    try:
                        data = json.loads(text)
                        print(f"   JSON 解析   : ✅ 成功")
                        print(f"   JSON 类型   : {type(data).__name__}")
                        if isinstance(data, list):
                            print(f"   列表长度    : {len(data)}")
                            if data:
                                print(f"   第一项 keys : {list(data[0].keys()) if isinstance(data[0], dict) else 'N/A'}")
                                print(f"   第一项内容  :")
                                print(f"   {json.dumps(data[0], ensure_ascii=False, indent=4)[:800]}")
                        elif isinstance(data, dict):
                            print(f"   dict keys   : {list(data.keys())}")
                            print(f"   内容预览    :")
                            print(f"   {json.dumps(data, ensure_ascii=False, indent=4)[:800]}")
                    except json.JSONDecodeError:
                        print(f"   JSON 解析   : ❌ 失败 (内容不是 JSON)")
                        print(f"   原始文本预览:")
                        print(f"   {text[:1000]}")
                else:
                    print(f"   内容: {str(item)[:500]}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n测试被中断。")
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
