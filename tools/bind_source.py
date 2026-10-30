"""Operator-only local DB binding. Does not call AWS or accept secret values."""
import argparse,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'backend')]
from pipeline.ueba.events import digest

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--user-id',required=True,type=int);p.add_argument('--credential',required=True)
    p.add_argument('--principal',required=True,help='CloudTrail accountId:principalId')
    p.add_argument('--bucket',required=True);p.add_argument('--write',action='store_true')
    args=p.parse_args()
    # Prefix comes from the principal policy, never an arbitrary browser path.
    prefix=f'results/realtime/{digest(args.principal)}/'
    print(f'Binding user {args.user_id}, credential {args.credential}, bucket {args.bucket}, prefix {prefix}')
    if not args.write: print('Dry run. Verify principal/account from independently trusted inventory before --write.');return
    from app.db.database import SessionLocal,Base,engine
    from app.models.user import User
    from app.models.aws_credential import AwsCredential
    from app.models.result_source import ResultSource
    from app.core.credentials import decrypt
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        cred=db.query(AwsCredential).filter_by(user_id=args.user_id,name=args.credential).one()
        identity=decrypt(cred.secret_access_key)
        if args.principal.split(':',1)[0]!=identity['account']: raise ValueError('account_mismatch')
        if not db.get(User,args.user_id): raise ValueError('user_missing')
        if db.query(ResultSource).filter_by(user_id=args.user_id,credential_name=args.credential).first():
            raise ValueError('binding_exists_review_manually')
        db.add(ResultSource(user_id=args.user_id,credential_name=args.credential,bucket=args.bucket,prefix=prefix,principal=args.principal))
        db.commit()
if __name__=='__main__': main()
