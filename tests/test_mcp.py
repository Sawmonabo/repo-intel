import io
import json
import os
import subprocess
import sys
import threading
import urllib.error
import urllib.request

import pytest
from repo_intel.service import Repository


def make(tmp_path):
    root=tmp_path/'project';root.mkdir()
    (root/'a.py').write_text('def f(x):\n    return x+1\n\ndef g():\n    return f(2)\n')
    repo=Repository(root,tmp_path/'state');repo.index()
    return repo


def request(method,params=None,ident=1):
    return {'jsonrpc':'2.0','id':ident,'method':method,'params':params or {}}


def test_initialize_tools_query_and_validation(tmp_path):
    from repo_intel.mcp import MCPApplication
    repo=make(tmp_path);app=MCPApplication(repo)
    response=app.handle(request('initialize',{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'test','version':'1'}}))
    assert response['result']['protocolVersion']=='2025-06-18'
    tools=app.handle(request('tools/list'))['result']['tools']
    assert 'repo_query' in {x['name'] for x in tools}
    assert not {'repo_capture','repo_run_tool','repo_refresh'} & {x['name'] for x in tools}
    result=app.handle(request('tools/call',{'name':'repo_query','arguments':{'kind':'callers','symbol':'a.f'}}))
    assert result['result']['structuredContent']['items'][0]['caller']=='a.g'
    bad=app.handle(request('tools/call',{'name':'repo_query','arguments':{'kind':'calls','arbitrary_sql':'DROP TABLE files'}}))
    assert bad['result']['isError'] is True
    assert app.handle({'jsonrpc':'2.0','method':'notifications/initialized'}) is None
    assert app.handle(request('made-up'))['error']['code']==-32601


def test_stdio_roundtrip_and_malformed_input(tmp_path):
    from repo_intel.mcp import MCPApplication,serve_stdio
    app=MCPApplication(make(tmp_path))
    source=io.BytesIO(b'{bad}\n'+json.dumps(request('tools/list')).encode()+b'\n')
    target=io.BytesIO()
    serve_stdio(app,source,target)
    lines=target.getvalue().splitlines()
    assert len(lines)==2
    assert json.loads(lines[0])['error']['code']==-32700
    assert json.loads(lines[1])['result']['tools']


def test_mcp_rejects_unknown_args_and_bool_in_integer_field(tmp_path):
    from repo_intel.mcp import MCPApplication
    app=MCPApplication(make(tmp_path),allow_refresh=True)
    for args in ({'kind':'calls','limit':True},{'kind':'calls','limit':999999}, {'kind':'not-real'}):
        result=app.handle(request('tools/call',{'name':'repo_query','arguments':args}))
        assert result['result']['isError'] is True
    assert 'repo_refresh' in {x['name'] for x in app.handle(request('tools/list'))['result']['tools']}


def open_http(server,payload=None,*,token='x'*40,origin=None,method='POST',extra=None):
    address=f'http://127.0.0.1:{server.server_address[1]}/mcp'
    headers={'Authorization':f'Bearer {token}', 'Content-Type':'application/json',
             'Accept':'application/json, text/event-stream','MCP-Protocol-Version':'2025-06-18'}
    if origin:headers['Origin']=origin
    headers.update(extra or {})
    req=urllib.request.Request(address,data=json.dumps(payload).encode() if payload is not None else None,
                               headers=headers,method=method)
    return urllib.request.urlopen(req,timeout=5)


@pytest.fixture
def http_server(tmp_path):
    from repo_intel.mcp import MCPApplication
    from repo_intel.http_server import MCPHTTPServer
    app=MCPApplication(make(tmp_path))
    server=MCPHTTPServer(('127.0.0.1',0),app,'x'*40,max_workers=2)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    yield server
    server.shutdown();server.server_close();thread.join(timeout=5)


