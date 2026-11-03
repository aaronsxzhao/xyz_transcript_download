"""Real deployed API checks using a scoped token; emit no content or secrets."""
import argparse
import json
import os
import time
import httpx

BASE = 'https://aipodcastsummary.online'
READ_CHECKS = {
    'stats':'/api/stats', 'podcasts':'/api/podcasts', 'library':'/api/library',
    'video_tasks':'/api/video-notes/tasks', 'jobs':'/api/jobs',
    'summaries':'/api/summaries/recent', 'settings':'/api/settings',
    'platform_accounts':'/api/cookies',
}


def run(probe=None):
    token = os.environ.get('PLATFORM_TEST_TOKEN', '')
    if not token.startswith('ptt_'):
        print(json.dumps({'diagnostics':'unavailable', 'reason':'test_token_not_configured'}))
        return False
    passed = True
    with httpx.Client(base_url=BASE, headers={'Authorization':'Bearer '+token},
                      timeout=55, follow_redirects=False) as client:
        checks = [(label,'GET',path,None) for label,path in READ_CHECKS.items()]
        if probe == 'models':
            checks = [('models','POST','/api/settings/models',{'kind':'summary'})]
        elif probe == 'youtube':
            checks = [('youtube','POST','/api/cookies/youtube/verify',{})]
        for label, method, path, payload in checks:
            start = time.monotonic()
            report = {'diagnostics':label}
            try:
                response = client.request(method, path, json=payload)
                report['status'] = response.status_code
                report['json_response'] = response.headers.get('content-type','').startswith('application/json')
                report['milliseconds'] = round((time.monotonic()-start)*1000)
                passed &= response.status_code == 200 and report['json_response']
                if label == 'youtube' and response.status_code == 200:
                    from scripts.diagnose_deployment import safe_youtube_reports
                    report['verification'] = safe_youtube_reports('YouTube verification '+response.text)
                    passed &= response.json().get('download_ok') is True
                # No model IDs, source URLs, titles, account metadata or response bodies.
            except httpx.HTTPError:
                report['network_error'] = True
                passed = False
            print(json.dumps(report))
    return passed


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--probe', choices=['models','youtube'])
    arguments = parser.parse_args()
    raise SystemExit(0 if run(arguments.probe) else 1)
