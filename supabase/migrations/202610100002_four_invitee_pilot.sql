begin;

-- Preserve the existing five-account QA scope and all ownership policies.
-- Production will use four operator-selected existing accounts only after approval.
alter table public.sdl_pilot_access_config
  drop constraint sdl_pilot_exactly_five_accounts;
alter table public.sdl_pilot_access_config
  add constraint sdl_pilot_four_or_five_accounts check (
    not enabled or coalesce((
      cardinality(account_ids) in (4, 5) and array_ndims(account_ids) = 1
      and array_lower(account_ids, 1) = 1
      and array_upper(account_ids, 1) = cardinality(account_ids)
      and array_position(account_ids, null) is null
      and account_ids[1] <> account_ids[2] and account_ids[1] <> account_ids[3]
      and account_ids[1] <> account_ids[4] and account_ids[2] <> account_ids[3]
      and account_ids[2] <> account_ids[4] and account_ids[3] <> account_ids[4]
      and (cardinality(account_ids) = 4 or (
        account_ids[1] <> account_ids[5] and account_ids[2] <> account_ids[5]
        and account_ids[3] <> account_ids[5] and account_ids[4] <> account_ids[5]
      ))
    ), false)
  );

commit;