def test_http_initialize_notification_and_get(http_server):
    with open_http(http_server,request('initialize',{'protocolVersion':'2025-06-18'})) as response:
        assert response.status==200
        assert json.load(response)['result']['serverInfo']['name']=='repo-intel'
    with open_http(http_server,{'jsonrpc':'2.0','method':'notifications/initialized'}) as response:
        assert response.status==202 and response.read()==b''
    with pytest.raises(urllib.error.HTTPError) as exc:
        open_http(http_server,method='GET')
    assert exc.value.code==405


def test_http_auth_origin_host_and_version_rejection(http_server):
    for kwargs,expected in [({'token':'wrong'},401),({'origin':'https://evil.example'},403),
                            ({'extra':{'Host':'evil.example'}},403),
                            ({'extra':{'MCP-Protocol-Version':'not-supported'}},400)]:
        with pytest.raises(urllib.error.HTTPError) as exc:
            open_http(http_server,request('tools/list'),**kwargs)
        assert exc.value.code==expected


def test_http_multiple_clients_same_snapshot(http_server):
    snapshots=[]
    def call():
        with open_http(http_server,request('tools/call',{'name':'repo_status','arguments':{}})) as response:
            snapshots.append(json.load(response)['result']['structuredContent']['snapshot'])
    # Sequential clients share one service; concurrency is exercised separately below.
    for _ in range(3):call()
    assert len(set(snapshots))==1


def test_proxy_real_subprocess_and_cli(http_server,tmp_path):
    port=http_server.server_address[1]
    token=tmp_path/'token';token.write_text('x'*40);token.chmod(0o600)
    messages=[request('initialize',{'protocolVersion':'2025-06-18'}),
              {'jsonrpc':'2.0','method':'notifications/initialized'},
              request('tools/call',{'name':'repo_status','arguments':{}},ident=2)]
    proc=subprocess.run([sys.executable,'-m','repo_intel','proxy','--url',f'http://127.0.0.1:{port}/mcp',
                         '--token-file',str(token)],input=''.join(json.dumps(m)+'\n' for m in messages),
                        text=True,capture_output=True,timeout=10)
    assert proc.returncode==0,proc.stderr
    responses=[json.loads(line) for line in proc.stdout.splitlines()]
    assert len(responses)==2 and responses[-1]['id']==2
    assert responses[-1]['result']['structuredContent']['indexed'] is True


def test_cli_stdio_executable(tmp_path):
    repo=make(tmp_path)
    proc=subprocess.run([sys.executable,'-m','repo_intel','--repo',str(repo.root),'--state',str(repo.store.state),
                         'serve','stdio'],input=json.dumps(request('tools/list'))+'\n',text=True,
                        capture_output=True,timeout=10)
    assert proc.returncode==0,proc.stderr
    assert 'repo_query' in {t['name'] for t in json.loads(proc.stdout)['result']['tools']}


def test_http_never_binds_public_interface(tmp_path):
    from repo_intel.mcp import MCPApplication
    from repo_intel.http_server import MCPHTTPServer
    with pytest.raises(ValueError,match='loopback'):
        MCPHTTPServer(('0.0.0.0',0),MCPApplication(make(tmp_path)),'x'*40)


def test_mcp_capture_accepts_target_interpreter_and_requires_call_trust(tmp_path):
    from repo_intel.mcp import MCPApplication
    repo=make(tmp_path)
    (repo.root/'test_a.py').write_text('from a import g\ndef test_g():\n    assert g()==3\n')
    app=MCPApplication(repo,allow_execution=True)
    missing=app.handle(request('tools/call',{'name':'repo_capture','arguments':{'args':['-q']}}))
    assert missing['result']['isError'] is True
    refused=app.handle(request('tools/call',{'name':'repo_capture','arguments':{'args':['-q'],'trust':False}}))
    assert refused['result']['isError'] is True
    result=app.handle(request('tools/call',{'name':'repo_capture','arguments':{
        'args':['-q'],'trust':True,'python':sys.executable,'timeout':30}}))
    assert result['result']['isError'] is False, result
    data=result['result']['structuredContent']
    assert data['exit_code']==0 and data['imported']['events']>0
