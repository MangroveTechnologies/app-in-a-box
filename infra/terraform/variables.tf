variable "project_id" {
  description = "GCP project id"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}

variable "environment" {
  description = "Environment name (dev, test, prod)"
  type        = string
  default     = "dev"
}

variable "service_name" {
  description = "Cloud Run service name"
  type        = string
}

variable "repo_name" {
  description = "Artifact Registry repository name"
  type        = string
}

variable "image" {
  description = "Container image URL"
  type        = string
}

variable "allow_unauthenticated" {
  description = "Allow public access"
  type        = bool
  default     = true
}
