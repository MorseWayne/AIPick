"""
Qwen Deep Research 客户端封装。

使用 DashScope 原生 SDK 调用 qwen-deep-research 模型，
实现多轮深度搜索、信息整合和结构化研究报告生成。

注意：该模型仅支持 DashScope 原生 SDK（不支持 OpenAI 兼容接口），且仅支持流式输出。

Deep Research 是两步式工作流：
  Step 1: 反问确认（模型提出细化问题，明确研究范围）
  Step 2: 深入研究（基于确认后的方向，执行多轮搜索并生成报告）
"""

import os
import logging
import asyncio
from typing import Optional, Callable

import dashscope

logger = logging.getLogger(__name__)


class DeepResearchClient:
    """封装 Qwen Deep Research 的两步式调用逻辑"""

    def __init__(self, api_key: Optional[str] = None, model: str = "qwen-deep-research"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
        self.model = model

    async def research(
        self,
        query: str,
        on_status: Optional[Callable[[str, str], None]] = None,
    ) -> str:
        """
        执行完整的两步式深度研究，返回最终的研究报告文本。

        Step 1: 发送查询 → 模型返回反问/确认内容
        Step 2: 将反问内容 + 用户确认（"请直接按上述方向深入研究"）发回 → 模型执行深度搜索并生成报告

        Args:
            query: 研究查询内容（应包含完整的用户需求和搜索指令）
            on_status: 可选的状态回调函数 (phase, status) -> None

        Returns:
            最终研究报告的完整文本
        """
        logger.info(f"[DeepResearch] Starting two-step research with model={self.model}")

        # DashScope SDK 是同步的，使用 asyncio.to_thread 包装以兼容异步架构
        result = await asyncio.to_thread(
            self._two_step_research_sync, query, on_status
        )

        logger.info(f"[DeepResearch] Research completed, report length={len(result)} chars")
        return result

    def _two_step_research_sync(
        self,
        query: str,
        on_status: Optional[Callable[[str, str], None]] = None,
    ) -> str:
        """
        同步执行两步式 Deep Research 流程。
        """
        # ===== Step 1: 反问确认 =====
        logger.info("[DeepResearch] Step 1: Sending initial query for clarification...")
        if on_status:
            try:
                on_status("Step1", "正在分析研究方向...")
            except Exception:
                pass

        messages_step1 = [{"role": "user", "content": query}]
        step1_content = self._call_stream(messages_step1, on_status, step_name="Step1")

        if not step1_content.strip():
            logger.warning("[DeepResearch] Step 1 returned empty content")
            return ""

        logger.info(f"[DeepResearch] Step 1 completed, clarification length={len(step1_content)} chars")

        # ===== Step 2: 深入研究 =====
        # 将 Step 1 的反问内容作为 assistant 回复，然后用户确认"按此方向研究"
        logger.info("[DeepResearch] Step 2: Starting deep research...")
        if on_status:
            try:
                on_status("Step2", "开始深入研究...")
            except Exception:
                pass

        messages_step2 = [
            {"role": "user", "content": query},
            {"role": "assistant", "content": step1_content},
            {"role": "user", "content": "请直接按以上方向进行全面深入的研究，不需要再确认。请重点调研各电商平台的销量排行、用户好评率、差评率、专业评测评分等具体数据。"},
        ]
        step2_content = self._call_stream(messages_step2, on_status, step_name="Step2")

        logger.info(f"[DeepResearch] Step 2 completed, report length={len(step2_content)} chars")
        return step2_content

    def _call_stream(
        self,
        messages: list,
        on_status: Optional[Callable[[str, str], None]] = None,
        step_name: str = "",
    ) -> str:
        """
        单次流式调用 DashScope Deep Research API。
        解析多阶段响应，累积 answer 阶段的内容并返回。
        """
        try:
            responses = dashscope.Generation.call(
                api_key=self.api_key,
                model=self.model,
                messages=messages,
                stream=True,
            )
        except Exception as e:
            logger.error(f"[DeepResearch] API call failed: {e}")
            raise

        current_phase = None
        answer_content = ""
        research_plan = ""
        web_sites_count = 0

        for response in responses:
            # 检查响应状态
            if hasattr(response, "status_code") and response.status_code != 200:
                error_code = getattr(response, "code", "unknown")
                error_msg = getattr(response, "message", "unknown error")
                logger.error(f"[DeepResearch] API error: code={error_code}, message={error_msg}")
                raise RuntimeError(f"Deep Research API 错误: [{error_code}] {error_msg}")

            if not hasattr(response, "output") or not response.output:
                continue

            message = response.output.get("message", {})
            phase = message.get("phase", "")
            content = message.get("content", "")
            status = message.get("status", "")
            extra = message.get("extra", {})

            # 阶段切换时记录日志
            if phase != current_phase:
                if current_phase:
                    logger.info(f"[DeepResearch][{step_name}] Phase '{current_phase}' completed")
                current_phase = phase
                if phase and phase != "KeepAlive":
                    logger.info(f"[DeepResearch][{step_name}] Entering phase: {phase}")
                    if on_status:
                        try:
                            phase_display = {
                                "ResearchPlanning": "📋 正在制定研究计划...",
                                "WebResearch": "🔍 正在深度搜索全网信息...",
                                "answer": "📝 正在生成研究报告..." if step_name == "Step2" else "🤔 正在分析研究方向...",
                            }.get(phase, f"⏳ {phase}")
                            on_status(phase, phase_display)
                        except Exception:
                            pass

            # KeepAlive 阶段：跳过
            if phase == "KeepAlive":
                continue

            # ResearchPlanning 阶段
            if phase == "ResearchPlanning" and content:
                research_plan += content

            # WebResearch 阶段
            if phase == "WebResearch":
                deep_research_info = extra.get("deep_research", {})
                research_info = deep_research_info.get("research", {})

                if status == "streamingWebResult":
                    sites = research_info.get("webSites", [])
                    if sites:
                        web_sites_count = len(sites)
                elif status == "WebResultFinished":
                    logger.info(f"[DeepResearch][{step_name}] Web search completed, found {web_sites_count} sources")
                    if on_status:
                        try:
                            on_status(phase, f"🔍 搜索完成，找到 {web_sites_count} 个信息源")
                        except Exception:
                            pass

            # answer 阶段：累积内容
            if phase == "answer" and content:
                answer_content += content

            # 记录 token 消耗
            if status == "finished":
                if hasattr(response, "usage") and response.usage:
                    usage = response.usage
                    input_tokens = usage.get("input_tokens", 0)
                    output_tokens = usage.get("output_tokens", 0)
                    logger.info(
                        f"[DeepResearch][{step_name}] Token usage: input={input_tokens}, output={output_tokens}"
                    )

        if research_plan:
            logger.info(f"[DeepResearch][{step_name}] Research plan length: {len(research_plan)} chars")

        return answer_content
