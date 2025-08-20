#!/bin/bash

# Authentication renewal script for SASEWaddle Docker Client
# Handles JWT token refresh and certificate rotation

set -e

echo "Starting SASEWaddle authentication renewal service..."

while true; do
    # Load current authentication config
    if [ ! -f "/config/auth.json" ]; then
        echo "$(date): ERROR: Authentication config file not found"
        sleep 300  # Wait 5 minutes before retrying
        continue
    fi
    
    CLIENT_ID=$(jq -r '.client_id' /config/auth.json)
    ACCESS_TOKEN=$(jq -r '.access_token' /config/auth.json)
    REFRESH_TOKEN=$(jq -r '.refresh_token' /config/auth.json)
    MANAGER_URL=$(jq -r '.manager_url' /config/auth.json)
    CLIENT_API_KEY=$(jq -r '.client_api_key' /config/auth.json)
    
    if [ -z "$CLIENT_ID" ] || [ "$CLIENT_ID" = "null" ]; then
        echo "$(date): ERROR: Invalid authentication configuration"
        sleep 300
        continue
    fi
    
    # Check if JWT token needs renewal (refresh 5 minutes before expiry)
    if [ -n "$ACCESS_TOKEN" ] && [ "$ACCESS_TOKEN" != "null" ]; then
        # Decode JWT to check expiry (basic check)
        TOKEN_PAYLOAD=$(echo "$ACCESS_TOKEN" | cut -d'.' -f2)
        
        # Add padding if needed for base64 decoding
        case $((${#TOKEN_PAYLOAD} % 4)) in
            2) TOKEN_PAYLOAD="${TOKEN_PAYLOAD}==";;
            3) TOKEN_PAYLOAD="${TOKEN_PAYLOAD}=";;
        esac
        
        # Try to decode and check expiry
        TOKEN_EXP=$(echo "$TOKEN_PAYLOAD" | base64 -d 2>/dev/null | jq -r '.exp // empty' 2>/dev/null || echo "")
        
        if [ -n "$TOKEN_EXP" ] && [ "$TOKEN_EXP" != "null" ]; then
            CURRENT_TIME=$(date +%s)
            TIME_TO_EXPIRY=$((TOKEN_EXP - CURRENT_TIME))
            
            if [ $TIME_TO_EXPIRY -lt 300 ]; then  # Less than 5 minutes to expiry
                echo "$(date): JWT token expiring soon, refreshing..."
                
                # Attempt to refresh token
                REFRESH_RESPONSE=$(curl -sf -X POST "$MANAGER_URL/api/v1/auth/refresh" \
                    -H "Content-Type: application/json" \
                    -d "{\"refresh_token\": \"$REFRESH_TOKEN\"}" 2>/dev/null || echo "")
                
                if [ -n "$REFRESH_RESPONSE" ]; then
                    NEW_ACCESS_TOKEN=$(echo "$REFRESH_RESPONSE" | jq -r '.access_token // empty')
                    NEW_REFRESH_TOKEN=$(echo "$REFRESH_RESPONSE" | jq -r '.refresh_token // empty')
                    
                    if [ -n "$NEW_ACCESS_TOKEN" ] && [ "$NEW_ACCESS_TOKEN" != "null" ]; then
                        # Update authentication config
                        jq --arg access_token "$NEW_ACCESS_TOKEN" \
                           --arg refresh_token "$NEW_REFRESH_TOKEN" \
                           '.access_token = $access_token | .refresh_token = $refresh_token' \
                           /config/auth.json > /config/auth.json.tmp
                        
                        mv /config/auth.json.tmp /config/auth.json
                        chmod 600 /config/auth.json
                        
                        echo "$(date): JWT token refreshed successfully"
                        ACCESS_TOKEN="$NEW_ACCESS_TOKEN"
                        REFRESH_TOKEN="$NEW_REFRESH_TOKEN"
                    else
                        echo "$(date): WARNING: Failed to refresh JWT token"
                    fi
                else
                    echo "$(date): ERROR: Token refresh request failed"
                fi
            fi
        fi
    fi
    
    # Check certificate expiry (check every hour)
    HOUR_CHECK=$(($(date +%s) / 3600))
    if [ $((HOUR_CHECK % 1)) -eq 0 ]; then  # Every hour
        if [ -f "/certs/client.crt" ]; then
            # Check certificate expiry (30 days before expiration)
            CERT_EXPIRY=$(openssl x509 -in /certs/client.crt -noout -enddate | cut -d= -f2)
            CERT_EXPIRY_EPOCH=$(date -d "$CERT_EXPIRY" +%s 2>/dev/null || echo "0")
            CURRENT_EPOCH=$(date +%s)
            DAYS_TO_EXPIRY=$(((CERT_EXPIRY_EPOCH - CURRENT_EPOCH) / 86400))
            
            if [ $DAYS_TO_EXPIRY -lt 30 ]; then
                echo "$(date): Client certificate expiring in $DAYS_TO_EXPIRY days, requesting renewal..."
                
                # Request certificate renewal
                CERT_RESPONSE=$(curl -sf -X POST "$MANAGER_URL/api/v1/clients/$CLIENT_ID/renew-cert" \
                    -H "Authorization: Bearer $ACCESS_TOKEN" \
                    -H "Content-Type: application/json" 2>/dev/null || echo "")
                
                if [ -n "$CERT_RESPONSE" ]; then
                    NEW_CLIENT_CERT=$(echo "$CERT_RESPONSE" | jq -r '.certificates.cert // empty')
                    NEW_CLIENT_KEY=$(echo "$CERT_RESPONSE" | jq -r '.certificates.key // empty')
                    NEW_CA_CERT=$(echo "$CERT_RESPONSE" | jq -r '.certificates.ca // empty')
                    
                    if [ -n "$NEW_CLIENT_CERT" ] && [ "$NEW_CLIENT_CERT" != "null" ]; then
                        # Backup old certificates
                        cp /certs/client.crt /certs/client.crt.backup
                        cp /certs/client.key /certs/client.key.backup
                        cp /certs/ca.crt /certs/ca.crt.backup
                        
                        # Install new certificates
                        echo "$NEW_CLIENT_CERT" > /certs/client.crt
                        echo "$NEW_CLIENT_KEY" > /certs/client.key
                        echo "$NEW_CA_CERT" > /certs/ca.crt
                        
                        chmod 600 /certs/client.key
                        chmod 644 /certs/client.crt /certs/ca.crt
                        
                        echo "$(date): Client certificates renewed successfully"
                    else
                        echo "$(date): WARNING: Certificate renewal request failed"
                    fi
                fi
            fi
        fi
    fi
    
    # Sleep for 5 minutes before next check
    sleep 300
done