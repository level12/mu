import pytest

from mu.libs import ec2


@pytest.fixture
def client(moto_sess):
    return moto_sess.client('ec2')


@pytest.fixture
def vpc_id(client):
    return client.create_vpc(CidrBlock='10.0.0.0/16')['Vpc']['VpcId']


def create_subnet(client, vpc_id, cidr, name=None):
    tags = [{'ResourceType': 'subnet', 'Tags': [{'Key': 'Name', 'Value': name}]}] if name else []
    return client.create_subnet(VpcId=vpc_id, CidrBlock=cidr, TagSpecifications=tags)['Subnet'][
        'SubnetId'
    ]


def create_group(client, vpc_id, name):
    return client.create_security_group(VpcId=vpc_id, GroupName=name, Description=name)['GroupId']


def test_describe_subnets_handles_untagged_subnets(moto_sess, client, vpc_id):
    tagged_id = create_subnet(client, vpc_id, '10.0.0.0/24', 'private-a')
    untagged_id = create_subnet(client, vpc_id, '10.0.1.0/24')

    result = ec2.describe_subnets(moto_sess, name_tag_key='Name')

    assert result['private-a']['SubnetId'] == tagged_id
    assert result[untagged_id]['SubnetId'] == untagged_id


def test_subnet_ids(moto_sess, client, vpc_id):
    a_id = create_subnet(client, vpc_id, '10.0.0.0/24', 'private-a')
    b_id = create_subnet(client, vpc_id, '10.0.1.0/24', 'private-b')

    assert ec2.subnet_ids(moto_sess, ['private-b', 'private-a'], 'Name') == [b_id, a_id]

    with pytest.raises(ValueError, match='Subnets not found .+: private-missing'):
        ec2.subnet_ids(moto_sess, ['private-a', 'private-missing'], 'Name')


def test_security_group_ids(moto_sess, client, vpc_id):
    app_id = create_group(client, vpc_id, 'app')
    db_id = create_group(client, vpc_id, 'db')

    assert ec2.security_group_ids(moto_sess, ['db', 'app']) == [db_id, app_id]

    with pytest.raises(ValueError, match='Security groups not found: missing'):
        ec2.security_group_ids(moto_sess, ['app', 'missing'])
