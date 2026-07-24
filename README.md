# Gestão Rural

Sistema web em português do Brasil para gestão de uma propriedade de gado
leiteiro. A aplicação é um monólito modular Django, orientado ao uso pelo
celular, com SQLite como fonte oficial dos dados, histórico preservado,
auditoria, relatórios e rotinas de backup.

O desenho de produção pressupõe um único servidor Linux no sítio. O acesso
externo acontece por um domínio real e um Cloudflare Tunnel gerenciado. O
Compose padrão **não publica nenhuma porta no host**: Gunicorn e Caddy só se
comunicam pelas redes Docker.

## Funcionalidades

- Autenticação Django, alteração de senha e ausência de cadastro público.
- Cadastro unificado de animais, raças, lotes, parentesco, situação e foto.
- Histórico de movimentações e pesagens, idade calculada e linha do tempo.
- Coberturas, diagnósticos, perdas gestacionais, previsão de parto e partos.
- Cadastro transacional de um ou mais bezerros e vínculo com mãe e pai.
- Lactações, secagem, ordenhas totais ou individuais e produção por vaca.
- Destino e conciliação do leite produzido, armazenado, descartado ou entregue.
- Um laticínio ativo, histórico de preços, entregas, fechamentos e recebimentos.
- Medicamentos, tratamentos e períodos de carência.
- Dashboard, alertas operacionais, auditoria e relatórios em tela, PDF e XLSX.
- Health checks de processo e banco, dados de demonstração e comandos de
  verificação para cron ou systemd timer.
- Backup consistente e verificado de SQLite e mídia, com retenção e restauração protegida.

As operações históricas e financeiras usam cancelamento lógico e justificativa
quando aplicável. Dinheiro, litros e peso são tratados com `Decimal`, nunca com
`float`.

## Stack

- Python 3.13 e Django 5.2 LTS;
- SQLite com WAL e transações `IMMEDIATE`, adequado ao único usuário previsto;
- Django Templates, HTMX, Bootstrap 5, Alpine.js pontual e Chart.js;
- Gunicorn e Caddy 2.10;
- Docker Compose e Cloudflare Tunnel;
- OpenPyXL e WeasyPrint;
- Pytest, Ruff e mypy com django-stubs.

