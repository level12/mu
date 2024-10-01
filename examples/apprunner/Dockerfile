FROM public.ecr.aws/lambda/python:3.12

WORKDIR ${LAMBDA_TASK_ROOT}

# Install the apps's dependencies.  This should include mu.
COPY requirements.txt /tmp/requirements.txt

# Its deliberate that this is below requirements.  It means these packages will
# get updated every time our apps' packages get updated.
RUN pip install --break-system-packages -U pip uv

RUN uv pip install --python=/var/lang/bin/python --no-cache-dir -r /tmp/requirements.txt

# Now everything to do with the app
COPY app.py ./

# Uncomment this to get the CMD to be updated in the image.
# RUN echo 'd' > /tmp/annoying.txt

CMD ["app.lambda_handler"]
