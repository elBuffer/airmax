# Terraform deployment

Terraform provisions two private S3 buckets, the SQS queue, three ZIP-based Python Lambdas, the
production SNS subscription and five-minute EventBridge Rule, and the unauthenticated website
Function URL. The subscription and schedule exist only in `prd`; `dev` is invoked manually. Every
named resource starts with `andre-airmax-<stage>` by default.

## Prerequisites

- Python 3.11+ and `uv`;
- Terraform;
- `.env` copied from `.env.example` and filled with your AWS credentials and account ID;
- the existing `lambda-execution-role` (Terraform reuses it and does not modify it).

Run from the repository root:

```powershell
uv run python tools/package_lambdas.py
.\with-env.ps1 aws sts get-caller-identity
.\with-env.ps1 terraform -chdir=infra/terraform init
.\with-env.ps1 terraform -chdir=infra/terraform validate
.\with-env.ps1 terraform -chdir=infra/terraform plan -var="stage=dev"
```

The provider refuses to operate outside `AWS_ACCOUNT_ID`. Review the plan before running:

```powershell
.\with-env.ps1 terraform -chdir=infra/terraform apply -var="stage=dev"
```

For `prd`, also pass `-var="openaq_topic_arn=..."`. Only `prd` subscribes to the real topic and
activates the SQS event-source mapping; `dev` and `qa` use replay so they cannot steal production
messages.

Delete the temporary environment with:

```powershell
.\with-env.ps1 terraform -chdir=infra/terraform destroy -var="stage=dev"
```

Terraform empties `dev` and `qa` buckets and deletes their one-day Lambda log groups. Production
buckets retain deletion protection and must be emptied deliberately.

## Account constraints

This account denies ECR and IAM policy changes. Deployment therefore uses ZIP packages and the
existing role's attached policy. Docker still checks the Lambda-like Linux environment locally, but
the AWS-managed ZIP runtime is not byte-for-byte identical; see
[`docs/architecture.md`](../../docs/architecture.md#lambda-packaging-constraint). Smoke-test every
deployment in AWS.

The configuration uses EventBridge Rules, not EventBridge Scheduler. It creates no IAM role, does
not set reserved concurrency, and uses no Athena, Glue, Redshift, Aurora, or DynamoDB resources.
The Function URL intentionally uses `NONE` authentication for this PoC.
