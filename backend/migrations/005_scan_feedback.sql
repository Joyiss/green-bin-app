create table if not exists public.scan_feedback (
    request_id text primary key,
    item_name text not null,
    location text,
    guidance jsonb not null,
    rating text not null check (rating in ('positive', 'negative')),
    reasons text[] not null default '{}',
    details text,
    submitted_at timestamptz not null default now()
);

alter table public.scan_feedback enable row level security;
revoke all on public.scan_feedback from anon, authenticated;
grant select, insert, update on public.scan_feedback to service_role;

comment on table public.scan_feedback is
    'Result-sheet ratings written only through the server-side feedback endpoint.';
