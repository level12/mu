import base64
import getpass
import hashlib
import json
import logging
from pathlib import Path
import platform
import shlex
import subprocess
import tempfile
import uuid

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
    def __init__(self, label: str, enc_key: str = None):
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
    return subprocess.run(args, **kwargs)


def take(from_: dict, *keys):
    return {k: from_[k] for k in keys}


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
