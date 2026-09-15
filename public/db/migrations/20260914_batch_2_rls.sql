-- Health Insights Agent: Batch 2 security migration for an existing project.
-- Run once in the Supabase SQL Editor after taking a database backup.
-- The migration aborts if a legacy profile does not map to an auth.users row.

BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM public.users AS profile
        LEFT JOIN auth.users AS auth_user ON auth_user.id = profile.id
        WHERE auth_user.id IS NULL
    ) THEN
        RAISE EXCEPTION
            'Cannot link public.users to auth.users: orphaned profile IDs exist. Resolve them before rerunning this migration.';
    END IF;
END;
$$;

-- Profile IDs must always originate from auth.users, not gen_random_uuid().
ALTER TABLE public.users ALTER COLUMN id DROP DEFAULT;
ALTER TABLE public.users DROP CONSTRAINT IF EXISTS users_id_fkey;
ALTER TABLE public.users
    ADD CONSTRAINT users_id_fkey
    FOREIGN KEY (id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- Delete report data with its parent profile/session when an Auth user is removed.
ALTER TABLE public.chat_sessions DROP CONSTRAINT IF EXISTS chat_sessions_user_id_fkey;
ALTER TABLE public.chat_sessions
    ADD CONSTRAINT chat_sessions_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE public.chat_messages DROP CONSTRAINT IF EXISTS chat_messages_session_id_fkey;
ALTER TABLE public.chat_messages
    ADD CONSTRAINT chat_messages_session_id_fkey
    FOREIGN KEY (session_id) REFERENCES public.chat_sessions(id) ON DELETE CASCADE;

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

DROP POLICY IF EXISTS users_select_own ON public.users;
DROP POLICY IF EXISTS users_update_own ON public.users;
DROP POLICY IF EXISTS chat_sessions_select_own ON public.chat_sessions;
DROP POLICY IF EXISTS chat_sessions_insert_own ON public.chat_sessions;
DROP POLICY IF EXISTS chat_sessions_update_own ON public.chat_sessions;
DROP POLICY IF EXISTS chat_sessions_delete_own ON public.chat_sessions;
DROP POLICY IF EXISTS chat_messages_select_own_session ON public.chat_messages;
DROP POLICY IF EXISTS chat_messages_insert_own_session ON public.chat_messages;
DROP POLICY IF EXISTS chat_messages_update_own_session ON public.chat_messages;
DROP POLICY IF EXISTS chat_messages_delete_own_session ON public.chat_messages;

REVOKE ALL ON TABLE public.users, public.chat_sessions, public.chat_messages
    FROM anon, authenticated;
GRANT SELECT, UPDATE ON TABLE public.users TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.chat_sessions TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.chat_messages TO authenticated;

ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.chat_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.chat_messages ENABLE ROW LEVEL SECURITY;

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

COMMIT;
