begin;

create table if not exists public.sleeper_connections (
  team_id uuid primary key,
  owner_id uuid not null references auth.users(id) on delete cascade,
  sleeper_username text not null check (char_length(sleeper_username) between 1 and 50),
  sleeper_user_id text not null,
  sleeper_league_id text not null,
  sleeper_roster_id text,
  league_name text,
  source_team_name text,
  last_successful_sync_at timestamptz,
  last_attempted_sync_at timestamptz,
  sync_status text not null default 'CONNECTED' check (sync_status in ('CONNECTED','SYNCING','UP_TO_DATE','CHANGES_DETECTED','PARTIAL','FAILED','DISCONNECTED')),
  last_source_hash text,
  last_source_snapshot jsonb,
  pending_snapshot jsonb,
  pending_changes jsonb,
  unmatched_players jsonb not null default '[]'::jsonb,
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  foreign key (team_id, owner_id) references public.fantasy_teams(id, owner_id) on delete cascade
);

create table if not exists public.sleeper_sync_history (
  id bigint generated always as identity primary key,
  team_id uuid not null,
  owner_id uuid not null references auth.users(id) on delete cascade,
  attempted_at timestamptz not null default now(),
  completed_at timestamptz,
  status text not null check (status in ('UP_TO_DATE','CHANGES_DETECTED','PARTIAL','FAILED')),
  source_hash text,
  changes jsonb,
  unmatched_players jsonb not null default '[]'::jsonb,
  error_code text,
  foreign key (team_id, owner_id) references public.fantasy_teams(id, owner_id) on delete cascade
);

create table if not exists public.sleeper_player_mappings (
  owner_id uuid not null references auth.users(id) on delete cascade,
  external_player_id text not null,
  player_id text not null references public.nfl_players(player_id),
  confirmed_at timestamptz not null default now(),
  primary key (owner_id, external_player_id)
);

create index if not exists sleeper_connections_owner_idx on public.sleeper_connections(owner_id, updated_at desc);
create index if not exists sleeper_sync_history_team_idx on public.sleeper_sync_history(owner_id, team_id, attempted_at desc);

alter table public.sleeper_connections enable row level security;
alter table public.sleeper_sync_history enable row level security;
alter table public.sleeper_player_mappings enable row level security;

revoke all on table public.sleeper_connections, public.sleeper_sync_history, public.sleeper_player_mappings from anon, authenticated;
grant select, insert, update, delete on public.sleeper_connections, public.sleeper_player_mappings to authenticated;
grant select on public.sleeper_sync_history to authenticated;

create policy sleeper_connections_own on public.sleeper_connections for all to authenticated
  using ((select auth.uid()) = owner_id) with check ((select auth.uid()) = owner_id);
create policy sleeper_sync_history_read_own on public.sleeper_sync_history for select to authenticated
  using ((select auth.uid()) = owner_id);
create policy sleeper_player_mappings_own on public.sleeper_player_mappings for all to authenticated
  using ((select auth.uid()) = owner_id) with check ((select auth.uid()) = owner_id);

create or replace function public.begin_sleeper_sync(p_team_id uuid) returns void
language plpgsql security invoker set search_path = '' as $$
declare v_owner uuid := (select auth.uid());
begin
  update public.sleeper_connections set sync_status = 'SYNCING', last_attempted_sync_at = now(), updated_at = now()
  where team_id = p_team_id and owner_id = v_owner
    and (last_attempted_sync_at is null or last_attempted_sync_at < now() - interval '60 seconds')
    and not (sync_status = 'SYNCING' and last_attempted_sync_at > now() - interval '2 minutes');
  if not found then raise exception 'sync already active or refresh cooldown applies'; end if;
end;
$$;

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

create or replace function public.resolve_sleeper_sync(
  p_team_id uuid,
  p_decision text,
  p_assignments jsonb default '[]'::jsonb
) returns void
language plpgsql security invoker set search_path = '' as $$
declare
  v_owner uuid := (select auth.uid());
  v_connection public.sleeper_connections%rowtype;
  v_row jsonb;
begin
  if p_decision not in ('KEEP_SDL_LINEUP','APPLY_SLEEPER_LINEUP') then raise exception 'invalid sync decision'; end if;
  select * into v_connection from public.sleeper_connections
    where team_id = p_team_id and owner_id = v_owner for update;
  if not found or v_connection.pending_snapshot is null then raise exception 'no pending sync review'; end if;

  if p_decision = 'APPLY_SLEEPER_LINEUP' then
    delete from public.roster_assignments where team_id = p_team_id and owner_id = v_owner;
    for v_row in select value from jsonb_array_elements(coalesce(p_assignments, '[]'::jsonb)) loop
      if not exists (select 1 from public.roster_slots where id = (v_row->>'slot_id')::uuid and team_id = p_team_id and owner_id = v_owner) then
        raise exception 'invalid roster slot';
      end if;
      insert into public.roster_assignments(team_id, slot_id, owner_id, player_id)
      values (p_team_id, (v_row->>'slot_id')::uuid, v_owner, v_row->>'player_id');
    end loop;
  end if;

  update public.sleeper_connections set
    last_source_snapshot = pending_snapshot,
    last_source_hash = pending_snapshot->>'source_hash',
    pending_snapshot = null,
    pending_changes = null,
    sync_status = case when jsonb_array_length(unmatched_players) > 0 then 'PARTIAL' else 'UP_TO_DATE' end,
    updated_at = now()
  where team_id = p_team_id and owner_id = v_owner;
end;
$$;

revoke all on function public.begin_sleeper_sync(uuid) from public;
revoke all on function public.record_sleeper_sync_result(uuid,text,jsonb,jsonb,text) from public;
revoke all on function public.resolve_sleeper_sync(uuid,text,jsonb) from public;
grant execute on function public.begin_sleeper_sync(uuid) to authenticated;
grant execute on function public.record_sleeper_sync_result(uuid,text,jsonb,jsonb,text) to authenticated;
grant execute on function public.resolve_sleeper_sync(uuid,text,jsonb) to authenticated;

commit;
