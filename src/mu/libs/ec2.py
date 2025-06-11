import boto3


def describe_subnets(
    b3_sess: boto3.Session,
    filter_prefix=None,
    name_tag_key=None,
) -> dict[str, dict]:
    ec2 = boto3.client('ec2')
    resp = ec2.describe_subnets()
    retval = {}
    for subnet in resp['Subnets']:
        names = [pair['Value'] for pair in subnet['Tags'] if pair['Key'] == name_tag_key]
        name = names[0] if names else ''
        retval_key = name if name else subnet['SubnetId']
        if not filter_prefix or name.startswith(filter_prefix):
            retval[retval_key] = subnet
    return retval


def describe_security_groups(b3_sess: boto3.Session, names=()) -> dict[str, dict]:
    ec2 = boto3.client('ec2')
    resp = ec2.describe_security_groups()
    return {
        group['GroupName']: group
        for group in resp.get('SecurityGroups', ())
        if not names or group['GroupName'] in names
    }
