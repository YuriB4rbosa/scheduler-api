# Scheduler API

API REST de agendamento para pequenos negócios (salões, clínicas, oficinas). Cada negócio cadastra
seus clientes e serviços e gerencia a agenda, com a garantia de que **dois atendimentos ativos nunca
se sobrepõem no mesmo horário**.

[![CI](https://github.com/YuriB4rbosa/scheduler-api/actions/workflows/ci.yml/badge.svg)](https://github.com/YuriB4rbosa/scheduler-api/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.12%2B-blue)
![Flask](https://img.shields.io/badge/flask-3.1-lightgrey)
![PostgreSQL](https://img.shields.io/badge/postgresql-16-336791)
![Cobertura](https://img.shields.io/badge/cobertura-100%25-brightgreen)

O foco do projeto é a **qualidade de engenharia**: código em camadas, regras de negócio testadas,
documentação gerada a partir do código e decisões registradas (com seus trade-offs).

## Demonstração ao vivo

**Swagger (teste direto no navegador):** https://scheduler-api-3mdo.onrender.com/docs

Crie uma conta em `POST /api/v1/auth/register`, faça login em `POST /api/v1/auth/login` e use o botão
**Authorize** com o `access_token`. Não há dados de demonstração publicados (o seed é bloqueado em
produção de propósito): cada visitante cria a própria conta.

> Hospedado no plano gratuito do Render: a **primeira requisição após um período parado pode levar cerca
> de 1 minuto** (o serviço hiberna), e o banco gratuito **expira 30 dias após a criação** (por volta de
> 24/12/2026). Por isso é uma demonstração, não um ambiente para dados reais.

## Destaques

- **Conflito de horário à prova de corrida:** validação no service (com mensagem clara) + *exclusion
  constraint* no PostgreSQL como garantia final. [Como funciona](docs/technical-decisions.md#1-sobreposição-de-horários-service--constraint-do-banco).
- **Isolamento entre usuários:** cada um só enxerga os próprios dados; o recurso de outro usuário
  responde `404`, como se não existisse.
- **Autenticação JWT** (access + refresh), senhas com **argon2**, login que não revela se o e-mail existe e
  *rate limit* em login/cadastro.
- **Erros padronizados** em toda a API: `{"error": {"code", "message", "details"}}`.
- **Swagger/OpenAPI** em `/docs`, gerado dos mesmos schemas que validam a entrada, com exemplos.
- **Testes com PostgreSQL real**, inclusive um teste que garante que as migrations geram o mesmo schema
  dos models.

## Tecnologias

| Área | Escolha |
|---|---|
| Linguagem / framework | Python 3.12+, Flask 3 |
| Banco / ORM | PostgreSQL 16, SQLAlchemy 2, Flask-Migrate (Alembic) |
| Validação e docs | Marshmallow + flask-smorest (OpenAPI 3) |
| Autenticação | Flask-JWT-Extended, argon2-cffi |
| Segurança | Flask-Limiter, segredos só em variáveis de ambiente |
| Qualidade | pytest, pytest-cov, ruff (lint + formatação) |

## Como rodar

### Com Docker (mais rápido)

Pré-requisito: **Docker**. Não precisa de Python, `.env` nem de configuração.

```bash
git clone https://github.com/YuriB4rbosa/scheduler-api.git && cd scheduler-api
docker compose up --build           # sobe a API (porta 8000) e o PostgreSQL; aplica as migrations
docker compose exec api flask seed  # em outro terminal: dados de demonstração (opcional)
```

A API fica em `http://localhost:8000` e o Swagger em **http://localhost:8000/docs**. Para parar:
`docker compose down` (acrescente `-v` para apagar também os dados do banco).

> As chaves usadas aqui são valores de **demonstração local** definidos no `docker-compose.yml`
> (`APP_ENV=development`). Com `APP_ENV=production` a API recusa chaves de exemplo ou curtas e não sobe.
> Para usar as suas, defina `SECRET_KEY` e `JWT_SECRET_KEY` no shell ou em um `.env`.

### Localmente (para desenvolver)

Pré-requisitos: **Python 3.12+** e **Docker** (usado apenas para o PostgreSQL).

```bash
git clone https://github.com/YuriB4rbosa/scheduler-api.git && cd scheduler-api

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

cp .env.example .env               # depois, gere chaves próprias (veja "Variáveis de ambiente")
docker compose up -d db            # só o PostgreSQL, em localhost:5433 (+ banco scheduler_test)

flask db upgrade                   # cria as tabelas
flask seed                         # dados de demonstração (opcional)
flask run --port 8000          # use --debug para recarregar o código ao editar
```

Pronto: a API está em `http://localhost:8000` e o Swagger em **http://localhost:8000/docs**.

> O `.env` é lido automaticamente pelo `flask`. A porta do banco é **5433** (e não 5432) para não
> colidir com um PostgreSQL já instalado na máquina.

### Dados de demonstração (`flask seed`)

Cria o usuário `demo@scheduler.dev` com 8 clientes, 8 serviços e uma agenda de ~36 agendamentos
(passado concluído/cancelado e futuro agendado). Em `development` a senha é `demo12345`; em qualquer
outro ambiente é obrigatório definir `SEED_DEMO_PASSWORD`. O comando **se recusa a rodar com
`APP_ENV=production`**. Para recriar os dados: `flask seed --reset`.

## Variáveis de ambiente

Veja o [`.env.example`](.env.example). Segredos nunca ficam no código, e o `.env` está no `.gitignore`.

| Variável | Obrigatória | Descrição |
|---|---|---|
| `SECRET_KEY` | sim | Chave secreta do Flask. |
| `JWT_SECRET_KEY` | sim | Chave de assinatura dos tokens JWT. |
| `DATABASE_URL` | sim | Conexão do banco (`postgresql+psycopg://usuario:senha@host:porta/banco`). Prefixos `postgres://` e `postgresql://` também são aceitos. |
| `TEST_DATABASE_URL` | para testes | Banco **separado** usado pelo pytest. |
| `APP_ENV` | não | `development` (padrão), `testing` ou `production`. |
| `JWT_ACCESS_TOKEN_MINUTES` | não | Validade do access token (padrão 15). |
| `JWT_REFRESH_TOKEN_DAYS` | não | Validade do refresh token (padrão 7). |
| `AUTH_RATE_LIMIT` | não | Limite em login/cadastro por IP (padrão `10 per minute`). |
| `RATELIMIT_STORAGE_URI` | não | Armazenamento do limitador (padrão `memory://`; use Redis com vários workers). |
| `SEED_DEMO_PASSWORD` | para o seed fora de dev | Senha do usuário de demonstração. |
| `TRUSTED_PROXY_COUNT` | não | Proxies confiáveis na frente da API (padrão: `0`; em `production`, `1`). Faz o rate limit enxergar o IP real. |

Para gerar uma chave: `python -c "import secrets; print(secrets.token_hex(32))"`.

Em `APP_ENV=production` a aplicação **se recusa a iniciar** se `SECRET_KEY`/`JWT_SECRET_KEY` tiverem menos de
32 caracteres, forem iguais entre si ou parecerem valores de exemplo (`change-me...`).

## Endpoints

Todas as rotas (exceto `health`, `register` e `login`) exigem `Authorization: Bearer <access_token>`.
A documentação interativa, com exemplos de requisição e resposta, está em `/docs` (JSON em `/openapi.json`).

| Recurso | Rotas |
|---|---|
| Saúde | `GET /health` |
| Autenticação | `POST /api/v1/auth/register` · `POST /api/v1/auth/login` · `POST /api/v1/auth/refresh` · `GET /api/v1/auth/me` |
| Clientes | `GET, POST /api/v1/customers` · `GET, PATCH, DELETE /api/v1/customers/{id}` |
| Serviços | `GET, POST /api/v1/services` · `GET, PATCH, DELETE /api/v1/services/{id}` |
| Agendamentos | `GET, POST /api/v1/appointments` · `GET, PATCH, DELETE /api/v1/appointments/{id}` · `POST /api/v1/appointments/{id}/cancel` · `POST /api/v1/appointments/{id}/complete` |

**Listagens** aceitam `page`, `per_page` (máx. 100), `sort` e `order` (`asc`/`desc`), e respondem com
`{"items": [...], "page", "per_page", "total", "pages"}`. Filtros por recurso:

- Clientes: `q` (nome, e-mail ou telefone)
- Serviços: `q`, `active`, `min_price`, `max_price`
- Agendamentos: `status`, `customer_id`, `service_id`, `date_from` (inclusivo), `date_to` (exclusivo)

Parâmetros desconhecidos (ex.: `?satus=canceled`) retornam `422` em vez de serem ignorados.

### Códigos HTTP

| Código | Quando |
|---|---|
| `200` / `201` / `204` | Sucesso / criado / removido sem corpo |
| `400` | Requisição malformada (ex.: corpo que não é JSON válido) |
| `401` | Token ausente, inválido ou expirado; credenciais incorretas |
| `403` | Reservado para falta de permissão (hoje, dado de outro usuário retorna `404`) |
| `404` | Recurso inexistente **ou de outro usuário** |
| `409` | Conflito de estado: horário ocupado, e-mail duplicado, transição de status inválida, item com agendamentos |
| `422` | Dados inválidos ou regra violada: campos, data sem fuso, horário no passado, serviço inativo |
| `429` | Limite de tentativas excedido |

## Exemplos com curl

Os exemplos usam `grep`/`cut` para extrair valores (sem depender do `jq`). No Windows/Git Bash use
nomes sem acento nos exemplos de `curl`, ou prefira o Swagger/Postman.

```bash
API=http://localhost:8000
JSON='Content-Type: application/json'

# 1. Criar a conta e fazer login
curl -s -X POST $API/api/v1/auth/register -H "$JSON" \
  -d '{"name":"Ana Souza","email":"ana@salao.com","password":"senha-segura-123"}'

TOKEN=$(curl -s -X POST $API/api/v1/auth/login -H "$JSON" \
  -d '{"email":"ana@salao.com","password":"senha-segura-123"}' \
  | grep -o '"access_token": *"[^"]*"' | cut -d'"' -f4)
AUTH="Authorization: Bearer $TOKEN"
```

```bash
# 2. Cadastrar um cliente e um serviço (guardando os ids retornados)
CUSTOMER_ID=$(curl -s -X POST $API/api/v1/customers -H "$JSON" -H "$AUTH" \
  -d '{"name":"Maria Oliveira","phone":"+55 11 98888-7777","email":"maria@email.com"}' \
  | grep -o '"id": *[0-9]*' | head -1 | grep -o '[0-9]*$')

SERVICE_ID=$(curl -s -X POST $API/api/v1/services -H "$JSON" -H "$AUTH" \
  -d '{"name":"Corte de cabelo","duration_minutes":45,"price":"60.00"}' \
  | grep -o '"id": *[0-9]*' | head -1 | grep -o '[0-9]*$')
```

```bash
# 3. Agendar (o fuso é obrigatório; o término é calculado pela duração do serviço)
curl -s -X POST $API/api/v1/appointments -H "$JSON" -H "$AUTH" \
  -d "{\"customer_id\":$CUSTOMER_ID,\"service_id\":$SERVICE_ID,\"start_at\":\"2030-01-10T09:00:00-03:00\"}"
# 201 → "start_at":"2030-01-10T12:00:00+00:00","end_at":"2030-01-10T12:45:00+00:00","status":"scheduled"

# 4. Tentar um horário sobreposto → 409
curl -s -X POST $API/api/v1/appointments -H "$JSON" -H "$AUTH" \
  -d "{\"customer_id\":$CUSTOMER_ID,\"service_id\":$SERVICE_ID,\"start_at\":\"2030-01-10T09:15:00-03:00\"}"
# 409 → {"error":{"code":"APPOINTMENT_CONFLICT", ..., "details":{"conflicting_appointment":{"id":...}}}}

# 5. Data sem fuso horário → 422
curl -s -X POST $API/api/v1/appointments -H "$JSON" -H "$AUTH" \
  -d "{\"customer_id\":$CUSTOMER_ID,\"service_id\":$SERVICE_ID,\"start_at\":\"2030-01-10T11:00:00\"}"
# 422 → {"error":{"code":"VALIDATION_ERROR","details":{"json":{"start_at":["Not a valid aware datetime."]}}}}
```

```bash
# 6. Listar com filtros, ordenação e paginação
curl -s "$API/api/v1/appointments?status=scheduled&sort=start_at&order=desc&per_page=5" -H "$AUTH"
curl -s "$API/api/v1/appointments?date_from=2030-01-01T00:00:00Z&date_to=2030-02-01T00:00:00Z" -H "$AUTH"
curl -s "$API/api/v1/customers?q=maria&sort=name" -H "$AUTH"

# 7. Cancelar (libera o horário). Troque 42 pelo "id" do agendamento criado no passo 3.
curl -s -X POST $API/api/v1/appointments/42/cancel -H "$AUTH"
curl -s -X POST $API/api/v1/appointments/42/cancel -H "$AUTH"   # de novo → 409 INVALID_STATUS_TRANSITION
```

Ao usar o usuário de demonstração (`flask seed`), os ids de 1 a 8 já pertencem a ele. Por isso
**capture os ids das respostas**, como acima. Tentar usar o id de outro usuário retorna `404`.

Também há uma coleção pronta para [Postman/Insomnia](docs/postman_collection.json): o login guarda o
token e as criações guardam os ids usados nas chamadas seguintes.

## Testes

Os testes usam **PostgreSQL real** em um banco separado (`TEST_DATABASE_URL`), então o container do
banco precisa estar de pé:

```bash
docker compose up -d db
pytest                  # roda tudo, com cobertura (mínimo 80%) e relatório em coverage.xml
pytest tests/test_appointments_api.py -k conflict    # um subconjunto
```

Qualidade de código:

```bash
ruff check .            # lint (inclui regras de segurança do bandit)
ruff format --check .   # formatação
```

### Cobertura

| Métrica | Resultado | Mínimo exigido |
|---|---|---|
| Linhas e ramos | **100%** | 80% (o `pytest` falha abaixo disso) |

A suíte tem mais de 200 testes. Cobre, além do fluxo normal: sem token, token malformado, assinado por
outra chave e expirado; refresh usado no lugar de access; acesso a dado de outro usuário; conflito de
horário (bordas, corrida entre requisições simultâneas e fallback do banco); transições de status;
e a equivalência entre migrations e models.

## Integração contínua

O workflow [`.github/workflows/ci.yml`](.github/workflows/ci.yml) roda a cada push e pull request:

| Job | O que faz |
|---|---|
| **Lint** | `ruff check` e `ruff format --check` (Python 3.12) |
| **Testes** | `pytest` contra um PostgreSQL 16 (service container); falha se a cobertura ficar abaixo de 80%; publica `coverage.xml` e um resumo da cobertura |
| **Docker** | Constrói a imagem, sobe a stack com `docker compose up --wait`, faz um smoke test pela API (cadastro, login, `/auth/me`, `/docs`), roda o seed e confirma que a API **recusa subir em produção com chaves de exemplo** |

## Deploy no Render

O repositório já traz o [`render.yaml`](render.yaml) (Blueprint), que cria o banco PostgreSQL e o
serviço web a partir do `Dockerfile`. Não é necessário configurar nada à mão.

1. Envie o código para um repositório no GitHub.
2. No [Render](https://render.com): **New > Blueprint**, escolha o repositório e confirme (**Apply**).
3. Aguarde o primeiro deploy. O container aplica as migrations ao iniciar (`flask db upgrade`) e só
   fica saudável quando o `GET /health` responde.
4. Acesse `https://<nome-do-servico>.onrender.com/docs` e crie sua conta em `POST /api/v1/auth/register`.

O que o Blueprint configura:

| Variável | Valor |
|---|---|
| `APP_ENV` | `production` |
| `SECRET_KEY`, `JWT_SECRET_KEY` | gerados pelo Render (aleatórios, 256 bits, **distintos**); nunca ficam no repositório |
| `DATABASE_URL` | string de conexão do banco criado pelo Blueprint |
| `TRUSTED_PROXY_COUNT` | `1` (o Render põe um proxy na frente; sem isso o rate limit veria o IP do proxy) |
| `RUN_MIGRATIONS` / `WEB_CONCURRENCY` | `1` / `2` |

Pontos de atenção do **plano gratuito** (confira os limites atuais na
[documentação do Render](https://render.com/docs/free)):

- O serviço **hiberna após 15 min sem tráfego**; a primeira requisição depois disso demora.
- O PostgreSQL gratuito **expira 30 dias após a criação** (há uma carência para fazer upgrade antes de
  os dados serem apagados) e só pode existir um por conta. Serve para demonstração, não para dados reais.
- As migrations rodam no start do container porque o `preDeployCommand` do Render é exclusivo de planos pagos.
- O `flask seed` é **bloqueado em produção** de propósito: não existe usuário de demonstração publicado.
- Trocar `JWT_SECRET_KEY` invalida todos os tokens já emitidos.

Campos do Blueprint: [referência oficial](https://render.com/docs/blueprint-spec). O arquivo foi
validado contra o schema JSON publicado pelo Render.

<details>
<summary>Railway (alternativa, não validada nesta entrega)</summary>

O Railway também constrói a partir do `Dockerfile`. Crie um projeto a partir do repositório, adicione um
banco PostgreSQL e defina no serviço: `APP_ENV=production`, `SECRET_KEY` e `JWT_SECRET_KEY` (valores
aleatórios e distintos), `TRUSTED_PROXY_COUNT=1` e `DATABASE_URL=${{Postgres.DATABASE_URL}}`
(referência à variável do banco). O `PORT` é injetado pela plataforma e o healthcheck é `/health`.

</details>

## Estrutura do projeto

```
app/
  models/      tabelas e constraints            routes/    endpoints (sem regra de negócio)
  schemas/     validação e serialização         services/  regras de negócio
  config.py · extensions.py · errors.py · error_handlers.py · cli.py
migrations/    Alembic          tests/    unitários e de integração          docs/    documentação
Dockerfile · docker-compose.yml · docker/entrypoint.sh · render.yaml · .github/workflows/ci.yml
```

## Documentação

| Documento | Conteúdo |
|---|---|
| [`docs/er-diagram.md`](docs/er-diagram.md) | Diagrama do banco (Mermaid) e constraints que carregam regra de negócio |
| [`docs/architecture.md`](docs/architecture.md) | Camadas, fluxo de uma requisição e ambientes (Mermaid) |
| [`docs/technical-decisions.md`](docs/technical-decisions.md) | Decisões técnicas, trade-offs e limitações conhecidas |
| [`docs/postman_collection.json`](docs/postman_collection.json) | Coleção do Postman (importável no Insomnia) |
