-- Health Insights Agent: Batch 4 persistent daily quota migration.
-- Run once after the Batch 2 schema migration (or after the original fresh
-- schema) in the Supabase SQL Editor. It does not alter report/chat records.

BEGIN;

CREATE TABLE IF NOT EXISTS public.analysis_usage (
    user_id UUID PRIMARY KEY REFERENCES public.users(id) ON DELETE CASCADE,
    usage_date DATE NOT NULL DEFAULT ((CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::date),
    analysis_count INTEGER NOT NULL DEFAULT 0 CHECK (analysis_count >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

REVOKE ALL ON TABLE public.analysis_usage FROM anon, authenticated;
ALTER TABLE public.analysis_usage ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS analysis_usage_select_own ON public.analysis_usage;
CREATE POLICY analysis_usage_select_own
    ON public.analysis_usage FOR SELECT TO authenticated
    USING ((SELECT auth.uid()) = user_id);

CREATE OR REPLACE FUNCTION public.get_analysis_quota(limit_value INTEGER)
RETURNS TABLE(used_count INTEGER, remaining INTEGER, resets_on DATE)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    current_user_id UUID := auth.uid();
    current_day DATE := (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::date;
    current_count INTEGER := 0;
BEGIN
    IF current_user_id IS NULL THEN
        RAISE EXCEPTION 'Authentication is required.';
    END IF;
    IF limit_value < 1 THEN
        RAISE EXCEPTION 'The daily analysis limit must be positive.';
    END IF;

    SELECT usage.analysis_count INTO current_count
    FROM public.analysis_usage AS usage
    WHERE usage.user_id = current_user_id AND usage.usage_date = current_day;

    current_count := COALESCE(current_count, 0);
    RETURN QUERY SELECT current_count, GREATEST(limit_value - current_count, 0), current_day + 1;
END;
$$;

CREATE OR REPLACE FUNCTION public.reserve_analysis_quota(limit_value INTEGER)
RETURNS TABLE(allowed BOOLEAN, used_count INTEGER, remaining INTEGER, resets_on DATE)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    current_user_id UUID := auth.uid();
    current_day DATE := (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::date;
    current_count INTEGER;
BEGIN
    IF current_user_id IS NULL THEN
        RAISE EXCEPTION 'Authentication is required.';
    END IF;
    IF limit_value < 1 THEN
        RAISE EXCEPTION 'The daily analysis limit must be positive.';
    END IF;

    INSERT INTO public.analysis_usage (user_id, usage_date, analysis_count)
    VALUES (current_user_id, current_day, 1)
    ON CONFLICT (user_id) DO UPDATE
    SET
        usage_date = EXCLUDED.usage_date,
        analysis_count = CASE
            WHEN public.analysis_usage.usage_date = current_day
                THEN public.analysis_usage.analysis_count + 1
            ELSE 1
        END,
        updated_at = CURRENT_TIMESTAMP
    WHERE public.analysis_usage.usage_date <> current_day
       OR public.analysis_usage.analysis_count < limit_value
    RETURNING analysis_count INTO current_count;

    IF FOUND THEN
        RETURN QUERY SELECT TRUE, current_count, GREATEST(limit_value - current_count, 0), current_day + 1;
        RETURN;
    END IF;

    SELECT usage.analysis_count INTO current_count
    FROM public.analysis_usage AS usage
    WHERE usage.user_id = current_user_id AND usage.usage_date = current_day;

    current_count := COALESCE(current_count, limit_value);
    RETURN QUERY SELECT FALSE, current_count, 0, current_day + 1;
END;
$$;

CREATE OR REPLACE FUNCTION public.release_analysis_quota()
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    current_user_id UUID := auth.uid();
    current_day DATE := (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::date;
    current_count INTEGER := 0;
BEGIN
    IF current_user_id IS NULL THEN
        RAISE EXCEPTION 'Authentication is required.';
    END IF;

    UPDATE public.analysis_usage AS usage
    SET analysis_count = GREATEST(usage.analysis_count - 1, 0),
        updated_at = CURRENT_TIMESTAMP
    WHERE usage.user_id = current_user_id AND usage.usage_date = current_day
    RETURNING usage.analysis_count INTO current_count;

    RETURN COALESCE(current_count, 0);
END;
$$;

REVOKE ALL ON FUNCTION public.get_analysis_quota(INTEGER) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.reserve_analysis_quota(INTEGER) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.release_analysis_quota() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.get_analysis_quota(INTEGER) TO authenticated;
GRANT EXECUTE ON FUNCTION public.reserve_analysis_quota(INTEGER) TO authenticated;
GRANT EXECUTE ON FUNCTION public.release_analysis_quota() TO authenticated;

COMMIT;
