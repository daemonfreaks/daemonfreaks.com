#!/usr/bin/env python3
"""トップページの Recent Activities 用に、フィードを取得して JSON を書き出す。

使い方: python3 fetch_activities.py <出力先の JSON パス>

cron で定期的に動かす。標準ライブラリだけで動く（Python 3.8 以上）。
"""
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime


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
        title = " ".join(_text(entry, "title").split())
        if is_atom:
            url = _atom_link(entry)
            published = parse_date(_text(entry, "published", "updated"))
        else:
            url = _text(entry, "link")
            published = parse_date(_text(entry, "pubDate", "date"))
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
