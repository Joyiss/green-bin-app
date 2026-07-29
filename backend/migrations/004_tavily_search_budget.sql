create table if not exists public.tavily_search_budget (
    period_type text not null
        check (period_type in ('day', 'month')),
    period_start date not null,
    credit_count bigint not null default 0
        check (credit_count >= 0),
    updated_at timestamptz not null default now(),
    primary key (period_type, period_start)
);

alter table public.tavily_search_budget enable row level security;
revoke all on public.tavily_search_budget from anon, authenticated;
grant select, insert, update, delete on public.tavily_search_budget to service_role;

create or replace function public.reserve_tavily_search_budget(
    p_daily_limit integer,
    p_monthly_limit integer,
    p_now timestamptz default now()
)
returns table (
    allowed boolean,
    daily_count bigint,
    monthly_count bigint,
    daily_reset_at timestamptz,
    monthly_reset_at timestamptz
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
    if p_daily_limit < 1 or p_monthly_limit < 1 then
        raise exception 'Tavily budget limits must be positive.';
    end if;

    -- A transaction-scoped advisory lock makes the check-and-increment atomic
    -- across all backend workers and instances.
    perform pg_advisory_xact_lock(hashtext('green_bin_tavily_search_budget'));

    insert into public.tavily_search_budget (period_type, period_start)
    values ('day', v_day), ('month', v_month)
    on conflict (period_type, period_start) do nothing;

    select credit_count into v_daily_count
      from public.tavily_search_budget
     where period_type = 'day' and period_start = v_day;

    select credit_count into v_monthly_count
      from public.tavily_search_budget
     where period_type = 'month' and period_start = v_month;

    allowed := v_daily_count < p_daily_limit
        and v_monthly_count < p_monthly_limit;

    if allowed then
        update public.tavily_search_budget
           set credit_count = credit_count + 1,
               updated_at = p_now
         where (period_type = 'day' and period_start = v_day)
            or (period_type = 'month' and period_start = v_month);
        v_daily_count := v_daily_count + 1;
        v_monthly_count := v_monthly_count + 1;
    end if;

    daily_count := v_daily_count;
    monthly_count := v_monthly_count;
    daily_reset_at := (v_day + 1)::timestamp at time zone 'UTC';
    monthly_reset_at := (v_month + interval '1 month')::timestamp at time zone 'UTC';
    return next;
end;
$$;

revoke all on function public.reserve_tavily_search_budget(integer, integer, timestamptz)
    from public, anon, authenticated;
grant execute on function public.reserve_tavily_search_budget(integer, integer, timestamptz)
    to service_role;

comment on table public.tavily_search_budget is
    'Atomic daily and monthly Tavily Search credit reservations. Contains no user or request data.';
