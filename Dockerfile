# mu-hello runs locally and on production lambda
FROM public.ecr.aws/lambda/python:3.12 as mu-hello

RUN pip install --user -U pip

# Install the apps's dependencies
# COPY requirements/aws.txt /tmp
# RUN pip install --no-cache-dir --target ${LAMBDA_TASK_ROOT} -r /tmp/aws.txt

# Now everything to do with the app
COPY mu_hello/mu_hello.py ${LAMBDA_TASK_ROOT}/mu_hello.py
COPY mu ${LAMBDA_TASK_ROOT}/mu

# Uncomment this to get the CMD to be updated in the image.
# RUN echo 'd' > /tmp/annoying.txt

CMD ["mu_hello.lambda_entry"]

# If you use a non-lambda image, you can add the lambda runtime so that you can invoke locally
# in docker.
# https://github.com/aws/aws-lambda-runtime-interface-emulator
# FROM mu-hello as mu-hello-rie

# # Install the Python package used by RIE for the Python runtime
# RUN pip install --no-warn-script-location --user awslambdaric

# ENTRYPOINT [ "/usr/local/bin/aws-lambda-rie", "/var/lang/bin/python", "-m", "awslambdaric" ]
# CMD ["mu_hello.lambda_entry"]
