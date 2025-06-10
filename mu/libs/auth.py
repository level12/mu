import logging

import boto3

from mu.config import Config


log = logging.getLogger(__name__)


def b3_sess(config: Config | None = None, *, region_name: str | None = None, testing=False):
    # Assuming credentials come from the environment.  config.aws_region is None by default so, if
    # not set, the region from the environment should be used.
    region_name = config.aws_region if config else region_name

    sess = boto3.Session(
        region_name=region_name or 'us-east-2' if testing else None,
        # Shortcircuit whatever auth exists in our environment (assumes mocks will be used)
        aws_access_key_id='abc' if testing else None,
        aws_secret_access_key='def' if testing else None,
        aws_session_token='mu-testing' if testing else None,
    )

    if config:
        config.apply_sess(sess, testing=testing)

    return sess
