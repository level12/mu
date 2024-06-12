from flask import Flask

import mu


app = Flask(__name__)


@app.route('/')
def hello_world():
    return '<p>Hello, <strong>World</strong>!</p>'


class ActionHandler(mu.ActionHandler):
    wsgi_app = app


# The entry point for AWS lambda has to be a function
lambda_handler = ActionHandler.on_event