O `cloudflared` está fixado em `2026.7.2`, publicado em 15/07/2026. Além da
tag, o Compose fixa o digest multi-arquitetura
`sha256:4f6655284ab3d252b7f28fedb19fe6c8fc82ee5b1295c20ac74d475e5398a52d`.
A versão e o digest foram conferidos em 22/07/2026 nas páginas oficiais de
[releases do cloudflared](https://github.com/cloudflare/cloudflared/releases/tag/2026.7.2)
e da [imagem `cloudflare/cloudflared:2026.7.2`](https://hub.docker.com/layers/cloudflare/cloudflared/2026.7.2/images/sha256-18626b1baac4450214535cd5bc40ef44c0635244d585ebf707749c22b6f3408f).

## Arquitetura

```text
Navegador
    │ HTTPS
    ▼
Cloudflare DNS / Access opcional
    │
    ▼
Cloudflare Tunnel (conexão iniciada de dentro para fora)
    │ rede Docker tunnel interna + egress exclusivo do cloudflared
    ▼
Caddy interno :80
    │ rede Docker frontend
    ▼
Django + Gunicorn :8000
    │
    ▼
SQLite persistente /app/data/db.sqlite3
```

`cloudflared` participa de `tunnel` e da rede exclusiva de saída `egress`;
`proxy` faz a ponte controlada entre `tunnel` e `frontend`; e `web` participa
somente de `frontend`. Assim, o conector não alcança Gunicorn diretamente.
`expose` documenta portas entre containers, mas não cria portas no host.

O banco SQLite fica no volume nomeado `sqlite_data`, montado em `/app/data`.
O Compose fixa um único worker do Gunicorn, pois o cenário previsto possui um
usuário e o SQLite permite apenas um escritor por vez. WAL, timeout de 30 segundos
e transações `IMMEDIATE` reduzem conflitos de escrita.

Fotos e documentos privados não são servidos diretamente pelo Caddy. A rota de
mídia deve passar pelas views autenticadas do Django. Apenas os arquivos
coletados em `staticfiles` são expostos como `/static/`.

## Estrutura principal

```text
apps/                   módulos de negócio Django
config/settings/        configurações por ambiente
deployment/Caddyfile    proxy interno
scripts/backup.sh       backup seguro e verificado
scripts/restore.sh      restauração destrutiva com confirmação
secrets/                arquivos secretos ignorados pelo Git
templates/              templates compartilhados
compose.yaml            produção sem portas publicadas
compose.lan.yaml        override emergencial, perfil lan
Dockerfile              imagem Python multi-stage e não root
```

## Pré-requisitos de produção

- Servidor Linux de 64 bits com horário sincronizado;
- Docker Engine atual e plugin Docker Compose v2;
- domínio adicionado à Cloudflare;
- túnel remoto criado no painel Cloudflare;
- DNS e saída para a Cloudflare liberados no firewall;
- espaço separado, preferencialmente outro disco, para backups;
- usuário administrativo do sistema operacional sem login direto como `root`.

Os scripts `backup.sh` e `restore.sh` são destinados a Linux. Ao copiar o
projeto a partir de um sistema que não preserve bits de execução, rode:

```bash
chmod 750 scripts/backup.sh scripts/restore.sh
```

## Configuração do `.env`

Crie o arquivo local e restrinja suas permissões:

```bash
cp .env.example .env
chmod 600 .env
```

Edite todos os valores `TROQUE`. Gere valores aleatórios sem reutilizar senhas:

```bash
openssl rand -base64 48
```

Variáveis essenciais:

| Variável | Uso |
|---|---|
| `DJANGO_SECRET_KEY` | assinatura criptográfica do Django; longa e exclusiva |
| `DJANGO_ALLOWED_HOSTS` | domínio e hosts internos de health check |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | origem HTTPS completa do domínio |
| `APP_DOMAIN` | hostname público, sem esquema nem caminho |
| `APP_BASE_URL` | URL pública com `https://` |
| `SQLITE_PATH` | caminho do banco; no Docker use `/app/data/db.sqlite3` |
| `SQLITE_TIMEOUT_SECONDS` | espera por liberação de escrita, padrão 30 segundos |
| `MAX_UPLOAD_BYTES` | limite global de upload em bytes |
| `GESTACAO_DIAS_PADRAO` | duração inicial da gestação, padrão 283 |
| `MARGEM_PARTO_DIAS_PADRAO` | margem anterior e posterior, padrão 7 |
| `BACKUP_MAX_AGE_HOURS` | idade máxima do último backup confirmado, padrão 36 horas |
| `DISK_MIN_FREE_PERCENT` | percentual livre mínimo no volume monitorado, padrão 10% |

Use listas separadas por vírgula, sem aspas adicionais:

```dotenv
DJANGO_ALLOWED_HOSTS=gado.seudominio.com.br,127.0.0.1,localhost
DJANGO_CSRF_TRUSTED_ORIGINS=https://gado.seudominio.com.br
```

Não inclua o token do túnel no `.env`; ele possui um arquivo secret dedicado.

## Configuração do domínio e Cloudflare Tunnel

1. Adicione o domínio à Cloudflare e conclua a troca dos nameservers no
   registrador. Aguarde a zona ficar ativa.
2. No painel Zero Trust, acesse **Networks > Tunnels**, crie um túnel do tipo
   `cloudflared` e mantenha a configuração gerenciada remotamente.
3. Na opção de adicionar um conector/replica, copie somente o token `eyJ...` do
   comando exibido. Quem possui esse token pode executar o túnel.
4. Grave o token como Docker Secret, sem espaço ou quebra de linha adicional.
   A imagem oficial executa como UID/GID `65532`; como o Compose local monta
   secrets originados de arquivo sem remapear proprietário, o arquivo `0600`
   também precisa pertencer a esse UID/GID:

   ```bash
   install -d -m 700 secrets
   token_tmp="$(mktemp)"
   chmod 600 "$token_tmp"
   read -r -s -p 'Token do túnel: ' CF_TOKEN; printf '\n'
   printf '%s' "$CF_TOKEN" > "$token_tmp"
   unset CF_TOKEN
   sudo install -o 65532 -g 65532 -m 600 \
     "$token_tmp" secrets/cloudflare_tunnel_token.txt
   rm -f "$token_tmp"
   stat -c '%u:%g %a %n' secrets/cloudflare_tunnel_token.txt
   ```

   O resultado esperado do `stat` começa com `65532:65532 600`. Não troque
   por `0644`: o token deve continuar legível apenas pelo processo do conector.

5. No túnel, crie um **Public Hostname** para
   `gado.seudominio.com.br` (ou o valor real de `APP_DOMAIN`).
6. Configure o serviço de origem exatamente como `http://proxy:80`. Não use
   `localhost`: cada serviço possui seu próprio namespace de rede no Docker.
7. Confirme `.env`, secret e Compose antes de iniciar:

   ```bash
   docker compose config --quiet
   docker compose pull
   docker compose build --pull
   docker compose up -d
   ```

8. Confira o conector no painel e os logs locais:

   ```bash
   docker compose ps
   docker compose logs --tail=100 cloudflared proxy web
   ```

9. Opcional e recomendado: em Cloudflare Access, crie uma aplicação
   **Self-hosted** para o mesmo hostname e uma política `Allow` somente para o
   e-mail ou identidade autorizada. O Access é uma camada adicional; o login do
   Django permanece obrigatório.
10. Acesse `https://gado.seudominio.com.br/`, autentique-se e valide
    `/health/live/` e `/health/ready/`. Os endpoints retornam apenas
    `{"status":"ok"}` e não expõem versões ou credenciais.
11. Se o token for revelado, revogue ou rotacione-o no painel, repita o passo 4
    para instalar o novo secret com proprietário `65532:65532` e modo `0600`, e
    recrie somente o conector:

    ```bash
    docker compose up -d --force-recreate cloudflared
    ```

12. Configure o acesso LAN opcional somente depois de validar a implantação
    principal, conforme a seção “Acesso local de emergência”.

O Compose, as redes e o serviço de origem podem ser validados sem credenciais
reais. Entretanto, o estado `Healthy` do conector, o public hostname, o HTTPS do
domínio e uma eventual política Access só ficam comprovados depois de instalar um
token real e configurar o domínio no painel. Um token fictício faz o container
encerrar com erro e não substitui essa validação externa.

O container `cloudflared` participa de duas redes: `tunnel`, interna e compartilhada
somente com o Caddy, e `egress`, usada para iniciar conexões externas com a
Cloudflare. Banco, aplicação e proxy não participam da rede de saída.

O Compose usa `--token-file`, suportado para túneis gerenciados a partir do
cloudflared 2025.4.0, conforme a
[documentação oficial dos parâmetros de execução](https://developers.cloudflare.com/tunnel/advanced/run-parameters/#token-file).

## Primeira inicialização

As migrations e o `collectstatic` rodam antes do Gunicorn a cada criação do
container `web`. A primeira subida pode demorar enquanto imagens são baixadas e
o banco é inicializado:

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f --tail=100 web
```

Crie o único usuário administrador inicial por um terminal protegido:

```bash
docker compose exec web python manage.py createsuperuser
```

Não publique nem compartilhe uma senha padrão. Depois do primeiro login, teste a
alteração de senha e mantenha o Django Admin para manutenção técnica; a operação
diária é feita na interface própria.

Se o administrador esquecer a senha, recupere o acesso pelo console protegido do
servidor, sem criar outro usuário nem desativar autenticação:

```bash
docker compose exec web python manage.py changepassword NOME_DO_USUARIO
```

Comandos manuais equivalentes:

```bash
docker compose exec web python manage.py migrate --noinput
docker compose exec web python manage.py collectstatic --noinput
docker compose exec web python manage.py check
docker compose exec web python manage.py check --deploy
docker compose exec web python manage.py showmigrations
docker compose exec web python manage.py makemigrations --check --dry-run
```

## Dados de demonstração

Use dados fictícios somente em desenvolvimento ou homologação:

```bash
python manage.py seed_demo
```

O comando é idempotente para evitar duplicação acidental. Não execute em uma
base real sem confirmar previamente o ambiente e possuir backup.

## Desenvolvimento local

Crie o ambiente virtual. O desenvolvimento usa `db.sqlite3` na raiz do projeto:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
cp .env.example .env
```

Defina no `.env` de desenvolvimento:

```dotenv
DJANGO_SETTINGS_MODULE=config.settings.development
DJANGO_DEBUG=true
DJANGO_SECURE_SSL_REDIRECT=false
SQLITE_PATH=./db.sqlite3
```

O Django não interpreta o arquivo `.env` diretamente. Exporte suas variáveis na
sessão atual antes de executar comandos locais:

```bash
set -a
source .env
set +a
```

Depois, na mesma sessão:

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 127.0.0.1:8000
```

Não execute `seed_demo` se quiser começar com a base vazia. Depois das migrations,
somente as tabelas e metadados internos do Django existem; crie apenas o usuário
administrador necessário para entrar.

No Windows, use o PowerShell na raiz do projeto:

```powershell
py -3.13 -m venv .venv
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
$env:DJANGO_SETTINGS_MODULE = "config.settings.development"
$env:DJANGO_DEBUG = "true"
$env:DJANGO_SECURE_SSL_REDIRECT = "false"
$env:SQLITE_PATH = Join-Path (Get-Location) "db.sqlite3"
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 127.0.0.1:8000
```

Abra `http://127.0.0.1:8000/`. O comando `createsuperuser` é o único passo acima
que adiciona um registro à base limpa e serve para criar a conta usada no login.

## Testes e qualidade

Com o extra `dev` instalado:

```bash
pytest
pytest --cov=apps --cov=config --cov-report=term-missing
ruff check .
ruff format --check .
mypy apps config
python manage.py makemigrations --check --dry-run
python manage.py check --deploy --settings=config.settings.production
```

Para `check --deploy`, exporte antes uma chave e domínio fictícios seguros, sem
apontar para produção. A configuração de testes usa SQLite isolado em memória.

## Comandos administrativos

Os comandos foram preparados para execução manual, cron ou systemd timer, sem
Celery:

```bash
python manage.py verificar_alertas
python manage.py verificar_partos
python manage.py verificar_carencias
python manage.py verificar_queda_producao
python manage.py gerar_relatorio_mensal
python manage.py verificar_integridade
```

No servidor Docker, prefixe com `docker compose exec -T web`. Não permita
execuções simultâneas do mesmo comando; use `flock` no cron quando necessário e
registre a saída no journal ou em diretório protegido.

`verificar_alertas` também confere a idade do último backup e o espaço livre no
volume configurado. Por padrão, o marcador fica em
`/app/media/.sistema/ultimo_backup.json` no Docker e o próprio volume de mídia é
medido. Ajuste `BACKUP_STATUS_FILE` e `DISK_MONITOR_PATH` somente para caminhos
acessíveis pelo container `web`; os monitores podem ser desativados
individualmente com `BACKUP_MONITOR_ENABLED=false` ou
`DISK_MONITOR_ENABLED=false`.

Exemplo de verificação a cada 15 minutos:

```cron
*/15 * * * * cd /srv/gestao-rural && /usr/bin/flock -n /run/lock/gestao-rural-alertas.lock /usr/bin/docker compose exec -T web python manage.py verificar_alertas
```

## Backup

O backup contém:

- cópia consistente do SQLite criada pela API nativa de backup;
- conteúdo completo do volume de mídia em `tar.gz`;
- horário UTC, versão da aplicação, commit e versão do SQLite;
- manifesto SHA-256 verificado antes da publicação;
- pacote final com permissão `0600` e nome UTC único.

O script usa diretório temporário, não substitui arquivo existente e só aplica
retenção a arquivos `gestao-rural-*.tar.gz`. A aplicação precisa estar em execução
e a imagem `web` precisa ter sido construída. A cópia passa por
`PRAGMA integrity_check`. Depois de publicar e verificar o
pacote, ele atualiza atomicamente o marcador usado pelo alerta operacional; uma
falha anterior a essa etapa deixa o marcador antigo, permitindo detectar o
atraso na próxima execução de `verificar_alertas`.

```bash
BACKUP_DIR=/mnt/backup-gestao-rural \
BACKUP_RETENTION_DAYS=30 \
./scripts/backup.sh
```

O caminho completo do pacote é a última linha da saída. Confira periodicamente:

```bash
gzip -t /mnt/backup-gestao-rural/gestao-rural-AAAAMMDDTHHMMSSZ.tar.gz
tar -tzf /mnt/backup-gestao-rural/gestao-rural-AAAAMMDDTHHMMSSZ.tar.gz
```

Exemplo de cron diário às 02:15, com caminhos absolutos:

```cron
15 2 * * * BACKUP_DIR=/mnt/backup-gestao-rural BACKUP_RETENTION_DAYS=30 /srv/gestao-rural/scripts/backup.sh >/dev/null 2>&1
```

O script já mantém `backup.log` no diretório configurado, ou no caminho definido
por `BACKUP_LOG_FILE`. Restrinja o cron ao usuário operador do Docker.

Um backup no mesmo disco do banco **não é backup suficiente**. Copie os pacotes
para outro dispositivo, mantenha ao menos uma cópia fora do sítio e use
criptografia no dispositivo ou no processo de cópia. Não coloque `.env` ou o
token do túnel dentro do pacote de dados; guarde uma cópia criptografada desses
segredos por procedimento separado.

## Restauração

A restauração substitui integralmente banco e mídia. Antes de alterar dados, o
script:

1. valida gzip, caminhos internos, arquivos obrigatórios e SHA-256;
2. executa `PRAGMA integrity_check` na cópia SQLite;
3. mostra os metadados;
4. exige a palavra exata `RESTAURAR`;
5. cria e verifica um backup preventivo do estado atual;
6. para túnel, proxy e web antes da substituição.

Execute em janela de manutenção:

```bash
./scripts/restore.sh /mnt/backup-gestao-rural/gestao-rural-AAAAMMDDTHHMMSSZ.tar.gz
```

Para automação deliberada e não interativa:

```bash
RESTORE_CONFIRM=RESTAURAR \
./scripts/restore.sh /caminho/backup.tar.gz
```

Se uma etapa falhar depois da parada, os serviços web permanecem parados para
evitar uso de dados parciais. Consulte `backups/restore.log` e recupere usando o
backup preventivo informado pelo script.

Teste a restauração regularmente em uma cópia isolada do projeto, com volumes e
`COMPOSE_PROJECT_NAME` próprios. Após restaurar, verifique login, contagens,
fotos, relatórios, `/health/ready/` e os fluxos principais. Um arquivo de backup
que nunca foi restaurado ainda não foi operacionalmente comprovado.

## Acesso local de emergência

O modo normal deve permanecer:

```dotenv
ENABLE_LAN_FALLBACK=false
```

Quando a internet do sítio falhar, o túnel ficará indisponível. Para uma
contingência curta:

1. descubra o IP privado fixo atribuído ao servidor, por exemplo
   `192.168.1.10`; não use `0.0.0.0`, IP público ou hostname;
2. restrinja no firewall a origem à sub-rede privada necessária;
3. ajuste temporariamente `.env`:

   ```dotenv
   ENABLE_LAN_FALLBACK=true
   LAN_BIND_ADDRESS=192.168.1.10
   LAN_PORT=8080
   DJANGO_ALLOWED_HOSTS=gado.seudominio.com.br,127.0.0.1,localhost,192.168.1.10
   DJANGO_CSRF_TRUSTED_ORIGINS=https://gado.seudominio.com.br,http://192.168.1.10:8080
   ```

4. inicie o proxy adicional com o override e o perfil explícito:

   ```bash
   docker compose -f compose.yaml -f compose.lan.yaml \
     --profile lan up -d web lan-proxy
   ```

5. acesse `http://192.168.1.10:8080`, mantendo obrigatório o login Django.

Exemplo UFW — adapte a sub-rede antes de executar:

```bash
sudo ufw allow from 192.168.1.0/24 to 192.168.1.10 port 8080 proto tcp
```

Uma porta publicada pelo Docker pode ser processada por regras de `iptables`
antes das regras comuns do UFW. Não considere o comando acima suficiente sem
validar a integração do host: restrinja também pela cadeia `DOCKER-USER` ou pelas
regras `nftables` equivalentes da distribuição e teste a porta a partir de um host
permitido e de outro que deva ser recusado. Preserve uma sessão SSH ao revisar o
firewall para evitar bloqueio administrativo acidental.

`ENABLE_LAN_FALLBACK=true` desativa temporariamente o redirecionamento HTTPS e
o atributo `Secure` dos cookies para viabilizar o HTTP privado. Isso reduz a
proteção do transporte: use apenas em rede confiável, pelo menor tempo possível,
sem Wi-Fi de convidados.

Ao normalizar a internet:

```bash
docker compose -f compose.yaml -f compose.lan.yaml --profile lan stop lan-proxy
```

Remova a regra de firewall, volte `ENABLE_LAN_FALLBACK=false` e recrie `web`:

```bash
docker compose up -d --force-recreate web proxy cloudflared
```

Remova também o IP LAN de `DJANGO_ALLOWED_HOSTS` e a origem HTTP de
`DJANGO_CSRF_TRUSTED_ORIGINS`, mantendo apenas os valores normais do domínio.

O `compose.lan.yaml` exige `LAN_BIND_ADDRESS`; a ausência da variável interrompe
a validação. O Compose base jamais publica a porta LAN.

## Firewall e exposição de rede

- Não abra `8000` (Gunicorn).
- Não abra `80` ou `443` para os containers do sistema.
- Restrinja SSH por IP, chave e política da propriedade.
- Permita ao `cloudflared` as conexões de saída exigidas pela Cloudflare.
- Quando o modo LAN estiver ativo, aceite apenas a sub-rede privada definida.
- Revise periodicamente `docker compose ps` e `ss -lntp` no host.

No modo padrão, a coluna `PORTS` de `docker compose ps` deve mostrar somente
portas internas, sem mapeamentos como `0.0.0.0:...->...` ou `[::]:...->...`.
O roteador não precisa e não deve possuir encaminhamento HTTP/HTTPS para o
servidor.

## Atualização

1. Leia notas de versão e mudanças de migrations.
2. Gere um backup e copie-o para outro dispositivo.
3. Registre o commit/imagem atualmente em uso.
4. Atualize o código e revise alterações em `.env.example`.
5. Reconstrua e suba:

   ```bash
   docker compose build --pull
   docker compose up -d
   ```

6. Verifique logs, health checks, migrations, login e fluxos críticos.
7. Só remova imagens antigas depois do período de observação.

O `cloudflared` não se autoatualiza. Para atualizá-lo, confirme uma release
oficial, altere tag **e digest** no Compose, revise notas, faça `docker compose
pull cloudflared` e recrie o serviço. Não troque por `latest` em produção.

As demais imagens e dependências Python usam atualmente tags ou intervalos de
versão, permitindo atualizações de correção durante um novo build. Para uma
release reproduzível, registre os digests efetivamente homologados das imagens e
gere um arquivo de constraints/lock a partir do ambiente testado, revise-o e
versione-o antes da implantação. Este repositório ainda não fornece esse lock;
portanto não se deve afirmar que dois builds em datas distintas são idênticos.

Para rollback de código, volte ao commit anterior e reconstrua. Se a atualização
alterou o esquema de modo incompatível, restaure o backup correspondente em vez
de tentar reverter migrations manualmente sem um plano testado.

## Regras de negócio essenciais

- A identificação do animal é única; mãe é fêmea, pai é macho e ciclos de
  parentesco são bloqueados.
- A idade é calculada; o tipo de animal (vaca, novilha, bezerro ou boi) é informado no cadastro.
- Coberturas e previsões originais permanecem no histórico; cancelamentos e
  correções relevantes exigem justificativa.
- Parto, bezerros, parentesco, cobertura e histórico são gravados em transação.
- Uma vaca não possui duas lactações ativas.
- Produções, destinos, entregas e fechamentos são entidades distintas e
  conciliadas, sem assumir que produzido significa vendido.
- O preço da entrega é preservado no registro histórico.
- Só pode existir um laticínio ativo.
- Medicamentos calculam carência e destacam leite que não pode ser vendido.
- Registros históricos não são apagados fisicamente pela operação normal.

## Limitações deliberadas da primeira versão

- uma propriedade, um usuário principal e um laticínio ativo;
- um banco e uma aplicação monolítica;
- sem multitenancy, API pública, frontend separado ou JWT para a interface;
- sem Redis, Celery, filas ou microsserviços;
- sem notificações por WhatsApp, SMS ou e-mail;
- Cloudflare é a única dependência externa necessária ao acesso remoto;
- o acesso LAN emergencial usa HTTP privado e exige mitigação operacional.

## Solução de problemas

### `compose config` reclama de variável ausente

Confirme que `.env` existe na raiz e que todos os valores `TROQUE` foram
substituídos. Não execute com senha vazia.

### `cloudflared` reinicia ou aparece `unhealthy` no painel

Confira permissão e conteúdo do secret, rotação do token e serviço de origem:

```bash
stat secrets/cloudflare_tunnel_token.txt
docker compose logs --tail=200 cloudflared
docker compose exec proxy wget -qO- --header="Host: $APP_DOMAIN" http://127.0.0.1/health/ready/
```

O public hostname deve apontar para `http://proxy:80`.

### Redirecionamento infinito

Mantenha `APP_BASE_URL` e origem CSRF com `https://`, confirme que o Cloudflare
acessa `http://proxy:80` e não remova a preservação de `X-Forwarded-Proto` do
Caddyfile. No modo normal, `ENABLE_LAN_FALLBACK` deve ser `false`.

### Erro 400 de host ou falha CSRF

Confira o hostname exato em `DJANGO_ALLOWED_HOSTS` e a URL completa, com esquema,
em `DJANGO_CSRF_TRUSTED_ORIGINS`. Recrie `web` depois de alterar `.env`.

### Banco não fica pronto

```bash
docker compose logs --tail=200 web
docker compose exec web python manage.py showmigrations
docker compose exec web python -c \
  'import sqlite3; c=sqlite3.connect("/app/data/db.sqlite3"); print(c.execute("PRAGMA integrity_check").fetchone()); c.close()'
```

Confirme que `sqlite_data` está montado em `/app/data` e nunca apague os arquivos
`db.sqlite3-wal` ou `db.sqlite3-shm` enquanto a aplicação estiver em execução.

### Arquivos estáticos ausentes

```bash
docker compose exec web python manage.py collectstatic --noinput
docker compose restart proxy
```

Não coloque mídia privada em `static/`.

### Pouco espaço em disco

Verifique volumes, logs e diretório de backup. Não apague volumes Docker para
liberar espaço sem identificar exatamente o conteúdo e confirmar um backup
restaurável.

## Recuperação de falhas

- Após reinício do servidor, `restart: unless-stopped` recupera os serviços;
  confirme `docker compose ps` e `/health/ready/`.
- Se somente o túnel falhar, a aplicação e o banco continuam locais; corrija ou
  rotacione o token sem recriar volumes.
- Se a aplicação falhar após atualização, preserve volumes, volte a imagem ou o
  commit e inspecione logs antes de restaurar dados.
- Se houver corrupção ou perda lógica, isole a escrita, guarde uma cópia do
  estado atual e restaure o último backup testado.
- Se o disco do servidor falhar, reinstale em outro host, restaure `.env` e
  secrets a partir do cofre separado, construa a aplicação e execute `restore.sh`.
- Nunca use `docker compose down -v` em produção: `-v` remove os volumes de
  banco, estáticos e mídia.

## Checklist antes de liberar produção

- [ ] `.env` com `chmod 600` e secret `65532:65532`/`0600`, ambos fora do Git;
- [ ] migrations aplicadas e nenhuma migration pendente;
- [ ] `pytest`, Ruff, mypy e `check --deploy` aprovados;
- [ ] containers saudáveis e túnel `Healthy` no painel;
- [ ] login, alteração de senha e proteção das rotas validados;
- [ ] health checks sem informação sensível;
- [ ] PDF, XLSX, upload JPG/PNG/PDF e visualização privada testados;
- [ ] cálculos financeiros e de produção revisados com `Decimal`;
- [ ] fuso `America/Campo_Grande` conferido no servidor e aplicação;
- [ ] visualização em celular testada;
- [ ] nenhum mapeamento público para 8000, 80 ou 443;
- [ ] backup concluído, copiado para outro dispositivo e restaurado em ambiente
  isolado;
- [ ] token não aparece no Git, `.env`, logs ou histórico do shell;
- [ ] Cloudflare Access configurado, quando adotado;
- [ ] modo LAN desativado fora de uma emergência.
