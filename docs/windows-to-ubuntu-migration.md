# Windows to Ubuntu Migration Plan

## Recommendation

Do the actual development inside Ubuntu on VMware, not on the Windows host filesystem. Use Windows only as the host machine running VMware.

That avoids:

- path separator issues
- file permission differences
- Docker performance problems on shared folders
- line-ending problems
- slower Python virtual environments

## Target setup

Windows host:

- VMware Workstation
- optional Git client
- optional VS Code

Ubuntu guest:

- main development environment
- Docker and Docker Compose
- Python tooling
- repository clone

## VM sizing

For this project, start with:

- `4 vCPU`
- `12 GB RAM` minimum
- `16 GB RAM` preferred if you will run Kafka, Postgres, MinIO, and embeddings together
- `60 GB` disk minimum

If you later add local model training or Milvus, increase memory.

## Ubuntu version

Use `Ubuntu 22.04 LTS` or `Ubuntu 24.04 LTS`.

If you want maximum library compatibility today, `22.04 LTS` is the safer default.

## Migration steps

### 1. Create the VM

- install Ubuntu
- enable VMware shared clipboard
- do not keep the active repo in a shared folder

### 2. Install base packages in Ubuntu

```bash
sudo apt update
sudo apt install -y git curl build-essential pkg-config libpq-dev python3-dev python3-venv
```

### 3. Install Docker

Use Docker Engine and the Compose plugin from Docker's official repository. After installation:

```bash
sudo usermod -aG docker "$USER"
newgrp docker
docker --version
docker compose version
```

### 4. Install Python dependency tooling

Recommended:

- `uv` for fast virtual environments and dependency management

Example:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 5. Move the repository

Best option:

- push the Windows copy to Git and clone it in Ubuntu

Fallback option:

- copy the folder once through a VMware shared folder or `scp`
- then work from a native Ubuntu path such as `~/workspace/ATS_BD_PROJECT`

Example:

```bash
mkdir -p ~/workspace
cd ~/workspace
git clone <your-repo-url> ATS_BD_PROJECT
cd ATS_BD_PROJECT
```

### 6. Normalize line endings

This repository now includes a `.gitattributes` file that defaults to `LF`, which is what you want in Ubuntu.

After cloning in Ubuntu:

```bash
git config core.autocrlf input
```

### 7. Start local infrastructure

From the Ubuntu repo directory:

```bash
cp .env.example .env
docker compose -f infra/docker-compose.yml up -d
```

## Recommended working model

### Source code

Keep source code in:

```text
/home/<user>/workspace/ATS_BD_PROJECT
```

Avoid:

```text
/mnt/hgfs/...
```

VMware shared folders are fine for one-time transfer, not daily development.

### Data and artifacts

Use local Linux directories or Docker volumes for:

- uploaded resumes
- parsed artifacts
- vector indexes
- logs

### IDE access

Two practical options:

1. install VS Code inside Ubuntu
2. SSH into the Ubuntu VM from Windows and use Remote SSH

Both are better than editing files through a shared folder.

## Stack choices for Ubuntu first

Use these choices for the first implementation:

- Python `3.11`
- `FastAPI`
- `spaCy`
- `sentence-transformers`
- `Redpanda`
- `PostgreSQL`
- `MinIO`
- local `FAISS`

This is much lighter than trying to run Spark, Kafka, Airflow, and Milvus immediately inside a VM.

## Migration strategy from your current baseline

Do not rewrite everything at once. Move in this order:

1. Preserve the existing conceptual stages: upload, parse, rank, shortlist.
2. Replace regex/RAKE with NLP parsing.
3. Replace TF-IDF with embeddings.
4. Keep heuristic scoring initially so you can validate the pipeline.
5. Add Kafka-compatible streaming after the service boundaries are stable.
6. Add ML ranking only after you have training signals.

## Risks to avoid

- using Spark too early for tasks that do not need distributed compute
- keeping the repo on shared Windows folders
- introducing Milvus and Airflow before the core parsing and ranking pipeline works
- depending on GPU-only workflows inside a small VM

## Practical conclusion

The cleanest move is:

- keep Windows as the host
- use Ubuntu in VMware as the real dev machine
- run infra with Docker Compose
- start with FAISS locally
- add Milvus, Airflow, and learning-to-rank only after the MVP pipeline is stable
