"""Offline tests for the Yila-adapted WorldbookService; never imports newGeYi.

Can run while the bot is online: JSON is read-only; synthetic books live in temp dirs.
"""
from pathlib import Path
import importlib.util
import json
import os
import tempfile
import unittest

WORKSPACE = Path(__file__).resolve().parent
STAGED = WORKSPACE / 'worldbook_yila_adapted.py'
if STAGED.exists():
    MODULE_PATH = STAGED
    ROOT = Path(r'E:\dice\newGeYi')
else:
    ROOT = Path(__file__).resolve().parents[1]
    MODULE_PATH = ROOT / 'memory' / 'worldbook.py'


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


WB = load_module('yila_worldbook_under_test', MODULE_PATH)
BOOK = ROOT / 'data' / 'worldbook.json'


class OptionalRetrievalTests(unittest.TestCase):
    def book(self, entries, retrieval=None):
        folder = tempfile.TemporaryDirectory(prefix='yila_wb_')
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / 'worldbook.json'
        data = {'entries': entries}
        if retrieval is not None:
            data['retrieval'] = retrieval
        path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        return WB.WorldbookService(str(path))

    def test_existing_strong_words_are_never_automatically_demoted(self):
        for keyword in ['学校', '朋友', '科技']:
            book = self.book([{'id': 'entry', 'keywords': [keyword], 'content': '资料正文'}])
            self.assertEqual(book.lookup('我今天聊' + keyword), ['资料正文'])

    def test_explicit_weak_words_need_addressing_or_distinct_companion(self):
        book = self.book([{'id': 'weak', 'weak_keywords': ['学校', '朋友'], 'content': '私有学校资料'}])
        self.assertEqual(book.lookup('我今天在学校'), [])
        self.assertEqual(book.lookup('学校学校学校'), [])
        self.assertEqual(book.lookup('你的学校'), ['私有学校资料'])
        self.assertEqual(book.lookup('学校里的朋友'), ['私有学校资料'])

    def test_persona_anchors_are_data_not_other_character_names(self):
        book = self.book([{'id': 'weak', 'weak_keywords': ['学校'], 'content': '课业描述'}],
                         {'persona_anchors': ['伊菈', '艾什科姆']})
        self.assertEqual(book.lookup('伊菈的学校'), ['课业描述'])
        self.assertEqual(book.lookup('艾什科姆学校'), ['课业描述'])
        self.assertEqual(book.lookup('歌伊学校'), [])
        self.assertEqual(book.lookup('你学校'), [])

    def test_empty_configured_anchors_require_multiple_weak_hits(self):
        book = self.book([{'id': 'weak', 'weak_keywords': ['学校'], 'content': '学习材料'}],
                         {'persona_anchors': []})
        self.assertEqual(book.lookup('你的学校'), [])

    def test_exclusion_masks_keyword_bm25_and_history_without_joining_words(self):
        book = self.book([{'id': 'ocean', 'keywords': ['海'], 'excludes': ['上海'], 'content': '海'}])
        self.assertEqual(book.lookup('上海'), [])
        self.assertEqual(book.lookup('然后呢', recent=['上海']), [])
        self.assertEqual(book.lookup('上海附近的海'), ['海'])
        self.assertEqual(book.lookup('大海'), ['海'])

    def test_priority_adjusts_otherwise_equal_candidates(self):
        book = self.book([{'id': 'first', 'keywords': ['茶'], 'content': '相同内容'},
                          {'id': 'second', 'keywords': ['茶'], 'content': '相同内容', 'priority': 1}])
        self.assertEqual([entry.id for entry in book._docs], ['first', 'second'])
        self.assertEqual(book._docs[1].priority, 1)
        self.assertEqual(book.lookup('茶', max_entries=1), ['相同内容'])
        # Different output, matching token count, so rank can be observed externally.
        book = self.book([{'id': 'first', 'keywords': ['茶'], 'content': '甲'},
                          {'id': 'second', 'keywords': ['茶'], 'content': '乙', 'priority': 1}])
        self.assertEqual(book.lookup('茶', max_entries=1), ['乙'])

    def test_non_finite_priority_and_malformed_metadata_are_safe(self):
        book = self.book([{'id': 'first', 'keywords': ['茶'], 'content': '甲', 'priority': float('inf'),
                           'excludes': '茶', 'links': {'bad': 'entry'}, 'weak_keywords': [None, 3]},
                          {'id': 'second', 'keywords': ['茶'], 'content': '乙', 'priority': float('nan')}])
        self.assertTrue(book.lookup('茶'))
        self.assertTrue(all(entry.priority == 0 for entry in book._docs))

    def test_one_hop_links_only_fill_and_do_not_override_direct_hit(self):
        book = self.book([{'id': 'source', 'keywords': ['入口'], 'content': '入口资料', 'links': ['linked', 'missing']},
                          {'id': 'linked', 'keywords': ['遥远'], 'content': '关联资料', 'priority': 1000, 'links': ['third']},
                          {'id': 'third', 'keywords': ['另外'], 'content': '二跳资料'}])
        self.assertEqual(book.lookup('入口', max_entries=1), ['入口资料'])
        self.assertEqual(book.lookup('入口', max_entries=3), ['入口资料', '关联资料'])

    def test_links_never_bypass_stage_scope_always_or_topic(self):
        entries = [{'id': 'source', 'keywords': ['公开'], 'content': '公开资料',
                    'links': ['secret', 'private', 'always', 'topic']},
                   {'id': 'secret', 'keywords': ['秘密'], 'content': '机密资料', 'scope': 'private', 'min_stage': 5},
                   {'id': 'private', 'keywords': ['私事'], 'content': '私聊资料', 'scope': 'private'},
                   {'id': 'always', 'always': True, 'content': '常驻'},
                   {'id': 'topic', 'topic': True, 'content': '谈资'}]
        book = self.book(entries)
        self.assertEqual(book.lookup('公开', stage=0, scope='group'), ['公开资料'])
        self.assertEqual(book.lookup('公开', stage=4, scope='private'), ['公开资料', '私聊资料'])
        self.assertEqual(book.lookup('公开', stage=5, scope='private'), ['公开资料', '机密资料', '私聊资料'])

    def test_links_cannot_reintroduce_excluded_target(self):
        # Excluded collision with no independent target keyword must not be linked back.
        book = self.book([{'id': 'source', 'keywords': ['入口'], 'content': '甲', 'links': ['linked']},
                          {'id': 'linked', 'keywords': ['海'], 'excludes': ['上海'], 'content': '海'}])
        self.assertEqual(book.lookup('入口上海'), ['甲'])

    def test_total_budget_is_hard_including_ellipsis(self):
        book = self.book([{'id': 'first', 'keywords': ['测试'], 'content': '甲' * 20},
                          {'id': 'second', 'keywords': ['测试'], 'content': '乙' * 20}])
        self.assertEqual(len(book.lookup('测试')), 2)
        self.assertLessEqual(sum(map(len, book.lookup('测试', max_total_chars=5))), 5)
        self.assertEqual(book.lookup('测试', max_total_chars=1), ['…'])
        self.assertEqual(book.lookup('测试', max_total_chars=0), book.lookup('测试'))
        self.assertEqual(book.lookup('测试', max_entries=0), [])

    def test_entry_budget_then_total_budget_skip_nonfitting_entries(self):
        book = self.book([{'id': 'first', 'keywords': ['测试'], 'content': '甲'*12, 'max_chars': 5},
                          {'id': 'second', 'keywords': ['测试'], 'content': '乙'*12, 'max_chars': 5},
                          {'id': 'third', 'keywords': ['测试'], 'content': '丙'}])
        hits = book.lookup('测试', max_total_chars=8)
        self.assertLessEqual(sum(map(len, hits)), 8)
        self.assertIn('丙', hits)


class AshcombeAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = json.loads(BOOK.read_text(encoding='utf-8'))['entries']
        cls.book = WB.WorldbookService(str(BOOK))

    def test_structure_always_length_and_no_old_character_ids(self):
        self.assertEqual(len(self.book.entries), 132)
        self.assertEqual(len({entry['id'] for entry in self.raw}), 132)
        self.assertEqual([entry['id'] for entry in self.raw if entry.get('always')],
                         ['core-profile', 'appearance', 'time-sense'])
        self.assertTrue(all(len(e['content']) < e.get('max_chars', 800) and len(e['content']) < 800 for e in self.raw))
        source = MODULE_PATH.read_text(encoding='utf-8')
        for forbidden in ['_AMBIENT_KEYWORDS', '_MALE_NPC_ENTRIES', '_FEMALE_NPC_ENTRIES', 'friend-yuebai', 'origin-brother']:
            self.assertNotIn(forbidden, source)

    def test_group_public_replies_and_no_secret_context(self):
        for query in ['家里是做什么的', '今天游戏打得怎么样', '祖父', '你的能力']:
            hits = self.book.lookup(query, stage=0, scope='group')
            self.assertTrue(hits, query)
            for word in ['根源之瞳', '灰灯塔', '主启副躯', '第十三环']:
                self.assertNotIn(word, ''.join(hits), query)
        for query in ['根源之瞳', '灰灯塔', '零点市场', '蜕皮教团']:
            self.assertEqual(self.book.lookup(query, stage=0, scope='group'), [], query)

    def test_organisations_individually_rank_first_at_private_stage_two(self):
        for name in ['零点市场', '蜕皮教团', '星骸猎团', '深锚团', '锈钉会', '织网者', '回声社', '末日钟摆', '棱镜集团', '灰烬之路']:
            hits = self.book.lookup(name, stage=2, scope='private')
            self.assertTrue(hits, name)
            self.assertIn(name, hits[0])

    def test_family_and_eye_secrets_keep_exact_stage_gates(self):
        for stage in range(4):
            self.assertEqual(self.book.lookup('灰灯塔', stage=stage, scope='private'), [])
        self.assertIn('灰灯塔', ''.join(self.book.lookup('灰灯塔', stage=4, scope='private')))
        for stage in range(5):
            self.assertEqual(self.book.lookup('根源之瞳', stage=stage, scope='private'), [])
        self.assertIn('根源之瞳', ''.join(self.book.lookup('根源之瞳', stage=5, scope='private')))

    def test_all_private_topic_pools_nonempty(self):
        for stage in range(6):
            self.assertTrue(self.book.topics(stage=stage, scope='private'), stage)

    def test_legacy_book_retrieval_parity_for_every_entry_and_stage(self):
        # Only compare while a separate original module is available in staging.
        baseline = WORKSPACE / 'worldbook_yila_before.py'
        if not baseline.exists():
            self.skipTest('Baseline parity verified during staging; standalone release has no old module.')
        old = load_module('old_worldbook_compat', baseline).WorldbookService(str(BOOK))
        queries = set(['学校', '朋友', '科技', '你的朋友', '今天游戏打得怎么样', '家里是做什么的'])
        for entry in self.raw:
            queries.update(entry.get('keywords', [])[:3])
        for stage in range(6):
            for scope in ['group', 'private']:
                for query in queries:
                    with self.subTest(stage=stage, scope=scope, query=query):
                        self.assertEqual(self.book.lookup(query, stage=stage, scope=scope),
                                         old.lookup(query, stage=stage, scope=scope))
                self.assertEqual(self.book.always_entries(stage=stage, scope=scope), old.always_entries(stage=stage, scope=scope))
                self.assertEqual(self.book.topics(stage=stage, scope=scope), old.topics(stage=stage, scope=scope))


if __name__ == '__main__':
    unittest.main(verbosity=2)
