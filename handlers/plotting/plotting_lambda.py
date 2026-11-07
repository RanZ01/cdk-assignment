"""Part 3. Only DynamoDB Query; never Scan. REST API Lambda proxy response."""
import io
import json
import logging
import os
import time
from datetime import datetime, timezone

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import boto3
from boto3.dynamodb.conditions import Key

log = logging.getLogger()
log.setLevel(logging.INFO)
s3 = boto3.client("s3")
table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])


def reply(status, body):
    return {"statusCode": status, "headers": {"Content-Type": "application/json"},
            "body": json.dumps(body)}


def recent_history(bucket, start_us, end_us):
    options = {
        "KeyConditionExpression": Key("history_group").eq("ALL") & Key("record_key").between(
            f"{bucket}#{start_us:020d}#", f"{bucket}#{end_us:020d}#~"),
        "ConsistentRead": True,
    }
    items = []
    while True:
        page = table.query(**options)
        items.extend(page.get("Items", []))
        if not page.get("LastEvaluatedKey"):
            return items
        options["ExclusiveStartKey"] = page["LastEvaluatedKey"]


def build_plot(items, maximum, start_us, end_us, bucket):
    fig, ax = plt.subplots(figsize=(9, 4.5))
    try:
        timestamps = [datetime.fromtimestamp(int(x["timestamp_us"]) / 1e6, timezone.utc) for x in items]
        sizes = [int(x["total_size"]) for x in items]
        if items:
            ax.plot(timestamps, sizes, "o-", label=f"{bucket}: measured size")
        else:
            ax.text(.5, .5, "No measurements in the last 10 seconds", transform=ax.transAxes,
                    ha="center")
        ax.axhline(maximum, color="crimson", linestyle="--",
                   label=f"All buckets / all history max: {maximum} bytes")
        ax.set_xlim(datetime.fromtimestamp(start_us / 1e6, timezone.utc),
                    datetime.fromtimestamp(end_us / 1e6, timezone.utc))
        ax.set_ylim(0, max(maximum, max(sizes, default=0), 1) * 1.2)
        ax.xaxis.set_major_locator(mdates.SecondLocator(interval=1))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S", tz=timezone.utc))
        ax.set(xlabel="Computation time (UTC)", ylabel="Total bucket size (bytes)",
               title="S3 bucket size during the last 10 seconds")
        ax.grid(alpha=.25)
        ax.legend(fontsize=8)
        fig.autofmt_xdate()
        fig.tight_layout()
        output = io.BytesIO()
        fig.savefig(output, format="png", dpi=150)
        return output.getvalue()
    finally:
        plt.close(fig)


def lambda_handler(event, context):
    params = (event or {}).get("queryStringParameters") or {}
    # Initialize plotting imports without writing an S3 object before the experiment.
    if params.get("health") == "1":
        return reply(200, {"status": "ready"})
    bucket = os.environ["BUCKET_NAME"]
    end_us = time.time_ns() // 1000
    start_us = end_us - 10_000_000
    try:
        items = recent_history(bucket, start_us, end_us)
        expected = set(filter(None, params.get("request_ids", "").split(",")))
        observed = {x.get("s3_request_id") for x in items}
        if expected - observed:
            return reply(409, {"error": "Some driver measurements are outside the last 10 seconds or missing.",
                               "missing_request_ids": sorted(expected - observed),
                               "hint": "Clean up, warm the API with ?health=1, and rerun the driver."})
        # LSI shares the base partition and supports strongly consistent reads.
        # Descending numeric size + Limit=1 gives the max across ALL rows/buckets/times.
        result = table.query(IndexName=os.environ["SIZE_INDEX_NAME"],
                             KeyConditionExpression=Key("history_group").eq("ALL"),
                             ScanIndexForward=False, Limit=1, ConsistentRead=True)
        max_item = next(iter(result.get("Items", [])), None)
        maximum = int(max_item["total_size"]) if max_item else 0
        image = build_plot(items, maximum, start_us, end_us, bucket)
        # 'plot' is deliberately included by the tracker as an ordinary bucket object.
        s3.put_object(Bucket=bucket, Key="plot", Body=image, ContentType="image/png")
        return reply(200, {"bucket": bucket, "plot_key": "plot", "point_count": len(items),
                           "global_max_bytes": maximum,
                           "global_max_bucket": max_item["bucket_name"] if max_item else None,
                           "window_start_us": start_us, "window_end_us": end_us})
    except Exception:
        log.exception("Plot generation failed")
        return reply(500, {"error": "Plot generation failed; inspect the plotting Lambda CloudWatch log."})
