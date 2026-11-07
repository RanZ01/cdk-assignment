"""Part 4. Invoke manually with {}. Starts from an EMPTY, unversioned bucket."""
import json
import os
import time
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import urlopen

import boto3
from boto3.dynamodb.conditions import Key

s3 = boto3.client("s3")
table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])


def call_api(url, params):
    target = url + ("&" if "?" in url else "?") + urlencode(params)
    try:
        with urlopen(target, timeout=28) as response:
            return json.loads(response.read().decode())
    except HTTPError as exc:
        raise RuntimeError(f"Plot API HTTP {exc.code}: {exc.read().decode()}") from exc


def wait_for_measurement(bucket, request_id, since_us, size, count, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        options = {
            "KeyConditionExpression": Key("history_group").eq("ALL") & Key("record_key").between(
                f"{bucket}#{since_us:020d}#", f"{bucket}#~"),
            "ConsistentRead": True,
        }
        while True:
            page = table.query(**options)
            for item in page.get("Items", []):
                if item.get("s3_request_id") == request_id:
                    if int(item["total_size"]) != size or int(item["object_count"]) != count:
                        raise RuntimeError("Unexpected bucket contents or concurrent writes. Reset before retrying.")
                    return item
            if not page.get("LastEvaluatedKey"):
                break
            options["ExclusiveStartKey"] = page["LastEvaluatedKey"]
        time.sleep(.1)
    raise TimeoutError(f"No tracker snapshot for S3 request {request_id}; check trigger, permissions and logs.")


def lambda_handler(event, context):
    bucket = os.environ["BUCKET_NAME"]
    api_url = os.environ["PLOT_API_URL"]
    if urlsplit(api_url).scheme != "https":
        raise ValueError("PLOT_API_URL must use HTTPS")
    if s3.list_objects_v2(Bucket=bucket, MaxKeys=1).get("KeyCount", 0):
        raise RuntimeError("Bucket must be empty. Follow the cleanup instructions before running again.")
    call_api(api_url, {"health": "1"})
    # A newline makes the assignment samples 19 and 28 bytes as specified. 
    newline = b"\n" if os.environ.get("ADD_NEWLINE", "false").lower() == "true" else b""
    first = b"Empty Assignment 1" + newline
    second = b"Empty Assignment 2222222222" + newline
    operations = [("put", "assignment1.txt", first, len(first), 1),
                  ("put", "assignment1.txt", second, len(second), 1),
                  ("delete", "assignment1.txt", None, 0, 0),
                  ("put", "assignment2.txt", b"33", 2, 1)]
    records, request_ids = [], []
    started_us = time.time_ns() // 1000
    gap = float(os.environ.get("SLEEP_SECONDS", "1.0"))
    if not .2 <= gap <= 1.5:
        raise ValueError("SLEEP_SECONDS must be between 0.2 and 1.5")
    for index, (op, key, body, size, count) in enumerate(operations):
        if records and time.time_ns() // 1000 - int(records[0]["timestamp_us"]) > 8_000_000:
            raise TimeoutError("10-second window is too close to expiring. Reset and rerun with warm Lambdas.")
        if op == "put":
            result = s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType="text/plain")
        else:
            result = s3.delete_object(Bucket=bucket, Key=key)
        request_id = result["ResponseMetadata"]["RequestId"]
        timeout = 20 if not records else max(.1, 8 - (
            time.time_ns() // 1000 - int(records[0]["timestamp_us"])) / 1e6)
        row = wait_for_measurement(bucket, request_id, started_us, size, count, timeout)
        records.append(row)
        request_ids.append(request_id)
        if index < len(operations) - 1:
            time.sleep(gap)
    plot = call_api(api_url, {"request_ids": ",".join(request_ids)})
    return {"status": "ok", "measured_sizes": [int(x["total_size"]) for x in records],
            "plot": plot}
