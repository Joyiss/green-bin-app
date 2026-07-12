create table if not exists public.closed_test_feedback (
    id uuid primary key default gen_random_uuid(),
    request_id text not null unique
        check (char_length(request_id) between 1 and 96),
    original_prediction text not null
        check (char_length(original_prediction) between 1 and 200),
    original_status text not null
        check (original_status in ('confident', 'uncertain', 'unknown')),
    recognition_source text,
    recognition_confidence_level text
        check (recognition_confidence_level is null or recognition_confidence_level in ('high', 'medium', 'low', 'unknown')),
    recognition_confidence_score double precision
        check (recognition_confidence_score is null or recognition_confidence_score between 0 and 1),
    recognition_reason_codes text[] not null default '{}',
    recognition_cache_hit boolean not null default false,
    clarification_required boolean not null default false,
    clarification_reason_codes text[] not null default '{}',

    guidance_confidence_level text
        check (guidance_confidence_level is null or guidance_confidence_level in ('high', 'medium', 'low', 'unknown')),
    guidance_confidence_score double precision
        check (guidance_confidence_score is null or guidance_confidence_score between 0 and 1),
    guidance_reason_codes text[] not null default '{}',
    guidance_source text,
    final_action text,
    guidance_cache_hit boolean not null default false,
    retrieved_chunk_ids text[] not null default '{}',
    applicable_chunk_ids text[] not null default '{}',
    conditional_chunk_ids text[] not null default '{}',
    not_applicable_chunk_ids text[] not null default '{}',
    retrieval_reason_codes text[] not null default '{}',
    final_generation_path text,
    consistency_guard_triggered boolean not null default false,
    consistency_reason_codes text[] not null default '{}',

    item_correct boolean,
    guidance_helpful boolean,
    prediction_changed boolean not null default false,
    corrected_item text
        check (corrected_item is null or char_length(corrected_item) between 1 and 200),
    correction_request_id text
        check (correction_request_id is null or char_length(correction_request_id) between 1 and 96),

    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),

    check (
        not prediction_changed
        or (corrected_item is not null and correction_request_id is not null)
    )
);

create index if not exists closed_test_feedback_created_at_idx
    on public.closed_test_feedback (created_at desc);

create or replace function public.set_closed_test_feedback_updated_at()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists closed_test_feedback_updated_at on public.closed_test_feedback;
create trigger closed_test_feedback_updated_at
before update on public.closed_test_feedback
for each row execute function public.set_closed_test_feedback_updated_at();

alter table public.closed_test_feedback enable row level security;
revoke all on public.closed_test_feedback from anon, authenticated;
grant select, insert, update, delete on public.closed_test_feedback to service_role;

comment on table public.closed_test_feedback is
    'Closed-testing prediction diagnostics and optional user feedback. No photos, location, personal information, or raw model content.';

create table if not exists public.closed_test_correction_context (
    request_id text primary key
        check (char_length(request_id) between 1 and 96),
    original_request_id text not null references public.closed_test_feedback(request_id)
        on delete cascade,
    corrected_item text not null
        check (char_length(corrected_item) between 1 and 200),
    guidance_confidence_level text
        check (guidance_confidence_level is null or guidance_confidence_level in ('high', 'medium', 'low', 'unknown')),
    guidance_confidence_score double precision
        check (guidance_confidence_score is null or guidance_confidence_score between 0 and 1),
    guidance_reason_codes text[] not null default '{}',
    guidance_source text,
    final_action text,
    guidance_cache_hit boolean not null default false,
    retrieved_chunk_ids text[] not null default '{}',
    applicable_chunk_ids text[] not null default '{}',
    conditional_chunk_ids text[] not null default '{}',
    not_applicable_chunk_ids text[] not null default '{}',
    retrieval_reason_codes text[] not null default '{}',
    final_generation_path text,
    consistency_guard_triggered boolean not null default false,
    consistency_reason_codes text[] not null default '{}',
    created_at timestamptz not null default now()
);

create index if not exists closed_test_correction_original_request_idx
    on public.closed_test_correction_context (original_request_id);

alter table public.closed_test_correction_context enable row level security;
revoke all on public.closed_test_correction_context from anon, authenticated;
grant select, insert, update, delete on public.closed_test_correction_context to service_role;

comment on table public.closed_test_correction_context is
    'Trusted corrected-prediction guidance context linked to an immutable original closed-test feedback row.';
