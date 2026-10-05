# 🚀 Artilery (KAOS)

**Fully autonomous, event-driven CI/CD orchestration platform powered by AI agents.**

Artilery automates the entire DevOps lifecycle — from bug triage to deployment resolution — using 4 specialized AI agents communicating over Apache Kafka, backed by LangGraph state machines and LLM-powered intelligence.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        ARTILERY PLATFORM                            │
│                                                                     │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────────┐  │
│  │  Agent 1  │    │  Agent 2  │    │  Agent 3  │    │   Agent 4    │  │
│  │  TRIAGE   │    │  REVIEW   │    │    OPS    │    │   CHATBOT    │  │
│  │           │    │           │    │           │    │              │  │
│  │ Bug→Jira  │    │ PR→Review │    │ Deploy→AI │    │  RAG Q&A    │  │
│  │ →Notion   │    │ →Assign   │    │ →Diagnose │    │  over graph  │  │
│  │ →Slack    │    │ →Track    │    │ →Resolve  │    │  + logs      │  │
│  └─────┬─────┘    └─────┬─────┘    └─────┬─────┘    └──────┬───────┘  │
│        │                │                │                 │          │
│  ──────┴────────────────┴────────────────┴─────────────────┴──────── │
│                         APACHE KAFKA                                 │
│  ────────────────────────────────────────────────────────────────── │
│        │                │                │                 │          │
│  ┌─────┴─────┐    ┌─────┴─────┐    ┌─────┴─────┐    ┌─────┴───────┐│
│  │  Neo4j    │    │  GitHub   │    │   LLM      │    │  ChromaDB   ││
│  │  (Graph)  │    │  Webhooks │    │ Ollama/    │    │  Vector DB  ││
│  │           │    │  (Events) │    │ Bedrock    │    │  (RAG)      ││
│  └───────────┘    └───────────┘    │  S3, Dynamo│    └─────────────┘│
│                                    └───────────┘                    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🤖 AI Agents

| Agent | Name | Kafka Topics | Purpose |
|-------|------|-------------|---------|
| 1 | **Triage** | `bug.ingested` → `ticket.created` | Ingests bugs, queries Neo4j for owner, creates Jira/Notion tickets, Slack DMs |
| 2 | **Review** | `pr.opened`, `pr.reviewed`, `pr.approved` | Assigns reviewers via skill-matching, tracks PR lifecycle |
| 3 | **Ops** | `deploy.triggered`, `deploy.failed`, `deploy.succeeded` | Monitors deployments, AI-diagnoses failures, auto-resolves |
| 4 | **Chatbot** | API only | RAG Q&A over Neo4j graph + S3 event logs + ChromaDB vectors |

---

## ⚡ Quick Start (Local — No Cloud Accounts Needed)

The entire platform runs locally using Docker. Zero cloud accounts, zero API keys, zero credit cards required.

### Prerequisites

