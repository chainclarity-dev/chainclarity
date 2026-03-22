"""
generate_article.py
Claude API を使って ChainClarity 用の記事 HTML を自動生成する。

改善点:
  1. web_search ツールでリアルタイム情報を取得
  2. 既存記事スラッグを渡して重複トピックを防止

使い方:
  python generate_article.py --topic "What is a Bitcoin Halving?"
  python generate_article.py  # トピックを省略するとAIが自動選定
"""

import os
import re
import json
import argparse
import datetime
import anthropic

# ── 設定 ────────────────────────────────────────────────
ARTICLES_DIR = "./articles"          # 生成したHTMLを保存するフォルダ
MODEL        = "claude-sonnet-4-6"   # 使用モデル
MAX_TOKENS   = 8000

# 著者ボックス HTML（全記事共通）
AUTHOR_BOX = """
  <!-- AUTHOR BOX (E-E-A-T) -->
  <div class="author-box">
    <div class="author-avatar">
      <svg width="48" height="48" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="24" cy="24" r="24" fill="url(#ag)"/>
        <ellipse cx="24" cy="35" rx="10" ry="6" fill="rgba(0,229,160,0.15)"/>
        <circle cx="24" cy="18" r="8" fill="rgba(0,229,160,0.2)"/>
        <circle cx="21" cy="17" r="1.2" fill="rgba(0,229,160,0.8)"/>
        <circle cx="27" cy="17" r="1.2" fill="rgba(0,229,160,0.8)"/>
        <path d="M21 21 Q24 23.5 27 21" stroke="rgba(0,229,160,0.8)" stroke-width="1.2" fill="none" stroke-linecap="round"/>
        <defs><radialGradient id="ag" cx="40%" cy="35%" r="65%"><stop offset="0%" stop-color="#0d2b20"/><stop offset="100%" stop-color="#080f18"/></radialGradient></defs>
      </svg>
    </div>
    <div class="author-info">
      <div class="author-name-line">
        <a href="/author.html" class="author-name">Marcus Webb</a>
        <span class="author-credential">Fintech Engineer · Crypto Researcher since 2017</span>
      </div>
      <p class="author-bio">Marcus spent nearly a decade building payment infrastructure at fintech companies. He writes plain-English explainers focused on accuracy and honest risk disclosure.</p>
      <div class="author-meta-line">
        <span>✓ Reviewed for accuracy</span>
        <span>·</span>
        <a href="/author.html">Full bio →</a>
      </div>
    </div>
  </div>
"""

# ── プロンプト ────────────────────────────────────────────
SYSTEM_PROMPT = """You are Marcus Webb, a fintech engineer and independent crypto researcher writing for ChainClarity, an educational blog for everyday Americans.

WRITING RULES:
- Plain English only. No jargon without explanation.
- Beginner-friendly but not condescending.
- Always include real risks alongside opportunities.
- Never give financial advice or tell readers to buy anything.
- Accurate, fact-based, balanced tone.
- Use web_search to find the latest information, recent news, and accurate statistics before writing. Always search first.

OUTPUT FORMAT — respond with a single JSON object:
{
  "title": "Article title",
  "slug": "url-friendly-slug",
  "tag": "Stablecoins|Bitcoin|DeFi|RWA|Regulation|Basics",
  "tag_class": "tag-stablecoin|tag-bitcoin|tag-defi|tag-rwa|tag-regulation|tag-basics",
  "description": "Meta description (120-155 chars)",
  "read_time": "5 min",
  "date": "March 2026",
  "date_iso": "2026-03-22",
  "key_takeaways": ["takeaway1", "takeaway2", "takeaway3", "takeaway4"],
  "sections": [
    {
      "id": "anchor-id",
      "heading": "Section heading",
      "content": "HTML content using <p>, <strong>, <ul><li>, <table class='compare-table'>, <div class='callout'> as needed"
    }
  ],
  "toc": [{"anchor": "id", "label": "TOC label"}],
  "related": [
    {"url": "/articles/what-is-a-stablecoin.html", "tag": "Stablecoins", "tag_color": "var(--accent)", "title": "What Is a Stablecoin?"},
    {"url": "/articles/bitcoin-etf-explained.html", "tag": "Bitcoin", "tag_color": "var(--accent3)", "title": "Bitcoin ETFs Explained"}
  ]
}

IMPORTANT: Return ONLY the JSON object. No markdown fences, no preamble, no explanation text before or after the JSON.
"""

