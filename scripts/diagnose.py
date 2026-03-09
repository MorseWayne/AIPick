#!/usr/bin/env python3
"""
AIPick 诊断工具集
用法: uv run python scripts/diagnose.py
"""
import os
import sys
import asyncio
import logging

# 将项目根目录加入 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("diagnose")


def print_header(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_result(label: str, ok: bool, detail: str = ""):
    icon = "✅" if ok else "❌"
    print(f"  {icon} {label}")
    if detail:
        for line in detail.strip().split("\n"):
            print(f"      {line}")


async def check_env():
    """检查环境变量配置"""
    print_header("1. 环境变量与配置检查")

    api_key = os.getenv("OPENAI_API_KEY", "")
    print_result("OPENAI_API_KEY", bool(api_key), 
                 f"已设置 (长度: {len(api_key)})" if api_key else "未设置! 请在 .env 中配置")

    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    print_result("OPENAI_BASE_URL", True, base_url)

    model = os.getenv("LLM_MODEL", "gpt-4o")
    print_result("LLM_MODEL", True, model)

    mcp_url = os.getenv("XHS_MCP_URL", "")
    print_result("XHS_MCP_URL", bool(mcp_url),
                 mcp_url if mcp_url else "未设置! 将使用默认值 http://10.10.131.118:18060/mcp")

    # 检查代理
    proxy_vars = ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"]
    print(f"\n  ⚙️  代理环境变量:")
    for var in proxy_vars:
        val = os.environ.get(var, os.environ.get(var.lower(), ""))
        if val:
            print(f"      {var} = {val}")
    
    if not any(os.environ.get(v) or os.environ.get(v.lower()) for v in proxy_vars):
        print(f"      (无代理配置)")


async def check_mcp_connectivity():
    """测试 MCP 服务器的网络可达性"""
    print_header("2. MCP 服务器连通性测试")

    from urllib.parse import urlparse
    mcp_url = os.getenv("XHS_MCP_URL", "http://10.10.131.118:18060/mcp")
    parsed = urlparse(mcp_url)
    host = parsed.hostname
    port = parsed.port or 80

    # 将 MCP Host 加入 NO_PROXY
    no_proxy = os.environ.get("NO_PROXY", os.environ.get("no_proxy", ""))
    os.environ["NO_PROXY"] = ",".join(filter(bool, [no_proxy, "127.0.0.1", "localhost", host]))
    os.environ["no_proxy"] = os.environ["NO_PROXY"]

    # TCP 连通性
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=5
        )
        writer.close()
        await writer.wait_closed()
        print_result(f"TCP 连接 {host}:{port}", True, "端口可达")
    except Exception as e:
        print_result(f"TCP 连接 {host}:{port}", False, f"连接失败: {e}")
        return False

    # HTTP 可达性 (用 httpx 发 POST 到 MCP 端点)
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(mcp_url, json={"jsonrpc": "2.0", "method": "initialize", "id": 1, "params": {}})
            print_result(f"HTTP POST {mcp_url}", True, f"HTTP {resp.status_code}")
    except Exception as e:
        print_result(f"HTTP POST {mcp_url}", False, f"请求失败: {e}")
        return False
    
    return True


async def check_mcp_session():
    """尝试建立 MCP Session 并列出可用工具"""
    print_header("3. MCP Session 建立与工具发现")

    mcp_url = os.getenv("XHS_MCP_URL", "http://10.10.131.118:18060/mcp")
    
    try:
        from mcp.client.streamable_http import streamablehttp_client
        from mcp.client.session import ClientSession

        async with streamablehttp_client(mcp_url) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                print_result("MCP Session 建立", True, "Streamable HTTP 握手成功")

                tools = await session.list_tools()
                tool_names = [t.name for t in tools.tools]
                print_result(f"发现 {len(tool_names)} 个工具", True, ", ".join(tool_names))
                return tool_names
    except Exception as e:
        print_result("MCP Session 建立", False, f"失败: {e}")
        
        # 如果 streamable http 失败，尝试 SSE 降级
        print(f"      尝试 SSE 传输降级...")
        try:
            from mcp.client.sse import sse_client
            from mcp.client.session import ClientSession
            async with sse_client(mcp_url) as streams:
                async with ClientSession(streams[0], streams[1]) as session:
                    await session.initialize()
                    print_result("MCP Session (SSE 模式)", True, "SSE 握手成功")
                    tools = await session.list_tools()
                    tool_names = [t.name for t in tools.tools]
                    print_result(f"发现 {len(tool_names)} 个工具", True, ", ".join(tool_names))
                    return tool_names
        except Exception as e2:
            print_result("MCP Session (SSE 降级)", False, f"也失败: {e2}")
        
        return []


async def check_search_feeds():
    """测试 search_feeds 调用与返回数据结构"""
    print_header("4. search_feeds 调用测试")
    
    mcp_url = os.getenv("XHS_MCP_URL", "http://10.10.131.118:18060/mcp")
    
    try:
        from mcp.client.streamable_http import streamablehttp_client
        from mcp.client.session import ClientSession

        async with streamablehttp_client(mcp_url) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                
                result = await session.call_tool("search_feeds", arguments={
                    "keyword": "护肤品推荐"
                })
                
                print_result("search_feeds 调用", True)
                print(f"\n      返回结果结构分析:")
                print(f"      result type        = {type(result).__name__}")
                print(f"      result.content     = {type(result.content).__name__} (len={len(result.content) if result.content else 0})")
                print(f"      result.isError     = {getattr(result, 'isError', 'N/A')}")
                
                if result.content:
                    for i, item in enumerate(result.content[:3]):
                        print(f"\n      --- content[{i}] ---")
                        print(f"      type  : {type(item).__name__}")
                        print(f"      .type : {getattr(item, 'type', 'N/A')}")
                        text = getattr(item, "text", None)
                        if text:
                            preview = text[:600].replace("\n", "\n              ")
                            print(f"      .text : {preview}")
                        else:
                            print(f"      str() : {str(item)[:400]}")
                            
    except Exception as e:
        print_result("search_feeds 调用", False, f"失败: {e}")


async def check_llm():
    """测试 LLM 连接"""
    print_header("5. LLM API 连通性测试")
    
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = os.getenv("LLM_MODEL", "gpt-4o")
    
    if not api_key:
        print_result("LLM API", False, "OPENAI_API_KEY 未配置")
        return
    
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=5
        )
        answer = resp.choices[0].message.content
        print_result(f"LLM ({model})", True, f"响应正常 -> '{answer}'")
    except Exception as e:
        print_result(f"LLM ({model})", False, f"请求失败: {e}")


async def main():
    print("\n🔍 AIPick 系统诊断工具")
    print("=" * 60)

    await check_env()
    await check_llm()
    reachable = await check_mcp_connectivity()
    
    if reachable:
        tools = await check_mcp_session()
        if "search_feeds" in tools:
            await check_search_feeds()
        else:
            print("\n  ⚠️  search_feeds 工具不在发现列表中，跳过调用测试。")
    else:
        print("\n  ⚠️  MCP 服务器不可达，跳过后续测试。请检查服务是否启动、地址是否正确。")

    print(f"\n{'='*60}")
    print("  诊断完成。如果你看到了 ❌，请按提示排查对应项。")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n诊断被中断。")
