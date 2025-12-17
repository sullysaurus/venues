# Venue Seat Views

AI-powered seat view generation for any venue. See the view from any seat before you buy tickets.

## Tech Stack

- **Frontend**: Next.js 14 (deployed on Vercel)
- **Backend**: FastAPI
- **Workflows**: Temporal Cloud
- **Compute**: Modal (Blender rendering + AI generation)
- **Database**: Supabase (PostgreSQL + Storage)

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Next.js Web   │────▶│   FastAPI on     │────▶│  Temporal Cloud │
│   (Vercel)      │     │   Modal          │     │  (Orchestrator) │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                               │                          │
                               ▼                          ▼
                       ┌──────────────────┐      ┌─────────────────┐
                       │     Supabase     │      │ Temporal Worker │
                       │   (DB + Storage) │      │   (Modal*)      │
                       └──────────────────┘      └────────┬────────┘
                                                          │
                        ┌─────────────────────────────────┼─────────────────────────────────┐
                        ▼                                 ▼                                 ▼
               ┌─────────────────┐             ┌─────────────────┐             ┌─────────────────┐
               │  Blender on     │             │  Replicate API  │             │   OpenAI API    │
               │  Modal (3D)     │             │  (Flux, SDXL)   │             │ (GPT-4V, DALL-E)│
               └─────────────────┘             └─────────────────┘             └─────────────────┘
```

### Component Responsibilities

| Component | Role |
|-----------|------|
| **Next.js** | UI - upload seatmaps, select sections, view results |
| **FastAPI on Modal** | API - handles requests, starts Temporal workflows |
| **Temporal Cloud** | Orchestrates the pipeline - tracks state, handles retries, manages long-running jobs |
| **Temporal Worker** | Executes workflow steps - calls Blender, Replicate, OpenAI |
| **Blender on Modal** | Builds 3D arena model, renders depth maps from each seat |
| **Replicate/OpenAI** | AI image generation from depth maps |
| **Supabase** | PostgreSQL database + image storage |

### Why Temporal?

The pipeline has 4 steps that can take 10+ minutes total. Temporal provides:
- **State persistence** - if a step fails, resume from where it left off
- **Automatic retries** - if Replicate fails, retry that one image
- **Progress tracking** - query "how many images done?" anytime
- **Cancellation** - stop mid-pipeline without losing completed work
- **Observability** - full visibility into workflow execution

### *Worker Deployment Note

Currently the Temporal Worker runs on Modal (auto-started via GitHub Actions). For production/enterprise, the worker should move to dedicated infrastructure:

| Option | Best For | Pros |
|--------|----------|------|
| **Railway / Render** | Startups | Simple deploy, cheap, no DevOps needed |
| **AWS ECS Fargate** | Enterprise | Auto-scaling, AWS ecosystem, managed |
| **Kubernetes** | Enterprise | Maximum flexibility, multi-cloud |

The worker is a simple Python process that needs to run continuously. See `temporal/worker.py`.

## How It Works

1. **Define sections** - Map venue layout to angular positions
2. **Generate seats** - Calculate XYZ coordinates for each seat
3. **Build 3D model** - Create venue geometry in Blender (Modal)
4. **Render depth maps** - Capture geometry from each seat position
5. **AI generation** - Convert depth maps to photorealistic images

## Quick Start

### 1. Environment Variables

```bash
cp .env.example .env
# Fill in your credentials:
# - SUPABASE_URL, SUPABASE_KEY
# - TEMPORAL_ADDRESS, TEMPORAL_NAMESPACE, TEMPORAL_API_KEY
# - REPLICATE_API_TOKEN
```

### 2. Supabase Setup

1. Create a Supabase project
2. Run the migrations in `supabase/migrations/` in order
3. Create a storage bucket called "IMAGES" (public)

### 3. Install Dependencies

```bash
# Python (from root)
pip install -r requirements.txt

# Frontend
cd web && npm install
```

### 4. Run Locally

```bash
# Terminal 1: FastAPI backend
uvicorn api.main:app --reload --port 8000

# Terminal 2: Temporal worker
python -m temporal.worker

# Terminal 3: Next.js frontend
cd web && npm run dev
```

## Deployment

### Frontend (Vercel)
- Connect repo to Vercel
- Set root directory to `web`
- Environment variables: `NEXT_PUBLIC_API_URL`

### Modal (GitHub Actions)
- Push to main triggers `modal deploy modal_app.py`
- Requires `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET` secrets

### Temporal Worker
- Run on any server with Python 3.11+
- Requires Temporal Cloud credentials

## Project Structure

```
venue-seat-views/
├── api/                    # FastAPI backend
│   ├── main.py             # API entry point
│   ├── schemas.py          # Pydantic models
│   ├── routes/             # API endpoints
│   └── db/                 # Supabase integration
│
├── web/                    # Next.js frontend
│   ├── app/                # App router pages
│   └── lib/api.ts          # API client
│
├── temporal/               # Workflow orchestration
│   ├── workflows/          # Temporal workflows
│   ├── activities/         # Temporal activities
│   └── worker.py           # Worker entry point
│
├── modal_app.py            # Modal compute functions
└── supabase/migrations/    # Database migrations
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/venues` | GET | List all venues |
| `/venues` | POST | Create venue |
| `/venues/{id}` | GET | Get venue details |
| `/venues/{id}` | DELETE | Delete venue |
| `/venues/{id}/sections` | GET/PUT | Manage sections |
| `/pipelines` | POST | Start pipeline |
| `/pipelines/{id}` | GET | Get progress |
| `/images/{venue}/{seat}` | GET | Get image |

## Pipeline Stages

1. **Seats** - Generate seat positions from section configurations
2. **Model** - Build 3D Blender model of the venue
3. **Depth Maps** - Render depth maps from each seat position
4. **Images** - Generate AI images using depth maps as guidance

## Cost Estimates

| AI Model | Per Image | 18 anchors | 291 samples |
|----------|-----------|------------|-------------|
| flux (default) | ~$0.03 | ~$0.50 | ~$9 |
| ip_adapter (style transfer) | ~$0.04 | ~$0.70 | ~$12 |

Blender rendering runs on Modal (serverless GPU).
