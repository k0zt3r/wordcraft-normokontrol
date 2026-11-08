"""MCP transport/lifecycle tests independent of Wordcraft or GUI availability."""
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import agent_mcp


TOOLS = [{'name': 'doctor', 'description': 'Check environment',
          'inputSchema': {'type': 'object'}, 'outputSchema': {'type': 'object'},
          'annotations': {'readOnlyHint': True}}]


def request(method, params=None, request_id=1):
    return {'jsonrpc': '2.0', 'id': request_id, 'method': method, 'params': params or {}}


def initialize(server, protocol='2025-11-25'):
    reply = server.handle(request('initialize', {'protocolVersion': protocol,
        'capabilities': {}, 'clientInfo': {'name': 'tests', 'version': '1'}}))
    server.handle({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
    return reply


class MCPTests(unittest.TestCase):
    def test_root_launcher_from_another_directory_with_real_api(self):
        """Exercise package imports, UTF-8 pipes and discovery without mocks."""
        root = Path(__file__).resolve().parent.parent
        for version in ('2024-11-05', '2025-11-25'):
            with self.subTest(version=version), tempfile.TemporaryDirectory(prefix='mcp-client-') as folder:
                messages = [
                    request('initialize', {'protocolVersion': version, 'capabilities': {},
                                          'clientInfo': {'name': 'subprocess-tests', 'version': '1'}}),
                    {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                    request('tools/list', request_id=2),
                    request('tools/call', {'name': 'get_capabilities'}, 3),
                    request('tools/call', {'name': 'get_requirement',
                                          'arguments': {'reference': '6.2', 'search': 'шифр'}}, 4),
                    request('tools/call', {'name': 'get_requirement',
                                          'arguments': {'reference': 6.2}}, 5),
                    request('tools/call', {'name': 'does_not_exist'}, 6),
                    request('ping', request_id=7),
                ]
                process = subprocess.run(
                    [sys.executable, '-X', 'utf8', str(root / 'normokontrol.py'), '--mcp'],
                    cwd=folder, input='\n'.join(json.dumps(item, ensure_ascii=False) for item in messages) + '\n',
                    capture_output=True, text=True, encoding='utf-8', timeout=30,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                self.assertEqual(process.returncode, 0, process.stderr)
                replies = [json.loads(line) for line in process.stdout.splitlines()]
                self.assertEqual([reply['id'] for reply in replies], list(range(1, 8)))
                self.assertEqual(replies[0]['result']['protocolVersion'], version)
                tools = {tool['name']: tool for tool in replies[1]['result']['tools']}
                self.assertIn('get_capabilities', tools)
                self.assertIn('get_requirement', tools)
                self.assertIn('format_document', tools)
                envelopes = []
                for reply in replies[2:5]:
                    result = reply['result']
                    envelope = json.loads(result['content'][0]['text'])
                    envelopes.append(envelope)
                    if version >= '2025-06-18':
                        self.assertEqual(result['structuredContent'], envelope)
                    else:
                        self.assertNotIn('structuredContent', result)
                capabilities, requirement, invalid = envelopes
                self.assertTrue(capabilities['ok'])
                self.assertEqual(Path(capabilities['data']['path_base']).resolve(), Path(folder).resolve())
                self.assertEqual({tool['name'] for tool in capabilities['data']['tools']}, set(tools))
                self.assertTrue(requirement['ok'])
                self.assertTrue(requirement['data']['rules'])
                self.assertTrue(all(rule['source'] == '6.2' for rule in requirement['data']['rules']))
                self.assertIn('шифр', json.dumps(requirement['data']['rules'], ensure_ascii=False).casefold())
                self.assertEqual(Path(requirement['data']['source']).resolve(), root / 'Normokontrol.pdf')
                self.assertFalse(invalid['ok'])
                self.assertEqual(invalid['error']['code'], 'invalid_request')
                self.assertTrue(replies[4]['result']['isError'])
                self.assertEqual(replies[5]['error']['code'], -32602)
                self.assertEqual(replies[6]['result'], {})

    def test_negotiation_and_lifecycle(self):
        for version in agent_mcp.PROTOCOLS + ('future-version',):
            server = agent_mcp.Server()
            self.assertEqual(server.handle(request('tools/list'))['error']['code'], -32000)
            self.assertEqual(server.handle(request('ping'))['result'], {})
            reply = initialize(server, version)
            self.assertEqual(reply['result']['protocolVersion'],
                             version if version in agent_mcp.PROTOCOLS else agent_mcp.PROTOCOLS[-1])
            self.assertEqual(server.handle(request('initialize'))['error']['code'], -32600)

    def test_tool_result_errors_and_version_compatibility(self):
        for version in agent_mcp.PROTOCOLS:
            server = agent_mcp.Server()
            initialize(server, version)
            for ok in (True, False):
                envelope = {'schema_version': 1, 'ok': ok,
                            'status': 'completed' if ok else 'error', 'data': {}, 'error': None}
                api = types.SimpleNamespace(TOOLS=TOOLS, invoke=lambda *_: envelope)
                with patch.object(agent_mcp, 'load_api', return_value=api):
                    definitions = server.handle(request('tools/list'))['result']['tools']
                    self.assertEqual('outputSchema' in definitions[0], version >= '2025-06-18')
                    self.assertEqual('annotations' in definitions[0], version >= '2025-03-26')
                    result = server.handle(request('tools/call', {'name': 'doctor'}))['result']
                    self.assertEqual(result['isError'], not ok)
                    self.assertEqual(json.loads(result['content'][0]['text']), envelope)
                    self.assertEqual('structuredContent' in result, version >= '2025-06-18')
                    self.assertEqual(server.handle(request('tools/call', {'name': 'unknown'}))[
                        'error']['code'], -32602)
            self.assertIn('outputSchema', TOOLS[0])  # older sessions cannot mutate shared discovery

    def test_bad_requests_and_notifications(self):
        server = agent_mcp.Server()
        initialize(server)
        self.assertEqual(server.handle([])['error']['code'], -32600)
        self.assertEqual(server.handle({'jsonrpc': '2.0', 'id': None, 'method': 'ping'})[
            'error']['code'], -32600)
        self.assertEqual(server.handle(request('unknown'))['error']['code'], -32601)
        self.assertEqual(server.handle(request('tools/call', {'name': 'doctor', 'arguments': []}))[
            'error']['code'], -32602)
        self.assertIsNone(server.handle({'jsonrpc': '2.0', 'method': 'unknown', 'params': []}))
        self.assertIsNone(server.handle({'jsonrpc': '2.0', 'id': 2, 'result': {}}))

    def test_stream_recovery_and_stdout_isolation(self):
        def invoke(*_):
            print('unstructured processing output')
            return {'schema_version': 1, 'ok': True, 'status': 'completed', 'data': {}, 'error': None}
        messages = [request('initialize', {'protocolVersion': '2025-11-25', 'capabilities': {},
                                         'clientInfo': {'name': 'tests', 'version': '1'}}),
                    {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
                    request('tools/call', {'name': 'doctor'}, 2), request('ping', request_id=3)]
        stream = io.StringIO('{bad json\n' + '\n'.join(json.dumps(item) for item in messages) + '\n')
        output, diagnostic = io.StringIO(), io.StringIO()
        with patch.object(agent_mcp, 'load_api', return_value=types.SimpleNamespace(TOOLS=TOOLS, invoke=invoke)), \
                patch.object(agent_mcp.sys, 'stderr', diagnostic):
            self.assertEqual(agent_mcp.serve(stream, output), 0)
        replies = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(len(replies), 4)
        self.assertEqual(replies[0]['error']['code'], -32700)
        self.assertEqual(replies[-1]['id'], 3)
        self.assertIn('unstructured processing output', diagnostic.getvalue())


if __name__ == '__main__':
    unittest.main()
