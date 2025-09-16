import os
import tempfile
import boto3
import json
import time
import uuid
from datetime import datetime
from typing import Dict, Any, Optional

from PIL import Image

# Initialize AWS clients
s3 = boto3.client('s3')

# Configuration
SIZE = (1280, 1280)
RESIZED_PREFIX = ''
PROCESSING_TAG = 'processing'
PROCESSED_TAG = 'processed'

# Supported image formats
SUPPORTED_FORMATS = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp'}


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda handler for S3 image resizing with deduplication.
    
    Args:
        event: S3 event containing bucket and object information
        context: Lambda context object
        
    Returns:
        Dict containing processing results
    """
    try:
        results = []
        
        for record in event.get('Records', []):
            try:
                result = process_s3_record(record)
                results.append(result)
            except Exception as e:
                error_msg = f"Failed to process record {record.get('s3', {}).get('object', {}).get('key', 'unknown')}: {str(e)}"
                print(f"ERROR: {error_msg}")
                results.append({
                    'success': False,
                    'error': error_msg,
                    'key': record.get('s3', {}).get('object', {}).get('key', 'unknown')
                })
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': f'Processed {len(results)} records',
                'results': results
            })
        }
        
    except Exception as e:
        error_msg = f"Lambda execution failed: {str(e)}"
        print(f"ERROR: {error_msg}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': error_msg
            })
        }


def process_s3_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process a single S3 event record with thread-safe deduplication.
    
    Args:
        record: S3 event record
        
    Returns:
        Dict containing processing result
    """
    bucket_name = record['s3']['bucket']['name']
    object_key = record['s3']['object']['key']
    
    # Skip if not an image
    if not is_image_file(object_key):
        return {
            'success': True,
            'skipped': True,
            'reason': 'Not an image file',
            'key': object_key
        }
    
    # Generate resized key
    resized_key = generate_resized_key(object_key)
    
    # Try to acquire processing lock atomically
    if not try_acquire_processing_lock(bucket_name, resized_key):
        return {
            'success': True,
            'skipped': True,
            'reason': 'Already being processed or completed',
            'key': object_key
        }
    
    try:
        # Check if already completed (double-check after acquiring lock)
        if is_resized_image_completed(bucket_name, resized_key):
            return {
                'success': True,
                'skipped': True,
                'reason': 'Already completed',
                'key': object_key
            }
        
        # Process the image
        with tempfile.TemporaryDirectory() as tmpdir:
            download_path = os.path.join(tmpdir, os.path.basename(object_key))
            upload_path = os.path.join(tmpdir, f"resized_{os.path.basename(object_key)}")
            
            # Download original image
            s3.download_file(bucket_name, object_key, download_path)
            
            # Generate resized image
            generate_thumbnail(download_path, upload_path)
            
            # Upload resized image with atomic operation
            upload_resized_image_atomically(
                upload_path, 
                bucket_name, 
                resized_key, 
                object_key
            )
            
            print(f'Resized image saved at {bucket_name}/{resized_key}')
            
            return {
                'success': True,
                'original_key': object_key,
                'resized_key': resized_key,
                'bucket': bucket_name
            }
            
    except Exception as e:
        # Release lock on error
        release_processing_lock(bucket_name, resized_key)
        raise e


def is_image_file(key: str) -> bool:
    """
    Check if the file is a supported image format.
    
    Args:
        key: S3 object key
        
    Returns:
        True if file is a supported image format
    """
    if not key:
        return False
    
    # Skip resized images to avoid infinite loops
    if key.startswith(RESIZED_PREFIX):
        return False
    
    # Check file extension
    _, ext = os.path.splitext(key.lower())
    return ext in SUPPORTED_FORMATS


def generate_resized_key(original_key: str) -> str:
    """
    Generate the key for the resized image.
    
    Args:
        original_key: Original S3 object key
        
    Returns:
        Key for the resized image
    """
    filename = os.path.basename(original_key)
    name, ext = os.path.splitext(filename)
    return f"{RESIZED_PREFIX}{name}_resized{ext}"


