#!/bin/sh
# The enclosing directories are private; only the individually mounted app
# password must be readable by container UID 10001 on Linux bind mounts.
set -eu
umask 077
root=${MIS_SECRET_DIR:-.secrets}
mkdir -p "$root/db/apps" "$root/db/migrators"
[ -e .env ] || cp .env.example .env
secret() {
    if [ ! -e "$1" ]; then
        openssl rand -hex 32 > "$1"
        chmod "$2" "$1"
    fi
    [ -s "$1" ] || { echo "Empty secret: $1" >&2; exit 1; }
}
secret "$root/postgres-password" 600
secret "$root/iam-key" 444
sh infra/db/prepare-iam.sh
for owner in iam screening content reporting files ai ${MIS_BFF_DB:+bff}; do
    secret "$root/db/apps/$owner" 444
    secret "$root/db/migrators/$owner" 600
done
