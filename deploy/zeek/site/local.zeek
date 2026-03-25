##! Tobogganing local Zeek configuration
##! Loaded by default when Zeek starts

# Load standard analysis scripts
@load base/frameworks/logging
@load base/frameworks/notice
@load base/frameworks/sumstats
@load base/protocols/conn
@load base/protocols/dns
@load base/protocols/http
@load base/protocols/ssl
@load base/protocols/ftp
@load base/protocols/smtp
@load base/protocols/ssh
@load base/protocols/dhcp

# Load policy scripts for threat detection
@load policy/frameworks/notice/community-id
@load policy/misc/detect-traceroute
@load policy/protocols/conn/known-hosts
@load policy/protocols/conn/known-services
@load policy/protocols/dns/detect-external-names
@load policy/protocols/http/detect-sqli
@load policy/protocols/ssl/validate-certs

# JSON output for all logs (Elasticsearch/Loki compatible)
@load policy/tuning/json-logs

# Load Tobogganing custom scripts
@load ./tobogganing.zeek
