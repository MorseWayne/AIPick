from pydantic import BaseModel, Field
from typing import List, Optional

class SearchIntent(BaseModel):
    """提取的用户搜索意图（包含深度需求分析后的完整信息）"""
    keywords: str = Field(description="传递给小红书搜索的关键词字符串，用空格分隔")
    category: Optional[str] = Field(None, description="商品类目，例如笔记本、手机、护肤品")
    budget: Optional[str] = Field(None, description="用户预算")
    core_needs: List[str] = Field(default_factory=list, description="用户的核心需求列表，如：续航好、轻薄")
    user_profile: Optional[str] = Field(None, description="用户画像（如：25岁女生、油皮、IT从业者等）")
    usage_scenario: Optional[str] = Field(None, description="使用场景（如：日常通勤、送长辈、户外运动）")
    brand_preference: Optional[str] = Field(None, description="品牌偏好或排斥（如：偏好国货、不考虑XX品牌）")
    pain_points: List[str] = Field(default_factory=list, description="过往使用同类产品的痛点/踩坑经历")
    search_queries: List[str] = Field(default_factory=list, description="LLM 从多个角度生成的 2~3 个补充搜索查询（用于 Phase 1 扩大候选覆盖面）")

class NeedsAnalysis(BaseModel):
    """LLM 对用户需求的深度分析，用于驱动多轮对话式追问"""
    is_sufficient: bool = Field(
        description="当前收集到的信息是否已足够进行精准的商品搜索推荐。"
                    "判断标准：至少需明确【商品类目】+【大致预算】+【2个以上具体核心需求】。"
                    "如果用户首次输入就非常详细，可以直接标为 true。"
    )
    follow_up_question: Optional[str] = Field(
        None,
        description="如果信息不足，生成的下一个追问问题。"
                    "问题应该自然亲切、有针对性，帮助深度挖掘用户真实需求。"
                    "每次只问一个问题，不要同时问多个。"
    )
    follow_up_reason: Optional[str] = Field(
        None,
        description="简短的追问理由（展示给用户，让用户理解为什么需要这个信息），"
                    "例如：'了解您的肤质可以帮我排除可能引起过敏的产品'"
    )

    # ----- 以下是从对话中逐步提取的结构化意图 -----
    category: Optional[str] = Field(None, description="商品类目")
    budget: Optional[str] = Field(None, description="用户预算范围")
    core_needs: List[str] = Field(default_factory=list, description="核心需求列表")
    user_profile: Optional[str] = Field(
        None, description="用户画像描述（年龄段、性别、个人特征如肤质/体型等）"
    )
    usage_scenario: Optional[str] = Field(
        None, description="使用场景（日常/送礼/特定活动等）"
    )
    brand_preference: Optional[str] = Field(
        None, description="品牌偏好或排斥信息"
    )
    pain_points: List[str] = Field(
        default_factory=list, description="用户过往使用同类产品的痛点/踩坑经历"
    )
    keywords: str = Field(
        default="",
        description="综合所有已收集到的信息合成的搜索关键词（即使信息还不完整也尝试生成）"
    )

class CandidateProduct(BaseModel):
    """LLM联网搜索阶段筛选出的候选商品"""
    product_name: str = Field(description="具体的商品名称/型号，例如：ThinkPad X1 Carbon 2024, MacBook Air M3")
    brand: str = Field(description="品牌名称")
    price_range: str = Field(description="参考价格区间，如：4999-5499")
    highlights: List[str] = Field(description="通过全网搜索得到的核心卖点/亮点，不超过5条")
    sales_info: Optional[str] = Field(None, description="销量或市场热度信息(如果搜索到)")
    search_keyword_for_xhs: str = Field(description="为该商品生成的用于小红书二次搜索的精准关键词")

class WebSearchReport(BaseModel):
    """LLM联网搜索阶段的结构化输出"""
    market_summary: str = Field(description="当前市场概况简述(该品类的市场现状、热门趋势)")
    candidates: List[CandidateProduct] = Field(description="从全网筛选出的符合用户需求的候选商品列表，推荐3-5款")
    raw_search_evidence: Optional[str] = Field(
        None,
        description="LLM 联网搜索时获取到的关键数据点和信息来源摘要（如：京东月销10万+、什么值得买评分8.7等），"
                    "保留原始搜索证据，供后续综合分析阶段参考"
    )

class ProductEvaluation(BaseModel):
    """LLM对某个单品的多维度评估报告"""
    product_name: str = Field(description="商品完整名称")
    recommendation_index: int = Field(description="推荐指数，0到100的整数")
    needs_match_detail: Optional[str] = Field(
        None,
        description="该商品对用户核心需求和痛点的逐项匹配分析简述（如：'拍照需求✅ 徕卡调色出色；续航需求⚠️ 中等水平'）"
    )
    pros: List[str] = Field(description="该商品的前3大真实优点")
    cons: List[str] = Field(description="该商品的不可忽视的缺点/槽点")
    cost_performance: float = Field(description="性价比得分，0到10")
    positive_rate: str = Field(description="好评度估算（例如：80%）")
    negative_rate: str = Field(description="差评度估算（例如：15%）")
    confidence_level: str = Field(
        default="高",
        description="推荐置信度：'高'（全网+小红书数据充足）/ '中'（部分数据不足）/ '低'（缺少小红书验证）"
    )
    summary: str = Field(description="一段给用户的总结性购买建议")

class RecommendationReport(BaseModel):
    """最终的推荐榜单列表"""
    recommendations: List[ProductEvaluation] = Field(description="评估过的商品列表，按推荐指数从高到低排序")
