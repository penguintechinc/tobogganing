##! Tobogganing-specific Zeek analysis scripts
##! Provides: policy violation notices, VPN tunnel visibility,
##!           tenant-aware logging, WireGuard metadata extraction

module Tobogganing;

export {
    ## Notice types for Tobogganing-specific events
    redef enum Notice::Type += {
        ## A connection violated a deny policy
        Policy_Violation,
        ## DNS query for a blocked domain
        Blocked_Domain_Query,
        ## Connection from an unauthorized source CIDR
        Unauthorized_Source,
        ## Unusually large data transfer through VPN
        Large_VPN_Transfer,
        ## Port scan detected through VPN tunnel
        VPN_Port_Scan,
    };

    ## WireGuard VPN network prefix (configurable)
    const wg_network: subnet = 10.200.0.0/16 &redef;

    ## Threshold for large transfer notice (bytes)
    const large_transfer_threshold: count = 104857600 &redef;  # 100MB

    ## Blocked domain patterns (loaded from hub-api)
    global blocked_domains: set[string] = {} &redef;
}

# Tag connections that traverse the WireGuard VPN
event connection_state_remove(c: connection)
{
    if ( c$id$orig_h in wg_network || c$id$resp_h in wg_network )
    {
        # Add VPN tag to connection log
        add c$conn$service["vpn-tunnel"];

        # Check for large transfers
        local total_bytes = c$conn$orig_bytes + c$conn$resp_bytes;
        if ( total_bytes > large_transfer_threshold )
        {
            NOTICE([
                $note=Large_VPN_Transfer,
                $conn=c,
                $msg=fmt("Large VPN transfer: %d bytes from %s to %s",
                         total_bytes, c$id$orig_h, c$id$resp_h),
                $sub=fmt("%d bytes", total_bytes),
                $identifier=cat(c$id$orig_h, c$id$resp_h)
            ]);
        }
    }
}

# Monitor DNS queries against blocked domain list
event dns_request(c: connection, msg: dns_msg, query: string, qtype: count, qclass: count)
{
    if ( query in blocked_domains )
    {
        NOTICE([
            $note=Blocked_Domain_Query,
            $conn=c,
            $msg=fmt("DNS query for blocked domain: %s from %s",
                     query, c$id$orig_h),
            $sub=query,
            $identifier=cat(c$id$orig_h, query)
        ]);
    }
}

# Track VPN-internal port scanning via SumStats
event zeek_init()
{
    local r1 = SumStats::Reducer(
        $stream="vpn.port.scan",
        $apply=set(SumStats::UNIQUE)
    );

    SumStats::create([
        $name="detect-vpn-port-scan",
        $epoch=5min,
        $reducers=set(r1),
        $threshold_val(key: SumStats::Key, result: SumStats::Result) = {
            return result["vpn.port.scan"]$unique + 0.0;
        },
        $threshold=25.0,
        $threshold_crossed(key: SumStats::Key, result: SumStats::Result) = {
            NOTICE([
                $note=VPN_Port_Scan,
                $msg=fmt("VPN port scan: %s touched %d unique ports",
                         key$str, result["vpn.port.scan"]$unique),
                $sub=key$str,
                $identifier=key$str
            ]);
        }
    ]);
}

event new_connection(c: connection)
{
    if ( c$id$orig_h in wg_network )
    {
        SumStats::observe(
            "vpn.port.scan",
            SumStats::Key($str=cat(c$id$orig_h)),
            SumStats::Observation($str=cat(c$id$resp_p))
        );
    }
}
