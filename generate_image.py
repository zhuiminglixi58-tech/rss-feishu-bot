"""
generate_image.py
用 HTML 渲染 AI 早报，通过 playwright 截长图
依赖：pip install playwright && playwright install chromium
"""

import os
from datetime import datetime

EMOJI_MAP = {
    "要闻":            "🗞️ 要闻",
    "模型发布":         "🚀 模型发布",
    "开发生态":         "🛠️ 开发生态",
    "技术与洞察":       "🔬 技术与洞察",
    "行业动态":         "📊 行业动态",
    "前瞻与传闻":       "🔮 前瞻与传闻",
    "AI for Science":  "🧪 AI for Science",
    "具身智能":         "🤖 具身智能",
    "AI音乐":          "🎵 AI音乐",
    "AI绘画":          "🎨 AI绘画",
    "AI视频":          "🎬 AI视频",
    "工具推荐":         "⚙️ 工具推荐",
    "产品动态":         "📱 产品动态",
}


def build_html(issue, sections):
    today = datetime.now().strftime("%Y-%m-%d")

    sections_html = ""
    for title, items in sections.items():
        if not items:
            continue
        display_title = EMOJI_MAP.get(title, f"📌 {title}")
        items_html = "\n".join([
            f'<li>{item["text"]}</li>'
            for item in items
        ])
        sections_html += f"""
        <div class="section">
            <div class="section-title">{display_title}</div>
            <ul>{items_html}</ul>
        </div>
        """

    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}

  body {{
    background: #0f1117;
    font-family: "PingFang SC", "Noto Sans CJK SC", "Microsoft YaHei", sans-serif;
    width: 800px;
    padding-bottom: 32px;
  }}

  .header {{
    background: linear-gradient(135deg, #1a3a5c 0%, #0d2137 100%);
    padding: 28px 40px;
    display: flex;
    align-items: center;
    gap: 12px;
    border-bottom: 2px solid #2a5a8c;
  }}

  .header-title {{
    font-size: 26px;
    font-weight: 700;
    color: #ffffff;
    letter-spacing: 1px;
  }}

  .header-date {{
    font-size: 15px;
    color: #7eb8e8;
    margin-top: 4px;
  }}

  .content {{
    padding: 24px 40px 0;
  }}

  .section {{
    margin-bottom: 20px;
    background: #161b27;
    border-radius: 12px;
    overflow: hidden;
    border: 1px solid #1e2a3a;
  }}

  .section-title {{
    background: linear-gradient(90deg, #1a3a5c, #162030);
    color: #63b3ed;
    font-size: 17px;
    font-weight: 700;
    padding: 12px 20px;
    border-bottom: 1px solid #1e2a3a;
    letter-spacing: 0.5px;
  }}

  ul {{
    list-style: none;
    padding: 10px 20px 12px;
  }}

  li {{
    color: #dce3ed;
    font-size: 15px;
    line-height: 1.7;
    padding: 5px 0 5px 16px;
    position: relative;
    border-bottom: 1px solid #1a2233;
  }}

  li:last-child {{
    border-bottom: none;
  }}

  li::before {{
    content: "•";
    color: #4a9fd4;
    position: absolute;
    left: 0;
    font-size: 18px;
    line-height: 1.5;
  }}

  .footer {{
    text-align: center;
    color: #4a5568;
    font-size: 13px;
    padding: 20px 40px 0;
  }}
</style>
</head>
<body>
  <div class="header">
    <div>
      <div class="header-title">🤖 AI 早报</div>
      <div class="header-date">{today}</div>
    </div>
  </div>
  <div class="content">
    {sections_html}
  </div>
  <div class="footer">
    来源：github.com/imjuya/juya-ai-daily
  </div>
</body>
</html>"""


def generate_image(issue, sections, output_path="daily_report.png"):
    html = build_html(issue, sections)

    # 写入临时 HTML 文件
    html_path = output_path.replace(".png", ".html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    # 用 playwright 截图
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 800, "height": 600})
        page.goto(f"file://{os.path.abspath(html_path)}")
        page.wait_for_timeout(500)

        # 截取完整页面高度
        height = page.evaluate("document.body.scrollHeight")
        page.set_viewport_size({"width": 800, "height": height})
        page.screenshot(path=output_path, full_page=True)
        browser.close()

    print(f"图片已生成：{output_path}")
    return output_path


if __name__ == "__main__":
    # 本地测试用
    test_sections = {
        "要闻": [{"text": "OpenAI 发布 GPT-5.4 模型", "url": "https://openai.com"}],
        "模型发布": [
            {"text": "Lightricks正式发布LTX-2.3音视频模型及开源编辑器", "url": None},
            {"text": "Ai2发布全开源混合架构模型Olmo Hybrid 7B", "url": None},
        ],
    }
    test_issue = {"html_url": "https://github.com/imjuya/juya-ai-daily/issues/17"}
    generate_image(test_issue, test_sections)
