"""Synthetic AWS session for Moto only; never replaces injected runtime auth."""
import tempfile
from pathlib import Path
import boto3
import botocore.session

def configure_mock_session():
    config=Path(tempfile.gettempdir())/'ueba-moto-only.config'
    config.write_text('[profile ueba-moto-only]\nregion=us-east-1\n')
    local=botocore.session.Session(profile='ueba-moto-only')
    local.set_config_variable('config_file',str(config))
    boto3.setup_default_session(botocore_session=local,aws_access_key_id='testing',
                               aws_secret_access_key='testing',region_name='us-east-1')

from contextlib import contextmanager
from unittest.mock import patch
from moto import mock_aws

@contextmanager
def mock_services():
    with mock_aws():
        configure_mock_session()
        # Moto internally creates another Session for region metadata. Bind that
        # metadata lookup to the same synthetic profile without changing AWS_PROFILE.
        with patch('moto.core.base_backend.Session',lambda: boto3.DEFAULT_SESSION):
            yield
