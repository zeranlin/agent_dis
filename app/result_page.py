from __future__ import annotations

from html import escape


def render_result_page(payload: dict[str, object]) -> str:
    page_state = str(payload["page_state"])
    title = escape(str(payload.get("summary_title", payload["title"])))
    file_name = escape(str(payload["file_name"]))
    message = escape(str(payload.get("overall_conclusion", payload["message"])))
    page_guidance = escape(str(payload.get("page_guidance", "")))
    primary_actions = payload.get("primary_actions", [])
    support_notes = payload.get("support_notes", [])

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
.download-list { display: grid; gap: 12px; }
.download-item { background: #f7f2e9; border-radius: 12px; padding: 14px; }
.split { display: grid; grid-template-columns: 1.2fr 0.8fr; gap: 16px; margin-top: 24px; }
.note { background: #f0e8da; border-radius: 14px; padding: 16px; line-height: 1.7; }
.tiny { color: #6d655b; font-size: 14px; }
.lead { font-size: 18px; margin-bottom: 8px; }
.section { margin-top: 22px; }
.actions { margin-top: 14px; display: flex; flex-wrap: wrap; gap: 10px; }
.buttonish { display: inline-block; padding: 10px 14px; border-radius: 999px; background: #214d38; color: #fffdf8; text-decoration: none; font-weight: 600; }
.risk-item { margin-bottom: 12px; }
@media (max-width: 720px) { .split { grid-template-columns: 1fr; } }
"""

    status_html = f'<div class="status {escape(page_state)}">{escape(str(payload["status_label"]))}</div>'
    actions_html = "".join(
        f'<a class="buttonish" href="{escape(str(item["url"]))}">{escape(str(item["label"]))}</a>'
        for item in primary_actions
    )
    support_notes_html = "".join(
        "<div class=\"note\" style=\"margin-top: 16px;\">"
        f"<h3>{escape(str(item['title']))}</h3>"
        f"<p class=\"tiny\">{escape(str(item['body']))}</p>"
        "</div>"
        for item in support_notes
    )

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
            "<li class=\"risk-item\">"
            f"<strong>{escape(str(item['risk_title']))}</strong> | {escape(str(item['risk_level']))}<br>"
            f"<span class=\"tiny\">归并命中数：{escape(str(item.get('merged_hit_count') or 1))}</span><br>"
            f"<span class=\"tiny\">章节上下文：{escape(str(item.get('chapter_title') or '未标注'))}</span><br>"
            f"<span class=\"tiny\">业务单元：{escape(str(item.get('unit_label') or '未标注'))}</span><br>"
            f"<span class=\"tiny\">片段类型：{escape(str(item.get('clause_type') or '未标注'))}</span><br>"
            f"<span class=\"tiny\">命中位置：{escape(str(item['location_label']))}</span><br>"
            f"{escape(str(item['risk_description']))}<br>"
            f"<span class=\"tiny\">审查说明：{escape(str(item.get('review_reasoning') or '无'))}</span>"
            "</li>"
            for item in top_risks
        ) or "<li>当前未识别到明显风险。</li>"
        download_links_html = "".join(
            "<div class=\"download-item\">"
            f"<a class=\"buttonish\" href=\"{escape(str(item['url']))}\">{escape(str(item.get('label') or item['name']))}</a>"
            f"<p class=\"tiny\">文件名称：{escape(str(item['name']))}</p>"
            f"<p class=\"tiny\">文件类型：{escape(str(item.get('type') or '未知'))}</p>"
            f"<p class=\"tiny\">{escape(str(item.get('description') or ''))}</p>"
            "</div>"
            for item in downloadables
        )
        body = f"""
<div class="panel">
  <div class="eyebrow">结果查看页</div>
  {status_html}
  <h1>{title}</h1>
  <p class="meta">文件：{file_name}</p>
  <p class="lead">{message}</p>
  <p class="tiny">结果生成时间：{generated_at}。当前统计优先展示归并后的风险组数量，建议先浏览风险组概览，再查看详细结论。</p>
  <div class="grid">
    <div class="card"><h3>高风险组</h3><p>{escape(str(risk_count_summary["high"]))}</p></div>
    <div class="card"><h3>中风险组</h3><p>{escape(str(risk_count_summary["medium"]))}</p></div>
    <div class="card"><h3>低风险组</h3><p>{escape(str(risk_count_summary["low"]))}</p></div>
  </div>
  <div class="split">
    <div>
      <div class="section">
      <h2>建议先这样看</h2>
      <p class="tiny">{page_guidance}</p>
      </div>
      <div class="section">
      <h2>优先关注的风险组</h2>
      <ul>{risk_items_html}</ul>
      </div>
      <div class="section">
      <h2>最终结论</h2>
      <pre>{conclusion_markdown}</pre>
      </div>
      <div class="section">
      <h2>审查报告</h2>
      <pre>{report_markdown}</pre>
      </div>
    </div>
    <div>
      <div class="note">
        <h3>快速操作</h3>
        <div class="download-list">{download_links_html}</div>
        <div class="actions">{actions_html}</div>
        <p class="tiny">页面地址：{page_url}</p>
        <p class="tiny">状态接口：{status_api_url}</p>
        <p class="tiny">结果接口：{result_api_url}</p>
      </div>
      {support_notes_html}
    </div>
  </div>
</div>
"""
    elif page_state == "failed":
        error_code = escape(str(payload.get("error_code") or "UNKNOWN"))
        status_api_url = escape(str(payload["status_api_url"]))
        page_url = escape(str(payload["page_url"]))
        body = f"""
<div class="panel">
  <div class="eyebrow">结果查看页</div>
  {status_html}
  <h1>{title}</h1>
  <p class="meta">文件：{file_name}</p>
  <p class="lead">{message}</p>
  <p>错误码：{error_code}</p>
  <p>建议：{page_guidance}</p>
  <div class="actions">{actions_html}</div>
  <p class="tiny">你也可以先查看状态接口，再决定是否重新提交文件：{status_api_url}</p>
  {support_notes_html}
</div>
"""
    else:
        status_api_url = escape(str(payload["status_api_url"]))
        result_api_url = escape(str(payload["result_api_url"]))
        page_url = escape(str(payload["page_url"]))
        body = f"""
<div class="panel">
  <div class="eyebrow">结果查看页</div>
  {status_html}
  <h1>{title}</h1>
  <p class="meta">文件：{file_name}</p>
  <p class="lead">{message}</p>
  <p>{page_guidance}</p>
  <div class="actions">{actions_html}</div>
  <p class="tiny">如果你在联调或排查问题，可继续查看状态接口：{status_api_url}</p>
  <p class="tiny">结果生成后，可从这里直接查看结果接口：{result_api_url}</p>
  {support_notes_html}
</div>
"""

    return (
        "<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
        f"<title>{title}</title><style>{base_styles}</style></head><body><main>{body}</main></body></html>"
    )


def render_missing_page() -> str:
    return """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>结果页不存在</title>
  <style>
    body { font-family: Georgia, "Noto Serif SC", serif; margin: 0; background: #f6f1e8; color: #1e2a23; }
    main { max-width: 760px; margin: 0 auto; padding: 48px 24px 80px; }
    .panel { background: #fffdf8; border: 1px solid #d8cfbd; border-radius: 16px; padding: 24px; box-shadow: 0 12px 30px rgba(49, 43, 31, 0.08); }
    .eyebrow { color: #7f6a46; font-size: 13px; letter-spacing: 0.08em; text-transform: uppercase; margin-bottom: 12px; }
    .tiny { color: #6d655b; font-size: 14px; line-height: 1.7; }
  </style>
</head>
<body>
  <main>
    <div class="panel">
      <div class="eyebrow">结果查看页</div>
      <h1>未找到可查看的结果页</h1>
      <p class="tiny">请先确认任务标识是否正确，或回到上传入口重新提交文件。</p>
      <p class="tiny">如果你在联调，可先检查任务是否已经创建并进入可查看状态。</p>
    </div>
  </main>
</body>
</html>
"""
