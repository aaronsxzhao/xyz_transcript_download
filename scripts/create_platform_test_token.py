"""Create an opaque token in a new private file; print only registration metadata."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import uuid


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--owner',type=uuid.UUID,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--days',type=int,default=30)
    args=parser.parse_args()
    if not 1 <= args.days <= 90: parser.error('--days must be between 1 and 90')
    token='ptt_'+secrets.token_urlsafe(32)
    fd=os.open(args.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as output: output.write(token+'\n')
    print(json.dumps({'token_digest':hashlib.sha256(token.encode()).hexdigest(),
        'owner_id':str(args.owner),'expires_at':(datetime.now(timezone.utc)+timedelta(days=args.days)).isoformat(),
        'scopes':['content:read','diagnostics:run','models:probe']}))


if __name__=='__main__': main()
