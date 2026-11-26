#!/bin/sh
# Disposable stand only. Never mount the CA signing key or share service keys.
set -eu
umask 077
root=${MIS_SECRET_DIR:-.secrets}
dest=$root/iam-tls
if [ -e "$dest" ]; then
    for name in iam bff; do
        for f in ca.crt tls.crt tls.key; do test -s "$dest/$name/$f"; done
    done
    exit 0
fi
tmp=$(mktemp -d "$root/.iam-tls.XXXXXXXX")
trap 'rm -rf "$tmp"' EXIT
printf '[req]\ndistinguished_name=dn\nx509_extensions=ca\n[dn]\n[ca]\nbasicConstraints=critical,CA:TRUE,pathlen:0\nkeyUsage=critical,keyCertSign\nsubjectKeyIdentifier=hash\n' > "$tmp/ca.cnf"
openssl req -x509 -newkey rsa:2048 -nodes -sha256 -days 365 -subj '/CN=local MIS IAM CA' -config "$tmp/ca.cnf" \
    -keyout "$tmp/ca.key" -out "$tmp/ca.crt" 2>/dev/null
for name in iam bff; do
    dir=$tmp/$name; mkdir "$dir"
    usage=serverAuth; [ "$name" = iam ] || usage=clientAuth
    printf 'basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=%s\nsubjectAltName=DNS:%s\n' "$usage" "$name" > "$tmp/ext"
    openssl req -new -newkey rsa:2048 -nodes -subj "/CN=$name" -keyout "$dir/tls.key" -out "$tmp/leaf.csr" 2>/dev/null
    openssl x509 -req -in "$tmp/leaf.csr" -CA "$tmp/ca.crt" -CAkey "$tmp/ca.key" -set_serial "0x$(openssl rand -hex 16)" \
        -days 365 -sha256 -extfile "$tmp/ext" -out "$dir/tls.crt" 2>/dev/null
    cp "$tmp/ca.crt" "$dir/ca.crt"
    # Parent is private; the non-root container mounts only its own leaf directory.
    chmod 755 "$dir"; chmod 444 "$dir"/*
done
mkdir "$dest"
mv "$tmp/iam" "$tmp/bff" "$dest/"
