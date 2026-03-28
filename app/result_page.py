from __future__ import annotations

from html import escape


def render_result_page(payload: dict[str, object]) -> str:
    page_state = str(payload["page_state"])
    title = escape(str(payload["title"]))
    file_name = escape(str(payload["file_name"]))
    message = escape(str(payload["message"]))

    base_styles = """
body { font-family: Georgia, "Noto Serif SC", serif; margin: 0; background: #f6f1e8; color: #1e2a23; }
main { max-width: 880px; margin: 0 auto; padding: 48px 24px 80px; }
.panel { background: #fffdf8; border: 1px solid #d8cfbd; border-radius: 16px; padding: 24px; box-shadow: 0 12px 30px rgba(49, 43, 31, 0.08); }
.eyebrow { color: #7f6a46; font-size: 13px; letter-spacing: 0.08em; text-transform: uppercase; margin-bottom: 12px; }
h1, h2, h3 { margin: 0 0 12px; }
p { line-height: 1.7; }
.meta { color: #5c564e; margin-bottom: 20px; }
.status { display: inline-block; padding: 6px 12px; border-radius: 999px; font-size: 13px; margin-bottom: 16px; }
.status.completed { background: #d9efe1; color: #1f5a3a; }
.status.reviewing { background: #f7e6b8; color: #6a4b00; }
.status.failed { background: #f4d7d7; color: #7c1f1f; }
.grid { display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); margin: 20px 0 28px; }
.card { background: #f7f2e9; border-radius: 14px; padding: 16px; }
.links a { display: inline-block; margin-right: 12px; margin-bottom: 8px; color: #1b4d74; text-decoration: none; font-weight: 600; }
pre { white-space: pre-wrap; background: #f3efe6; border-radius: 14px; padding: 18px; overflow-x: auto; }
ul { line-height: 1.8; }
.split { display: grid; grid-template-columns: 1.2fr 0.8fr; gap: 16px; margin-top: 24px; }
.note { background: #f0e8da; border-radius: 14px; padding: 16px; line-height: 1.7; }
.tiny { color: #6d655b; font-size: 14px; }
@media (max-width: 720px) { .split { grid-template-columns: 1fr; } }
"""

    status_html = f'<div class="status {escape(page_state)}">{escape(str(payload["status_label"]))}</div>'

    if page_state == "completed":
        risk_count_summary = payload["risk_count_summary"]
        top_risks = payload["top_risks"]
        downloadables = payload["downloadable_files"]
        conclusion_markdown = escape(str(payload["conclusion_markdown"]))
        report_markdown = escape(str(payload["report_markdown"]))
        generated_at = escape(str(payload["generated_at"]))
        page_url = escape(str(payload["page_url"]))
        status_api_url = escape(str(payload["status_api_url"]))
        result_api_url = escape(str(payload["result_api_url"]))
        risk_items_html = "".join(
            f"<li><strong>{escape(str(item['risk_title']))}</strong> | {escape(str(item['risk_level']))} | "
            f"{escape(str(item['location_label']))}<br>{escape(str(item['risk_description']))}</li>"
            for item in top_risks
        ) or "<li>当前未识别到明显风险。</li>"
        download_links_html = "".join(
            f'<a href="{escape(str(item["url"]))}">{escape(str(item["name"]))}</a>'
            for item in downloadables
        )
        body = f"""
<div class="panel">
  <div class="eyebrow">结果页最小实现</div>
  {status_html}
  <h1>{title}</h1>
  <p class="meta">文件：{file_name}</p>
  <p>{message}</p>
  <p class="tiny">结果生成时间：{generated_at}</p>
  <div class="grid">
    <div class="card"><h3>高风险</h3><p>{escape(str(risk_count_summary["high"]))}</p></div>
    <div class="card"><h3>中风险</h3><p>{escape(str(risk_count_summary["medium"]))}</p></div>
    <div class="card"><h3>低风险</h3><p>{escape(str(risk_count_summary["low"]))}</p></div>
  </div>
  <div class="split">
    <div>
      <h2>重点风险摘要</h2>
      <ul>{risk_items_html}</ul>
      <h2>最终结论</h2>
      <pre>{conclusion_markdown}</pre>
      <h2>审查报告</h2>
      <pre>{report_markdown}</pre>
    </div>
    <div>
      <div class="note">
        <h3>快速操作</h3>
        <div class="links">{download_links_html}</div>
        <p class="tiny">页面地址：{page_url}</p>
        <p class="tiny">状态接口：{status_api_url}</p>
        <p class="tiny">结果接口：{result_api_url}</p>
      </div>
      <div class="note" style="margin-top: 16px;">
        <h3>查看建议</h3>
        <p class="tiny">建议先看风险统计和重点风险摘要，再结合完整审查报告下钻原文证据。</p>
      </div>
    </div>
  </div>
</div>
"""
    elif page_state == "failed":
        error_code = escape(str(payload.get("error_code") or "UNKNOWN"))
        status_api_url = escape(str(payload["status_api_url"]))
        body = f"""
<div class="panel">
  <div class="eyebrow">结果页最小实现</div>
  {status_html}
  <h1>{title}</h1>
  <p class="meta">文件：{file_name}</p>
  <p>{message}</p>
  <p>错误码：{error_code}</p>
  <p>建议：请根据错误提示重新提交文件，或先检查运行链路。</p>
  <p class="tiny">状态接口：{status_api_url}</p>
</div>
"""
    else:
        status_api_url = escape(str(payload["status_api_url"]))
        result_api_url = escape(str(payload["result_api_url"]))
        body = f"""
<div class="panel">
  <div class="eyebrow">结果页最小实现</div>
  {status_html}
  <h1>{title}</h1>
  <p class="meta">文件：{file_name}</p>
  <p>{message}</p>
  <p>建议：页面可继续轮询结果接口，或稍后刷新查看。</p>
  <p class="tiny">状态接口：{status_api_url}</p>
  <p class="tiny">结果接口：{result_api_url}</p>
</div>
"""

    return (
        "<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
        f"<title>{title}</title><style>{base_styles}</style></head><body><main>{body}</main></body></html>"
    )
