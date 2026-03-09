import logging
import asyncio
from contextlib import asynccontextmanager
from typing import Dict, Any, List

from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
RETRY_DELAY = 1.0  # 基础重试延迟秒数


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

    @asynccontextmanager
    async def batch_session(self):
        """
        提供一个复用的批量 session 上下文管理器。
        在一个 session 内可多次调用 search / detail，避免反复握手。
        用法:
            async with client.batch_session() as batch:
                res1 = await batch.call_tool(...)
                res2 = await batch.call_tool(...)
        """
        async with streamablehttp_client(self.mcp_url) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield session

    async def _call_with_retry(self, session, tool_name: str, arguments: dict, retries: int = MAX_RETRIES):
        """带指数退避重试的 MCP 工具调用"""
        last_error = None
        for attempt in range(retries + 1):
            try:
                return await session.call_tool(tool_name, arguments=arguments)
            except Exception as e:
                last_error = e
                if attempt < retries:
                    delay = RETRY_DELAY * (2 ** attempt)
                    logger.warning(f"MCP call '{tool_name}' failed (attempt {attempt+1}/{retries+1}): {e}, retrying in {delay}s...")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"MCP call '{tool_name}' failed after {retries+1} attempts: {e}")
        raise last_error

    async def search_feeds(self, keywords: str, max_results: int = 5, session=None) -> List[Dict[str, Any]]:
        """调用 search_feeds 工具搜索符合条件的笔记。
        如果传入已有 session 则复用，否则自行创建新的 session。
        """
        async def _do_search(sess):
            logger.info(f"Searching XHS feeds for: {keywords}")
            result = await self._call_with_retry(sess, "search_feeds", arguments={
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
        
        if session:
            return await _do_search(session)
        else:
            async with self.session() as sess:
                return await _do_search(sess)

    async def get_feed_detail(self, feed_id: str, xsec_token: str, max_comments: int = 20, session=None) -> str:
        """调用 get_feed_detail 抓取特定笔记详情与评论。
        如果传入已有 session 则复用，否则自行创建新的 session。
        """
        async def _do_detail(sess):
            logger.info(f"Fetching detail for feed: {feed_id}")
            result = await self._call_with_retry(sess, "get_feed_detail", arguments={
                "feed_id": feed_id,
                "xsec_token": xsec_token,
                "load_all_comments": True,
                "limit": max_comments
            })
            
            if result.content and len(result.content) > 0:
                return "\n".join(c.text for c in result.content if getattr(c, "type", "") == "text")
            return str(result)
        
        if session:
            return await _do_detail(session)
        else:
            async with self.session() as sess:
                return await _do_detail(sess)
