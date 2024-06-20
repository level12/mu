from app import app

import mu


class ActionHandler(mu.ActionHandler):
    wsgi_app = app


# The entry point for AWS lambda has to be a function
lambda_handler = ActionHandler.on_event
