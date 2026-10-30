import os
import sys
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parents[1]/'backend')]
os.environ.update(AWS_ACCESS_KEY_ID='testing',AWS_SECRET_ACCESS_KEY='testing',AWS_DEFAULT_REGION='us-east-1',
                  AWS_EC2_METADATA_DISABLED='true',SECRET_KEY='test-only-jwt-signing-key-47-not-production',
                  DATABASE_URL='sqlite://',FERNET_KEY='MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=')
import boto3
import pytest
from moto import mock_aws
from datetime import datetime,timedelta,timezone
from pipeline.ueba.events import normalize


def cloud_event(i=0,user='ALICE',timestamp=None):
    ts=timestamp or (datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(seconds=i*10)).isoformat()
    return {'detail':dict(eventID=f'evt-{i:05}',eventTime=ts,eventName=['ListBuckets','GetObject','DescribeInstances','PutObject'][i%4],
                         userIdentity=dict(accountId='123456789012',principalId=user,arn=f'arn:aws:iam::123456789012:user/{user}',userName=user))}

@pytest.fixture
def aws():
    from tools.mock_setup import mock_services
    with mock_services():
        ddb=boto3.resource('dynamodb');s3=boto3.client('s3')
        table=ddb.create_table(TableName='events',KeySchema=[dict(AttributeName='pk',KeyType='HASH'),dict(AttributeName='sk',KeyType='RANGE')],
            AttributeDefinitions=[dict(AttributeName=n,AttributeType='S') for n in ('pk','sk')],BillingMode='PAY_PER_REQUEST',
            StreamSpecification=dict(StreamEnabled=True,StreamViewType='NEW_IMAGE'))
        for name in ('failure-archive','ueba-results'): s3.create_bucket(Bucket=name)
        yield table,s3

@pytest.fixture(scope='session')
def model_dir(tmp_path_factory):
    from pipeline.ueba.models import train
    p=tmp_path_factory.mktemp('models')
    rows=[normalize(cloud_event(i)) for i in range(100)]
    train(rows,p,'v1',minimum=100,vec_size=16,min_samples=3)
    return p

@pytest.fixture
def api(tmp_path):
    from sqlalchemy import create_engine,event
    from sqlalchemy.orm import sessionmaker
    from app.main import app
    from app.db.database import Base,get_db
    from fastapi.testclient import TestClient
    engine=create_engine('sqlite:///'+str(tmp_path/'test.sqlite'),connect_args={'check_same_thread':False,'timeout':20})
    @event.listens_for(engine,'connect')
    def foreign_key(conn,_): conn.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine)
    factory=sessionmaker(bind=engine)
    def db():
        with factory() as session: yield session
    app.dependency_overrides[get_db]=db
    with TestClient(app) as client: yield client,factory
    app.dependency_overrides.clear();engine.dispose()
