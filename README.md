# rss-feishu-bot

Push RSS updates to Feishu via GitHub Actions.

## 功能

- 定时拉取 RSS 并推送到飞书群机器人。
- 通过 `state.json` 记录上次推送位置，避免重复发送。
- 支持手动触发“强制推送”用于测试。
- 支持推送摘要（可配置长度）。

## 使用方式

1. Fork/Clone 本仓库。
2. 在 GitHub 仓库 `Settings -> Secrets and variables -> Actions` 中添加：
   - `FEISHU_WEBHOOK`: 飞书机器人 Webhook 地址。
3. 启用 Actions，工作流会每天北京时间 09:00 自动执行。
4. 你也可以在 Actions 页面手动 `Run workflow`，并通过输入项控制：
   - `force_send`：是否忽略 `state.json` 强制发送。
   - `force_items`：强制发送条数。

## 可选环境变量

脚本 `rss_to_feishu.py` 支持以下环境变量：

- `RSS_URL`（默认：`https://imjuya.github.io/juya-ai-daily/rss.xml`）
- `MAX_ITEMS_PER_RUN`（默认：`5`）
- `INCLUDE_SUMMARY`（默认：`0`）
- `SUMMARY_MAX_LEN`（默认：`140`）
- `ALWAYS_NOTIFY`（默认：`0`）
- `FORCE_SEND`（默认：`false`）
- `FORCE_ITEMS`（默认：`3`）
- `TIMEOUT`（默认：`15`）
- `KIMI_API_KEY`（用于生成 AI 解读，默认：空）

## 本地运行

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export FEISHU_WEBHOOK='https://open.feishu.cn/open-apis/bot/v2/hook/xxx'
python rss_to_feishu.py
```
