"""MCP server entrypoint.

Wires the fo4-mcp tools (6 MVP + follow-on) into a FastMCP server. Each
tool's schema is derived from its function signature; errors are caught at
the boundary and serialized into the standard envelope.

Run via:
    fo4-mcp                   # from installed entrypoint
    python -m fo4_mcp.server  # from source
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from . import (
    ba2_pack,
    compact_formids,
    esl_flag,
    facegen,
    ingame_test,
    lod,
    nif_ops,
    plugin_format,
    previs,
    save_clean,
    save_inspect,
    seq,
    tools,
    voice_bake,
)
from .config import Config, load_config
from .errors import Fo4McpError
from .manifest import Manifest, parse_manifest


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )


def _safe(call) -> dict[str, Any]:
    """Wrap a tool call so Fo4McpError becomes a serialized envelope."""
    try:
        return call()
    except Fo4McpError as e:
        return e.to_dict()


def build_server(cfg: Config | None = None, manifest: Manifest | None = None):
    """Construct the FastMCP server with all tools registered.

    Imported lazily so unit tests can import this module without requiring
    the `mcp` package to be installed.
    """
    from mcp.server.fastmcp import FastMCP  # noqa: PLC0415

    cfg = cfg or load_config()
    manifest = manifest or parse_manifest(cfg.tools_dir / "MANIFEST.md")

    _setup_logging(cfg.log_level)
    log = logging.getLogger(__name__)
    log.info("fo4-mcp starting | repo=%s tools=%s", cfg.repo_root, cfg.tools_dir)
    log.info("manifest: %d tools loaded", len(manifest.tools))
    if cfg.fo4_install_dir is None:
        log.warning("FO4 install not detected — set FO4_INSTALL_DIR in .env")

    mcp = FastMCP("fo4-mcp")

    # Tool 1
    @mcp.tool()
    def fo4_get_environment() -> dict[str, Any]:
        """Report FO4 install path, runtime version, F4SE, MO2 status."""
        return _safe(lambda: tools.fo4_get_environment(cfg))

    # Tool 2
    @mcp.tool()
    def fo4_read_load_order() -> dict[str, Any]:
        """Read combined MO2 active profile + AppData plugins.txt load order."""
        return _safe(lambda: tools.fo4_read_load_order(cfg))

    # Tool 3
    @mcp.tool()
    def fo4_inspect_record(plugin: str, record_id: str) -> dict[str, Any]:
        """Inspect one record (FormID or EditorID) in a plugin via Mutagen."""
        return _safe(lambda: tools.fo4_inspect_record(cfg, manifest, plugin, record_id))

    # Tool 3j — author a new plugin from a record spec; gated output + .bak
    @mcp.tool()
    def fo4_create_record(
        spec: dict[str, Any], output_plugin: str, confirm_overwrite: bool = False
    ) -> dict[str, Any]:
        """Author a new plugin (NPC/Armor/Quest + Keyword/FormList/Message/Global glue
        records + Faction) from a record spec via Mutagen.
        NPCs accept Race/Class FormLinks + factions + W3b full-field (voice/combatStyle/
        defaultOutfit/attackRace/skin FormLinks + aggression/confidence/assistance/
        responsibility/mood AI enums + keywords + inventory[item,count] + perks[perk,rank]
        + W3c template-chain [defaultTemplate FormLink + useTemplateActors flags] for FaceGen inheritance);
        Armors accept keywords + value/
        weight + armor rating + biped body slots; Quests accept type/flags +
        stages (each log entry gets a QSDT marker; runOnStart marks a startup stage) +
        objectives (W2: + flags + QSTA targets — alias-pointed compass markers with
        target flags/LCRT keyword/conditions) + quest-nested dialogue topics (DIAL->INFO->lines) with
        INFO conditions + quest aliases (QuestReferenceAlias: flags/ForcedReference/
        UniqueActor/conditions) + Papyrus VMAD binding (attach scripts by .psc name with
        typed properties) + SCEN scenes (actors by alias ID + phases with conditions +
        a dialogue-action timeline referencing topics) + quest stage script fragments
        (QF fragment script + per-stage Fragment_* entries) + quest alias script
        fragments (per-alias OnBegin/OnEnd scripts bound by alias ID into
        QuestAdapter.Aliases); fragment metadata only, compile the .pex via
        fo4_papyrus_build. Glue records: Keyword (bare KYWD), FormList (FLST item
        FormLinks), Message (MESG text/title), Global (GLOB float|int|short + value),
        Faction (FACT flags + interfaction combat-reaction relations), and leveled
        lists (W3d/W3e: LeveledNpc/LeveledItem — entries[reference/level/count] + calc flags).
        World content (W4): interior Cell (IsInteriorCell + LightingTemplate/location/
        imageSpace/... + nested placed refs — placedObjects[REFR] + placedNpcs[ACHR] with
        base/position/rotation/scale, into Temporary or Persistent; block/subblock auto-
        derived from the FormID). CellOverride (W5, see fo4_place_into_cell). Story Manager
        (W6): smqn (StoryManagerQuestNode — event-driven quest auto-start: parent/
        previousSibling SM-tree links + flags + conditions + quests[{quest, hoursUntilReset}];
        see fo4_inspect_sm_tree to pick the parent).
        FormLinks auto-add their masters.
        Output gated to staging/fixtures; an existing target is backed up to .bak only
        with confirm_overwrite=true."""
        return _safe(lambda: tools.fo4_create_record(
            cfg, manifest, spec, output_plugin, confirm_overwrite=confirm_overwrite))

    # Tool 3k: previs/precombine safety check (Faz 3 / W5 BLOCKING precondition)
    @mcp.tool()
    def fo4_check_previs_safety(cell: str, source_plugin: str | None = None) -> dict[str, Any]:
        """Read-only: is it safe to add/move refs in this cell? Adding a placed ref to a cell
        with precombined geometry/previs invalidates them — the engine keeps the stale meshes,
        so new refs may be invisible + the cell can show holes until previs is REGENERATED in
        the CK (W12). Returns precombine/previs signals + a verdict; safe=True only when the
        cell has neither. cell = FormKey '<6hex>:<master>'; source_plugin defaults to the
        FormKey's master in the FO4 install Data dir."""
        return _safe(lambda: tools.fo4_check_previs_safety(cfg, manifest, cell, source_plugin))

    # Tool 3l: place refs into an existing cell as an override (Faz 3 / W5)
    @mcp.tool()
    def fo4_place_into_cell(
        cell: str,
        output_plugin: str,
        placed_objects: list[dict[str, Any]] | None = None,
        placed_npcs: list[dict[str, Any]] | None = None,
        source_plugin: str | None = None,
        clear_existing: bool = False,
        acknowledge_previs: bool = False,
        confirm_overwrite: bool = False,
    ) -> dict[str, Any]:
        """Add placed refs (REFR placed_objects / ACHR placed_npcs, each {base, position?,
        rotation?, scale?, editorId?, persistent?}) to an EXISTING cell as an override. The
        writer DeepCopies the master cell (lighting/data carry forward — no black cell) and
        ADDITIVELY appends the new refs (clear_existing=False, safe default — keeps the master's
        refs). clear_existing=True WIPES the deep-copied refs (destructive on populated cells; use
        only for empty/new cells). cell = FormKey '<6hex>:<master>'; source_plugin defaults to the
        FormKey's master in the FO4 Data dir. BLOCKING: if the cell is precombined/previs'd this
        REFUSES unless acknowledge_previs=true (refs may be invisible until a CK previs regen,
        W12). Output gated to staging/fixtures; .bak on overwrite."""
        return _safe(lambda: tools.fo4_place_into_cell(
            cfg, manifest, cell, output_plugin,
            placed_objects=placed_objects, placed_npcs=placed_npcs, source_plugin=source_plugin,
            clear_existing=clear_existing, acknowledge_previs=acknowledge_previs,
            confirm_overwrite=confirm_overwrite))

    # Tool 3m: Story Manager tree reader (Faz 3 / W6)
    @mcp.tool()
    def fo4_inspect_sm_tree(plugin: str, node: str | None = None) -> dict[str, Any]:
        """Read-only Story Manager tree reader. Without `node`: lists a plugin's SM EVENT nodes
        (auto-start anchor points) with editorId/formKey/event-type + childCount. With `node`
        (FormKey|EditorID): that node + its direct children. Use it to pick the right Parent
        (+ PreviousSibling) for a new SMQN (`fo4_create_record` type=smqn) — a wrong parent/
        sibling is the silent-fail mode (clean load but the quest never auto-starts). `plugin`
        may be a bare master name (resolved in the FO4 Data dir) or a path."""
        return _safe(lambda: tools.fo4_inspect_sm_tree(cfg, manifest, plugin, node))

    # Tool 3n — Faz 3 / W12: per-cell navmesh CK-handoff checklist (read-only)
    @mcp.tool()
    def fo4_navmesh_handoff(plugin: str) -> dict[str, Any]:
        """Read-only per-cell navmesh checklist for the CK handoff. Classifies every cell:
        interior navmesh authored (+ NAVI) = OK (Mutagen-authored, in-game-pathable since
        A-in-game 2026-06-21); interior without navmesh = agent-authorable gap (add
        navmesh:{floor,divisions}); exterior/worldspace cell = CK-gated (navmesh + neighbour
        stitch must be generated in the Creation Kit). Returns findings + a scoped ck_checklist
        of only the cells that genuinely need the CK. Authors nothing."""
        return _safe(lambda: tools.fo4_navmesh_handoff(cfg, manifest, plugin))

    # Tool 3o — Faz 3 / W12: aggregate ship-readiness preflight (read-only)
    @mcp.tool()
    def fo4_release_preflight(plugin: str) -> dict[str, Any]:
        """Read-only ship-readiness preflight: composes ESL/format eligibility + navmesh handoff
        + per-cell previs impact into ONE verdict (ship-blocked > review > ship-ready) before the
        user-gated CK finalize / BA2 pack / FOMOD steps. Each sub-check degrades to a warning if
        its backend is missing rather than failing the whole preflight. Performs no flag flip,
        compaction, or pack — those stay user-gated."""
        return _safe(lambda: tools.fo4_release_preflight(cfg, manifest, plugin))

    # Tool 3p — Faz 3 / W9: voice/lip recording handoff checklist (read-only)
    @mcp.tool()
    def fo4_voice_handoff(plugin: str, audio_root: str | None = None) -> dict[str, Any]:
        """Read-only voice/lip checklist for the human voice-acting handoff. Walks every dialogue
        response LINE (quest-nested DIAL->INFO->line) and reports the subtitle, speaker, resolved
        voice type, and the canonical .fuz path
        (Sound/Voice/<plugin>/<VoiceType>/<INFO-8hex>_<respNum>.fuz; the .lip is FUZE-packed inside
        the .fuz). Flags each line OK (.fuz present under audio_root) / needs-recording (.fuz
        missing) / voice-type-unresolved. Path embeds the INFO FormID, so run after FormID-lock.
        audio_root defaults to the plugin's directory. Records nothing."""
        return _safe(lambda: tools.fo4_voice_handoff(cfg, manifest, plugin, audio_root))

    # Tool 3j-lint (Faz 3 / W3f)
    @mcp.tool()
    def fo4_lint_npc_template(plugin: str) -> dict[str, Any]:
        """Lint a plugin's NPCs (read-only): orphan UseTemplateActors flags (set without a
        DefaultTemplate = inert, an authoring bug) + a FaceGen bake-coverage list (NPCs with
        own HeadParts/FaceMorphs/FaceTintingLayers that need baked FaceGen via CK/W10 or risk
        dark face, annotated with whether they inherit Traits from a template). Dark-face risk
        is not a verdict — FaceGen assets are external to the plugin."""
        return _safe(lambda: tools.fo4_lint_npc_template(cfg, manifest, plugin))

    # Tool 3b
    @mcp.tool()
    def fo4_check_esl_eligibility(plugin: str) -> dict[str, Any]:
        """Advisory ESL/ESM-flag eligibility for a plugin (new-record count, max
        ObjectID, new cells). Read-only; never writes flags or compacts FormIDs."""
        return _safe(lambda: tools.fo4_check_esl_eligibility(cfg, manifest, plugin))

    # Tool 3f
    @mcp.tool()
    def fo4_backup_saves(label: str | None = None, dest_dir: str | None = None) -> dict[str, Any]:
        """Copy the player's FO4 saves to a timestamped archive under staging/.
        Read-only source; run before any save-breaking op."""
        return _safe(lambda: tools.fo4_backup_saves(cfg, label=label, dest_dir=dest_dir))

    # Tool 3g — read-only save summary (pure-Python .fos parser)
    @mcp.tool()
    def fo4_inspect_save(save_path: str) -> dict[str, Any]:
        """Parse a FO4 .fos save (pure-Python) into a structured summary:
        header (player/level/location/race/exp/filetime), screenshot dims,
        formVersion, gameVersion, and the full + ESL plugin lists. Read-only."""
        return _safe(lambda: save_inspect.fo4_inspect_save(cfg, save_path))

    # Tool 16-A — native .fos changeform cleaner (pure-Python WRITE path; gated)
    @mcp.tool()
    def fo4_clean_save_changeforms(
        save_path: str, output_path: str, plugins: list[str], confirm: bool = False
    ) -> dict[str, Any]:
        """Remove a removed-plugin's orphaned ChangeForms from a FO4 .fos and
        write a cleaned save (pure-Python). Destructive-class: requires explicit
        `plugins` + confirm=True; gated output + .bak. Run fo4_backup_saves first."""
        return _safe(lambda: save_clean.fo4_clean_save_changeforms(
            cfg, save_path, output_path, plugins=plugins, confirm=confirm))

    # Tool 16-B — Papyrus-VM cleaner via headless ReSaver (Apache-2.0) shim; gated
    @mcp.tool()
    def fo4_clean_save_papyrus(
        save_path: str,
        output_path: str,
        mode: str,
        confirm: bool = False,
        accept_unattached_risk: bool = False,
    ) -> dict[str, Any]:
        """Remove orphaned Papyrus-VM elements (undefined script elements or
        unattached instances) from a FO4 .fos, by driving ReSaver's engine
        headlessly (the deep VM graph is NOT reimplemented in Python). mode in
        {undefined, unattached}; unattached is engine-normal in FO4 so it needs
        accept_unattached_risk=True. Destructive-class: confirm=True + gated
        output + ReSaver .bak. Run fo4_backup_saves first. Refuses cleanly if the
        JDK + CleanShim.jar toolchain is not built under tools/."""
        return _safe(lambda: save_clean.fo4_clean_save_papyrus(
            cfg, save_path, output_path, mode=mode,
            confirm=confirm, accept_unattached_risk=accept_unattached_risk))

    # Tool 3e
    @mcp.tool()
    def fo4_ba2_version_patch(
        ba2_path: str, output_path: str, target_version: int = 1
    ) -> dict[str, Any]:
        """Rewrite a BA2 header version (NG v7/v8 -> OG v1) for cross-compat.
        Pure header rewrite; gated output + .bak. No external tool."""
        return _safe(lambda: tools.fo4_ba2_version_patch(
            cfg, ba2_path, output_path, target_version=target_version))

    # Tool A2 — BA2 packer (console BSArch64 wrapper)
    @mcp.tool()
    def fo4_pack_ba2(
        source_dir: str,
        output_ba2: str,
        archive_type: str = "general",
        compress: bool = False,
        multithreaded: bool = True,
        share: bool = False,
    ) -> dict[str, Any]:
        """Pack a Data/-style source folder into a BA2 via console BSArch.
        archive_type "general" (-fo4) or "dds"/"textures" (-fo4dds); -z compress
        is general-only (breaks sounds). Output gated to staging/fixtures + .bak."""
        return _safe(lambda: ba2_pack.fo4_pack_ba2(
            cfg, manifest, source_dir, output_ba2,
            archive_type=archive_type, compress=compress,
            multithreaded=multithreaded, share=share))

    # Tool P1 — CK precombine/previs builder (Creation Kit CLI; CKPE-headless)
    @mcp.tool()
    def fo4_build_previs(
        plugin: str,
        step: str = "precombined",
        filter: str = "clean",
        area: str = "all",
        dry_run: bool = True,
    ) -> dict[str, Any]:
        """Construct (and on dry_run=False, run) Creation Kit precombine/previs
        commands for a plugin. step in {precombined,previs,compress_psg,build_cdx,
        full}; full = [precombined, compress_psg, build_cdx, previs] in order.
        Defaults to dry_run=True (returns argv WITHOUT executing) because a real
        CK run is long, machine-locked, and irreversible (user-triggered)."""
        return _safe(lambda: previs.fo4_build_previs(
            cfg, plugin, step=step, filter=filter, area=area, dry_run=dry_run))

    # Tool P2 — CK FaceGen export (Creation Kit CLI; CKPE-headless, W10)
    @mcp.tool()
    def fo4_build_facegen(plugin: str, target: str = "W32", dry_run: bool = True) -> dict[str, Any]:
        """Construct (and on dry_run=False, run) the Creation Kit FaceGen-export command
        (-ExportFaceGenData:<plugin> <target>; target=W32 PC/X64/XB1/PS4, mandatory — verified
        by a live CK run). Bakes per-NPC face .nif/.dds for NPCs carrying own face data;
        trait-templated NPCs need NO export (scope with fo4_lint_npc_template). Defaults to
        dry_run=True (returns argv WITHOUT executing): a real CK run is machine-locked, needs
        Steam logged in + the GPU, and writes the Data tree (route via MO2 for VFS-safe output)."""
        return _safe(lambda: facegen.fo4_build_facegen(cfg, plugin, target=target, dry_run=dry_run))

    # Tool P3 — silent-subtitled voice (.fuz) baker (LipGen+xWMAEncode+FUZE, W9)
    @mcp.tool()
    def fo4_bake_voice_assets(
        plugin: str, out_root: str | None = None, dry_run: bool = True
    ) -> dict[str, Any]:
        """Bake one SILENT .fuz per dialogue line so the quest is fully playable subtitled (W9 MVP).
        Reads dialogue lines via voice-handoff, then per line: silence WAV -> LipGenerator (.lip) +
        xWMAEncode (.xwm) -> pure-Python FUZE pack -> <out_root>/Sound/Voice/<plugin>/<VoiceType>/
        <INFO-8hex>_<respNum>.fuz. Silent = closed mouth, NOT lip-synced speech. Bake AFTER
        fo4_compact_formids (the .fuz name embeds the INFO FormID). dry_run=True returns the plan;
        False actually bakes. Output gated to staging/ (never the game folder)."""
        return _safe(lambda: voice_bake.fo4_bake_voice_assets(
            cfg, manifest, plugin, out_root=out_root, dry_run=dry_run))

    # Tool P4 — CK SEQ generation (start-game-enabled quest fire; CK CLI via MO2-VFS, W12)
    @mcp.tool()
    def fo4_build_seq(plugin: str, dry_run: bool = True) -> dict[str, Any]:
        """Construct (and on dry_run=False, run via MO2-VFS) the Creation Kit SEQ-generation
        command (-GenerateSEQ:<plugin>). A start-game-enabled quest won't fire on a new game
        without its Data/SEQ/<plugin>.seq — this generates it. Unlike navmesh, SEQ is a scriptable
        CK CLI op. Output lands in the MO2 overwrite (never Steam Data). dry_run=True returns argv;
        a plugin with no start-game-enabled quest produces no .seq (correct, not a failure)."""
        return _safe(lambda: seq.fo4_build_seq(cfg, plugin, dry_run=dry_run))

    # Tool L1 — xLODGen LOD-build command (GUI generation stays user-driven)
    @mcp.tool()
    def fo4_build_lod(
        output_dir: str,
        data_path: str | None = None,
        plugins_path: str | None = None,
        ini_path: str | None = None,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        """Construct (and optionally launch) an xLODGen FO4 LOD-build command.
        xLODGen is a GUI fork of xEdit: -autoload/-autoexit only skip the
        module-select dialog. Worldspace selection + "Build meshes" is
        INTERACTIVE, so this builds + validates the argv and gates the output
        dir (staging/fixtures), returning the command for the user to run
        interactively (e.g. as an MO2 tool). License of xLODGen is UNVERIFIED."""
        return _safe(lambda: lod.fo4_build_lod(
            cfg, output_dir, data_path=data_path, plugins_path=plugins_path,
            ini_path=ini_path, dry_run=dry_run, manifest=manifest))

    # Tool — ESL FormID compaction (SAFE GATING + planning; xEdit GUI action)
    @mcp.tool()
    def fo4_compact_formids(
        plugin: str,
        confirm: bool = False,
        saves_backed_up: bool = False,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        """Gate + plan an ESL "Compact FormIDs for ESL" for one author plugin.
        IRREVERSIBLE + SAVE-BREAKING. Refuses unless confirm=True and
        saves_backed_up=True (run fo4_backup_saves first). dry_run=True (default)
        returns the plan + documented xedit_cmd WITHOUT touching anything; on
        execute it makes a .bak first. A reliable headless xEdit compaction is
        NOT confirmed — the user performs the GUI menu action on the .bak-
        protected plugin."""
        return _safe(lambda: compact_formids.fo4_compact_formids(
            cfg, plugin, confirm=confirm,
            saves_backed_up=saves_backed_up, dry_run=dry_run))

    # Tool 3h — read real ESL/master flags from the TES4 header (read-only)
    @mcp.tool()
    def fo4_read_esl_flag(plugin: str) -> dict[str, Any]:
        """Read a plugin's real light/master flags from its TES4 header.
        Closes the extension-only gap: an ESL-flagged .esp reports light_flagged
        True. Read-only."""
        return _safe(lambda: esl_flag.fo4_read_esl_flag(cfg, plugin))

    # Tool 3i — set/clear the ESL (light master) flag; gated output + .bak
    @mcp.tool()
    def fo4_set_esl_flag(
        plugin: str, output_path: str, enable: bool = True
    ) -> dict[str, Any]:
        """Set/clear the ESL light-master flag, writing a patched copy to a gated
        output (staging/fixtures; never Steam Data/). Warns if not esl-eligible."""
        return _safe(lambda: esl_flag.fo4_set_esl_flag(
            cfg, plugin, output_path, enable=enable))

    # Tool 3k — Faz 3 / W0: plugin-format advisor (read-only). Enforces the locked
    # format law (any new cell/worldspace -> ESM-flagged ESP, never light).
    @mcp.tool()
    def fo4_plan_plugin_format(plugin: str) -> dict[str, Any]:
        """Advise the REQUIRED plugin format for a draft plugin's content and whether
        its current TES4 flags match. Core law: any new cell/worldspace forces an
        ESM-flagged ESP (never light). Read-only; composes fo4_check_esl_eligibility."""
        return _safe(lambda: plugin_format.fo4_plan_plugin_format(cfg, plugin))

    # Tool 3l — Faz 3 / W0: set/clear the ESM master flag (0x0001); gated + .bak.
    @mcp.tool()
    def fo4_set_master_flag(
        plugin: str, output_path: str, enable: bool = True
    ) -> dict[str, Any]:
        """Set/clear the ESM master flag, writing a patched copy to a gated output
        (staging/fixtures; never Steam Data/). Refuses the corruption combo
        (light-flagged + new cells); warns when ESM isn't actually required."""
        return _safe(lambda: plugin_format.fo4_set_master_flag(
            cfg, plugin, output_path, enable=enable))

    # Tool 3d
    @mcp.tool()
    def fo4_lint_engine_config(config_path: str, plugins_dir: str | None = None) -> dict[str, Any]:
        """Lint an Addictol/Buffout engine-config TOML: no-op settings, bad
        scaleform values, and double-patching vs standalone plugins. Read-only."""
        return _safe(lambda: tools.fo4_lint_engine_config(cfg, config_path, plugins_dir=plugins_dir))

    # Tool 3c
    @mcp.tool()
    def fo4_generate_fomod(spec: dict[str, Any], output_dir: str) -> dict[str, Any]:
        """Generate a FOMOD installer (info.xml + ModuleConfig.xml) from a spec.
        Output gated to staging/fixtures. No external tool needed."""
        return _safe(lambda: tools.fo4_generate_fomod(cfg, spec, output_dir))

    # Tool 4a
    @mcp.tool()
    def fo4_spriggit_export(plugin_path: str, output_dir: str) -> dict[str, Any]:
        """Serialize a plugin to YAML/JSON via Spriggit (for git-tracking)."""
        return _safe(lambda: tools.fo4_spriggit_export(cfg, manifest, plugin_path, output_dir))

    # Tool 4b
    @mcp.tool()
    def fo4_spriggit_import(
        source_dir: str, output_plugin: str, confirm_overwrite: bool = False
    ) -> dict[str, Any]:
        """Reconstruct a plugin from Spriggit YAML sources. Diff-gated: an
        existing target is not overwritten unless confirm_overwrite=true."""
        return _safe(lambda: tools.fo4_spriggit_import(
            cfg, manifest, source_dir, output_plugin, confirm_overwrite=confirm_overwrite,
        ))

    # Tool 5
    @mcp.tool()
    def fo4_papyrus_build(source_paths: list[str], output_dir: str) -> dict[str, Any]:
        """Compile Papyrus scripts via Caprica. Handles namespaced quest/topicinfo
        fragments ("Fragments:Quests:QF_<eid>_<fid>"): the namespace root is
        auto-derived for imports and the produced .pex (written to a subdir) is
        reported with a posix relative path that mirrors the VMAD ScriptName
        (':' -> '/') — closing the fo4_create_record fragment-metadata loop."""
        return _safe(lambda: tools.fo4_papyrus_build(cfg, manifest, source_paths, output_dir))

    # Tool 6
    @mcp.tool()
    def fo4_analyze_crash_log(crash_log_path: str) -> dict[str, Any]:
        """Parse a Buffout/Addictol crash log via CLASSIC + FormID->plugin map."""
        return _safe(lambda: tools.fo4_analyze_crash_log(cfg, manifest, crash_log_path))

    # Tool T3 — Faz 2.2b: headless in-game test runner (Tier 3 native F4SE plugin)
    @mcp.tool()
    def fo4_run_ingame_test(spec: dict[str, Any], dry_run: bool = True) -> dict[str, Any]:
        """Drive a headless FO4 in-game test via the proven Tier 3 F4SE runner plugin.
        Renders a job file the plugin reads, launches the game through MO2, waits for
        it to auto-quit (qqq), then judges success by grepping Papyrus.0.log for
        success_pattern (+ reports the plugin's flush-on-write diag trace).
        spec keys: commands (req list[str]; console cmds with {KEY} placeholders),
        resolves ([{key,plugin,form_id}] -> runtime FormID, because FO4 strips
        editorIDs so SetStage-by-EditorID no-ops), save ("quickload" default |
        "mostrecent" | "coc:<cell>"), success_pattern (substring grepped in Papyrus),
        settle_ms/gap_ms/post_ms timings, appear_timeout_s/run_timeout_s.
        dry_run=True (default) returns the rendered job + launch plan WITHOUT writing
        or launching; dry_run=False actually runs the game (long, machine-locked;
        needs Steam logged in or FO4 dies as a ~25MB DRM stub)."""
        return _safe(lambda: ingame_test.fo4_run_ingame_test(cfg, spec, dry_run=dry_run))

    # Tool N1 — PyNifly FO4 export post-processor (collision splice + texture clamp fix)
    @mcp.tool()
    def fo4_postprocess_nif(
        target_nif: str, donor_nif: str, output_nif: str | None = None
    ) -> dict[str, Any]:
        """Repair a PyNifly-exported FO4 nif in one pass: binary-splice the donor's engine-proven
        collision (PyNifly regenerates bhkPhysicsSystem -> crash) AND patch the BSLightingShaderProperty
        texture clamp mode (PyNifly leaves it -1 -> blank Pip-Boy/Inspect preview). donor_nif must share
        the target's block layout (e.g. Money_Prewar.nif). Output gated to staging/fixtures (.bak on
        in-place). Returns the post-fix validation. Run after every PyNifly FO4 flat-MISC export."""
        return _safe(lambda: nif_ops.fo4_postprocess_nif(cfg, target_nif, donor_nif, output_nif))

    # Tool N2 — flat-MISC nif Layer-0 validation gate
    @mcp.tool()
    def fo4_validate_nif(
        nif: str, donor_nif: str | None = None, textures_root: str | None = None
    ) -> dict[str, Any]:
        """Read-only gate for a flat-MISC (coupon/card/note) nif before deploy: collision integrity
        (vs donor size), texture clamp mode == 3, vertex normals+tangents, diffuse texture path, and
        mesh Z thickness (zero-thickness blanks the preview). Pass textures_root (a Data-style root, e.g.
        the mod folder) to also confirm the diffuse .dds exists. Returns ok({ok, issues, info}); ok=False
        means do not ship. Catches the three stacked PyNifly/flat-MISC render bugs."""
        return _safe(lambda: nif_ops.fo4_validate_nif(cfg, nif, donor_nif, textures_root=textures_root))

    return mcp


def main() -> None:
    """Entry point for `fo4-mcp` script."""
    server = build_server()
    server.run()


if __name__ == "__main__":
    main()
