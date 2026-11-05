import boto3


def describe_subnets(
    b3_sess: boto3.Session,
    filter_prefix=None,
    name_tag_key=None,
) -> dict[str, dict]:
    ec2 = b3_sess.client('ec2')
    resp = ec2.describe_subnets()
    retval = {}
    for subnet in resp['Subnets']:
        names = [pair['Value'] for pair in subnet.get('Tags', []) if pair['Key'] == name_tag_key]
        name = names[0] if names else ''
        retval_key = name if name else subnet['SubnetId']
        if not filter_prefix or name.startswith(filter_prefix):
            retval[retval_key] = subnet
    return retval


def describe_security_groups(b3_sess: boto3.Session, names=()) -> dict[str, dict]:
    ec2 = b3_sess.client('ec2')
    resp = ec2.describe_security_groups()
    return {
        group['GroupName']: group
        for group in resp.get('SecurityGroups', ())
        if not names or group['GroupName'] in names
    }


def subnet_ids(b3_sess: boto3.Session, names, name_tag_key: str) -> list[str]:
    """Resolve subnet names to ids, in the order given.  Raises if a name isn't found."""
    subnets = describe_subnets(b3_sess, name_tag_key=name_tag_key)
    missing = [name for name in names if name not in subnets]
    if missing:
        raise ValueError(f'Subnets not found (tag key: {name_tag_key}): {", ".join(missing)}')
    return [subnets[name]['SubnetId'] for name in names]


def security_group_ids(b3_sess: boto3.Session, names) -> list[str]:
    """Resolve security group names to ids, in the order given.  Raises if a name isn't found."""
    groups = describe_security_groups(b3_sess, names)
    missing = [name for name in names if name not in groups]
    if missing:
        raise ValueError(f'Security groups not found: {", ".join(missing)}')
    return [groups[name]['GroupId'] for name in names]
