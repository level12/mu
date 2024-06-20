FROM public.ecr.aws/lambda/python:3.12

WORKDIR ${LAMBDA_TASK_ROOT}
ENV APP_DIR examples/tasker

# Install the apps's dependencies.  This should include mu.
COPY $APP_DIR/requirements.txt /tmp/requirements.txt

# Its deliberate that this is below requirements.  It means these packages will
# get updated every time our apps' packages get updated.
RUN pip install --break-system-packages -U pip uv

RUN uv pip install --python=/var/lang/bin/python --no-cache-dir -r /tmp/requirements.txt

# Now everything to do with the app
COPY $APP_DIR/app.py $APP_DIR/handler.py .
COPY mu mu

# Uncomment this to get the CMD to be updated in the image.
# RUN echo 'd' > /tmp/annoying.txt

CMD ["handler.lambda_handler"]
