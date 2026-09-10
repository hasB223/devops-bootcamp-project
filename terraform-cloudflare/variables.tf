variable "cloudflare_account_id" {
  description = "Cloudflare Account ID (non-secret)"
  type        = string
}

variable "cloudflare_zone_id" {
  description = "Cloudflare Zone ID for hasb.dev (non-secret)"
  type        = string
}

variable "domain_name" {
  description = "Root domain name"
  type        = string
  default     = "hasb.dev"
}

variable "web_subdomain" {
  description = "Web application subdomain"
  type        = string
  default     = "web"
}

variable "monitoring_subdomain" {
  description = "Monitoring dashboard subdomain"
  type        = string
  default     = "monitoring"
}

variable "docs_subdomain" {
  description = "Documentation portal subdomain"
  type        = string
  default     = "docs"
}

variable "web_origin_ipv4" {
  description = "Web server origin IPv4 address (Elastic IP)"
  type        = string
  default     = "18.142.89.74"
}
