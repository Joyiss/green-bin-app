create table if not exists public.scan_usage_daily (
    client_id_hash text not null,
    usage_date date not null,
    scan_count integer not null default 0 check (scan_count >= 0),
    updated_at timestamptz not null default now(),
    primary key (client_id_hash, usage_date)
);

create unique index if not exists scan_usage_daily_client_date_idx
    on public.scan_usage_daily (client_id_hash, usage_date);

alter table public.scan_usage_daily enable row level security;
revoke all on public.scan_usage_daily from anon, authenticated;
grant select, insert, update, delete on public.scan_usage_daily to service_role;

create or replace function public.reserve_scan_usage(
    p_client_id_hash text,
    p_daily_limit integer,
    p_monthly_limit integer,
    p_now timestamptz default now()
)
returns table (
    allowed boolean,
    limit_period text,
    daily_count bigint,
    monthly_count bigint
)
language plpgsql
security definer
set search_path = public
as $$
declare
    v_day date := (p_now at time zone 'UTC')::date;
    v_month date := date_trunc('month', p_now at time zone 'UTC')::date;
    v_daily_count bigint;
    v_monthly_count bigint;
begin
    if p_client_id_hash is null or btrim(p_client_id_hash) = '' then
        raise exception 'A scan client hash is required.';
    end if;
    if p_daily_limit < 1 or p_monthly_limit < 1 then
        raise exception 'Scan limits must be positive.';
    end if;

    -- Serialize reservations for this user across every backend worker/instance.
    perform pg_advisory_xact_lock(hashtextextended(p_client_id_hash, 0));

    insert into public.scan_usage_daily (
        client_id_hash,
        usage_date,
        scan_count,
        updated_at
    )
    values (p_client_id_hash, v_day, 0, p_now)
    on conflict (client_id_hash, usage_date) do nothing;

    select scan_count into v_daily_count
      from public.scan_usage_daily
     where client_id_hash = p_client_id_hash
       and usage_date = v_day;

    select coalesce(sum(scan_count), 0) into v_monthly_count
      from public.scan_usage_daily
     where client_id_hash = p_client_id_hash
       and usage_date >= v_month
       and usage_date < (v_month + interval '1 month')::date;

    if v_daily_count >= p_daily_limit then
        allowed := false;
        limit_period := 'daily';
    elsif v_monthly_count >= p_monthly_limit then
        allowed := false;
        limit_period := 'monthly';
    else
        update public.scan_usage_daily
           set scan_count = scan_count + 1,
               updated_at = p_now
         where client_id_hash = p_client_id_hash
           and usage_date = v_day;
        v_daily_count := v_daily_count + 1;
        v_monthly_count := v_monthly_count + 1;
        allowed := true;
        limit_period := null;
    end if;

    daily_count := v_daily_count;
    monthly_count := v_monthly_count;
    return next;
end;
$$;

revoke all on function public.reserve_scan_usage(text, integer, integer, timestamptz)
    from public, anon, authenticated;
grant execute on function public.reserve_scan_usage(text, integer, integer, timestamptz)
    to service_role;

comment on function public.reserve_scan_usage(text, integer, integer, timestamptz) is
    'Atomically validates daily/monthly per-user scan limits and counts one accepted scan.';
