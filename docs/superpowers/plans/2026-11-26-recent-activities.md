# Recent Activities の復活 実装手順

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** トップページに、Booklog と GitHub の最近の活動を新しい順に 10 件並べた「Recent Activities」を戻す。

**Architecture:** cron で動く Python スクリプトがフィードを取得して `activities.json` を書き出し、`public_html/js/recent-activities.js` がそれを読んで一覧を作る。先にリポジトリの中身を `public_html/` に一段下げ、`tools/` と `docs/` を Web に出ないルートに置く。

**Tech Stack:** Python 3（標準ライブラリのみ：`urllib`、`xml.etree.ElementTree`、`email.utils`、`unittest`）、素の JavaScript（ES5 の書き方、既存の `js/copyright-year.js` に合わせる）。

**Spec:** `docs/superpowers/specs/2026-11-26-recent-activities-design.md`

## Global Constraints

- Python は 3.8 以上で動くこと。追加ライブラリは入れない。
- インラインスクリプトは使わない（本番の CSP は `script-src 'self'`）。jQuery は使わない。
- 表示は 10 件、「サービス名 - タイトル [yyyy/mm/dd hh:mm]」の形。
- 作業は `recent-activities` ブランチで行う。master に直接コミットしない。
- コミットメッセージは日本語で、既存の履歴に合わせて句点で終える。末尾に
  `Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>` を付ける。
- コメントや画面に出る文言は日本語。

## Review Focus

仕様には書かれていないが実際に起こりそうな入力。それぞれ担当タスクのテストに入れてある。

1. 日時がない、または読めない項目 → その項目だけ捨て、フィード全体は失敗にしない（Task 2）。
2. フィードの URL が 200 で HTML やエラーページを返す → 失敗として扱い、前回の項目を引き継ぐ（Task 2、3）。
3. 前回の JSON がない、または壊れている → 前回の項目は 0 件として続行する（Task 3）。
4. タイトルに改行や連続した空白、前後の空白がある → 1 つの空白にまとめる。空のタイトルの項目は捨てる（Task 2）。
5. タイムゾーンのない日時 → UTC とみなす（Task 2）。

---

### Task 1: 中身を `public_html/` に移す

**Files:**
- Move: ルート直下の `index.html` `result.html` `main.css` `favicon.ico` `robots.txt` `css/` `js/` `images/` → `public_html/`
- Create: `.gitignore`

- [ ] **Step 1: ブランチを作り、設計書と手順書をコミットする**

```bash
git switch -c recent-activities
git add docs
git commit -m "Recent Activities復活の設計書と実装手順を追加。"
```

- [ ] **Step 2: `git mv` で移動する**

```bash
mkdir public_html
git mv index.html result.html main.css favicon.ico robots.txt css js images public_html/
```

- [ ] **Step 3: `.gitignore` を作る**

内容は 2 行：`public_html/activities.json` と `__pycache__/`。

- [ ] **Step 4: 確認する**

Run: `git status --short | grep -v '^R ' ; ls`
Expected: `.gitignore` の追加だけが出る（移動はすべて `R`）。ルートに残るのは `docs` `public_html` と `.gitignore`。

Run: `grep -rn 'href="/\|src="/' public_html/*.html`
Expected: `result.html` の `href="/"`（Home へのリンク）だけ。ほかに絶対パスの参照がないこと。

- [ ] **Step 5: コミットする**

```bash
git add .gitignore
git commit -m "公開するファイルをpublic_html/に移動。"
```

---

### Task 2: フィードを読む（`parse_date` と `parse_feed`）

**Files:**
- Create: `tools/fetch_activities.py`
- Test: `tools/test_fetch_activities.py`

**Interfaces:**
- Produces:
  - `parse_date(text: str) -> datetime | None` … RFC 822（RSS の `pubDate`）と ISO 8601（Atom の `updated`、RSS 1.0 の `dc:date`）を読み、タイムゾーン付きの UTC の `datetime` を返す。読めなければ `None`。
  - `parse_feed(data: bytes) -> list[dict]` … 各要素は `{"title": str, "url": str, "published": "YYYY-MM-DDTHH:MM:SSZ"}`。フィードとして読めないときは `ValueError`。