- **Python 3.11+**
- **Docker & Docker Compose**
- **(Optional)** [Ollama](https://ollama.com) for local LLM — `ollama pull llama3.2`

### Setup (5 minutes)

```bash
# 1. Clone and enter the project
cd Artillery

# 2. Create virtual environment and install dependencies
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 3. Start all local infrastructure (Kafka, Neo4j, DynamoDB, MinIO)
docker compose up -d

# 4. Run one-command setup (creates tables, topics, seeds data)
python -m scripts.setup_local

# 5. Run agents (each in a separate terminal)
python -m agents.triage.agent    # Terminal 1
python -m agents.review.agent    # Terminal 2
python -m agents.ops.agent       # Terminal 3
uvicorn api.main:app --reload    # Terminal 4 (API server)
```

### Verify It Works

```bash
# Kafka round-trip smoke test
python -m scripts.test_event_flow

# Unit tests (34 tests)
pytest tests/ -v

# Chatbot API
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "Who owns PaymentService?"}'
```

---

## 🐳 Docker Services

| Service | Container | Port | Purpose |
|---------|-----------|------|---------|
| **Kafka** (KRaft) | `artilery-kafka` | 9092 | Event streaming (no Zookeeper) |
| **Neo4j** | `artilery-neo4j` | 7474, 7687 | Graph DB (team/service/on-call) |
| **DynamoDB Local** | `artilery-dynamodb` | 8000 | PR state, chat history, idempotency |
| **MinIO** | `artilery-minio` | 9000, 9001 | S3-compatible event log storage |

---

## 🔧 Environment Modes

Artilery supports two modes via `ARTILERY_ENV`:

### Local Mode (default)
- All infra runs in Docker (Kafka, Neo4j, DynamoDB, MinIO)
- LLM via Ollama (or graceful fallback if not installed)
- Zero cloud credentials needed
- `.env` is pre-configured for local use

### Production Mode
- Confluent Cloud for Kafka
- AWS Bedrock for LLM
- Real Jira, Notion, Slack integrations
- Set `ARTILERY_ENV=production` in `.env`

---

## 📡 Kafka Topics

| Topic | Producer | Consumer | Purpose |
|-------|----------|----------|---------|
| `bug.ingested` | External / Monitoring | Triage Agent | New bug detected |
| `ticket.created` | Triage Agent | — | Jira ticket created |
| `pr.opened` | GitHub Webhook | Review Agent | PR opened or updated |
| `pr.review.requested` | Review Agent | — | Reviewer assigned |
| `pr.reviewed` | GitHub Webhook | Review Agent | PR review submitted |
| `pr.approved` | GitHub Webhook | Review Agent, Ops Agent | PR approved |
| `deploy.triggered` | Ops Agent | Ops Agent | Deployment started |
| `deploy.failed` | CloudWatch Bridge | Ops Agent | Deployment failed |
| `deploy.succeeded` | CloudWatch Bridge | Ops Agent | Deployment succeeded |
| `ticket.resolved` | Ops Agent | — | Jira ticket resolved |

Each topic also has a `.dlq` dead letter queue counterpart (20 topics total).

---

## 🏗️ Project Structure

```
Artillery/
├── agents/                         # AI agent implementations
│   ├── triage/                     # Agent 1: Bug triage
│   │   ├── agent.py                # LangGraph state machine
│   │   ├── tools.py                # Jira, Notion, Slack tools
│   │   └── Dockerfile              # Per-agent Docker image
│   ├── review/                     # Agent 2: PR review
│   │   ├── agent.py                # LangGraph state machine
│   │   ├── tools.py                # Reviewer assignment, Slack, Jira tools
│   │   └── Dockerfile
│   ├── ops/                        # Agent 3: Deployment ops
│   │   ├── agent.py                # LangGraph with escalation edges
│   │   ├── tools.py                # CodeDeploy, Bedrock, rollback, notify tools
│   │   └── Dockerfile
│   └── chatbot/                    # Agent 4: RAG chatbot
│       ├── agent.py                # LangGraph with hybrid retrieval
│       ├── tools.py                # LLM answer generation
│       ├── intent_classifier.py    # LLM + keyword intent classification
│       ├── retrievers.py           # Neo4j, DynamoDB, ChromaDB retrievers
│       └── Dockerfile
├── shared/                         # Cross-cutting utilities
│   ├── config.py                   # Pydantic Settings (local/production modes)
│   ├── kafka_utils.py              # Kafka producer/consumer with DLQ
│   ├── llm.py                      # Unified LLM (Ollama local / Bedrock cloud)
│   ├── neo4j_utils.py              # Neo4j graph queries
│   ├── dynamo_utils.py             # DynamoDB state management
│   ├── s3_utils.py                 # S3/MinIO log storage
│   ├── vector_store.py             # ChromaDB + Titan embeddings
│   └── observability.py            # Structured logging, metrics, decorators
├── api/                            # FastAPI application
│   ├── main.py                     # App entry point with CORS
│   └── routers/
│       ├── github.py               # GitHub webhook handler (HMAC)
│       └── chat.py                 # Chatbot REST API
├── lambda_functions/               # CloudWatch → Kafka bridge
│   └── __init__.py                 # Lambda handler for deployment events
├── scripts/                        # Operational scripts
│   ├── setup_local.py              # 🆕 One-command local setup
│   ├── create_kafka_topics.py      # Topic provisioning
│   ├── seed_neo4j.py               # Graph seeding
│   ├── test_event_flow.py          # Kafka smoke test
│   ├── index_events.py             # S3 → ChromaDB event indexer
│   ├── package_lambda.py           # Lambda ZIP packaging
│   ├── deploy_aws.py               # AWS infrastructure deployment
│   ├── setup_kafka_triggers.py     # Lambda ↔ Kafka event source mapping
│   ├── create_cloudwatch_alarms.py # CloudWatch alarms + SNS
│   ├── e2e_test.py                 # 9-step integration test
│   └── teardown_aws.py             # AWS resource cleanup
├── tests/                          # Test suite (34 tests)
│   ├── test_triage_agent.py
│   ├── test_review_agent.py
│   ├── test_ops_agent.py
│   ├── test_chatbot_agent.py
│   ├── test_kafka_utils.py
│   └── test_api.py
├── .env                            # Local configuration (auto-generated)
├── .env.example                    # Environment template
├── docker-compose.yml              # Kafka + Neo4j + DynamoDB + MinIO
├── .dockerignore                   # Docker build exclusions
├── Dockerfile                      # Multi-stage API Docker image
├── requirements.txt                # Python dependencies
└── README.md                       # This file
```

---

## 🚀 Production Deployment (AWS)

```bash
# Set ARTILERY_ENV=production in .env and fill in cloud credentials

# 1. Package agents as Lambda deployment ZIPs
python -m scripts.package_lambda

# 2. Deploy all AWS resources (DynamoDB, S3, Lambda, API Gateway)
python -m scripts.deploy_aws

# 3. Set up Kafka → Lambda event source mappings
python -m scripts.setup_kafka_triggers

# 4. Create CloudWatch alarms and SNS alerts
python -m scripts.create_cloudwatch_alarms

# 5. Run end-to-end validation
python -m scripts.e2e_test

# 6. (Optional) Teardown all resources
python -m scripts.teardown_aws --dry-run  # Preview first
python -m scripts.teardown_aws            # Execute
```

---

## 🚀 Build Phases

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Environment Setup & Kafka Foundations | ✅ Complete |
| 2 | Triage Agent (Bug → Jira/Notion/Slack) | ✅ Complete |
| 3 | Review Agent & GitHub Webhooks | ✅ Complete |
| 4 | Ops Agent & AWS Integration | ✅ Complete |
| 5 | Knowledge Chatbot (RAG + ChromaDB) | ✅ Complete |
| 6 | Local-First Development & Production Hardening | ✅ Complete |

---

## 🐛 Troubleshooting

| Problem | Solution |
|---------|----------|
| `confluent_kafka` import error | Install librdkafka: `brew install librdkafka` (macOS) |
| Kafka connection timeout | Run `docker compose up -d` and wait 30s for Kafka to start |
| Neo4j connection refused | Run `docker compose up -d` — Neo4j needs ~30s to initialize |
| DynamoDB connection error | Start local DynamoDB: `docker compose up -d dynamodb-local` |
| MinIO connection error | Check `docker compose ps` — MinIO should show `healthy` |
| `.env` not loading | Ensure `.env` is in project root (same dir as `requirements.txt`) |
| Pydantic validation error | Run `python -c "from shared.config import get_settings; get_settings().validate()"` |
| Kafka topic not found | Run `python -m scripts.create_kafka_topics` |
| Agent consumer not starting | Check `docker compose ps` — Kafka must be `healthy` |
| Tests failing | Run `pytest tests/ -v --tb=short` for detailed output |

---

## 📜 License

Internal project — not for public distribution.
