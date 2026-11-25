#!/usr/bin/env python3
"""トップページの Recent Activities 用に、フィードを取得して JSON を書き出す。

使い方: python3 fetch_activities.py <出力先の JSON パス>

cron で定期的に動かす。標準ライブラリだけで動く（Python 3.8 以上）。
"""
import html
import json
import os
import re
import sys
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

# 取得するフィード。足すときはここに 1 行加える。
#   source:     一覧に出すサービス名
#   feed_url:   RSS / Atom の URL
#   source_url: サービス名のリンク先
FEEDS = [
    {
        "source": "Booklog",
        "feed_url": "https://booklog.jp/users/daemonfreaks/feed",
        "source_url": "https://booklog.jp/users/daemonfreaks",
    },
    {
        "source": "GitHub",
        "feed_url": "https://github.com/daemonfreaks.atom",
        "source_url": "https://github.com/daemonfreaks",
    },
]

# 書き出す件数（全フィードを混ぜた新しい順）。
MAX_ITEMS = 10
# 1 つのフィードから使う件数。更新の多いフィードが一覧を埋めて、
# 更新の少ないフィードが出なくなるのを防ぐ。
MAX_PER_SOURCE = 5

TIMEOUT_SECONDS = 20
USER_AGENT = "daemonfreaks.com-activities/1.0"
ITEM_KEYS = ("source", "source_url", "title", "url", "published")


def parse_date(text):
    """RFC 822 か ISO 8601 の日時を UTC の datetime にする。読めなければ None。

    タイムゾーンのない日時は UTC とみなす。
    """
    text = (text or "").strip()
    if not text:
        return None
    parsed = None
    try:
        # 3.8 は末尾の Z を読めないので置き換える。
        parsed = datetime.fromisoformat(re.sub(r"[Zz]$", "+00:00", text))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(text)
        except (TypeError, ValueError):
            return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _local(tag):
    """名前空間を除いたタグ名。"""
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _children(element, name):
    return [child for child in element if _local(child.tag) == name]


def _text(element, *names):
    """names の順に子要素を探し、最初に見つかった空でない文字列を返す。"""
    for name in names:
        for child in _children(element, name):
            text = "".join(child.itertext()).strip()
            if text:
                return text
    return ""


def _atom_title(entry):
    """Atom のタイトル。type="html" のときはタグを除き、実体参照を文字に直す。"""
    text = _text(entry, "title")
    titles = _children(entry, "title")
    if titles and titles[0].get("type") == "html":
        text = html.unescape(re.sub(r"<[^>]*>", "", text))
    return text


def _atom_link(entry):
    for link in _children(entry, "link"):
        if link.get("rel", "alternate") == "alternate" and link.get("href"):
            return link.get("href").strip()
    return ""


def parse_feed(data):
    """RSS 2.0 / RSS 1.0 / Atom の bytes から項目の一覧を取り出す。

    各項目は {"title", "url", "published"}。published は UTC の
    "YYYY-MM-DDTHH:MM:SSZ"。タイトル、http(s) のリンク、読める日時の
    どれかが欠けた項目は捨てる。フィードとして読めなければ ValueError。
    """
    try:
        root = ET.fromstring(data)
    except ET.ParseError as error:
        raise ValueError("XML として読めない: %s" % error)

    kind = _local(root.tag)
    if kind == "feed":
        entries = _children(root, "entry")
        is_atom = True
    elif kind in ("rss", "RDF"):
        # RSS 2.0 は channel の中、RSS 1.0 は channel と同じ階層に item がある。
        entries = [e for e in root.iter() if _local(e.tag) == "item"]
        is_atom = False
    else:
        raise ValueError("フィードではない: ルート要素が <%s>" % kind)

    items = []
    for entry in entries:
        if is_atom:
            title = _atom_title(entry)
            url = _atom_link(entry)
            published = parse_date(_text(entry, "published", "updated"))
        else:
            title = _text(entry, "title")
            url = _text(entry, "link")
            published = parse_date(_text(entry, "pubDate", "date"))
        title = " ".join(title.split())
        if not title or published is None:
            continue
        if not re.match(r"https?://", url):
            continue
        items.append(
            {
                "title": title,
                "url": url,
                "published": published.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        )
    return items


def fetch_url(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return response.read()


def load_previous(path):
    """前回書き出した JSON の項目を返す。ない、壊れている、形が違うときは []。"""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    return [
        item
        for item in items
        if isinstance(item, dict)
        and all(isinstance(item.get(key), str) for key in ITEM_KEYS)
    ]


def _newest_unique(entries):
    """新しい順に並べ、タイトルとリンクが同じものは新しいほうだけ残す。"""
    seen = set()
    unique = []
    for entry in sorted(entries, key=lambda e: e["published"], reverse=True):
        key = (entry["title"], entry["url"])
        if key not in seen:
            seen.add(key)
            unique.append(entry)
    return unique


def collect(feeds, previous, fetch=fetch_url):
    """各フィードの項目を混ぜ、新しい順の上位 MAX_ITEMS 件を返す。

    1 つのフィードからは新しい順に MAX_PER_SOURCE 件まで使う。
    取得や解析に失敗したフィードは、previous にある同じ source の項目を
    引き継ぐ。戻り値は (項目の一覧, 失敗したフィードの source の一覧)。
    """
    items = []
    failed = []
    for feed in feeds:
        try:
            entries = parse_feed(fetch(feed["feed_url"]))
        except Exception as error:  # 1 つの失敗で全体を止めない
            print("%s: %s" % (feed["source"], error), file=sys.stderr)
            failed.append(feed["source"])
            items.extend(i for i in previous if i["source"] == feed["source"])
            continue
        for entry in _newest_unique(entries)[:MAX_PER_SOURCE]:
            item = {"source": feed["source"], "source_url": feed["source_url"]}
            item.update(entry)
            items.append(item)
    items.sort(key=lambda item: item["published"], reverse=True)
    return items[:MAX_ITEMS], failed


def write_json(path, items, now):
    """一時ファイルに書いてから置き換える（途中の内容を読ませない）。"""
    data = {"generated": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "items": items}
    directory = os.path.dirname(os.path.abspath(path))
    temp = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=directory, prefix=".activities-", delete=False
    )
    try:
        with temp:
            json.dump(data, temp, ensure_ascii=False, indent=1)
            temp.write("\n")
        # 一時ファイルは 0600 で作られる。Web サーバーが読めるようにする。
        os.chmod(temp.name, 0o644)
        os.replace(temp.name, path)
    except BaseException:
        try:
            os.unlink(temp.name)
        except OSError:
            pass
        raise


def main(argv):
    if len(argv) != 2:
        print("使い方: %s <出力先の JSON パス>" % argv[0], file=sys.stderr)
        return 2
    path = argv[1]
    items, failed = collect(FEEDS, load_previous(path), fetch_url)
    try:
        write_json(path, items, datetime.now(timezone.utc))
    except OSError as error:
        print("書き出せない: %s" % error, file=sys.stderr)
        return 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
