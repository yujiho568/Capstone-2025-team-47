import os
import boto3
from datetime import datetime
from zoneinfo import ZoneInfo

dynamodb = boto3.client('dynamodb')

def lambda_handler(event, context):
    table_name = os.environ['TABLE_NAME']

    # Compute KST date strings
    now_kst = datetime.now(ZoneInfo("Asia/Seoul"))
    date_path = now_kst.strftime("%Y/%m/%d")      # e.g., 2025/08/25
    date_dash = now_kst.strftime("%Y-%m-%d")

    total = 0
    paginator = dynamodb.get_paginator('scan')
    for page in paginator.paginate(TableName=table_name, Select='COUNT', FilterExpression='attribute_exists(eventID)'):
        total += page.get('Count', 0)
        if total >= 3000:
            break

    return {
        "count": total,
        "date_path": date_path,
        "date_dash": date_dash
    }
