import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

event = json.loads(os.environ['PROBE_EVENT'])
name = os.environ['GITHUB_EVENT_NAME']
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
path = os.environ.get('GITHUB_EVENT_PATH')
file_event = json.load(open(path)) if path and os.path.isfile(path) else None
digest = lambda value: hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
allowed = {'issues': ('opened', 'edited'), 'issue_comment': ('created',)}
checks = {
    'event_name': name in allowed,
    'action': event.get('action') in allowed.get(name, ()),
    'repository': event['repository']['full_name'] == os.environ['GITHUB_REPOSITORY'],
    'issue_shape': 'pull_request' not in event['issue'],
    'default_ref': os.environ['GITHUB_REF'] == 'refs/heads/main',
    'immutable_checkout': head == os.environ['GITHUB_SHA'],
    'event_file': file_event is not None,
    'full_payload_equal': file_event == event,
    'edited_changes': event.get('action') != 'edited' or bool(event.get('changes')),
    'comment_present': name != 'issue_comment' or bool(event.get('comment', {}).get('id')),
}
side = 'BUILDKITE' if path and '/buildkite-gha-runner/' in path else 'NATIVE'
summary = {'checks': checks, 'side': side, 'event': name, 'action': event.get('action'),
           'issue': event['issue']['number'], 'sender': event['sender']['login'],
           'sender_type': event['sender']['type'], 'sha': head, 'payload_sha256': digest(event),
           'comment_id': event.get('comment', {}).get('id')}
print('PB3469_PROBE=' + json.dumps(summary, sort_keys=True), flush=True)
assert all(checks.values()), 'Failed checks: ' + ', '.join(k for k, v in checks.items() if not v)

if '--write' in sys.argv:
    # Writers mutate only on the opened event, so any recursive delivery reaches
    # only non-mutating probes. No manual reruns are planned in this lab.
    assert name == 'issues' and event['action'] == 'opened'
    token = os.environ['PROBE_TOKEN']
    issue_url = 'https://api.github.com/repos/' + os.environ['GITHUB_REPOSITORY'] + '/issues/' + str(event['issue']['number'])

    def request(method, url, body=None):
        req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body else None,
            headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
                     'Content-Type': 'application/json', 'User-Agent': 'PB3469-dedicated-lab'})
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            return error.code, None

    marker = 'PB3469_' + side + '_WRITE'
    status, current = request('GET', issue_url)
    assert status == 200, f'GET issue HTTP {status}'
    if marker in (current.get('body') or ''):
        edit = {'already_present': True}
    else:
        status, updated = request('PATCH', issue_url, {'body': (current.get('body') or '') + '\n' + marker})
        edit = {'http': status}
    status, comment = request('POST', issue_url + '/comments', {'body': 'PB3469_' + side + '_COMMENT'})
    result = {'side': side, 'edit': edit, 'comment_http': status,
              'comment_id': comment and comment['id'], 'comment_user': comment and comment['user']['login']}
    print('PB3469_WRITE=' + json.dumps(result, sort_keys=True), flush=True)
    assert edit.get('http', 200) == 200 and status == 201, 'Writer mutation failed'
