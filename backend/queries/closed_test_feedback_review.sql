-- Recognition quality by confidence and source.
select
    recognition_source,
    recognition_confidence_level,
    count(*) filter (where item_correct is not null) as rated_items,
    avg(
        case
            when item_correct is true then 1.0
            when item_correct is false then 0.0
        end
    ) as item_correct_rate,
    count(*) filter (where prediction_changed) as corrected_items
from public.closed_test_feedback
group by recognition_source, recognition_confidence_level
order by recognition_source, recognition_confidence_level;

-- Common recognition corrections.
select original_prediction, corrected_item, count(*) as correction_count
from public.closed_test_feedback
where prediction_changed and corrected_item is not null
group by original_prediction, corrected_item
order by correction_count desc, original_prediction, corrected_item;

-- Guidance quality by generation path and evidence state.
select
    coalesce(c.guidance_source, f.guidance_source) as displayed_guidance_source,
    coalesce(c.final_generation_path, f.final_generation_path) as displayed_generation_path,
    coalesce(c.guidance_confidence_level, f.guidance_confidence_level) as displayed_guidance_confidence,
    coalesce(c.guidance_cache_hit, f.guidance_cache_hit) as displayed_guidance_cache_hit,
    coalesce(c.consistency_guard_triggered, f.consistency_guard_triggered) as displayed_consistency_guard_triggered,
    count(*) filter (where guidance_helpful is not null) as rated_guidance,
    avg(
        case
            when guidance_helpful is true then 1.0
            when guidance_helpful is false then 0.0
        end
    ) as helpful_rate
from public.closed_test_feedback f
left join public.closed_test_correction_context c
    on c.request_id = f.correction_request_id
group by
    displayed_guidance_source,
    displayed_generation_path,
    displayed_guidance_confidence,
    displayed_guidance_cache_hit,
    displayed_consistency_guard_triggered
order by rated_guidance desc;

-- Manual 90-day closed-testing retention cleanup. Review the count before running delete.
select count(*) as rows_older_than_90_days
from public.closed_test_feedback
where created_at < now() - interval '90 days';

-- delete from public.closed_test_feedback
-- where created_at < now() - interval '90 days';
-- Linked correction contexts are removed by ON DELETE CASCADE.
