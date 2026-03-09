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
    """LLM 对用户需求的深度分析结果"""
    is_sufficient: bool = Field(description="信息是否足够进行搜索推荐")
    follow_up_question: Optional[str] = Field(None, description="追问问题")
    follow_up_reason: Optional[str] = Field(None, description="追问理由")
    follow_up_options: List[str] = Field(default_factory=list, description="与 follow_up_question 直接对应的快捷回答选项，必须是该问题的合理答案")
    category: Optional[str] = Field(None, description="商品类目")
    budget: Optional[str] = Field(None, description="预算范围")
    core_needs: List[str] = Field(default_factory=list, description="核心需求列表")
    user_profile: Optional[str] = Field(None, description="用户画像")
    usage_scenario: Optional[str] = Field(None, description="使用场景")
    brand_preference: Optional[str] = Field(None, description="品牌偏好")
    pain_points: List[str] = Field(default_factory=list, description="过往痛点")
    keywords: str = Field(default="", description="搜索关键词")
    search_queries: List[str] = Field(default_factory=list, description="多角度补充搜索查询")

class QuestionItem(BaseModel):
    """批量追问中的单个问题"""
    question: str = Field(description="要向用户提出的追问问题")
    reason: str = Field(description="为什么需要问这个问题（一句话解释）")
    options: List[str] = Field(default_factory=list, description="2~5个简短选项（每个≤10汉字），必须是该问题的直接回答")
    allow_multiple: bool = Field(
        default=False,
        description="是否允许多选。互斥性维度（预算、年龄段、性别）为false；可叠加维度（功能需求、品牌偏好、痛点）为true"
    )

class BatchQuestions(BaseModel):
    """LLM 根据用户初始输入一次性生成的追问问题列表"""
    questions: List[QuestionItem] = Field(description="需要向用户追问的问题列表，按重要性排序")
    category: Optional[str] = Field(None, description="从输入中初步提取的商品类目")
    initial_keywords: str = Field(default="", description="初步搜索关键词")

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
