from mu.libs.utils import deep_merge


def test_deep_merge():
    default_config = {
        'db': {'host': 'localhost', 'port': 5432},
        'logging': {'level': 'info', 'handlers': ['console']},
    }

    user_config = {
        'db': {'port': 5433},
        'logging': {'level': 'debug'},
        'ignore': 'this',
    }

    merged = deep_merge(default_config.copy(), user_config)
    assert merged['db']['host'] == 'localhost'
    assert merged['db']['port'] == 5433
    assert merged['logging']['level'] == 'debug'
    assert merged['logging']['handlers'] == ['console']
    assert 'ignore' not in merged

    assert default_config['db']['port'] == 5432
