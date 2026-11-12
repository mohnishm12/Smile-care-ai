output "backend_repository_url" {
  description = "ECR repository URL for backend images"
  value       = aws_ecr_repository.backend.repository_url
}

output "celery_repository_url" {
  description = "ECR repository URL for celery images"
  value       = aws_ecr_repository.celery.repository_url
}

output "frontend_repository_url" {
  description = "ECR repository URL for frontend images"
  value       = aws_ecr_repository.frontend.repository_url
}
