# Website Lambda: serves the dashboard, the bundled map library, the municipality boundaries and
# results/latest.json from S3. No database; it keeps working if the transformation fails.
# Build from this folder: docker build -t airmax-website services/website
FROM public.ecr.aws/lambda/python:3.12

COPY src/airmax_website ${LAMBDA_TASK_ROOT}/airmax_website

CMD ["airmax_website.handler.lambda_handler"]
