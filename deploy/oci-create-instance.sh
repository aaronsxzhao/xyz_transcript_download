#!/bin/bash
# =============================================================================
# Oracle Cloud - Auto-retry ARM Instance Creation
# Keeps trying every 60 seconds until capacity is available
# Usage: bash deploy/oci-create-instance.sh
# =============================================================================

export SUPPRESS_LABEL_WARNING=True

# --- Configuration ---
COMPARTMENT_ID="ocid1.compartment.oc1..aaaaaaaaorvzawio5acl4awquwshitqthiu7yp3k7muym47wv632talxpuoa"
SUBNET_ID="ocid1.subnet.oc1.iad.aaaaaaaahxx7dhu37m5enxzaolx6lxir6iz4pp3sp3o75dcxcy5gw5nyh5fa"
IMAGE_ID="ocid1.image.oc1.iad.aaaaaaaa3axglz7hak6fmtcrpfckybc4j7zkausb4xpbqwbfypzfsto2pdmq"
SSH_KEY_FILE="$HOME/.ssh/oci_podcast.pub"

INSTANCE_NAME="podcast-tool"
SHAPE="VM.Standard.A1.Flex"
OCPUS=2
MEMORY_GB=12

# All three availability domains to cycle through
ADS=(
    "ZBww:US-ASHBURN-AD-1"
    "ZBww:US-ASHBURN-AD-2"
    "ZBww:US-ASHBURN-AD-3"
)

RETRY_INTERVAL=60  # seconds between retries

# --- Script ---
echo "============================================"
echo "  Oracle Cloud ARM Instance Auto-Creator"
echo "============================================"
echo "  Shape: $SHAPE ($OCPUS OCPUs, ${MEMORY_GB}GB RAM)"
echo "  Image: Ubuntu 22.04 aarch64"
echo "  Retry interval: ${RETRY_INTERVAL}s"
echo "  Press Ctrl+C to stop"
echo "============================================"
echo ""

ATTEMPT=0
while true; do
    for AD in "${ADS[@]}"; do
        ATTEMPT=$((ATTEMPT + 1))
        TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
        echo "[$TIMESTAMP] Attempt #$ATTEMPT - Trying $AD..."

        RESULT=$(oci compute instance launch \
            --compartment-id "$COMPARTMENT_ID" \
            --availability-domain "$AD" \
            --shape "$SHAPE" \
            --shape-config "{\"ocpus\": $OCPUS, \"memoryInGBs\": $MEMORY_GB}" \
            --image-id "$IMAGE_ID" \
            --subnet-id "$SUBNET_ID" \
            --display-name "$INSTANCE_NAME" \
            --assign-public-ip true \
            --ssh-authorized-keys-file "$SSH_KEY_FILE" \
            --metadata '{}' \
            2>&1)

        # Check if it succeeded
        if echo "$RESULT" | grep -q '"lifecycle-state"'; then
            echo ""
            echo "============================================"
            echo "  SUCCESS! Instance created!"
            echo "============================================"
            echo ""
            
            # Extract instance ID and IP
            INSTANCE_ID=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['id'])" 2>/dev/null)
            echo "Instance ID: $INSTANCE_ID"
            echo "Availability Domain: $AD"
            echo ""
            echo "Waiting for public IP assignment..."
            sleep 30
            
            # Get the public IP
            if [ -n "$INSTANCE_ID" ]; then
                VNIC_ATTACHMENTS=$(oci compute vnic-attachment list \
                    --compartment-id "$COMPARTMENT_ID" \
                    --instance-id "$INSTANCE_ID" \
                    2>&1)
                VNIC_ID=$(echo "$VNIC_ATTACHMENTS" | python3 -c "import sys,json; print(json.load(sys.stdin)['data'][0]['vnic-id'])" 2>/dev/null)
                
                if [ -n "$VNIC_ID" ]; then
                    VNIC_INFO=$(oci network vnic get --vnic-id "$VNIC_ID" 2>&1)
                    PUBLIC_IP=$(echo "$VNIC_INFO" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['public-ip'])" 2>/dev/null)
                    echo ""
                    echo "============================================"
                    echo "  Public IP: $PUBLIC_IP"
                    echo "============================================"
                    echo ""
                    echo "SSH into your new VM:"
                    echo "  ssh -i ~/.ssh/oci_podcast ubuntu@$PUBLIC_IP"
                    echo ""
                fi
            fi
            
            exit 0
        fi

        # Check error type
        if echo "$RESULT" | grep -q "Out of capacity"; then
            echo "  -> Out of capacity in $AD, trying next..."
        elif echo "$RESULT" | grep -q "LimitExceeded"; then
            echo "  -> Resource limit reached. You may already have the max free tier instances."
            echo "  $RESULT"
            exit 1
        else
            echo "  -> Error: $(echo "$RESULT" | head -5)"
        fi
    done

    echo ""
    echo "All ADs full. Waiting ${RETRY_INTERVAL}s before retrying..."
    echo "(Press Ctrl+C to stop)"
    sleep $RETRY_INTERVAL
done
