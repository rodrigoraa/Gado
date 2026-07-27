#!/usr/bin/env bash

set -Eeuo pipefail
umask 077

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd -P)"
COMPOSE=(docker compose --project-directory "${PROJECT_DIR}" -f "${PROJECT_DIR}/compose.yaml")

if (( $# != 1 )); then
    printf 'Uso: %s caminho/gestao-rural-AAAAMMDDTHHMMSSZ.tar.gz\n' "$0" >&2
    exit 2
fi

for command_name in docker tar gzip sha256sum mktemp realpath sed grep; do
    command -v "${command_name}" >/dev/null 2>&1 || {
        printf 'Erro: comando obrigatório não encontrado: %s\n' "${command_name}" >&2
        exit 2
    }
done

[[ -f "$1" ]] || {
    printf 'Erro: backup não encontrado ou inválido: %s\n' "$1" >&2
    exit 2
}
archive="$(realpath -- "$1")"
LOG_FILE="${RESTORE_LOG_FILE:-${PROJECT_DIR}/backups/restore.log}"
mkdir -p -- "$(dirname -- "${LOG_FILE}")"
touch -- "${LOG_FILE}"
chmod 600 -- "${LOG_FILE}"

log() {
    printf '%s %s\n' "$(date --utc '+%Y-%m-%dT%H:%M:%SZ')" "$*" \
        | tee -a "${LOG_FILE}" >&2
}

die() {
    log "ERRO: $*"
    exit 1
}

validate_tar_archive() {
    local archive_path="$1"
    local member=""
    local members=""
    local listing_line=""
    local type_listing=""
    local member_type=""

    members="$(tar --list --gzip --file="${archive_path}")" || return 1
    while IFS= read -r member; do
        case "${member}" in
            ''|/*|../*|*/../*|*/..|*\\*) return 1 ;;
        esac
    done <<<"${members}"

    type_listing="$(tar --list --verbose --gzip --file="${archive_path}")" || return 1
    while IFS= read -r listing_line; do
        member_type="${listing_line:0:1}"
        case "${member_type}" in
            -|d) ;;
            *) return 1 ;;
        esac
    done <<<"${type_listing}"
}

WORK_DIR=""
TRAFFIC_STOPPED="false"
DESTRUCTIVE_STARTED="false"
cleanup() {
    local status=$?
    trap - EXIT
    if [[ -n "${WORK_DIR}" && -d "${WORK_DIR}" ]]; then
        rm -rf -- "${WORK_DIR}"
    fi
    if (( status != 0 )); then
        if [[ "${TRAFFIC_STOPPED}" == "true" && "${DESTRUCTIVE_STARTED}" == "false" ]]; then
            log "Nenhum dado foi substituído; reativando os serviços."
            "${COMPOSE[@]}" up --detach web proxy cloudflared >>"${LOG_FILE}" 2>&1 || true
        fi
        log "Restauração interrompida. Após o início da substituição, os serviços permanecem parados."
    fi
    exit "${status}"
}
trap cleanup EXIT

log "Validando o pacote antes de qualquer alteração."
gzip --test "${archive}" || die "o pacote não é um gzip íntegro."
validate_tar_archive "${archive}" \
    || die "o pacote contém caminhos ou tipos inseguros."
members="$(tar --list --gzip --file="${archive}")" || die "o pacote não pode ser listado."
expected=$'SHA256SUMS\ndatabase.sqlite3\nmedia.tar.gz\nmetadata.txt'
actual="$(printf '%s\n' "${members}" | sort)"
[[ "${actual}" == "${expected}" ]] || die "o pacote contém membros ausentes ou inesperados."
while IFS= read -r member; do
    case "${member}" in
        ''|/*|../*|*/../*|*/..|*\\*) die "o pacote contém caminho inseguro." ;;
    esac
done <<<"${members}"

WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/gestao-rural-restore-XXXXXX")"
tar --extract --gzip --file="${archive}" --directory="${WORK_DIR}" \
    --no-same-owner --no-same-permissions
for required_file in database.sqlite3 media.tar.gz metadata.txt SHA256SUMS; do
    [[ -f "${WORK_DIR}/${required_file}" && ! -L "${WORK_DIR}/${required_file}" ]] \
        || die "arquivo obrigatório ausente ou inválido: ${required_file}."