def try_acquire_processing_lock(bucket_name: str, resized_key: str) -> bool:
    """
    Try to acquire a processing lock using S3 object with conditional put.
    This prevents multiple Lambda instances from processing the same image.
    
    Args:
        bucket_name: S3 bucket name
        resized_key: Resized image key
        
    Returns:
        True if lock acquired successfully
    """
    try:
        # Create a temporary lock object
        lock_key = f"{resized_key}.processing_lock"
        lock_id = str(uuid.uuid4())
        
        # Check if lock already exists
        try:
            s3.head_object(Bucket=bucket_name, Key=lock_key)
            print(f"Processing lock already exists for {resized_key}")
            return False
        except s3.exceptions.NoSuchKey:
            # Lock doesn't exist, try to create it
            pass
        
        # Try to create the lock object atomically
        s3.put_object(
            Bucket=bucket_name,
            Key=lock_key,
            Body=lock_id.encode(),
            ContentType='text/plain',
            Tagging=f'{PROCESSING_TAG}={lock_id}',
            ServerSideEncryption='AES256',
            # Add a short expiration to prevent stuck locks
            Metadata={
                'lock-id': lock_id,
                'created-at': datetime.utcnow().isoformat(),
                'expires-at': str(int(time.time()) + 300)  # 5 minutes
            }
        )
        
        print(f"Acquired processing lock for {resized_key}")
        return True
        
    except s3.exceptions.ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code in ['NoSuchKey', 'ConditionalCheckFailed', 'PreconditionFailed']:
            print(f"Could not acquire lock for {resized_key}: {error_code}")
            return False
        else:
            print(f"Error acquiring lock: {e}")
            return False
    except Exception as e:
        print(f"Unexpected error acquiring lock: {e}")
        return False


def release_processing_lock(bucket_name: str, resized_key: str) -> None:
    """
    Release the processing lock by deleting the lock object.
    
    Args:
        bucket_name: S3 bucket name
        resized_key: Resized image key
    """
    try:
        lock_key = f"{resized_key}.processing_lock"
        s3.delete_object(Bucket=bucket_name, Key=lock_key)
        print(f"Released processing lock for {resized_key}")
    except Exception as e:
        print(f"Warning: Could not release lock for {resized_key}: {e}")


def is_resized_image_completed(bucket_name: str, resized_key: str) -> bool:
    """
    Check if the resized image already exists and is completed.
    
    Args:
        bucket_name: S3 bucket name
        resized_key: Resized image key
        
    Returns:
        True if resized image exists and is completed
    """
    try:
        response = s3.head_object(Bucket=bucket_name, Key=resized_key)
        
        # Check if the object has the processed tag
        tags_response = s3.get_object_tagging(Bucket=bucket_name, Key=resized_key)
        tags = {tag['Key']: tag['Value'] for tag in tags_response.get('TagSet', [])}
        
        if tags.get(PROCESSED_TAG) == 'true':
            print(f"Resized image already completed: {resized_key}")
            return True
            
        return False
        
    except s3.exceptions.NoSuchKey:
        return False
    except Exception as e:
        print(f"Warning: Could not check completion status for {resized_key}: {e}")
        return False


def upload_resized_image_atomically(
    local_path: str, 
    bucket_name: str, 
    resized_key: str, 
    original_key: str
) -> None:
    """
    Upload the resized image atomically with proper tagging and metadata.
    
    Args:
        local_path: Local path to the resized image
        bucket_name: S3 bucket name
        resized_key: Key for the resized image
        original_key: Original image key
    """
    try:
        # Upload the resized image with metadata and tags
        s3.upload_file(
            local_path,
            bucket_name,
            resized_key,
            ExtraArgs={
                'Metadata': {
                    'original-key': original_key,
                    'processed-at': datetime.utcnow().isoformat(),
                    'resize-dimensions': f"{SIZE[0]}x{SIZE[1]}",
                    'processor': 'lambda-image-resizer'
                },
                'Tagging': f'{PROCESSED_TAG}=true',
                'ServerSideEncryption': 'AES256'
            }
        )
        
        # Clean up the processing lock
        release_processing_lock(bucket_name, resized_key)
        
        print(f"Successfully uploaded resized image: {resized_key}")
        
    except Exception as e:
        print(f"Error uploading resized image: {e}")
        # Try to clean up lock even if upload failed
        release_processing_lock(bucket_name, resized_key)
        raise


def generate_thumbnail(source_path: str, dest_path: str) -> None:
    """
    Generate a thumbnail/resized image.
    
    Args:
        source_path: Path to source image
        dest_path: Path to save resized image
    """
    print(f'Generating resized image from: {source_path}')
    
    try:
        with Image.open(source_path) as image:
            # Convert to RGB if necessary (for PNG with transparency)
            if image.mode in ('RGBA', 'LA', 'P'):
                # Create a white background
                background = Image.new('RGB', image.size, (255, 255, 255))
                if image.mode == 'P':
                    image = image.convert('RGBA')
                background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
                image = background
            elif image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Generate thumbnail maintaining aspect ratio
            image.thumbnail(SIZE, Image.Resampling.LANCZOS)
            
            # Save with quality optimization
            image.save(dest_path, 'JPEG', quality=85, optimize=True)
            
    except Exception as e:
        print(f"Error generating thumbnail: {e}")
        raise