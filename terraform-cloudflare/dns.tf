# Web Application A-Record (matches live proxied state)
resource "cloudflare_dns_record" "web" {
  zone_id = var.cloudflare_zone_id
  name    = var.web_subdomain
  type    = "A"
  content = var.web_origin_ipv4
  proxied = true
  ttl     = 1
}

# Monitoring Dashboard CNAME pointing to Tunnel (matches live proxied state)
resource "cloudflare_dns_record" "monitoring" {
  zone_id = var.cloudflare_zone_id
  name    = var.monitoring_subdomain
  type    = "CNAME"
  content = "${cloudflare_zero_trust_tunnel_cloudflared.monitoring.id}.cfargotunnel.com"
  proxied = true
  ttl     = 1
}

# Documentation Portal CNAME pointing to GitHub Pages (matches live proxied state)
resource "cloudflare_dns_record" "docs" {
  zone_id = var.cloudflare_zone_id
  name    = var.docs_subdomain
  type    = "CNAME"
  content = "hasb223.github.io"
  proxied = true
  ttl     = 1
}
