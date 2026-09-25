#!/usr/bin/env bash
# check-dockerfile-rootless.sh — fail any Dockerfile that ends up running as root.
#
# devops-containers.md requires a non-root process in every container. An
# explicit, approved exception is allowed but must be annotated so the decision
# is visible in review rather than implied by silence.
#
# Usage: check-dockerfile-rootless.sh <Dockerfile>...   (invoked by pre-commit)
set -uo pipefail

status=0

for file in "$@"; do
    [[ -f "$file" ]] || continue

    # An approved exception suppresses the check for the whole file.
    #
    # The pattern is deliberately strict. A loose `#.*ROOT EXCEPTION` match
    # would also fire on comment-shaped lines that are not Dockerfile comments
    # at all — most importantly heredoc bodies, where the token can be smuggled
    # into file content and silently disable the check:
    #
    #     RUN cat <<'EOF' > /etc/motd
    #     # ROOT EXCEPTION (approved)
    #     EOF
    #
    # Requiring the trailing colon plus a non-empty reason means an exception
    # has to be written deliberately, and heredoc payloads do not match by
    # accident. A bypass is also never silent — see the notice below.
    exception="$(grep -nE '^[[:space:]]*#[[:space:]]*ROOT EXCEPTION \(approved\):[[:space:]]*[^[:space:]]' "$file" | head -1)"
    if [[ -n "$exception" ]]; then
        echo "$file: rootless check BYPASSED by approved exception"
        echo "  ${exception}"
        continue
    fi

    # A malformed annotation must not fail open — it reads as an exception to a
    # human but matches nothing above, so call it out explicitly.
    if grep -qE '^[[:space:]]*#.*ROOT EXCEPTION' "$file"; then
        echo "$file: malformed ROOT EXCEPTION annotation — not honoured"
        echo "  Required form: # ROOT EXCEPTION (approved): <reason>"
        status=1
        continue
    fi

    # The effective user is whatever the last USER instruction sets. Strip any
    # group suffix ("appuser:appgroup") before deciding.
    last_user="$(grep -iE '^[[:space:]]*USER[[:space:]]+' "$file" | tail -1 | awk '{print $2}')"
    last_user="${last_user%%:*}"

    if [[ -z "$last_user" ]]; then
        echo "$file: no USER instruction — container would run as root"
        echo "  Add a non-root USER, or annotate: # ROOT EXCEPTION (approved): <reason>"
        status=1
    elif [[ "$last_user" == \$* || "$last_user" == *'${'* ]]; then
        # Resolved at build time from an ARG/ENV — cannot be verified statically.
        echo "$file: final USER is build-arg '$last_user' — cannot verify it is non-root"
        echo "  Use a literal non-root USER, or annotate: # ROOT EXCEPTION (approved): <reason>"
        status=1
    elif [[ "$last_user" == "root" || "$last_user" == "0" || "$last_user" == 0:* ]]; then
        echo "$file: final USER is '$last_user' — container runs as root"
        echo "  Switch to a non-root user, or annotate: # ROOT EXCEPTION (approved): <reason>"
        status=1
    fi
done

exit "$status"
