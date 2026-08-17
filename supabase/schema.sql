-- Multilingual Health Insurance Voice Bot — Supabase schema
--
-- Run in the Supabase SQL editor against a fresh project; see README.md
-- "Supabase Setup". No row-level security policies are enabled -- this is
-- a server-only demo accessed exclusively with the service role key from
-- the backend, never from a browser/frontend.

create extension if not exists pgcrypto;

create table if not exists sessions (
    id uuid primary key default gen_random_uuid(),
    livekit_session_id text,
    call_id text,
    started_at timestamptz not null default now(),
    ended_at timestamptz,
    status text not null default 'in_progress' check (status in ('in_progress', 'completed', 'failed')),
    primary_language text not null default 'en',
    detected_languages jsonb not null default '["en"]'::jsonb,
    created_at timestamptz not null default now()
);

create table if not exists caller_profiles (
    id uuid primary key default gen_random_uuid(),
    session_id uuid not null references sessions(id) on delete cascade,
    name text,
    age integer,
    city text,
    family_size integer,
    existing_conditions jsonb not null default '[]'::jsonb,
    existing_insurance boolean,
    desired_coverage integer,
    annual_budget integer,
    family_members jsonb not null default '[]'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (session_id)
);

create table if not exists recommendations (
    id uuid primary key default gen_random_uuid(),
    session_id uuid not null references sessions(id) on delete cascade,
    policy_id text not null,
    policy_name text not null,
    coverage integer not null,
    annual_premium integer not null,
    reasons jsonb not null default '[]'::jsonb,
    created_at timestamptz not null default now()
);

create table if not exists transcript_messages (
    id uuid primary key default gen_random_uuid(),
    session_id uuid not null references sessions(id) on delete cascade,
    speaker text not null check (speaker in ('user', 'assistant')),
    text text not null,
    language text not null,
    timestamp timestamptz not null default now()
);

create index if not exists idx_caller_profiles_session_id on caller_profiles(session_id);
create index if not exists idx_recommendations_session_id on recommendations(session_id);
create index if not exists idx_transcript_messages_session_id on transcript_messages(session_id);
create index if not exists idx_sessions_started_at on sessions(started_at desc);
