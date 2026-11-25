"""fetch_activities.py のテスト。ネットワークには出ない。

実行: python3 -m unittest discover -s tools -v
"""
import io
import json
import os
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stderr
from datetime import datetime, timezone
from unittest import mock

import fetch_activities
from fetch_activities import (
    MAX_ITEMS,
    MAX_PER_SOURCE,
    collect,
    load_previous,
    main,
    parse_date,
    parse_feed,
)

RSS2 = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>daemonfreaksの本棚</title>
    <link>https://booklog.jp/users/daemonfreaks</link>
    <item>
      <title>本のタイトル</title>
      <link>https://booklog.jp/item/1/1</link>
      <pubDate>Fri, 20 Nov 2026 21:03:00 +0900</pubDate>
    </item>
  </channel>
</rss>
""".encode("utf-8")

ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:media="http://search.yahoo.com/mrss/">
  <id>tag:github.com,2008:/daemonfreaks</id>
  <link type="text/html" rel="alternate" href="https://github.com/daemonfreaks"/>
  <link type="application/atom+xml" rel="self" href="https://github.com/daemonfreaks.atom"/>
  <title>daemonfreaks's Activity</title>
  <updated>2026-11-25T14:10:00Z</updated>
  <entry>
    <id>tag:github.com,2008:PushEvent/1</id>
    <published>2026-11-25T14:10:00Z</published>
    <updated>2026-11-25T14:20:00Z</updated>
    <link type="text/html" rel="alternate" href="https://github.com/daemonfreaks/x/compare/a...b"/>
    <title type="html">daemonfreaks pushed to master</title>
    <content type="html">&lt;div&gt;...&lt;/div&gt;</content>
  </entry>
  <entry>
    <id>tag:github.com,2008:PushEvent/2</id>
    <updated>2026-11-24T01:02:03Z</updated>
    <link href="https://github.com/daemonfreaks/y"/>
    <title>updated だけの項目</title>
  </entry>
</feed>
""".encode("utf-8")

RSS1 = """<?xml version="1.0" encoding="UTF-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns="http://purl.org/rss/1.0/"
         xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel rdf:about="https://example.com/">
    <title>日記</title>
    <link>https://example.com/</link>
  </channel>
  <item rdf:about="https://example.com/1">
    <title>日記の題</title>
    <link>https://example.com/1</link>
    <dc:date>2026-11-01T09:00:00+09:00</dc:date>
  </item>
</rdf:RDF>
""".encode("utf-8")


def rss2_with_items(items_xml):
    return (
        '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
        "<title>t</title>" + items_xml + "</channel></rss>"
    ).encode("utf-8")


GOOD_ITEM = (
    "<item><title>よい項目</title><link>https://example.com/good</link>"
    "<pubDate>Fri, 20 Nov 2026 12:00:00 GMT</pubDate></item>"
)
GOOD = {
    "title": "よい項目",
    "url": "https://example.com/good",
    "published": "2026-11-20T12:00:00Z",
}


class ParseDateTest(unittest.TestCase):
    def test_rfc822(self):
        self.assertEqual(
            parse_date("Wed, 25 Nov 2026 23:10:00 +0900"),
            datetime(2026, 11, 25, 14, 10, tzinfo=timezone.utc),
        )

    def test_iso8601_z(self):
        self.assertEqual(
            parse_date("2026-11-25T14:10:00Z"),
            datetime(2026, 11, 25, 14, 10, tzinfo=timezone.utc),
        )

    def test_iso8601_offset(self):
        self.assertEqual(
            parse_date("2026-11-25T23:10:00+09:00"),
            datetime(2026, 11, 25, 14, 10, tzinfo=timezone.utc),
        )

    def test_naive_is_utc(self):
        self.assertEqual(
            parse_date("2026-11-25T14:10:00"),
            datetime(2026, 11, 25, 14, 10, tzinfo=timezone.utc),
        )

    def test_surrounding_whitespace(self):
        self.assertEqual(
            parse_date("\n  2026-11-25T14:10:00Z  "),
            datetime(2026, 11, 25, 14, 10, tzinfo=timezone.utc),
        )

    def test_garbage(self):
        self.assertIsNone(parse_date("yesterday"))
        self.assertIsNone(parse_date(""))


