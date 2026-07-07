# =============================================================================
# HealFlow AI — Terraform Infrastructure (Baseline)
# Minimal AWS footprint: ECR repositories for the three service images.
# Extend with VPC/ECS/RDS modules as production needs grow.
# =============================================================================

terraform {
  required_version = ">= 1.9.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
  }

  # Recommended: configure a remote backend before running in CI, e.g.
  # backend "s3" {
  #   bucket         = "healflow-terraform-state"
  #   key            = "prod/terraform.tfstate"
  #   region         = "us-east-1"
  #   dynamodb_table = "healflow-terraform-locks"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "healflow-ai"
      ManagedBy   = "terraform"
      Environment = var.environment
    }
  }
}

resource "aws_ecr_repository" "backend" {
  name                 = "healflow-backend"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }
}

resource "aws_ecr_repository" "celery" {
  name                 = "healflow-celery"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }
}

resource "aws_ecr_repository" "frontend" {
  name                 = "healflow-frontend"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }
}

resource "aws_ecr_lifecycle_policy" "keep_recent" {
  for_each = {
    backend  = aws_ecr_repository.backend.name
    celery   = aws_ecr_repository.celery.name
    frontend = aws_ecr_repository.frontend.name
  }

  repository = each.value

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 20 images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 20
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}
