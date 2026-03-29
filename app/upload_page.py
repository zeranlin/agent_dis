from __future__ import annotations

from html import escape


def render_upload_page(*, error_message: str | None = None) -> str:
    error_block = ""
    if error_message:
        error_block = (
            '<div class="alert">'
            f"<strong>提交未成功：</strong>{escape(error_message)}"
            "</div>"
        )

    return f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>提交招标文件</title>
  <style>
    body {{ font-family: Georgia, "Noto Serif SC", serif; margin: 0; background: linear-gradient(180deg, #efe4cf 0%, #f7f2e8 100%); color: #1f2c24; }}
    main {{ max-width: 880px; margin: 0 auto; padding: 48px 24px 80px; }}
    .hero {{ display: grid; gap: 22px; grid-template-columns: 1.15fr 0.85fr; align-items: start; }}
    .panel {{ background: rgba(255, 253, 248, 0.94); border: 1px solid #d7ccb8; border-radius: 18px; padding: 26px; box-shadow: 0 16px 32px rgba(57, 47, 31, 0.08); }}
    .eyebrow {{ color: #7a6745; font-size: 13px; letter-spacing: 0.08em; text-transform: uppercase; margin-bottom: 12px; }}
    h1, h2, h3 {{ margin: 0 0 12px; }}
    p, li {{ line-height: 1.75; }}
    .lead {{ font-size: 18px; margin-bottom: 14px; }}
    .tiny {{ color: #6d655b; font-size: 14px; }}
    .alert {{ margin-bottom: 18px; border-radius: 14px; background: #f7dddd; color: #7a1e1e; padding: 14px 16px; }}
    .upload-box {{ border: 1px dashed #9d8960; border-radius: 16px; padding: 18px; background: #f7f2e8; }}
    label {{ display: block; margin-bottom: 8px; font-weight: 700; }}
    input[type=file] {{ width: 100%; padding: 10px 0; }}
    button {{ border: 0; border-radius: 999px; background: #214d38; color: #fffdf8; padding: 12px 18px; font-size: 15px; font-weight: 700; cursor: pointer; }}
    .list {{ margin: 0; padding-left: 18px; }}
    .meta-card {{ background: #f2ebdd; border-radius: 14px; padding: 16px; }}
    @media (max-width: 720px) {{ .hero {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <main>
    <div class="hero">
      <section class="panel">
        <div class="eyebrow">上传页</div>
        <h1>提交待审查招标文件</h1>
        <p class="lead">当前版本支持审核人员直接上传 1 份招标文件，系统会自动进入审查，并在结果生成后进入结果页。</p>
        {error_block}
        <form action="/review-tasks/upload" method="post" enctype="multipart/form-data">
          <div class="upload-box">
            <label for="file">选择文件</label>
            <input id="file" name="file" type="file" accept=".pdf,.doc,.docx" required>
            <p class="tiny">支持格式：PDF / Word。当前一次只支持提交 1 份文件。</p>
          </div>
          <div style="margin-top: 18px;">
            <button type="submit">开始审核</button>
          </div>
        </form>
      </section>
      <aside class="panel">
        <div class="eyebrow">提交说明</div>
        <div class="meta-card">
          <h3>这次会发生什么</h3>
          <ol class="list">
            <li>文件上传进入系统</li>
            <li>页面进入等待审查状态</li>
            <li>结果生成后自动进入结果页</li>
          </ol>
        </div>
        <div class="meta-card" style="margin-top: 14px;">
          <h3>当前不做</h3>
          <ul class="list">
            <li>多文件联审</li>
            <li>OCR 扫描件识别</li>
            <li>复杂工作台和任务列表</li>
          </ul>
        </div>
      </aside>
    </div>
  </main>
</body>
</html>
"""


def render_waiting_page(
    *,
    task_id: str,
    file_name: str,
    status_message: str,
    status_api_url: str,
    result_page_url: str,
) -> str:
    safe_task_id = escape(task_id)
    safe_file_name = escape(file_name)
    safe_status_message = escape(status_message)
    safe_status_api_url = escape(status_api_url)
    safe_result_page_url = escape(result_page_url)
    return f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>等待审查</title>
  <meta http-equiv="refresh" content="2;url=/review-tasks/{safe_task_id}/waiting">
  <style>
    body {{ font-family: Georgia, "Noto Serif SC", serif; margin: 0; background: #f6f1e8; color: #1e2a23; }}
    main {{ max-width: 760px; margin: 0 auto; padding: 54px 24px 80px; }}
    .panel {{ background: #fffdf8; border: 1px solid #d8cfbd; border-radius: 18px; padding: 26px; box-shadow: 0 14px 28px rgba(49, 43, 31, 0.08); }}
    .eyebrow {{ color: #7f6a46; font-size: 13px; letter-spacing: 0.08em; text-transform: uppercase; margin-bottom: 12px; }}
    .status {{ display: inline-block; padding: 6px 12px; border-radius: 999px; background: #f7e6b8; color: #6a4b00; font-size: 13px; margin-bottom: 16px; }}
    .tiny {{ color: #6d655b; font-size: 14px; line-height: 1.75; }}
    .actions a {{ display: inline-block; margin-right: 12px; margin-top: 12px; color: #1b4d74; text-decoration: none; font-weight: 700; }}
  </style>
  <script>
    async function pollStatus() {{
      try {{
        const response = await fetch("{safe_status_api_url}", {{ headers: {{ "Accept": "application/json" }} }});
        if (!response.ok) return;
        const payload = await response.json();
        if (payload.status === "completed" || payload.status === "failed") {{
          window.location.href = "{safe_result_page_url}";
        }}
      }} catch (_error) {{
      }}
    }}
    window.addEventListener("load", () => {{
      pollStatus();
      window.setInterval(pollStatus, 2000);
    }});
  </script>
</head>
<body>
  <main>
    <div class="panel">
      <div class="eyebrow">等待页</div>
      <div class="status">等待审查</div>
      <h1>系统正在自动审核，请稍候</h1>
      <p class="tiny">文件：{safe_file_name}</p>
      <p>{safe_status_message}</p>
      <p class="tiny">当前页面会自动检查状态，并在审查完成后进入结果页。</p>
      <div class="actions">
        <a href="{safe_status_api_url}">查看状态接口</a>
        <a href="{safe_result_page_url}">直接查看结果页</a>
      </div>
    </div>
  </main>
</body>
</html>
"""
