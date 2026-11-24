# Arquitetura

## Camadas

A regra de ouro: **rotas não têm regra de negócio**, **services não conhecem HTTP**.
Cada camada só conversa com a de baixo.

```mermaid
flowchart TD
    Client["Cliente HTTP<br/>(curl, Postman, Swagger UI)"]

    subgraph API["Aplicação Flask"]
        direction TB
        Routes["routes/<br/>Endpoints, autenticação (JWT), documentação OpenAPI"]
        Schemas["schemas/<br/>Validação de entrada e serialização (Marshmallow)"]
        Services["services/<br/>Regras de negócio e autorização por dono"]
        Models["models/<br/>Tabelas e constraints (SQLAlchemy)"]
        Errors["errors.py + error_handlers.py<br/>Exceções de domínio → formato de erro único"]
    end

    DB[("PostgreSQL<br/>exclusion constraint · CHECKs · UNIQUEs")]

    Client -->|"JSON + Bearer token"| Routes
    Routes -->|"valida / serializa"| Schemas
    Routes -->|"chama"| Services
    Services -->|"consulta / grava"| Models
    Models --> DB
    Services -.->|"levanta AppError"| Errors
    Errors -.->|"{error: {code, message, details}}"| Client
```

| Camada | Responsabilidade | Não deve |
|---|---|---|
| `routes/` | Receber a requisição, exigir JWT, validar via schema, chamar o service, escolher o status HTTP | Conter `if` de regra de negócio ou falar com o banco |
| `schemas/` | Definir o contrato (campos, tipos, limites, exemplos do Swagger) | Consultar o banco |
| `services/` | Aplicar regras (conflito de horário, máquina de estados, dono do recurso) | Importar `request`/`response` do Flask |
| `models/` | Mapear tabelas e declarar constraints | Conter fluxo de negócio |
| `errors.py` | Exceções de domínio (`NotFoundError`, `ConflictError`…) | Conhecer HTTP além do status associado |

## Fluxo de uma requisição: criar agendamento

```mermaid
sequenceDiagram
    autonumber
    participant C as Cliente
    participant R as routes/appointments
    participant S as schemas
    participant V as appointment_service
    participant DB as PostgreSQL

    C->>R: POST /api/v1/appointments (Bearer token)
    R->>R: jwt_required (401 se ausente, inválido ou expirado)
    R->>S: valida corpo (fuso obrigatório, campos desconhecidos)
    S-->>C: 422 VALIDATION_ERROR (se inválido)
    R->>V: create_appointment(user_id do token, dados)
    V->>DB: cliente e serviço pertencem ao usuário?
    DB-->>V: não → 404 (igual a "não existe")
    V->>V: início no passado? serviço ativo? → 422
    V->>DB: existe agendamento ativo sobreposto?
    DB-->>V: sim → 409 APPOINTMENT_CONFLICT (com o id conflitante)
    V->>DB: INSERT appointment
    Note over DB: A exclusion constraint barra a corrida<br/>entre duas requisições simultâneas
    DB-->>V: ok, ou violação → 409 APPOINTMENT_CONFLICT
    V-->>R: Appointment
    R-->>C: 201 + JSON (datas em UTC)
```

## Estrutura de pastas

```
app/
  __init__.py        create_app(): monta extensões, rotas, handlers e CLI
  config.py          Config por ambiente (segredos só via variáveis de ambiente)
  extensions.py      db, migrate, jwt, limiter, api (instanciados sem app)
  auth.py            helpers do usuário autenticado
  errors.py          exceções de domínio
  error_handlers.py  formato de erro padronizado (inclui falhas do JWT)
  cli.py             comando `flask seed`
  models/            User, Customer, Service, Appointment
  schemas/           contratos de entrada/saída e envelopes de paginação
  routes/            blueprints /api/v1/... e exemplos do Swagger
  services/          regras de negócio (auth, clientes, catálogo, agendamentos, seed)
migrations/          Alembic (inclui a exclusion constraint e btree_gist)
tests/               unitários (services) e integração (endpoints), banco de teste separado
docs/                este diretório
```

## Ambientes

```mermaid
flowchart LR
    Dev["Desenvolvimento<br/>flask run + Postgres (docker compose)"]
    Test["Testes<br/>pytest + banco scheduler_test (mesmo servidor)"]
    CI["CI (GitHub Actions)<br/>Postgres como service container"]
    Prod["Produção (Render/Railway)<br/>gunicorn + Postgres gerenciado"]

    Dev --- Test
    Test --- CI
    CI --> Prod
```

Os testes usam **PostgreSQL de verdade**, em um banco separado do de desenvolvimento, porque as
garantias mais importantes (exclusion constraint, `timestamptz`) não existem em SQLite.
