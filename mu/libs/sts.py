from functools import cache

import boto3


@cache
def account_id(b3_sess: boto3.Session):
    sts = b3_sess.client('sts')
    identity = sts.get_caller_identity()
    return identity['Account']
