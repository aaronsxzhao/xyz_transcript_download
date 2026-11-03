"""Run inside the application's trusted runtime, using its existing cookie store.

python -m scripts.verify_youtube --user-id ACCOUNT_UUID --url YOUTUBE_VIDEO_URL
No production credentials are fetched or exported by this command.
"""
import argparse
import json
from api.youtube_diagnostics import video_url, verify_saved_cookie


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--user-id',help='Account that explicitly authorized verification; required in cloud mode')
    parser.add_argument('--url',default='',help='One HTTPS YouTube video URL; defaults to a public test video')
    args=parser.parse_args()
    from config import USE_SUPABASE
    if USE_SUPABASE and not args.user_id:parser.error('--user-id is required in cloud mode')
    try:url=video_url(args.url)
    except ValueError as error:parser.error(str(error))
    report=verify_saved_cookie(args.user_id,url)
    print(json.dumps(report))
    return 0 if report['code']=='ok' else 1


if __name__=='__main__':raise SystemExit(main())
