from enum import Enum
import inspect
import logging

import click
import colorlog


_logs_init = False


class LogLevel(Enum):
    quiet = logging.WARNING
    info = logging.INFO
    debug = logging.DEBUG


def init_logging(log_level: str):
    global _logs_init
    assert not _logs_init

    logging.addLevelName(logging.DEBUG, 'debug')
    logging.addLevelName(logging.INFO, 'info')
    logging.addLevelName(logging.WARNING, 'warning')
    logging.addLevelName(logging.ERROR, 'error')
    logging.addLevelName(logging.CRITICAL, 'critical')

    handler = colorlog.StreamHandler()
    formatter = colorlog.ColoredFormatter(
        '%(log_color)s%(levelname)8s%(reset)s  %(message)s',
        log_colors={
            'debug': 'white',
            'info': 'cyan',
            'warning': 'yellow',
            'error': 'red',
            'critical': 'red',
        },
    )
    handler.setFormatter(formatter)
    logging.getLogger('mu').setLevel(LogLevel[log_level].value)
    logging.getLogger('__main__').setLevel(LogLevel[log_level].value)
    logging.basicConfig(handlers=(handler,))

    _logs_init = True


def click_options(click_func):
    click.option('--quiet', 'log_level', flag_value=LogLevel.quiet.name, help='WARN+ logging')(
        click_func,
    )
    click.option(
        '--info',
        'log_level',
        flag_value=LogLevel.info.name,
        help='INFO+ logging',
        default=True,
    )(
        click_func,
    )
    click.option('--debug', 'log_level', flag_value=LogLevel.debug.name, help='DEBUG+ logging')(
        click_func,
    )
    return click_func


def logger():
    frame = inspect.stack()[1].frame  # caller's frame
    module = inspect.getmodule(frame)
    return logging.getLogger(module.__name__)
