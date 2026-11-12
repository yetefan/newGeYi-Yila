"""Offline regressions for conversation windows, priority and topic participation."""
import os
import tempfile
os.environ.setdefault('GEYI_DATA_DIR', tempfile.mkdtemp(prefix='yila_features_'))
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from newGeYi.runtime.private_gate import PrivateGate
from newGeYi.runtime.active_requests import ActiveRequests
from newGeYi.routing.topic_participation import TopicParticipation
from newGeYi.tests.test_private_gate import make_private_msg, BASE_CFG
from newGeYi.tests.test_scheduler import FakeRuntime, SessionScheduler, make_msg

class Store:
    def __init__(self): self.rows = {}
    def get_setting(self, key): return self.rows.get(key)
    def set_setting(self, key, value): self.rows[key] = value

class PrivateWindowTest(unittest.TestCase):
    def setUp(self):
        self.config = dict(BASE_CFG, private_trigger_only=True, private_session_idle_seconds=600)
        self.gate = PrivateGate(Store(), self.config)
        self.msg = make_private_msg('u1', '伊菈在吗')
        self.follow = make_private_msg('u1', '今天好累')
        self.key = self.msg.session.as_text()

    def test_window_renews_on_user_activity_and_expires_at_boundary(self):
        with patch('newGeYi.runtime.private_gate.time.monotonic', return_value=0):
            self.assertTrue(self.gate.allow(self.msg)[0])
            self.gate.commit(self.key)
        with patch('newGeYi.runtime.private_gate.time.monotonic', return_value=599):
            self.assertTrue(self.gate.allow(self.follow)[0])
        with patch('newGeYi.runtime.private_gate.time.monotonic', return_value=1198):
            self.assertTrue(self.gate.dialogue_open(self.key))
        with patch('newGeYi.runtime.private_gate.time.monotonic', return_value=1199):
            self.assertEqual(self.gate.allow(self.follow), (False, 'trigger'))

    def test_keyword_check_alone_does_not_open_or_share_window(self):
        self.assertTrue(self.gate.allow(self.msg)[0])
        self.assertFalse(self.gate.addressed(self.follow))
        self.gate.commit(self.key)
        self.assertFalse(self.gate.addressed(make_private_msg('u2', '今天好累')))

    def test_window_keeps_quotas_and_rate_limits(self):
        self.config['private_daily_quota'] = 1
        self.gate.commit(self.key)
        self.assertEqual(self.gate.allow(self.follow), (False, 'quota_user'))
        self.config['private_daily_quota'] = 0
        self.config['private_min_interval'] = 10
        self.assertEqual(self.gate.allow(self.follow), (False, 'interval'))

    def test_reply_renews_existing_window_but_cannot_reopen_expired_one(self):
        with patch('newGeYi.runtime.private_gate.time.monotonic', return_value=0):
            self.gate.commit(self.key)
        with patch('newGeYi.runtime.private_gate.time.monotonic', return_value=590):
            self.gate.note_activity(self.key)
        with patch('newGeYi.runtime.private_gate.time.monotonic', return_value=1189):
            self.assertTrue(self.gate.dialogue_open(self.key))
        with patch('newGeYi.runtime.private_gate.time.monotonic', return_value=1190):
            self.gate.note_activity(self.key)
            self.assertFalse(self.gate.dialogue_open(self.key))

    def test_zero_disables_window(self):
        self.config['private_session_idle_seconds'] = 0
        self.gate.commit(self.key)
        self.assertFalse(self.gate.addressed(self.follow))