class ParseFeedTest(unittest.TestCase):
    def test_rss2(self):
        self.assertEqual(
            parse_feed(RSS2),
            [
                {
                    "title": "本のタイトル",
                    "url": "https://booklog.jp/item/1/1",
                    "published": "2026-11-20T12:03:00Z",
                }
            ],
        )

    def test_atom(self):
        self.assertEqual(
            parse_feed(ATOM)[0],
            {
                "title": "daemonfreaks pushed to master",
                "url": "https://github.com/daemonfreaks/x/compare/a...b",
                "published": "2026-11-25T14:10:00Z",
            },
        )

    def test_atom_falls_back_to_updated_and_link_without_rel(self):
        self.assertEqual(
            parse_feed(ATOM)[1],
            {
                "title": "updated だけの項目",
                "url": "https://github.com/daemonfreaks/y",
                "published": "2026-11-24T01:02:03Z",
            },
        )

    def test_rss1(self):
        self.assertEqual(
            parse_feed(RSS1),
            [
                {
                    "title": "日記の題",
                    "url": "https://example.com/1",
                    "published": "2026-11-01T00:00:00Z",
                }
            ],
        )

    def test_title_whitespace_collapsed(self):
        data = rss2_with_items(
            "<item><title>  a\n   b  </title><link>https://example.com/1</link>"
            "<pubDate>Fri, 20 Nov 2026 12:00:00 GMT</pubDate></item>"
        )
        self.assertEqual(parse_feed(data)[0]["title"], "a b")

    def test_item_without_date_dropped(self):
        data = rss2_with_items(
            "<item><title>日付なし</title><link>https://example.com/1</link></item>"
            "<item><title>変な日付</title><link>https://example.com/2</link>"
            "<pubDate>yesterday</pubDate></item>" + GOOD_ITEM
        )
        self.assertEqual(parse_feed(data), [GOOD])

    def test_item_with_empty_title_dropped(self):
        data = rss2_with_items(
            "<item><title>   </title><link>https://example.com/1</link>"
            "<pubDate>Fri, 20 Nov 2026 12:00:00 GMT</pubDate></item>"
            "<item><link>https://example.com/2</link>"
            "<pubDate>Fri, 20 Nov 2026 12:00:00 GMT</pubDate></item>" + GOOD_ITEM
        )
        self.assertEqual(parse_feed(data), [GOOD])

    def test_item_with_non_http_link_dropped(self):
        data = rss2_with_items(
            "<item><title>js</title><link>javascript:alert(1)</link>"
            "<pubDate>Fri, 20 Nov 2026 12:00:00 GMT</pubDate></item>"
            "<item><title>相対</title><link>/item/1</link>"
            "<pubDate>Fri, 20 Nov 2026 12:00:00 GMT</pubDate></item>"
            "<item><title>リンクなし</title>"
            "<pubDate>Fri, 20 Nov 2026 12:00:00 GMT</pubDate></item>" + GOOD_ITEM
        )
        self.assertEqual(parse_feed(data), [GOOD])

    def test_empty_feed_is_empty_list(self):
        self.assertEqual(parse_feed(rss2_with_items("")), [])

    def test_html_is_error(self):
        with self.assertRaises(ValueError):
            parse_feed(b"<html><body>Service Unavailable</body></html>")

    def test_broken_xml_is_error(self):
        with self.assertRaises(ValueError):
            parse_feed(b"<rss><channel>")


FEEDS = [
    {"source": "A", "feed_url": "https://a.example/feed", "source_url": "https://a.example/"},
    {"source": "B", "feed_url": "https://b.example/feed", "source_url": "https://b.example/"},
]


def rss_item(title, day, hour=12):
    return (
        "<item><title>%s</title><link>https://example.com/%s</link>"
        "<pubDate>%04d-%02d-%02dT%02d:00:00Z</pubDate></item>"
        % (title, title, 2026, 11, day, hour)
    )


def fake_fetch(responses):
    """URL ごとの応答を返す fetch。値が例外ならそれを投げる。"""

    def fetch(url):
        response = responses[url]
        if isinstance(response, Exception):
            raise response
        return response

    return fetch


def titles(items):
    return [item["title"] for item in items]


def quiet(function, *args, **kwargs):
    """標準エラーを捨てて呼ぶ。戻り値は (結果, 標準エラーの内容)。"""
    stderr = io.StringIO()
    with redirect_stderr(stderr):
        result = function(*args, **kwargs)
    return result, stderr.getvalue()


