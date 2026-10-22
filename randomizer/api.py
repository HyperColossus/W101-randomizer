"""Loopback-only HTTP bridge API for a trusted Imlight integration process.

The game adapter remains responsible for actually changing client/character data.
Only use this service on a trusted machine. Never expose its bearer token to players.
"""
from __future__ import annotations

import hmac
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import ip_address
from urllib.parse import unquote, urlsplit

from .core import RandomizerError
from .runtime import RunStore


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        self.status, self.message = status, message


def make_server(store: RunStore, token: str, host='127.0.0.1', port=18951) -> ThreadingHTTPServer:
    if not isinstance(token, str) or len(token) < 24:
        raise RandomizerError('W101_API_TOKEN must be at least 24 characters')
    try:
        if not ip_address(host).is_loopback:
            raise RandomizerError('HTTP API may bind only to loopback (no TLS available)')
    except ValueError as e:
        raise RandomizerError('host must be a loopback IP address') from e

    class Handler(BaseHTTPRequestHandler):
        server_version = 'W101Randomizer/0.2'

        def _json(self, status, body):
            data = json.dumps(body, sort_keys=True, separators=(',', ':')).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(data)

        def _auth(self):
            authorization = self.headers.get('Authorization', '')
            if not hmac.compare_digest(authorization, 'Bearer ' + token):
                raise ApiError(401, 'unauthorized')

        def _path(self):
            return [unquote(p) for p in urlsplit(self.path).path.split('/') if p]

        def _handle(self, method):
            try:
                self._auth()
                segments = self._path()
                if method == 'GET':
                    if segments == ['v1', 'health']:
                        return self._json(200, {'ok': True, 'status': store.status()})
                    if segments == ['v1', 'manifest']:
                        return self._json(200, store.manifest)
                    if len(segments) == 4 and segments[:2] == ['v1', 'world']:
                        return self._json(200, {'kind': segments[2], 'slot': segments[3],
                                                'result': store.lookup(segments[2], segments[3])})
                    if len(segments) in (3, 4) and segments[:2] == ['v1', 'characters']:
                        actor = segments[2]
                        if len(segments) == 4 and segments[3] == 'pending':
                            return self._json(200, {'events': store.pending(actor)})
                        if len(segments) == 3:
                            character = store.get_character(actor)
                            if character is None:
                                raise ApiError(404, 'character not initialized')
                            return self._json(200, {'character': character})
                    raise ApiError(404, 'route not found')
                if method == 'POST':
                    length = self.headers.get('Content-Length')
                    if length is None or not length.isdigit() or int(length) > 65536:
                        raise ApiError(413, 'JSON body must be 65536 bytes or less')
                    try:
                        data = json.loads(self.rfile.read(int(length)))
                    except (ValueError, UnicodeDecodeError):
                        raise ApiError(400, 'invalid JSON') from None
                    if not isinstance(data, dict):
                        raise ApiError(400, 'JSON body must be an object')
                    if segments == ['v1', 'commands']:
                        result = store.perform(data.get('actor'), data.get('action'),
                                               data.get('request_id'), data.get('payload', {}))
                        return self._json(200, result)
                    if segments == ['v1', 'ack']:
                        result = store.ack(data.get('actor'), data.get('event_id'))
                        return self._json(200, {'new_ack': result})
                    raise ApiError(404, 'route not found')
                raise ApiError(405, 'method not allowed')
            except ApiError as exc:
                self._json(exc.status, {'error': exc.message})
            except (RandomizerError, KeyError, TypeError, ValueError) as exc:
                self._json(400, {'error': str(exc)})

        def do_GET(self):
            self._handle('GET')

        def do_POST(self):
            self._handle('POST')

        def log_message(self, fmt, *args):
            # Default logs include requests; never print authorization headers or body.
            return

    class BridgeServer(ThreadingHTTPServer):
        daemon_threads = True

    server = BridgeServer((host, port), Handler)
    return server
