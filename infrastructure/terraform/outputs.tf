output "service_ports" {
  value = {
    redis          = 6380
    postgres       = 5434
    influxdb       = 18087
    qdrant         = 6334
    grafana        = 3001
    gitea          = 3000
    gitea_ssh      = 2222
    woodpecker     = 8012
    taiga_front    = 9001
    taiga_back     = 9002
    taiga_events   = 9003
  }
}
