# Decisões técnicas

Cada decisão segue o formato **contexto → escolha → trade-off**. O objetivo não é listar o que foi
feito, e sim registrar *por que* e *o que se perde* com cada escolha.

## Sumário

1. [Sobreposição de horários: service + constraint do banco](#1-sobreposição-de-horários-service--constraint-do-banco)
2. [Recurso de outro usuário responde 404, não 403](#2-recurso-de-outro-usuário-responde-404-não-403)
3. [Datas: fuso obrigatório na entrada, UTC no banco](#3-datas-fuso-obrigatório-na-entrada-utc-no-banco)
4. [Máquina de estados do agendamento](#4-máquina-de-estados-do-agendamento)
5. [Autenticação: argon2 e dois tokens](#5-autenticação-argon2-e-dois-tokens)
6. [Rate limiting em memória](#6-rate-limiting-em-memória)
7. [Formato de erro único](#7-formato-de-erro-único)
8. [Camadas: rotas sem regra, services sem HTTP](#8-camadas-rotas-sem-regra-services-sem-http)
9. [Listagens: paginação, ordenação, filtros e N+1](#9-listagens-paginação-ordenação-filtros-e-n1)
10. [Modelagem](#10-modelagem)
11. [Stack: Flask, flask-smorest e Marshmallow](#11-stack-flask-flask-smorest-e-marshmallow)
12. [Estratégia de testes](#12-estratégia-de-testes)
13. [Lint e formatação](#13-lint-e-formatação)
14. [Seed seguro](#14-seed-seguro)
15. [Container, CI e deploy](#15-container-ci-e-deploy)
16. [Limitações conhecidas e próximos passos](#16-limitações-conhecidas-e-próximos-passos)

---

## 1. Sobreposição de horários: service + constraint do banco

**Contexto.** A regra central do domínio é: um usuário não pode ter dois agendamentos ativos
sobrepostos. Validar só no código tem uma falha clássica: duas requisições simultâneas executam a
checagem ("não há conflito") antes de qualquer uma gravar, e as duas gravam.

**Escolha.** Duas camadas com papéis diferentes:

1. O **service** consulta o banco e devolve um `409 APPOINTMENT_CONFLICT` explicativo, com o `id` e o
   horário do agendamento que conflita. É a camada da boa experiência.
2. Uma **exclusion constraint** do PostgreSQL é a camada da garantia:
   `EXCLUDE USING gist (user_id WITH =, tstzrange(start_at, end_at) WITH &&) WHERE (status = 'scheduled')`.
   Se a corrida passar pela camada 1, o banco rejeita o segundo `INSERT`, e a aplicação converte essa
   violação (identificada pelo nome da constraint) no mesmo `409`. Qualquer *outro* erro de
   integridade **não** é mascarado.

Detalhes que importam:

- Intervalo **semiaberto** `[início, fim)`: um atendimento de 10:00 a 10:45 não conflita com outro
  que começa às 10:45.
- Só `scheduled` ocupa a agenda (`WHERE`): cancelar libera o horário.
- A constraint combina igualdade (`user_id`) com sobreposição de intervalo, o que exige a extensão
  `btree_gist`, criada na migration.

**Trade-off.** Prende a regra a um recurso específico do PostgreSQL (não portável para SQLite/MySQL) e
o Alembic não gera a constraint sozinho (ela entra na migration à mão, e um teste garante que existe).
Em troca, a regra vale mesmo que alguém escreva no banco por outro caminho.

**Como foi validado.** Testes de borda (sobreposição parcial, total, contida, adjacente), um teste
determinístico que *desliga* a camada 1 e prova que o banco barra sozinho, e um teste com duas threads
disputando o mesmo horário (resultado final: exatamente um `201` e um `409`).

## 2. Recurso de outro usuário responde 404, não 403

**Contexto.** Cada usuário só pode ver e alterar os próprios dados. Quando alguém pede o recurso de
outro, "403 Forbidden" confirma que aquele ID existe.

**Escolha.** Responder **404** nos dois casos (inexistente e de outro usuário). Toda busca passa por
um único ponto (`get_owned_or_404`), que filtra por `user_id`, para nenhuma rota esquecer o filtro.
Referências no corpo (`customer_id`/`service_id` de outro usuário ao criar agendamento) também dão 404.

**Trade-off.** Perde-se a distinção "não existe" × "não é seu" na depuração. Ganha-se resistência a
enumeração de IDs. O `403` fica reservado para o caso em que o usuário *sabidamente* conhece o recurso
mas não tem permissão (não há esse caso hoje).

## 3. Datas: fuso obrigatório na entrada, UTC no banco

**Contexto.** `2030-01-10T09:00:00` sem fuso é ambíguo: 9h de onde? Isso gera bugs em horário de verão e
quando cliente e servidor estão em regiões diferentes.

**Escolha.** `start_at` exige ISO 8601 **com fuso** (`-03:00` ou `Z`); sem fuso retorna `422`. O servidor
converte para UTC, grava em `timestamptz` e **responde sempre em UTC**. O mesmo vale para os filtros
`date_from`/`date_to`.

**Trade-off.** O cliente da API precisa enviar o fuso (um pouco menos amigável do que assumir um fuso
padrão do negócio). A alternativa esconderia a ambiguidade em vez de eliminá-la. Agendar no passado
também é rejeitado (`START_IN_THE_PAST`), por ser quase sempre erro de digitação.

## 4. Máquina de estados do agendamento

**Escolha.** Só `scheduled` pode virar `canceled` ou `completed`; nenhum estado volta a `scheduled`.
O status **não é editável via `PATCH`**: muda apenas por `POST /cancel` e `POST /complete`, que
documentam a intenção. Transição inválida retorna `409 INVALID_STATUS_TRANSITION`.

**Detalhe não óbvio.** Concluir só é permitido **depois que o atendimento começou**. Como a constraint só
considera `scheduled`, concluir um atendimento *futuro* liberaria o horário e permitiria uma segunda
reserva por cima dele.

**Outras regras.** Só agendamentos ativos são editáveis; concluídos são histórico e não podem ser
removidos. Remover agendado ou cancelado é permitido.

**Trade-off.** Mais endpoints e regras do que um simples campo `status` editável, mas o histórico fica
consistente e os estados inválidos são impossíveis de alcançar pela API.

## 5. Autenticação: argon2 e dois tokens

- **Senhas com argon2** (`argon2-cffi`): vencedor da Password Hashing Competition e recomendado pela
  OWASP, resistente a ataque com GPU por usar muita memória. bcrypt também seria aceitável; o argon2
  foi escolhido por ser a recomendação atual.
- **Login não revela se o e-mail existe.** E-mail inexistente e senha errada retornam a mesma mensagem
  (`401 INVALID_CREDENTIALS`) e gastam o mesmo tempo (a verificação roda contra um hash descartável quando
  o usuário não existe), para um atacante não descobrir contas pelo tempo de resposta.
- **Access token curto (15 min) + refresh token (7 dias).** Se um access token vazar, a janela de uso é
  pequena. Os tipos não se misturam: refresh em rota protegida e access em `/refresh` retornam `401`.
- **Cadastro simultâneo com o mesmo e-mail:** o service checa antes, mas quem decide é a constraint
  única; a violação vira `409` em vez de `500`.

**Trade-off.** JWT é *stateless*: não há como revogar um token antes de expirar (ver
[limitações](#16-limitações-conhecidas-e-próximos-passos)). O access token curto mitiga, mas não elimina.

## 6. Rate limiting em memória

**Escolha.** `Flask-Limiter` em login e cadastro (10 por minuto por IP, configurável), para dificultar
força bruta. Excedido: `429 RATE_LIMITED` no formato padrão.

**Trade-off.** O contador em memória é **por processo**: com vários workers do gunicorn o limite
efetivo é multiplicado. Para produção com vários processos, apontar `RATELIMIT_STORAGE_URI` para Redis.
Atrás de proxy (Render/Railway) o IP visto pelo Flask é o do proxy, então o limite valeria para todos
os usuários juntos. Por isso `TRUSTED_PROXY_COUNT` configura o `ProxyFix` (padrão `0`; em produção `1`).
Se a aplicação confiasse em `X-Forwarded-For` sem proxy, qualquer cliente forjaria o próprio IP e fugiria
do limite; com `1`, só o último salto (o que o proxy anexou) vale. Ambos os casos têm teste.

## 7. Formato de erro único

**Escolha.** Toda resposta de erro tem a mesma forma:

```json
{"error": {"code": "APPOINTMENT_CONFLICT", "message": "...", "details": {}}}
```

- `code` é estável e pensado para o cliente tomar decisões (`message` é para humanos).
- Cobre erros de domínio, validação (`422` com `details` por campo), 404/405/429, falhas do JWT
  (por padrão a extensão devolve outro formato) e exceções inesperadas.
- `500` nunca vaza a mensagem interna da exceção.

**Códigos usados.** `400`/`401`/`403`/`404`/`409`/`422`, mais `405`/`429`/`500`. `422` é para entrada
inválida ou regra de negócio violada (horário no passado, serviço inativo); `409` é para conflito com o
estado atual (horário ocupado, e-mail duplicado, transição inválida).

## 8. Camadas: rotas sem regra, services sem HTTP

**Escolha.** `routes/` recebe e responde; `schemas/` define o contrato; `services/` aplica as regras;
`models/` mapeia tabelas. Os services não importam `request`/`response` e levantam exceções de domínio
(`AppError`), que carregam apenas o status associado; a tradução para a resposta HTTP acontece em um
único lugar (`error_handlers.py`).

**Benefício concreto.** As regras são testadas como funções comuns (testes unitários sem cliente HTTP),
e trocar o framework web não exigiria reescrever o domínio.

**Trade-off.** Mais arquivos e indireção do que colocar tudo na rota. Para um CRUD trivial seria exagero;
aqui as regras (conflito, estados, ownership) justificam.

## 9. Listagens: paginação, ordenação, filtros e N+1

- **Envelope** `{items, page, per_page, total, pages}`, com `per_page` máximo de 100. Paginação por
  *offset*: simples e suficiente para o volume do domínio (ver limitações).
- **Ordenação por lista permitida.** `sort` só aceita colunas declaradas no schema; o nome nunca vai
  direto para o `ORDER BY` (evita injeção e vazamento de colunas como `password_hash`). Há **desempate
  por `id`**: sem ele, registros com o mesmo valor de ordenação repetem ou somem entre páginas.
- **Busca escapada.** `q=%` procura o caractere `%`, não "tudo" (`autoescape`).
- **Parâmetros desconhecidos retornam 422.** Um typo como `?satus=canceled` não pode devolver a lista
  inteira em silêncio. (O `Meta.unknown` do schema é ignorado para query string no webargs; é preciso
  passar `unknown=RAISE` no `arguments`.)
- **Sem N+1.** Cliente e serviço de cada agendamento vêm por `JOIN` na mesma consulta; um teste conta
  os SQLs para garantir que o custo não cresce com o tamanho da página.

## 10. Modelagem

- **`status` como `String` + `CHECK`**, não como enum nativo do PostgreSQL. Incluir um status novo vira
  uma migration simples, sem `ALTER TYPE` (que tem restrições em transações).
- **`user_id` denormalizado em `appointments`.** Dá para chegar ao dono via cliente ou serviço, mas
  guardar direto elimina um `JOIN` em toda checagem de dono e de conflito, e é necessário para a
  constraint de sobreposição. Custo: uma coluna redundante (consistência garantida pelo service).
- **`end_at` armazenado** (não calculado na leitura): permite consultar sobreposição como comparação de
  intervalo e indexar. Custo: se a duração do serviço mudar depois, agendamentos antigos mantêm o término
  original — o que é o comportamento desejado (o histórico não muda retroativamente).
- **Dinheiro como `Numeric(10,2)`/`Decimal`**, serializado como *string* (`"59.90"`): evita erros de ponto
  flutuante e arredondamento no cliente.
- **`RESTRICT` em cliente/serviço com agendamentos** (e não `CASCADE`): apagar um cliente não pode apagar
  o histórico de atendimentos em silêncio. A API verifica antes e devolve `409` com a saída sugerida
  (desativar o serviço).
- **E-mail normalizado** (minúsculas, sem espaços) antes de comparar e gravar.

## 11. Stack: Flask, flask-smorest e Marshmallow

- **flask-smorest** gera o OpenAPI (`/docs`) a partir dos mesmos schemas que validam a entrada, então
  documentação e comportamento não divergem. Marshmallow foi escolhido por ser a integração nativa dele.
  Pydantic seria uma opção válida, mas exigiria outra biblioteca para gerar o OpenAPI.
- **SQLAlchemy 2.x** com tipagem (`Mapped[...]`) e **Flask-Migrate/Alembic** para migrations versionadas.
- **Application factory** (`create_app`): permite instanciar apps com configurações diferentes (testes,
  migrations, produção).

**Trade-off.** Flask é mais enxuto que Django/FastAPI e exige montar as peças (auth, validação, docs);
em troca, cada peça é visível e substituível, o que ajuda a mostrar as escolhas.

## 12. Estratégia de testes

- **PostgreSQL real** em um banco separado (`scheduler_test`), não SQLite: as garantias mais importantes
  (exclusion constraint, `timestamptz`) não existem em SQLite, e um teste que passa contra um banco
  diferente do de produção dá falsa confiança.
- **Dois níveis:** unitários das regras (services) e de integração dos endpoints (cliente HTTP real do
  Flask), incluindo os casos de erro: sem token, token malformado, assinado por outra chave, expirado,
  refresh usado no lugar de access, dado de outro usuário e conflito de horário.
- **Migrations testadas contra os models.** Os testes usam `create_all`; por isso um teste à parte sobe
  as migrations em um banco descartável e exige **zero divergência** com os models (além de conferir a
  constraint e exercitar o `downgrade`). Sem isso, uma migration errada só apareceria em produção.
- **Relógio controlável** no service de agendamentos, para testar passado/futuro sem `sleep`.
- **Cobertura mínima de 80%** imposta pela configuração (`pytest` falha abaixo disso), com `UserWarning`
  tratado como erro (um schema duplicado no OpenAPI quebra a suíte).

**Trade-off.** Testes com banco real são mais lentos e exigem o Postgres rodando; o custo vale pela
fidelidade.

## 13. Lint e formatação

**Escolha.** Apenas o **ruff** (lint e `ruff format`), em vez de ruff + black. O formatador do ruff é
praticamente compatível com o black e roda em uma única ferramenta e uma única configuração
(`pyproject.toml`). O conjunto de regras inclui `S` (bandit) para segurança.

## 14. Seed seguro

**Escolha.** `flask seed` cria um usuário de demonstração com clientes, serviços e uma agenda realista
(passado concluído/cancelado e futuro agendado, sem sobreposição), de forma determinística.

- **Recusa rodar com `APP_ENV=production`**, mesmo que a senha esteja definida.
- A senha vem de `SEED_DEMO_PASSWORD`; só em `development` existe um valor padrão. Fora disso, sem a
  variável, o comando falha em vez de criar um login conhecido.
- É idempotente: rodar de novo exige `--reset` explícito. A senha nunca é impressa.

**Trade-off.** Um login de demonstração é conveniente para quem avalia o projeto, mas é um risco se
existir em produção; por isso as travas acima.

## 15. Container, CI e deploy

**Imagem.** Dockerfile em dois estágios: o primeiro instala as dependências em um venv, o segundo copia só
o venv e o código da aplicação (sem testes, docs, `.git` nem `.env`, garantido pelo `.dockerignore`).
O processo roda como **usuário sem privilégios** (`uid 10001`) com **gunicorn**, e a imagem tem
`HEALTHCHECK` próprio.

**Migrations no start do container.** O `entrypoint.sh` roda `flask db upgrade` e depois inicia o servidor.
Alternativa melhor em planos pagos: `preDeployCommand` (migrar uma vez, antes de trocar a versão). No plano
gratuito do Render ele não existe. *Trade-off:* com várias instâncias subindo ao mesmo tempo, todas tentam
migrar e não há exclusão mútua entre elas: uma pode falhar e o container reinicia. Com uma instância (o caso
do plano gratuito) isso não ocorre; com mais, o correto é migrar em um passo separado.

**Falhar cedo em produção.** Com `APP_ENV=production`, a aplicação **se recusa a iniciar** se as chaves
forem curtas (< 32), iguais entre si ou começarem com marcadores de exemplo (`change-me`, `dev-only`...).
A mensagem orienta como gerar uma chave, mas nunca imprime o valor configurado. O CI prova isso subindo o
container em produção com as chaves de demonstração e exigindo que ele falhe.

**Sem `DEBUG=True` na configuração.** Sob o gunicorn ele ligaria o modo debug do Flask. Para depurar,
`flask run --debug`.

**CI com três jobs.** Lint, testes (PostgreSQL como service container, cobertura mínima de 80% imposta) e
um smoke test do Docker que valida o que os testes de unidade não veem: o `Dockerfile`, o entrypoint, as
migrations em um banco vazio e a stack real.

**Deploy declarativo.** O `render.yaml` descreve banco e serviço; as chaves são geradas pelo Render
(`generateValue`) e a conexão do banco é injetada (`fromDatabase`). Há testes que impedem o Blueprint de
definir variáveis que a aplicação não lê ou de conter segredos literais, e o arquivo foi validado contra o
schema JSON oficial do Render.

## 16. Limitações conhecidas e próximos passos

O que ficou **de fora de propósito** (e o que faria depois):

| Limitação | Por quê | Próximo passo |
|---|---|---|
| Sem revogação de token / logout real | JWT stateless; access token é curto | Lista de revogação (Redis) ou rotação de refresh token |
| Rate limit em memória, por processo | Simplicidade | Redis como storage |
| Um usuário = uma agenda | Foco no domínio central | Profissionais/recursos por negócio, conflito por profissional |
| Sem horário de funcionamento nem disponibilidade | Escopo | Regras de expediente e endpoint de horários livres |
| Paginação por *offset* | Suficiente para o volume | Paginação por cursor se as tabelas crescerem muito |
| Sem exclusão lógica (*soft delete*) | Histórico já é preservado por status e `RESTRICT` | Soft delete se houver exigência legal de retenção |
| Migrations rodam no start do container | Plano gratuito do Render não tem `preDeployCommand` | `preDeployCommand` (ou job de migração) assim que houver mais de uma instância |
| Sem notificações (e-mail/SMS) | Escopo | Fila de tarefas + lembretes de agendamento |
| Fuso do negócio não é guardado | A API fala UTC/ISO com fuso | Campo de fuso no usuário para relatórios por dia local |
