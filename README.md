# S3 bucket size history with AWS CDK

This Python CDK v2 project deploys the three Lambda handlers from Assignment 2,
an S3 bucket with create/remove notifications, a DynamoDB history table with a
local secondary index, and a REST API for the plotter. The infrastructure is
split into `S3SizeDataStack` and `S3SizeApplicationStack`. CDK generates the
physical names of the bucket, table, functions, API, and layer. The index name
is derived from the table construct ID. Runtime values are passed through
Lambda environment variables, not fixed names in handler source. Each application
function gets a CDK-created execution role. Its permissions match the three
Assignment 2 policies, with ARNs derived from the new bucket and table.

## Contents

- `handlers/`: the three original Python handlers with resource names supplied
  by CDK environment variables.
- `assets/matplotlib-python313-x86_64.zip`: the existing Linux x86_64,
  Python 3.13 Matplotlib layer. It is deployed from this project; no Console
  upload is needed.
- `cdk_assignment/`: the two infrastructure stacks.

The driver preserves the original Assignment 2 behavior: no newline is
appended, so the literal sample strings are 18 and 27 UTF-8 bytes. The later
assignment text lists 19 and 28 bytes, but that count would require an extra
newline not present in the stated strings.

## Local setup and verification

Use Python 3.13, the AWS CDK v2 CLI, and the `assignment-admin` AWS profile in
`us-east-1`. The project virtual environment contains CDK dependencies; the
Matplotlib layer is a deployment asset rather than a Mac package.

```sh
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
cdk ls --profile assignment-admin
cdk synth --profile assignment-admin
```

`cdk synth` creates `cdk.out` locally and does not deploy resources. If the jsii
cache is not writable, prefix commands with `JSII_RUNTIME_PACKAGE_CACHE=disabled`.

## Deploy and demo

Before the demo, make sure any previous assignment stacks are destroyed. A CDK
bootstrap stack (`CDKToolkit`) may remain because it is CDK infrastructure, not
an assignment stack. Bootstrap this account/region once if it has not already
been bootstrapped:

```sh
cdk bootstrap --profile assignment-admin
```

Deploy both stacks in dependency order:

```sh
cdk deploy --all --profile assignment-admin
```

CloudFormation outputs show the generated bucket/table names, index name,
REST API URL, and driver function name. In the AWS Console, verify the two
assignment stacks and their creation times. Invoke the generated driver
function with `{}` **once**, starting with an empty bucket. Inspect the new
DynamoDB rows and download the `plot` object from the generated bucket.
The plotting API is a public GET endpoint. The driver warms it with `?health=1`
before starting measurements.

CDK creates helper resources for S3 notifications and automatic deletion. In
CloudFormation, identify the three application functions by their Python 3.13
runtime and handler names; helper Lambdas are implementation resources.

To remove the assignment stacks and their data after verification:

```sh
cdk destroy --all --profile assignment-admin
```

The bucket is configured to delete its contents on stack deletion, and the
table is configured to be deleted with the data stack. These policies are for
this disposable assignment deployment. Never run the old `create_resources.py`
alongside this project: CDK owns the resources here.

## Submission

Submit this project directory, including `assets/` and `handlers/`. Exclude
`.venv/`, `.git/`, `cdk.out/`, caches, credentials, and generated plots. The
layer ZIP is about 38 MiB, so verify the GradeScope upload size limit.
