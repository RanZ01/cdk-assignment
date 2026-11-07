"""Check the synthesized application contract without contacting AWS."""
import json
import unittest

import aws_cdk as cdk
from aws_cdk import assertions

from cdk_assignment.application_stack import ApplicationStack
from cdk_assignment.data_stack import DataStack


class InfrastructureTest(unittest.TestCase):
    def test_application_resources_and_generated_names(self):
        app = cdk.App()
        data = DataStack(app, "DataTest")
        ApplicationStack(
            app, "ApplicationTest",
            bucket=data.bucket, table=data.table,
            size_index_name=data.size_index_name,
        )
        data_template = assertions.Template.from_stack(data)
        app_template = assertions.Template.from_stack(app.node.find_child("ApplicationTest"))

        buckets = data_template.find_resources("AWS::S3::Bucket")
        tables = data_template.find_resources("AWS::DynamoDB::Table")
        self.assertEqual(1, len(buckets))
        self.assertEqual(1, len(tables))
        self.assertNotIn("BucketName", next(iter(buckets.values()))["Properties"])
        table_props = next(iter(tables.values()))["Properties"]
        self.assertNotIn("TableName", table_props)
        self.assertEqual(1, len(table_props["LocalSecondaryIndexes"]))
        self.assertEqual(1, len(app_template.find_resources("AWS::ApiGateway::RestApi")))

        expected_handlers = {
            "size_tracking_lambda.lambda_handler",
            "plotting_lambda.lambda_handler",
            "driver_lambda.lambda_handler",
        }
        functions = []
        for template in (data_template, app_template):
            functions += [
                resource["Properties"]
                for resource in template.find_resources("AWS::Lambda::Function").values()
                if resource["Properties"].get("Handler") in expected_handlers
            ]
        self.assertEqual(expected_handlers, {fn["Handler"] for fn in functions})
        self.assertEqual(3, len(functions))
        self.assertTrue(all(fn["Runtime"] == "python3.13" for fn in functions))
        self.assertTrue(all(fn["Architectures"] == ["x86_64"] for fn in functions))
        self.assertTrue(all("FunctionName" not in fn for fn in functions))
        driver = next(fn for fn in functions if fn["Handler"] == "driver_lambda.lambda_handler")
        self.assertNotIn("ADD_NEWLINE", driver["Environment"]["Variables"])
        self.assertEqual(1, len(app_template.find_resources("AWS::Lambda::LayerVersion")))
        self.assertNotIn("dynamodb:Scan", json.dumps(app_template.to_json()))


if __name__ == "__main__":
    unittest.main()
