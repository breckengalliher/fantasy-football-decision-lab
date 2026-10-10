begin;

-- Operator-managed pilot scope. No account identifiers belong in source.
create table if not exists public.sdl_pilot_access_config (
  singleton boolean primary key default true check (singleton),
  enabled boolean not null default false,
  account_ids uuid[] not null default '{}',
  constraint sdl_pilot_exactly_five_accounts check (
    not enabled or (
      cardinality(account_ids) = 5 and array_ndims(account_ids) = 1
      and array_lower(account_ids, 1) = 1 and array_upper(account_ids, 1) = 5
      and array_position(account_ids, null) is null
      and account_ids[1] <> account_ids[2] and account_ids[1] <> account_ids[3]
      and account_ids[1] <> account_ids[4] and account_ids[1] <> account_ids[5]
      and account_ids[2] <> account_ids[3] and account_ids[2] <> account_ids[4]
      and account_ids[2] <> account_ids[5] and account_ids[3] <> account_ids[4]
      and account_ids[3] <> account_ids[5] and account_ids[4] <> account_ids[5]
    )
  )
);
alter table public.sdl_pilot_access_config enable row level security;
revoke all on public.sdl_pilot_access_config from public, anon, authenticated;
insert into public.sdl_pilot_access_config(singleton) values (true)
on conflict (singleton) do nothing;

-- The definer reads only the private configuration and returns a boolean.
-- Ownership policies still apply; this cannot grant access to somebody's team.
create or replace function public.sdl_pilot_access_allowed()
returns boolean language sql stable security definer set search_path = '' as $$
  select coalesce((select not enabled or auth.uid() = any(account_ids)
    from public.sdl_pilot_access_config where singleton), false);
$$;
create or replace function public.sdl_pilot_team_creation_allowed()
returns boolean language sql stable security definer set search_path = '' as $$
  select coalesce((select not enabled
    from public.sdl_pilot_access_config where singleton), false);
$$;
revoke all on function public.sdl_pilot_access_allowed() from public, anon;
revoke all on function public.sdl_pilot_team_creation_allowed() from public, anon;
grant execute on function public.sdl_pilot_access_allowed() to authenticated;
grant execute on function public.sdl_pilot_team_creation_allowed() to authenticated;

-- Existing definer RPC must also enforce scope before bypassing table RLS.
create or replace function public.record_sleeper_sync_result(
  p_team_id uuid,
  p_status text,
  p_snapshot jsonb default null,
  p_changes jsonb default null,
  p_error_code text default null
) returns void
language plpgsql security definer set search_path = '' as $$
declare
  v_owner uuid := (select auth.uid());
  v_unmatched jsonb := coalesce(p_snapshot->'unmatched', '[]'::jsonb);
  v_hash text := p_snapshot->>'source_hash';
begin
  if not public.sdl_pilot_access_allowed() then raise exception 'Pilot access unavailable'; end if;
  if v_owner is null or not exists (
    select 1 from public.fantasy_teams where id = p_team_id and owner_id = v_owner
  ) then raise exception 'not authorized'; end if;
  if p_status not in ('UP_TO_DATE','CHANGES_DETECTED','PARTIAL','FAILED') then raise exception 'invalid sync status'; end if;

  update public.sleeper_connections
  set last_attempted_sync_at = now(),
      last_successful_sync_at = case when p_status <> 'FAILED' then now() else last_successful_sync_at end,
      sync_status = p_status,
      sleeper_roster_id = coalesce(p_snapshot->>'roster_id', sleeper_roster_id),
      league_name = coalesce(p_snapshot->>'league_name', league_name),
      source_team_name = coalesce(p_snapshot->>'team_name', source_team_name),
      pending_snapshot = case when p_status in ('CHANGES_DETECTED','PARTIAL') then p_snapshot else null end,
      pending_changes = case when p_status in ('CHANGES_DETECTED','PARTIAL') then p_changes else null end,
      unmatched_players = v_unmatched,
      last_source_hash = case when p_status = 'UP_TO_DATE' then v_hash else last_source_hash end,
      last_source_snapshot = case when p_status = 'UP_TO_DATE' then p_snapshot else last_source_snapshot end,
      last_error = p_error_code,
      updated_at = now()
  where team_id = p_team_id and owner_id = v_owner;
  if not found then raise exception 'Sleeper connection not found'; end if;

  insert into public.sleeper_sync_history(team_id, owner_id, completed_at, status, source_hash, changes, unmatched_players, error_code)
  values (p_team_id, v_owner, now(), p_status, v_hash, p_changes, v_unmatched, p_error_code);
  delete from public.sleeper_sync_history h where h.team_id = p_team_id and h.owner_id = v_owner and h.id not in (
    select id from public.sleeper_sync_history where team_id = p_team_id and owner_id = v_owner order by attempted_at desc limit 25
  );
end;
$$;

revoke all on function public.record_sleeper_sync_result(uuid,text,jsonb,jsonb,text) from public, anon;

do $$
declare table_name text;
begin
  foreach table_name in array array[
    'profiles', 'fantasy_leagues', 'fantasy_teams', 'roster_slots',
    'roster_assignments', 'roster_change_log', 'team_preferences',
    'sleeper_connections', 'sleeper_player_mappings', 'sleeper_sync_history'
  ] loop
    execute format('drop policy if exists sdl_pilot_invitation_guard on public.%I', table_name);
    execute format('create policy sdl_pilot_invitation_guard on public.%I as restrictive for all to authenticated using ((select public.sdl_pilot_access_allowed())) with check ((select public.sdl_pilot_access_allowed()))', table_name);
  end loop;
  foreach table_name in array array['fantasy_leagues', 'fantasy_teams', 'roster_slots'] loop
    execute format('drop policy if exists sdl_pilot_creation_guard on public.%I', table_name);
    execute format('create policy sdl_pilot_creation_guard on public.%I as restrictive for insert to authenticated with check ((select public.sdl_pilot_team_creation_allowed()))', table_name);
  end loop;
end;
$$;

commit;
