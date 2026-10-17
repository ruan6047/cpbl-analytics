-- #316 expand：保留076的單值列／雜湊／不可變守衛，只為新版本加多值契約。
ALTER TABLE cpbl.roster_annotation_revision
    ADD COLUMN IF NOT EXISTS role_format_version SMALLINT NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS tactical_roles TEXT[],
    ADD COLUMN IF NOT EXISTS role_provenance JSONB;

CREATE OR REPLACE FUNCTION cpbl.roster_roles_v2_valid(roles TEXT[], provenance JSONB)
RETURNS boolean LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
    item JSONB;
    source JSONB;
BEGIN
    IF roles IS NULL OR cardinality(roles) = 0 OR array_ndims(roles) <> 1
       OR array_position(roles, NULL) IS NOT NULL
       OR cardinality(roles) <> (SELECT count(DISTINCT r) FROM unnest(roles) r)
       OR NOT roles <@ ARRAY['先發','中繼','終結','勝利組','拆彈組','長中繼',
                              '主力','代打','代跑','守備替補','工具人','替補','指定打擊']::TEXT[]
       OR provenance IS NULL OR jsonb_typeof(provenance) <> 'object' THEN
        RETURN false;
    END IF;
    IF (SELECT count(*) FROM jsonb_object_keys(provenance)) <> 4
       OR NOT provenance ?& ARRAY['approval_table_sha256','approval_manifest_sha256','approval_url','roles']
       OR jsonb_typeof(provenance->'approval_table_sha256') <> 'string'
       OR jsonb_typeof(provenance->'approval_manifest_sha256') <> 'string'
       OR (provenance->>'approval_table_sha256') !~ '^[0-9a-f]{64}$'
       OR (provenance->>'approval_manifest_sha256') !~ '^[0-9a-f]{64}$'
       OR jsonb_typeof(provenance->'approval_url') <> 'string'
       OR (provenance->>'approval_url') !~ '^https://github[.]com/ruan6047/cpbl-analytics/issues/[0-9]+#issuecomment-[0-9]+$'
       OR jsonb_typeof(provenance->'roles') <> 'object' THEN
        RETURN false;
    END IF;
    IF (SELECT count(*) FROM jsonb_object_keys(provenance->'roles')) <> cardinality(roles)
       OR NOT (provenance->'roles') ?& roles THEN RETURN false; END IF;
    FOR source IN SELECT value FROM jsonb_each(provenance->'roles') LOOP
        IF jsonb_typeof(source) <> 'object' THEN RETURN false; END IF;
        IF (SELECT count(*) FROM jsonb_object_keys(source)) <> 4
           OR NOT source ?& ARRAY['origin','source_ids','original_basis','original_evidence']
           OR jsonb_typeof(source->'origin') <> 'string'
           OR (source->>'origin') NOT IN ('human','research')
           OR jsonb_typeof(source->'source_ids') <> 'array'
           OR jsonb_typeof(source->'original_basis') <> 'string'
           OR btrim(source->>'original_basis') = ''
           OR jsonb_typeof(source->'original_evidence') <> 'string'
           OR btrim(source->>'original_evidence') = '' THEN RETURN false; END IF;
        IF jsonb_array_length(source->'source_ids') = 0
           OR jsonb_array_length(source->'source_ids') <>
              (SELECT count(DISTINCT v) FROM jsonb_array_elements(source->'source_ids') v)
           THEN RETURN false; END IF;
        FOR item IN SELECT value FROM jsonb_array_elements(source->'source_ids') LOOP
            IF jsonb_typeof(item) <> 'string' OR btrim(item #>> '{}') = '' THEN RETURN false; END IF;
        END LOOP;
    END LOOP;
    RETURN true;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'cpbl.roster_annotation_revision'::regclass
                   AND conname = 'roster_role_format_v2_check') THEN
        ALTER TABLE cpbl.roster_annotation_revision ADD CONSTRAINT roster_role_format_v2_check CHECK (
            (role_format_version = 1 AND tactical_roles IS NULL AND role_provenance IS NULL)
            OR (role_format_version = 2 AND tactical_role = 'unclassified'
                AND cpbl.roster_roles_v2_valid(tactical_roles, role_provenance) IS TRUE)
        );
    END IF;
END $$;

CREATE OR REPLACE FUNCTION cpbl.check_roster_revision_roles_v2() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    formats INTEGER;
    approvals INTEGER;
    position TEXT;
BEGIN
    SELECT count(DISTINCT role_format_version),
           count(DISTINCT (role_provenance - 'roles'))
      INTO formats, approvals FROM cpbl.roster_annotation_revision
     WHERE roster_id = NEW.roster_id AND revision = NEW.revision;
    IF formats <> 1 OR (NEW.role_format_version = 2 AND approvals <> 1) THEN
        RAISE EXCEPTION '同一角色版本須有相同格式與全表核准來源' USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.role_format_version = 2 THEN
        SELECT official_position INTO position FROM cpbl.series_roster_member
         WHERE roster_id = NEW.roster_id AND player_id = NEW.player_id;
        IF (position = '投手' AND NOT NEW.tactical_roles <@ ARRAY['先發','中繼','終結','勝利組','拆彈組','長中繼']::TEXT[])
           OR (position <> '投手' AND NOT NEW.tactical_roles <@ ARRAY['主力','代打','代跑','守備替補','工具人','替補','指定打擊']::TEXT[]) THEN
            RAISE EXCEPTION 'v2角色與官方守位不相容' USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    RETURN NULL;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgrelid = 'cpbl.roster_annotation_revision'::regclass
                   AND tgname = 'roster_revision_roles_v2_complete') THEN
        CREATE CONSTRAINT TRIGGER roster_revision_roles_v2_complete
            AFTER INSERT ON cpbl.roster_annotation_revision DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION cpbl.check_roster_revision_roles_v2();
    END IF;
END $$;
