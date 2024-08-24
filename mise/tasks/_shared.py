import json
from os import environ
from pathlib import Path
import subprocess
import tomllib


base_dpath = Path(__file__).parent.parent.parent.resolve()
reqs_dpath = base_dpath / 'requirements'
pyproj_fpath = base_dpath / 'pyproject.toml'


def run(*args, check=True, **kwargs):
    args = args + kwargs.pop('args', ())
    print(args)
    return subprocess.run(args, **kwargs)


def pip(*args, **kwargs):
    run('pip', args=args, **kwargs)


def pipx_venv() -> str:
    if not pyproj_fpath.exists():
        return environ['PIPX_VENV_NAME']

    with pyproj_fpath.open('rb') as fo:
        config = tomllib.load(fo)
        name_default = config['project']['name'] + '-dev'
    return environ.get('PIPX_VENV_NAME', name_default)


def pipx(cmd, *args, **kwargs):
    run('pipx', cmd, pipx_venv(), *args, **kwargs)


def pipx_install(cmd, *args, **kwargs):
    run('pipx', 'install', *args, **kwargs)


def pipx_pip(*args, **kwargs):
    pipx('runpip', '--', '--quiet', *args, **kwargs)


def pipx_venv_exists() -> bool:
    result = pipx('list', '--json', capture_output=True, check=False)
    packages = json.loads(result.stdout)
    return pipx_venv() in packages
