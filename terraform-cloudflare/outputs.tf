output "web_fqdn" {
  description = "Public URL for web application"
  value       = "https://${var.web_subdomain}.${var.domain_name}"
}

output "monitoring_fqdn" {
  description = "Public URL for monitoring dashboard"
  value       = "https://${var.monitoring_subdomain}.${var.domain_name}"
}

output "docs_fqdn" {
  description = "Public URL for documentation portal"
  value       = "https://${var.docs_subdomain}.${var.domain_name}"
}

output "tunnel_id" {
  description = "UUID of the Cloudflare Zero Trust Tunnel"
  value       = cloudflare_zero_trust_tunnel_cloudflared.monitoring.id
}
