"""Local topic participation hints; no model calls and no long-term storage."""
from collections import deque
import re
import threading
import time


def topic_terms(text):
    text = re.sub(r'\[(?:OP|CQ):[^\]]*\]', ' ', str(text or '')).casefold()
    words = set(re.findall(r'[a-z0-9]{2,}', text))
    for chunk in re.findall(r'[\u4e00-\u9fff]+', text):
        words.update(chunk[i:i+2] for i in range(len(chunk)-1))
    return words


def related(left, right):
    return bool(left and right and len(left & right) / min(len(left), len(right)) >= 0.35)


class TopicParticipation:
    def __init__(self, config):
        self.config = config
        self._lock = threading.Lock()
        self._recent = {}

    def _prune(self, now):
        for key in list(self._recent):
            rows = self._recent[key]
            while rows and now - rows[0][0] >= 1800:
                rows.popleft()
            if not rows:
                del self._recent[key]

    def factor(self, session, text, recent=()):
        if not self.config.get('active_topic_enabled', True):
            return 1.0, '话题调节关闭'
        terms = topic_terms(text)
        if len(terms) < 2:
            return 1.0, '文本不足，沿用原概率'
        now = time.monotonic()
        cooldown = float(self.config.get('active_topic_cooldown_seconds', 180))
        with self._lock:
            self._prune(now)
            rows = list(self._recent.get(session, ()))
        for stamp, previous in reversed(rows):
            if now - stamp < cooldown and related(terms, previous):
                return 0.25, '近期已参与相近话题，减少重复插话'
        # Real recent assistant turn plus lexical overlap, rather than every group reply.
        for turn in list(recent)[-3:]:
            if turn.get('role') == 'assistant' and related(terms, topic_terms(turn.get('content', ''))):
                return 1.25, '群友正在接她刚才的话'
        if rows and not any(related(terms, previous) for _, previous in rows):
            return 1.15, '话题已变化'
        return 1.0, '沿用原概率'

    def note_spoken(self, session, trigger, reply):
        now = time.monotonic()
        terms = topic_terms(trigger) | topic_terms(reply)
        if not terms:
            return
        with self._lock:
            self._prune(now)
            self._recent.setdefault(session, deque(maxlen=8)).append((now, terms))
