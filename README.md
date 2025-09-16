# AWS Lambda S3 Image Resize với Deduplication

Giải pháp serverless để tự động resize ảnh upload lên S3 với cơ chế deduplication tích hợp để ngăn chặn xử lý trùng lặp.

## Tính năng

- **Tự động Resize Ảnh**: Resize ảnh về kích thước 1280x1280 pixel trong khi giữ nguyên tỷ lệ
- **Deduplication**: Ngăn chặn xử lý trùng lặp sử dụng S3 object tagging và locking
- **Lưu trữ cùng Bucket**: Lưu ảnh đã resize trong cùng bucket dưới prefix `resized/`
- **Hỗ trợ nhiều định dạng**: JPG, PNG, BMP, GIF, TIFF, và WebP
- **Xử lý lỗi**: Xử lý lỗi toàn diện và logging
- **Thread-safe**: Xử lý an toàn khi có nhiều Lambda instance chạy song song
- **Tối ưu chi phí**: Không cần DynamoDB, chỉ sử dụng S3

## Kiến trúc

```
S3 Bucket (images) → Lambda Function → S3 Bucket (resized/) + Lock Objects
```

## Cơ chế Deduplication

Hệ thống sử dụng cơ chế lock dựa trên S3 objects:

1. **Lock Object**: Tạo file `.processing_lock` để đánh dấu đang xử lý
2. **Atomic Operations**: Sử dụng S3 conditional operations để tránh race condition
3. **Tagging**: Sử dụng S3 object tags để đánh dấu trạng thái hoàn thành
4. **Auto-cleanup**: Tự động dọn dẹp lock objects sau khi hoàn thành

## Yêu cầu

- AWS CLI đã cấu hình với quyền phù hợp
- AWS SAM CLI đã cài đặt
- Python 3.11+

## Triển khai

1. **Clone và chuyển vào thư mục**:
   ```bash
   git clone <repository-url>
   cd aws-lambda-s3-resize-images
   ```

2. **Triển khai bằng script có sẵn**:
   ```bash
   ./deploy.sh your-bucket-name
   ```

   Hoặc thủ công bằng SAM:
   ```bash
   sam build
   sam deploy --guided
   ```

## Cấu hình

### Environment Variables

Không cần environment variables đặc biệt - tất cả cấu hình được hardcode trong Lambda function.

### Parameters

- `BucketName`: Tên S3 bucket cho ảnh
- `ResizeSize`: Kích thước tối đa cho ảnh đã resize (mặc định: 1280)

## Cách hoạt động

1. **Trigger**: S3 event kích hoạt Lambda khi có ảnh được upload
2. **Validation**: Kiểm tra file có phải định dạng ảnh được hỗ trợ không
3. **Lock Acquisition**: Thử lấy lock để xử lý ảnh (ngăn chặn duplicate processing)
4. **Double-check**: Kiểm tra lại xem ảnh đã được xử lý chưa
5. **Processing**: Download, resize, và upload vào thư mục `resized/`
6. **Cleanup**: Dọn dẹp lock object và đánh dấu hoàn thành

## Xử lý Race Condition

Khi có 2 Lambda instance chạy song song:

1. **Instance A** tạo lock object thành công → tiếp tục xử lý
2. **Instance B** thấy lock object đã tồn tại → bỏ qua
3. **Instance A** hoàn thành → xóa lock object và đánh dấu processed
4. **Instance B** (nếu chạy lại) sẽ thấy ảnh đã processed → bỏ qua

## Cấu trúc File

```
aws-lambda-s3-resize-images/
├── s3_resize_images.py      # Lambda function chính
├── requirements.txt         # Python dependencies
├── template.yaml           # CloudFormation/SAM template
├── deploy.sh              # Script triển khai
├── test_lambda.py         # Script test
└── README.md              # File này
```

## Testing

Chạy test script để kiểm tra:

```bash
python test_lambda.py
```

**Lưu ý**: Cần cấu hình AWS credentials trước khi chạy test.

## Monitoring

- **CloudWatch Logs**: `/aws/lambda/s3-image-resize`
- **S3 Metrics**: Theo dõi upload/download operations
- **Lock Objects**: Kiểm tra các file `.processing_lock` trong bucket

## Chi phí

- **Lambda**: Trả theo số lần invoke và thời gian thực thi
- **S3**: Chi phí storage và request (rất thấp)
- **Data Transfer**: Tối thiểu cho operations cùng region
- **Không có DynamoDB**: Tiết kiệm chi phí đáng kể

## Troubleshooting

### Các vấn đề thường gặp

1. **Permission Errors**: Đảm bảo Lambda có quyền S3 đầy đủ
2. **Memory Issues**: Tăng memory Lambda nếu xử lý ảnh lớn
3. **Timeout Errors**: Tăng timeout Lambda cho file lớn
4. **Lock Stuck**: Lock objects sẽ tự expire sau 5 phút

### Debugging

Xem logs real-time:
```bash
aws logs tail /aws/lambda/s3-image-resize --follow
```

## Bảo mật

- S3 bucket chặn public access
- Lambda chạy với quyền tối thiểu cần thiết
- Tất cả operations được log để audit
- Sử dụng server-side encryption cho tất cả objects

## Ưu điểm so với DynamoDB approach

1. **Đơn giản hơn**: Không cần quản lý DynamoDB table
2. **Chi phí thấp hơn**: Không có chi phí DynamoDB
3. **Reliable hơn**: S3 có độ tin cậy cao hơn
4. **Dễ debug**: Có thể xem lock objects trực tiếp trong S3
5. **Auto-cleanup**: Lock objects tự động expire

## License

MIT License - xem file LICENSE để biết chi tiết# lambda-s3-resizer
