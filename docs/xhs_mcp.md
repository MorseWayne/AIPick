# Xiaohongshu MCP Server Capability Documentation

This document outlines the capabilities and tools provided by the `xiaohongshu-mcp` server located at `http://10.10.131.118:18060/mcp`.

## Server Overview

- **Name**: `xiaohongshu-mcp`
- **Version**: `2.0.0`
- **Protocol Version**: `2024-11-05`
- **Capabilities**:
  - `logging`: Supports server-side logging.
  - `tools`: Provides interactive tools for Xiaohongshu operations.

---

## Tools Specification

The following tools are available for interacting with Xiaohongshu.

### 1. Authentication & Session Management

- **`check_login_status`**: 检查小红书登录状态
  - *Parameters:* None

- **`get_login_qrcode`**: 获取登录二维码（返回 Base64 图片和超时时间）
  - *Parameters:* None

- **`delete_cookies`**: 删除 cookies 文件，重置登录状态（删除后需要重新登录）
  - *Parameters:* None

### 2. Content Discovery

- **`list_feeds`**: 获取首页 Feeds 列表
  - *Parameters:* None

- **`search_feeds`**: 搜索小红书内容内容（需要已登录）
  - *Parameters:*
    - `keyword` (string, **required**): 搜索关键词
    - `filters` (object): 筛选选项，包含 `location`, `note_type`, `publish_time`, `search_scope`, `sort_by`

- **`get_feed_detail`**: 获取小红书笔记详情（内容、图片、作者、互动数据及评论）
  - *Parameters:*
    - `feed_id` (string, **required**): 小红书笔记ID
    - `xsec_token` (string, **required**): 访问令牌
    - `load_all_comments` (boolean): 是否加载全部评论（默认 false）
    - `click_more_replies` (boolean): 是否展开二级回复（当 `load_all_comments` 为 true 时有效）
    - `limit` (integer): 加载的一级评论数量限制
    - `reply_limit` (integer): 跳过回复数过多的评论
    - `scroll_speed` (string): 滚动速度 (slow, normal, fast)

- **`user_profile`**: 获取指定的小红书用户主页信息
  - *Parameters:*
    - `user_id` (string, **required**): 小红书用户ID
    - `xsec_token` (string, **required**): 访问令牌

### 3. Engagement & Interaction

- **`like_feed`**: 为指定笔记点赞或取消点赞
  - *Parameters:*
    - `feed_id` (string, **required**): 小红书笔记ID
    - `xsec_token` (string, **required**): 访问令牌
    - `unlike` (boolean): 是否取消点赞（true 为取消点赞）

- **`favorite_feed`**: 收藏指定笔记或取消收藏
  - *Parameters:*
    - `feed_id` (string, **required**): 小红书笔记ID
    - `xsec_token` (string, **required**): 访问令牌
    - `unfavorite` (boolean): 是否取消收藏（true 为取消收藏）

- **`post_comment_to_feed`**: 发表评论到小红书笔记
  - *Parameters:*
    - `feed_id` (string, **required**): 小红书笔记ID
    - `xsec_token` (string, **required**): 访问令牌
    - `content` (string, **required**): 评论内容

- **`reply_comment_in_feed`**: 回复小红书笔记下的指定评论
  - *Parameters:*
    - `feed_id` (string, **required**): 小红书笔记ID
    - `xsec_token` (string, **required**): 访问令牌
    - `comment_id` (string, **required**): 目标评论ID
    - `user_id` (string, **required**): 目标评论用户ID
    - `content` (string, **required**): 回复内容

### 4. Content Publishing

- **`publish_content`**: 发布小红书图文内容
  - *Parameters:*
    - `title` (string, **required**): 内容标题
    - `content` (string, **required**): 正文内容（不包含标签）
    - `images` (array, **required**): 图片路径列表（本地路径或 URL）
    - `tags` (array): 话题标签列表
    - `is_original` (boolean): 是否声明原创
    - `products` (array): 商品关键词列表
    - `schedule_at` (string): 定时发布时间 (ISO8601)
    - `visibility` (string): 可见范围 (公开可见、仅自己可见、仅互关好友可见)

- **`publish_with_video`**: 发布小红书视频内容
  - *Parameters:*
    - `title` (string, **required**): 内容标题
    - `content` (string, **required**): 正文内容
    - `video` (string, **required**): 本地视频绝对路径
    - `tags` (array): 话题标签列表
    - `products` (array): 商品关键词列表
    - `schedule_at` (string): 定时发布时间 (ISO8601)
    - `visibility` (string): 可见范围

---

## Usage Notes

- **Login Requirement**: Most tools require an active session. Use `check_login_status` to verify and `get_login_qrcode` if a new session is needed.
- **Tokens**: Many tools require an `xsec_token`, which is typically obtained from the feed list or search results.
- **Rate Limiting**: Be mindful of Xiaohongshu's rate limits when using automated tools.
