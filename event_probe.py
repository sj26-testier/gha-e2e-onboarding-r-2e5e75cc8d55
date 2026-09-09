"""Assert event payload and default-branch checkout without logging credentials."""
import json
import os
from pathlib import Path
import subprocess
import urllib.request


def inspect(event, env, checkout):
    name = env['PROBE_EVENT']
    assert name in {'issues', 'issue_comment'}, 'wrong event name'
    assert event['action'] == env['PROBE_ACTION'] == (
        'opened' if name == 'issues' else 'created'), 'wrong action'
    assert event['repository']['owner']['login'] == 'sj26-testier'
    assert event['repository']['name'].startswith('gha-e2e-onboarding-r-')
    assert 'pull_request' not in event['issue'], 'PR comments are not this scenario'
    assert event['issue']['title'].startswith('LAB issue-events ')
    assert event['issue']['body'] == 'LAB_PAYLOAD_issue_v1'
    assert event['issue']['user']['login'] == event['sender']['login'] == 'sj26-testier'
    assert str(event['issue']['number']) == env['PROBE_ISSUE']
    assert env['PROBE_REF'] == 'refs/heads/main', 'wrong default ref'
    assert checkout == env['PROBE_SHA'], 'checkout/context SHA mismatch'
    if name == 'issue_comment':
        assert str(event['comment']['id']) == env['PROBE_COMMENT']
        assert event['comment']['body'] == 'LAB_PAYLOAD_comment_v1'
        assert event['comment']['user']['login'] == 'sj26-testier'
    return {'event': name, 'action': event['action'], 'issue': event['issue']['number'],
            'comment': event.get('comment', {}).get('id'), 'is_pr': False,
            'ref': env['PROBE_REF'], 'sha': env['PROBE_SHA'], 'checkout_sha': checkout,
            'workflow_ref': env['PROBE_WORKFLOW_REF'], 'workflow_sha': env['PROBE_WORKFLOW_SHA'],
            'repository': event['repository']['full_name']}


if __name__ == '__main__':
    payload = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    checkout = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    result = inspect(payload, os.environ, checkout)
    token = os.environ['PROBE_TOKEN']
    assert token, 'workflow token missing'
    request = urllib.request.Request(
        'https://api.github.com/repos/' + result['repository'] + '/contents/event_probe.py?ref=' + checkout,
        headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(request, timeout=30) as response:
        content = json.load(response)
        assert content['path'] == 'event_probe.py'
        result.update(token_present=True, authenticated_contents_status=response.status)
    print('LAB_EVENT_EXECUTED:' + json.dumps(result, sort_keys=True), flush=True)
