import base64
from dataclasses import InitVar, asdict, dataclass
import getpass
import hashlib
import json
import logging
from pathlib import Path
import platform
import pprint
import shlex
import subprocess
import tempfile
import time
import uuid

import arrow
import boto3
from cryptography.fernet import Fernet


log = logging.getLogger(__name__)


def machine_ident():
    """
    Return a deterministic value based on the current machine's hardware and OS.

    Intended to be used to encrypt AWS session details that will be stored on the file system.
    Predictible but just trying to keep a rogue app on the dev's system from scraping creds
    from a plain text file.  Should be using a dedicated not-important account for testing anyway.
    """
    etc_mid = Path('/etc/machine-id')
    dbus_mid = Path('/var/lib/dbus/machine-id')
    machine_id = etc_mid.read_text() if etc_mid.exists() else dbus_mid.read_text()

    return str(uuid.getnode()) + machine_id


class EncryptedTempFile:
    def __init__(self, label: str, enc_key: str | None = None):
        enc_key = enc_key or machine_ident()
        id_hash: bytes = hashlib.sha256(enc_key.encode()).digest()
        self.fernet_key: str = base64.urlsafe_b64encode(id_hash)
        self.tmp_fpath: Path = Path(tempfile.gettempdir()) / label

    def save(self, data: dict) -> None:
        cipher_suite = Fernet(self.fernet_key)
        data_json: str = json.dumps(data)
        encrypted_data = cipher_suite.encrypt(data_json.encode())

        self.tmp_fpath.write_bytes(encrypted_data)

    def get(self) -> dict:
        blob: bytes = self.tmp_fpath.read_bytes()

        cipher_suite = Fernet(self.fernet_key)
        data_json: str = cipher_suite.decrypt(blob).decode()

        return json.loads(data_json)


def sub_run(*args, **kwargs):
    kwargs['check'] = True
    args = args or kwargs['args']
    log.info(shlex.join(str(arg) for arg in args))

    try:
        return subprocess.run(args, **kwargs)
    except subprocess.CalledProcessError as e:
        if kwargs.get('capture_output'):
            log.error('subprocess stdout: %s', e.stdout.decode('utf-8'))
            log.error('subprocess stderr: %s', e.stderr.decode('utf-8'))
        raise


def take(from_: dict, *keys, strict=True):
    return {k: from_[k] for k in keys if strict or k in from_}


def deep_merge(base, overrides, ignore_extras: bool = True):
    result = dict(base)
    for key, override_value in overrides.items():
        if key not in base and ignore_extras:
            continue
        base_value = result.get(key)
        if isinstance(base_value, dict) and isinstance(override_value, dict):
            result[key] = deep_merge(base_value, override_value)
        else:
            result[key] = override_value
    return result


def host_user():
    return f'{getpass.getuser()}.{platform.node()}'


def print_dict(d, indent=0):
    for key in sorted(d.keys()):
        value = d[key]
        if isinstance(value, dict):
            print('    ' * indent, f'{key}:')
            print_dict(value, indent + 1)
        else:
            print('    ' * indent, f'{key}:', value)


class RetryingAction:
    wait_seq = (0.1, 0.25, 0.5, 0.75, 1, 1.25, 1.5, 2.5, 3, 5, None)
    exc_type: Exception = None
    exc_contains: str = ''
    waiting_for: str = ''

    @classmethod
    def act(cls, *args, **kwargs):
        raise NotImplementedError

    @classmethod
    def run(cls, *args, **kwargs):
        for wait_for in cls.wait_seq:
            try:
                return cls.act(*args, **kwargs)
            except cls.exc_type as exc:
                if cls.exc_contains not in str(exc) or wait_for is None:
                    raise
                log.info(f'Waiting {wait_for}s for {cls.waiting_for}')
                time.sleep(wait_for)


def wait_seq(count, secs):
    extra = [secs] * count
    return (0.1, 0.25, 0.5, 0.75, 1, *extra)


def retry(func, *args, waiting_for, secs=1, count=30, **kwargs):
    for wait_for in wait_seq(count, secs):
        result = func(*args, **kwargs)
        if result:
            return result
        log.info(f'Waiting {wait_for}s for {waiting_for}')
        time.sleep(wait_for)


def compose_build(*service_names):
    sub_run(
        'docker',
        'compose',
        'build',
        '--pull',
        *service_names,
    )


def log_time(timestamp: str) -> arrow.Arrow:
    return arrow.get(int(timestamp))


def log_fmt(time: arrow.Arrow) -> str:
    return time.format('YYYY-MM-DD HH:mm')


@dataclass
class B3DataClass:
    b3_sess: InitVar[boto3.Session | None]

    def __post_init__(self, b3_sess):
        self._b3_sess = b3_sess

    def __str__(self):
        return pprint.pformat(asdict(self))


def first(iterable, empty_val=None):
    try:
        return next(iter(iterable))
    except StopIteration:
        return empty_val
