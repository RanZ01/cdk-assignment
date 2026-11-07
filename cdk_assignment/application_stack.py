"""Plotting API and the experiment driver consume the data stack resources."""
from pathlib import Path

from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack
from aws_cdk import aws_apigateway as apigateway
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_s3 as s3
from constructs import Construct

ROOT = Path(__file__).resolve().parents[1]


class ApplicationStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        bucket: s3.IBucket,
        table: dynamodb.ITable,
        size_index_name: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        matplotlib_layer = lambda_.LayerVersion(
            self, "MatplotlibLayer",
            code=lambda_.Code.from_asset(
                str(ROOT / "assets" / "matplotlib-python313-x86_64.zip")
            ),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_13],
            compatible_architectures=[lambda_.Architecture.X86_64],
            removal_policy=RemovalPolicy.DESTROY,
        )
        plotter = lambda_.Function(
            self, "Plotter",
            runtime=lambda_.Runtime.PYTHON_3_13,
            architecture=lambda_.Architecture.X86_64,
            code=lambda_.Code.from_asset(str(ROOT / "handlers" / "plotting")),
            handler="plotting_lambda.lambda_handler",
            layers=[matplotlib_layer],
            memory_size=1024,
            timeout=Duration.seconds(28),
            environment={
                "BUCKET_NAME": bucket.bucket_name,
                "TABLE_NAME": table.table_name,
                "SIZE_INDEX_NAME": size_index_name,
            },
        )
        plotter.add_to_role_policy(iam.PolicyStatement(
            actions=["dynamodb:Query"],
            resources=[table.table_arn, f"{table.table_arn}/index/{size_index_name}"],
        ))
        plotter.add_to_role_policy(iam.PolicyStatement(
            actions=["s3:PutObject"], resources=[bucket.arn_for_objects("plot")],
        ))

        api = apigateway.RestApi(self, "PlotApi")
        api.root.add_method("GET", apigateway.LambdaIntegration(plotter))

        driver = lambda_.Function(
            self, "Driver",
            runtime=lambda_.Runtime.PYTHON_3_13,
            architecture=lambda_.Architecture.X86_64,
            code=lambda_.Code.from_asset(str(ROOT / "handlers" / "driver")),
            handler="driver_lambda.lambda_handler",
            memory_size=256,
            timeout=Duration.seconds(90),
            environment={
                "BUCKET_NAME": bucket.bucket_name,
                "TABLE_NAME": table.table_name,
                "PLOT_API_URL": api.url,
            },
        )
        driver.add_to_role_policy(iam.PolicyStatement(
            actions=["s3:ListBucket"], resources=[bucket.bucket_arn],
        ))
        driver.add_to_role_policy(iam.PolicyStatement(
            actions=["s3:PutObject", "s3:DeleteObject"],
            resources=[bucket.arn_for_objects(key) for key in (
                "assignment1.txt", "assignment2.txt",
            )],
        ))
        driver.add_to_role_policy(iam.PolicyStatement(
            actions=["dynamodb:Query"],
            resources=[table.table_arn],
        ))

        CfnOutput(self, "PlotApiUrl", value=api.url)
        CfnOutput(self, "DriverFunctionName", value=driver.function_name)
