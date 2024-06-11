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

These commands all work on your local system:

```sh
$ mu build
$ docker compose up mu-hello

# In a different shell
$ mu invoke --local


## Usage: AWS


This is assuming you are in the `mu_hello` directory and have AWS auth setup.  `aws sts
get-caller-identity` should be working.

Verify AWS auth:

```sh
$ mu auth-check
Account: 429812345678
Region: us-east-2
Organization owner: you@example.com
```

Ensure IAM and ECR infra. is in place:

```sh
$ mu provision
Account: 429812345678
Region: us-east-2
Organization owner: you@example.com
```


## Testing

### Credentials

This project has a lot of integration tests that use live AWS.  You SHOULD have a dedicated AWS
**account** for mu testing.

An [env-config](https://github.com/level12/env-config) config is present which will use aws-vault
and a "mu-test" profile to load AWS creds.  But, you can use any method you prefer to setup
[credentials for boto3](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/credentials.html).


### Running tests

No CI yet due to need for an AWS account.  Run locally with `tox` or `pytest`.
