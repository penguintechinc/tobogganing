# SASEWaddle Terraform Variables

variable "cluster_name" {
  description = "Name of the SASEWaddle cluster"
  type        = string
  default     = "sasewaddle"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "prod"
}

variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-west-2"
}

# VPC Configuration
variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.100.0.0/16"
}

# EKS Configuration
variable "eks_public_access" {
  description = "Enable public access to EKS API endpoint"
  type        = bool
  default     = true
}

variable "node_groups" {
  description = "EKS node group configuration"
  type = map(object({
    instance_types = list(string)
    capacity_type  = string
    min_size       = number
    max_size       = number
    desired_size   = number
    disk_size      = number
    labels         = map(string)
    taints = list(object({
      key    = string
      value  = string
      effect = string
    }))
  }))
  default = {
    general = {
      instance_types = ["t3.medium"]
      capacity_type  = "ON_DEMAND"
      min_size       = 1
      max_size       = 10
      desired_size   = 3
      disk_size      = 50
      labels = {
        role = "general"
      }
      taints = []
    }
    headend = {
      instance_types = ["t3.large"]
      capacity_type  = "ON_DEMAND"
      min_size       = 1
      max_size       = 3
      desired_size   = 1
      disk_size      = 100
      labels = {
        role = "headend"
      }
      taints = [
        {
          key    = "headend"
          value  = "true"
          effect = "NO_SCHEDULE"
        }
      ]
    }
  }
}

# RDS Configuration
variable "enable_rds" {
  description = "Enable RDS for Manager database"
  type        = bool
  default     = false
}

variable "rds_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.micro"
}

variable "rds_allocated_storage" {
  description = "RDS allocated storage in GB"
  type        = number
  default     = 20
}

variable "rds_username" {
  description = "RDS master username"
  type        = string
  default     = "sasewaddle"
}

variable "rds_password" {
  description = "RDS master password"
  type        = string
  sensitive   = true
  default     = ""
}

# Redis Configuration
variable "redis_node_type" {
  description = "ElastiCache Redis node type"
  type        = string
  default     = "cache.t3.micro"
}

variable "redis_num_nodes" {
  description = "Number of Redis cache nodes"
  type        = number
  default     = 1
}

variable "redis_auth_token" {
  description = "Redis AUTH token"
  type        = string
  sensitive   = true
  default     = ""
}

# SSL Configuration
variable "ssl_certificate_arn" {
  description = "ARN of SSL certificate for ALB"
  type        = string
  default     = ""
}

variable "domain_name" {
  description = "Domain name for Route53 records"
  type        = string
  default     = ""
}

# Application Configuration
variable "jwt_secret" {
  description = "JWT secret for token signing"
  type        = string
  sensitive   = true
  default     = ""
}

variable "admin_password" {
  description = "Admin password for SASEWaddle Manager"
  type        = string
  sensitive   = true
  default     = ""
}

variable "admin_email" {
  description = "Admin email for SASEWaddle Manager"
  type        = string
  default     = "admin@example.com"
}

# Container Images
variable "manager_image" {
  description = "Docker image for Manager service"
  type        = string
  default     = "ghcr.io/your-org/sasewaddle/manager:latest"
}

variable "headend_image" {
  description = "Docker image for Headend service"
  type        = string
  default     = "ghcr.io/your-org/sasewaddle/headend:latest"
}

variable "client_image" {
  description = "Docker image for Client"
  type        = string
  default     = "ghcr.io/your-org/sasewaddle/client:latest"
}

# Monitoring Configuration
variable "enable_monitoring" {
  description = "Enable Prometheus and Grafana monitoring"
  type        = bool
  default     = true
}

variable "grafana_admin_password" {
  description = "Grafana admin password"
  type        = string
  sensitive   = true
  default     = ""
}

# Traffic Mirroring Configuration
variable "enable_traffic_mirroring" {
  description = "Enable traffic mirroring for IDS/IPS"
  type        = bool
  default     = false
}

variable "traffic_mirror_destinations" {
  description = "Comma-separated list of traffic mirror destinations"
  type        = string
  default     = ""
}

variable "traffic_mirror_protocol" {
  description = "Traffic mirror protocol (VXLAN, GRE, ERSPAN)"
  type        = string
  default     = "VXLAN"
}

# Backup Configuration
variable "enable_backups" {
  description = "Enable automated backups"
  type        = bool
  default     = true
}

variable "backup_retention_days" {
  description = "Number of days to retain backups"
  type        = number
  default     = 30
}

# Logging Configuration
variable "log_level" {
  description = "Application log level"
  type        = string
  default     = "info"
  validation {
    condition     = contains(["debug", "info", "warn", "error"], var.log_level)
    error_message = "Log level must be one of: debug, info, warn, error."
  }
}

# Resource Tagging
variable "additional_tags" {
  description = "Additional tags to apply to all resources"
  type        = map(string)
  default     = {}
}

# High Availability Configuration
variable "multi_az" {
  description = "Enable multi-AZ deployment"
  type        = bool
  default     = true
}

variable "enable_auto_scaling" {
  description = "Enable auto-scaling for services"
  type        = bool
  default     = true
}

# Security Configuration
variable "enable_pod_security_policies" {
  description = "Enable Kubernetes Pod Security Policies"
  type        = bool
  default     = true
}

variable "enable_network_policies" {
  description = "Enable Kubernetes Network Policies"
  type        = bool
  default     = true
}

# Cost Optimization
variable "use_spot_instances" {
  description = "Use spot instances for cost optimization"
  type        = bool
  default     = false
}

variable "enable_cluster_autoscaler" {
  description = "Enable cluster autoscaler"
  type        = bool
  default     = true
}