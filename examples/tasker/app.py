import logging

from flask import Flask

import mu


log = logging.getLogger()

app = Flask(__name__)


@app.route('/')
def hello_world():
    return '<p>Hello, <strong>World</strong>!</p>'


@mu.task
def ping_task(a, *, b):
    print('ping_task()', a, b)


@app.route('/ping')
def ping():
    ping_task.invoke(1, b=2)
    return 'ok'
