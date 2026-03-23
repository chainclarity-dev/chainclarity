"""
publish.py
生成した記事HTMLを GitHub にpushし、Buttondown API でメルマガを配信する。
あわせて articles.html の記事一覧を自動更新する。

環境変数:
  GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO, BUTTONDOWN_API_KEY
"""

import os, sys, base64, json, argparse, requests, datetime

GH_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GH_OWNER = os.environ.get("GITHUB_OWNER", "")
GH_REPO  = os.environ.get("GITHUB_REPO", "chainclarity")
GH_API   = "https://api.github.com"
BD_API_KEY = os.environ.get("BUTTONDOWN_API_KEY", "")
BD_API     = "https://api.buttondown.email/v1"


def github_push(filepath, slug):
    if not all([GH_TOKEN, GH_OWNER, GH_REPO]):
        print("⚠️  GitHub環境変数が未設定。pushをスキップします。")
        return False
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    gh_path = f"articles/{slug}.html"
    url = f"{GH_API}/repos/{GH_OWNER}/{GH_REPO}/contents/{gh_path}"
    headers = {
        "Authorization": f"Bearer {GH_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    sha = None
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        sha = resp.json().get("sha")
    today = datetime.date.today().isoformat()
    payload = {"message": f"feat: add article {slug} [{today}]", "content": encoded, "branch": "main"}
    if sha:
        payload["sha"] = sha
    resp = requests.put(url, headers=headers, json=payload)
    if resp.status_code in (200, 201):
        print(f"✅ GitHub push 完了: {gh_path}")
        return True
    print(f"❌ GitHub push 失敗: {resp.status_code} {resp.text}")
    return False


def github_update_articles_list(slug, title, description, tag, tag_class, date, read_time):
    if not all([GH_TOKEN, GH_OWNER, GH_REPO]):
        print("⚠️  GitHub環境変数が未設定。articles.html更新をスキップします。")
        return False
    url = f"{GH_API}/repos/{GH_OWNER}/{GH_REPO}/contents/articles.html"
    headers = {
        "Authorization": f"Bearer {GH_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        print(f"❌ articles.html 取得失敗: {resp.status_code}")
        return False
    sha = resp.json().get("sha")
    current = base64.b64decode(resp.json().get("content", "")).decode("utf-8")

    new_card = f"""
    <a href="/articles/{slug}.html" class="card card-new fade-in">
      <span class="card-tag {tag_class}">{tag}</span>
      <h2>{title}</h2>
      <p>{description}</p>
      <div class="card-meta"><time>{date}</time> <span>⏱ {read_time}</span></div>
    </a>
"""
    current = current.replace("card card-new fade-in", "card fade-in")
    insert_marker = '<div class="articles-grid">'
    if insert_marker not in current:
        print("❌ articles.html の挿入位置が見つかりません")
        return False
    updated = current.replace(insert_marker, insert_marker + new_card, 1)
    encoded = base64.b64encode(updated.encode("utf-8")).decode("utf-8")
    today = datetime.date.today().isoformat()
    payload = {
        "message": f"feat: update articles list with {slug} [{today}]",
        "content": encoded, "sha": sha, "branch": "main",
    }
    resp = requests.put(url, headers=headers, json=payload)
    if resp.status_code in (200, 201):
        print(f"✅ articles.html 自動更新完了")
        return True
    print(f"❌ articles.html 更新失敗: {resp.status_code} {resp.text}")
    return False


def github_update_sitemap(slug):
    """sitemap.xml に新記事URLを追加してGitHubにpushする"""
    if not all([GH_TOKEN, GH_OWNER, GH_REPO]):
        print("⚠️  GitHub環境変数が未設定。sitemap更新をスキップします。")
        return False
    url = f"{GH_API}/repos/{GH_OWNER}/{GH_REPO}/contents/sitemap.xml"
    headers = {
        "Authorization": f"Bearer {GH_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        print(f"❌ sitemap.xml 取得失敗: {resp.status_code}")
        return False
    sha = resp.json().get("sha")
    current = base64.b64decode(resp.json().get("content", "")).decode("utf-8")

    article_url = f"https://chainclarityblog.com/articles/{slug}.html"
    # すでに存在する場合はスキップ
    if article_url in current:
        print("⏭️  sitemap.xml にすでに存在します。スキップ。")
        return True

    new_entry = f"""  <url>
    <loc>{article_url}</loc>
    <changefreq>monthly</changefreq>
    <priority>0.8</priority>
  </url>
"""
    updated = current.replace("</urlset>", new_entry + "</urlset>")
    encoded = base64.b64encode(updated.encode("utf-8")).decode("utf-8")
    today = datetime.date.today().isoformat()
    payload = {
        "message": f"feat: update sitemap with {slug} [{today}]",
        "content": encoded, "sha": sha, "branch": "main",
    }
    resp = requests.put(url, headers=headers, json=payload)
    if resp.status_code in (200, 201):
        print(f"✅ sitemap.xml 自動更新完了")
        return True
    print(f"❌ sitemap.xml 更新失敗: {resp.status_code} {resp.text}")
    return False


def buttondown_send(slug, title, description, tag):
    if not BD_API_KEY:
        print("⚠️  BUTTONDOWN_API_KEY が未設定。メルマガ送信をスキップします。")
        return False
    article_url = f"https://chainclarityblog.com/articles/{slug}.html"
    email_html = f"""
<div style="font-family:Georgia,serif;max-width:600px;margin:0 auto;color:#1a1a1a;">
  <div style="background:#0a0c0f;padding:24px;border-radius:8px;margin-bottom:24px;">
    <p style="color:#00e5a0;font-size:11px;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;margin:0 0 8px;">{tag} &middot; New Article</p>
    <h1 style="color:#e8eaed;font-size:22px;font-weight:800;line-height:1.25;margin:0 0 12px;">{title}</h1>
    <p style="color:#c8ccd4;font-size:15px;line-height:1.6;margin:0;">{description}</p>
  </div>
  <p style="font-size:16px;line-height:1.7;color:#333;">A new explainer just went up on ChainClarity. No jargon, no hype.</p>
  <div style="text-align:center;margin:32px 0;">
    <a href="{article_url}" style="background:#00e5a0;color:#0a0c0f;font-weight:700;font-size:15px;padding:14px 32px;border-radius:6px;text-decoration:none;display:inline-block;">Read the Full Article &rarr;</a>
  </div>
  <hr style="border:none;border-top:1px solid #eee;margin:32px 0;">
  <p style="font-size:12px;color:#999;text-align:center;">ChainClarity &middot; Educational purposes only &middot; Not financial advice</p>
</div>
"""
    headers = {"Authorization": f"Token {BD_API_KEY}", "Content-Type": "application/json"}
    payload = {"subject": f"New: {title}", "body": email_html, "status": "about_to_send"}
    resp = requests.post(f"{BD_API}/emails", headers=headers, json=payload)
    if resp.status_code in (200, 201):
        print("✅ Buttondown メルマガ送信完了")
        return True
    print(f"❌ Buttondown 送信失敗: {resp.status_code} {resp.text}")
    return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ChainClarity 記事公開・メルマガ配信")
    parser.add_argument("--slug",          required=True)
    parser.add_argument("--title",         required=True)
    parser.add_argument("--description",   required=True)
    parser.add_argument("--tag",           required=True)
    parser.add_argument("--tag-class",     default="tag-basics")
    parser.add_argument("--date",          default=datetime.date.today().strftime("%B %Y"))
    parser.add_argument("--read-time",     default="6 min")
    parser.add_argument("--no-newsletter", action="store_true")
    args = parser.parse_args()

    filepath = f"./articles/{args.slug}.html"
    if not os.path.exists(filepath):
        print(f"❌ ファイルが見つかりません: {filepath}")
        sys.exit(1)

    github_ok  = github_push(filepath, args.slug)
    list_ok    = github_update_articles_list(
        args.slug, args.title, args.description,
        args.tag, args.tag_class, args.date, args.read_time
    )
    sitemap_ok = github_update_sitemap(args.slug)
    bd_ok = True
    if not args.no_newsletter:
        bd_ok = buttondown_send(args.slug, args.title, args.description, args.tag)
    else:
        print("⏭️  メルマガ送信スキップ")

    print("\n── 完了サマリー ──")
    print(f"  GitHub push       : {'✅' if github_ok    else '⚠️ スキップ/失敗'}")
    print(f"  articles.html更新 : {'✅' if list_ok      else '⚠️ スキップ/失敗'}")
    print(f"  sitemap.xml更新   : {'✅' if sitemap_ok   else '⚠️ スキップ/失敗'}")
    print(f"  Buttondown        : {'✅' if bd_ok         else '⚠️ スキップ/失敗'}")
