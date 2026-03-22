"""
run_all.py
記事生成 → GitHub push → articles.html自動更新 → Buttondownメルマガ配信
を一括実行する。

使い方:
  python run_all.py                        # トピックAI自動選定
  python run_all.py --topic "Bitcoin Halving explained"
  python run_all.py --topic "..." --no-newsletter  # メルマガなし

環境変数（.envファイルに書いておくか、GitHub Actions secretsに設定）:
  ANTHROPIC_API_KEY
  GITHUB_TOKEN
  GITHUB_OWNER
  GITHUB_REPO
  BUTTONDOWN_API_KEY
"""

import os
import sys
import argparse

# .envファイルがあれば読み込む
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from generate_article import generate
from publish import github_push, github_update_articles_list, buttondown_send


def run(topic=None, send_newsletter=True):
    print("=" * 50)
    print("🚀 ChainClarity 自動記事生成・公開パイプライン")
    print("=" * 50)

    # STEP 1: 記事生成
    print("\n📝 STEP 1: 記事生成")
    try:
        result = generate(topic)
    except Exception as e:
        print(f"❌ 記事生成に失敗しました: {e}")
        sys.exit(1)

    slug        = result["slug"]
    title       = result["title"]
    description = result["description"]
    tag         = result["tag"]
    tag_class   = result.get("tag_class", "tag-basics")
    filepath    = result["filepath"]

    import datetime
    date      = datetime.date.today().strftime("%B %Y")
    read_time = result.get("read_time", "6 min")

    print(f"\n  タイトル : {title}")
    print(f"  スラッグ : {slug}")
    print(f"  タグ     : {tag}")

    # STEP 2: GitHub push（記事HTML）
    print("\n📤 STEP 2: GitHub push")
    github_ok = github_push(filepath, slug)

    # STEP 3: articles.html 自動更新
    print("\n📋 STEP 3: articles.html 自動更新")
    list_ok = github_update_articles_list(
        slug, title, description, tag, tag_class, date, read_time
    )

    # STEP 4: Buttondown メルマガ配信
    if send_newsletter:
        print("\n📧 STEP 4: Buttondown メルマガ配信")
        bd_ok = buttondown_send(slug, title, description, tag)
    else:
        bd_ok = True
        print("\n📧 STEP 4: メルマガ配信スキップ")

    # 完了サマリー
    print("\n" + "=" * 50)
    print("✅ パイプライン完了")
    print("=" * 50)
    print(f"  記事タイトル      : {title}")
    print(f"  ファイル          : {filepath}")
    print(f"  GitHub push       : {'✅' if github_ok else '⚠️  環境変数未設定 / 失敗'}")
    print(f"  articles.html更新 : {'✅' if list_ok   else '⚠️  環境変数未設定 / 失敗'}")
    print(f"  メルマガ          : {'✅' if bd_ok     else '⚠️  環境変数未設定 / 失敗'}")
    print(f"\n  🌐 公開URL:")
    print(f"  https://chainclarityblog.com/articles/{slug}.html")
    print("=" * 50)

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ChainClarity 全自動パイプライン")
    parser.add_argument("--topic", type=str, default=None,
                        help="記事トピック（省略でAI自動選定）")
    parser.add_argument("--no-newsletter", action="store_true",
                        help="メルマガ配信をスキップ")
    args = parser.parse_args()

    run(
        topic=args.topic,
        send_newsletter=not args.no_newsletter,
    )
