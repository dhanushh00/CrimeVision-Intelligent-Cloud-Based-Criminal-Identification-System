"""
CrimeVision - AWS Cloud Resources Provisioning Script
Automatically creates:
1. Rekognition Face Collection ('criminal_collection')
2. DynamoDB Table ('criminal_records') with Primary Key 'RekognitionId'
3. Checks/Creates S3 Bucket ('criminal-images-bucket')
"""

import boto3
from botocore.exceptions import ClientError
from config import AWS_REGION, REKOGNITION_COLLECTION_ID, DYNAMODB_TABLE_NAME, S3_BUCKET_NAME

def setup_rekognition_collection():
    print(f"\n[+] Configuring Amazon Rekognition Collection: '{REKOGNITION_COLLECTION_ID}'...")
    client = boto3.client('rekognition', region_name=AWS_REGION)
    try:
        response = client.create_collection(CollectionId=REKOGNITION_COLLECTION_ID)
        print(f"    ✓ Collection created successfully! ARN: {response.get('CollectionArn')}")
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceAlreadyExistsException':
            print(f"    ✓ Collection '{REKOGNITION_COLLECTION_ID}' already exists.")
        else:
            print(f"    ✗ Error creating Rekognition collection: {e}")

def setup_dynamodb_table():
    print(f"\n[+] Configuring Amazon DynamoDB Table: '{DYNAMODB_TABLE_NAME}'...")
    client = boto3.client('dynamodb', region_name=AWS_REGION)
    try:
        response = client.create_table(
            TableName=DYNAMODB_TABLE_NAME,
            KeySchema=[
                {'AttributeName': 'RekognitionId', 'KeyType': 'HASH'}  # Partition key
            ],
            AttributeDefinitions=[
                {'AttributeName': 'RekognitionId', 'AttributeType': 'S'}
            ],
            BillingMode='PAY_PER_REQUEST'
        )
        print(f"    ✓ DynamoDB Table '{DYNAMODB_TABLE_NAME}' creation initiated. Status: {response['TableDescription']['TableStatus']}")
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceInUseException':
            print(f"    ✓ DynamoDB Table '{DYNAMODB_TABLE_NAME}' already exists.")
        else:
            print(f"    ✗ Error creating DynamoDB table: {e}")

def setup_s3_bucket():
    print(f"\n[+] Configuring Amazon S3 Bucket: '{S3_BUCKET_NAME}'...")
    s3 = boto3.client('s3', region_name=AWS_REGION)
    try:
        if AWS_REGION == 'us-east-1':
            s3.create_bucket(Bucket=S3_BUCKET_NAME)
        else:
            s3.create_bucket(
                Bucket=S3_BUCKET_NAME,
                CreateBucketConfiguration={'LocationConstraint': AWS_REGION}
            )
        print(f"    ✓ S3 Bucket '{S3_BUCKET_NAME}' created successfully.")
    except ClientError as e:
        if e.response['Error']['Code'] in ('BucketAlreadyOwnedByYou', 'BucketAlreadyExists'):
            print(f"    ✓ S3 Bucket '{S3_BUCKET_NAME}' is accessible.")
        else:
            print(f"    ✗ Error creating S3 bucket: {e}")

def main():
    print("=" * 65)
    print("      CrimeVision - Automated AWS Cloud Setup Utility")
    print("=" * 65)
    print(f"Target AWS Region: {AWS_REGION}")

    setup_rekognition_collection()
    setup_dynamodb_table()
    setup_s3_bucket()

    print("\n" + "=" * 65)
    print("✓ Cloud initialization steps completed.")
    print("  Next: Configure AWS Lambda S3 trigger following the README guide.")
    print("=" * 65)

if __name__ == '__main__':
    main()
