"""
CrimeVision - AWS Lambda Face Indexing Function
Triggered on S3 PutObject events in 'criminal-images-bucket'.
Indexes faces in Amazon Rekognition Collection ('criminal_collection')
and stores person metadata in DynamoDB ('criminal_records').
"""

import boto3
import json
import urllib.parse

# Initialize AWS SDK clients
dynamodb = boto3.client('dynamodb')
s3 = boto3.client('s3')
rekognition = boto3.client('rekognition')

# Configuration
COLLECTION_ID = "criminal_collection"
TABLE_NAME = "criminal_records"

def index_faces(bucket, key):
    """Detect and index faces from the uploaded image in Rekognition collection."""
    response = rekognition.index_faces(
        CollectionId=COLLECTION_ID,
        Image={"S3Object": {"Bucket": bucket, "Name": key}},
        DetectionAttributes=['DEFAULT'],
        MaxFaces=5,
        QualityFilter='AUTO'
    )
    return response

def save_record_to_dynamodb(table_name, face_id, full_name, crime_type="Unknown", status="Unknown", image_key=""):
    """Stores faceId + criminal metadata into DynamoDB."""
    response = dynamodb.put_item(
        TableName=table_name,
        Item={
            'RekognitionId': {'S': face_id},
            'FullName': {'S': full_name},
            'CrimeType': {'S': crime_type},
            'WantedStatus': {'S': status},
            'ImageKey': {'S': image_key}
        }
    )
    return response

def lambda_handler(event, context):
    """Main Lambda Entrypoint for S3 ObjectCreated events."""
    print("Received event:", json.dumps(event, indent=2))

    results = []

    for record in event.get('Records', []):
        bucket = record['s3']['bucket']['name']
        raw_key = record['s3']['object']['key']
        # S3 keys in events are URL encoded
        key = urllib.parse.unquote_plus(raw_key)

        print(f"Processing object '{key}' from bucket '{bucket}'...")

        try:
            # 1. Fetch metadata attached to S3 object
            head_resp = s3.head_object(Bucket=bucket, Key=key)
            metadata = head_resp.get('Metadata', {})

            full_name = metadata.get('fullname', 'Unknown')
            crime_type = metadata.get('crime', 'Unknown')
            wanted_status = metadata.get('status', 'Unknown')

            # 2. Index faces in Amazon Rekognition
            rek_resp = index_faces(bucket, key)
            face_records = rek_resp.get('FaceRecords', [])

            if not face_records:
                print(f"Warning: No faces detected in image '{key}'.")
                results.append({
                    "key": key,
                    "status": "NO_FACES_DETECTED"
                })
                continue

            # 3. Store each indexed face in DynamoDB
            indexed_face_ids = []
            for face_record in face_records:
                face_id = face_record['Face']['FaceId']
                indexed_face_ids.append(face_id)
                save_record_to_dynamodb(TABLE_NAME, face_id, full_name, crime_type, wanted_status, key)
                print(f"Successfully indexed FaceId '{face_id}' for '{full_name}' into DynamoDB table '{TABLE_NAME}'.")

            results.append({
                "key": key,
                "status": "SUCCESS",
                "indexed_faces": indexed_face_ids,
                "person": full_name
            })

        except Exception as e:
            print(f"Error processing key '{key}' from bucket '{bucket}': {str(e)}")
            results.append({
                "key": key,
                "status": "ERROR",
                "error": str(e)
            })

    return {
        "statusCode": 200,
        "body": json.dumps(results)
    }
