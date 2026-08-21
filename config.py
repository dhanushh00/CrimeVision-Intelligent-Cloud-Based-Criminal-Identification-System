"""
CrimeVision - Central Configuration File
Handles AWS credentials, resource identifiers, and application thresholds.
Can be overridden via environment variables or a .env file.
"""

import os
from pathlib import Path

# Load .env file if python-dotenv is installed
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
except ImportError:
    pass

# ==============================
# AWS Configuration Settings
# ==============================
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# Amazon S3 Bucket
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "criminal-images-bucket")
S3_PREFIX = os.getenv("S3_PREFIX", "criminals/")

# Amazon Rekognition
REKOGNITION_COLLECTION_ID = os.getenv("REKOGNITION_COLLECTION_ID", "criminal_collection")
MATCH_CONFIDENCE_THRESHOLD = float(os.getenv("MATCH_CONFIDENCE_THRESHOLD", "80.0"))
MAX_FACES_TO_MATCH = int(os.getenv("MAX_FACES_TO_MATCH", "5"))

# Amazon DynamoDB
DYNAMODB_TABLE_NAME = os.getenv("DYNAMODB_TABLE_NAME", "criminal_records")
DYNAMODB_PRIMARY_KEY = "RekognitionId"

# ==============================
# GUI & Application Settings
# ==============================
APP_TITLE = "CrimeVision - Intelligent Criminal Identification System"
WINDOW_WIDTH = 900
WINDOW_HEIGHT = 700
THEME = "dark"
