# Transformation Lambda: streams recent raw partitions, maps readings to municipalities, and
# writes results/latest.json. Build from this folder.
FROM public.ecr.aws/lambda/python:3.12

RUN pip install --no-cache-dir shapely==2.1.2 -t ${LAMBDA_TASK_ROOT}

COPY src/airmax_transformation ${LAMBDA_TASK_ROOT}/airmax_transformation

CMD ["airmax_transformation.handler.lambda_handler"]
