# Terraform deployment

Terraform provisions two private S3 buckets, three ZIP-based Python Lambdas, the five-minute
production EventBridge Rule, and the unauthenticated website Function URL. `dev` and `qa` receive
a disposable queue. `prd` reads the existing `openaq-andre` queue and adds a Terraform-owned DLQ
without owning the source queue. Every named resource starts with `andre-airmax-<stage>` by default.

## Prerequisites

- Python 3.11+ and `uv`;
- Terraform 1.4+;
- `.env` copied from `.env.example` and filled with your AWS credentials and account ID;
- the existing `lambda-execution-role` (Terraform reuses it and does not modify it).

## Stages are workspaces

Each stage has its own Terraform workspace and therefore its own state file, so a `dev` command can
never plan changes to `prd`. The workspace name is the stage; there is no `stage` variable. Terraform
refuses to plan in the `default` workspace. Check where you are before every plan or destroy:

```powershell
.\with-env.ps1 terraform '-chdir=infra/terraform' workspace show
```

State is local and ignored by Git (`infra/terraform/terraform.tfstate.d/<stage>/`). Back up the
`prd` state; losing it orphans the production resources.

## Deploy

Run from the repository root. `make deploy STAGE=dev` performs the first four steps.

```powershell
uv run python tools/package_lambdas.py
.\with-env.ps1 terraform '-chdir=infra/terraform' init
.\with-env.ps1 terraform '-chdir=infra/terraform' workspace select '-or-create=true' dev
.\with-env.ps1 terraform '-chdir=infra/terraform' plan '-out=dev.tfplan'
```

The provider refuses to operate outside `AWS_ACCOUNT_ID`. Review the plan, then apply exactly it:

```powershell
.\with-env.ps1 terraform '-chdir=infra/terraform' apply 'dev.tfplan'
```

Delete the temporary environment from the `dev` workspace with:

```powershell
.\with-env.ps1 terraform '-chdir=infra/terraform' workspace select dev
.\with-env.ps1 terraform '-chdir=infra/terraform' destroy
```

Terraform empties `dev` and `qa` buckets and deletes their one-day Lambda log groups. Production
buckets retain deletion protection and must be emptied deliberately; production logs are kept for
14 days.

## Production activation

The first `prd` deployment creates the queue consumer and the five-minute schedule **disabled**, so it
cannot consume the `openaq-andre` backlog. Smoke-test by invoking the Lambdas directly. Terraform
attaches a 14-day DLQ after five failed deliveries.

Before activation, raise the externally owned source queue's visibility timeout to 150 seconds:

```powershell
$queueUrl = .\with-env.ps1 aws sqs get-queue-url '--region=eu-west-1' '--queue-name=openaq-andre' '--query=QueueUrl' '--output=text'
.\with-env.ps1 aws sqs set-queue-attributes '--region=eu-west-1' "--queue-url=$queueUrl" '--attributes=VisibilityTimeout=150'
```

Activation is a reviewed code change, not a command-line flag, so a later plan can never silently
switch production off again. In `main.tf`, set `ingestion_enabled = true`, commit, then plan and
apply in the `prd` workspace. Ingestion uses batches of 100 and is capped at two concurrent Lambda
invocations, reducing request cost while bounding load. Set `schedule_enabled = true` the same way
once ingestion is healthy.

Enabling ingestion deletes messages from the provided queue as they are processed. Terraform never
deletes the queue itself; `dev` and `qa` use replay so they cannot steal production messages.

## Account constraints

This account denies ECR and IAM policy changes. Deployment therefore uses ZIP packages and the
existing role's attached policy. Docker still checks the Lambda-like Linux environment locally, but
the AWS-managed ZIP runtime is not byte-for-byte identical; see
[`docs/architecture.md`](../../docs/architecture.md#lambda-packaging-constraint). Smoke-test every
deployment in AWS.

The production ingestion timeout is 25 seconds because a cold S3 write exceeded 5 seconds in the
AWS smoke test. Before enabling ingestion, the externally owned queue's visibility timeout must be
raised from 30 to at least 150 seconds to retain AWS's recommended six-times timeout margin.

The configuration uses EventBridge Rules, not EventBridge Scheduler. It creates no IAM role, does
not set reserved concurrency, and uses no Athena, Glue, Redshift, Aurora, or DynamoDB resources.
The Function URL intentionally uses `NONE` authentication for this PoC.