def get_existing_slugs() -> list[str]:
    """articles/ フォルダの既存スラッグ一覧を取得する"""
    if not os.path.exists(ARTICLES_DIR):
        return []
    slugs = []
    for fname in os.listdir(ARTICLES_DIR):
        if fname.endswith(".html"):
            slugs.append(fname.replace(".html", ""))
    return slugs


def build_topic_picker_prompt(existing_slugs: list[str]) -> str:
    """既存スラッグを含めたトピック選定プロンプトを生成する"""
    existing_str = "\n".join(f"- {s}" for s in existing_slugs) if existing_slugs else "（なし）"
    return f"""You are a crypto content strategist for a US-focused educational blog called ChainClarity.
Today's date is {datetime.date.today().strftime('%B %d, %Y')}.

Use web_search to find what crypto topics are trending RIGHT NOW among US retail investors before suggesting a topic.

The following articles have ALREADY been published — do NOT suggest similar topics:
{existing_str}

Suggest ONE high-interest, SEO-friendly article topic for 2026 that:
- Is relevant to US retail investors
- Is currently trending or newsworthy (use web search to verify)
- Has NOT already been covered (see list above)
- Fits one of these categories: Stablecoins, Bitcoin, DeFi, RWA, Regulation, Basics

Respond with ONLY a plain topic sentence. Example: "What Is a Crypto Wallet and How Do You Keep It Safe?"
"""


# ── HTML テンプレート ─────────────────────────────────────
def build_html(data: dict, author_box: str) -> str:
    kp_items = "\n".join(f"        <li>{t}</li>" for t in data["key_takeaways"])

    sections_html = ""
    for sec in data["sections"]:
        sections_html += f'\n      <h2 id="{sec["id"]}">{sec["heading"]}</h2>\n      {sec["content"]}\n'

    toc_items = "\n".join(
        f'      <li><a href="#{t["anchor"]}">{t["label"]}</a></li>'
        for t in data["toc"]
    )

    related_html = ""
    for r in data["related"]:
        related_html += f"""
      <a href="{r['url']}" class="related-link">
        <div class="r-tag" style="color:{r['tag_color']}">{r['tag']}</div>
        <div class="r-title">{r['title']}</div>
      </a>"""

    schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": data["title"],
        "description": data["description"],
        "datePublished": data["date_iso"],
        "dateModified": data["date_iso"],
        "author": {
            "@type": "Person",
            "name": "Marcus Webb",
            "url": "https://chainclarityblog.com/author.html"
        },
        "publisher": {
            "@type": "Organization",
            "name": "ChainClarity",
            "url": "https://chainclarityblog.com"
        },
        "mainEntityOfPage": {
            "@type": "WebPage",
            "@id": f"https://chainclarityblog.com/articles/{data['slug']}.html"
        }
    }, indent=2)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{data['title']} — ChainClarity</title>
<meta name="description" content="{data['description']}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:ital,wght@0,300;0,400;0,500;1,300&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/style.css">
<script type="application/ld+json">
{schema}
</script>
</head>
<body>
<nav>
  <a href="/" class="logo">Chain<span>Clarity</span></a>
  <ul>
    <li><a href="/articles.html">Articles</a></li>
    <li><a href="/#topics">Topics</a></li>
    <li><a href="/#newsletter">Newsletter</a></li>
  </ul>
</nav>

<div class="article-wrap">
<article>
  <header>
    <p class="breadcrumb"><a href="/">Home</a> / <a href="/articles.html">Articles</a> / {data['tag']}</p>
    <span class="card-tag {data['tag_class']}">{data['tag']}</span>
    <h1 class="article-title">{data['title']}</h1>
    <div class="article-meta">
      <span>{data['date']}</span><span class="dot"></span>
      <span>{data['read_time']} read</span><span class="dot"></span>
      <span>Beginner</span>
    </div>
  </header>

  <div class="article-body">
{author_box}
    <div class="key-points">
      <h4>Key Takeaways</h4>
      <ul>
{kp_items}
      </ul>
    </div>
{sections_html}
    <div class="disclaimer"><strong>Disclaimer:</strong> This article is for educational purposes only and does not constitute financial, investment, or legal advice. Cryptocurrency assets carry risk. Always do your own research before making financial decisions.</div>
  </div>
