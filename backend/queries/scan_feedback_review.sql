-- Closed-testing result feedback summary. This table contains no scan images,
-- coordinates, installation IDs, or other direct user identifiers.
select
    rating,
    count(*) as submission_count
from public.scan_feedback
group by rating
order by rating;

select
    reason,
    count(*) as selection_count
from public.scan_feedback,
unnest(reasons) as reason
group by reason
order by selection_count desc, reason;
