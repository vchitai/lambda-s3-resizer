#!/usr/bin/env python3
"""
Test script for S3 Image Resize Lambda function.
This script simulates S3 events to test the Lambda function locally.
"""

import json
import os
import tempfile
from PIL import Image
import boto3
from s3_resize_images import lambda_handler

def create_test_image(filename: str, size: tuple = (2000, 2000)) -> str:
    """Create a test image file."""
    # Create a simple test image
    img = Image.new('RGB', size, color='red')
    
    # Add some content to make it more realistic
    from PIL import ImageDraw, ImageFont
    draw = ImageDraw.Draw(img)
    
    # Try to use a default font, fallback to basic if not available
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Arial.ttf", 50)
    except:
        font = ImageFont.load_default()
    
    draw.text((100, 100), "Test Image", fill='white', font=font)
    draw.text((100, 200), f"Size: {size[0]}x{size[1]}", fill='white', font=font)
    
    img.save(filename, 'JPEG', quality=95)
    return filename

def create_s3_event(bucket_name: str, object_key: str) -> dict:
    """Create a mock S3 event."""
    return {
        "Records": [
            {
                "eventVersion": "2.1",
                "eventSource": "aws:s3",
                "awsRegion": "us-east-1",
                "eventTime": "2024-01-01T00:00:00.000Z",
                "eventName": "ObjectCreated:Put",
                "userIdentity": {
                    "principalId": "EXAMPLE"
                },
                "requestParameters": {
                    "sourceIPAddress": "127.0.0.1"
                },
                "responseElements": {
                    "x-amz-request-id": "EXAMPLE123456789",
                    "x-amz-id-2": "EXAMPLE123/5678abcdefghijklambdaisawesome/mnopqrstuvwxyzABCDEFGH"
                },
                "s3": {
                    "s3SchemaVersion": "1.0",
                    "configurationId": "testConfigRule",
                    "bucket": {
                        "name": bucket_name,
                        "ownerIdentity": {
                            "principalId": "EXAMPLE"
                        },
                        "arn": f"arn:aws:s3:::{bucket_name}"
                    },
                    "object": {
                        "key": object_key,
                        "size": 1024,
                        "eTag": "0123456789abcdef0123456789abcdef",
                        "sequencer": "0A1B2C3D4E5F678901"
                    }
                }
            }
        ]
    }

def test_lambda_function():
    """Test the Lambda function with mock data."""
    print("Testing S3 Image Resize Lambda Function")
    print("=" * 50)
    
    # Create a test image
    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_file:
        test_image_path = tmp_file.name
    
    try:
        print(f"Creating test image: {test_image_path}")
        create_test_image(test_image_path, (2000, 1500))
        
        # Upload to S3 (you'll need to configure AWS credentials)
        bucket_name = "your-test-bucket"  # Replace with your bucket name
        object_key = "test-images/test-image.jpg"
        
        print(f"Uploading to S3: s3://{bucket_name}/{object_key}")
        s3 = boto3.client('s3')
        s3.upload_file(test_image_path, bucket_name, object_key)
        
        # Create S3 event
        event = create_s3_event(bucket_name, object_key)
        
        print("Invoking Lambda function...")
        result = lambda_handler(event, None)
        
        print("Lambda Result:")
        print(json.dumps(result, indent=2))
        
        # Check if resized image was created
        resized_key = f"resized/test-image_resized.jpg"
        try:
            s3.head_object(Bucket=bucket_name, Key=resized_key)
            print(f"✅ Resized image created successfully: s3://{bucket_name}/{resized_key}")
        except s3.exceptions.NoSuchKey:
            print(f"❌ Resized image not found: s3://{bucket_name}/{resized_key}")
        
        # Test deduplication
        print("\nTesting deduplication...")
        result2 = lambda_handler(event, None)
        print("Second invocation result:")
        print(json.dumps(result2, indent=2))
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Cleanup
        if os.path.exists(test_image_path):
            os.unlink(test_image_path)
        print("\nTest completed!")

if __name__ == "__main__":
    # Check if AWS credentials are configured
    try:
        boto3.client('s3').list_buckets()
        test_lambda_function()
    except Exception as e:
        print(f"❌ AWS credentials not configured: {e}")
        print("Please configure AWS credentials using 'aws configure' or environment variables")
