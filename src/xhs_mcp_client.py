import logging
from contextlib import asynccontextmanager
from typing import Dict, Any, List

from mcp.client.session import ClientSession
from mcp.client.sse import sse_client

logger = logging.getLogger(__name__)

class XhsMcpClient:
    """包装与小红书MCP服务(SSE HTTP)的交互逻辑"""
    def __init__(self, mcp_url: str = "http://10.10.131.118:18060/mcp"):
        self.mcp_url = mcp_url
    
    @asynccontextmanager
    async def session(self):
        """提供管理 mcp-session 生命周期的上下文管理器"""
        async with sse_client(self.mcp_url) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                yield session

    async def search_feeds(self, keywords: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """调用 search_feeds 工具搜索符合条件的笔记"""
        async with self.session() as session:
            logger.info(f"Searching XHS feeds for: {keywords}")
            # MCP调用远程 tool
            result = await session.call_tool("search_feeds", arguments={
                "keyword": keywords,
                "filters": {"sort_by": "综合"}
            })
            # 分析返回结果 (根据具体MCP实现提取文本与JSON列表)
            # 假设返回的是文本里面包含 JSON feed 列表，或者 JSON 数组字符串。
            try:
                # 兼容不同版式，直接抛回给上层，具体看实际数据结构
                return result.content
            except Exception as e:
                logger.error(f"Error parsing search_feeds response: {e}")
                return []

    async def get_feed_detail(self, feed_id: str, xsec_token: str, max_comments: int = 20) -> str:
        """调用 get_feed_detail 抓取特定笔记详情与评论"""
        async with self.session() as session:
            logger.info(f"Fetching detail for feed: {feed_id}")
            result = await session.call_tool("get_feed_detail", arguments={
                "feed_id": feed_id,
                "xsec_token": xsec_token,
                "load_all_comments": True,
                "limit": max_comments
            })
            
            # 返回抓取到的文本结果，供大模型解读
            if result.content and len(result.content) > 0:
                # 提取 MCP Content_Text
                return "\n".join(c.text for c in result.content if getattr(c, "type", "") == "text")
            return str(result)
