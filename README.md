# rss-feishu-bot

Fetch latest AI Daily issue and push digest cards to Feishu via GitHub Actions.

## 功能

- 定时拉取 RSS 并推送到飞书群机器人。
- 通过 `state.json` 记录上次推送位置，避免重复发送。
- 支持手动触发“强制推送”用于测试。
- 支持用 Kimi 生成第二条「AI 解读」卡片（可选）。

## 使用方式

1. Fork/Clone 本仓库。
2. 在 GitHub 仓库 `Settings -> Secrets and variables -> Actions` 中添加：
   - `FEISHU_WEBHOOK`: 飞书机器人 Webhook 地址。
   - `KIMI_API_KEY`: Kimi（Moonshot）API Key（用于生成 AI 解读）。
3. 启用 Actions，工作流会每天北京时间 09:00 自动执行。
4. 你也可以在 Actions 页面手动 `Run workflow`，并通过输入项控制：
   - `force_send`：是否忽略 `state.json` 强制发送。
   - `force_items`：强制发送条数。

## 环境变量

脚本 `rss_to_feishu.py` 当前使用以下环境变量：

- `FEISHU_WEBHOOK`：飞书机器人 Webhook（必填）
- `KIMI_API_KEY`：Kimi（Moonshot）API Key（可选，用于生成 AI 解读）
- `GITHUB_TOKEN`：GitHub Token（可选，用于提升 API 限额）

## 本地运行

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export FEISHU_WEBHOOK='https://open.feishu.cn/open-apis/bot/v2/hook/xxx'
python rss_to_feishu.py
```
