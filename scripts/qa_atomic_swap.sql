-- Run after the migration inside a transaction; always ROLLBACK.
select set_config('request.jwt.claim.sub', (select owner_id::text from public.fantasy_teams where name = 'QA Journey — disposable' limit 1), true);
set local role authenticated;
do $$
declare team uuid; a public.roster_assignments; b public.roster_assignments;
  w public.roster_assignments; snapshot jsonb; after_snapshot jsonb;
begin
  select id into team from public.fantasy_teams where name = 'QA Journey — disposable';
  if team is null then raise exception 'Dedicated QA team missing'; end if;
  select r.* into a from public.roster_assignments r join public.roster_slots s on s.id=r.slot_id
    where r.team_id=team and s.slot_type='QB';
  select r.* into b from public.roster_assignments r join public.roster_slots s on s.id=r.slot_id
    join public.nfl_players p on p.player_id=r.player_id
    where r.team_id=team and s.slot_type='BENCH' and p.position='QB' limit 1;
  select r.* into w from public.roster_assignments r join public.roster_slots s on s.id=r.slot_id
    where r.team_id=team and s.slot_type='WR' limit 1;
  if a.id is null or b.id is null or w.id is null then raise exception 'QA roster incomplete'; end if;
  perform public.swap_roster_players(team,a.id,a.slot_id,a.player_id,b.id,b.slot_id,b.player_id);
  if not exists(select 1 from public.roster_assignments where id=a.id and slot_id=b.slot_id and player_id=a.player_id)
     or not exists(select 1 from public.roster_assignments where id=b.id and slot_id=a.slot_id and player_id=b.player_id)
     then raise exception 'Valid swap lost assignments'; end if;
  begin
    perform public.swap_roster_players(team,a.id,a.slot_id,a.player_id,b.id,b.slot_id,b.player_id);
    raise exception 'Stale swap accepted';
  exception when others then
    if sqlerrm = 'Stale swap accepted' then raise; end if;
    if sqlerrm <> 'Roster changed; reload before saving' then raise; end if;
  end;
  select jsonb_agg(to_jsonb(r) order by id) into snapshot from public.roster_assignments r where team_id=team;
  begin
    perform public.swap_roster_players(team,b.id,a.slot_id,b.player_id,w.id,w.slot_id,w.player_id);
    raise exception 'Invalid position accepted';
  exception when others then
    if sqlerrm = 'Invalid position accepted' then raise; end if;
    if sqlerrm <> 'Player is not eligible for this roster slot' then raise; end if;
  end;
  select jsonb_agg(to_jsonb(r) order by id) into after_snapshot from public.roster_assignments r where team_id=team;
  if snapshot is distinct from after_snapshot then raise exception 'Failed swap changed roster'; end if;
end;
$$;
select 'PASS: valid swap, stale edit rejected, invalid-position rollback preserves exact roster' as result;
select set_config('request.jwt.claim.sub','00000000-0000-0000-0000-000000000001',true);
do $$ begin
  if exists(select 1 from public.fantasy_teams) or exists(select 1 from public.roster_assignments) then
    raise exception 'Cross-user RLS isolation failed';
  end if;
end $$;
select 'PASS: other identity cannot read teams or assignments' as result;
rollback;
