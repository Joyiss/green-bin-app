create extension if not exists pgcrypto with schema extensions;

create or replace function public.normalize_service_provider_field(p_value text)
returns text
language sql
immutable
security invoker
set search_path = pg_catalog, public
as $$
    select lower(regexp_replace(btrim(coalesce(p_value, '')), '\s+', ' ', 'g'));
$$;

revoke all on function public.normalize_service_provider_field(text)
    from public, anon, authenticated;
grant execute on function public.normalize_service_provider_field(text)
    to service_role;

create table if not exists public.service_providers (
    id uuid primary key default gen_random_uuid(),
    client_id_hash text not null
        check (client_id_hash ~ '^[0-9a-f]{64}$'),
    canonical_name text not null check (char_length(btrim(canonical_name)) between 1 and 200),
    raw_input_name text not null check (char_length(btrim(raw_input_name)) between 1 and 200),
    services jsonb not null default '[]'::jsonb check (jsonb_typeof(services) = 'array'),
    city text not null check (char_length(btrim(city)) between 1 and 120),
    state text not null check (char_length(btrim(state)) between 1 and 120),
    county text check (county is null or char_length(btrim(county)) between 1 and 120),
    status text not null check (status in ('verified', 'not_verified', 'uncertain')),
    evidence_urls jsonb not null default '[]'::jsonb
        check (jsonb_typeof(evidence_urls) = 'array'),
    verified_at timestamptz not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists service_providers_client_id_hash_idx
    on public.service_providers (client_id_hash);

create index if not exists service_providers_normalized_lookup_idx
    on public.service_providers (
        public.normalize_service_provider_field(canonical_name),
        public.normalize_service_provider_field(city),
        public.normalize_service_provider_field(state),
        public.normalize_service_provider_field(county)
    );

create unique index if not exists service_providers_client_provider_location_uidx
    on public.service_providers (
        client_id_hash,
        public.normalize_service_provider_field(canonical_name),
        public.normalize_service_provider_field(city),
        public.normalize_service_provider_field(state),
        coalesce(public.normalize_service_provider_field(county), '')
    );

create table if not exists public.service_provider_verification_cache (
    id uuid primary key default gen_random_uuid(),
    cache_key text not null unique check (cache_key ~ '^[0-9a-f]{64}$'),
    normalized_input_name text not null check (normalized_input_name <> ''),
    normalized_city text not null check (normalized_city <> ''),
    normalized_state text not null check (normalized_state <> ''),
    normalized_county text not null default '',
    result jsonb not null check (jsonb_typeof(result) = 'object'),
    created_at timestamptz not null default now(),
    expires_at timestamptz not null,
    updated_at timestamptz not null default now(),
    check (expires_at > created_at)
);

create index if not exists service_provider_verification_cache_expires_idx
    on public.service_provider_verification_cache (expires_at);

create table if not exists public.service_provider_limit_state (
    client_id_hash text primary key check (client_id_hash ~ '^[0-9a-f]{64}$'),
    consecutive_failures integer not null default 0 check (consecutive_failures between 0 and 3),
    failure_cooldown_until timestamptz,
    last_successful_confirmation_at timestamptz,
    last_confirmed_input_key text,
    last_confirmed_provider_key text,
    in_flight_key text,
    in_flight_until timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create or replace function public.set_service_provider_updated_at()
returns trigger
language plpgsql
security invoker
set search_path = pg_catalog, public
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists service_providers_updated_at on public.service_providers;
create trigger service_providers_updated_at
before update on public.service_providers
for each row execute function public.set_service_provider_updated_at();

drop trigger if exists service_provider_verification_cache_updated_at
    on public.service_provider_verification_cache;
create trigger service_provider_verification_cache_updated_at
before update on public.service_provider_verification_cache
for each row execute function public.set_service_provider_updated_at();

create or replace function public.reserve_service_provider_verification(
    p_client_id_hash text,
    p_provider_key text,
    p_now timestamptz default now()
)
returns table (allowed boolean, cooldown_reason text, retry_at timestamptz)
language plpgsql
security invoker
set search_path = pg_catalog, public
as $$
declare
    v_state public.service_provider_limit_state%rowtype;
begin
    if p_client_id_hash is null or p_client_id_hash !~ '^[0-9a-f]{64}$' then
        raise exception 'A valid client_id_hash is required.';
    end if;
    if p_provider_key is null or btrim(p_provider_key) = '' then
        raise exception 'A provider key is required.';
    end if;
    if p_now is null then raise exception 'p_now is required.'; end if;

    perform pg_advisory_xact_lock(hashtextextended(p_client_id_hash, 7001));
    insert into public.service_provider_limit_state (client_id_hash)
    values (p_client_id_hash)
    on conflict (client_id_hash) do nothing;

    select * into v_state from public.service_provider_limit_state
     where client_id_hash = p_client_id_hash for update;

    if v_state.failure_cooldown_until is not null
       and v_state.failure_cooldown_until <= p_now then
        update public.service_provider_limit_state
           set consecutive_failures = 0, failure_cooldown_until = null, updated_at = p_now
         where client_id_hash = p_client_id_hash;
        v_state.consecutive_failures := 0;
        v_state.failure_cooldown_until := null;
    end if;

    if v_state.failure_cooldown_until > p_now then
        return query select false, 'failed_attempts'::text, v_state.failure_cooldown_until;
        return;
    end if;

    if v_state.last_successful_confirmation_at is not null
       and v_state.last_successful_confirmation_at + interval '24 hours' > p_now
       and p_provider_key is distinct from v_state.last_confirmed_input_key
       and p_provider_key is distinct from v_state.last_confirmed_provider_key then
        return query select false, 'successful_confirmation'::text,
            v_state.last_successful_confirmation_at + interval '24 hours';
        return;
    end if;

    if v_state.in_flight_until > p_now then
        return query select false, 'verification_in_progress'::text, v_state.in_flight_until;
        return;
    end if;

    update public.service_provider_limit_state
       set in_flight_key = p_provider_key,
           in_flight_until = p_now + interval '2 minutes',
           updated_at = p_now
     where client_id_hash = p_client_id_hash;
    return query select true, null::text, null::timestamptz;
end;
$$;

create or replace function public.finalize_service_provider_verification(
    p_client_id_hash text,
    p_provider_key text,
    p_status text,
    p_now timestamptz default now()
)
returns table (cooldown_reason text, retry_at timestamptz)
language plpgsql
security invoker
set search_path = pg_catalog, public
as $$
declare v_failures integer;
begin
    if p_client_id_hash is null or p_client_id_hash !~ '^[0-9a-f]{64}$' then
        raise exception 'A valid client_id_hash is required.';
    end if;
    if p_provider_key is null or btrim(p_provider_key) = '' then
        raise exception 'A provider key is required.';
    end if;
    if p_status not in ('verified', 'not_verified', 'uncertain') then
        raise exception 'A valid status is required.';
    end if;
    if p_now is null then raise exception 'p_now is required.'; end if;

    perform pg_advisory_xact_lock(hashtextextended(p_client_id_hash, 7001));
    if not exists (
        select 1 from public.service_provider_limit_state
         where client_id_hash = p_client_id_hash and in_flight_key = p_provider_key
    ) then raise exception 'No matching verification reservation.'; end if;

    if p_status = 'verified' then
        update public.service_provider_limit_state
           set consecutive_failures = 0, failure_cooldown_until = null,
               in_flight_key = null, in_flight_until = null, updated_at = p_now
         where client_id_hash = p_client_id_hash;
        return query select null::text, null::timestamptz;
        return;
    end if;

    select least(consecutive_failures + 1, 3) into v_failures
      from public.service_provider_limit_state where client_id_hash = p_client_id_hash;
    update public.service_provider_limit_state
       set consecutive_failures = v_failures,
           failure_cooldown_until = case when v_failures >= 3 then p_now + interval '24 hours' else null end,
           in_flight_key = null, in_flight_until = null, updated_at = p_now
     where client_id_hash = p_client_id_hash;
    return query select
        case when v_failures >= 3 then 'failed_attempts'::text else null::text end,
        case when v_failures >= 3 then p_now + interval '24 hours' else null::timestamptz end;
end;
$$;

create or replace function public.release_service_provider_verification(
    p_client_id_hash text,
    p_provider_key text,
    p_now timestamptz default now()
)
returns void
language plpgsql
security invoker
set search_path = pg_catalog, public
as $$
begin
    if p_client_id_hash is null or p_client_id_hash !~ '^[0-9a-f]{64}$' then
        raise exception 'A valid client_id_hash is required.';
    end if;
    if p_provider_key is null or btrim(p_provider_key) = '' then
        raise exception 'A provider key is required.';
    end if;
    if p_now is null then raise exception 'p_now is required.'; end if;
    perform pg_advisory_xact_lock(hashtextextended(p_client_id_hash, 7001));
    update public.service_provider_limit_state
       set in_flight_key = null, in_flight_until = null, updated_at = p_now
     where client_id_hash = p_client_id_hash and in_flight_key = p_provider_key;
end;
$$;

create or replace function public.confirm_service_provider(
    p_client_id_hash text,
    p_verification_id uuid,
    p_raw_input_name text,
    p_now timestamptz default now()
)
returns table (allowed boolean, cooldown_reason text, retry_at timestamptz, provider jsonb)
language plpgsql
security invoker
set search_path = pg_catalog, public
as $$
declare
    v_cache public.service_provider_verification_cache%rowtype;
    v_state public.service_provider_limit_state%rowtype;
    v_provider public.service_providers%rowtype;
    v_provider_key text;
    v_input_key text;
    v_county text;
    v_is_same boolean;
begin
    if p_client_id_hash is null or p_client_id_hash !~ '^[0-9a-f]{64}$' then
        raise exception 'A valid client_id_hash is required.';
    end if;
    if p_verification_id is null then raise exception 'A verification id is required.'; end if;
    if public.normalize_service_provider_field(p_raw_input_name) = '' then
        raise exception 'A raw provider name is required.';
    end if;
    if p_now is null then raise exception 'p_now is required.'; end if;

    perform pg_advisory_xact_lock(hashtextextended(p_client_id_hash, 7001));
    select * into v_cache from public.service_provider_verification_cache
     where id = p_verification_id and expires_at > p_now for update;
    if not found then raise exception 'Verification is missing or expired.'; end if;
    if public.normalize_service_provider_field(p_raw_input_name) <> v_cache.normalized_input_name then
        raise exception 'Verification input does not match.';
    end if;
    if v_cache.result->>'status' <> 'verified' or v_cache.result->>'match' <> 'confirmed' then
        raise exception 'Only a verified provider can be confirmed.';
    end if;

    v_county := nullif(v_cache.normalized_county, '');
    v_provider_key := encode(extensions.digest(concat_ws(E'\x1f',
        public.normalize_service_provider_field(v_cache.result->>'name'),
        v_cache.normalized_city, v_cache.normalized_county, v_cache.normalized_state
    ), 'sha256'), 'hex');
    v_input_key := encode(extensions.digest(concat_ws(E'\x1f',
        v_cache.normalized_input_name, v_cache.normalized_city,
        v_cache.normalized_county, v_cache.normalized_state
    ), 'sha256'), 'hex');

    insert into public.service_provider_limit_state (client_id_hash)
    values (p_client_id_hash) on conflict (client_id_hash) do nothing;
    select * into v_state from public.service_provider_limit_state
     where client_id_hash = p_client_id_hash for update;
    v_is_same := v_provider_key is not distinct from v_state.last_confirmed_provider_key;

    if v_state.failure_cooldown_until > p_now then
        return query select false, 'failed_attempts'::text,
            v_state.failure_cooldown_until, null::jsonb;
        return;
    end if;
    if v_state.last_successful_confirmation_at is not null
       and v_state.last_successful_confirmation_at + interval '24 hours' > p_now
       and not v_is_same then
        return query select false, 'successful_confirmation'::text,
            v_state.last_successful_confirmation_at + interval '24 hours', null::jsonb;
        return;
    end if;

    update public.service_providers
       set raw_input_name = btrim(p_raw_input_name),
           services = v_cache.result->'services',
           status = v_cache.result->>'status',
           evidence_urls = coalesce((select jsonb_agg(item->>'url') from jsonb_array_elements(v_cache.result->'evidence') item), '[]'::jsonb),
           verified_at = p_now,
           updated_at = p_now
     where client_id_hash = p_client_id_hash
       and public.normalize_service_provider_field(canonical_name) = public.normalize_service_provider_field(v_cache.result->>'name')
       and public.normalize_service_provider_field(city) = v_cache.normalized_city
       and public.normalize_service_provider_field(state) = v_cache.normalized_state
       and public.normalize_service_provider_field(county) = v_cache.normalized_county
     returning * into v_provider;

    if not found then
        insert into public.service_providers (
            client_id_hash, canonical_name, raw_input_name, services,
            city, state, county, status, evidence_urls, verified_at
        ) values (
            p_client_id_hash, v_cache.result->>'name', btrim(p_raw_input_name),
            v_cache.result->'services', v_cache.normalized_city, v_cache.normalized_state,
            v_county, v_cache.result->>'status',
            coalesce((select jsonb_agg(item->>'url') from jsonb_array_elements(v_cache.result->'evidence') item), '[]'::jsonb),
            p_now
        ) returning * into v_provider;
    end if;

    update public.service_provider_limit_state
       set consecutive_failures = 0, failure_cooldown_until = null,
           last_successful_confirmation_at = case when v_is_same then last_successful_confirmation_at else p_now end,
           last_confirmed_input_key = v_input_key,
           last_confirmed_provider_key = v_provider_key,
           updated_at = p_now
     where client_id_hash = p_client_id_hash;
    return query select true, null::text, null::timestamptz, to_jsonb(v_provider);
end;
$$;

alter table public.service_providers enable row level security;
alter table public.service_provider_verification_cache enable row level security;
alter table public.service_provider_limit_state enable row level security;

revoke all on public.service_providers from public, anon, authenticated;
revoke all on public.service_provider_verification_cache from public, anon, authenticated;
revoke all on public.service_provider_limit_state from public, anon, authenticated;
grant select, insert, update, delete on public.service_providers to service_role;
grant select, insert, update, delete on public.service_provider_verification_cache to service_role;
grant select, insert, update, delete on public.service_provider_limit_state to service_role;

revoke all on function public.set_service_provider_updated_at() from public, anon, authenticated;
revoke all on function public.reserve_service_provider_verification(text, text, timestamptz) from public, anon, authenticated;
revoke all on function public.finalize_service_provider_verification(text, text, text, timestamptz) from public, anon, authenticated;
revoke all on function public.release_service_provider_verification(text, text, timestamptz) from public, anon, authenticated;
revoke all on function public.confirm_service_provider(text, uuid, text, timestamptz) from public, anon, authenticated;
grant execute on function public.set_service_provider_updated_at() to service_role;
grant execute on function public.reserve_service_provider_verification(text, text, timestamptz) to service_role;
grant execute on function public.finalize_service_provider_verification(text, text, text, timestamptz) to service_role;
grant execute on function public.release_service_provider_verification(text, text, timestamptz) to service_role;
grant execute on function public.confirm_service_provider(text, uuid, text, timestamptz) to service_role;

do $$
declare v_signature text;
begin
    foreach v_signature in array array[
        'public.reserve_service_provider_verification(text,text,timestamp with time zone)',
        'public.finalize_service_provider_verification(text,text,text,timestamp with time zone)',
        'public.release_service_provider_verification(text,text,timestamp with time zone)',
        'public.confirm_service_provider(text,uuid,text,timestamp with time zone)'
    ] loop
        if exists (
            select 1
              from pg_catalog.pg_proc p
              cross join lateral pg_catalog.aclexplode(
                  coalesce(p.proacl, pg_catalog.acldefault('f', p.proowner))
              ) acl
             where p.oid = v_signature::regprocedure
               and acl.grantee = 0
               and acl.privilege_type = 'EXECUTE'
        ) or has_function_privilege('anon', v_signature, 'EXECUTE')
           or has_function_privilege('authenticated', v_signature, 'EXECUTE') then
            raise exception 'Restricted role can execute %', v_signature;
        end if;
        if not has_function_privilege('service_role', v_signature, 'EXECUTE') then
            raise exception 'service_role cannot execute %', v_signature;
        end if;
    end loop;
    if exists (
        select 1
          from pg_catalog.pg_class c
          cross join lateral pg_catalog.aclexplode(
              coalesce(c.relacl, pg_catalog.acldefault('r', c.relowner))
          ) acl
         where c.oid = 'public.service_providers'::regclass
           and acl.grantee = 0
           and acl.privilege_type = 'SELECT'
    ) or has_table_privilege('anon', 'public.service_providers', 'SELECT')
       or has_table_privilege('authenticated', 'public.service_providers', 'SELECT')
       or not has_table_privilege('service_role', 'public.service_providers', 'SELECT') then
        raise exception 'service_providers grants are invalid';
    end if;
end;
$$;
