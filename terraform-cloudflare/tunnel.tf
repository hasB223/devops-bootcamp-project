resource "cloudflare_zero_trust_tunnel_cloudflared" "monitoring" {
  account_id = var.cloudflare_account_id
  name       = "devops-monitoring-tunnel"
  config_src = "cloudflare"
}

resource "cloudflare_zero_trust_tunnel_cloudflared_config" "monitoring" {
  account_id = var.cloudflare_account_id
  tunnel_id  = cloudflare_zero_trust_tunnel_cloudflared.monitoring.id

  config = {
    ingress = [
      {
        hostname = "${var.monitoring_subdomain}.${var.domain_name}"
        service  = "http://localhost:3000"
      },
      {
        service = "http_status:404"
      }
    ]
  }
}
