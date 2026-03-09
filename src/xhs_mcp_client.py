import logging
from contextlib import asynccontextmanager
from typing import Dict, Any, List

from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client

logger = logging.getLogger(__name__)

class XhsMcpClient:
    """包装与小红书MCP服务(Streamable HTTP)的交互逻辑"""
    def __init__(self, mcp_url: str = "http://127.0.0.1:18060/mcp"):
        self.mcp_url = mcp_url
    
    @asynccontextmanager
    async def session(self):
        """提供管理 mcp-session 生命周期的上下文管理器"""
        async with streamablehttp_client(self.mcp_url) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield session

    async def search_feeds(self, keywords: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """调用 search_feeds 工具搜索符合条件的笔记"""
        async with self.session() as session:
            logger.info(f"Searching XHS feeds for: {keywords}")
            result = await session.call_tool("search_feeds", arguments={
                "keyword": keywords,
                "filters": {"sort_by": "综合"}
            })
            logger.info(f"Raw search_feeds response type: {type(result)}")
            logger.info(f"Raw search_feeds result.content length: {len(result.content) if result.content else 0}")
            for i, c in enumerate(result.content or []):
                content_type = getattr(c, "type", "unknown")
                content_text = getattr(c, "text", "")[:500] if hasattr(c, "text") else str(c)[:500]
                logger.info(f"  content[{i}] type={content_type}, preview={content_text}")
            try:
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
            
            if result.content and len(result.content) > 0:
                return "\n".join(c.text for c in result.content if getattr(c, "type", "") == "text")
            return str(result)