class PriorityTest(unittest.TestCase):
    def test_pending_active_is_removed_and_passive_order_is_preserved(self):
        release = threading.Event()
        rt = FakeRuntime({'incomplete_hold_seconds': 0, 'max_pending_per_session': 1}, block=release)
        scheduler = SessionScheduler(rt)
        try:
            self.assertTrue(scheduler.submit(make_msg('running'), 'active'))
            self.assertTrue(rt.entered.wait(1))
            self.assertTrue(scheduler.submit(make_msg('obsolete'), 'active'))
            self.assertTrue(scheduler.submit(make_msg('important'), 'passive'))
            self.assertFalse(scheduler.submit(make_msg('another-active'), 'active'))
            key = make_msg('x').session.as_text()
            self.assertTrue(scheduler.passive_waiting(key))
            with scheduler._lock:
                self.assertEqual([(m.text, k) for m,k in scheduler._states[key].pending], [('important', 'passive')])
        finally:
            release.set()
            scheduler.shutdown()

    def test_inflight_evaluation_yields_without_waiting_for_http(self):
        pool = ActiveRequests(limit=1)
        entered = threading.Event(); release = threading.Event(); urgent = threading.Event(); finished = threading.Event()
        output = []
        def model():
            entered.set()
            release.wait(2)
            return 'discard this old result'
        def evaluate():
            output.append(pool.call('group-a', model, urgent.is_set))
            finished.set()
        worker = threading.Thread(target=evaluate)
        worker.start()
        try:
            self.assertTrue(entered.wait(1))
            urgent.set()
            self.assertTrue(finished.wait(1), 'priority is still blocked by the HTTP call')
            self.assertEqual(output, [None])
            self.assertIsNone(pool.call('group-a', lambda: 'duplicate', lambda: False))
            self.assertIsNone(pool.call('group-b', lambda: 'over limit', lambda: False))
        finally:
            release.set(); worker.join(2); pool.shutdown()

class TopicTest(unittest.TestCase):
    def test_repeated_topic_is_reduced_and_new_topic_gets_small_boost(self):
        policy = TopicParticipation({})
        policy.note_spoken('a', '今晚吃火锅', '火锅真好吃')
        self.assertEqual(policy.factor('a', '今晚吃火锅')[0], 0.25)
        self.assertEqual(policy.factor('a', '明天打游戏')[0], 1.15)
        self.assertEqual(policy.factor('b', '今晚吃火锅')[0], 1.0)

    def test_followup_uses_recent_assistant_turn(self):
        policy = TopicParticipation({})
        self.assertEqual(policy.factor('a', '火锅真的好吃', [{'role':'assistant','content':'火锅真的好吃'}])[0], 1.25)

    def test_short_text_and_disabled_policy_do_not_change_probability(self):
        policy = TopicParticipation({})
        self.assertEqual(policy.factor('a', '嗯')[0], 1.0)
        policy.config['active_topic_enabled'] = False
        policy.note_spoken('a', '今晚吃火锅', '火锅真好吃')
        self.assertEqual(policy.factor('a', '今晚吃火锅')[0], 1.0)

    def test_same_topic_can_return_after_cooldown(self):
        policy = TopicParticipation({'active_topic_cooldown_seconds': 180})
        with patch('newGeYi.routing.topic_participation.time.monotonic', return_value=0):
            policy.note_spoken('a', '今晚吃火锅', '火锅真好吃')
        with patch('newGeYi.routing.topic_participation.time.monotonic', return_value=181):
            self.assertEqual(policy.factor('a', '今晚吃火锅')[0], 1.0)

class CancelledGatewayTest(unittest.TestCase):
    def test_cancelled_before_start_sends_nothing(self):
        from newGeYi.tests.test_gateway_failover import build
        from newGeYi.models import ModelRequest
        gw, store, session, notes = build()
        event = threading.Event(); event.set()
        result = gw.chat(ModelRequest(messages=[], model='x', cancel_event=event), kind='active')
        self.assertEqual(result.error_code, 'cancelled')
        self.assertEqual(session.posts, [])
        self.assertEqual(notes, [])

    def test_yielding_during_http_does_not_retry_or_mark_provider_down(self):
        from newGeYi.tests.test_gateway_failover import build, FakeResp
        from newGeYi.models import ModelRequest
        gw, store, session, notes = build()
        gw.config['max_retries'] = 2
        event = threading.Event()
        def respond(*args, **kwargs):
            session.posts.append('one request')
            event.set()
            return FakeResp(500)
        session.post = respond
        with patch('newGeYi.providers.llm_gateway.time.sleep'):
            result = gw.chat(ModelRequest(messages=[], model='x', cancel_event=event), kind='active')
        self.assertEqual(result.error_code, 'cancelled')
        self.assertEqual(len(session.posts), 1)
        self.assertEqual(notes, [])
        self.assertEqual(gw._hold_name, '')
        self.assertEqual(store.api_calls, [])

if __name__ == '__main__': unittest.main()
