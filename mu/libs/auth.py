import logging

import boto3


log = logging.getLogger(__name__)


def b3_sess(region_name: str | None = None):
    # Assuming credentials come from the environment.  config.aws_region is None by default so, if
    # not set, the region from the environment should be used.
    return boto3.Session(region_name=region_name)
