begin;

-- Restricted pilot members may edit an EXISTING owned team. This narrow RPC
-- does not relax INSERT policies, create teams, or accept an owner from callers.
create or replace function public.save_team_settings(
  p_team_id uuid, p_team_name text, p_league_name text,
  p_passing_td_points integer, p_slot_counts jsonb, p_expected jsonb
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  v_owner uuid := auth.uid();
  v_team public.fantasy_teams;
  v_league public.fantasy_leagues;
  v_slots jsonb;
  v_kind text;
  v_desired integer;
  v_current integer;
  v_occupied integer;
  v_next integer;
  v_remove uuid[];
begin
  if v_owner is null or not public.sdl_pilot_access_allowed() then
    raise exception 'League settings are unavailable for this account.' using errcode = '42501';
  end if;
  select * into v_team from public.fantasy_teams
    where id = p_team_id and owner_id = v_owner for update;
  if not found then
    raise exception 'League settings are unavailable for this account.' using errcode = '42501';
  end if;
  select * into v_league from public.fantasy_leagues
    where id = v_team.league_id and owner_id = v_owner for update;
  if not found then
    raise exception 'League settings are unavailable for this account.' using errcode = '42501';
  end if;
  -- A shared league must not let one team's editor change another team.
  if exists (select 1 from public.fantasy_teams where league_id = v_league.id and id <> p_team_id) then
    raise exception 'This league is shared by multiple teams. No settings were changed.';
  end if;
  if p_team_name is null or char_length(btrim(p_team_name)) not between 1 and 80
    or p_league_name is null or char_length(btrim(p_league_name)) not between 1 and 80
    or p_passing_td_points is null or p_passing_td_points not in (4,6)
    or p_slot_counts is null or jsonb_typeof(p_slot_counts) <> 'object'
    or p_expected is null or jsonb_typeof(p_expected) <> 'object' then
    raise exception 'Invalid league settings. Check names, scoring and roster counts.';
  end if;
  if (select array_agg(k order by k) from jsonb_object_keys(p_slot_counts) k)
     is distinct from array['BENCH','FLEX','QB','RB','SUPERFLEX','TE','WR']::text[] then
    raise exception 'Invalid league settings. Check names, scoring and roster counts.';
  end if;
  for v_kind in select jsonb_object_keys(p_slot_counts) loop
    if jsonb_typeof(p_slot_counts->v_kind) <> 'number'
       or (p_slot_counts->>v_kind) !~ '^(0|[1-9]|1[0-9]|20)$' then
      raise exception 'Invalid league settings. Check names, scoring and roster counts.';
    end if;
  end loop;
  if (select sum(value::integer) from jsonb_each_text(p_slot_counts)) = 0 then
    raise exception 'Invalid league settings. Check names, scoring and roster counts.';
  end if;
  -- Slot locks and the existing team-locking assignment trigger serialize adds
  -- and moves. An occupied slot can never be cascade-deleted by this function.
  perform 1 from public.roster_slots where team_id = p_team_id order by id for update;
  select coalesce(jsonb_agg(jsonb_build_object(
    'id', id::text, 'slot_type', slot_type::text, 'slot_order', slot_order, 'is_starter', is_starter
  ) order by id), '[]'::jsonb) into v_slots from public.roster_slots where team_id = p_team_id;
  if v_team.league_id::text is distinct from p_expected->>'league_id'
    or v_team.name is distinct from p_expected->>'team_name'
    or v_league.name is distinct from p_expected->>'league_name'
    or to_jsonb(v_league.passing_td_points) is distinct from p_expected->'passing_td_points'
    or v_team.updated_at is distinct from (p_expected->>'team_updated_at')::timestamptz
    or v_league.updated_at is distinct from (p_expected->>'league_updated_at')::timestamptz
    or v_slots is distinct from p_expected->'slots' then
    raise exception 'Settings changed. Close League Settings and reopen it before saving.';
  end if;

  -- All checks/writes share one transaction; a failure rolls back every field.
  for v_kind in select jsonb_object_keys(p_slot_counts) loop
    v_desired := (p_slot_counts->>v_kind)::integer;
    select count(*), coalesce(max(slot_order), -1) + 1 into v_current, v_next
      from public.roster_slots where team_id = p_team_id and slot_type::text = v_kind;
    select count(*) into v_occupied from public.roster_slots s
      where s.team_id = p_team_id and s.slot_type::text = v_kind
        and exists(select 1 from public.roster_assignments a where a.slot_id = s.id);
    if v_desired < v_occupied then
      raise exception 'Occupied roster slots cannot be removed. Move or remove those players first.';
    end if;
    if v_desired < v_current then
      select array_agg(id) into v_remove from (
        select s.id from public.roster_slots s
          where s.team_id = p_team_id and s.slot_type::text = v_kind
            and not exists(select 1 from public.roster_assignments a where a.slot_id = s.id)
          order by s.slot_order desc, s.id limit (v_current - v_desired)
      ) empty_slots;
      delete from public.roster_slots where id = any(v_remove) and team_id = p_team_id;
    elsif v_desired > v_current then
      insert into public.roster_slots(team_id,owner_id,slot_type,slot_order,is_starter)
        select p_team_id, v_owner, v_kind::public.roster_slot_type, v_next + n, v_kind <> 'BENCH'
          from generate_series(0, v_desired - v_current - 1) n;
    end if;
  end loop;
  update public.fantasy_leagues
    set name = btrim(p_league_name), passing_td_points = p_passing_td_points, updated_at = clock_timestamp()
    where id = v_league.id and owner_id = v_owner;
  update public.fantasy_teams set name = btrim(p_team_name), updated_at = clock_timestamp()
    where id = p_team_id and owner_id = v_owner;
  return jsonb_build_object('saved', true);
end;
$$;
revoke all on function public.save_team_settings(uuid,text,text,integer,jsonb,jsonb) from public, anon;
grant execute on function public.save_team_settings(uuid,text,text,integer,jsonb,jsonb) to authenticated;
commit;