</article>

<aside class="sidebar">
  <div class="sidebar-card">
    <h4>In This Article</h4>
    <ul class="toc-list">
{toc_items}
    </ul>
  </div>
  <div class="sidebar-card">
    <h4>Related Articles</h4>
{related_html}
  </div>
  <div class="sidebar-card nl-sidebar" style="background:rgba(0,229,160,0.04);border-color:rgba(0,229,160,0.15);">
    <h4 style="color:var(--accent)">Newsletter</h4>
    <p>Get clear crypto explainers in your inbox. No spam.</p>
    <input type="email" placeholder="your@email.com">
    <button>Subscribe</button>
  </div>
</aside>
</div>

<footer class="site-footer">
  <a href="/" class="logo">Chain<span>Clarity</span></a>
  <ul class="footer-links">
    <li><a href="/articles.html">Articles</a></li>
    <li><a href="/about.html">About</a></li>
    <li><a href="/privacy.html">Privacy</a></li>
    <li><a href="/disclaimer.html">Disclaimer</a></li>
  </ul>
  <p class="footer-copy">© 2026 ChainClarity. For educational purposes only. Not financial advice.</p>
</footer>
</body>
</html>"""


# ── web_search ツール定義 ─────────────────────────────────
WEB_SEARCH_TOOL = {
    "type": "web_search_20250305",
    "name": "web_search"
}


def run_with_tool_loop(client, model, max_tokens, system, messages):
    """web_search はAnthropicサーバーサイドで処理される。
    stop_reason が end_turn になるまでループする。"""
    for _ in range(15):
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            tools=[WEB_SEARCH_TOOL],
            messages=messages,
        )

        # end_turn で完了
        if resp.stop_reason == "end_turn":
            texts = [b.text for b in resp.content if hasattr(b, "text") and b.type == "text"]
            return "\n".join(texts).strip()

        # tool_use の場合、レスポンス全体をassistantとして追加
        # web_search の tool_result はAPIが自動生成するため
        # content ブロックをそのままシリアライズして次のリクエストに渡す
        assistant_content = []
        has_tool_use = False
        for b in resp.content:
            if b.type == "text":
                assistant_content.append({"type": "text", "text": b.text})
            elif b.type == "tool_use":
                has_tool_use = True
                assistant_content.append({
                    "type": "tool_use",
                    "id": b.id,
                    "name": b.name,
                    "input": b.input,
                })
            elif b.type == "tool_result":
                # tool_result がすでに含まれている場合はそのまま追加
                result_content = []
                if hasattr(b, "content") and b.content:
                    for c in b.content:
                        if hasattr(c, "text"):
                            result_content.append({"type": "text", "text": c.text})
                assistant_content.append({
                    "type": "tool_result",
                    "tool_use_id": b.tool_use_id if hasattr(b, "tool_use_id") else "",
                    "content": result_content,
                })

        if not has_tool_use:
            # tool_use がないのに end_turn でもない場合は終了
            texts = [b["text"] for b in assistant_content if b.get("type") == "text"]
            return "\n".join(texts).strip()

        messages = messages + [{"role": "assistant", "content": assistant_content}]

    raise RuntimeError("tool loop の最大反復回数に達しました")


def extract_json(text: str) -> dict:
    """テキストからJSONオブジェクトを抽出してパースする"""
    # ```json フェンス除去
    text = re.sub(r"^```json\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    # 先頭の { を探してJSONを切り出す
    start = text.find("{")
    if start == -1:
        raise ValueError(f"JSONが見つかりません。受信テキスト:\n{text[:500]}")
    end = text.rfind("}")
    if end == -1:
        raise ValueError(f"JSONの終端が見つかりません。受信テキスト:\n{text[:500]}")

    json_str = text[start:end+1]

    # まずそのままパース試行
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass

    # 失敗した場合：不正な制御文字を除去して再試行
    # タブ(0x09)・改行(0x0a)・復帰(0x0d)は保持し、それ以外の制御文字を除去
    cleaned = re.sub(r'(?<!\\)[\x00-\x08\x0b\x0c\x0e-\x1f]', '', json_str)
    return json.loads(cleaned)


# ── メイン処理 ────────────────────────────────────────────
def generate(topic: str | None = None) -> dict:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    # 既存スラッグを取得
    existing_slugs = get_existing_slugs()
    print(f"📚 既存記事数: {len(existing_slugs)}")

    # トピック未指定ならAIに選ばせる（重複チェック付き・web検索あり）
    if not topic:
        print("🔍 最新トレンドを検索してトピックを自動選定中...")
        topic_prompt = build_topic_picker_prompt(existing_slugs)
        topic = run_with_tool_loop(
            client=client,
            model=MODEL,
            max_tokens=1000,
            system="You are a crypto content strategist. Always use web_search to check current trends before suggesting a topic. Reply with ONLY the topic sentence, nothing else.",
            messages=[{"role": "user", "content": topic_prompt}],
        )
        # 複数行返ってきた場合は最後の行を使う
        topic = [line.strip() for line in topic.splitlines() if line.strip()][-1]
        print(f"📌 選定トピック: {topic}")

    # STEP 1: web検索で最新情報を収集
    print(f"🔍 最新情報を検索中: {topic}")
    today = datetime.date.today()
    research_prompt = f"""Search for the latest news, statistics, and regulatory updates about: {topic}

