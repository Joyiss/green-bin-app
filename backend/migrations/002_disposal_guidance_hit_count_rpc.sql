create or replace function public.increment_disposal_guidance_hit_count(row_id uuid)
returns void
language sql
security definer
set search_path = public
as $$
    update public.disposal_guidance
       set hit_count = coalesce(hit_count, 0) + 1,
           last_used_at = now()
     where id = row_id;
$$;
