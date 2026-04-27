# HVAC/PV PDF Harvester — Backend

Backend FastAPI de collecte automatique de notices PDF techniques (HVAC, PAC, PV).

---

## Architecture

```
Lovable (frontend)
     │  HTTP REST
     ▼
FastAPI (Render / Railway)
  ├── POST /collect  →  DuckDuckGo → download PDF → Supabase Storage + Postgres
  ├── GET  /documents →  Supabase Postgres
  └── GET  /health
```

---

## 1. Prérequis Supabase

### 1.1 Créer la table `document_pdf`

Dans ton projet Supabase → **SQL Editor** → **New query**, colle et exécute :

```sql
create table if not exists public.document_pdf (
  id          uuid        primary key default gen_random_uuid(),
  created_at  timestamptz not null    default now(),
  brand       text,
  model       text,
  title       text,
  doc_type    text,
  source_url  text,
  storage_path text,
  storage_url  text,
  source      text,
  sha256      text unique,
  file_size   bigint
);

create index if not exists idx_document_pdf_brand_model
  on public.document_pdf (brand, model);

create index if not exists idx_document_pdf_sha256
  on public.document_pdf (sha256);

alter table public.document_pdf enable row level security;

create policy "Lecture publique document_pdf"
  on public.document_pdf for select using (true);
```

Le fichier `supabase_schema.sql` contient la même chose.

### 1.2 Créer le bucket Storage `documents`

Dans Supabase → **Storage** → **New bucket** :

| Champ | Valeur |
|-------|--------|
| Name | `documents` |
| Public bucket | ✅ coché (pour que les URLs soient accessibles publiquement) |

### 1.3 Récupérer les clés API

Dans Supabase → **Settings** → **API** :

- `Project URL` → `SUPABASE_URL`
- `service_role` (secret) → `SUPABASE_SERVICE_ROLE_KEY`

---

## 2. Variables d'environnement

Copie `.env.example` en `.env` pour le développement local :

```bash
cp .env.example .env
```

| Variable | Description |
|----------|-------------|
| `SUPABASE_URL` | URL du projet Supabase |
| `SUPABASE_SERVICE_ROLE_KEY` | Clé service_role (ne pas exposer publiquement) |
| `SUPABASE_BUCKET` | Nom du bucket (`documents` par défaut) |
| `ALLOWED_ORIGINS` | Origines CORS (`*` ou URL Lovable) |
| `PORT` | Port d'écoute (géré automatiquement par Render/Railway) |

---

## 3. Installation locale

```bash
# Cloner / se placer dans le dossier
cd backend/

# Créer un virtualenv Python 3.11
python3.11 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# Installer les dépendances
pip install -r requirements.txt

# Configurer l'environnement
cp .env.example .env
# → Édite .env avec tes vraies valeurs Supabase

# Lancer le serveur de développement
uvicorn main:app --reload --port 8000
```

Le backend est accessible sur `http://localhost:8000`.

---

## 4. Déploiement sur Render

### 4.1 Étapes

1. **Push** ton code sur GitHub (repo public ou privé)
2. Va sur [render.com](https://render.com) → **New** → **Web Service**
3. Connecte ton repo GitHub
4. Configure :

| Champ | Valeur |
|-------|--------|
| Environment | Python 3 |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn main:app --host 0.0.0.0 --port $PORT` |
| Instance Type | Free (ou Starter pour des perfs correctes) |

5. Dans **Environment Variables**, ajoute :
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_ROLE_KEY`
   - `SUPABASE_BUCKET` = `documents`
   - `ALLOWED_ORIGINS` = `https://ton-app.lovable.app` (ou `*`)

6. **Create Web Service** → Render build et déploie automatiquement

L'URL du service ressemble à : `https://hvac-pdf-harvester.onrender.com`

> ⚠️ Sur le plan Free de Render, le service s'endort après 15 min d'inactivité.
> Pour un usage production, utilise le plan Starter ($7/mois).

---

## 5. Déploiement sur Railway

### 5.1 Étapes

1. Va sur [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo**
2. Sélectionne ton repo
3. Railway détecte automatiquement Python grâce au `Procfile`
4. Dans **Variables**, ajoute les mêmes variables d'environnement que ci-dessus
5. **Deploy** → Railway construit et démarre le service

L'URL est disponible dans **Settings** → **Domains** → **Generate Domain**.

---

## 6. Tester avec curl

### Health check

```bash
curl https://ton-backend.onrender.com/health
# → {"status":"ok"}
```

### Lancer une collecte

```bash
curl -X POST https://ton-backend.onrender.com/collect \
  -H "Content-Type: application/json" \
  -d '{
    "products": [
      {"brand": "Atlantic", "model": "Calypso"},
      {"brand": "Daikin", "model": "Altherma"}
    ],
    "max_results_per_query": 5
  }'
```

Réponse attendue :
```json
{
  "status": "ok",
  "products_processed": 2,
  "pdfs_found": 14,
  "pdfs_uploaded": 11,
  "duplicates": 2,
  "errors": []
}
```

### Lister les documents

```bash
curl https://ton-backend.onrender.com/documents
```

### Documentation interactive

Ouvre dans le navigateur :
```
https://ton-backend.onrender.com/docs
```

---

## 7. Connecter Lovable

Dans ton projet Lovable, utilise `fetch` ou un client HTTP pour appeler le backend :

```typescript
// lib/api.ts

const API_BASE = import.meta.env.VITE_API_URL; // ex: https://ton-backend.onrender.com

export async function collectPdfs(products: { brand: string; model: string }[]) {
  const res = await fetch(`${API_BASE}/collect`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ products, max_results_per_query: 5 }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function getDocuments() {
  const res = await fetch(`${API_BASE}/documents`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}
```

Dans Lovable, définis la variable d'environnement :
```
VITE_API_URL=https://ton-backend.onrender.com
```

---

## 8. Structure du projet

```
backend/
├── main.py              # Application FastAPI, endpoints, CORS
├── collector.py         # Pipeline de collecte (search → download → upload)
├── supabase_client.py   # Appels REST Supabase (Storage + Postgres)
├── models.py            # Schémas Pydantic (requêtes et réponses)
├── requirements.txt     # Dépendances Python
├── Procfile             # Commande de démarrage (Render/Railway)
├── runtime.txt          # Version Python
├── supabase_schema.sql  # SQL de création de la table
├── .env.example         # Template de configuration
└── README.md            # Ce fichier
```

---

## 9. Notes techniques

### Déduplication
Les PDFs sont dédupliqués par **SHA256** du contenu. Un même fichier téléchargé depuis deux URLs différentes n'est stocké qu'une seule fois.

### Rate limiting DDG
Une pause de 1,5 s est insérée entre chaque requête DuckDuckGo pour éviter le blocage. Pour des collectes massives, augmente `_SEARCH_PAUSE` dans `collector.py`.

### Taille maximale
Les PDFs > 50 MB sont ignorés (paramètre `MAX_PDF_SIZE_MB` dans `collector.py`).

### Logs
Les logs sont en sortie standard — consultables dans Render (Logs) ou Railway (Deployments → Logs).
