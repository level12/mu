FROM public.ecr.aws/lambda/python:3.12 as mu-hello

RUN pip install --break-system-packages -U pip uv

# Install the apps's dependencies.  This should include mu.
COPY requirements.txt /tmp/requirements.txt
RUN uv pip install --python=/var/lang/bin/python --no-cache-dir -r /tmp/requirements.txt

# Now everything to do with the app
COPY mu_hello.py ${LAMBDA_TASK_ROOT}/mu_hello.py

# Uncomment this to get the CMD to be updated in the image.
# RUN echo 'd' > /tmp/annoying.txt

CMD ["mu_hello.lambda_entry"]
