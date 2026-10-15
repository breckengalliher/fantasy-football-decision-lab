-- QA ONLY: run against deburhwrnuqeyexpezzo. All fixtures roll back.
-- Tests execute as authenticated, not as the dashboard administrator.
create or replace function pg_temp.league_settings_expected(p_id uuid) returns jsonb
language sql as $$
 select jsonb_build_object('league_id',t.league_id::text,'team_name',t.name,
   'league_name',l.name,'passing_td_points',l.passing_td_points,
   'team_updated_at',t.updated_at,'league_updated_at',l.updated_at,
   'slots',coalesce((select jsonb_agg(jsonb_build_object('id',s.id::text,
     'slot_type',s.slot_type::text,'slot_order',s.slot_order,'is_starter',s.is_starter)
     order by s.id) from public.roster_slots s where s.team_id=t.id),'[]'::jsonb))
 from public.fantasy_teams t join public.fantasy_leagues l on l.id=t.league_id where t.id=p_id;
$$;
create or replace function pg_temp.test_league_settings() returns jsonb language plpgsql as $$
declare
 owners uuid[]; a uuid := gen_random_uuid(); b uuid := gen_random_uuid(); c uuid := gen_random_uuid();
 la uuid := gen_random_uuid(); lb uuid := gen_random_uuid(); lc uuid := gen_random_uuid();
 slot uuid := gen_random_uuid(); counts jsonb := '{"QB":1,"RB":0,"WR":0,"TE":0,"FLEX":0,"SUPERFLEX":0,"BENCH":1}';
 expected jsonb; fresh jsonb; other_before jsonb; roster_before jsonb; rows_before jsonb;
 blocked boolean; player text; receipt jsonb;
