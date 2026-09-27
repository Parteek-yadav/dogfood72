# Dogfood 2026 - Hackathon Submission & Judging Platform

A unified submission-and-judging platform built for the Dogfood 2026 72-hour hackathon.

## Quickstart

Run the entire application stack using Docker Compose:

```bash
# 1. Copy the example environment variables (if not already present)
cp .env.example .env

# 2. Build and start services
docker compose up --build
```

Once running:
- **Web Application**: [http://localhost:8000](http://localhost:8000)
- **OpenAPI Schema**: [http://localhost:8000/api/schema/](http://localhost:8000/api/schema/)
- **Swagger API Docs**: [http://localhost:8000/api/docs/](http://localhost:8000/api/docs/)
- **Django Admin**: [http://localhost:8000/admin/](http://localhost:8000/admin/)
