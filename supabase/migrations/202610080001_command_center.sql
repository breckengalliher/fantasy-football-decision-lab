begin;

create extension if not exists pgcrypto;

create table if not exists public.profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  display_name text check (char_length(display_name) <= 80),
  timezone text not null default 'America/Chicago',
  preferences jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.nfl_players (
  player_id text primary key,
  display_name text not null,
  position text not null check (position in ('QB','RB','WR','TE')),
  current_team text,
  active boolean not null default true,
  source_updated_at timestamptz not null
);

create table if not exists public.fantasy_leagues (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  name text not null check (char_length(name) between 1 and 80),
  season smallint not null check (season between 2020 and 2100),
  scoring_type text not null default 'full_ppr' check (scoring_type = 'full_ppr'),
  passing_td_points smallint not null default 4 check (passing_td_points in (4,6)),
  settings_version smallint not null default 1 check (settings_version > 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.fantasy_teams (
  id uuid primary key default gen_random_uuid(),
  league_id uuid not null references public.fantasy_leagues(id) on delete cascade,
  owner_id uuid not null references auth.users(id) on delete cascade,
  name text not null check (char_length(name) between 1 and 80),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (id, owner_id)
);

create type public.roster_slot_type as enum ('QB','RB','WR','TE','FLEX','SUPERFLEX','BENCH');

create table if not exists public.roster_slots (
  id uuid primary key default gen_random_uuid(),
  team_id uuid not null,
  owner_id uuid not null references auth.users(id) on delete cascade,
  slot_type public.roster_slot_type not null,
  slot_order smallint not null check (slot_order >= 0),
  is_starter boolean not null,
  created_at timestamptz not null default now(),
  unique (team_id, slot_type, slot_order),
  unique (id, team_id, owner_id),
  foreign key (team_id, owner_id) references public.fantasy_teams(id, owner_id) on delete cascade,
  check ((slot_type = 'BENCH' and not is_starter) or (slot_type <> 'BENCH' and is_starter))
);

create table if not exists public.roster_assignments (
  id uuid primary key default gen_random_uuid(),
  team_id uuid not null,
  slot_id uuid not null,
  owner_id uuid not null references auth.users(id) on delete cascade,
  player_id text not null references public.nfl_players(player_id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (slot_id),
  unique (team_id, player_id),
  foreign key (slot_id, team_id, owner_id) references public.roster_slots(id, team_id, owner_id) on delete cascade
);

create table if not exists public.team_preferences (
  team_id uuid primary key,
  owner_id uuid not null references auth.users(id) on delete cascade,
  alert_preferences jsonb not null default '{}'::jsonb,
  last_selected_at timestamptz,
  updated_at timestamptz not null default now(),
  foreign key (team_id, owner_id) references public.fantasy_teams(id, owner_id) on delete cascade
);

create table if not exists public.roster_change_log (
  id bigint generated always as identity primary key,
  team_id uuid not null,
  owner_id uuid not null references auth.users(id) on delete cascade,
  operation text not null check (operation in ('assign','move','replace','remove')),
  slot_id uuid,
  previous_player_id text,
  new_player_id text,
  changed_at timestamptz not null default now(),
  foreign key (team_id, owner_id) references public.fantasy_teams(id, owner_id) on delete cascade
);

create index if not exists fantasy_leagues_owner_idx on public.fantasy_leagues(owner_id, updated_at desc);
create index if not exists fantasy_teams_owner_idx on public.fantasy_teams(owner_id, updated_at desc);
create index if not exists roster_slots_owner_team_idx on public.roster_slots(owner_id, team_id);
create index if not exists roster_assignments_owner_team_idx on public.roster_assignments(owner_id, team_id);
create index if not exists roster_assignments_player_idx on public.roster_assignments(player_id);
create index if not exists roster_change_log_owner_team_idx on public.roster_change_log(owner_id, team_id, changed_at desc);

create or replace function public.validate_team_owner()
returns trigger language plpgsql set search_path = '' as $$
begin
  if not exists (
    select 1 from public.fantasy_leagues l
    where l.id = new.league_id and l.owner_id = new.owner_id
  ) then
    raise exception 'team owner must match league owner';
  end if;
  return new;
end;
$$;

drop trigger if exists fantasy_team_owner_guard on public.fantasy_teams;
create trigger fantasy_team_owner_guard
before insert or update on public.fantasy_teams
for each row execute function public.validate_team_owner();

alter table public.profiles enable row level security;
alter table public.nfl_players enable row level security;
alter table public.fantasy_leagues enable row level security;
alter table public.fantasy_teams enable row level security;
alter table public.roster_slots enable row level security;
alter table public.roster_assignments enable row level security;
alter table public.team_preferences enable row level security;
alter table public.roster_change_log enable row level security;

revoke all on table public.profiles, public.fantasy_leagues, public.fantasy_teams,
  public.roster_slots, public.roster_assignments, public.team_preferences,
  public.roster_change_log from anon, authenticated;
revoke all on table public.nfl_players from anon, authenticated;

grant select, insert, update, delete on public.profiles, public.fantasy_leagues,
  public.fantasy_teams, public.roster_slots, public.roster_assignments,
  public.team_preferences to authenticated;
grant select on public.roster_change_log, public.nfl_players to authenticated;

create policy profiles_select_own on public.profiles for select to authenticated
  using ((select auth.uid()) is not null and (select auth.uid()) = user_id);
create policy profiles_insert_own on public.profiles for insert to authenticated
  with check ((select auth.uid()) is not null and (select auth.uid()) = user_id);
create policy profiles_update_own on public.profiles for update to authenticated
  using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy profiles_delete_own on public.profiles for delete to authenticated
  using ((select auth.uid()) = user_id);

create policy nfl_players_read_authenticated on public.nfl_players for select to authenticated using (true);

create policy leagues_select_own on public.fantasy_leagues for select to authenticated using ((select auth.uid()) = owner_id);
create policy leagues_insert_own on public.fantasy_leagues for insert to authenticated with check ((select auth.uid()) = owner_id);
create policy leagues_update_own on public.fantasy_leagues for update to authenticated using ((select auth.uid()) = owner_id) with check ((select auth.uid()) = owner_id);
create policy leagues_delete_own on public.fantasy_leagues for delete to authenticated using ((select auth.uid()) = owner_id);

create policy teams_select_own on public.fantasy_teams for select to authenticated using ((select auth.uid()) = owner_id);
create policy teams_insert_own on public.fantasy_teams for insert to authenticated with check ((select auth.uid()) = owner_id);
create policy teams_update_own on public.fantasy_teams for update to authenticated using ((select auth.uid()) = owner_id) with check ((select auth.uid()) = owner_id);
create policy teams_delete_own on public.fantasy_teams for delete to authenticated using ((select auth.uid()) = owner_id);

create policy slots_select_own on public.roster_slots for select to authenticated using ((select auth.uid()) = owner_id);
create policy slots_insert_own on public.roster_slots for insert to authenticated with check ((select auth.uid()) = owner_id);
create policy slots_update_own on public.roster_slots for update to authenticated using ((select auth.uid()) = owner_id) with check ((select auth.uid()) = owner_id);
create policy slots_delete_own on public.roster_slots for delete to authenticated using ((select auth.uid()) = owner_id);

create policy assignments_select_own on public.roster_assignments for select to authenticated using ((select auth.uid()) = owner_id);
create policy assignments_insert_own on public.roster_assignments for insert to authenticated with check ((select auth.uid()) = owner_id);
create policy assignments_update_own on public.roster_assignments for update to authenticated using ((select auth.uid()) = owner_id) with check ((select auth.uid()) = owner_id);
create policy assignments_delete_own on public.roster_assignments for delete to authenticated using ((select auth.uid()) = owner_id);

create policy preferences_select_own on public.team_preferences for select to authenticated using ((select auth.uid()) = owner_id);
create policy preferences_insert_own on public.team_preferences for insert to authenticated with check ((select auth.uid()) = owner_id);
create policy preferences_update_own on public.team_preferences for update to authenticated using ((select auth.uid()) = owner_id) with check ((select auth.uid()) = owner_id);
create policy preferences_delete_own on public.team_preferences for delete to authenticated using ((select auth.uid()) = owner_id);

create policy roster_log_select_own on public.roster_change_log for select to authenticated using ((select auth.uid()) = owner_id);

commit;
