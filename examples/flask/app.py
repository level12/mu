from flask import Flask

import mu


app = Flask(__name__)


@app.route('/')
def hello_world():
    return '<p>Hello, World!</p>'


class ActionHandler(mu.ActionHandler):
    """mu.ActionHandler is a helper to handle the events that trigger your lambda.

    It's designed to map "actions" to the methods on this handler.  Calling `mu invoke hello` would
    cause lambda to execute this hello method.  Actions are also used when defining recurring
    events in the mu config file.

    See the parent class for actions that have been provided.
    """

    wsgi_app = app

    @classmethod
    def on_event(cls, event, context):
        """The entry point for AWS lambda"""
        keys = set(event.keys())
        wsgi_keys = {'headers', 'requestContext', 'routeKey', 'rawPath'}
        if cls.wsgi_app and wsgi_keys.issubset(keys):
            cls.wsgi(event, context)

        return cls.on_action('do-action', event, context)



# The entry point for AWS lambda has to be a function
# lambda_entry = ActionHandler.on_event


def lambda_entry(event, context):
    print(event)
    print(context)
    return ''
