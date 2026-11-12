"""Confirmation-only memory correction and owner-only emote preview."""
import re
import threading
import time
from ..memory.repository import cross_scope_enabled
from ..storage.database import normalize_fact

class ExtraCommands:
    def __init__(self, router):
        self.router = router
        self.pending = {}
        self.preview_at = {}
        self.lock = threading.RLock()

    def visible(self, msg, fid, old):
        r = self.router.r
        rows = r.store.list_user_facts(msg.session.as_text(), str(msg.sender_id), limit=100000,
            include_global=r.config.get('memory_cross_group_enabled', True),
            cross_scope=cross_scope_enabled(r.config, msg.is_group))
        return any(x['id'] == fid and x['fact'] == old and str(x['user_id']) == str(msg.sender_id) for x in rows)

    def status_reason(self, msg):
        renderer = self.router.r.renderer
        if not self.router.r.config.get('emote_enabled', True):
            return '当前自动表情：已关闭。'
        session, now = msg.session.as_text(), time.time()
        if renderer._emote_allowed(session, now):
            return '当前自动表情：额度允许发送（仍由模型选择是否使用）。'
        reasons = []
        gap = renderer._cfg_num('emote_min_gap_seconds', 180)
        cap = renderer._cfg_num('emote_hourly_cap', 6)
        window = renderer._cfg_num('emote_window_replies', 5)
        with renderer._lock:
            stamps = list(renderer._emote_at.get(session, []))
            recent = list(renderer._recent_replies.get(session, []))
        if stamps and now-stamps[-1] < gap:
            reasons.append('冷却未结束')
        if sum(now-stamp < 3600 for stamp in stamps) >= cap:
            reasons.append('每小时额度已满')
        if any(recent[-window:]):
            reasons.append('近期回复已发过表情')
        return '当前自动表情被拦下：' + '、'.join(reasons or ['会话节流']) + '。'

    def handle(self, msg, text):
        key = self.router._memory_page_key(msg)
        r = self.router.r
        if text.startswith('修正记忆') or text in ('确认修正', '取消修正'):
            with self.lock:
                if text == '取消修正':
                    self.pending.pop(key, None)
                    return '已取消记忆修正。'
                if text == '确认修正':
                    item = self.pending.pop(key, None)
                    if not item or time.time()-item[0] > 300:
                        return '没有待确认修正或已过5分钟，请重新查看记忆并发起修正。'
                    _, fid, old, new = item
                    if not self.visible(msg, fid, old):
                        return '原记忆已变化、删除或不再可见，本次未修改，请重新查看记忆。'
                    cur = r.store._conn().execute(
                        'UPDATE user_facts SET fact=?, fact_norm=?, keywords=? WHERE id=? AND user_id=? AND fact=? AND valid_to=0',
                        (new, normalize_fact(new), '', fid, str(msg.sender_id), old))
                    if cur.rowcount != 1:
                        return '原记忆已变化，本次未修改，请重新查看记忆。'
                    self.router._memory_pages.pop(key, None)
                    return '✅ 已修正记忆：' + new
                match = re.fullmatch(r'修正记忆\s+(\d+)\s+([\s\S]+)', text)
                if not match:
                    return '格式：伊菈修正记忆 编号 新内容。只支持记忆页带编号的事实，印象和摘要不支持。'
                page = self.router._memory_page(msg)
                n, new = int(match[1]), match[2].strip()
                if not page or not 1 <= n <= len(page):
                    return '编号无效或过期，请先发「伊菈记忆」。印象和摘要不能按编号修正。'
                if not new or len(new) > 500 or '[' in new or '【' in new:
                    return '新内容限1～500字普通文本，不要包含控制标记。'
                fid, old = page[n-1]
                if not self.visible(msg, fid, old):
                    return '只能修正当前会话可见且属于你自己的有效事实，请重新查看记忆。'
                now = time.time()
                self.pending = {k:v for k,v in self.pending.items() if now-v[0] <= 300}
                self.pending[key] = (now, fid, old, new)
                return f'待确认修正（尚未写入）：\n原内容：{old}\n新内容：{new}\n5分钟内发「伊菈确认修正」或「伊菈取消修正」。'
        if text == '表情列表' or text.startswith('预览表情'):
            if not r.permissions.is_master(msg):
                return '这个只有骰主或主人能用哦~'
            if text == '表情列表':
                available = {n for n,_ in r.renderer.available_emotes()}
                lines = ['--- 表情列表 ---']
                lines += [f'{name}：{entry.get("desc", "")}'+('（缺图）' if name not in available else '') for name,entry in r.renderer.emote_table.items()]
                return '\n'.join(lines + ['预览：伊菈预览表情 名称', self.router._cmd_emote_status(msg)])
            name = text[len('预览表情'):].strip()
            if name not in r.renderer.emote_table:
                return '表情名称无效，请先发「伊菈表情列表」。'
            path = r.renderer._find_emote(name)
            if path is None:
                return '这张表情缺图，暂时无法预览。'
            with self.lock:
                session = msg.session.as_text()
                if time.time()-self.preview_at.get(session, 0) < 15:
                    return '预览太快了，请稍等15秒再试。'
                self.preview_at[session] = time.time()
            return f'[CQ:image,file=file:///{path.resolve()}]'
        return None
