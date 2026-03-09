#!/usr/bin/env python3
"""
测试 _parse_search_result 的解析逻辑是否正确覆盖各种 MCP 返回结构。
用法: uv run python scripts/test_parse_logic.py
"""
import os
import sys
import json
from unittest.mock import MagicMock

# 在导入 OpenAI 之前先清理代理环境变量，避免 socks 代理阻塞
for var in ["ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"]:
    os.environ.pop(var, None)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 需要设置环境变量以免 agent 初始化时报错
os.environ.setdefault("OPENAI_API_KEY", "sk-test-placeholder")

from src.agent import RecommendationAgent

agent = RecommendationAgent.__new__(RecommendationAgent)
agent.llm = None
agent.model = "test"
agent.mcp_client = None

def make_text_content(text: str):
    """模拟 MCP TextContent 对象"""
    obj = MagicMock()
    obj.type = "text"
    obj.text = text
    return obj


def run_test(name: str, search_res, expected_count: int, expected_first_id: str = None):
    """运行单个测试并打印结果"""
    result = agent._parse_search_result(search_res)
    ok = len(result) == expected_count
    if expected_first_id and result:
        ok = ok and result[0].get("id") == expected_first_id
    
    icon = "✅" if ok else "❌"
    print(f"  {icon} {name}")
    if not ok:
        print(f"      期望 {expected_count} 条, 实际 {len(result)} 条")
        if expected_first_id and result:
            print(f"      期望首条 id={expected_first_id}, 实际={result[0].get('id')}")
    return ok


print("\n🧪 _parse_search_result 单元测试\n")

passed = 0
total = 0

# ========== 测试 1: 真实 MCP 返回结构 {"feeds": [...]} ==========
total += 1
real_mcp_response = [make_text_content(json.dumps({
    "feeds": [
        {"xsecToken": "ABC123", "id": "note001", "modelType": "note", "noteCard": {"displayTitle": "测试笔记1"}},
        {"xsecToken": "DEF456", "id": "note002", "modelType": "note", "noteCard": {"displayTitle": "测试笔记2"}},
        {"xsecToken": "GHI789", "id": "note003", "modelType": "note", "noteCard": {"displayTitle": "测试笔记3"}},
        {"xsecToken": "JKL012", "id": "note004", "modelType": "note", "noteCard": {"displayTitle": "测试笔记4"}},
    ]
}))]
if run_test("真实MCP结构: {feeds: [...]}, 取前3条", real_mcp_response, 3, "note001"):
    passed += 1

# ========== 测试 2: 纯数组结构 [...] ==========
total += 1
array_response = [make_text_content(json.dumps([
    {"xsec_token": "token1", "id": "id001"},
    {"xsec_token": "token2", "id": "id002"},
]))]
if run_test("备选结构: 纯JSON数组", array_response, 2, "id001"):
    passed += 1

# ========== 测试 3: 空 feeds ==========
total += 1
empty_feeds = [make_text_content(json.dumps({"feeds": []}))]
if run_test("空 feeds 数组", empty_feeds, 0):
    passed += 1

# ========== 测试 4: 非JSON文本 ==========
total += 1
non_json = [make_text_content("这不是JSON，这是纯文本返回")]
if run_test("非JSON文本内容", non_json, 0):
    passed += 1

# ========== 测试 5: None 输入 ==========
total += 1
if run_test("None 输入", None, 0):
    passed += 1

# ========== 测试 6: 空列表 ==========
total += 1
if run_test("空列表 []", [], 0):
    passed += 1

# ========== 测试 7: content 中有多个块，但只有一个是 text ==========
total += 1
mixed_content = [MagicMock(type="image", text=None), make_text_content(json.dumps({"feeds": [
    {"xsecToken": "t1", "id": "mixed001"}
]}))]
if run_test("混合content (image+text)", mixed_content, 1, "mixed001"):
    passed += 1

# ========== 测试 8: 验证 xsecToken 驼峰字段可被正确提取 ==========
total += 1
camel_feed = [make_text_content(json.dumps({"feeds": [
    {"xsecToken": "camelToken", "id": "camel001", "noteCard": {"displayTitle": "驼峰测试"}}
]}))]
result = agent._parse_search_result(camel_feed)
has_token = result and result[0].get("xsecToken") == "camelToken"
icon = "✅" if has_token else "❌"
print(f"  {icon} 驼峰字段 xsecToken 正确保留")
if has_token:
    passed += 1

# ========== 测试 9: 使用 "items" 作为键名 ==========
total += 1
items_response = [make_text_content(json.dumps({"items": [
    {"xsecToken": "item_tok", "id": "item001"}
]}))]
if run_test("备选key: {items: [...]}", items_response, 1, "item001"):
    passed += 1

print(f"\n{'='*50}")
print(f"  结果: {passed}/{total} 通过")
if passed == total:
    print(f"  🎉 全部通过!")
else:
    print(f"  ⚠️  有 {total - passed} 项失败，请检查解析逻辑。")
print(f"{'='*50}\n")
