#!/usr/bin/env python3
"""
测试 MCP get_feed_detail 返回值结构。
用法: uv run python scripts/test_mcp_detail.py <feed_id> <xsec_token>
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


async def main():
    if len(sys.argv) < 3:
        print("用法: uv run python scripts/test_mcp_detail.py <feed_id> <xsec_token>")
        print("  tip: 先运行 test_mcp_search.py 获取 feed_id 和 xsec_token")
        return
    
    feed_id = sys.argv[1]
    xsec_token = sys.argv[2]
    
    mcp_url = os.getenv("XHS_MCP_URL", "http://127.0.0.1:18060/mcp")
    
    from urllib.parse import urlparse
    host = urlparse(mcp_url).hostname or ""
    no_proxy = os.environ.get("NO_PROXY", "")
    os.environ["NO_PROXY"] = ",".join(filter(bool, [no_proxy, "127.0.0.1", "localhost", host]))
    os.environ["no_proxy"] = os.environ["NO_PROXY"]
    
    print(f"🔍 测试 MCP get_feed_detail")
    print(f"   MCP URL    : {mcp_url}")
    print(f"   feed_id    : {feed_id}")
    print(f"   xsec_token : {xsec_token}")
    print("-" * 60)
    
    from mcp.client.streamable_http import streamablehttp_client
    from mcp.client.session import ClientSession
    
    async with streamablehttp_client(mcp_url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            print("✅ MCP Session 已建立\n")
            
            print("📡 调用 get_feed_detail...")
            result = await session.call_tool("get_feed_detail", arguments={
                "feed_id": feed_id,
                "xsec_token": xsec_token,
                "load_all_comments": False
            })
            
            print(f"\n📦 返回结果:")
            print(f"   type(result)        = {type(result).__name__}")
            print(f"   result.isError      = {getattr(result, 'isError', 'N/A')}")
            print(f"   len(result.content) = {len(result.content) if result.content else 0}")
            
            if not result.content:
                print("   ⚠️  content 为空!")
                return
            
            for i, item in enumerate(result.content):
                print(f"\n   === content[{i}] ===")
                item_type = getattr(item, "type", "unknown")
                print(f"   type  : {type(item).__name__}")
                print(f"   .type : {item_type}")
                
                if item_type == "text" and hasattr(item, "text"):
                    text = item.text
                    print(f"   .text 长度: {len(text)} chars")
                    print(f"   预览:")
                    print(f"   {text[:2000]}")
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
