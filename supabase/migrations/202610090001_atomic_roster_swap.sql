begin;

-- Serializes edits for one team and enforces eligibility below the UI layer.
create or replace function public.validate_roster_assignment()
returns trigger language plpgsql set search_path = '' as $$
declare kind text; pos text;
begin
  perform 1 from public.fantasy_teams where id = new.team_id for update;
  select slot_type::text into kind from public.roster_slots
    where id = new.slot_id and team_id = new.team_id and owner_id = new.owner_id;
  select position into pos from public.nfl_players where player_id = new.player_id;
  if kind is null or pos is null or not (
    kind = pos or kind in ('SUPERFLEX','BENCH') or
    (kind = 'FLEX' and pos in ('RB','WR','TE'))
  ) then raise exception 'Player is not eligible for this roster slot'; end if;
  new.updated_at := clock_timestamp();
  return new;
end;
$$;
drop trigger if exists roster_assignment_eligibility on public.roster_assignments;
create trigger roster_assignment_eligibility before insert or update on public.roster_assignments
for each row execute function public.validate_roster_assignment();

create or replace function public.swap_roster_players(
  p_team_id uuid, p_first_id uuid, p_first_slot uuid, p_first_player text,
  p_second_id uuid, p_second_slot uuid, p_second_player text
) returns void language plpgsql security invoker set search_path = '' as $$
declare first_row public.roster_assignments; second_row public.roster_assignments;
begin
  if auth.uid() is null then raise exception 'Authentication required'; end if;
  perform 1 from public.fantasy_teams where id = p_team_id and owner_id = auth.uid() for update;
  if not found then raise exception 'Team unavailable'; end if;
  if p_first_id = p_second_id or p_first_slot = p_second_slot then
    raise exception 'Choose two different roster slots';
  end if;
  select * into first_row from public.roster_assignments
    where id = p_first_id and team_id = p_team_id and owner_id = auth.uid() for update;
  if not found or first_row.slot_id <> p_first_slot or first_row.player_id <> p_first_player then
    raise exception 'Roster changed; reload before saving';
  end if;
  select * into second_row from public.roster_assignments
    where id = p_second_id and team_id = p_team_id and owner_id = auth.uid() for update;
  if not found or second_row.slot_id <> p_second_slot or second_row.player_id <> p_second_player then
    raise exception 'Roster changed; reload before saving';
  end if;
  -- Constraints and eligibility are checked in the same transaction.
  -- Any failure restores BOTH assignments, with their original identities.
  delete from public.roster_assignments where id in (p_first_id, p_second_id);
  insert into public.roster_assignments(id,team_id,slot_id,owner_id,player_id,created_at)
    values (first_row.id,p_team_id,second_row.slot_id,auth.uid(),first_row.player_id,first_row.created_at),
           (second_row.id,p_team_id,first_row.slot_id,auth.uid(),second_row.player_id,second_row.created_at);
end;
$$;
revoke all on function public.swap_roster_players(uuid,uuid,uuid,text,uuid,uuid,text) from public, anon;
grant execute on function public.swap_roster_players(uuid,uuid,uuid,text,uuid,uuid,text) to authenticated;
commit;
