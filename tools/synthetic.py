"""Connectivity fixture only, never a detection accuracy benchmark."""
from datetime import datetime,timedelta,timezone

def generate(count=120,user='DEMO'):
    base=datetime(2026,1,1,tzinfo=timezone.utc)
    for i in range(count):
        # Two activity sessions separated by 40 minutes; endpoint windows span neither.
        time=base+timedelta(seconds=10*i+(2400 if i>=count//2 else 0))
        yield {'detail':dict(eventID=f'synthetic-{user}-{i:05d}',eventTime=time.isoformat(),
            eventName=['ListBuckets','GetObject','DescribeInstances','PutObject','ListUsers'][i%5],
            userIdentity=dict(accountId='123456789012',principalId=user,userName=user,
                              arn=f'arn:aws:iam::123456789012:user/{user}'))}

if __name__=='__main__':
    import argparse,json
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--count',type=int,default=120)
    for event in generate(p.parse_args().count): print(json.dumps(event))