- [ ] **Step 1: 失敗するテストを書く**

`tools/test_fetch_activities.py` に `unittest.TestCase` で書く。サンプル XML はテストファイル内の bytes 定数にする（RSS 2.0、Atom、RSS 1.0 を 1 つずつ。Atom は GitHub と同じく `<link rel="alternate" href="…"/>` と `<updated>` を持つ形）。

```python
class ParseDateTest(unittest.TestCase):
    def test_rfc822(self):
        self.assertEqual(parse_date("Wed, 25 Nov 2026 23:10:00 +0900"),
                         datetime(2026, 11, 25, 14, 10, tzinfo=timezone.utc))
    def test_iso8601_z(self):
        self.assertEqual(parse_date("2026-11-25T14:10:00Z"),
                         datetime(2026, 11, 25, 14, 10, tzinfo=timezone.utc))
    def test_naive_is_utc(self):
        self.assertEqual(parse_date("2026-11-25T14:10:00"),
                         datetime(2026, 11, 25, 14, 10, tzinfo=timezone.utc))
    def test_garbage(self):
        self.assertIsNone(parse_date("yesterday"))
        self.assertIsNone(parse_date(""))

class ParseFeedTest(unittest.TestCase):
    def test_rss2(self):
        self.assertEqual(parse_feed(RSS2), [
            {"title": "本のタイトル", "url": "https://booklog.jp/item/1/1",
             "published": "2026-11-20T12:03:00Z"}])
    def test_atom(self):      # <link rel="alternate" href> と <updated> を使う
        self.assertEqual(parse_feed(ATOM)[0], {
            "title": "daemonfreaks pushed to master",
            "url": "https://github.com/daemonfreaks/x/compare/a...b",
            "published": "2026-11-25T14:10:00Z"})
    def test_rss1(self):      # rdf:RDF の item と dc:date
        self.assertEqual(parse_feed(RSS1)[0]["published"], "2026-11-01T00:00:00Z")
    def test_title_whitespace_collapsed(self):   # "  a\n   b  " → "a b"
    def test_item_without_date_dropped(self):    # 残りの項目は返る
    def test_item_with_empty_title_dropped(self):
    def test_item_with_non_http_link_dropped(self):  # javascript:… や相対パス
    def test_html_is_error(self):
        with self.assertRaises(ValueError):
            parse_feed(b"<html><body>Service Unavailable</body></html>")
    def test_broken_xml_is_error(self):
        with self.assertRaises(ValueError):
            parse_feed(b"<rss><channel>")
```

コメントだけの 4 つも、コメントの内容どおりの入力と検証を書く。

- [ ] **Step 2: 失敗を確認する**

Run: `python3 -m unittest discover -s tools -v`
Expected: `ImportError`（`fetch_activities` がない）

- [ ] **Step 3: `parse_date` と `parse_feed` を実装する**

- ルート要素のタグ名（名前空間を除いた部分）で `rss` / `feed` / `RDF` を見分け、それ以外は `ValueError`。`ET.ParseError` も `ValueError` に変える。
- 要素の検索は名前空間を無視してローカル名で行う（RSS 1.0 と Atom は名前空間付きのため）。
- Atom のリンクは `rel` が `alternate` か未指定の `link` の `href`。日時は `published`、なければ `updated`。
- RSS の日時は `pubDate`、なければ `date`（`dc:date`）。
- ISO 8601 の末尾の `Z` は `+00:00` に置き換えてから `datetime.fromisoformat` に渡す（3.8 は `Z` を読めない）。

- [ ] **Step 4: 成功を確認する**

Run: `python3 -m unittest discover -s tools -v`
Expected: すべて `ok`

- [ ] **Step 5: コミットする**

```bash
git add tools
git commit -m "RSSとAtomから項目を取り出す処理を追加。"
```

---

### Task 3: 取得して混ぜ、JSON を書き出す

**Files:**
- Modify: `tools/fetch_activities.py`
- Test: `tools/test_fetch_activities.py`

