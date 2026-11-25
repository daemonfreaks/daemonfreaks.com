"""fetch_activities.py のテスト。ネットワークには出ない。

実行: python3 -m unittest discover -s tools -v
"""
import unittest
from datetime import datetime, timezone

from fetch_activities import parse_date, parse_feed

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


if __name__ == "__main__":
    unittest.main()
