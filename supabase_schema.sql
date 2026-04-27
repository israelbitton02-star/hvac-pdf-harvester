-- ============================================================
-- Table : document_pdf
-- À exécuter dans l'éditeur SQL de Supabase (SQL Editor)
-- ============================================================

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
  sha256      text        unique,      -- clé de déduplication
  file_size   bigint
);

-- Index sur brand+model pour les recherches filtrées
create index if not exists idx_document_pdf_brand_model
  on public.document_pdf (brand, model);

-- Index sur sha256 pour les checks de déduplication rapides
create index if not exists idx_document_pdf_sha256
  on public.document_pdf (sha256);

-- Row Level Security — désactivé pour un accès service_role complet
-- (le backend utilise la clé service_role qui bypasse RLS)
alter table public.document_pdf enable row level security;

-- Politique lecture publique (optionnel — pour GET /documents sans auth)
create policy "Lecture publique document_pdf"
  on public.document_pdf
  for select
  using (true);
