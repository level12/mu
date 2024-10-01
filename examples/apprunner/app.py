import logging
from os import environ

import boto3
from flask import Flask

import mu


log = logging.getLogger()

app = Flask(__name__)


@app.route('/')
def hello_world():
    return '<p>Hello, <strong>World</strong>!</p>'


@app.route('/sqs')
def sqs():
    sqs = boto3.client('sqs', region_name='us-east-2')
    queue_prefix = environ.get('MU_RESOURCE_IDENT')
    queue_name = f'{queue_prefix}-celery'
    response = sqs.get_queue_url(QueueName=queue_name)

    return str((response.get('QueueUrl'), environ.get('MU_ENV')))


@app.route('/log')
def logs_example():
    log.error('This is an error')
    log.warning('This is a warning')
    log.info('This is an info log')
    log.debug('This is a debug log')

    return 'Logs emitted at debug, info, warning, and error levels'


@app.route('/error')
def error():
    raise RuntimeError('Deliberate runtime error')


class ActionHandler(mu.ActionHandler):
    wsgi_app = app


# The entry point for AWS lambda has to be a function
lambda_handler = ActionHandler.on_event