begin
 select jsonb_build_object('teams',(select jsonb_agg(to_jsonb(t) order by id) from public.fantasy_teams t),
   'leagues',(select jsonb_agg(to_jsonb(t) order by id) from public.fantasy_leagues t),
   'slots',(select jsonb_agg(to_jsonb(t) order by id) from public.roster_slots t),
   'assignments',(select jsonb_agg(to_jsonb(t) order by id) from public.roster_assignments t)) into rows_before;
 begin
   select account_ids into owners from public.sdl_pilot_access_config where singleton and enabled;
   assert cardinality(owners)>=2, 'Requires existing restricted QA pilot';
   select player_id into player from public.nfl_players where position='QB' order by player_id limit 1;
   assert player is not null, 'Requires existing QA player catalog';
   insert into public.fantasy_leagues(id,owner_id,name,season) values
     (la,owners[1],'Settings QA A',2026),(lb,owners[1],'Settings QA B',2026),(lc,owners[2],'Settings QA C',2026);
   insert into public.fantasy_teams(id,league_id,owner_id,name) values
     (a,la,owners[1],'Settings QA A'),(b,lb,owners[1],'Settings QA B'),(c,lc,owners[2],'Settings QA C');
   insert into public.roster_slots(id,team_id,owner_id,slot_type,slot_order,is_starter)
     values(slot,a,owners[1],'QB',0,true);
   insert into public.roster_slots(team_id,owner_id,slot_type,slot_order,is_starter)
     values(a,owners[1],'BENCH',0,false);
   insert into public.roster_assignments(team_id,slot_id,owner_id,player_id) values(a,slot,owners[1],player);
   select jsonb_agg(to_jsonb(x) order by id) into roster_before from public.roster_assignments x where team_id=a;
   other_before := jsonb_build_array(pg_temp.league_settings_expected(b),pg_temp.league_settings_expected(c));
   expected := pg_temp.league_settings_expected(a);
   perform set_config('request.jwt.claim.sub',owners[1]::text,true);
   execute 'set local role authenticated';
   assert current_user='authenticated', 'Test role';
   assert public.save_team_settings(a,'Renamed team','Renamed league',6,counts||'{"BENCH":2}',expected)='{"saved":true}'::jsonb, 'Successful save';
   assert (select name='Renamed team' from public.fantasy_teams where id=a), 'Team name';
   assert (select name='Renamed league' and passing_td_points=6 from public.fantasy_leagues where id=la), 'League scoring';
   assert (select count(*)=3 from public.roster_slots where team_id=a), 'Added empty slot';
   assert (select jsonb_agg(to_jsonb(x) order by id) from public.roster_assignments x where team_id=a)=roster_before, 'Exact lineup retained';
   assert not exists(select 1 from public.fantasy_teams where id=c), 'Foreign-team RLS';
   assert not public.sdl_pilot_team_creation_allowed(), 'Creation restriction retained';
   blocked:=false;
   begin perform public.save_team_settings(a,'stale','stale',4,counts,expected);
   exception when others then blocked:=sqlerrm='Settings changed. Close League Settings and reopen it before saving.'; end;
   assert blocked,'Reject stale settings';
   fresh:=pg_temp.league_settings_expected(a);
   blocked:=false;
   begin perform public.save_team_settings(a,'bad','bad',4,counts||'{"QB":0,"BENCH":4}',fresh);
   exception when others then blocked:=sqlerrm='Occupied roster slots cannot be removed. Move or remove those players first.'; end;
   assert blocked,'Reject occupied shrink';
   assert pg_temp.league_settings_expected(a)=fresh,'Failed save atomic rollback';
   blocked:=false;
   begin perform public.save_team_settings(a,'bad','bad',4,counts||'{"BENCH":21}',fresh);
   exception when others then blocked:=sqlerrm='Invalid league settings. Check names, scoring and roster counts.'; end;
   assert blocked,'Reject invalid counts';
   blocked:=false;
   begin perform public.save_team_settings(c,'foreign','foreign',6,counts,fresh);
   exception when insufficient_privilege then blocked:=true; end;
   assert blocked,'Reject cross-account mutation';
   assert public.save_team_settings(a,'Renamed team','Renamed league',4,counts,fresh)='{"saved":true}'::jsonb,'Reduce empty slots and restore four-point';
   assert (select count(*)=2 from public.roster_slots where team_id=a),'Empty-only removal';
   assert (select jsonb_agg(to_jsonb(x) order by id) from public.roster_assignments x where team_id=a)=roster_before,'Lineup intact after empty removal';
   execute 'reset role';
   assert jsonb_build_array(pg_temp.league_settings_expected(b),pg_temp.league_settings_expected(c))=other_before,'Other teams exact';
   insert into public.fantasy_teams(league_id,owner_id,name) values(la,owners[1],'Shared-league guard fixture');
   perform set_config('request.jwt.claim.sub',owners[1]::text,true);
   execute 'set local role authenticated';
   blocked:=false;
   begin perform public.save_team_settings(a,'shared','shared',6,counts,pg_temp.league_settings_expected(a));
   exception when others then blocked:=sqlerrm='This league is shared by multiple teams. No settings were changed.'; end;
   assert blocked,'Reject shared-league edits';
   execute 'reset role';
   assert not has_function_privilege('anon','public.save_team_settings(uuid,text,text,integer,jsonb,jsonb)','EXECUTE'),'Anonymous denied';
   raise exception 'rollback successful test fixtures' using errcode='ZQA01';
 exception when sqlstate 'ZQA01' then null;
 end;
 assert rows_before=jsonb_build_object('teams',(select jsonb_agg(to_jsonb(t) order by id) from public.fantasy_teams t),
   'leagues',(select jsonb_agg(to_jsonb(t) order by id) from public.fantasy_leagues t),
   'slots',(select jsonb_agg(to_jsonb(t) order by id) from public.roster_slots t),
   'assignments',(select jsonb_agg(to_jsonb(t) order by id) from public.roster_assignments t)), 'All original QA rows unchanged';
 return jsonb_build_object('status','PASS','executed_at',clock_timestamp(),'role','authenticated',
   'checks',jsonb_build_array('owned save','names','4/6 scoring','add empty slots','exact saved lineup',
   'foreign-team RLS','pilot creation guard','stale edit rejection','occupied slot protection','atomic failure rollback',
   'input validation','cross-account mutation denied','empty-only removal','other teams unchanged','shared league guard','anonymous denied','all fixtures rolled back'),
   'production_touched',false);
end;
$$;
select pg_temp.test_league_settings() as qa_league_settings_receipt;