Today's date: {today.strftime('%B %d, %Y')}

Use web_search to find:
1. Recent news (last 3 months) about this topic
2. Key statistics or data points
3. Any regulatory changes or developments in the US

Summarize the key findings in plain text. Do NOT write the article yet — just summarize what you found."""

    research = run_with_tool_loop(
        client=client,
        model=MODEL,
        max_tokens=2000,
        system="You are a crypto researcher. Use web_search to find current information and summarize your findings clearly.",
        messages=[{"role": "user", "content": research_prompt}],
    )
    print(f"📋 リサーチ完了（{len(research)}文字）")

    # STEP 2: リサーチ結果を使ってJSON記事を生成（web検索なし）
    print(f"✍️  記事生成中...")
    article_prompt = f"""Write a ChainClarity article about: {topic}

Today's date: {today.strftime('%B %d, %Y')}
Target audience: Everyday Americans curious about crypto, not experts.
Length: Aim for 5-7 sections, approximately 800-1000 words total content.

RESEARCH FINDINGS (use this information in the article):
{research}

Already published slugs (do NOT reuse or create similar content):
{chr(10).join(f'- {s}' for s in existing_slugs)}

Return ONLY a valid JSON object. No markdown, no preamble, no text before or after the JSON.
All string values in the JSON must be properly escaped (use HTML entities for quotes in HTML content).
Do not use raw double quotes inside JSON string values — use &quot; instead."""

    resp = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": article_prompt}],
    )
    raw = resp.content[0].text.strip()

    # JSON パース
    data = extract_json(raw)

    # 重複スラッグチェック
    if data["slug"] in existing_slugs:
        raise ValueError(f"重複スラッグが生成されました: {data['slug']} — 再実行してください")

    # HTML生成
    html = build_html(data, AUTHOR_BOX)

    # ファイル保存
    os.makedirs(ARTICLES_DIR, exist_ok=True)
    filepath = os.path.join(ARTICLES_DIR, f"{data['slug']}.html")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ 生成完了: {filepath}")
    return {
        "slug": data["slug"],
        "title": data["title"],
        "description": data["description"],
        "tag": data["tag"],
        "filepath": filepath,
        "topic": topic,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ChainClarity 記事自動生成")
    parser.add_argument("--topic", type=str, default=None, help="記事トピック（省略でAI自動選定）")
    args = parser.parse_args()
    result = generate(args.topic)
    print(json.dumps(result, ensure_ascii=False, indent=2))
