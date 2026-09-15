-- Health Insights Agent: fresh Supabase schema
-- Run this file only for a new project. Existing projects must use the migration
-- in public/db/migrations/20260914_batch_2_rls.sql instead.

-- Each public profile is permanently linked to its Supabase Auth user.
CREATE TABLE public.users (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT NOT NULL UNIQUE,
    name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE public.chat_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    title TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE public.chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES public.chat_sessions(id) ON DELETE CASCADE,
    content TEXT,
    role TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- One row per user tracks the current UTC day's completed/reserved analyses.
-- The application can only access this table through the quota RPCs below.
CREATE TABLE public.analysis_usage (
    user_id UUID PRIMARY KEY REFERENCES public.users(id) ON DELETE CASCADE,
    usage_date DATE NOT NULL DEFAULT ((CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::date),
    analysis_count INTEGER NOT NULL DEFAULT 0 CHECK (analysis_count >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- RLS policies filter sessions by user_id and messages through their session.
CREATE INDEX idx_chat_sessions_user_id ON public.chat_sessions(user_id);
CREATE INDEX idx_chat_messages_session_id ON public.chat_messages(session_id);

-- Create the public profile inside the database whenever Supabase Auth creates a
-- user. This works whether email confirmation is enabled or disabled and prevents
-- the client from choosing another user's profile ID.
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
    INSERT INTO public.users (id, email, name)
    VALUES (
        NEW.id,
        NEW.email,
        NULLIF(NEW.raw_user_meta_data ->> 'name', '')
    )
    ON CONFLICT (id) DO UPDATE
    SET
        email = EXCLUDED.email,
        name = COALESCE(EXCLUDED.name, public.users.name);

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE PROCEDURE public.handle_new_user();

-- No anonymous access. Authenticated users receive only the operations the app
-- needs; RLS below then scopes each operation to the current Auth user.
REVOKE ALL ON TABLE public.users, public.chat_sessions, public.chat_messages, public.analysis_usage
    FROM anon, authenticated;
GRANT SELECT, UPDATE ON TABLE public.users TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.chat_sessions TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.chat_messages TO authenticated;

ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.chat_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.chat_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.analysis_usage ENABLE ROW LEVEL SECURITY;

CREATE POLICY users_select_own
    ON public.users FOR SELECT TO authenticated
    USING ((SELECT auth.uid()) = id);

CREATE POLICY users_update_own
    ON public.users FOR UPDATE TO authenticated
    USING ((SELECT auth.uid()) = id)
    WITH CHECK ((SELECT auth.uid()) = id);

CREATE POLICY chat_sessions_select_own
    ON public.chat_sessions FOR SELECT TO authenticated
    USING ((SELECT auth.uid()) = user_id);

CREATE POLICY chat_sessions_insert_own
    ON public.chat_sessions FOR INSERT TO authenticated
    WITH CHECK ((SELECT auth.uid()) = user_id);

CREATE POLICY chat_sessions_update_own
    ON public.chat_sessions FOR UPDATE TO authenticated
    USING ((SELECT auth.uid()) = user_id)
    WITH CHECK ((SELECT auth.uid()) = user_id);

CREATE POLICY chat_sessions_delete_own
    ON public.chat_sessions FOR DELETE TO authenticated
    USING ((SELECT auth.uid()) = user_id);

CREATE POLICY chat_messages_select_own_session
    ON public.chat_messages FOR SELECT TO authenticated
    USING (
        EXISTS (
            SELECT 1
            FROM public.chat_sessions
            WHERE public.chat_sessions.id = public.chat_messages.session_id
              AND public.chat_sessions.user_id = (SELECT auth.uid())
        )
    );

CREATE POLICY chat_messages_insert_own_session
    ON public.chat_messages FOR INSERT TO authenticated
    WITH CHECK (
        EXISTS (
            SELECT 1
            FROM public.chat_sessions
            WHERE public.chat_sessions.id = public.chat_messages.session_id
              AND public.chat_sessions.user_id = (SELECT auth.uid())
        )
    );

CREATE POLICY chat_messages_update_own_session
    ON public.chat_messages FOR UPDATE TO authenticated
    USING (
        EXISTS (
            SELECT 1
            FROM public.chat_sessions
            WHERE public.chat_sessions.id = public.chat_messages.session_id
              AND public.chat_sessions.user_id = (SELECT auth.uid())
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1
            FROM public.chat_sessions
            WHERE public.chat_sessions.id = public.chat_messages.session_id
              AND public.chat_sessions.user_id = (SELECT auth.uid())
        )
    );

CREATE POLICY chat_messages_delete_own_session
    ON public.chat_messages FOR DELETE TO authenticated
    USING (
        EXISTS (
            SELECT 1
            FROM public.chat_sessions
            WHERE public.chat_sessions.id = public.chat_messages.session_id
              AND public.chat_sessions.user_id = (SELECT auth.uid())
        )
    );

-- Direct access remains revoked, but this policy provides defence in depth for
-- any future narrowly scoped read grant.
CREATE POLICY analysis_usage_select_own
    ON public.analysis_usage FOR SELECT TO authenticated
    USING ((SELECT auth.uid()) = user_id);

-- Quota updates are performed only by these security-definer functions. The
-- reservation function is atomic, so concurrent requests cannot exceed the cap.
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

    SELECT usage.analysis_count
    INTO current_count
    FROM public.analysis_usage AS usage
    WHERE usage.user_id = current_user_id
      AND usage.usage_date = current_day;

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

    SELECT usage.analysis_count
    INTO current_count
    FROM public.analysis_usage AS usage
    WHERE usage.user_id = current_user_id
      AND usage.usage_date = current_day;

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
    WHERE usage.user_id = current_user_id
      AND usage.usage_date = current_day
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
