# Recent Activities の復活 設計

## 目的

トップページ（`index.html`）に、各サービスでの最近の活動を新しい順に並べた
「Recent Activities」を戻す。

以前は jquery.feeds がブラウザーから Google Feed API を呼んでいたが、API が終了したため
`1d7860c` で削除した。今回はブラウザーから外部を呼ばず、サーバー側で定期的に取得した結果を
ページが読む形にする。

## やること・やらないこと

- やること
  - Booklog と GitHub のフィードを混ぜ、新しい順に 10 件表示する。
    1 つのフィードからは 5 件まで。タイトルとリンクが同じ項目は 1 件にまとめる
    （実装中に追加。GitHub だけで 10 件が埋まり、Booklog が出なかったため）。
  - 見た目は以前と同じ「サービス名 - タイトル [yyyy/mm/dd hh:mm]」の箇条書き。
  - フィードはあとから足せるよう、スクリプト内の 1 か所の一覧にまとめる。
- やらないこと
  - Strava、Tumblr、Hatena::Diary（更新が止まっている）。
  - `blog/` の更新を混ぜること（必要になったら一覧に足す）。
  - API 認証が要るサービスへの対応。
- 避けたい状態
  - 見出しだけが表示されて中身が空（削除前の状態）。
  - 取得の失敗で一覧が空になる、または壊れた JSON が配信される。

## 制約

- 本番は FreeBSD。cron と Python 3 が使える。追加ライブラリは入れない（標準ライブラリのみ）。
- 本番の CSP は `script-src 'self'`。インラインスクリプトは使わず、`js/` の別ファイルにする。
- jQuery は使わない（すでに外してある）。

## 検討した作り方

- **A. Python が JSON を書き出し、ページの JavaScript が読んで並べる（採用）**
  リポジトリ内のファイルをサーバー上で書き換えない。置くのはスクリプト 1 本と cron 1 行。
  JavaScript を切っていると表示されないが、以前も同じだった。
- **B. Python が `index.html` を書き換える**
  JavaScript なしで表示できるが、git 管理のファイルを cron が書き換えるため pull と衝突する。
  テンプレートと生成物を分ける仕組みが要り、この規模には大げさ。
- **C. A と同じ構成で feedparser を使う**
  崩れたフィードに強いが、サーバーでライブラリを管理することになる。対象が RSS と Atom の
  2 つだけなら標準ライブラリで足りる。

A を選んだ（ユーザーの決定）。

## 構成

### 0. リポジトリの構成変更（先に行う）

今の中身をすべて `public_html/` に一段下げ、Web に出さないものをルートに置く。
移動は `git mv` で行い、機能追加とは別のコミットにする。

```
public_html/   今の中身（index.html, result.html, main.css, favicon.ico, robots.txt, css/, js/, images/）
tools/         fetch_activities.py とそのテスト
docs/          設計書など
```

本番は、別ディレクトリーに `git pull` したものを手でドキュメントルートにコピーしている。
構成変更後は `public_html/` の中身をコピーする。

### 1. 取得スクリプト `tools/fetch_activities.py`

- 使い方：`python3 tools/fetch_activities.py <出力先の JSON パス>`
- フィードの一覧（スクリプト先頭の定数）

  | 表示名 | フィード | 表示名のリンク先 |
  |---|---|---|
  | Booklog | `https://booklog.jp/users/daemonfreaks/feed` | `https://booklog.jp/users/daemonfreaks` |
  | GitHub | `https://github.com/daemonfreaks.atom` | `https://github.com/daemonfreaks` |

- 各フィードを `urllib` で取得し（タイムアウトあり、User-Agent を付ける）、`xml.etree` で
  RSS 2.0 / RSS 1.0（RDF）/ Atom のどれでも読めるようにする。
- 各項目からタイトル、リンク、日時を取り出す。日時は UTC の ISO 8601 にそろえる。
  リンクが `http://` か `https://` で始まらない項目は捨てる。
- フィードごとに、タイトルとリンクが同じ項目を 1 件にまとめ、新しい順に 5 件まで使う。
- それらを混ぜて新しい順に並べ、上位 10 件を残す。
- **失敗したとき：** あるフィードの取得や解析に失敗したら、前回の JSON にあるそのフィードの
  項目を引き継ぐ。標準エラーに理由を出し、終了コードを 1 にする（cron のメールで気づける）。
  他のフィードの処理は続ける。
- **書き出し：** 同じディレクトリーの一時ファイルに書いてから `os.replace` で置き換える。

出力する JSON の形：

```json
{
  "generated": "2026-11-26T03:00:02Z",
  "items": [
    {
      "source": "GitHub",
      "source_url": "https://github.com/daemonfreaks",
      "title": "daemonfreaks pushed to master in daemonfreaks/daemonfreaks.com",
      "url": "https://github.com/daemonfreaks/daemonfreaks.com/compare/...",
      "published": "2026-11-25T14:10:00Z"
    }
  ]
}
```

### 2. 表示 `index.html` と `js/recent-activities.js`

- 以下のパスはすべて `public_html/` の下。
- `index.html` の `<nav>` と `<footer>` の間にセクションを戻す。最初は `hidden` にしておく。

  ```html
  <section class="container-fluid" id="recent-activities" hidden>
    <h2 class="h3">Recent Activities</h2>
    <ul id="feed"></ul>
  </section>
  ```

- `js/recent-activities.js` が `activities.json` を `fetch` し、1 件以上あれば行を作って
  `hidden` を外す。取得に失敗した、または 0 件のときは隠したままにする。
- 行の形（以前と同じ）：

  ```
  ・GitHub - daemonfreaks pushed to master in … [2026/11/25 23:10]
  ```

  サービス名とタイトルはそれぞれリンクで、別タブで開く（`rel="noopener"` を付ける）。
  日時は閲覧者のローカル時刻で表示する。
- タイトルなどは `textContent` で入れ、HTML として解釈させない。リンク先は `http(s)` のものだけ使う。

### 3. 生成物の扱い

- 本番では、cron が本番のドキュメントルート直下に `activities.json` を直接書き出す
  （リポジトリの clone の中ではない）。手コピーで消したり上書きしたりしないよう注意する。
- 手元での確認では `public_html/activities.json` に出力する。これは `.gitignore` に入れる。

### 4. サーバーでの設定（手作業）

crontab に 1 行足す（パスは本番に合わせる）：

```
0 * * * * /usr/local/bin/python3 /path/to/clone/tools/fetch_activities.py /path/to/docroot/activities.json
```

## テスト

- Python：`unittest` で、RSS と Atom のサンプル XML からの取り出し、混ぜて並べる処理、
  失敗時に前回の項目を引き継ぐ処理を確かめる。ネットワークには出ない。
- 表示：ローカルでスクリプトを実際に動かして JSON を作り、簡易サーバーでトップページを開いて確かめる。

## 実装者の判断に任せること

- テストの置き場所とファイル名。
- タイムアウトの秒数、User-Agent の文字列。
- セクションの余白など、既存 CSS で足りない場合の最小限の調整。

## 未確認のこと

- 本番の CSP に `connect-src` や `default-src` の指定があるか。同じオリジンへの `fetch` は
  `'self'` があれば通るが、`'none'` だと止まる。デプロイ後に確認する。
- 本番の Python 3 のバージョン。3.8 以上で動くように書く。