**Interfaces:**
- Consumes: Task 2 の `parse_feed(data: bytes) -> list[dict]`
- Produces:
  - 定数 `MAX_ITEMS = 10`、`FEEDS`（下記）
  - `fetch_url(url: str) -> bytes` … `urllib.request` で取得。タイムアウト 20 秒、User-Agent は `daemonfreaks.com-activities/1.0`。
  - `load_previous(path: str) -> list[dict]` … 前回の JSON の `items`。ファイルがない、壊れている、形が違うときは `[]`。
  - `collect(feeds, previous, fetch=fetch_url) -> tuple[list[dict], list[str]]` … 戻り値は（新しい順の上位 `MAX_ITEMS` 件、失敗したフィードの表示名の一覧）。項目は `{"source", "source_url", "title", "url", "published"}`。
  - `write_json(path: str, items: list[dict], now: datetime) -> None`
  - `main(argv: list[str]) -> int` … `argv[1]` が出力先。成功 0、失敗したフィードがあれば 1、引数の誤りは 2。
  - 出力する JSON：`{"generated": "YYYY-MM-DDTHH:MM:SSZ", "items": [...]}`（Task 4 が読む）

```python
FEEDS = [
    {"source": "Booklog", "feed_url": "https://booklog.jp/users/daemonfreaks/feed",
     "source_url": "https://booklog.jp/users/daemonfreaks"},
    {"source": "GitHub", "feed_url": "https://github.com/daemonfreaks.atom",
     "source_url": "https://github.com/daemonfreaks"},
]
```

- [ ] **Step 1: 失敗するテストを書く**

`fetch` には URL を受けて bytes を返す（または例外を投げる）偽の関数を渡す。出力先は `tempfile.TemporaryDirectory` の中。

```python
class CollectTest(unittest.TestCase):
    def test_merged_newest_first(self):
        # 2 つのフィードの項目が published の降順に混ざり、source と source_url が付く
    def test_limited_to_max_items(self):
        # 合計 15 件 → len(items) == 10、failed == []
    def test_failed_feed_keeps_previous(self):
        # GitHub の fetch が URLError → items に previous の GitHub の項目が残り、
        # Booklog は新しい内容、failed == ["GitHub"]
    def test_unparseable_feed_keeps_previous(self):
        # fetch が HTML を返す → 上と同じ扱い
    def test_previous_of_succeeded_feed_is_replaced(self):
        # 成功したフィードの previous の項目は残らない
    def test_previous_of_unknown_source_dropped(self):
        # FEEDS にない source の previous の項目は残らない

class LoadPreviousTest(unittest.TestCase):
    def test_missing_file(self):   # → []
    def test_broken_json(self):    # 中身が "{" → []
    def test_wrong_shape(self):    # 中身が "[]" や {"items": "x"} → []

class MainTest(unittest.TestCase):
    def test_writes_json_and_returns_0(self):
        # 出力を json.load し、"generated" が Z で終わり、"items" が list
    def test_returns_1_when_a_feed_failed_but_still_writes(self):
    def test_no_temp_file_left(self):   # 出力先ディレクトリーに activities.json だけが残る
    def test_usage_error_returns_2(self):  # main(["prog"]) == 2
```

`main` のテストでは `fetch_activities.fetch_url` を `unittest.mock.patch` で差し替える。

- [ ] **Step 2: 失敗を確認する**

Run: `python3 -m unittest discover -s tools -v`
Expected: 新しいテストが `AttributeError` などで失敗、Task 2 のテストは `ok`

- [ ] **Step 3: 実装する**

- `collect` はフィードごとに `fetch` と `parse_feed` を `try` で囲み、どんな例外でも標準エラーに `表示名: 理由` を 1 行出して、`previous` のうち `source` が同じ項目を使う。
- `write_json` は `tempfile.NamedTemporaryFile(dir=出力先のディレクトリー, delete=False)` に書き、`os.replace` で置き換える。途中で失敗したら一時ファイルを消す。`ensure_ascii=False`、UTF-8。Web サーバーが読めるよう、置き換える前に `os.chmod(一時ファイル, 0o644)` にする（`NamedTemporaryFile` は 0600 で作るため）。
- ファイル末尾に `if __name__ == "__main__": sys.exit(main(sys.argv))`。

