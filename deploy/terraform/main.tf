# SASEWaddle Terraform Configuration
# This configuration deploys SASEWaddle to cloud providers

terraform {
  required_version = ">= 1.0"
  
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.20"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.10"
    }
  }
  
  # Configure remote state backend
  backend "s3" {
    # Configure these values or use terraform init with -backend-config
    # bucket = "your-terraform-state-bucket"
    # key    = "sasewaddle/terraform.tfstate"
    # region = "us-west-2"
  }
}

# Local variables
locals {
  name = var.cluster_name
  
  tags = {
    Environment = var.environment
    Project     = "SASEWaddle"
    ManagedBy   = "Terraform"
  }
}

# Data sources
data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_caller_identity" "current" {}

data "aws_region" "current" {}

# VPC Module
module "vpc" {
  source = "./modules/vpc"
  
  name               = local.name
  cidr               = var.vpc_cidr
  availability_zones = slice(data.aws_availability_zones.available.names, 0, 3)
  
  tags = local.tags
}

# EKS Cluster Module
module "eks" {
  source = "./modules/eks"
  
  name                    = local.name
  vpc_id                  = module.vpc.vpc_id
  subnet_ids              = module.vpc.private_subnet_ids
  endpoint_private_access = true
  endpoint_public_access  = var.eks_public_access
  
  # Node groups
  node_groups = var.node_groups
  
  tags = local.tags
  
  depends_on = [module.vpc]
}

# RDS for Manager database (optional)
module "rds" {
  source = "./modules/rds"
  count  = var.enable_rds ? 1 : 0
  
  name           = "${local.name}-db"
  vpc_id         = module.vpc.vpc_id
  subnet_ids     = module.vpc.private_subnet_ids
  
  engine         = "postgres"
  engine_version = "15"
  instance_class = var.rds_instance_class
  allocated_storage = var.rds_allocated_storage
  
  database_name = "sasewaddle"
  username      = var.rds_username
  password      = var.rds_password
  
  backup_retention_period = 7
  backup_window          = "03:00-04:00"
  maintenance_window     = "mon:04:00-mon:05:00"
  
  tags = local.tags
}

# ElastiCache Redis for session storage
module "redis" {
  source = "./modules/redis"
  
  name       = "${local.name}-redis"
  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnet_ids
  
  node_type           = var.redis_node_type
  num_cache_nodes     = var.redis_num_nodes
  parameter_group     = "default.redis7"
  port               = 6379
  
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  auth_token                = var.redis_auth_token
  
  tags = local.tags
}

# Application Load Balancer for Manager
module "alb" {
  source = "./modules/alb"
  
  name               = "${local.name}-alb"
  vpc_id             = module.vpc.vpc_id
  subnet_ids         = module.vpc.public_subnet_ids
  certificate_arn    = var.ssl_certificate_arn
  
  target_groups = {
    manager = {
      port     = 8000
      protocol = "HTTP"
      health_check_path = "/health"
    }
  }
  
  tags = local.tags
}

# Network Load Balancer for Headend (WireGuard)
resource "aws_lb" "headend_nlb" {
  name               = "${local.name}-headend-nlb"
  internal           = false
  load_balancer_type = "network"
  subnets            = module.vpc.public_subnet_ids
  
  enable_deletion_protection = false
  
  tags = merge(local.tags, {
    Name = "${local.name}-headend-nlb"
  })
}

resource "aws_lb_target_group" "headend_wireguard" {
  name     = "${local.name}-headend-wg"
  port     = 51820
  protocol = "UDP"
  vpc_id   = module.vpc.vpc_id
  
  health_check {
    enabled             = true
    healthy_threshold   = 2
    interval            = 30
    matcher             = "200"
    path                = "/health"
    port                = "8080"
    protocol            = "HTTP"
    timeout             = 5
    unhealthy_threshold = 2
  }
  
  tags = local.tags
}

resource "aws_lb_listener" "headend_wireguard" {
  load_balancer_arn = aws_lb.headend_nlb.arn
  port              = "51820"
  protocol          = "UDP"
  
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.headend_wireguard.arn
  }
}

# IAM roles and policies
module "iam" {
  source = "./modules/iam"
  
  name         = local.name
  cluster_name = module.eks.cluster_name
  
  # Additional policies for SASEWaddle services
  additional_policies = [
    {
      name = "SASEWaddleManagerPolicy"
      policy = jsonencode({
        Version = "2012-10-17"
        Statement = [
          {
            Effect = "Allow"
            Action = [
              "secretsmanager:GetSecretValue",
              "secretsmanager:DescribeSecret"
            ]
            Resource = "*"
          }
        ]
      })
    }
  ]
  
  tags = local.tags
}

# Secrets Manager for sensitive configuration
resource "aws_secretsmanager_secret" "sasewaddle_secrets" {
  name        = "${local.name}-secrets"
  description = "SASEWaddle sensitive configuration"
  
  tags = local.tags
}

resource "aws_secretsmanager_secret_version" "sasewaddle_secrets" {
  secret_id = aws_secretsmanager_secret.sasewaddle_secrets.id
  secret_string = jsonencode({
    redis_password    = var.redis_auth_token
    jwt_secret       = var.jwt_secret
    admin_password   = var.admin_password
    rds_password     = var.enable_rds ? var.rds_password : ""
  })
}

# Route53 DNS records (optional)
data "aws_route53_zone" "main" {
  count = var.domain_name != "" ? 1 : 0
  name  = var.domain_name
}

resource "aws_route53_record" "manager" {
  count   = var.domain_name != "" ? 1 : 0
  zone_id = data.aws_route53_zone.main[0].zone_id
  name    = "manager.${var.domain_name}"
  type    = "A"
  
  alias {
    name                   = module.alb.dns_name
    zone_id                = module.alb.zone_id
    evaluate_target_health = true
  }
}

resource "aws_route53_record" "headend" {
  count   = var.domain_name != "" ? 1 : 0
  zone_id = data.aws_route53_zone.main[0].zone_id
  name    = "headend.${var.domain_name}"
  type    = "A"
  
  alias {
    name                   = aws_lb.headend_nlb.dns_name
    zone_id                = aws_lb.headend_nlb.zone_id
    evaluate_target_health = true
  }
}