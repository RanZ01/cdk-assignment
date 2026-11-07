"""Part 2. Handler: size_tracking_lambda.lambda_handler (or lambda_function.lambda_handler)."""
import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from urllib.parse import unquote_plus

import boto3

log = logging.getLogger()
log.setLevel(logging.INFO)
s3 = boto3.client("s3")
table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])


def lambda_handler(event, context):
    written = []
    for record in event.get("Records", []):
        if record.get("eventSource") != "aws:s3":
            continue
        name = record.get("eventName", "")
        if not name.startswith(("ObjectCreated:", "ObjectRemoved:")):
            continue
        bucket = record["s3"]["bucket"]["name"]
        total, count = 0, 0
        # list_objects_v2 returns only up to 1000 objects per page.
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket):
            for obj in page.get("Contents", []):
                total += obj["Size"]
                count += 1
        timestamp_us = time.time_ns() // 1000
        request_id = record.get("responseElements", {}).get("x-amz-request-id", "")
        event_id = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()[:24]
        item = {
            "history_group": "ALL", "record_key": f"{bucket}#{timestamp_us:020d}#{event_id}",
            "bucket_name": bucket, "timestamp_us": timestamp_us,
            "computed_at": datetime.fromtimestamp(timestamp_us / 1_000_000, timezone.utc).isoformat(),
            "total_size": total, "object_count": count,
            "event_name": name, "object_key": unquote_plus(record["s3"]["object"]["key"]),
            "s3_request_id": request_id, "event_id": event_id,
        }
        # S3 may deliver duplicates: each execution is a new measured snapshot.
        table.put_item(Item=item)
        log.info("snapshot=%s", json.dumps(item))
        written.append({"bucket": bucket, "total_size": total, "object_count": count})
    return {"written": written}
