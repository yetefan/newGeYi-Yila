"""Bounded background evaluation: a passive message can take over its session.

An HTTP call already sent cannot be unsent. Its result is discarded when yielding;
only model generation runs here, never sending messages or recording a reply.
"""
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import threading


class ActiveRequests:
    def __init__(self, limit=2):
        self._pool = ThreadPoolExecutor(max_workers=limit, thread_name_prefix='geyi-active')
        self._slots = threading.BoundedSemaphore(limit)
        self._lock = threading.Lock()
        self._sessions = set()
        self._closed = False

    def call(self, session, generate, should_yield, cancel_event=None):
        with self._lock:
            if self._closed or session in self._sessions or not self._slots.acquire(blocking=False):
                return None
            self._sessions.add(session)
        try:
            future = self._pool.submit(generate)
        except Exception:
            self._release(session)
            raise
        future.add_done_callback(lambda _: self._release(session))
        while True:
            if should_yield():
                if cancel_event is not None:
                    cancel_event.set()
                future.cancel()
                return None
            try:
                result = future.result(timeout=0.05)
                if should_yield():
                    if cancel_event is not None:
                        cancel_event.set()
                    return None
                return result
            except TimeoutError:
                if future.done():
                    # A model implementation itself raised TimeoutError.
                    return future.result()

    def _release(self, session):
        with self._lock:
            self._sessions.discard(session)
        self._slots.release()

    def shutdown(self):
        with self._lock:
            self._closed = True
        self._pool.shutdown(wait=False, cancel_futures=True)
