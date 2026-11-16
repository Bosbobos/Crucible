-- Только disposable БД; рабочий rollback останавливает writer, сохраняя историю.
DROP TABLE IF EXISTS operations,reward_journal,preferences,collection_placements,loadouts,
 item_ownership,seal_state,xp_ledger,xp_entitlements,fact_revisions,source_facts,
 inbox_events,character_profile,definition_publications,command_receipts,source_stream,outbox;
DROP TABLE IF EXISTS campaign_projection,campaign_publications,profile_settings_projection,source_checkpoints;
DROP FUNCTION IF EXISTS reject_immutable_update();
