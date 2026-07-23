#!/usr/bin/env bash

set -Eeuo pipefail
umask 077

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_DIR="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd -P)"
COMPOSE=(docker compose --project-directory "${PROJECT_DIR}" -f "${PROJECT_DIR}/compose.yaml")
BACKUP_DIR="${BACKUP_DIR:-${PROJECT_DIR}/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
LOG_FILE="${BACKUP_LOG_FILE:-${BACKUP_DIR}/backup.log}"

for command_name in docker tar gzip sha256sum mktemp; do
    command -v "${command_name}" >/dev/null 2>&1 || {
        printf 'Erro: comando obrigatório não encontrado: %s\n' "${command_name}" >&2
        exit 2
    }
done

case "${RETENTION_DAYS}" in
    ''|*[!0-9]*) printf 'Erro: BACKUP_RETENTION_DAYS deve ser inteiro.\n' >&2; exit 2 ;;
esac
(( RETENTION_DAYS >= 1 )) || {
    printf 'Erro: BACKUP_RETENTION_DAYS deve ser maior que zero.\n' >&2
    exit 2
}

mkdir -p -- "${BACKUP_DIR}"
BACKUP_DIR="$(CDPATH= cd -- "${BACKUP_DIR}" && pwd -P)"
case "${BACKUP_DIR}" in
    /|/tmp|/var/tmp|"${PROJECT_DIR}") printf 'Erro: diretório de backup inseguro.\n' >&2; exit 2 ;;
esac
if [[ "${LOG_FILE}" != /* ]]; then
    LOG_FILE="${PROJECT_DIR}/${LOG_FILE#./}"
fi
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
REMOTE_COPY=""
PARTIAL_ARCHIVE=""
cleanup() {
    local status=$?
    trap - EXIT
    if [[ -n "${REMOTE_COPY}" ]]; then
        "${COMPOSE[@]}" exec -T web rm -f -- "${REMOTE_COPY}" >/dev/null 2>&1 || true
    fi
    if [[ -n "${WORK_DIR}" && -d "${WORK_DIR}" ]]; then
        rm -rf -- "${WORK_DIR}"
    fi
    if [[ -n "${PARTIAL_ARCHIVE}" && -f "${PARTIAL_ARCHIVE}" ]]; then
        rm -f -- "${PARTIAL_ARCHIVE}"
    fi
    exit "${status}"
}
trap cleanup EXIT

"${COMPOSE[@]}" config --quiet >>"${LOG_FILE}" 2>&1 \
    || die "compose.yaml ou .env inválido."
"${COMPOSE[@]}" exec -T web true >>"${LOG_FILE}" 2>&1 \
    || die "o serviço web precisa estar em execução."

timestamp="$(date --utc '+%Y%m%dT%H%M%SZ')"
archive_name="gestao-rural-${timestamp}.tar.gz"
final_archive="${BACKUP_DIR}/${archive_name}"
[[ ! -e "${final_archive}" ]] || die "o pacote final já existe e não será sobrescrito."
WORK_DIR="$(mktemp -d "${BACKUP_DIR}/.backup-${timestamp}-XXXXXX")"
case "${WORK_DIR}" in
    "${BACKUP_DIR}"/.backup-*) ;;
    *) die "mktemp retornou um caminho inesperado." ;;
esac

log "Criando cópia consistente do SQLite."
REMOTE_COPY="/tmp/gestao-rural-${timestamp}.sqlite3"
"${COMPOSE[@]}" exec -T web \
    python manage.py exportar_backup_sqlite --saida "${REMOTE_COPY}" \
    >>"${LOG_FILE}" 2>&1 || die "a exportação consistente do SQLite falhou."
"${COMPOSE[@]}" cp "web:${REMOTE_COPY}" "${WORK_DIR}/database.sqlite3" \
    >>"${LOG_FILE}" 2>&1 || die "não foi possível copiar o backup SQLite do container."
"${COMPOSE[@]}" exec -T web rm -f -- "${REMOTE_COPY}" >>"${LOG_FILE}" 2>&1 || true
REMOTE_COPY=""
[[ -s "${WORK_DIR}/database.sqlite3" ]] || die "a cópia SQLite ficou vazia."

log "Compactando o volume de mídia em modo somente leitura."
"${COMPOSE[@]}" run --rm --no-deps -T --entrypoint /bin/tar web \
    --create --gzip --file=- --directory=/app/media . \
    >"${WORK_DIR}/media.tar.gz" 2>>"${LOG_FILE}" \
    || die "não foi possível arquivar o volume de mídia."
gzip --test "${WORK_DIR}/media.tar.gz" || die "o arquivo de mídia está corrompido."
validate_tar_archive "${WORK_DIR}/media.tar.gz" \
    || die "o arquivo de mídia contém caminhos ou tipos inseguros."

app_version="${APP_VERSION:-}"
if [[ -z "${app_version}" ]]; then
    app_version="$(git -C "${PROJECT_DIR}" describe --always --dirty 2>/dev/null || printf 'desconhecida')"
fi
app_version="$(printf '%s' "${app_version}" | tr -d '\r\n' | cut -c1-200)"
git_commit="$(git -C "${PROJECT_DIR}" rev-parse HEAD 2>/dev/null || printf 'desconhecido')"
sqlite_version="$("${COMPOSE[@]}" exec -T web python -c \
    'import sqlite3; print(sqlite3.sqlite_version)' 2>>"${LOG_FILE}" | tr -d '\r\n')"

{
    printf 'format_version=2\n'
    printf 'database_engine=sqlite\n'
    printf 'created_at_utc=%s\n' "$(date --utc '+%Y-%m-%dT%H:%M:%SZ')"
    printf 'application_version=%s\n' "${app_version}"
    printf 'git_commit=%s\n' "${git_commit}"
    printf 'sqlite_version=%s\n' "${sqlite_version}"
    printf 'contents=database.sqlite3,media.tar.gz\n'
} >"${WORK_DIR}/metadata.txt"

(
    cd -- "${WORK_DIR}"
    sha256sum database.sqlite3 media.tar.gz metadata.txt > SHA256SUMS
    sha256sum --check --strict SHA256SUMS >>"${LOG_FILE}"
) || die "a verificação SHA-256 dos arquivos falhou."

PARTIAL_ARCHIVE="${final_archive}.partial"
(
    set -o noclobber
    tar --create --gzip --file=- --directory="${WORK_DIR}" \
        database.sqlite3 media.tar.gz metadata.txt SHA256SUMS >"${PARTIAL_ARCHIVE}"
) 2>>"${LOG_FILE}" || die "não foi possível criar o pacote final."
gzip --test "${PARTIAL_ARCHIVE}" || die "a verificação gzip do pacote final falhou."
validate_tar_archive "${PARTIAL_ARCHIVE}" \
    || die "o pacote final contém caminhos ou tipos inseguros."
mv -- "${PARTIAL_ARCHIVE}" "${final_archive}"
PARTIAL_ARCHIVE=""
chmod 600 -- "${final_archive}"

find "${BACKUP_DIR}" -maxdepth 1 -type f -name 'gestao-rural-*.tar.gz' \
    -mtime "+${RETENTION_DAYS}" ! -path "${final_archive}" -print -delete >>"${LOG_FILE}"

"${COMPOSE[@]}" exec -T web \
    python manage.py registrar_backup_sucesso --arquivo "${archive_name}" \
    >>"${LOG_FILE}" 2>&1 \
    || die "o pacote foi criado, mas o marcador operacional não pôde ser atualizado."

log "Backup SQLite concluído e verificado: ${final_archive}"
printf '%s\n' "${final_archive}"
