"""Storage, measurement, and the S3 event source live together in one stack."""
from pathlib import Path

from aws_cdk import CfnOutput, Duration, Names, RemovalPolicy, Stack
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_notifications as s3n
from constructs import Construct

HANDLERS = Path(__file__).resolve().parents[1] / "handlers"


class DataStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.bucket = s3.Bucket(
            self, "TestBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )
        self.table = dynamodb.Table(
            self, "SizeHistory",
            partition_key=dynamodb.Attribute(
                name="history_group", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="record_key", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )
        # CDK derives a unique index name; the plotter receives it via its environment.
        self.size_index_name = f"{Names.unique_id(self.table)}-TotalSize"
        self.table.add_local_secondary_index(
            index_name=self.size_index_name,
            sort_key=dynamodb.Attribute(
                name="total_size", type=dynamodb.AttributeType.NUMBER
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )
        tracker = lambda_.Function(
            self, "SizeTracker",
            runtime=lambda_.Runtime.PYTHON_3_13,
            architecture=lambda_.Architecture.X86_64,
            code=lambda_.Code.from_asset(str(HANDLERS / "size_tracking")),
            handler="size_tracking_lambda.lambda_handler",
            memory_size=256,
            timeout=Duration.seconds(30),
            environment={"TABLE_NAME": self.table.table_name},
        )
        tracker.add_to_role_policy(iam.PolicyStatement(
            actions=["s3:ListBucket"], resources=[self.bucket.bucket_arn],
        ))
        tracker.add_to_role_policy(iam.PolicyStatement(
            actions=["dynamodb:PutItem"], resources=[self.table.table_arn],
        ))
        destination = s3n.LambdaDestination(tracker)
        self.bucket.add_event_notification(s3.EventType.OBJECT_CREATED, destination)
        self.bucket.add_event_notification(s3.EventType.OBJECT_REMOVED, destination)

        CfnOutput(self, "BucketName", value=self.bucket.bucket_name)
        CfnOutput(self, "TableName", value=self.table.table_name)
        CfnOutput(self, "SizeIndexName", value=self.size_index_name)