- [ ] **Step 4: 成功を確認する**

Run: `python3 -m unittest discover -s tools -v`
Expected: すべて `ok`

- [ ] **Step 5: 実際のフィードで動かす**

Run: `python3 tools/fetch_activities.py public_html/activities.json; echo "exit=$?"; python3 -m json.tool public_html/activities.json | head -30`
Expected: `exit=0`。Booklog と GitHub の項目が新しい順に最大 10 件。`git status` に `activities.json` が出ない。

どちらかのフィードが読めなかった場合は、実際の XML を見て `parse_feed` を直し、その形のサンプルをテストに足す。

- [ ] **Step 6: コミットする**

```bash
git add tools
git commit -m "フィードを取得してactivities.jsonを書き出すスクリプトを追加。"
```

---

### Task 4: トップページに表示する

**Files:**
- Modify: `public_html/index.html`（`</nav>` と `<footer>` の間、および末尾の `<script>` の並び）
- Create: `public_html/js/recent-activities.js`

**Interfaces:**
- Consumes: Task 3 の `activities.json`（`items[].source` `source_url` `title` `url` `published`）

- [ ] **Step 1: `index.html` にセクションと script を足す**

```html
    <section class="container-fluid" id="recent-activities" hidden>
      <h2 class="h3">Recent Activities</h2>
      <ul id="feed"></ul>
    </section>
```

script は `<script src="js/recent-activities.js"></script>` を `copyright-year.js` の後ろに置く。

- [ ] **Step 2: `js/recent-activities.js` を書く**

`js/copyright-year.js` と同じ書き方（即時関数、`'use strict'`、`var`、冒頭に日本語のコメント）。

- `fetch('activities.json', { cache: 'no-cache' })` で読む。`fetch` がない、応答が `ok` でない、JSON でない、`items` が配列でない、表示できる項目が 0 件、のどれでもセクションは `hidden` のままにする（コンソールにエラーを出さない）。
- 1 項目の DOM：`<li><a>source</a> - <a>title</a> <small>[yyyy/mm/dd hh:mm]</small></li>`。
  どちらの `<a>` も `target="_blank"` `rel="noopener"`。文字は `textContent` で入れる。
- `url` と `source_url` は `/^https?:\/\//` に合うものだけ使う。`url` が合わない項目は飛ばす。`source_url` が合わなければサービス名はリンクにしない。
- 日時は `new Date(published)` を閲覧者のローカル時刻で `yyyy/mm/dd hh:mm`（ゼロ埋め）にする。`Invalid Date` の項目は飛ばす。
- 行を 1 件以上足したら `section.hidden = false`。

- [ ] **Step 3: ブラウザーで確かめる**

Run: `python3 -m http.server 8765 --directory public_html`（バックグラウンド）

`http://localhost:8765/` を開き、次を確かめる（使えるならヘッドレスの Chrome/Chromium の `--dump-dom`、なければ依頼者に見てもらう）。
- 見出しの下に 10 件以内の行が新しい順に並び、形が「サービス名 - タイトル [日時]」。
- `public_html/activities.json` を一時的に別名にして再読み込みすると、見出しごと表示されない。確かめたら元に戻す。
- `result.html` とナビのドロップダウン、フッターの年が移動前と同じように動く。

- [ ] **Step 4: コミットする**

```bash
git add public_html/index.html public_html/js/recent-activities.js
git commit -m "トップページにRecent Activitiesを復活。"
```

---

## 実装後に依頼者が行うこと（本番）

1. clone を `git pull` し、`public_html/` の中身をドキュメントルートにコピーする。
2. crontab に足す：
   `0 * * * * /usr/local/bin/python3 /path/to/clone/tools/fetch_activities.py /path/to/docroot/activities.json`
3. 一度手で実行して `activities.json` ができることと、トップページに一覧が出ることを確かめる。出ない場合はブラウザーのコンソールで CSP（`connect-src`）のエラーを確認する。
