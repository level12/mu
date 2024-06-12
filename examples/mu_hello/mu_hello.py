# If you don't want mu as a dependency, copy the ActionHandler src to your project.
import click

import mu


class ActionHandler(mu.ActionHandler):
    """mu.ActionHandler is a helper to handle the events that trigger your lambda.

    It's designed to map "actions" to the methods on this handler.  Calling `mu invoke hello` would
    cause lambda to execute this hello method.  Actions are also used when defining recurring
    events in the mu config file.

    See the parent class for actions that have been provided.
    """

    @staticmethod
    def hello(event, context):
        action_args = event.get('action-args')
        name = action_args[0] if action_args else 'World'

        return f'Hello {name} from mu_hello'

    @staticmethod
    def cli(event, context):
        """Demonstrates how to hook into existing click commands."""
        action_args = event.get('action-args')
        return cli.main(args=action_args, prog_name='mu-hello', standalone_mode=False)


# The entry point for AWS lambda has to be a function
lambda_entry = ActionHandler.on_event


@click.command()
@click.argument('name', default='Alpha Quadrant')
def cli(name: str):
    print(f'Hello {name} from mu_hello')
    return 47
