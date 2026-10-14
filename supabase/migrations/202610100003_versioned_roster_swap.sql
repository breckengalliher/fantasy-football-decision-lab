begin;

-- The previous seven-argument contract could not distinguish an old display
-- from a roster moved away and then back. Remove it so old clients fail closed.
drop function public.swap_roster_players(uuid,uuid,uuid,text,uuid,uuid,text);

create or replace function public.swap_roster_players(
  p_team_id uuid, p_first_id uuid, p_first_slot uuid, p_first_player text,
  p_second_id uuid, p_second_slot uuid, p_second_player text,
  p_first_updated_at timestamptz, p_second_updated_at timestamptz
) returns void language plpgsql security invoker set search_path = '' as $$
declare first_row public.roster_assignments; second_row public.roster_assignments;
begin
  if auth.uid() is null then raise exception 'Authentication required'; end if;
  if p_first_updated_at is null or p_second_updated_at is null then
    raise exception 'Roster changed; reload before saving';
  end if;
  perform 1 from public.fantasy_teams where id = p_team_id and owner_id = auth.uid() for update;
  if not found then raise exception 'Team unavailable'; end if;
  if p_first_id = p_second_id or p_first_slot = p_second_slot then
    raise exception 'Choose two different roster slots';
  end if;
  select * into first_row from public.roster_assignments
    where id = p_first_id and team_id = p_team_id and owner_id = auth.uid() for update;
  if not found or first_row.slot_id <> p_first_slot or first_row.player_id <> p_first_player
     or first_row.updated_at is distinct from p_first_updated_at then
    raise exception 'Roster changed; reload before saving';
  end if;
  select * into second_row from public.roster_assignments
    where id = p_second_id and team_id = p_team_id and owner_id = auth.uid() for update;
  if not found or second_row.slot_id <> p_second_slot or second_row.player_id <> p_second_player
     or second_row.updated_at is distinct from p_second_updated_at then
    raise exception 'Roster changed; reload before saving';
  end if;
  -- Team lock, owner RLS and eligibility constraints protect both rows in one
  -- transaction. The trigger assigns fresh versions even for a same-state return.
  delete from public.roster_assignments where id in (p_first_id, p_second_id);
  insert into public.roster_assignments(id,team_id,slot_id,owner_id,player_id,created_at)
    values (first_row.id,p_team_id,second_row.slot_id,auth.uid(),first_row.player_id,first_row.created_at),
           (second_row.id,p_team_id,first_row.slot_id,auth.uid(),second_row.player_id,second_row.created_at);
end;
$$;
revoke all on function public.swap_roster_players(uuid,uuid,uuid,text,uuid,uuid,text,timestamptz,timestamptz) from public, anon;
grant execute on function public.swap_roster_players(uuid,uuid,uuid,text,uuid,uuid,text,timestamptz,timestamptz) to authenticated;
notify pgrst, 'reload schema';
commit;
