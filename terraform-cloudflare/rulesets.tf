# Cloudflare Zone Configuration Ruleset
# Manages edge configuration rules for hasb.dev in phase http_config_settings.
# Overrides SSL/TLS encryption mode to Flexible specifically for web.hasb.dev
# because the origin EC2 container serves plain HTTP on port 80.
resource "cloudflare_ruleset" "web_ssl_override" {
  zone_id     = var.cloudflare_zone_id
  name        = "default"
  description = "Zone-level configuration ruleset for hasb.dev"
  kind        = "zone"
  phase       = "http_config_settings"

  rules = [
    {
      ref         = "web_ssl_flexible_override"
      action      = "set_config"
      description = "Web Subdomain Flexible"
      expression  = "(http.host eq \"${var.web_subdomain}.${var.domain_name}\")"
      enabled     = true
      action_parameters = {
        ssl = "flexible"
      }
    }
  ]
}
