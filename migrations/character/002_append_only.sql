CREATE FUNCTION reject_immutable_update() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 RAISE EXCEPTION 'append-only character history';
END;
$$;
CREATE TRIGGER ledger_append_only BEFORE UPDATE OR DELETE ON xp_ledger
 FOR EACH ROW EXECUTE FUNCTION reject_immutable_update();
CREATE TRIGGER definitions_immutable BEFORE UPDATE OR DELETE ON definition_publications
 FOR EACH ROW EXECUTE FUNCTION reject_immutable_update();
CREATE TRIGGER fact_history_immutable BEFORE UPDATE OR DELETE ON fact_revisions
 FOR EACH ROW EXECUTE FUNCTION reject_immutable_update();
