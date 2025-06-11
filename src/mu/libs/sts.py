from functools import cache

import boto3


@cache
def caller_identity(b3_sess: boto3.Session):
    sts = b3_sess.client('sts')
    return sts.get_caller_identity()


@cache
def account_id(b3_sess: boto3.Session):
    return caller_identity(b3_sess)['Account']
