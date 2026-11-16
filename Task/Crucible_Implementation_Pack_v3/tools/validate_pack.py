"""Validate this handoff package, not the application/repository it describes.

Default mode uses only the standard library. --full-schema additionally uses an
installed jsonschema validator for the bundled Draft 2020-12 schemas/examples.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import struct
from collections import Counter
from pathlib import Path
from urllib.parse import unquote
from progression_reference import Part, candidate_xp, total_xp
ROOT = Path(__file__).resolve().parents[1]

class PackError(ValueError):
    pass

def require(condition: bool, message: str) -> None:
    if not condition:
        raise PackError(message)

def read(name: str):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))

def check_full_schema() -> dict:
    try:
        from jsonschema import Draft202012Validator, FormatChecker
        from referencing import Registry, Resource
    except ImportError as exc:
        raise PackError("--full-schema requires installed jsonschema and referencing; no schema pass was recorded") from exc
    resources = []
    schemas = {}
    for path in sorted((ROOT / "contracts").glob("*.schema.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        schema = {**schema, "$id": path.as_uri()}
        resources.append((path.as_uri(), Resource.from_contents(schema)))
        schemas[path.name] = schema
    registry = Registry().with_resources(resources)
    for schema_name, example_name in [("event-envelope.schema.json", "attempt-result.example.json"), ("loadout-command.schema.json", "loadout-command.example.json")]:
        validator = Draft202012Validator(schemas[schema_name], registry=registry, format_checker=FormatChecker())
        validator.validate(read("contracts/" + example_name))
    return {"schemas_checked": len(schemas), "examples_validated": 2}

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full-schema", action="store_true")
    args = parser.parse_args()
    # Parse every active JSON. Deliberately ignore historical source documents.
    json_files = [p for p in ROOT.rglob("*.json") if not ({"archive", "qa"} & set(p.relative_to(ROOT).parts))]
    for p in json_files:
        json.loads(p.read_text(encoding="utf-8"))
    cfg = read("data/progression.json")
    require(len(cfg["levels"]) == 60, "Expected 60 levels")
    for level, row in enumerate(cfg["levels"], 1):
        require(row["level"] == level and row["total_xp"] == total_xp(level), f"Wrong threshold {level}")
        require(row["next_level_cost"] == (100 + 16*(level-1) if level < 60 else None), f"Wrong next-level cost {level}")
    catalog = read("data/items.json")
    items = catalog["items"]
    ids = [x["id"] for x in items]
    require(len(ids) == 59 and len(set(ids)) == 59, "Catalog must have 59 unique items")
    require(len(catalog["slots"]) == 9, "Expected 9 selectors")
    require(sum(not x["unlock"]["all"] for x in items) == 7, "Expected 7 starting items")
    require(all(x["grants_xp"] == 0 and not x["auto_equip"] for x in items), "Item XP cycle or auto-equip")
    metrics = {"level", "seals.V", "seals.E", "seals.R", "seals.K", "seals.M", "disciplines_with_V", "disciplines_with_E", "discipline_seal.K", "first_fresh_independent_C_ge_80"}
    for item in items:
        require(item["slot"] in catalog["slots"] or item["kind"] == "relic", f"Unknown slot {item['id']}")
        for clause in item["unlock"]["all"]:
            require(clause["metric"] in metrics and clause["gte"] > 0, f"Bad unlock {item['id']}")
    aliases = read("data/id_aliases.json")["item_id_aliases"]
    require(all(old not in ids and new in ids for old, new in aliases.items()), "Aliases duplicate catalog items or point nowhere")
    for tier in range(6):
        for slot in ("chest", "shoulders", "bracers", "legs"):
            require(f"armor-{tier}-{slot}" in ids, "Missing armor part")
    require(len(read("data/ranks.json")["ranks"]) == 6, "Expected 6 ranks")
    vols = read("data/volumes.json")["volumes"]
    require(len(vols) == 25 and len({v['id'] for v in vols}) == 25, "Expected 25 unique volumes")
    require(Counter(v["discipline_id"] for v in vols) == {d:5 for d in ["LA", "CA", "PR", "DS", "OD"]}, "Volume discipline mapping")
    trials = read("data/trial_blueprints.json")["blueprints"]
    require(len({t["id"] for t in trials}) == 58, "Trial IDs must be unique")
    require(Counter(t["seal"] for t in trials) == {"E":25,"R":25,"K":5,"M":3}, "Incorrect trial counts")
    for trial in trials:
        require(trial["binding_status"] == "unbound", "No real content was supplied; invented binding")
        if trial["seal"] in {"K", "M"}:
            require(sum(trial["weights"]) == 100, "Assessment weights must sum to 100")
    require(read("data/campaign-bindings.template.json")["bindings"] == [], "Template must not pretend to contain real problems")
    art = read("data/art_manifest.json")
    assets = art["assets"]
    art_ids = {a["asset_id"] for a in assets}
    require(len(art_ids) == len(assets) == 45, "Expected 45 unique art targets")
    require(sum(a["source_generation_complete"] for a in assets) == 6, "Exactly 6 completed art sources")
    code_ids = {x["asset_id"] for x in art["code_assets"]}
    require(all(it["asset_id"] in art_ids | code_ids for it in items), "Item references unknown art")
    for asset in assets:
        if asset["source_path"]:
            require((ROOT / asset["source_path"]).is_file(), f"Missing real source {asset['asset_id']}")
        if asset["prompt_file"]:
            require((ROOT / asset["prompt_file"]).is_file(), f"Missing prompt {asset['asset_id']}")
        require(asset["runtime_status"] != "runtime_ready", "No runtime layers were prepared in this handoff")
        require(all(part["path"] is None and part["hide_base_path"] is None for part in asset["representations"].values()), "Invented production asset path")
    sources = read("data/source_assets.json")["assets"]
    require(len(sources) == 7, "Expected 7 actual input images")
    for src in sources:
        data = (ROOT / src["package_path"]).read_bytes()
        require(hashlib.sha256(data).hexdigest() == src["sha256"], f"Source checksum changed: {src['asset_id']}")
        require(data[:8] == b"\x89PNG\r\n\x1a\n", "Invalid PNG signature")
        w,h = struct.unpack(">II", data[16:24])
        require((w,h) == (1024,1536), f"Wrong source canvas {src['asset_id']}")
    mapping = {s["asset_id"]:s["uploaded_filename"] for s in sources}
    require(mapping["ARM-00"] == "Tier_1.png" and mapping["ARM-01"] == "Tier_0.png", "Tier0/1 accidental reversal")
    pi = read("data/prompt_index.json")["prompts"]
    require(len(pi) == 40 and sum(p["kind"] == "art" for p in pi) == 39, "Expected 39 art prompts + 1 technical")
    require(len({p["asset_id"] for p in pi}) == 40, "Duplicate prompt ID")
    all_text = (ROOT / "08_ART_PROMPTS_ALL.md").read_text(encoding="utf-8")
    for prompt in pi:
        text = (ROOT / prompt["file"]).read_text(encoding="utf-8")
        require(text.count("<!-- PROMPT_START -->") == text.count("<!-- PROMPT_END -->") == 1, f"Prompt delimiters {prompt['asset_id']}")
        require("РОВНО ОДНО изображение" in text and "РОВНО ТРИ" not in text, f"Wrong generation count {prompt['asset_id']}")
        require(text in all_text, f"Combined index is stale: {prompt['asset_id']}")
        for reference in prompt["references"]:
            require((ROOT / "references" / reference).is_file(), f"Missing prompt reference {reference}")
    expected_prompts = {a["asset_id"] for a in assets if not a["source_generation_complete"]}
    require(expected_prompts == {p["asset_id"] for p in pi if p["kind"] == "art"}, "Incomplete art prompt coverage")
    rig = read("data/rig.template.json")
    require(all(v is None for v in rig["anchors"].values()), "Unmeasured rig claims actual coordinates")
    visual = read("data/visual_test_cases.json")
    require(len(visual["mixed_outfits"]) == 10 and visual["status"] == "not_run", "Wrong visual QA claims")
    for case in visual["mixed_outfits"]:
        require(all(iid in ids for iid in case["slots"].values()), "Unknown mixed outfit item")
        require(len({v.split('-')[1] for v in case['slots'].values()}) >= 3, "Mix should use at least three sets")
    # Structural example checks; full schema mode below provides formal validation.
    event = read("contracts/attempt-result.example.json")
    require(event["user_id"].startswith("synthetic-"), "Fixture looks like real user data")
    snap = event["payload"]["snapshot"]
    require(candidate_xp(snap["difficulty"], [Part(**p) for p in snap["parts"]]) == 68, "Wrong synthetic example arithmetic")
    cmd = read("contracts/loadout-command.example.json")
    require(set(cmd["slots"]) == set(catalog["slots"]), "Command does not contain all slots")
    for slot, iid in cmd["slots"].items():
        if iid:
            require(next(i for i in items if i['id'] == iid)['slot'] == slot, "Wrong-slot example")
    # Check real local Markdown hyperlinks (not illustrative future repository paths in code).
    links_checked = 0
    for md in ROOT.rglob("*.md"):
        if "archive" in md.relative_to(ROOT).parts:
            continue
        text = md.read_text(encoding="utf-8")
        for url in re.findall(r"\]\(([^)]+)\)", text):
            if url.startswith(("http:", "https:", "#", "mailto:")):
                continue
            target = unquote(url.split('#',1)[0])
            require((md.parent / target).exists(), f"Broken local link: {md.relative_to(ROOT)} -> {target}")
            links_checked += 1
    require(not list(ROOT.rglob("*.ttf")) and not list(ROOT.rglob("*.otf")) and not list(ROOT.rglob("*.woff*")), "Font binaries should not be bundled")
    schema_result = check_full_schema() if args.full_schema else {"status":"not_run; use --full-schema with installed jsonschema"}
    print(json.dumps({"status":"passed","scope":"handoff-package consistency only; not repository integration or visual paper-doll QA","counts":{"levels":60,"items":59,"ranks":6,"volumes":25,"trial_blueprints":58,"art_targets":45,"completed_art_sources":6,"input_png_files":7,"art_prompts":39,"conditional_technical_prompts":1,"local_links_checked":links_checked},"schema_validation":schema_result},ensure_ascii=False,indent=2))

if __name__ == "__main__":
    try:
        main()
    except (PackError, ValueError, KeyError, OSError) as exc:
        raise SystemExit(f"PACK VALIDATION FAILED: {exc}")
