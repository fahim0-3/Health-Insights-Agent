# Database setup and security verification

## Apply the schema

- For a new Supabase project, run [`script.sql`](script.sql) once in the Supabase SQL Editor.
- For an existing project that already used the previous schema, back up the database and run [`migrations/20260914_batch_2_rls.sql`](migrations/20260914_batch_2_rls.sql) once instead. Do not run both files.
- Then apply [`migrations/20260914_batch_4_persistent_quota.sql`](migrations/20260914_batch_4_persistent_quota.sql) to add the persistent daily analysis limit.

The migration stops if it finds a profile whose ID is not an `auth.users` ID. Resolve any reported orphaned profiles before rerunning it. The app's previous sign-up flow used the Auth user ID for profiles, so a normally created profile should already match.

The schema creates profiles through an `auth.users` trigger, enables row-level security (RLS), revokes anonymous access, and permits an authenticated user to access only their own profile, chat sessions, and the messages belonging to those sessions.

The Batch 4 quota migration adds a UTC daily counter that clients cannot edit directly. Only authenticated calls to the server-side quota functions can reserve or release an analysis slot, which prevents a user from bypassing the daily cap by opening another browser session.

## Verify two-user isolation

Perform this check after applying the SQL, using two ordinary test accounts. Do not use a service-role key for either account.

1. Sign in as **User A**, create an analysis session, and send a message. Record the session ID from the `chat_sessions` table in the Supabase Table Editor.
2. Sign in as **User B** in a separate private browser window. User B's session list must not show User A's session.
3. Using User B's access token, request User A's session through the REST API. The result must be an empty array:

   ```bash
   curl "$SUPABASE_URL/rest/v1/chat_sessions?id=eq.<USER_A_SESSION_ID>" \
     -H "apikey: $SUPABASE_ANON_KEY" \
     -H "Authorization: Bearer <USER_B_ACCESS_TOKEN>"
   ```

4. Repeat against `chat_messages?session_id=eq.<USER_A_SESSION_ID>`; it must also return an empty array.
5. With User B's token, try to create a `chat_sessions` row whose `user_id` is User A's Auth user ID. Supabase must reject it with a row-level-security error.

If any request returns User A's data or accepts the forged `user_id`, stop using the project and review the migration, table grants, and policies before processing health reports.
