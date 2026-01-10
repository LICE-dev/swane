#!/bin/bash
set -e

# Recupera l'UID, GID e USERNAME dall'host (passati come variabili)
: "${HOST_UID:=1000}"
: "${HOST_GID:=1000}"
: "${HOST_USER:=user}"

# Crea il gruppo se non esiste
if ! getent group "$HOST_GID" >/dev/null; then
    groupadd -g "$HOST_GID" "$HOST_USER"
fi

# Crea l'utente se non esiste
if ! id "$HOST_USER" >/dev/null 2>&1; then
    useradd -m -u "$HOST_UID" -g "$HOST_GID" -s /bin/bash "$HOST_USER"
fi

# Cambia proprietà della home (in caso di mount)
chown -R "$HOST_UID:$HOST_GID" /home/"$HOST_USER"

# Esegui il comando come utente host
exec gosu "$HOST_USER" "$@"
