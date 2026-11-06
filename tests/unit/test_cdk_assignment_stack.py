import aws_cdk as core
import aws_cdk.assertions as assertions

from cdk_assignment.cdk_assignment_stack import CdkAssignmentStack

# example tests. To run these tests, uncomment this file along with the example
# resource in cdk_assignment/cdk_assignment_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = CdkAssignmentStack(app, "cdk-assignment")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
