# rss-feishu-bot

一个轻量脚本：抓取 [imjuya/juya-ai-daily](https://github.com/imjuya/juya-ai-daily) 最新一期 Issue 的「概览」内容，并推送到飞书群机器人。

## 当前功能（基于最新代码）

- 拉取目标仓库最新一条 **open issue**。
- 解析 issue 中 `## 概览` 下的 `###` 小节与 bullet 列表。
- 推送一条飞书交互卡片（AI 早报）。
- 可选调用 Kimi（Moonshot）生成第二条「今日 AI 解读」卡片。
- 不包含本地状态管理（不会写入/读取 `state.json`）。

## 环境变量

`rss_to_feishu.py` 使用以下环境变量：

- `FEISHU_WEBHOOK`：飞书机器人 Webhook（可选；未配置则不推送）
- `KIMI_API_KEY`：Kimi API Key（可选；配置后会额外生成 AI 解读卡片）
- `GITHUB_TOKEN`：GitHub Token（可选；用于提高 API 请求限额）

## 本地运行

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export FEISHU_WEBHOOK='https://open.feishu.cn/open-apis/bot/v2/hook/xxx'
# 可选：开启 AI 解读
# export KIMI_API_KEY='your-kimi-api-key'

python rss_to_feishu.py
```

## 运行逻辑说明

1. 请求 GitHub Issues API，获取最新 issue。
2. 仅提取 `## 概览` 区块内容。
3. 发送「🤖 AI 早报」飞书卡片。
4. 若同时配置 `KIMI_API_KEY`，再发送「🧠 今日 AI 解读」卡片。

## 说明

- `generate_image.py` 当前仅保留占位说明，图片生成流程已移除。
- `reports/` 目录用于存放历史生成内容，不参与脚本主流程。
