#!/bin/bash

# S3 Image Resize Lambda Deployment Script
set -e

# Configuration
STACK_NAME="s3-image-resize"
BUCKET_NAME="${1:-my-image-bucket}"
REGION="${AWS_DEFAULT_REGION:-us-east-1}"

echo "Deploying S3 Image Resize Lambda..."
echo "Stack Name: $STACK_NAME"
echo "Bucket Name: $BUCKET_NAME"
echo "Region: $REGION"

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo "Error: AWS CLI is not installed. Please install it first."
    exit 1
fi

# Check if SAM CLI is installed
if ! command -v sam &> /dev/null; then
    echo "Error: AWS SAM CLI is not installed. Please install it first."
    exit 1
fi

# Create deployment package
echo "Creating deployment package..."
sam build

# Deploy the stack
echo "Deploying CloudFormation stack..."
sam deploy \
    --template-file .aws-sam/build/template.yaml \
    --stack-name $STACK_NAME \
    --parameter-overrides BucketName=$BUCKET_NAME \
    --capabilities CAPABILITY_IAM \
    --region $REGION \
    --confirm-changeset

echo "Deployment completed successfully!"
echo ""
echo "Next steps:"
echo "1. Upload an image to the S3 bucket: $BUCKET_NAME"
echo "2. Check the 'resized/' folder for the processed image"
echo "3. Monitor CloudWatch logs for the Lambda function"
echo ""
echo "To view logs:"
echo "aws logs tail /aws/lambda/s3-image-resize --follow --region $REGION"
