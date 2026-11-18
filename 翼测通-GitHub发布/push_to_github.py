import os, json, urllib.request

cfg = json.loads(os.environ['CODEBUDDY_MCP_CONFIG'])
g = cfg['mcpServers']['github']
url = g['url']
headers = dict(g['headers'])
headers.update({'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream'})

def call(method, params, sid=None):
    h = dict(headers)
    if sid:
        h['Mcp-Session-Id'] = sid
    body = {'jsonrpc': '2.0', 'id': 99, 'method': method, 'params': params}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=h, method='POST')
    r = urllib.request.urlopen(req, timeout=120)
    raw = r.read().decode()
    sid2 = r.headers.get('Mcp-Session-Id', sid)
    data = None
    for line in raw.splitlines():
        if line.startswith('data: '):
            data = json.loads(line[6:])
            break
    if data is None:
        data = json.loads(raw)
    return data, sid2

init, sid = call('initialize', {
    'protocolVersion': '2025-03-26',
    'capabilities': {},
    'clientInfo': {'name': 'jice-tong-uploader', 'version': '1'}
})

root = r'D:/workbuddy/2026-09-01-21-59-29/05-演示与申报材料/翼测通-GitHub发布/upload'
files = []
for dp, dn, fn in os.walk(root):
    dn[:] = [d for d in dn if d != '.git']
    for f in fn:
        p = os.path.join(dp, f)
        rel = os.path.relpath(p, root).replace('\\', '/')
        content = open(p, encoding='utf-8').read()
        files.append({'path': rel, 'content': content})

files.sort(key=lambda x: x['path'])
print('UPLOADING', len(files), 'files, total chars', sum(len(f['content']) for f in files), flush=True)

res, _ = call('tools/call', {
    'name': 'push_files',
    'arguments': {
        'owner': '3185506410',
        'repo': 'jice-tong',
        'branch': 'main',
        'message': 'Initial commit: Jice Tong academic record Skill (14 files)',
        'files': files
    }
}, sid)

print(json.dumps(res, ensure_ascii=False)[:3000])
