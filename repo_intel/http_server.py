"""Authenticated loopback-only stateless Streamable HTTP transport.

Not an Internet-facing web server. No OAuth server, SSE channel, or persistent
session is advertised. POST JSON responses, 202 notifications and GET 405 follow
MCP 2025-06-18. A bounded number of request threads limits concurrent query caches.
"""
from __future__ import annotations

import contextlib
import hmac
import json
import os
import secrets
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .mcp import MAX_MESSAGE, PROTOCOLS, error, parse_message


class MCPHTTPServer(ThreadingHTTPServer):
    daemon_threads=True
    allow_reuse_address=True

    def __init__(self,address,app,token,*,max_workers=4):
        if address[0]!='127.0.0.1':
            raise ValueError('Only IPv4 loopback 127.0.0.1 may be bound')
        if not isinstance(token,str) or len(token)<32 or not token.isascii():
            raise ValueError('Local authentication token must contain at least 32 characters')
        if type(max_workers) is not int or not 1<=max_workers<=32:
            raise ValueError('max_workers must be 1..32')
        self.app,self.token=app,token
        self.slots=threading.BoundedSemaphore(max_workers)
        super().__init__(address,Handler)

    def get_request(self):
        connection,address=super().get_request()
        connection.settimeout(15)
        return connection,address

    def process_request(self,request,client_address):
        if not self.slots.acquire(blocking=False):
            with contextlib.suppress(OSError):
                request.sendall(b'HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
            self.shutdown_request(request)
            return
        try:super().process_request(request,client_address)
        except BaseException:
            self.slots.release();raise

    def process_request_thread(self,request,client_address):
        try:super().process_request_thread(request,client_address)
        finally:self.slots.release()


class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    server_version='RepoIntel'
    sys_version=''

    def log_message(self,format,*args):
        # Do not log credentials, request bodies or source snippets.
        pass

    def send(self,status,payload=None):
        data=json.dumps(payload,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode() if payload is not None else b''
        self.send_response(status)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Connection','close')
        if status==405:self.send_header('Allow','POST, GET')
        self.end_headers()
        self.close_connection=True
        if data:self.wfile.write(data)

    def authorized(self):
        port=self.server.server_address[1]
        hosts={f'127.0.0.1:{port}',f'localhost:{port}'}
        if self.path!='/mcp':self.send(404);return False
        if len(self.headers.get_all('Host',[]))!=1 or self.headers.get('Host') not in hosts:
            self.send(403);return False
        if len(self.headers.get_all('Origin',[]))>1:
            self.send(403);return False
        if len(self.headers.get_all('Authorization',[]))!=1:
            self.send(401);return False
        origin=self.headers.get('Origin')
        if origin is not None and origin not in {f'http://{h}' for h in hosts}:
            self.send(403);return False
        actual=self.headers.get('Authorization','')
        if not hmac.compare_digest(actual.encode('utf-8'),('Bearer '+self.server.token).encode('ascii')):
            self.send(401,{'error':'Local bearer token required'});return False
        if self.headers.get('MCP-Protocol-Version','2025-03-26') not in PROTOCOLS:
            self.send(400,{'error':'Unsupported MCP protocol version'});return False
        return True

    def do_GET(self):
        if self.authorized():self.send(405)

    do_DELETE=do_GET

    def do_POST(self):
        try:
            if not self.authorized():return
            if self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length',[]))!=1:
                self.send(400);return
            if self.headers.get('Content-Type','').split(';')[0].strip().lower()!='application/json':
                self.send(415);return
            if 'application/json' not in self.headers.get('Accept',''):
                self.send(406);return
            length=int(self.headers['Content-Length'])
            if not 0<length<=MAX_MESSAGE:
                self.send(413);return
            body=self.rfile.read(length)
            if len(body)!=length:self.send(400);return
            try:message=parse_message(body)
            except (ValueError,UnicodeError,RecursionError):
                self.send(400,error(None,-32700,'Malformed JSON'));return
            response=self.server.app.handle(message)
            if response is None:self.send(202)
            else:self.send(200,response)
        except (TimeoutError,ConnectionError,BrokenPipeError):
            self.close_connection=True
        except ValueError:
            self.send(400)


def token_file(path: Path):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if path.is_symlink():raise ValueError('Token file must not be a symlink')
    try:
        descriptor=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    except FileExistsError:
        if os.name!='nt' and path.stat().st_mode & 0o077:
            raise ValueError('Token file permissions must be 0600')
    else:
        with os.fdopen(descriptor,'w') as file:file.write(secrets.token_urlsafe(32)+'\n')
    token=path.read_text().strip()
    if len(token)<32 or len(token)>4096:raise ValueError('Invalid token file')
    return token


def serve_http(app,port=8765,token_path=None,max_workers=4):
    path=Path(token_path) if token_path else app.repo.store.state/'mcp-token'
    token=token_file(path)
    with MCPHTTPServer(('127.0.0.1',port),app,token,max_workers=max_workers) as server:
        print(json.dumps({'endpoint':f'http://127.0.0.1:{server.server_address[1]}/mcp',
                          'token_file':str(path.resolve()),'read_only':not app.allow_execution}),file=sys.stderr,flush=True)
        server.serve_forever(poll_interval=.2)
