"""Reaction HTTP contract tests; no plugin startup, database or real network."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch, MagicMock

spec = importlib.util.spec_from_file_location('reaction_under_test', Path(__file__).resolve().parents[1] / 'runtime' / 'reactions.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class ReactionTests(unittest.TestCase):
    def test_base_and_action_urls_preserve_token_query(self):
        for raw in ['http://127.0.0.1:3000', 'http://127.0.0.1:3000/send_msg',
                    'http://127.0.0.1:3000/set_msg_emoji_like']:
            client = module.ReactionClient({'reaction_http_url': raw + '?access_token=test'})
            self.assertEqual(client._url(), 'http://127.0.0.1:3000/set_msg_emoji_like?access_token=test')

    def test_prefix_path_is_preserved(self):
        client = module.ReactionClient({'reaction_http_url': 'http://localhost/api/send_msg/'})
        self.assertEqual(client._url(), 'http://localhost/api/set_msg_emoji_like')

    def test_voice_url_and_token_fallback(self):
        client = module.ReactionClient({'reaction_enabled': True,
            'voice_onebot_http_url': 'http://localhost/send_msg', 'voice_onebot_access_token': 'test-token'})
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"retcode":0}'
        with patch.object(module.urllib.request, 'urlopen', return_value=response) as opened:
            self.assertTrue(client.react(SimpleNamespace(is_group=True, message_id='-123'), 'test'))
        req = opened.call_args.args[0]
        self.assertEqual(req.full_url, 'http://localhost/set_msg_emoji_like')
        self.assertEqual(req.get_header('Authorization'), 'Bearer test-token')
        self.assertEqual(json.loads(req.data)['message_id'], '-123')

    def test_separate_endpoint_does_not_inherit_voice_token(self):
        client = module.ReactionClient({'reaction_enabled': True,
            'reaction_http_url': 'http://localhost:3000', 'voice_onebot_access_token': 'voice-token'})
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"status":"ok"}'
        with patch.object(module.urllib.request, 'urlopen', return_value=response) as opened:
            client.react(SimpleNamespace(is_group=True, message_id='1'), 'test')
        self.assertIsNone(opened.call_args.args[0].get_header('Authorization'))

    def test_private_disabled_and_missing_id_make_no_request(self):
        with patch.object(module.urllib.request, 'urlopen') as opened:
            client = module.ReactionClient({'reaction_enabled': True})
            self.assertFalse(client.react(SimpleNamespace(is_group=False, message_id='1'), 'test'))
            self.assertFalse(client.react(SimpleNamespace(is_group=True, message_id=''), 'test'))
            self.assertFalse(module.ReactionClient({}).react(SimpleNamespace(is_group=True, message_id='1'), 'test'))
        opened.assert_not_called()

    def test_network_failure_is_nonfatal(self):
        client = module.ReactionClient({'reaction_enabled': True, 'reaction_http_url': 'http://localhost'})
        with patch.object(module.urllib.request, 'urlopen', side_effect=TimeoutError):
            self.assertFalse(client.react(SimpleNamespace(is_group=True, message_id='1'), 'test'))

if __name__ == '__main__':
    unittest.main()
