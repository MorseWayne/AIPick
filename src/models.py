from pydantic import BaseModel, Field
from typing import List, Optional

class SearchIntent(BaseModel):
    """提取的用户搜索意图"""
    keywords: str = Field(description="传递给小红书搜索的关键词字符串，用空格分隔")
    category: Optional[str] = Field(None, description="商品类目，例如笔记本、手机、护肤品")
    budget: Optional[str] = Field(None, description="用户预算")
    core_needs: List[str] = Field(default_factory=list, description="用户的核心需求列表，如：续航好、轻薄")

class ProductEvaluation(BaseModel):
    """LLM对某个单品的多维度评估报告"""
    product_name: str = Field(description="商品完整名称")
    recommendation_index: int = Field(description="推荐指数，0到100的整数")
    pros: List[str] = Field(description="该商品的前3大真实优点")
    cons: List[str] = Field(description="该商品的不可忽视的缺点/槽点")
    cost_performance: float = Field(description="性价比得分，0到10")
    positive_rate: str = Field(description="好评度估算（例如：80%）")
    negative_rate: str = Field(description="差评度估算（例如：15%）")
    summary: str = Field(description="一段给用户的总结性购买建议")

class RecommendationReport(BaseModel):
    """最终的推荐榜单列表"""
    recommendations: List[ProductEvaluation] = Field(description="评估过的商品列表，按推荐指数从高到低排序")