PREVIOUS = [
    {"source": "A", "source_url": "https://a.example/", "title": "old-a",
     "url": "https://example.com/old-a", "published": "2026-11-02T00:00:00Z"},
    {"source": "B", "source_url": "https://b.example/", "title": "old-b",
     "url": "https://example.com/old-b", "published": "2026-11-03T00:00:00Z"},
    {"source": "Gone", "source_url": "https://gone.example/", "title": "old-gone",
     "url": "https://example.com/old-gone", "published": "2026-11-04T00:00:00Z"},
]


class CollectTest(unittest.TestCase):
    def test_merged_newest_first(self):
        fetch = fake_fetch({
            "https://a.example/feed": rss2_with_items(rss_item("a1", 10) + rss_item("a2", 20)),
            "https://b.example/feed": rss2_with_items(rss_item("b1", 15) + rss_item("b2", 25)),
        })
        items, failed = collect(FEEDS, [], fetch)
        self.assertEqual(titles(items), ["b2", "a2", "b1", "a1"])
        self.assertEqual(failed, [])
        self.assertEqual(items[0], {
            "source": "B",
            "source_url": "https://b.example/",
            "title": "b2",
            "url": "https://example.com/b2",
            "published": "2026-11-25T12:00:00Z",
        })

    def test_limited_to_max_items(self):
        fetch = fake_fetch({
            "https://a.example/feed": rss2_with_items(
                "".join(rss_item("a%d" % d, d) for d in range(1, 9))),
            "https://b.example/feed": rss2_with_items(
                "".join(rss_item("b%d" % d, d, hour=13) for d in range(1, 8))),
        })
        items, failed = collect(FEEDS, [], fetch)
        self.assertEqual(MAX_ITEMS, 10)
        self.assertEqual(len(items), 10)
        self.assertEqual(titles(items)[:3], ["a8", "b7", "a7"])
        self.assertEqual(failed, [])

    def test_busy_feed_does_not_push_out_quiet_feed(self):
        # A が最近 12 件、B は古い 2 件だけ。B も一覧に残る。
        fetch = fake_fetch({
            "https://a.example/feed": rss2_with_items(
                "".join(rss_item("a%d" % d, d) for d in range(10, 22))),
            "https://b.example/feed": rss2_with_items(rss_item("b1", 1) + rss_item("b2", 2)),
        })
        items, failed = collect(FEEDS, [], fetch)
        self.assertEqual(MAX_PER_SOURCE, 5)
        self.assertEqual(
            titles(items), ["a21", "a20", "a19", "a18", "a17", "b2", "b1"])

    def test_same_title_and_url_shown_once(self):
        # GitHub は同じ PR への活動を同じタイトルとリンクで何度も出す。
        duplicated = (
            "<item><title>same</title><link>https://example.com/pr/9</link>"
            "<pubDate>2026-11-%02dT12:00:00Z</pubDate></item>"
        )
        fetch = fake_fetch({
            "https://a.example/feed": rss2_with_items(
                duplicated % 20 + duplicated % 19 + rss_item("a1", 18)),
            "https://b.example/feed": rss2_with_items(""),
        })
        items, failed = collect(FEEDS, [], fetch)
        self.assertEqual(titles(items), ["same", "a1"])
        self.assertEqual(items[0]["published"], "2026-11-20T12:00:00Z")

    def test_failed_feed_keeps_previous(self):
        fetch = fake_fetch({
            "https://a.example/feed": rss2_with_items(rss_item("a1", 10)),
            "https://b.example/feed": urllib.error.URLError("timed out"),
        })
        (items, failed), stderr = quiet(collect, FEEDS, PREVIOUS, fetch)
        self.assertEqual(titles(items), ["a1", "old-b"])
        self.assertEqual(failed, ["B"])
        self.assertIn("B:", stderr)
        self.assertIn("timed out", stderr)

    def test_unparseable_feed_keeps_previous(self):
        fetch = fake_fetch({
            "https://a.example/feed": b"<html><body>Service Unavailable</body></html>",
            "https://b.example/feed": rss2_with_items(rss_item("b1", 10)),
        })
        (items, failed), _ = quiet(collect, FEEDS, PREVIOUS, fetch)
        self.assertEqual(titles(items), ["b1", "old-a"])
        self.assertEqual(failed, ["A"])

    def test_previous_of_succeeded_feed_is_replaced(self):
        fetch = fake_fetch({
            "https://a.example/feed": rss2_with_items(rss_item("a1", 10)),
            "https://b.example/feed": rss2_with_items(""),
        })
        items, failed = collect(FEEDS, PREVIOUS, fetch)
        self.assertEqual(titles(items), ["a1"])
        self.assertEqual(failed, [])

    def test_previous_of_unknown_source_dropped(self):
        fetch = fake_fetch({
            "https://a.example/feed": urllib.error.URLError("x"),
            "https://b.example/feed": urllib.error.URLError("x"),
        })
        (items, failed), _ = quiet(collect, FEEDS, PREVIOUS, fetch)
        self.assertEqual(titles(items), ["old-b", "old-a"])
        self.assertEqual(failed, ["A", "B"])


class LoadPreviousTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = os.path.join(self.dir.name, "activities.json")

    def write(self, text):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(text)

    def test_reads_items(self):
        self.write(json.dumps({"generated": "x", "items": PREVIOUS}))
        self.assertEqual(load_previous(self.path), PREVIOUS)

    def test_missing_file(self):
        self.assertEqual(load_previous(self.path), [])

    def test_broken_json(self):
        self.write("{")
        self.assertEqual(load_previous(self.path), [])

    def test_wrong_shape(self):
        for text in ("[]", '{"items": "x"}', '{"generated": "x"}', "null"):
            self.write(text)
            self.assertEqual(load_previous(self.path), [], text)

    def test_non_dict_items_skipped(self):
        self.write(json.dumps({"items": ["x", 1, None, PREVIOUS[0]]}))
        self.assertEqual(load_previous(self.path), [PREVIOUS[0]])


class MainTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = os.path.join(self.dir.name, "activities.json")

    def run_main(self, fetch):
        with mock.patch.object(fetch_activities, "fetch_url", fetch):
            return quiet(main, ["prog", self.path])

    def read(self):
        with open(self.path, encoding="utf-8") as f:
            return json.load(f)

    def test_writes_json_and_returns_0(self):
        code, _ = self.run_main(lambda url: rss2_with_items(rss_item("日本語", 10)))
        self.assertEqual(code, 0)
        data = self.read()
        self.assertRegex(data["generated"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertEqual(titles(data["items"]), ["日本語", "日本語"])
        self.assertEqual(
            sorted(item["source"] for item in data["items"]), ["Booklog", "GitHub"])
        with open(self.path, encoding="utf-8") as f:
            self.assertIn("日本語", f.read())

    def test_returns_1_when_a_feed_failed_but_still_writes(self):
        def fetch(url):
            if "github" in url:
                raise urllib.error.URLError("down")
            return rss2_with_items(rss_item("b", 10))

        code, stderr = self.run_main(fetch)
        self.assertEqual(code, 1)
        self.assertIn("GitHub", stderr)
        self.assertEqual(titles(self.read()["items"]), ["b"])

    def test_failed_feed_keeps_items_from_existing_file(self):
        self.run_main(lambda url: rss2_with_items(rss_item("first", 10)))

        def fetch(url):
            raise urllib.error.URLError("down")

        code, _ = self.run_main(fetch)
        self.assertEqual(code, 1)
        self.assertEqual(titles(self.read()["items"]), ["first", "first"])

    def test_no_temp_file_left(self):
        self.run_main(lambda url: rss2_with_items(rss_item("a", 10)))
        self.assertEqual(os.listdir(self.dir.name), ["activities.json"])

    def test_output_is_world_readable(self):
        self.run_main(lambda url: rss2_with_items(rss_item("a", 10)))
        self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o644)

    def test_usage_error_returns_2(self):
        code, stderr = quiet(main, ["prog"])
        self.assertEqual(code, 2)
        self.assertIn("使い方", stderr)

    def test_unwritable_destination_returns_1(self):
        path = os.path.join(self.dir.name, "no-such-dir", "activities.json")
        with mock.patch.object(
            fetch_activities, "fetch_url",
            lambda url: rss2_with_items(rss_item("a", 10)),
        ):
            code, stderr = quiet(main, ["prog", path])
        self.assertEqual(code, 1)
        self.assertNotEqual(stderr, "")


if __name__ == "__main__":
    unittest.main()
