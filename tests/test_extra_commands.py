"""Offline tests using only an in-memory SQLite database and a fake runtime."""
import importlib.util
import sqlite3
import sys
import threading
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch

# Load helper without importing plugin __init__ (which constructs Runtime).
_PACKAGE = '_extra_command_test'
for name in (_PACKAGE, _PACKAGE+'.routing', _PACKAGE+'.memory', _PACKAGE+'.storage'):
    pkg=types.ModuleType(name); pkg.__path__=[]; sys.modules[name]=pkg
repo=types.ModuleType(_PACKAGE+'.memory.repository')
repo.cross_scope_enabled=lambda config, group: False
sys.modules[repo.__name__]=repo
db_path=Path(__file__).resolve().parents[1]/'storage'/'database.py'
if not db_path.exists(): db_path=Path(r'E:\dice\newGeYi\storage\database.py')
db_spec=importlib.util.spec_from_file_location(_PACKAGE+'.storage.database',db_path)
db_module=importlib.util.module_from_spec(db_spec); db_spec.loader.exec_module(db_module)
sys.modules[db_spec.name]=db_module
path=Path(__file__).resolve().parents[1]/'routing'/'extra_commands.py'
if not path.exists(): path=Path(__file__).with_name('extra_commands.py')
spec=importlib.util.spec_from_file_location(_PACKAGE+'.routing.extra_commands',path)
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)

class ExtraTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:',isolation_level=None)
        self.db.execute('CREATE TABLE user_facts(id INTEGER, user_id TEXT, fact TEXT, keywords TEXT, valid_to INTEGER, session_key TEXT, fact_norm TEXT)')
        self.db.execute("INSERT INTO user_facts VALUES(1,'10','旧内容','旧关键词',0,'group:1',?)", (db_module.normalize_fact('旧内容'),))
        db=self.db
        class Store:
            def _conn(self): return db
            def list_user_facts(self, session, uid, **kw):
                return [dict(id=x[0],user_id=x[1],fact=x[2]) for x in db.execute('SELECT id,user_id,fact FROM user_facts WHERE session_key=? AND user_id=? AND valid_to=0',(session,uid))]
        self.msg=types.SimpleNamespace(sender_id='10',is_group=True,session=types.SimpleNamespace(as_text=lambda:'group:1'))
        self.pages={'10|group:1':[(1,'旧内容')]}
        self.master=True
        self.path=Path(__file__)
        renderer=types.SimpleNamespace(emote_table={'开心':{'desc':'开心时用'},'缺图':{'desc':''}}, available_emotes=lambda:[('开心','开心时用')], _find_emote=lambda name:self.path if name=='开心' else None)
        runtime=types.SimpleNamespace(config={},store=Store(),renderer=renderer,permissions=types.SimpleNamespace(is_master=lambda m:self.master))
        router=types.SimpleNamespace(r=runtime,_memory_pages=self.pages,_memory_page_key=lambda m:m.sender_id+'|'+m.session.as_text(),_memory_page=lambda m:self.pages.get(m.sender_id+'|'+m.session.as_text()),_cmd_emote_status=lambda m:'开关:开 冷却180秒 每小时6张 最近5条')
        self.helper=module.ExtraCommands(router)
    def tearDown(self): self.db.close()
    def fact(self): return self.db.execute('SELECT fact FROM user_facts WHERE id=1').fetchone()[0]
    def test_confirmation_required_and_sql_text_is_literal(self):
        new="喜欢 '茶'; DROP TABLE user_facts; --"
        result=self.helper.handle(self.msg,'修正记忆 1 '+new)
        self.assertIn('旧内容',result); self.assertIn(new,result); self.assertEqual(self.fact(),'旧内容')
        self.assertIn('已修正',self.helper.handle(self.msg,'确认修正')); self.assertEqual(self.fact(),new)
        self.assertNotIn('10|group:1',self.pages)
        by_new = self.db.execute('SELECT fact FROM user_facts WHERE fact_norm=?', (db_module.normalize_fact(new),)).fetchone()
        self.assertEqual(by_new[0], new)
        self.assertIsNone(self.db.execute('SELECT id FROM user_facts WHERE fact_norm=?', (db_module.normalize_fact('旧内容'),)).fetchone())
        self.assertEqual(self.db.execute('SELECT keywords FROM user_facts').fetchone()[0], '')
    def test_cancel_and_expiry_never_write(self):
        self.helper.handle(self.msg,'修正记忆 1 新内容'); self.helper.handle(self.msg,'取消修正')
        self.assertIn('没有待确认',self.helper.handle(self.msg,'确认修正'))
        self.helper.handle(self.msg,'修正记忆 1 新内容')
        with patch.object(module.time,'time',return_value=time.time()+301): self.assertIn('5分钟',self.helper.handle(self.msg,'确认修正'))
        self.assertEqual(self.fact(),'旧内容')
    def test_sender_and_session_binding(self):
        self.helper.handle(self.msg,'修正记忆 1 新内容')
        self.msg.sender_id='20'; self.assertIn('没有待确认',self.helper.handle(self.msg,'确认修正'))
        self.msg.sender_id='10'; self.msg.session.as_text=lambda:'group:2'
        self.assertIn('没有待确认',self.helper.handle(self.msg,'确认修正')); self.assertEqual(self.fact(),'旧内容')
    def test_changed_expired_and_other_owner_rejected(self):
        for sql in ["UPDATE user_facts SET fact='被别人改了'",'UPDATE user_facts SET valid_to=1',"UPDATE user_facts SET user_id='20'"]:
            self.db.execute("UPDATE user_facts SET fact='旧内容',valid_to=0,user_id='10'")
            self.helper.handle(self.msg,'修正记忆 1 新内容'); self.db.execute(sql)
            self.assertIn('未修改',self.helper.handle(self.msg,'确认修正'))
    def test_nonfact_and_bad_index(self):
        self.assertIn('印象和摘要',self.helper.handle(self.msg,'修正记忆 印象 新内容'))
        self.assertIn('编号无效',self.helper.handle(self.msg,'修正记忆 2 新内容'))
    def test_status_reports_each_existing_renderer_limit(self):
        renderer = self.helper.router.r.renderer
        renderer._lock = threading.Lock()
        renderer._cfg_num = lambda key, default: default
        renderer._emote_allowed = lambda *args: False
        renderer._emote_at = {'group:1':[time.time()]*6}
        renderer._recent_replies = {'group:1':[True]}
        reason = self.helper.status_reason(self.msg)
        for text in ('冷却未结束', '每小时额度已满', '近期回复已发过表情'):
            self.assertIn(text, reason)
        renderer._emote_allowed = lambda *args: True
        self.assertIn('允许发送', self.helper.status_reason(self.msg))
        self.helper.router.r.config['emote_enabled'] = False
        self.assertIn('已关闭', self.helper.status_reason(self.msg))

    def test_preview_permissions_missing_and_throttle(self):
        self.master=False; self.assertIn('只有',self.helper.handle(self.msg,'预览表情 开心'))
        self.master=True; self.assertIn('缺图',self.helper.handle(self.msg,'预览表情 缺图'))
        self.assertIn('[CQ:image',self.helper.handle(self.msg,'预览表情 开心'))
        self.assertIn('15秒',self.helper.handle(self.msg,'预览表情 开心'))
        self.assertIn('冷却',self.helper.handle(self.msg,'表情列表'))

if __name__=='__main__': unittest.main()
