import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

event = json.loads(os.environ['PROBE_EVENT'])
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
path = os.environ.get('GITHUB_EVENT_PATH')
file_event = json.load(open(path)) if path and os.path.isfile(path) else None
digest = lambda value: hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
checks = {
    'event_name': os.environ['GITHUB_EVENT_NAME'] == 'issues',
    'action': event['action'] in ('opened', 'edited'),
    'repository': event['repository']['full_name'] == os.environ['GITHUB_REPOSITORY'],
    'issue_shape': 'pull_request' not in event['issue'],
    'default_ref': os.environ['GITHUB_REF'] == 'refs/heads/main',
    'immutable_checkout': head == os.environ['GITHUB_SHA'],
    'event_file': file_event is not None,
    'full_payload_equal': file_event == event,
    'edited_changes': event['action'] != 'edited' or bool(event.get('changes')),
}
summary = {'checks': checks, 'action': event['action'], 'issue': event['issue']['number'],
           'sender': event['sender']['login'], 'sha': head, 'payload_sha256': digest(event),
           'event_path': path, 'event_keys': sorted(event), 'body': event['issue']['body']}
print('PB2952_PROBE=' + json.dumps(summary, sort_keys=True), flush=True)
if '--write' in sys.argv:
    side = 'BUILDKITE' if os.environ.get('BUILDKITE') == 'true' else 'NATIVE'
    token = os.environ['PROBE_TOKEN']
    url = 'https://api.github.com/repos/' + os.environ['GITHUB_REPOSITORY'] + '/issues/' + str(event['issue']['number'])
    def request(method, body=None):
        req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body else None,
            headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
                     'Content-Type': 'application/json', 'User-Agent': 'PB2952-dedicated-lab'})
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status, json.load(response)
    # Bound recursion even if the product does not suppress its own tokens. Only
    # opened runs write; a rebuild checks current state before repeating the write.
    assert event['action'] == 'opened'
    marker = 'PB2952_' + side + '_WRITE'
    _, current = request('GET')
    if marker in (current.get('body') or ''):
        print('PB2952_WRITE=' + json.dumps({'side': side, 'already_present': True}), flush=True)
    else:
        try:
            status, updated = request('PATCH', {'body': (current.get('body') or '') + '\n' + marker})
            print('PB2952_WRITE=' + json.dumps({'side': side, 'http': status, 'issue': updated['number'], 'body': updated['body']}), flush=True)
        except urllib.error.HTTPError as error:
            print('PB2952_WRITE=' + json.dumps({'side': side, 'http': error.code}), flush=True)
            raise SystemExit(1)
assert all(checks.values()), 'Failed checks: ' + ', '.join(k for k, v in checks.items() if not v)
