#!/usr/bin/env python3
"""CDK entry point for the S3 size history application."""
import os

import aws_cdk as cdk

from cdk_assignment.data_stack import DataStack
from cdk_assignment.application_stack import ApplicationStack

app = cdk.App()
environment = cdk.Environment(
    account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
    region=os.environ.get("CDK_DEFAULT_REGION", "us-east-1"),
)

data = DataStack(app, "S3SizeDataStack", env=environment)
ApplicationStack(
    app,
    "S3SizeApplicationStack",
    bucket=data.bucket,
    table=data.table,
    size_index_name=data.size_index_name,
    env=environment,
)
app.synth()
