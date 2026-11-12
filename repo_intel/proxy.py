"""Small stdio-to-loopback bridge. It has no repository index or analysis cache."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from .mcp import MAX_MESSAGE, MAX_RESULT, PROTOCOLS, error, parse_message


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        raise ValueError('MCP redirects are not permitted')


def run_proxy(url: str,token_path: str,timeout=60):
    parsed=urlparse(url)
    if parsed.scheme!='http' or parsed.hostname!='127.0.0.1' or parsed.path!='/mcp' or parsed.query or parsed.fragment or parsed.username:
        raise ValueError('Proxy URL must be http://127.0.0.1:PORT/mcp without credentials or query')
    path=Path(token_path)
    if path.is_symlink() or path.stat().st_size>4096:
        raise ValueError('Invalid token file')
    if os.name!='nt' and path.stat().st_mode & 0o077:
        raise ValueError('Token file permissions must be 0600')
    token=path.read_text().strip()
    if len(token)<32:raise ValueError('Invalid local authentication token')
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    version=PROTOCOLS[-1]
    source,target=sys.stdin.buffer,sys.stdout.buffer
    while line:=source.readline(MAX_MESSAGE+1):
        response=None;message=None
        try:
            if len(line)>MAX_MESSAGE:
                while line and not line.endswith(b'\n'):line=source.readline(MAX_MESSAGE+1)
                raise ValueError('Message exceeds byte budget')
            if not line.strip():continue
            message=parse_message(line)
            headers={'Authorization':'Bearer '+token,'Content-Type':'application/json',
                     'Accept':'application/json, text/event-stream','MCP-Protocol-Version':version}
            req=urllib.request.Request(url,data=line,headers=headers,method='POST')
            with opener.open(req,timeout=timeout) as result:
                payload=result.read(2*MAX_RESULT+65537)
                if len(payload)>2*MAX_RESULT+65536:raise ValueError('Server result exceeds byte budget')
                if result.status!=202 and payload:
                    response=parse_message(payload)
                    if isinstance(message,dict) and message.get('method')=='initialize':
                        version=response.get('result',{}).get('protocolVersion',version)
        except (OSError,ValueError,urllib.error.URLError) as exc:
            if not isinstance(message,dict) or 'id' in message:
                response=error(message.get('id') if isinstance(message,dict) else None,-32603,f'Local MCP transport failed: {exc}')
        if response is not None:
            target.write(json.dumps(response,ensure_ascii=True,separators=(',',':')).encode()+b'\n');target.flush()
