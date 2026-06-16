import unittest

from source_radar.models import EvidenceCard
from source_radar.evidence import (
    classify_evidence_bucket,
    has_strong_source,
    sort_evidence_by_strength,
)
from source_radar.agent import _extract_entity_name, _build_strong_source_queries


def _card(title="", url="", summary="", adapter="search", source_type="search-result"):
    return EvidenceCard(
        id="ev-test", source_type=source_type, title=title,
        url=url, summary=summary, adapter=adapter,
    )


class TestClassifyEvidenceBucket(unittest.TestCase):
    def test_gov_url_with_relevant_query_is_official(self):
        c = _card(url="https://www.suzhou.gov.cn/notice/123", title="苏州市政府公告")
        self.assertEqual(classify_evidence_bucket(c, "苏州 政策"), "official")

    def test_gov_url_with_unrelated_query_is_noise(self):
        c = _card(url="https://www.suzhou.gov.cn/", title="苏州市人民政府", summary="苏州旅游景点")
        self.assertEqual(classify_evidence_bucket(c, "张雪峰怎么了"), "noise")

    def test_official_announcement_source_type_is_official(self):
        c = _card(
            title="张雪峰讣告",
            summary="公司发布讣告，张雪峰因病去世",
            source_type="official-announcement",
        )
        self.assertEqual(classify_evidence_bucket(c, "张雪峰怎么了"), "official")

    def test_search_result_with_obituary_text_is_not_official(self):
        c = _card(
            title="张雪峰官方讣告发布",
            summary="网友转载公司发布讣告",
            url="https://weibo.com/a/hot/123",
            adapter="search-baidu",
        )
        self.assertNotEqual(classify_evidence_bucket(c, "张雪峰怎么了"), "official")

    def test_mainstream_media_with_relevant_query(self):
        c = _card(url="https://www.donews.com/news/123", title="张雪峰去世确认")
        self.assertEqual(classify_evidence_bucket(c, "张雪峰怎么了"), "mainstream")

    def test_mainstream_media_with_unrelated_query(self):
        c = _card(url="https://www.donews.com/news/123", title="科技新闻速报")
        self.assertEqual(classify_evidence_bucket(c, "张雪峰怎么了"), "noise")

    def test_community_post_is_community(self):
        c = _card(adapter="mediacrawler", source_type="community-post",
                  title="张雪峰怎么了", summary="网友热议")
        self.assertEqual(classify_evidence_bucket(c, "张雪峰怎么了"), "community")

    def test_community_comment_is_lower_priority(self):
        c = _card(adapter="mediacrawler", source_type="community-comment",
                  title="评论: 我的也是这个问题", summary="我的也是这个问题")
        bucket = classify_evidence_bucket(c, "小米15拍照")
        self.assertEqual(bucket, "community-comment")
        self.assertIn(bucket, ("community", "community-comment"))

    def test_community_comment_sorted_after_post(self):
        post = _card(adapter="mediacrawler", source_type="community-post",
                     title="小米15拍照体验", summary="分享体验")
        comment = _card(adapter="mediacrawler", source_type="community-comment",
                        title="评论: 我的也是", summary="我的也是翻车")
        sorted_cards = sort_evidence_by_strength([comment, post], "小米15拍照")
        self.assertEqual(sorted_cards[0].source_type, "community-post")
        self.assertEqual(sorted_cards[1].source_type, "community-comment")

    def test_noise_search_result(self):
        c = _card(title="张姓起源", summary="张姓是中国大姓")
        self.assertEqual(classify_evidence_bucket(c, "张雪峰怎么了"), "noise")


class TestHasStrongSource(unittest.TestCase):
    def test_empty_returns_false(self):
        self.assertFalse(has_strong_source([]))

    def test_only_noise_returns_false(self):
        cards = [_card(title="噪音1"), _card(title="噪音2")]
        self.assertFalse(has_strong_source(cards))

    def test_official_card_returns_true(self):
        cards = [
            _card(title="噪音"),
            _card(title="张雪峰讣告", summary="公司发布讣告", source_type="official-announcement"),
        ]
        self.assertTrue(has_strong_source(cards))

    def test_obituary_text_on_community_url_is_not_strong_source(self):
        cards = [
            _card(
                title="张雪峰公司发布讣告",
                summary="微博热榜转载",
                url="https://weibo.com/a/hot/123",
                adapter="search-baidu",
            ),
        ]
        self.assertFalse(has_strong_source(cards, "张雪峰怎么了"))

    def test_mainstream_card_returns_true(self):
        cards = [
            _card(title="噪音"),
            _card(url="https://www.donews.com/news/123", title="张雪峰去世"),
        ]
        self.assertTrue(has_strong_source(cards))


class TestSortEvidenceByStrength(unittest.TestCase):
    def test_strong_sources_first(self):
        cards = [
            _card(title="噪音", adapter="search"),
            _card(title="社区帖", adapter="mediacrawler", source_type="community-post"),
            _card(title="讣告", summary="公司发布讣告", source_type="official-announcement"),
            _card(url="https://donews.com/x", title="媒体报道"),
        ]
        sorted_cards = sort_evidence_by_strength(cards)
        buckets = [classify_evidence_bucket(c) for c in sorted_cards]
        self.assertEqual(buckets[0], "official")
        self.assertEqual(buckets[1], "mainstream")


class TestExtractEntityName(unittest.TestCase):
    def test_removes_suffix(self):
        self.assertEqual(_extract_entity_name("张雪峰怎么了"), "张雪峰")

    def test_removes_death_suffix(self):
        self.assertEqual(_extract_entity_name("张雪峰死了吗"), "张雪峰")

    def test_plain_name(self):
        self.assertEqual(_extract_entity_name("张雪峰"), "张雪峰")


class TestBuildStrongSourceQueries(unittest.TestCase):
    def test_generates_obituary_queries(self):
        queries = _build_strong_source_queries("张雪峰怎么了", [])
        self.assertTrue(any("讣告" in q for q in queries))
        self.assertTrue(any("官方" in q or "声明" in q for q in queries))
        self.assertTrue(any("证券时报" in q or "财联社" in q for q in queries))

    def test_extracts_org_from_evidence(self):
        cards = [_card(title="苏州峰学蔚来教育科技有限公司", summary="公司公告")]
        queries = _build_strong_source_queries("张雪峰怎么了", cards)
        self.assertTrue(any("峰学蔚来" in q for q in queries))

    def test_limits_queries(self):
        queries = _build_strong_source_queries("张雪峰怎么了", [])
        self.assertLessEqual(len(queries), 8)


if __name__ == "__main__":
    unittest.main()