done
(
    cd -- "${WORK_DIR}"
    sha256sum --check --strict SHA256SUMS >>"${LOG_FILE}"
) || die "as somas SHA-256 não conferem."
grep -qx 'format_version=2' "${WORK_DIR}/metadata.txt" \
    || die "o formato do backup não é compatível com esta versão."
grep -qx 'database_engine=sqlite' "${WORK_DIR}/metadata.txt" \
    || die "o pacote não contém um banco SQLite."
gzip --test "${WORK_DIR}/media.tar.gz" || die "o arquivo de mídia está corrompido."
validate_tar_archive "${WORK_DIR}/media.tar.gz" \
    || die "o arquivo de mídia contém caminhos ou tipos inseguros."

"${COMPOSE[@]}" config --quiet >>"${LOG_FILE}" 2>&1 \
    || die "compose.yaml ou .env inválido."
"${COMPOSE[@]}" run --rm --no-deps -T \
    -v "${WORK_DIR}/database.sqlite3:/tmp/restore.sqlite3:ro" web \
    python -c 'import sqlite3; c=sqlite3.connect("file:/tmp/restore.sqlite3?mode=ro", uri=True); result=c.execute("PRAGMA integrity_check").fetchone(); c.close(); raise SystemExit(0 if result == ("ok",) else 1)' \
    >>"${LOG_FILE}" 2>&1 || die "o SQLite não passou na verificação de integridade."

printf '\nMetadados do backup:\n' >&2
sed -n '1,20p' "${WORK_DIR}/metadata.txt" >&2
printf '\nATENÇÃO: banco e mídia atuais serão integralmente substituídos.\n' >&2
confirmation="${RESTORE_CONFIRM:-}"
if [[ "${confirmation}" != "RESTAURAR" ]]; then
    [[ -t 0 ]] || die "defina RESTORE_CONFIRM=RESTAURAR para uso não interativo."
    read -r -p 'Digite RESTAURAR para continuar: ' confirmation
fi
[[ "${confirmation}" == "RESTAURAR" ]] || die "confirmação recusada; nada foi alterado."

log "Interrompendo o tráfego externo antes do backup preventivo."
"${COMPOSE[@]}" stop cloudflared proxy >>"${LOG_FILE}" 2>&1 \
    || die "não foi possível interromper o tráfego."
TRAFFIC_STOPPED="true"

log "Criando backup preventivo consistente do estado atual."
safety_backup="$(bash "${SCRIPT_DIR}/backup.sh")" \
    || die "o backup preventivo falhou; a restauração foi cancelada."
log "Backup preventivo: ${safety_backup}"

"${COMPOSE[@]}" stop web >>"${LOG_FILE}" 2>&1 \
    || die "não foi possível parar a aplicação."
DESTRUCTIVE_STARTED="true"

log "Substituindo o banco SQLite e o volume de mídia."
"${COMPOSE[@]}" run --rm --no-deps -T \
    -v "${WORK_DIR}:/restore:ro" --entrypoint /bin/sh web -ceu '
        test "$(readlink -f /app/data)" = "/app/data"
        test "$(readlink -f /app/media)" = "/app/media"
        cp /restore/database.sqlite3 /app/data/db.sqlite3.new
        chmod 600 /app/data/db.sqlite3.new
        rm -f /app/data/db.sqlite3-wal /app/data/db.sqlite3-shm
        mv /app/data/db.sqlite3.new /app/data/db.sqlite3
        find /app/media -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
        tar --extract --gzip --file=/restore/media.tar.gz --directory=/app/media \
            --no-same-owner --no-same-permissions
    ' >>"${LOG_FILE}" 2>&1 || die "a substituição dos dados falhou."

log "Aplicando migrations após restaurar o backup."
"${COMPOSE[@]}" run --rm --no-deps -T web \
    python manage.py migrate --noinput >>"${LOG_FILE}" 2>&1 \
    || die "as migrations falharam após a restauração."
"${COMPOSE[@]}" run --rm --no-deps -T web \
    python manage.py collectstatic --noinput >>"${LOG_FILE}" 2>&1 \
    || die "collectstatic falhou após a restauração."
log "Reiniciando aplicação, proxy e túnel."
"${COMPOSE[@]}" up --detach web proxy cloudflared >>"${LOG_FILE}" 2>&1 \
    || die "os dados foram restaurados, mas os serviços não reiniciaram."
TRAFFIC_STOPPED="false"

log "Restauração SQLite concluída."
printf 'Restauração concluída. Backup preventivo: %s\n' "${safety_backup}"
