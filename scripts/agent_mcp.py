"""Small local MCP stdio adapter over agent_api (no server/network dependency).

Supports handshake revisions 2024-11-05 through 2025-11-25. Calls run serially;
this adapter does not advertise tasks, cancellation or progress notifications.
Only JSON-RPC messages go to stdout; incidental processing output goes to stderr.
"""
from contextlib import redirect_stdout
import copy
import importlib
import json
import math
from pathlib import Path
import sys


PROTOCOLS = ('2024-11-05', '2025-03-26', '2025-06-18', '2025-11-25')
ROOT = Path(__file__).resolve().parent.parent


class RPCError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)


def load_api():
    if __package__:
        return importlib.import_module('.agent_api', __package__)
    return importlib.import_module('agent_api')


def error_reply(request_id, code, message):
    return {'jsonrpc': '2.0', 'id': request_id,
            'error': {'code': code, 'message': message}}


def reject_constant(value):
    raise ValueError(f'Invalid JSON constant: {value}')


class Server:
    def __init__(self):
        self.protocol = None
        self.initialized = False

    def handle(self, message):
        """Return one response, or None for notifications/client responses."""
        if not isinstance(message, dict):
            return error_reply(None, -32600, 'Expected one JSON-RPC object; batches are unsupported.')
        # The server does not issue requests, so there are no responses to consume.
        if message.get('jsonrpc') == '2.0' and 'method' not in message and (
                'result' in message or 'error' in message):
            return None
        request_id = message.get('id')
        has_id = 'id' in message
        valid_id = (isinstance(request_id, (str, int, float)) and not isinstance(request_id, bool)
                    and (not isinstance(request_id, float) or math.isfinite(request_id)))
        method = message.get('method')
        if message.get('jsonrpc') != '2.0' or not isinstance(method, str) or (has_id and not valid_id):
            return error_reply(request_id if valid_id else None, -32600, 'Invalid JSON-RPC request.')
        params = message.get('params', {})
        if not has_id:
            if method == 'notifications/initialized' and self.protocol and isinstance(params, dict):
                self.initialized = True
            return None
        try:
            if not isinstance(params, dict):
                raise RPCError(-32602, 'params must be an object.')
            with redirect_stdout(sys.stderr):
                result = self._dispatch(method, params)
            return {'jsonrpc': '2.0', 'id': request_id, 'result': result}
        except RPCError as error:
            return error_reply(request_id, error.code, error.message)
        except Exception as error:
            print(f'MCP request failed: {type(error).__name__}: {error}', file=sys.stderr)
            return error_reply(request_id, -32603, 'Internal server error; see stderr diagnostics.')

    def _dispatch(self, method, params):
        if method == 'ping':
            return {}
        if method == 'initialize':
            if self.protocol is not None:
                raise RPCError(-32600, 'This connection is already initialized.')
            requested = params.get('protocolVersion')
            info = params.get('clientInfo')
            if (not isinstance(requested, str) or not requested
                    or not isinstance(params.get('capabilities'), dict)
                    or not isinstance(info, dict)
                    or not isinstance(info.get('name'), str)
                    or not isinstance(info.get('version'), str)):
                raise RPCError(-32602, 'initialize requires protocolVersion, capabilities and clientInfo name/version.')
            self.protocol = requested if requested in PROTOCOLS else PROTOCOLS[-1]
            return {'protocolVersion': self.protocol, 'capabilities': {'tools': {'listChanged': False}},
                    'serverInfo': {'name': 'wordcraft-normokontrol',
                                   'version': (ROOT / 'VERSION').read_text(encoding='utf-8').strip()},
                    'instructions': 'Start with get_capabilities and doctor. Use separate output folders. '
                                    'A completed run may still have findings requiring review. '
                                    'Tools run serially; cancellation and tasks are unsupported.'}
        if self.protocol is None or not self.initialized:
            raise RPCError(-32000, 'Send initialize and notifications/initialized before using tools.')
        if method == 'tools/list':
            if params.get('cursor') is not None:
                raise RPCError(-32602, 'This server returns all tools in one page; omit cursor.')
            definitions = copy.deepcopy(load_api().TOOLS)
            for tool in definitions:
                if self.protocol < '2025-06-18':
                    tool.pop('outputSchema', None)
                    tool.pop('title', None)
                if self.protocol < '2025-03-26':
                    tool.pop('annotations', None)
            return {'tools': definitions}
        if method == 'tools/call':
            name, arguments = params.get('name'), params.get('arguments', {})
            if not isinstance(name, str) or not isinstance(arguments, dict):
                raise RPCError(-32602, 'tools/call requires a string name and object arguments.')
            api = load_api()
            if name not in {tool['name'] for tool in api.TOOLS}:
                raise RPCError(-32602, f'Unknown tool: {name}')
            envelope = api.invoke(name, arguments)
            result = {'content': [{'type': 'text', 'text': json.dumps(envelope, ensure_ascii=False)}],
                      'isError': not envelope['ok']}
            if self.protocol >= '2025-06-18':
                result['structuredContent'] = envelope
            return result
        raise RPCError(-32601, f'Method not found: {method}')


def serve(input_stream=None, output_stream=None):
    """Serve newline-delimited JSON until EOF. No GUI, sockets or global setup."""
    input_stream = sys.stdin if input_stream is None else input_stream
    output_stream = sys.stdout if output_stream is None else output_stream
    server = Server()
    for line in input_stream:
        try:
            message = json.loads(line, parse_constant=reject_constant)
        except (ValueError, TypeError):
            reply = error_reply(None, -32700, 'Parse error: expected valid JSON.')
        else:
            reply = server.handle(message)
        if reply is not None:
            output_stream.write(json.dumps(reply, ensure_ascii=False, allow_nan=False) + '\n')
            output_stream.flush()
    return 0


if __name__ == '__main__':
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    raise SystemExit(serve())
