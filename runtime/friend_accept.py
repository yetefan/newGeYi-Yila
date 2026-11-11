# -*- encoding: utf-8 -*-
"""自动同意好友申请：补上「协议端不推申请事件」的那个缺口。

为什么需要（2026-11-11 实测）：LLBot 在有头模式 + PMHQ 下，好友申请不会被当成
申请事件推给 OlivOS，于是青果（OlivaDice）的 autoAcceptFriendAdd 一次都不会触发，
开关开着也没用。LLBot 自己的网页接口能列出待处理申请、也能直接同意，
所以这里定时去问一次，代替那个不来的事件。

只处理「普通好友申请」：QQ 判成风险账号的那份（被过滤申请，存在另一份名单里）
一律不碰，那些仍然要骰主自己到 LLBot 网页里点。

安全边界：
- 只认 reqType=1（对方加我、等我同意）。已同意、已拒绝、我发起的、已忽略都不碰，
  免得把别的状态顶掉。
- 同一个 flag 只同意一次，失败不重试，避免反复戳接口。
- 默认关闭。
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
import urllib.error
import urllib.request

logger = logging.getLogger('newGeYi.friend_accept')

# 对方加我、还没处理。其余状态见 LLBot 的 FriendReqType。
PEER_INITIATOR = 1

# 启动后先等一会儿：OlivOS 自己还没登录完的时候去问也没有意义。
STARTUP_DELAY = 30.0
# 最短轮询间隔：再短就是白戳接口，还容易被对方风控。
MIN_INTERVAL = 20.0


class FriendAutoAcceptor:
    def __init__(self, config: dict):
        self.config = config
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._approved: set[str] = set()
        self._last_run_at = 0.0
        self._last_error = ''
        self._total_approved = 0

    # ==================== 配置 ====================
    def enabled(self) -> bool:
        return bool(self.config.get('friend_auto_accept', False))

    def _base_url(self) -> str:
        raw = str(self.config.get('llbot_webui_url') or 'http://127.0.0.1:3080').strip()
        return raw.rstrip('/') or 'http://127.0.0.1:3080'

    def _headers(self) -> dict:
        """LLBot 网页接口要的是**密码的 sha256**，不是密码本身。"""
        raw = str(self.config.get('llbot_webui_token') or '').strip()
        token = hashlib.sha256(raw.encode('utf-8')).hexdigest() if raw else ''
        return {'X-Webui-Token': token, 'Content-Type': 'application/json'}

    def _interval(self) -> float:
        try:
            return max(MIN_INTERVAL, float(self.config.get('friend_auto_interval', 120) or 120))
        except (TypeError, ValueError):
            return 120.0

    # ==================== HTTP ====================
    def _get(self, path: str) -> dict:
        request = urllib.request.Request(self._base_url() + path, headers=self._headers())
        with urllib.request.urlopen(request, timeout=8) as response:
            return json.loads(response.read().decode('utf-8'))

    def _post(self, path: str, payload: dict) -> dict:
        request = urllib.request.Request(
            self._base_url() + path, data=json.dumps(payload).encode('utf-8'),
            headers=self._headers(), method='POST')
        with urllib.request.urlopen(request, timeout=8) as response:
            return json.loads(response.read().decode('utf-8'))

    # ==================== 主流程 ====================
    def pending(self) -> list:
        """还没处理、且是「对方加我」的普通申请。被过滤的那份不在这里。"""
        rows = (self._get('/api/webqq/notifications/friend') or {}).get('data') or []
        out = []
        for row in rows:
            if not isinstance(row, dict) or row.get('isDecide'):
                continue
            try:
                if int(row.get('reqType') or 0) != PEER_INITIATOR:
                    continue
            except (TypeError, ValueError):
                continue
            flag = str(row.get('flag') or '')
            if flag and flag not in self._approved:
                out.append(row)
        return out

    def run_once(self) -> list:
        """走一轮：拉申请 -> 同意。返回这一轮真的同意了的人。"""
        approved = []
        for row in self.pending():
            flag = str(row.get('flag') or '')
            uin = str(row.get('friendUin') or '')
            nick = str(row.get('friendNick') or '')
            try:
                self._post('/api/webqq/notifications/friend/handle',
                           {'flag': flag, 'action': 'approve'})
            except Exception as exc:  # noqa: BLE001 - 单条失败不影响下一轮
                self._last_error = '%s: %s' % (type(exc).__name__, exc)
                logger.warning('同意好友申请失败（%s）：%s', uin or nick, exc)
                continue
            self._approved.add(flag)
            self._total_approved += 1
            approved.append({'uin': uin, 'nick': nick})
            logger.info('已自动同意好友申请：%s（%s）', nick or '未知昵称', uin or '未知号码')
        self._last_run_at = time.time()
        self._last_error = ''
        return approved

    # ==================== 后台线程 ====================
    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name='geyi-friend-auto', daemon=True)
        self._thread.start()
        logger.info('自动同意好友线程已启动（开关：%s）', '开' if self.enabled() else '关')

    def stop(self) -> None:
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=3)

    def _loop(self) -> None:
        if self._stop.wait(STARTUP_DELAY):
            return
        while not self._stop.is_set():
            if self.enabled():
                try:
                    self.run_once()
                except Exception:  # noqa: BLE001 - 后台线程绝不带着异常退出
                    logger.exception('自动同意好友这一轮失败')
            if self._stop.wait(self._interval()):
                return

    # ==================== 给命令看 ====================
    def status_text(self) -> str:
        lines = ['自动同意好友: ' + ('开' if self.enabled() else '关')]
        lines.append('轮询间隔: %d 秒 | LLBot: %s' % (self._interval(), self._base_url()))
        if not str(self.config.get('llbot_webui_token') or '').strip():
            lines.append('⚠ 没填 llbot_webui_token，读不到申请列表')
        if self._last_run_at:
            when = time.strftime('%m-%d %H:%M', time.localtime(self._last_run_at))
            lines.append('上次检查: %s | 累计同意 %d 人' % (when, self._total_approved))
        else:
            lines.append('上次检查: 还没跑过')
        if self._last_error:
            lines.append('上次出错: ' + self._last_error)
        lines.append('只同意普通申请；QQ 判成风险账号的那份仍然要手动点。')
        return '\n'.join(lines)
