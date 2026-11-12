# -*- encoding: utf-8 -*-
"""表情回应：群里她决定要回一条消息时（被点名，或自己主动搭话），先贴一个表情表示「收到了」。

为什么单独走 HTTP，不走 OlivOS：表情回应（set_msg_emoji_like）是 LLBot / NapCat
这一类接入端自己加的接口，标准 OneBot 和 OlivOS 都没有。本机 LLBot 在
127.0.0.1:3000 开了 HTTP 服务端，这里直接调它。

只对群聊生效：LLBot 这个接口自己就只支持群消息，私聊调用会直接报错。
贴失败只写日志，绝不影响回复主流程。
"""

from __future__ import annotations

import json
import logging
import random
import threading
import urllib.error
import urllib.request
from urllib.parse import urlsplit, urlunsplit

logger = logging.getLogger('newGeYi.reactions')

# QQ 经典表情：爱心 / 玫瑰 / 太阳 / 月亮。编号是常用对照表里的，
# 2026-11-12 用 66 在群里实测过，贴上和撤掉都成功。
DEFAULT_EMOJI_IDS = ['66', '63', '74', '75']


class ReactionClient:
    def __init__(self, config: dict):
        self.config = config

    def enabled(self) -> bool:
        return bool(self.config.get('reaction_enabled', False))

    def _url(self) -> str:
        raw = str(self.config.get('reaction_http_url') or '').strip().rstrip('/')
        if not raw:
            # 没单独配就借用语音直发的地址（同一个 LLBot HTTP 服务）
            raw = str(self.config.get('voice_onebot_http_url') or '').strip().rstrip('/')
        if not raw:
            return ''
        parts = urlsplit(raw)
        path = parts.path.rstrip('/')
        # 语音配置可能是完整动作地址；替换动作，保留查询参数中的 access_token。
        for action in ('send_msg', 'send_group_msg', 'send_private_msg', 'set_msg_emoji_like'):
            if path.endswith('/' + action):
                path = path[:-(len(action) + 1)]
                break
        return urlunsplit((parts.scheme, parts.netloc, path + '/set_msg_emoji_like',
                           parts.query, ''))

    def _emoji_ids(self) -> list[str]:
        raw = self.config.get('reaction_emoji_ids')
        if isinstance(raw, list) and raw:
            ids = [str(item).strip() for item in raw if str(item).strip()]
            if ids:
                return ids
        return list(DEFAULT_EMOJI_IDS)

    def react(self, msg, reason: str) -> bool:
        """给这条群消息贴一个随机表情。不该贴、或贴失败都返回 False。"""
        if not self.enabled():
            return False
        if not getattr(msg, 'is_group', False):
            return False
        message_id = str(getattr(msg, 'message_id', '') or '').strip()
        if not message_id:
            return False
        base = self._url()
        if not base:
            logger.warning('表情回应没配地址（reaction_http_url），跳过 | %s', reason)
            return False
        emoji_id = random.choice(self._emoji_ids())
        payload = json.dumps({'message_id': message_id, 'emoji_id': emoji_id}).encode('utf-8')
        headers = {'Content-Type': 'application/json'}
        token = str(self.config.get('reaction_access_token') or (
            self.config.get('voice_onebot_access_token') if not self.config.get('reaction_http_url')
            else '') or '').strip()
        if token:
            headers['Authorization'] = 'Bearer ' + token
        request = urllib.request.Request(base, data=payload, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                body = json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as exc:
            logger.warning('表情回应被拒（HTTP %s，%s）| msg=%s', exc.code, reason, message_id)
            return False
        except Exception as exc:  # noqa: BLE001 - 贴表情失败绝不能影响主流程
            logger.warning('表情回应失败（%s: %s，%s）| msg=%s',
                           type(exc).__name__, exc, reason, message_id)
            return False
        if isinstance(body, dict) and (body.get('status') == 'ok' or body.get('retcode') == 0):
            logger.info('已贴表情回应 %s（%s）| msg=%s', emoji_id, reason, message_id)
            return True
        logger.warning('表情回应接口返回异常（%s）：%s | msg=%s', reason, body, message_id)
        return False

    def react_async(self, msg, reason: str) -> None:
        """后台贴：HTTP 最多等 5 秒，不能挡在消息处理的路上。"""
        if not self.enabled() or not getattr(msg, 'is_group', False):
            return
        threading.Thread(target=self.react, args=(msg, reason), daemon=True).start()
