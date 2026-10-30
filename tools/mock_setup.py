"""Synthetic AWS session for Moto only; never replaces injected runtime auth."""
import tempfile
from pathlib import Path
import boto3
import botocore.session

def configure_mock_session():
    with tempfile.NamedTemporaryFile(mode='w',suffix='.config',prefix='ueba-moto-',delete=False) as f:
        f.write('[profile ueba-moto-only]\nregion=us-east-1\n')
        config=Path(f.name)
    local=botocore.session.Session(profile='ueba-moto-only')
    local.set_config_variable('config_file',str(config))
    boto3.setup_default_session(botocore_session=local,aws_access_key_id='testing',
                               aws_secret_access_key='testing',region_name='us-east-1')
    return config

from contextlib import contextmanager
from unittest.mock import patch
from moto import mock_aws

@contextmanager
def mock_services():
    with mock_aws():
        config=configure_mock_session()
        # Moto internally creates another Session for region metadata. Bind that
        # metadata lookup to the same synthetic profile without changing AWS_PROFILE.
        try:
            with patch('moto.core.base_backend.Session',lambda: boto3.DEFAULT_SESSION):
                yield
        finally:
            config.unlink(missing_ok=True)
