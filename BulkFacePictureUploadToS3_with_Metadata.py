"""
CrimeVision - Bulk Face Picture Upload to Amazon S3 with Metadata
Uploads criminal database images to Amazon S3 with custom HTTP metadata
(FullName, CrimeType, WantedStatus), which automatically triggers AWS Lambda.
"""

import os
import boto3
from botocore.exceptions import ClientError
from config import AWS_REGION, S3_BUCKET_NAME, S3_PREFIX

# Initialize S3 resource
s3 = boto3.resource('s3', region_name=AWS_REGION)

# Master list of criminal records for indexing:
# Format: (image_filename, full_name, crime_type, wanted_status)
CRIMINAL_DATABASE = [
    ('1.jpg',   'John Doe',          'Robbery',        'Wanted'),
    ('2.jpg',   'Jane Smith',        'Fraud',          'Not Wanted'),
    ('3.jpg',   'David Beckham',     'Match Fixing',   'Wanted'),
    ('4.png',   'Albert Einstein',   'No Crime',       'Not Wanted'),
    ('5.jpg',   'Isaac Newton',      'No Crime',       'Not Wanted'),
    ('6.png',   'Lionel Messi',      'Tax Evasion',    'Wanted'),
    ('7.jpeg',  'Nikola Tesla',      'No Crime',       'Not Wanted'),
    ('8.jpeg',  'MS Dhoni',          'No Crime',       'Not Wanted'),
    ('9.jpeg',  'Mithali Raj',       'No Crime',       'Not Wanted'),
    ('10.jpeg', 'Smriti Mandhana',   'No Crime',       'Not Wanted'),
    ('11.jpeg', 'Hardik Pandya',     'Match Fixing',   'Not Wanted'),
    ('12.jpeg', 'Yuvraj Singh',      'No Crime',       'Not Wanted'),
    ('13.jpg',  'Sachin Tendulkar',  'No Crime',       'Not Wanted'),
    ('14.jpeg', 'Yuzvendra Chahal',  'No Crime',       'Not Wanted'),
    ('15.jpeg', 'Virat Kohli',       'No Crime',       'Not Wanted'),
    ('16.jpg',  'Sunil Gavaskar',    'No Crime',       'Not Wanted'),
    ('17.jpg',  'Kapil Dev',         'No Crime',       'Not Wanted'),
    ('18.jpeg', 'Ruturaj Gaikwad',   'No Crime',       'Not Wanted'),
    ('19.jpeg', 'Kiran Kumar',       'Theft',          'Wanted'),
    ('20.jpeg', 'Vijay',             'Smuggling',      'Wanted'),
    ('21.jpeg', 'Shahrukh Khan',     'No Crime',       'Not Wanted'),
    ('22.jpg',  'Harleen Deol',      'No Crime',       'Not Wanted')
]

def upload_criminal_dataset(dataset=CRIMINAL_DATABASE, images_dir="."):
    """Uploads each image in the dataset along with associated metadata to S3."""
    print("=" * 65)
    print(f"  Uploading Criminal Records to S3 Bucket: {S3_BUCKET_NAME}")
    print(f"  Destination Prefix: {S3_PREFIX}")
    print("=" * 65)

    bucket = s3.Bucket(S3_BUCKET_NAME)
    success_count = 0
    missing_count = 0

    for filename, name, crime, status in dataset:
        filepath = os.path.join(images_dir, filename)

        if not os.path.exists(filepath):
            print(f"  [-] Skipped '{filename}' (File not found locally in '{images_dir}')")
            missing_count += 1
            continue

        s3_key = f"{S3_PREFIX}{filename}"

        try:
            with open(filepath, 'rb') as img_file:
                s3_obj = s3.Object(S3_BUCKET_NAME, s3_key)
                s3_obj.put(
                    Body=img_file,
                    Metadata={
                        'fullname': name,
                        'crime': crime,
                        'status': status
                    },
                    ContentType='image/jpeg' if filename.lower().endswith(('.jpg', '.jpeg')) else 'image/png'
                )
                print(f"  [✓] Uploaded: {filename} -> Name: {name} | Crime: {crime} | Status: {status}")
                success_count += 1

        except ClientError as e:
            print(f"  [✗] Failed to upload '{filename}': {e}")

    print("\n" + "-" * 65)
    print(f"Upload Summary: {success_count} succeeded, {missing_count} skipped/missing.")
    print("Each upload will automatically trigger the AWS Lambda Face Indexing function.")
    print("-" * 65)

if __name__ == '__main__':
    upload_criminal_dataset()
