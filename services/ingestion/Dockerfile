# Ingestion Lambda: receives OpenAQ messages from SQS and stores them unchanged in S3 raw/.
# boto3 is already in the Lambda base image, so only our code is copied.
# Build from this folder: docker build -t airmax-ingestion services/ingestion
FROM public.ecr.aws/lambda/python:3.12

COPY src/airmax_ingestion ${LAMBDA_TASK_ROOT}/airmax_ingestion

CMD ["airmax_ingestion.handler.lambda_handler"]
