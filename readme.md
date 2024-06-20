Mu
================================================

AWS Lambda support for Python projects.

## Project Setup

To use mu, a project needs a `pyproject.toml` and either

1. a `mu.toml` in the same directory (takes precedence); or
2. `tools.mu` sections in the `pyproject.toml`

It also needs

* Dockerfile
* compose.yaml (or docker-compose.yaml if you insist)
* An entry point in the app for the lambda events

An example application with these required elements can be found at:
[mu_hello](https://github.com/level12/mu/tree/master/mu_hello)


## Usage: Local

Let's demonstrate usage with [`mu_hello`](https://github.com/level12/mu/tree/master/mu_hello).
Assuming you have copied that source locally and are in the directory:

```shell
$ mu build
$ docker compose up mu-hello

# Watch current shell for log output and, in a new shell, run:
$ mu invoke --local
```

That command should have output like:
```
{'context': {'aws_request_id': '83fd7a58-5f6d-45e1-8092-b509c4f60898',
             'function_name': 'test_function',
             'function_version': '$LATEST',
             'invoked_function_arn': 'arn:aws:lambda:us-east-1:012345678912:function:test_function',
             'log_group_name': '/aws/lambda/Functions',
             'log_stream_name': '$LATEST',
             'memory_limit_in_mb': '3008',
             'remaining_time': 299967},
 'error': None,
 'event': {'action-args': [], 'do-action': 'diagnostics'}}
```

And the first shell should have output like:

```
11 Jun 2024 19:28:28,809 [INFO] (rapid) INIT START(type: on-demand, phase: init)
...
11 Jun 2024 19:28:28,843 [INFO] (rapid) INVOKE RTDONE(status: success, produced bytes: 0, duration: 0.724000ms)
```

Now invoke the hello command:

```sh
$ mu invoke --local hello
'Hello World from mu_hello'

# with arguments
$ mu invoke --local hello 'Capt. Picard'
'Hello Capt. Picard from mu_Hello'

# call a Click command
$ mu invoke --local cli
47

# And you should see the following in the docker shell
'Hello Alpha Quadrant from mu_Hello'
```

## Usage: AWS


This is assuming you are (still) in the `mu_hello` directory and have AWS auth setup.  `aws sts
get-caller-identity` should be working.

```sh
Verify AWS auth:
$ mu auth-check
Account: 429812345678
Region: us-east-2
Organization owner: you@example.com
```

Note that mu has the concept of an "environment" which is used when naming objects to support
provision and deployment for beta, prod, etc.  There is a default environment that is part of the
mu config and defaults to `you.your-host`.


```sh
# Ensure IAM and ECR infra. is in place for the enterprise environment
$ mu provision enterprise
    info  Role created: starfleet-mu-hello-lambda-enterprise
    info  Policy created: starfleet-mu-hello-lambda-enterprise-logs
    info  Policy created: starfleet-mu-hello-lambda-enterprise-ecr-repo
    info  Repository created: starfleet-mu-hello-enterprise
    info  Waiting 0.1s for role to be ready
    info  Waiting 0.25s for role to be ready
    ...[snip]...
    info  Provision finished for env: enterprise

# Build and push image, setup aws lambda
$ mu deploy --build enterprise
    info  docker compose build --pull
[+] Building 0.3s (10/10)
...[snip docker output]...
    info  Tagged, pushing...
    info  Tagged and pushed: 429829037495.dkr.ecr.us-east-2.amazonaws.com/starfleet-mu-hello-enterprise mu-hello-2024-06-11T21.31.09
    info  Deploying: 429829037495.dkr.ecr.us-east-2.amazonaws.com/starfleet-mu-hello-enterprise:mu-hello-2024-06-11T21.31.09
    info  Lambda function created: starfleet-mu-hello-handler-enterprise
    info  Function arn: arn:aws:lambda:us-east-2:429829037495:function:starfleet-mu-hello-handler-enterprise
    info  Waiting for lambda to be updated: starfleet-mu-hello-handler-enterprise


$ mu invoke --env enterprise
{'context': {'aws_request_id': 'cc44e34f-b7f1-4f2a-a314-e4dd2513b229'
...[snip]...
```


## Usage: Async Tasks

Async task workers without a broker/queue:

```python
from flask import Flask
import mu

app = Flask(__name__)


@mu.task
def ping_task(a, *, b):
    print('ping_task()', a, b)


@app.route('/ping')
def ping():
    # ping_task() will be called through async lambda invokation
    ping_task.invoke(1, b=2)
    return 'ok'
```

Be mindeful of:

- [async invocation](https://docs.aws.amazon.com/lambda/latest/dg/invocation-async.html)
- [retries](https://docs.aws.amazon.com/lambda/latest/dg/invocation-retries.html)


## Testing

### Credentials

This project has a lot of integration tests that use live AWS.  You SHOULD have a dedicated AWS
**account** for mu testing.

An [env-config](https://github.com/level12/env-config) config is present which will use aws-vault
and a "mu-test" profile to load AWS creds.  But, you can use any method you prefer to setup
[credentials for boto3](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/credentials.html).


### Running tests

No CI yet due to need for an AWS account.  Run locally with `tox` or `pytest`.
