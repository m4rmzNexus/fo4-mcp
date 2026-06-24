// mutagen-cli — record-scoped lookup for fo4_inspect_record.
//
// Streams a plugin's records with a binary overlay (lazy, read-only) and stops
// at the first match, so a single-record query never materializes the whole
// plugin. The perf win over the Spriggit-serialize backend is structural: no
// temp-dir write, no whole-tree YAML, break-on-first-match.
//
//   mutagen-cli --plugin <path> --record <FormID|EditorID>
//
// stdout: one JSON object. stderr: errors only.
// exit 0 = found, 1 = not found, 2 = bad args / load error.
//
// GPL-3.0 (Mutagen.Bethesda) — subprocess-only, gitignored, never distributed.

using System.Text.Json;
using Loqui;
using Mutagen.Bethesda;
using Mutagen.Bethesda.Fallout4;
using Mutagen.Bethesda.Plugins;
using Mutagen.Bethesda.Plugins.Records;

// ---- subcommand dispatch: "create" writes a new plugin; "lint-npc" streams NPC
// template/FaceGen flags; default = single-record query ----
if (args.Length > 0 && args[0] == "create")
    return RunCreate(args);
if (args.Length > 0 && args[0] == "lint-npc")
    return RunLintNpc(args);
if (args.Length > 0 && args[0] == "cell-info")
    return RunCellInfo(args);
if (args.Length > 0 && args[0] == "sm-tree")
    return RunSmTree(args);
if (args.Length > 0 && args[0] == "navmesh-dump")
    return RunNavmeshDump(args);
if (args.Length > 0 && args[0] == "navi-dump")
    return RunNaviDump(args);
if (args.Length > 0 && args[0] == "cell-navmesh-list")
    return RunCellNavmeshList(args);
if (args.Length > 0 && args[0] == "package-dump")
    return RunPackageDump(args);
if (args.Length > 0 && args[0] == "voice-handoff")
    return RunVoiceHandoff(args);
if (args.Length > 0 && args[0] == "exterior-navmesh-spike")
    return RunExteriorNavmeshSpike(args);
if (args.Length > 0 && args[0] == "lvli-find")
    return RunLvliFind(args);
if (args.Length > 0 && args[0] == "dialogue-dump")
    return RunDialogueDump(args);

// ---- lvli-find (loot-injection target discovery): stream a plugin's LeveledItems and report
// every LVLI whose Entries reference a target FormKey (e.g. which lists distribute SugarBombs).
// The reverse lookup the leveledItemOverride writer needs to pick an injection point. Read-only.
//   mutagen-cli lvli-find --plugin <path> --contains <6hex:master> [--max N]
static int RunLvliFind(string[] argv)
{
    string? pluginPath = null, contains = null;
    int max = 50;
    for (int i = 1; i + 1 < argv.Length; i += 2)
    {
        switch (argv[i])
        {
            case "--plugin": pluginPath = argv[i + 1]; break;
            case "--contains": contains = argv[i + 1]; break;
            case "--max": int.TryParse(argv[i + 1], out max); break;
        }
    }
    if (pluginPath is null || contains is null)
    { Console.Error.WriteLine("lvli-find: --plugin and --contains required"); return 2; }
    if (!FormKey.TryFactory(contains, out var targetKey))
    { Console.Error.WriteLine($"lvli-find: bad FormKey '{contains}'"); return 2; }
    var mod = Fallout4Mod.CreateFromBinaryOverlay(new ModPath(pluginPath), Fallout4Release.Fallout4);
    var hits = new List<Dictionary<string, object?>>();
    foreach (var lvli in mod.LeveledItems)
    {
        var n = lvli.Entries?.Count(e => e.Data?.Reference.FormKey == targetKey) ?? 0;
        if (n > 0)
        {
            hits.Add(new Dictionary<string, object?>
            {
                ["formKey"] = lvli.FormKey.ToString(),
                ["editorId"] = lvli.EditorID,
                ["entryCount"] = lvli.Entries?.Count ?? 0,
                ["targetEntries"] = n,
            });
            if (hits.Count >= max) break;
        }
    }
    Console.Out.Write(JsonSerializer.Serialize(new { contains, count = hits.Count, lists = hits }));
    return 0;
}

// ---- navi-dump (A-in-game RE, ground-truth): summarize the NAVI (NavigationMeshInfoMap) record's
// first few MapInfo entries so we can compare a CK-finalized vanilla NAVI against our authored one
// (parent type, island geometry presence, linked-doors / merged-to). Read-only. ----
static int RunNaviDump(string[] argv)
{
    string? pluginPath = null;
    int max = 3;
    for (int i = 1; i + 1 < argv.Length; i += 2)
        switch (argv[i])
        {
            case "--plugin": pluginPath = argv[i + 1]; break;
            case "--max": int.TryParse(argv[i + 1], out max); break;
            default: return Fail($"unknown arg: {argv[i]}");
        }
    if (string.IsNullOrWhiteSpace(pluginPath)) return Fail("usage: mutagen-cli navi-dump --plugin <path> [--max N]");
    if (!File.Exists(pluginPath)) return Fail($"plugin not found: {pluginPath}");
    try
    {
        var mod = Fallout4Mod.CreateFromBinaryOverlay(new ModPath(pluginPath), Fallout4Release.Fallout4);
        var maps = new List<object>();
        foreach (var navi in mod.NavigationMeshInfoMaps)
        {
            var infos = new List<object>();
            foreach (var mi in navi.MapInfos)
            {
                infos.Add(new
                {
                    navm = mi.NavigationMesh.FormKey.ToString(),
                    parentType = mi.Parent?.GetType().Name,
                    islandMin = mi.Island?.Min.ToString(),
                    islandMax = mi.Island?.Max.ToString(),
                    islandVerts = mi.Island?.Vertices.Count ?? 0,
                    islandTris = mi.Island?.Triangles.Count ?? 0,
                    point = mi.Point.ToString(),
                    unknown = mi.Unknown,
                    unknown2 = mi.Unknown2,
                    unknownFloat = mi.UnknownFloat,
                    linkedDoors = mi.LinkedDoors.Count,
                    mergedTo = mi.MergedTo.Count,
                    preferredMerges = mi.PreferredMerges.Count,
                });
                if (infos.Count >= max) break;
            }
            maps.Add(new
            {
                navi = navi.FormKey.ToString(),
                navMeshVersion = navi.NavMeshVersion,
                mapInfoCount = navi.MapInfos.Count,
                hasNvsi = navi.NVSI != null,
                preferredPathingSets = navi.PreferredPathing?.NavmeshSets.Count ?? 0,
                preferredPathingTree = navi.PreferredPathing?.NavmeshTree.Count ?? 0,
                sampleInfos = infos,
            });
        }
        Console.Out.Write(JsonSerializer.Serialize(new { count = maps.Count, navis = maps }));
        return maps.Count > 0 ? 0 : 1;
    }
    catch (Exception e) { return Fail($"load error: {e.Message}"); }
}

// ---- package-dump (W7-Data support / RE ground-truth): dump a PACK record's Data input map
// (the sbyte index -> {name, type, value} dictionary that the template defines) + PackageTemplate
// + ProcedureType so the writer can resolve data inputs by NAME against a vanilla template. ----
static int RunPackageDump(string[] argv)
{
    string? pluginPath = null;
    string? record = null;
    for (int i = 1; i + 1 < argv.Length; i += 2)
        switch (argv[i])
        {
            case "--plugin": pluginPath = argv[i + 1]; break;
            case "--record": record = argv[i + 1]; break;
            default: return Fail($"unknown arg: {argv[i]}");
        }
    if (string.IsNullOrWhiteSpace(pluginPath) || string.IsNullOrWhiteSpace(record))
        return Fail("usage: mutagen-cli package-dump --plugin <path> --record <FormID|EditorID>");
    if (!File.Exists(pluginPath)) return Fail($"plugin not found: {pluginPath}");
    try
    {
        var mod = Fallout4Mod.CreateFromBinaryOverlay(new ModPath(pluginPath), Fallout4Release.Fallout4);
        // list mode: --record *travel* -> editorIds containing the substring (RE discovery)
        if (record.StartsWith('*') && record.EndsWith('*') && record.Length > 2)
        {
            string needle = record.Trim('*');
            var matches = mod.Packages
                .Where(p => p.EditorID is { } e && e.Contains(needle, StringComparison.OrdinalIgnoreCase))
                .Take(40)
                .Select(p => new { formKey = p.FormKey.ToString(), editorId = p.EditorID,
                    template = p.PackageTemplate.FormKeyNullable?.ToString(), inputs = p.Data.Count })
                .ToList();
            Console.Out.Write(JsonSerializer.Serialize(new { count = matches.Count, packages = matches }));
            return 0;
        }
        uint? wantId = NormFormId(record);
        string wantEd = record.Trim();
        IPackageGetter? pkg = mod.Packages.FirstOrDefault(p =>
            (wantId is { } w && p.FormKey.ID == w) ||
            string.Equals(p.EditorID, wantEd, StringComparison.OrdinalIgnoreCase));
        if (pkg is null) { Console.Out.Write("{\"found\":false}"); return 1; }
        var inputs = new List<object>();
        foreach (var kv in pkg.Data)
        {
            var d = kv.Value;
            inputs.Add(new
            {
                index = (int)kv.Key,
                name = d.Name,
                type = d.GetType().Name,
                flags = d.Flags?.ToString(),
            });
        }
        Console.Out.Write(JsonSerializer.Serialize(new
        {
            found = true,
            formKey = pkg.FormKey.ToString(),
            editorId = pkg.EditorID,
            packageTemplate = pkg.PackageTemplate.FormKeyNullable?.ToString(),
            dataInputVersion = pkg.DataInputVersion,
            procedureBranches = pkg.ProcedureTree?.Count ?? 0,
            inputCount = inputs.Count,
            inputs,
        }));
        return 0;
    }
    catch (Exception e) { return Fail($"load error: {e.Message}"); }
}

// ---- voice-handoff (W9 voice support): enumerate EVERY dialogue response LINE in the plugin
// (quest-nested + top-level DIAL->INFO->line) and emit the per-line .fuz the human voice/TTS step
// must produce + the canonical on-disk path. The .lip is packed INTO the .fuz (FUZE container), so
// one .fuz per line is the deliverable. The voice-type FOLDER comes from the speaker NPC's Voice
// (INFO.Speaker -> Npc.Voice -> VoiceType.EditorID); resolved across the plugin itself or, with
// --masters-dir, the masters that own the speaker/voicetype. FormID-encoded path => run after
// FormID-lock. Read-only. ----
static int RunVoiceHandoff(string[] argv)
{
    string? pluginPath = null;
    string? mastersDir = null;
    for (int i = 1; i + 1 < argv.Length; i += 2)
        switch (argv[i])
        {
            case "--plugin": pluginPath = argv[i + 1]; break;
            case "--masters-dir": mastersDir = argv[i + 1]; break;
            default: return Fail($"unknown arg: {argv[i]}");
        }
    if (string.IsNullOrWhiteSpace(pluginPath))
        return Fail("usage: mutagen-cli voice-handoff --plugin <path> [--masters-dir <dir>]");
    if (!File.Exists(pluginPath)) return Fail($"plugin not found: {pluginPath}");
    try
    {
        var mod = Fallout4Mod.CreateFromBinaryOverlay(new ModPath(pluginPath), Fallout4Release.Fallout4);
        string pluginName = Path.GetFileName(pluginPath);

        // lazy mod cache: resolve a speaker NPC + its voice type across the plugin / masters.
        var cache = new Dictionary<string, IFallout4ModGetter?>();
        IFallout4ModGetter? OpenMod(ModKey mk)
        {
            string key = mk.ToString();
            if (cache.TryGetValue(key, out var c)) return c;
            IFallout4ModGetter? m = null;
            if (mk == mod.ModKey) m = mod;
            else if (!string.IsNullOrWhiteSpace(mastersDir))
            {
                string p = Path.Combine(mastersDir, key);
                if (File.Exists(p))
                    try { m = Fallout4Mod.CreateFromBinaryOverlay(new ModPath(p), Fallout4Release.Fallout4); }
                    catch { m = null; }
            }
            cache[key] = m;
            return m;
        }
        string? VoiceTypeOf(IFormLinkNullableGetter<INpcGetter> speaker)
        {
            if (speaker.FormKeyNullable is not { } sk) return null;
            var npc = OpenMod(sk.ModKey)?.Npcs.FirstOrDefault(n => n.FormKey == sk);
            if (npc is null || npc.Voice.FormKeyNullable is not { } vk) return null;
            return OpenMod(vk.ModKey)?.VoiceTypes.FirstOrDefault(v => v.FormKey == vk)?.EditorID;
        }

        var lines = new List<object>();
        // FO4 DIALs are quest-nested only (no mod-level DialogTopics group, unlike Skyrim).
        void Walk(IEnumerable<IDialogTopicGetter> topics)
        {
            foreach (var dt in topics)
                foreach (var info in dt.Responses)
                {
                    string? vt = VoiceTypeOf(info.Speaker);
                    string info8 = info.FormKey.ID.ToString("X8");
                    foreach (var r in info.Responses)
                        lines.Add(new
                        {
                            dialog = dt.FormKey.ToString(),
                            info = info.FormKey.ToString(),
                            responseNumber = (int)r.ResponseNumber,
                            text = r.Text?.String,
                            speaker = info.Speaker.FormKeyNullable?.ToString(),
                            voiceType = vt,
                            fuzPath = $"Sound/Voice/{pluginName}/{vt ?? "<VoiceType>"}/{info8}_{r.ResponseNumber}.fuz",
                            voiceTypeResolved = vt != null,
                        });
                }
        }
        foreach (var q in mod.Quests) Walk(q.DialogTopics);

        Console.Out.Write(JsonSerializer.Serialize(new { count = lines.Count, plugin = pluginName, lines }));
        return 0;
    }
    catch (Exception e) { return Fail($"load error: {e.Message}"); }
}

// ---- exterior-navmesh-spike (W12-RE feasibility): can the WRITER construct a NEW isolated
// WORLDSPACE + exterior cell + a WorldspaceNavmeshParent navmesh + a worldspace-parent NAVI
// override, and round-trip it on disk? This is the disk half of the exterior-navmesh RE thesis
// (the in-game half reuses the proven F4SE displacement harness). Ground-truth (navmesh-dump
// --exterior): vanilla exterior NAVM uses parentType=WorldspaceNavmeshParent, crcHash=2783551548
// (same constant as interior), and its edge-links are cross-cell (the neighbour stitch). A NEW
// ISOLATED worldspace has NO neighbours -> crossCellLinks=0 (boundary edges, like interior). ----
static int RunExteriorNavmeshSpike(string[] argv)
{
    string? outPath = null;
    for (int i = 1; i + 1 < argv.Length; i += 2)
        switch (argv[i])
        {
            case "--out": outPath = argv[i + 1]; break;
            default: return Fail($"unknown arg: {argv[i]}");
        }
    if (string.IsNullOrWhiteSpace(outPath)) return Fail("usage: mutagen-cli exterior-navmesh-spike --out <path>");
    try
    {
        var modKey = ModKey.FromNameAndExtension(Path.GetFileName(outPath));
        var m = new Fallout4Mod(modKey, Fallout4Release.Fallout4);

        // --- new worldspace + one exterior cell at grid (0,0) ---
        var ws = new Worldspace(m, "MCPExtWS");
        var cell = new Cell(m, "MCPExtCell");   // exterior: leave IsInteriorCell unset
        cell.Grid = new CellGrid { Point = new Noggog.P2Int(0, 0) };
        var block = new WorldspaceBlock { BlockNumberX = 0, BlockNumberY = 0,
            GroupType = GroupTypeEnum.ExteriorCellBlock };
        var sub = new WorldspaceSubBlock { BlockNumberX = 0, BlockNumberY = 0,
            GroupType = GroupTypeEnum.ExteriorCellSubBlock };
        sub.Items.Add(cell);
        block.Items.Add(sub);
        ws.SubCells.Add(block);
        m.Worldspaces.Add(ws);

        // --- a tiny flat navmesh (2 tris) with a WORLDSPACE parent ---
        float minX = 0, minY = 0, maxX = 256, maxY = 256, z = 0;
        var navm = new NavigationMesh(m);
        var geo = new NavmeshGeometry { NavmeshVersion = 15 };
        geo.Vertices.Add(new Noggog.P3Float(minX, minY, z));
        geo.Vertices.Add(new Noggog.P3Float(maxX, minY, z));
        geo.Vertices.Add(new Noggog.P3Float(maxX, maxY, z));
        geo.Vertices.Add(new Noggog.P3Float(minX, maxY, z));
        geo.Triangles.Add(new NavmeshTriangle {
            Vertices = new Noggog.P3Int16(0, 1, 2),
            EdgeLink_0_1 = -1, EdgeLink_1_2 = -1, EdgeLink_2_0 = 1, Height = z });
        geo.Triangles.Add(new NavmeshTriangle {
            Vertices = new Noggog.P3Int16(0, 2, 3),
            EdgeLink_0_1 = 0, EdgeLink_1_2 = -1, EdgeLink_2_0 = -1, Height = z });
        geo.GridMin = new Noggog.P3Float(minX, minY, z);
        geo.GridMax = new Noggog.P3Float(maxX, maxY, z);
        geo.GridSize = 1;
        geo.GridMaxDistance = new Noggog.P2Float(maxX - minX, maxY - minY);
        var grid = new NavmeshGridArray();
        grid.GridCell.Add((short)(geo.Triangles.Count & 0xFFFF));
        grid.GridCell.Add(0);
        for (short ti = 0; ti < geo.Triangles.Count; ti++) grid.GridCell.Add(ti);
        geo.GridArrays = grid;
        var wparent = new WorldspaceNavmeshParent();
        wparent.Parent.SetTo(ws.FormKey);
        wparent.Coordinates = new Noggog.P2Int16(0, 0);
        geo.Parent = wparent;
        navm.NavmeshGeometry = geo;
        cell.NavigationMeshes.Add(navm);

        // --- NAVI override (000FF1) with a WORLDSPACE-parent map-info ---
        var naviKey = Mutagen.Bethesda.Plugins.FormKey.Factory("000FF1:Fallout4.esm");
        var navi = new NavigationMeshInfoMap(naviKey, Fallout4Release.Fallout4) { NavMeshVersion = 15 };
        m.NavigationMeshInfoMaps.RecordCache.Add(navi);
        var info = new NavigationMapInfo();
        info.NavigationMesh.SetTo(navm.FormKey);
        var wp = new NavigationMapInfoWorldspaceParent();
        wp.Worldspace.SetTo(ws.FormKey);
        info.Parent = wp;
        info.Unknown = 32;
        info.Unknown2 = unchecked((int)2783551548u);
        info.Point = new Noggog.P3Float((minX + maxX) / 2f, (minY + maxY) / 2f, z);
        navi.MapInfos.Add(info);

        var dir = Path.GetDirectoryName(Path.GetFullPath(outPath));
        if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
        m.WriteToBinary(outPath);

        // --- read-back proof ---
        var chk = Fallout4Mod.CreateFromBinaryOverlay(new ModPath(outPath), Fallout4Release.Fallout4);
        var rws = chk.Worldspaces.FirstOrDefault();
        INavigationMeshGetter? rnav = null;
        foreach (var w in chk.Worldspaces)
            foreach (var b in w.SubCells)
                foreach (var s in b.Items)
                    foreach (var c in s.Items)
                        foreach (var nmg in c.NavigationMeshes) rnav = nmg;
        var g2 = rnav?.NavmeshGeometry;
        var rinfo = chk.NavigationMeshInfoMaps.FirstOrDefault()?.MapInfos.FirstOrDefault();
        Console.Out.Write(JsonSerializer.Serialize(new
        {
            wrote = true,
            worldspace = rws?.FormKey.ToString(),
            worldspaceEditorId = rws?.EditorID,
            navm = rnav?.FormKey.ToString(),
            navmParentType = g2?.Parent?.GetType().Name,
            verts = g2?.Vertices.Count ?? 0,
            tris = g2?.Triangles.Count ?? 0,
            crcHash = g2?.CrcHash,
            naviMapInfoParentType = rinfo?.Parent?.GetType().Name,
            naviCovers = rinfo?.NavigationMesh.FormKeyNullable?.ToString(),
        }));
        return 0;
    }
    catch (Exception e) { return Fail($"spike error: {e.Message}"); }
}

// ---- cell-navmesh-list (W12 navmesh_handoff support): enumerate EVERY cell in the plugin
// (interior block hierarchy + worldspace sub-cells) with per-cell navmesh coverage so the
// Python side can build a per-cell CK navmesh checklist. Read-only. Reports interior flag,
// worldspace parent (exterior only), navmesh record count, and whether a NAVI MapInfo covers it. ----
static int RunCellNavmeshList(string[] argv)
{
    string? pluginPath = null;
    for (int i = 1; i + 1 < argv.Length; i += 2)
        switch (argv[i])
        {
            case "--plugin": pluginPath = argv[i + 1]; break;
            default: return Fail($"unknown arg: {argv[i]}");
        }
    if (string.IsNullOrWhiteSpace(pluginPath)) return Fail("usage: mutagen-cli cell-navmesh-list --plugin <path>");
    if (!File.Exists(pluginPath)) return Fail($"plugin not found: {pluginPath}");
    try
    {
        var mod = Fallout4Mod.CreateFromBinaryOverlay(new ModPath(pluginPath), Fallout4Release.Fallout4);

        // NAVM FormKeys that a NAVI MapInfo covers (additive across this plugin's NAVI overrides).
        var naviCovered = new HashSet<string>();
        foreach (var navi in mod.NavigationMeshInfoMaps)
            foreach (var mi in navi.MapInfos)
                naviCovered.Add(mi.NavigationMesh.FormKey.ToString());

        var cells = new List<object>();
        object Emit(ICellGetter c, bool interior, string? wrldParent) => new
        {
            cell = c.FormKey.ToString(),
            editorId = c.EditorID,
            interior,
            worldspaceParent = wrldParent,
            navmeshCount = c.NavigationMeshes.Count,
            hasNavi = c.NavigationMeshes.Any(nm => naviCovered.Contains(nm.FormKey.ToString())),
        };

        // interior cells (top-level block hierarchy)
        foreach (var b in mod.Cells)
            foreach (var s in b.SubBlocks)
                foreach (var c in s.Cells)
                    cells.Add(Emit(c, c.Flags.HasFlag(Cell.Flag.IsInteriorCell), null));

        // exterior cells (worldspace-parented)
        foreach (var w in mod.Worldspaces)
        {
            string wp = w.FormKey.ToString();
            if (w.TopCell is { } tc) cells.Add(Emit(tc, false, wp));
            foreach (var blk in w.SubCells)
                foreach (var sub in blk.Items)
                    foreach (var c in sub.Items)
                        cells.Add(Emit(c, c.Flags.HasFlag(Cell.Flag.IsInteriorCell), wp));
        }

        Console.Out.Write(JsonSerializer.Serialize(new { count = cells.Count, cells }));
        return 0;
    }
    catch (Exception e) { return Fail($"load error: {e.Message}"); }
}

// OS-13: render a condition function param from the correct packed slot. A FunctionConditionData
// overlaps ONE slot across three views (number/string/record); which view is valid depends on the
// function. Condition.GetParameterTypes(Function) tells us the slot's ParameterType -> bucket it
// into Number | String | Form | None and read the matching view. Without this the dump always read
// the Form view, so GetIsAliasRef (an Alias = NUMBER slot) showed a spurious/null FormKey instead
// of the alias index. `which` is 1 or 2.
static string? RenderParam(IFunctionConditionDataGetter d, int which)
{
    var (p1, p2, _) = Condition.GetParameterTypes(d.Function);
    var pt = which == 1 ? p1 : p2;
    switch (pt)
    {
        case Condition.ParameterType.None:
            return null;
        case Condition.ParameterType.String:
        case Condition.ParameterType.VariableName:
            return which == 1 ? d.ParameterOneString : d.ParameterTwoString;
        // Number-like slots: the value lives in ParameterOne/TwoNumber, not as a FormKey.
        case Condition.ParameterType.Integer:
        case Condition.ParameterType.Float:
        case Condition.ParameterType.Alias:
        case Condition.ParameterType.QuestStage:
        case Condition.ParameterType.Sex:
        case Condition.ParameterType.Axis:
        case Condition.ParameterType.Alignment:
        case Condition.ParameterType.CrimeType:
        case Condition.ParameterType.CriticalStage:
        case Condition.ParameterType.MiscStat:
        case Condition.ParameterType.FormType:
        case Condition.ParameterType.CastingSource:
        case Condition.ParameterType.WardState:
        case Condition.ParameterType.VATSValueFunction:
        case Condition.ParameterType.VATSValueParam:
            return $"{(which == 1 ? d.ParameterOneNumber : d.ParameterTwoNumber)}";
        // Everything else is a record/Form slot -> render the FormKey.
        default:
            return (which == 1 ? d.ParameterOneRecord : d.ParameterTwoRecord).FormKeyNullable?.ToString();
    }
}

// OS-13: the GetParameterTypes category string for a slot, so a consumer can tell number-vs-form
// unambiguously (e.g. paramType1=="Alias" proves the alias-index render path).
static string RenderParamType(IFunctionConditionDataGetter d, int which)
{
    var (p1, p2, _) = Condition.GetParameterTypes(d.Function);
    return $"{(which == 1 ? p1 : p2)}";
}

// ---- dialogue-dump: inspect a quest's player-dialogue wiring (DLBR + DIAL + INFO) so an authored
// quest can be diffed against a known-working vanilla one (why doesn't the wheel surface?). Read-only.
//   no --quest: list quests that own a Player+TopLevel DialogBranch (candidate player-dialogue quests)
//   --quest <FormID|EditorID>: full DLBR/DIAL/INFO dump for that quest
static int RunDialogueDump(string[] argv)
{
    string? pluginPath = null, quest = null;
    int max = 25;
    for (int i = 1; i + 1 < argv.Length; i += 2)
        switch (argv[i])
        {
            case "--plugin": pluginPath = argv[i + 1]; break;
            case "--quest": quest = argv[i + 1]; break;
            case "--max": int.TryParse(argv[i + 1], out max); break;
            default: return Fail($"unknown arg: {argv[i]}");
        }
    if (string.IsNullOrWhiteSpace(pluginPath)) return Fail("usage: mutagen-cli dialogue-dump --plugin <path> [--quest <FormID>] [--max N]");
    if (!File.Exists(pluginPath)) return Fail($"plugin not found: {pluginPath}");
    try
    {
        var mod = Fallout4Mod.CreateFromBinaryOverlay(new ModPath(pluginPath), Fallout4Release.Fallout4);
        uint? wantId = quest is null ? null : NormFormId(quest);
        string wantEid = quest?.Trim() ?? "";

        if (string.IsNullOrWhiteSpace(quest))
        {
            var qs = new List<object>();
            foreach (var q in mod.Quests)
            {
                int playerTop = q.DialogBranches.Count(b => b.Category == DialogBranch.CategoryType.Player
                    && b.Flags.GetValueOrDefault().HasFlag(DialogBranch.Flag.TopLevel));
                if (playerTop == 0) continue;
                qs.Add(new { quest = q.FormKey.ToString(), editorId = q.EditorID,
                    branches = q.DialogBranches.Count, playerTopLevelBranches = playerTop,
                    topics = q.DialogTopics.Count });
                if (qs.Count >= max) break;
            }
            Console.Out.Write(JsonSerializer.Serialize(new { count = qs.Count, quests = qs }));
            return 0;
        }

        IQuestGetter? qg = null;
        foreach (var q in mod.Quests)
            if ((wantId is uint id && (q.FormKey.ID & 0xFFFFFF) == id)
                || (q.EditorID is { } e && string.Equals(e, wantEid, StringComparison.OrdinalIgnoreCase)))
            { qg = q; break; }
        if (qg is null) { Console.Out.Write(JsonSerializer.Serialize(new { found = false })); return 1; }

        var branches = qg.DialogBranches.Select(b => new {
            formKey = b.FormKey.ToString(), editorId = b.EditorID,
            category = $"{b.Category}", flags = $"{b.Flags}",
            startingTopic = b.StartingTopic.FormKeyNullable?.ToString(),
        }).ToList();

        var topics = new List<object>();
        foreach (var dt in qg.DialogTopics.Take(max))
        {
            var infos = dt.Responses.Select(info => new {
                prompt = info.Prompt?.String,
                speaker = info.Speaker.FormKeyNullable?.ToString(),
                responseCount = info.Responses.Count,
                // P0/P3: surface the script-free stage-advance (SNAM) + Papyrus fragment (VMAD)
                // so dialogue-driven progression is verifiable by dump alone (raw value; -1 = unused).
                setStageOnBegin = info.SetParentQuestStage?.OnBegin,
                setStageOnEnd = info.SetParentQuestStage?.OnEnd,
                hasFragment = info.VirtualMachineAdapter is not null,
                // OS-13: full TIF VMAD fragment readback (scriptName + per-OnBegin/OnEnd
                // scriptName/fragmentName), null when no ScriptFragments adapter. Proves OS-04.
                fragment = info.VirtualMachineAdapter?.ScriptFragments is { } sf ? new {
                    scriptName = sf.Script?.Name,
                    onBegin = sf.OnBegin is { } ob ? new { scriptName = ob.ScriptName, fragmentName = ob.FragmentName } : null,
                    onEnd = sf.OnEnd is { } oe ? new { scriptName = oe.ScriptName, fragmentName = oe.FragmentName } : null,
                } : null,
                // OS-13: INFO link/scene readback — emits null until link/scene authoring lands (P4),
                // but the shape contract is fixed now so consumers can rely on the keys.
                previousDialog = info.PreviousDialog.FormKeyNullable?.ToString(),
                linkTopic = info.Topic.FormKeyNullable?.ToString(),
                startScene = info.StartScene.FormKeyNullable?.ToString(),
                startScenePhase = info.StartScenePhase,
                conditionCount = info.Conditions.Count,
                conditions = info.Conditions.Select(c => new {
                    fn = c.Data is IFunctionConditionDataGetter f ? $"{f.Function}" : null,
                    runOn = $"{c.Data?.RunOnType}",
                    reference = c.Data?.Reference.FormKeyNullable?.ToString(),
                    // OS-13: render each param from the correct packed slot (number/string/form)
                    // via GetParameterTypes, and surface the slot category so a consumer can tell
                    // number-vs-form unambiguously. aliasRunOn = the QuestAlias run-on id (Unknown3).
                    param1 = c.Data is IFunctionConditionDataGetter f2 ? RenderParam(f2, 1) : null,
                    param2 = c.Data is IFunctionConditionDataGetter f3 ? RenderParam(f3, 2) : null,
                    paramType1 = c.Data is IFunctionConditionDataGetter f4 ? RenderParamType(f4, 1) : null,
                    paramType2 = c.Data is IFunctionConditionDataGetter f5 ? RenderParamType(f5, 2) : null,
                    aliasRunOn = (c.Data as IFunctionConditionDataGetter)?.Unknown3,
                    cmp = $"{c.CompareOperator}",
                    val = c is IConditionFloatGetter cf ? (float?)cf.ComparisonValue : null,
                }).ToList(),
            }).ToList();
            topics.Add(new {
                formKey = dt.FormKey.ToString(), editorId = dt.EditorID,
                name = dt.Name?.String,
                subtype = $"{dt.Subtype}", category = $"{dt.Category}", priority = dt.Priority,
                branch = dt.Branch.FormKeyNullable?.ToString(),
                infoCount = dt.Responses.Count, infos,
            });
        }
        Console.Out.Write(JsonSerializer.Serialize(new {
            found = true, quest = qg.FormKey.ToString(), editorId = qg.EditorID,
            questFlags = $"{qg.Data?.Flags}",
            branchCount = branches.Count, branches, topicCount = qg.DialogTopics.Count, topics,
        }));
        return 0;
    }
    catch (Exception e) { return Fail($"load error: {e.Message}"); }
}

// ---- navmesh-dump subcommand (A-in-game RE, ground-truth): summarize the first N populated
// cell-child navmeshes' NVNM geometry so we can compare a CK-finalized vanilla navmesh against our
// authored one (GridSize, count fields, CrcHash, cover/waypoint/grid presence). Read-only. ----
static int RunNavmeshDump(string[] argv)
{
    string? pluginPath = null;
    int max = 1;
    string? record = null;   // optional NAVM FormID filter (exterior RE: target a specific mesh)
    bool exteriorOnly = false;
    for (int i = 1; i + 1 < argv.Length; i += 2)
        switch (argv[i])
        {
            case "--plugin": pluginPath = argv[i + 1]; break;
            case "--max": int.TryParse(argv[i + 1], out max); break;
            case "--record": record = argv[i + 1]; break;
            case "--exterior": exteriorOnly = bool.TryParse(argv[i + 1], out var e) && e; break;
            default: return Fail($"unknown arg: {argv[i]}");
        }
    if (string.IsNullOrWhiteSpace(pluginPath)) return Fail("usage: mutagen-cli navmesh-dump --plugin <path> [--max N] [--record <NAVM FormID>] [--exterior true]");
    if (!File.Exists(pluginPath)) return Fail($"plugin not found: {pluginPath}");
    uint? wantId = record is null ? null : NormFormId(record);
    try
    {
        var mod = Fallout4Mod.CreateFromBinaryOverlay(new ModPath(pluginPath), Fallout4Release.Fallout4);
        var outList = new List<object>();

        // W12-RE: dump one navmesh's NVNM geometry + the exterior-specific connectivity
        // (parent type, cross-cell EdgeLinks -> {triangle, linked mesh}, door triangles).
        object Dump(INavigationMeshGetter nm, ICellGetter c, bool interior, string? wrld)
        {
            var g = nm.NavmeshGeometry!;
            // EdgeLink.Mesh = the OTHER navmesh this edge connects to (cross-cell portal =
            // the exterior "stitch"). A non-null/non-self mesh here is the inter-cell link.
            var edgeSample = g.EdgeLinks.Take(8)
                .Select(el => el.Mesh.FormKeyNullable?.ToString())
                .ToList();
            int crossCellLinks = g.EdgeLinks.Count(el =>
                el.Mesh.FormKeyNullable is { } mk && mk != nm.FormKey);
            return new
            {
                navm = nm.FormKey.ToString(),
                cell = c.FormKey.ToString(),
                interior,
                worldspaceParent = wrld,
                navmeshVersion = g.NavmeshVersion,
                crcHash = g.CrcHash,
                parentType = g.Parent?.GetType().Name,
                verts = g.Vertices.Count,
                tris = g.Triangles.Count,
                edgeLinks = g.EdgeLinks.Count,
                crossCellLinks = crossCellLinks,
                edgeLinkSample = edgeSample,
                doorTriangles = g.DoorTriangles.Count,
                cover = g.Cover.Count,
                coverTriMap = g.CoverTriangleMappings.Count,
                waypoints = g.Waypoints.Count,
                gridSize = g.GridSize,
                gridCells = g.GridArrays?.GridCell?.Count ?? 0,
                gridMin = g.GridMin.ToString(),
                gridMax = g.GridMax.ToString(),
                gridMaxDistance = g.GridMaxDistance.ToString(),
                tri0Flags = g.Triangles.Count > 0 ? (int?)g.Triangles[0].Flags : null,
            };
        }
        bool Want(INavigationMeshGetter nm) =>
            nm.NavmeshGeometry is not null && (wantId is null || nm.FormKey.ID == wantId);

        // interior cells
        if (!exteriorOnly)
            foreach (var b in mod.Cells)
                foreach (var s in b.SubBlocks)
                    foreach (var c in s.Cells)
                        foreach (var nm in c.NavigationMeshes)
                        {
                            if (!Want(nm)) continue;
                            outList.Add(Dump(nm, c, c.Flags.HasFlag(Cell.Flag.IsInteriorCell), null));
                            if (outList.Count >= max) goto done;
                        }
        // exterior worldspace cells
        foreach (var w in mod.Worldspaces)
        {
            string wp = w.FormKey.ToString();
            void Scan(ICellGetter? c)
            {
                if (c is null) return;
                foreach (var nm in c.NavigationMeshes)
                {
                    if (!Want(nm) || outList.Count >= max) continue;
                    outList.Add(Dump(nm, c, c.Flags.HasFlag(Cell.Flag.IsInteriorCell), wp));
                }
            }
            Scan(w.TopCell);
            foreach (var blk in w.SubCells)
                foreach (var sub in blk.Items)
                    foreach (var c in sub.Items)
                        Scan(c);
            if (outList.Count >= max) goto done;
        }
        done:
        Console.Out.Write(JsonSerializer.Serialize(new { count = outList.Count, navmeshes = outList }));
        return outList.Count > 0 ? 0 : 1;
    }
    catch (Exception e) { return Fail($"load error: {e.Message}"); }
}

static int Fail(string msg)
{
    Console.Error.WriteLine(msg);
    return 2;
}

// ---- argv ----
string? pluginPath = null;
string? record = null;
for (int i = 0; i + 1 < args.Length; i += 2)
{
    switch (args[i])
    {
        case "--plugin": pluginPath = args[i + 1]; break;
        case "--record": record = args[i + 1]; break;
        default: return Fail($"unknown arg: {args[i]}");
    }
}
if (string.IsNullOrWhiteSpace(pluginPath) || string.IsNullOrWhiteSpace(record))
    return Fail("usage: mutagen-cli --plugin <path> --record <FormID|EditorID>");
if (!File.Exists(pluginPath))
    return Fail($"plugin not found: {pluginPath}");

// ---- query disambiguation (mirrors tools.py _norm_formid) ----
// Try FormID-normalize first: strip 0x, hex-only, keep the low 6 object-id
// digits. If it parses, match on the record's ObjectID; the EditorID compare
// runs in parallel (the Python side ORs both, same as here).
uint? wantObjectId = NormFormId(record);
string wantEditor = record.Trim();

// ---- open read-only + stream ----
IMajorRecordGetter? hit;
try
{
    var mod = Fallout4Mod.CreateFromBinaryOverlay(new ModPath(pluginPath), Fallout4Release.Fallout4);
    hit = null;
    foreach (var rec in mod.EnumerateMajorRecords())
    {
        bool idMatch = wantObjectId is uint id && (rec.FormKey.ID & 0xFFFFFF) == id;
        bool edMatch = rec.EditorID is { } eid
                       && string.Equals(eid, wantEditor, StringComparison.OrdinalIgnoreCase);
        if (idMatch || edMatch) { hit = rec; break; }
    }
}
catch (Exception e)
{
    return Fail($"load error: {e.Message}");
}

// ---- emit ----
if (hit is null)
{
    Console.Out.Write(JsonSerializer.Serialize(new { found = false }));
    return 1;
}

string recordType = hit.GetType().Name;
try { recordType = LoquiRegistration.GetRegister(hit.GetType())?.Name ?? recordType; }
catch { /* fall back to the runtime type name */ }

// MISC detail (diag): surface the fields that govern inventory render + world pickup so a
// coupon can be byte-compared against vanilla clutter (model path, OBND bounds, KWDA, value/weight).
object? miscDetail = null;
if (hit is IMiscItemGetter mi)
{
    var ob = mi.ObjectBounds;
    miscDetail = new
    {
        name = mi.Name?.String,
        model = mi.Model?.File.ToString(),
        modelHasData = mi.Model is not null,
        objectBounds = new { x1 = ob.First.X, y1 = ob.First.Y, z1 = ob.First.Z, x2 = ob.Second.X, y2 = ob.Second.Y, z2 = ob.Second.Z },
        objectBoundsZero = ob.First.X == 0 && ob.First.Y == 0 && ob.First.Z == 0 && ob.Second.X == 0 && ob.Second.Y == 0 && ob.Second.Z == 0,
        // PTRN — Preview Transform (TRNS). Governs how the model is framed in the Pip-Boy/Inspect
        // inventory preview (separate from the world model). Null = engine default framing.
        previewTransform = mi.PreviewTransform.FormKeyNullable?.ToString(),
        value = mi.Value,
        weight = mi.Weight,
        keywords = mi.Keywords?.Select(k => k.FormKey.ToString()).ToArray() ?? System.Array.Empty<string>(),
        keywordCount = mi.Keywords?.Count ?? 0,
        iconPath = mi.Icons?.ToString(),
        pickUpSound = mi.PickUpSound?.FormKey.ToString(),
        putDownSound = mi.PutDownSound?.FormKey.ToString(),
    };
}

// KYWD detail (diag): workshop-menu category keywords carry a CNAM Color (+ Name); a custom build
// category that won't render is usually a bare keyword missing the color the menu UI draws the button from.
object? kywdDetail = null;
if (hit is IKeywordGetter kw)
{
    var c = kw.Color;
    kywdDetail = new
    {
        name = kw.Name?.String,
        colorPresent = c is not null,
        color = c is { } cc ? new { a = cc.A, r = cc.R, g = cc.G, b = cc.B } : null,
    };
}

Console.Out.Write(JsonSerializer.Serialize(new
{
    found = true,
    formKey = hit.FormKey.ToString(),   // "<6hex>:<ModKey>" — matches Spriggit form_key
    editorId = hit.EditorID,
    recordType,                          // Loqui name, e.g. "GlobalInt" — matches Spriggit MutagenObjectType
    misc = miscDetail,
    kywd = kywdDetail,
}));
return 0;

// strip 0x, reject non-hex, drop a load-order prefix to the low 6 object-id hex.
static uint? NormFormId(string s)
{
    string t = s.Trim().ToLowerInvariant();
    if (t.StartsWith("0x")) t = t[2..];
    if (t.Length == 0 || t.Any(c => !Uri.IsHexDigit(c))) return null;
    uint full = Convert.ToUInt32(t, 16);
    return full & 0xFFFFFF;
}

// ---- create subcommand: JSON spec -> new plugin (Faz 1 MVP authoring writer) ----
//
//   mutagen-cli create --spec <file.json> --out <plugin.esp>
//
// spec: {"records":[{"type":"Npc|Armor|Quest","editorId":"...","name":"...",
//   NPC (Faz 1.1):  "race":"013746:Fallout4.esm","class":"...",
//                   "factions":[{"faction":"...","rank":0}]
//   Armor (Faz 1.2):"keywords":["<6hex>:<ModKey>"],"value":250,"weight":12.5,
//                   "armorRating":110,"bipedSlots":["TorsoArmor","LeftArmArmor"]
//                     // armorRating 0-65535 (UInt16); bipedSlots = BipedObjectFlag names
//   Quest (Faz 2):  "questType":"SideQuests","flags":["StartGameEnabled"],
//                   "stages":[{"index":0,"logEntry":"...","runOnStart":true},
//                     {"index":10,"logEntry":"..."}],  // runOnStart = INDX 0x02 (startup stage);
//                     // every logEntry gets a QSDT marker (mandatory; engine-required)
//                   "objectives":[{"index":10,"text":"..."}],
//   Quest (Faz 2.1):"topics":[{"editorId":"...","name":"...","subtype":"Custom0",
//                     "branch":"<branch editorId|6hex:ModKey>",  // Kerem-polish: surface in the wheel
//                     "responses":[{"prompt":"...","speaker":"<6hex>:<ModKey>",
//                       "lines":[{"text":"...","responseNumber":1,"emotion":"<key>"}],
//                       "conditions":[{"function":"GetStage","comparison":"GreaterThanOrEqualTo",
//                         "value":10,"param1":"<6hex>:<ModKey>","runOn":"Subject"}]}]}]
//   Quest (Kerem-polish):"branches":[{"editorId":"...","startingTopic":"<topic editorId|6hex:ModKey>",
//                     "category":"Player","flags":["TopLevel"]}]  // DLBR: bare DIAL/INFO won't surface
//   Quest (Faz 2.1c):"aliases":[{"id":0,"name":"QuestGiver","flags":["Optional"],
//                     "forcedReference":"<6hex>:<ModKey>","uniqueActor":"<6hex>:<ModKey>",
//                     "conditions":[{...}]}]  // id null => auto (list order)
//   Quest (Faz 2.1d):"scripts":[{"name":"MyQuestScript","flags":"Local",
//                     "properties":[{"name":"pTarget","type":"object","value":"<6hex>:<ModKey>"},
//                       {"name":"pCount","type":"int","value":3}]}]  // VMAD v6/objfmt2
//   Quest (Faz 2.1e):"scenes":[{"editorId":"...","flags":["BeginOnQuestStart"],
//                     "actors":[{"id":0,"flags":["..."]}],  // id = quest alias ID
//                     "phases":[{"name":"P0","startConditions":[{...}]}],
//                     "actions":[{"type":"Dialog","actor":0,"topic":"<topic editorId|6hex:ModKey>",
//                       "startPhase":0,"endPhase":0,"flags":["..."]}]}]
//   Quest (Faz 2.1f):"fragments":{"scriptName":"MyMod:Fragments:Quests:QF_MyQuest_01000800",
//                     "properties":[{"name":"p","type":"int","value":1}],
//                     "stages":[{"stage":10,"fragmentName":"Fragment_Stage_0010_Item_00"},
//                       {"stage":20,"stageIndex":0,"fragmentName":"Fragment_Stage_0020_Item_00"}]}
//                     // QF fragment metadata only; compile the .pex via fo4_papyrus_build
//   Quest (Faz 2.1g):"aliasFragments":[{"alias":2,"scripts":[{"name":"MyMod:MyAliasScript",
//                     "properties":[{"name":"p","type":"int","value":1}]}]}]
//                     // binds alias 2 to its fragment script(s); .pex compiled separately
// (NPC/Quest fields are type-specific, all optional.)
// The ModKey is taken from the --out filename so new records' FormKeys self-ref it.
// FormLinks into masters are auto-collected into the header (Mutagen master-iterate).
// stdout: one JSON object {created, plugin, masters, records:[{type,editorId,
//         formKey, ...read-back fields}]} — the per-record fields after "formKey"
//         (npc: race/class/factionCount; armor: value/weight/armorRating/
//         keywordCount/bipedSlotCount; quest: name/questType/stageCount/
//         objectiveCount/fragmentCount/aliasFragmentCount) are read back from the
//         written binary (round-trip proof).
// exit 0 = written, 2 = bad args / spec / write error.
static int RunCreate(string[] argv)
{
    string? specPath = null;
    string? outPath = null;
    string? mastersDir = null;   // W7-Data: FO4 Data dir, for resolving package template input indices by name
    for (int i = 1; i + 1 < argv.Length; i += 2)
    {
        switch (argv[i])
        {
            case "--spec": specPath = argv[i + 1]; break;
            case "--out": outPath = argv[i + 1]; break;
            case "--masters-dir": mastersDir = argv[i + 1]; break;
            default: return Fail($"unknown arg: {argv[i]}");
        }
    }
    if (string.IsNullOrWhiteSpace(specPath) || string.IsNullOrWhiteSpace(outPath))
        return Fail("usage: mutagen-cli create --spec <file.json> --out <plugin.esp>");
    if (!File.Exists(specPath))
        return Fail($"spec not found: {specPath}");

    CreateSpec? spec;
    try
    {
        spec = JsonSerializer.Deserialize<CreateSpec>(
            File.ReadAllText(specPath),
            new JsonSerializerOptions { PropertyNameCaseInsensitive = true });
    }
    catch (Exception e) { return Fail($"spec parse error: {e.Message}"); }
    if (spec?.Records is not { Count: > 0 } records)
        return Fail("spec has no records");

    var modKey = ModKey.FromNameAndExtension(Path.GetFileName(outPath));
    var mod = new Fallout4Mod(modKey, Fallout4Release.Fallout4);

    // local FormKey parse with a clear error (Factory throws on a malformed key).
    static bool TryKey(string? s, out FormKey key, out string err)
    {
        key = default; err = "";
        try { key = FormKey.Factory(s); return true; }
        catch (Exception e) { err = $"bad FormKey '{s}': {e.Message}"; return false; }
    }

    // W7-Data: resolve a package template's location-data input SLOT by name. The Data
    // dictionary key (sbyte) is defined by the TEMPLATE the engine binds, not by us — so we
    // load the master ESM that owns the template PACK (lazy overlay), find the
    // PackageDataLocation input whose Name matches (or the first one when name is null), and
    // return its index + the template's DataInputVersion. Wrong index = silently-broken AI,
    // so we never guess: the slot comes from the live template every time.
    static bool ResolvePackageLocationInput(string mastersDir, FormKey templateKey, string? inputName,
        out sbyte index, out int dataInputVersion, out string err)
    {
        index = 0; dataInputVersion = 0; err = "";
        string masterFile = Path.Combine(mastersDir, templateKey.ModKey.ToString());
        if (!File.Exists(masterFile)) { err = $"template master not found: {masterFile}"; return false; }
        IPackageGetter? tmpl;
        try
        {
            var mm = Fallout4Mod.CreateFromBinaryOverlay(new ModPath(masterFile), Fallout4Release.Fallout4);
            tmpl = mm.Packages.FirstOrDefault(p => p.FormKey == templateKey);
        }
        catch (Exception e) { err = $"template load error: {e.Message}"; return false; }
        if (tmpl is null) { err = $"template package {templateKey} not found in {templateKey.ModKey}"; return false; }
        dataInputVersion = tmpl.DataInputVersion;
        foreach (var kv in tmpl.Data)
        {
            if (kv.Value is not IPackageDataLocationGetter) continue;
            if (inputName is null || string.Equals(kv.Value.Name, inputName, StringComparison.OrdinalIgnoreCase))
            { index = kv.Key; return true; }
        }
        err = inputName is null
            ? $"template {templateKey} has no PackageDataLocation input"
            : $"template {templateKey} has no PackageDataLocation input named '{inputName}'";
        return false;
    }

    // A condition param can be a FormLink ("<hex>:<modkey>"), an int, or a string —
    // FO4 packs all three slots into one FunctionConditionData; pick by shape.
    static bool SetParam(FunctionConditionData d, int which, string? raw, out string err)
    {
        err = "";
        if (string.IsNullOrWhiteSpace(raw)) return true;
        if (raw.Contains(':'))
        {
            if (!TryKey(raw, out var fk, out err)) return false;
            if (which == 1) d.ParameterOneRecord.SetTo(fk); else d.ParameterTwoRecord.SetTo(fk);
        }
        else if (int.TryParse(raw, out var num))
        {
            if (which == 1) d.ParameterOneNumber = num; else d.ParameterTwoNumber = num;
        }
        else
        {
            if (which == 1) d.ParameterOneString = raw; else d.ParameterTwoString = raw;
        }
        return true;
    }

    // Build a ConditionFloat from a spec: a function (Condition.Function, 479 names),
    // a compare operator + float value, up to 2 params, and a run-on target. FO4 uses
    // ONE generic FunctionConditionData for every function (not per-function classes),
    // so any function name works through this single path.
    static bool BuildCondition(ConditionSpec cs, out ConditionFloat cond, out string err)
    {
        cond = new ConditionFloat();
        err = "";
        if (string.IsNullOrWhiteSpace(cs.Function)
            || !Enum.TryParse<Condition.Function>(cs.Function, true, out var fn))
        { err = $"bad condition function '{cs.Function}'"; return false; }
        var op = CompareOperator.EqualTo;
        if (!string.IsNullOrWhiteSpace(cs.Comparison) && !Enum.TryParse(cs.Comparison, true, out op))
        { err = $"bad comparison '{cs.Comparison}'"; return false; }
        var runOn = Condition.RunOnType.Subject;
        if (!string.IsNullOrWhiteSpace(cs.RunOn) && !Enum.TryParse(cs.RunOn, true, out runOn))
        { err = $"bad runOn '{cs.RunOn}'"; return false; }
        cond.CompareOperator = op;
        cond.ComparisonValue = cs.Value;
        var data = new FunctionConditionData { Function = fn, RunOnType = runOn };
        // Faz 3 / W1: run-on payload slots. RunOnType.QuestAlias stores the alias id in
        // Unknown3 (default 0 == alias-0, so Python requires an explicit value); RunOnType
        // .Reference stores a FormLink in Reference — distinct from the function params.
        if (cs.AliasRunOn.HasValue) data.Unknown3 = cs.AliasRunOn.Value;
        if (!string.IsNullOrWhiteSpace(cs.Reference))
        {
            if (!TryKey(cs.Reference, out var rfk, out err)) return false;
            data.Reference.SetTo(rfk);
        }
        if (!SetParam(data, 1, cs.Param1, out err)) return false;
        if (!SetParam(data, 2, cs.Param2, out err)) return false;
        cond.Data = data;
        return true;
    }

    // OS-02: build an ALCH/INGR magic Effect — a base MGEF FormLink + EffectData scalars.
    static bool BuildEffect(EffectSpec es, out Effect effect, out string err)
    {
        effect = new Effect();
        err = "";
        if (string.IsNullOrWhiteSpace(es.BaseEffect)) { err = "effect missing baseEffect (MGEF FormKey)"; return false; }
        if (!TryKey(es.BaseEffect, out var bk, out err)) return false;
        effect.BaseEffect.SetTo(bk);
        effect.Data = new EffectData { Magnitude = es.Magnitude, Area = es.Area, Duration = es.Duration };
        return true;
    }

    // Build a ScriptProperty from a spec: a name + a typed value. FO4 models each
    // Papyrus property type as its own class (object/int/float/bool/string + list/
    // struct variants); MVP covers the 5 scalar types. A value-bearing property is
    // flagged Edited (what CK sets). 'object' = a FormLink (or an alias index).
    static bool BuildScriptProperty(ScriptPropertySpec ps, out ScriptProperty prop, out string err)
    {
        prop = new ScriptProperty();
        err = "";
        if (string.IsNullOrWhiteSpace(ps.Name)) { err = "script property missing name"; return false; }
        const ScriptProperty.Flag edited = ScriptProperty.Flag.Edited;
        switch ((ps.Type ?? "").Trim().ToLowerInvariant())
        {
            case "object":
            {
                var op = new ScriptObjectProperty { Name = ps.Name, Flags = edited };
                if (ps.Value is { ValueKind: JsonValueKind.String } sv
                    && !string.IsNullOrWhiteSpace(sv.GetString()))
                {
                    if (!TryKey(sv.GetString(), out var fk, out err)) return false;
                    op.Object.SetTo(fk);
                }
                if (ps.Alias is { } al)
                {
                    if (al < short.MinValue || al > short.MaxValue) { err = $"alias index out of range: {al}"; return false; }
                    op.Alias = (short)al;
                }
                prop = op;
                return true;
            }
            case "int":
            {
                int d = 0;
                if (ps.Value is { } v)
                {
                    if (v.ValueKind != JsonValueKind.Number) { err = $"int property '{ps.Name}' value must be a number"; return false; }
                    d = v.GetInt32();
                }
                prop = new ScriptIntProperty { Name = ps.Name, Flags = edited, Data = d };
                return true;
            }
            case "float":
            {
                float d = 0f;
                if (ps.Value is { } v)
                {
                    if (v.ValueKind != JsonValueKind.Number) { err = $"float property '{ps.Name}' value must be a number"; return false; }
                    d = v.GetSingle();
                }
                prop = new ScriptFloatProperty { Name = ps.Name, Flags = edited, Data = d };
                return true;
            }
            case "bool":
            {
                bool d = false;
                if (ps.Value is { } v)
                {
                    if (v.ValueKind is not (JsonValueKind.True or JsonValueKind.False)) { err = $"bool property '{ps.Name}' value must be true/false"; return false; }
                    d = v.GetBoolean();
                }
                prop = new ScriptBoolProperty { Name = ps.Name, Flags = edited, Data = d };
                return true;
            }
            case "string":
            {
                string d = "";
                if (ps.Value is { } v)
                {
                    if (v.ValueKind != JsonValueKind.String) { err = $"string property '{ps.Name}' value must be a string"; return false; }
                    d = v.GetString() ?? "";
                }
                prop = new ScriptStringProperty { Name = ps.Name, Flags = edited, Data = d };
                return true;
            }
            default:
                err = $"bad script property type '{ps.Type}' (object|int|float|bool|string)";
                return false;
        }
    }

    // Build a ScriptEntry (named Papyrus script + flags + typed properties) — shared by
    // the quest whole-script binding (Scripts) and the fragment script (Script, Faz 2.1f).
    static bool BuildScriptEntry(string? name, string? flags, List<ScriptPropertySpec>? props,
                                 out ScriptEntry entry, out string err)
    {
        entry = new ScriptEntry();
        err = "";
        if (string.IsNullOrWhiteSpace(name)) { err = "script entry missing name"; return false; }
        entry.Name = name;
        if (!string.IsNullOrWhiteSpace(flags))
        {
            if (!Enum.TryParse<ScriptEntry.Flag>(flags, true, out var sf)) { err = $"bad script flag '{flags}'"; return false; }
            entry.Flags = sf;
        }
        if (props is { Count: > 0 })
            foreach (var p in props)
            {
                if (!BuildScriptProperty(p, out var prop, out var pe)) { err = pe; return false; }
                entry.Properties.Add(prop);
            }
        return true;
    }

    // W4: parse a [x,y,z] float array into a P3Float (default origin when absent).
    static bool Vec3(List<float>? v, string what, out Noggog.P3Float p, out string err)
    {
        p = new Noggog.P3Float(0, 0, 0); err = "";
        if (v is null) return true;
        if (v.Count != 3) { err = $"{what} must be [x,y,z] (3 floats), got {v.Count}"; return false; }
        p = new Noggog.P3Float(v[0], v[1], v[2]);
        return true;
    }

    // W4/W5: add placed refs (REFR/ACHR) into a cell's child lists (Temporary, or Persistent
    // when persistent=true). Shared by a new cell (type=cell) and an override (type=cellOverride).
    static bool AddPlacedRefs(Fallout4Mod m, Cell cell, List<PlacedRefSpec>? objs,
                              List<PlacedRefSpec>? npcs, out string err)
    {
        err = "";
        if (objs is { Count: > 0 })
            foreach (var po in objs)
            {
                if (string.IsNullOrWhiteSpace(po.Base)) { err = "placedObject missing base"; return false; }
                if (!TryKey(po.Base, out var bk, out err)) return false;
                var refr = string.IsNullOrWhiteSpace(po.EditorId) ? new PlacedObject(m) : new PlacedObject(m, po.EditorId);
                refr.Base.SetTo(bk);
                if (!Vec3(po.Position, "placedObject position", out var pos, out err)) return false;
                if (!Vec3(po.Rotation, "placedObject rotation", out var rot, out err)) return false;
                refr.Position = pos; refr.Rotation = rot;
                if (po.Scale is { } sc) refr.Scale = sc;
                // W8.5 — XTEL door-link: a door REFR teleports to a destination door + spawn point.
                if (po.Teleport is { } tp)
                {
                    if (string.IsNullOrWhiteSpace(tp.Door)) { err = "placedObject teleport missing door"; return false; }
                    if (!TryKey(tp.Door, out var dk, out err)) return false;
                    var td = new TeleportDestination();
                    td.Door.SetTo(dk);
                    if (!Vec3(tp.Position, "teleport position", out var tpos, out err)) return false;
                    if (!Vec3(tp.Rotation, "teleport rotation", out var trot, out err)) return false;
                    td.Position = tpos; td.Rotation = trot;
                    refr.TeleportDestination = td;
                }
                (po.Persistent ? cell.Persistent : cell.Temporary).Add(refr);
            }
        if (npcs is { Count: > 0 })
            foreach (var pn in npcs)
            {
                if (string.IsNullOrWhiteSpace(pn.Base)) { err = "placedNpc missing base"; return false; }
                if (!TryKey(pn.Base, out var bk, out err)) return false;
                var achr = string.IsNullOrWhiteSpace(pn.EditorId) ? new PlacedNpc(m) : new PlacedNpc(m, pn.EditorId);
                achr.Base.SetTo(bk);
                if (!Vec3(pn.Position, "placedNpc position", out var pos, out err)) return false;
                if (!Vec3(pn.Rotation, "placedNpc rotation", out var rot, out err)) return false;
                achr.Position = pos; achr.Rotation = rot;
                if (pn.Scale is { } sc) achr.Scale = sc;
                (pn.Persistent ? cell.Persistent : cell.Temporary).Add(achr);
            }
        return true;
    }

    // W4/W5: insert a cell into the interior block hierarchy (block = id%10, subblock = (id/10)%10),
    // reusing a CellBlock/CellSubBlock per number. Shared by new-cell + override.
    static void PlaceCell(Fallout4Mod m, Cell cell, Dictionary<int, CellBlock> blocks,
                          Dictionary<(int, int), CellSubBlock> subs)
    {
        uint cid = cell.FormKey.ID;
        int blockNo = (int)(cid % 10);
        int subNo = (int)((cid / 10) % 10);
        if (!blocks.TryGetValue(blockNo, out var blk))
        {
            blk = new CellBlock { BlockNumber = blockNo, GroupType = GroupTypeEnum.InteriorCellBlock };
            m.Cells.Records.Add(blk);
            blocks[blockNo] = blk;
        }
        if (!subs.TryGetValue((blockNo, subNo), out var sub))
        {
            sub = new CellSubBlock { BlockNumber = subNo, GroupType = GroupTypeEnum.InteriorCellSubBlock };
            blk.SubBlocks.Add(sub);
            subs[(blockNo, subNo)] = sub;
        }
        sub.Cells.Add(cell);
    }

    // W5-ext (Kerem): locate an exterior cell inside any worldspace, returning the cell + its
    // worldspace + the exact block/subblock coords the master uses (replicate them in the override
    // so no exterior grid math is needed — match the source structure verbatim).
    static (ICellGetter cell, IWorldspaceGetter ws, int bx, int by, int sx, int sy)? FindExteriorCell(
        IFallout4ModGetter src, FormKey cellKey)
    {
        foreach (var w in src.Worldspaces)
            foreach (var blk in w.SubCells)
                foreach (var sub in blk.Items)
                    foreach (var c in sub.Items)
                        if (c.FormKey == cellKey)
                            return (c, w, blk.BlockNumberX, blk.BlockNumberY,
                                    sub.BlockNumberX, sub.BlockNumberY);
        return null;
    }

    // W5-ext: nest an exterior cell override under a worldspace override at the given block/subblock,
    // creating (and caching) the worldspace + block + subblock groups as needed.
    // The WRLD override MUST carry the master's record data. FO4 resolves the winning override of a
    // record WHOLESALE (no subrecord-level merge), so a bare `new Worldspace(wsKey)` override — which
    // has no subrecords — wipes the worldspace's map data (MNAM), water, climate, parent and LOD =>
    // a BROKEN Pip-Boy world map (user-reported). DeepCopy the master WRLD record but mask off the
    // cell children (SubCells = the thousands of master exterior cells; TopCell = the persistent
    // cell): we only attach our one added cell, not re-author the whole worldspace.
    static void PlaceExteriorCell(Fallout4Mod m, Cell ov, IWorldspaceGetter srcWs, int bx, int by, int sx, int sy,
        Dictionary<FormKey, Worldspace> wsCache,
        Dictionary<(FormKey, int, int), WorldspaceBlock> blkCache,
        Dictionary<(FormKey, int, int, int, int), WorldspaceSubBlock> subCache)
    {
        var wsKey = srcWs.FormKey;
        if (!wsCache.TryGetValue(wsKey, out var ws))
        {
            ws = srcWs.DeepCopy(new Worldspace.TranslationMask(defaultOn: true)
            {
                SubCells = false,         // skip the master's exterior cell tree (we add only our cell)
                TopCell = false,          // skip the worldspace persistent cell (inherited from master)
                LargeReferences = false,  // DROP large-ref grid: copying the master's whole list bloats
                                          // the plugin (~900KB) and risks FO4's large-reference bug
                                          // (distant objects flicker/vanish). Stripping large refs from
                                          // a worldspace override is established practice; the engine
                                          // keeps the master's. The MAP data (MNAM) etc. ARE direct WRLD
                                          // fields and STAY copied — that's what fixes the broken map.
            });
            ws.SubCells.Clear();    // DeepCopy with SubCells masked leaves it empty; ensure so
            m.Worldspaces.Add(ws);
            wsCache[wsKey] = ws;
        }
        var bk = (wsKey, bx, by);
        if (!blkCache.TryGetValue(bk, out var blk))
        {
            blk = new WorldspaceBlock { BlockNumberX = (short)bx, BlockNumberY = (short)by,
                GroupType = GroupTypeEnum.ExteriorCellBlock };
            ws.SubCells.Add(blk);
            blkCache[bk] = blk;
        }
        var sk = (wsKey, bx, by, sx, sy);
        if (!subCache.TryGetValue(sk, out var sub))
        {
            sub = new WorldspaceSubBlock { BlockNumberX = (short)sx, BlockNumberY = (short)sy,
                GroupType = GroupTypeEnum.ExteriorCellSubBlock };
            blk.Items.Add(sub);
            subCache[sk] = sub;
        }
        sub.Items.Add(ov);
    }

    // A-disk (RE finding, 2026-06-20): author an ISOLATED INTERIOR navmesh on a NEW cell. Mutagen
    // fully models NAVM — a rectangular floor auto-triangulates into a grid: (nx+1)*(ny+1) vertices,
    // 2 triangles per grid cell, with proper EDGE-LINK adjacency (a shared interior edge links to the
    // neighbour triangle index; a boundary edge = -1). DISK-PROVEN: construct->write->reopen
    // round-trips. The §4 FREEZE GATE is in-game pathing (CrcHash validate? GridArrays needed? NAVI
    // map-info needed for interior? does the NPC actually path?) — verified via fo4_run_ingame_test
    // before this is trusted. EXTERIOR/worldspace navmesh stays CK-gated (23-mesh neighbour stitch).
    static bool AddNavmesh(Fallout4Mod m, Cell cell, NavmeshSpec nv, out string err)
    {
        err = "";
        var f = nv.Floor;
        if (f is null || f.Count != 4) { err = "navmesh.floor must be [minX,minY,maxX,maxY]"; return false; }
        float minX = f[0], minY = f[1], maxX = f[2], maxY = f[3];
        if (maxX <= minX || maxY <= minY) { err = "navmesh.floor max must exceed min"; return false; }
        float z = nv.Z ?? 0f;
        int nx = Math.Max(1, nv.DivisionsX ?? 1);
        int ny = Math.Max(1, nv.DivisionsY ?? 1);

        var navm = new NavigationMesh(m);
        var geo = new NavmeshGeometry { NavmeshVersion = 15 };

        // vertex grid (row-major: idx = j*(nx+1) + i)
        for (int j = 0; j <= ny; j++)
            for (int i = 0; i <= nx; i++)
                geo.Vertices.Add(new Noggog.P3Float(
                    minX + (maxX - minX) * i / nx,
                    minY + (maxY - minY) * j / ny, z));

        int Vidx(int i, int j) => j * (nx + 1) + i;
        int Ta(int i, int j) => 2 * (j * nx + i);       // triangle A index of cell (i,j)
        int Tb(int i, int j) => 2 * (j * nx + i) + 1;   // triangle B index of cell (i,j)
        short Lnk(bool boundary, int tri) => boundary ? (short)-1 : (short)tri;

        for (int j = 0; j < ny; j++)
            for (int i = 0; i < nx; i++)
            {
                int v00 = Vidx(i, j), v10 = Vidx(i + 1, j), v01 = Vidx(i, j + 1), v11 = Vidx(i + 1, j + 1);
                // Triangle A = (v00, v10, v11): edges bottom / right / diagonal
                geo.Triangles.Add(new NavmeshTriangle
                {
                    Vertices = new Noggog.P3Int16((short)v00, (short)v10, (short)v11),
                    EdgeLink_0_1 = Lnk(j == 0, Tb(i, j - 1)),       // bottom -> below cell's B
                    EdgeLink_1_2 = Lnk(i == nx - 1, Tb(i + 1, j)),  // right  -> right cell's B
                    EdgeLink_2_0 = (short)Tb(i, j),                 // diagonal -> same cell's B
                    Height = z,
                });
                // Triangle B = (v00, v11, v01): edges diagonal / top / left
                geo.Triangles.Add(new NavmeshTriangle
                {
                    Vertices = new Noggog.P3Int16((short)v00, (short)v11, (short)v01),
                    EdgeLink_0_1 = (short)Ta(i, j),                 // diagonal -> same cell's A
                    EdgeLink_1_2 = Lnk(j == ny - 1, Ta(i, j + 1)),  // top  -> above cell's A
                    EdgeLink_2_0 = Lnk(i == 0, Ta(i - 1, j)),       // left -> left cell's A
                    Height = z,
                });
            }

        geo.GridMin = new Noggog.P3Float(minX, minY, z);
        geo.GridMax = new Noggog.P3Float(maxX, maxY, z);
        // A-in-game RE (2026-06-20): the engine builds an N×N pathing grid at data-load from GridSize +
        // the flattened GridArrays.GridCell int16[] (Mutagen reads GridCell greedily, no count, so a
        // mismatch round-trips on disk but OOB-crashes the engine). Ground-truthed against vanilla
        // DLCRobot interior navmeshes (navmesh-dump verb): a valid record uses GridSize=1 (a 1×1 grid =
        // one cell holding every triangle), GridMaxDistance = GridMax-GridMin, and the single grid cell
        // is encoded as [triCount : uint32 (two int16)] followed by triCount triangle indices — verified
        // by exact byte count (4-tri mesh -> 2+4 = 6 shorts; 2-tri -> 2+2 = 4). CrcHash is a fixed
        // constant in vanilla too (2783551548), not a per-record hash, so it is NOT the gate.
        geo.GridSize = 1;
        geo.GridMaxDistance = new Noggog.P2Float(maxX - minX, maxY - minY);
        var grid = new NavmeshGridArray();
        int triCount = geo.Triangles.Count;
        grid.GridCell.Add((short)(triCount & 0xFFFF));
        grid.GridCell.Add((short)((triCount >> 16) & 0xFFFF));
        for (short ti = 0; ti < triCount; ti++) grid.GridCell.Add(ti);
        geo.GridArrays = grid;
        geo.Parent = new CellNavmeshParent();
        ((CellNavmeshParent)geo.Parent).Parent.SetTo(cell.FormKey);
        navm.NavmeshGeometry = geo;
        cell.NavigationMeshes.Add(navm);

        // A-in-game RE (2026-06-20): a NAVM with no NAVI entry CTDs at load — the engine builds its
        // pathing graph from the top-level NavigationMeshInfoMap (NAVI) and dereferences a per-NAVM
        // map-info; a missing entry => null-deref => hard crash (controlled 2-launch experiment proved
        // the NAVM record is the crash cause). NAVI is a singleton top-level GRUP: get-or-create it,
        // then append one NavigationMapInfo linking this NAVM to its parent cell, with an Island
        // (bounding box + the mesh verts/tris mirrored) so the high-level graph has geometry to load.
        // RE toggle (navi=false) lets us A/B whether a grid-correct NAVM needs a NAVI entry at all.
        // GROUND TRUTH (navi-dump vs vanilla): NAVI is the SINGLETON global record 000FF1:Fallout4.esm
        // — every navmesh-adding plugin OVERRIDES it and the engine MERGES the MapInfo lists additively
        // across the load order (that is how CK navmesh mods coexist). Authoring a NEW NAVI with our own
        // FormID (the earlier bug) is invalid -> load CTD; authoring NO NAVI loads but CTDs the moment an
        // actor tries to path (the pathfinder dereferences the missing map-info). So we author an
        // OVERRIDE of 000FF1 holding just our one entry, with the vanilla magic constants (Unknown=32,
        // Unknown2=0xA5F0..; same dword as the NAVM CrcHash).
        if (nv.Navi == false) return true;
        var naviKey = Mutagen.Bethesda.Plugins.FormKey.Factory("000FF1:Fallout4.esm");
        var navi = m.NavigationMeshInfoMaps.RecordCache.Items.FirstOrDefault(x => x.FormKey == naviKey);
        if (navi is null)
        {
            navi = new NavigationMeshInfoMap(naviKey, Fallout4Release.Fallout4) { NavMeshVersion = 15 };
            m.NavigationMeshInfoMaps.RecordCache.Add(navi);
        }
        var info = new NavigationMapInfo();
        info.NavigationMesh.SetTo(navm.FormKey);
        var cp = new NavigationMapInfoCellParent();
        cp.Cell.SetTo(cell.FormKey);
        info.Parent = cp;
        info.Unknown = 32;
        info.Unknown2 = unchecked((int)2783551548u);
        var island = new IslandData
        {
            Min = new Noggog.P3Float(minX, minY, z),
            Max = new Noggog.P3Float(maxX, maxY, z),
        };
        foreach (var v in geo.Vertices) island.Vertices.Add(v);
        foreach (var t in geo.Triangles) island.Triangles.Add(t.Vertices);
        info.Island = island;
        info.Point = new Noggog.P3Float((minX + maxX) / 2f, (minY + maxY) / 2f, z);
        navi.MapInfos.Add(info);
        return true;
    }

    var made = new List<Dictionary<string, object?>>();
    // W4: interior cells live in a block hierarchy (Cells = ListGroup<CellBlock> ->
    // CellSubBlock -> Cell), NOT a flat group. Interior block placement is by FormID:
    // block = id % 10, subblock = (id/10) % 10 (CK/xEdit rule, verified vs
    // SanctuaryRosaHouse 01F398 -> block 6 sub 9). Merge cells sharing a block/subblock.
    var cellBlocks = new Dictionary<int, CellBlock>();
    var cellSubBlocks = new Dictionary<(int, int), CellSubBlock>();
    // W5: cache opened source plugins (cellOverride DeepCopy source) by path.
    var sourceCache = new Dictionary<string, IFallout4ModGetter>();
    // W5-ext (Kerem): exterior cell-override caches — worldspace override + its block/subblock
    // groups, keyed so multiple exterior overrides into the same worldspace/block share structure.
    var wsOverrides = new Dictionary<FormKey, Worldspace>();
    var wsBlocks = new Dictionary<(FormKey, int, int), WorldspaceBlock>();
    var wsSubBlocks = new Dictionary<(FormKey, int, int, int, int), WorldspaceSubBlock>();
    foreach (var r in records)
    {
        // editorId is required for new records; an override (cell / leveled-item) identifies its
        // target by FormKey (the master's editorId carries forward via DeepCopy), so it needs none.
        if (string.IsNullOrWhiteSpace(r.EditorId)
            && r.Type?.Trim().ToLowerInvariant() is not ("celloverride" or "leveleditemoverride"))
            return Fail("record missing editorId");
        string formKey;
        switch (r.Type?.Trim().ToLowerInvariant())
        {
            case "npc":
            {
                var npc = mod.Npcs.AddNew(r.EditorId);
                if (r.Name is { } n) npc.Name = n;
                if (!string.IsNullOrWhiteSpace(r.Race))
                {
                    if (!TryKey(r.Race, out var rk, out var e)) return Fail(e);
                    npc.Race.SetTo(rk);
                }
                if (!string.IsNullOrWhiteSpace(r.Class))
                {
                    if (!TryKey(r.Class, out var ck, out var e)) return Fail(e);
                    npc.Class.SetTo(ck);
                }
                if (r.Factions is { Count: > 0 })
                {
                    foreach (var f in r.Factions)
                    {
                        if (!TryKey(f.Faction, out var fk, out var e)) return Fail(e);
                        var rp = new RankPlacement { Rank = (sbyte)f.Rank };
                        rp.Faction.SetTo(fk);
                        npc.Factions.Add(rp);
                    }
                }
                // W3b — scalar FormLink fields (mirror Race/Class above).
                if (!string.IsNullOrWhiteSpace(r.Voice))
                {
                    if (!TryKey(r.Voice, out var k, out var e)) return Fail(e);
                    npc.Voice.SetTo(k);
                }
                if (!string.IsNullOrWhiteSpace(r.CombatStyle))
                {
                    if (!TryKey(r.CombatStyle, out var k, out var e)) return Fail(e);
                    npc.CombatStyle.SetTo(k);
                }
                if (!string.IsNullOrWhiteSpace(r.DefaultOutfit))
                {
                    if (!TryKey(r.DefaultOutfit, out var k, out var e)) return Fail(e);
                    npc.DefaultOutfit.SetTo(k);
                }
                if (!string.IsNullOrWhiteSpace(r.AttackRace))
                {
                    if (!TryKey(r.AttackRace, out var k, out var e)) return Fail(e);
                    npc.AttackRace.SetTo(k);
                }
                if (!string.IsNullOrWhiteSpace(r.Skin))
                {
                    if (!TryKey(r.Skin, out var k, out var e)) return Fail(e);
                    npc.Skin.SetTo(k);
                }
                // W3b — AI personality enums (mirror faction-flag Enum.TryParse; non-nullable).
                if (!string.IsNullOrWhiteSpace(r.Aggression))
                {
                    if (!Enum.TryParse<Npc.AggressionType>(r.Aggression, true, out var a))
                        return Fail($"bad aggression '{r.Aggression}' (Unaggressive|Aggressive|VeryAggressive|Frenzied)");
                    npc.Aggression = a;
                }
                if (!string.IsNullOrWhiteSpace(r.Confidence))
                {
                    if (!Enum.TryParse<Npc.ConfidenceType>(r.Confidence, true, out var c))
                        return Fail($"bad confidence '{r.Confidence}' (Cowardly|Cautious|Average|Brave|Foolhardy)");
                    npc.Confidence = c;
                }
                if (!string.IsNullOrWhiteSpace(r.Assistance))
                {
                    if (!Enum.TryParse<Npc.AssistanceType>(r.Assistance, true, out var asg))
                        return Fail($"bad assistance '{r.Assistance}' (HelpsNobody|HelpsAllies|HelpsFriendsAndAllies)");
                    npc.Assistance = asg;
                }
                if (!string.IsNullOrWhiteSpace(r.Responsibility))
                {
                    if (!Enum.TryParse<Npc.ResponsibilityType>(r.Responsibility, true, out var rsp))
                        return Fail($"bad responsibility '{r.Responsibility}' (AnyCrime|ViolenceAgainstEnemies|PropertyCrimeOnly|NoCrime)");
                    npc.Responsibility = rsp;
                }
                if (!string.IsNullOrWhiteSpace(r.Mood))
                {
                    if (!Enum.TryParse<Npc.MoodType>(r.Mood, true, out var md))
                        return Fail($"bad mood '{r.Mood}' (Neutral|Angry|Fear|Happy|Sad|Surprised|Puzzled|Disgusted)");
                    npc.Mood = md;
                }
                // W3b — keywords (mirror ARMO; Keywords is an optional KWDA subrecord -> guard).
                if (r.Keywords is { Count: > 0 })
                {
                    npc.Keywords ??= new();
                    foreach (var kw in r.Keywords)
                    {
                        if (!TryKey(kw, out var kk, out var e)) return Fail(e);
                        npc.Keywords.Add(new FormLink<IKeywordGetter>(kk));
                    }
                }
                // W3b — inventory (CNTO: item FormLink + count).
                if (r.Inventory is { Count: > 0 })
                {
                    npc.Items ??= new();
                    foreach (var it in r.Inventory)
                    {
                        if (it.Count < 0) return Fail($"item count out of range: {it.Count}");
                        if (!TryKey(it.Item, out var ik, out var e)) return Fail(e);
                        var entry = new ContainerEntry { Item = new ContainerItem { Count = it.Count } };
                        entry.Item.Item.SetTo(ik);
                        npc.Items.Add(entry);
                    }
                }
                // W3b — perks (PerkPlacement: perk FormLink + rank byte).
                if (r.Perks is { Count: > 0 })
                {
                    npc.Perks ??= new();
                    foreach (var pk in r.Perks)
                    {
                        if (pk.Rank < 0 || pk.Rank > byte.MaxValue)
                            return Fail($"perk rank out of range (0-255): {pk.Rank}");
                        if (!TryKey(pk.Perk, out var pkk, out var e)) return Fail(e);
                        var pp = new PerkPlacement { Rank = (byte)pk.Rank };
                        pp.Perk.SetTo(pkk);
                        npc.Perks.Add(pp);
                    }
                }
                // W3c — template-chain: DefaultTemplate FormLink + UseTemplateActors bitfield.
                // FaceGen inheritance: DefaultTemplate (NPC_ or LVLN) + Traits flag = inherited,
                // dark-face-free appearance. TemplateActorType is a non-[Flags] Int32, so OR the
                // named bits ourselves and cast back (mirrors the quest-flag accumulator pattern).
                if (!string.IsNullOrWhiteSpace(r.DefaultTemplate))
                {
                    if (!TryKey(r.DefaultTemplate, out var k, out var e)) return Fail(e);
                    npc.DefaultTemplate.SetTo(k);
                }
                if (r.UseTemplateActors is { Count: > 0 })
                {
                    var bits = 0;
                    foreach (var fl in r.UseTemplateActors)
                    {
                        if (!Enum.TryParse<Npc.TemplateActorType>(fl, true, out var tf))
                            return Fail($"bad template flag '{fl}' (Traits|Stats|Factions|SpellList|AiData|AiPackages|ModelOrAnimation|BaseData|Inventory|Script|DefPackList|AttackData|Keywords)");
                        bits |= (int)tf;
                    }
                    npc.UseTemplateActors = (Npc.TemplateActorType)bits;
                }
                // W7 — bind existing AI packages (PACK FormLinks) so a placed NPC behaves
                // (patrol/sandbox/guard). Ordered list = priority. Authoring a NEW PACK with a
                // template Data input-map is the deferred research gate (see type=package).
                if (r.Packages is { Count: > 0 })
                    foreach (var pk in r.Packages)
                    { if (!TryKey(pk, out var pkk, out var e)) return Fail(e); npc.Packages.Add(new FormLink<IPackageGetter>(pkk)); }
                // OS-14 — actor flags (Essential/Protected/Invulnerable/...). A quest-critical NPC
                // without Essential/Protected can die before turn-in -> soft-lock. OR the named bits
                // into npc.Flags (mirror the faction-flag accumulator at faction:2316).
                if (r.NpcFlags is { Count: > 0 })
                    foreach (var fn in r.NpcFlags)
                    {
                        if (!Enum.TryParse<Npc.Flag>(fn, true, out var nf))
                            return Fail($"bad npc flag '{fn}' (Essential|Protected|Invulnerable|Unique|Respawn|Summonable|DoesNotBleed|IsGhost|...)");
                        npc.Flags |= nf;
                    }
                formKey = npc.FormKey.ToString();
                break;
            }
            case "armor":
            {
                var armo = mod.Armors.AddNew(r.EditorId);
                if (r.Name is { } n) armo.Name = n;
                if (r.Value is { } val)
                {
                    if (val < 0) return Fail($"armor value out of range: {val}");
                    armo.Value = val;
                }
                if (r.Weight is { } wt)
                {
                    if (wt < 0) return Fail($"armor weight out of range: {wt}");
                    armo.Weight = wt;
                }
                if (r.ArmorRating is { } ar)
                {
                    if (ar < 0 || ar > ushort.MaxValue)
                        return Fail($"armorRating out of range (0-65535): {ar}");
                    armo.ArmorRating = (ushort)ar;
                }
                if (r.Keywords is { Count: > 0 })
                {
                    armo.Keywords ??= new();
                    foreach (var kw in r.Keywords)
                    {
                        if (!TryKey(kw, out var kk, out var e)) return Fail(e);
                        armo.Keywords.Add(new FormLink<IKeywordGetter>(kk));
                    }
                }
                if (r.BipedSlots is { Count: > 0 })
                {
                    var tmpl = armo.BipedBodyTemplate ??= new BipedBodyTemplate();
                    foreach (var sn in r.BipedSlots)
                    {
                        if (!Enum.TryParse<BipedObjectFlag>(sn, true, out var bf))
                            return Fail($"bad biped slot '{sn}'");
                        tmpl.FirstPersonFlags |= bf;
                    }
                }
                // Kerem-polish: ARMA addon links + Race = the worn-mesh render chain. An ARMO
                // with an empty Armatures list renders NOTHING equipped (the invisible-reward bug).
                // Referencing existing (vanilla) ARMA addons gives a visible armor with zero new art;
                // Race must match the addon's race (HumanRace 013746). MaleWorldModel etc. live on the
                // referenced ARMA, so no model is authored here.
                if (r.Armatures is { Count: > 0 })
                {
                    foreach (var aa in r.Armatures)
                    {
                        if (!TryKey(aa, out var aak, out var e)) return Fail(e);
                        var aam = new ArmorAddonModel { AddonIndex = 0 };
                        aam.ArmorAddon.SetTo(aak);
                        armo.Armatures.Add(aam);
                    }
                }
                if (!string.IsNullOrWhiteSpace(r.Race))
                {
                    if (!TryKey(r.Race, out var rk, out var e)) return Fail(e);
                    armo.Race.SetTo(rk);
                }
                formKey = armo.FormKey.ToString();
                break;
            }
            case "weapon":
            {
                // OS-01 — WEAP base record. Stats (DNAM) live DIRECTLY on the record (not a nested
                // WeaponData like xEdit): BaseDamage/Capacity are UInt16; Speed/Reach/Min/MaxRange
                // Single; Value UInt32. FormLinks: Ammo (AMMO), Attack/Equip sound (SNDR). Model +
                // OBND + Keywords reuse the shared item idiom (book/misc). OMOD attach-mod authoring
                // is a separate follow-up — AttachParentSlots just exposes the AKEY slot keywords.
                var weap = mod.Weapons.AddNew(r.EditorId);
                if (r.Name is { } n) weap.Name = n;
                if (r.Value is { } val)
                {
                    if (val < 0) return Fail($"weapon value out of range: {val}");
                    weap.Value = (uint)val;        // WEAP Value is UInt32 (Armor.Value is Int32)
                }
                if (r.Weight is { } wt)
                {
                    if (wt < 0) return Fail($"weapon weight out of range: {wt}");
                    weap.Weight = wt;
                }
                if (r.BaseDamage is { } bd)
                {
                    if (bd < 0 || bd > ushort.MaxValue) return Fail($"baseDamage out of range (0-65535): {bd}");
                    weap.BaseDamage = (ushort)bd;
                }
                if (r.Speed is { } sp) { if (sp < 0) return Fail($"weapon speed out of range: {sp}"); weap.Speed = sp; }
                if (r.Reach is { } rch) { if (rch < 0) return Fail($"weapon reach out of range: {rch}"); weap.Reach = rch; }
                if (r.MinRange is { } mnr) { if (mnr < 0) return Fail($"weapon minRange out of range: {mnr}"); weap.MinRange = mnr; }
                if (r.MaxRange is { } mxr) { if (mxr < 0) return Fail($"weapon maxRange out of range: {mxr}"); weap.MaxRange = mxr; }
                if (r.AmmoCapacity is { } cap)
                {
                    if (cap < 0 || cap > ushort.MaxValue) return Fail($"ammoCapacity out of range (0-65535): {cap}");
                    weap.Capacity = (ushort)cap;
                }
                if (!string.IsNullOrWhiteSpace(r.Ammo))
                { if (!TryKey(r.Ammo, out var k, out var e)) return Fail(e); weap.Ammo.SetTo(k); }
                if (!string.IsNullOrWhiteSpace(r.AttackSound))
                { if (!TryKey(r.AttackSound, out var k, out var e)) return Fail(e); weap.AttackSound.SetTo(k); }
                if (!string.IsNullOrWhiteSpace(r.EquipSound))
                { if (!TryKey(r.EquipSound, out var k, out var e)) return Fail(e); weap.EquipSound.SetTo(k); }
                if (!string.IsNullOrWhiteSpace(r.AnimationType))
                {
                    if (!Enum.TryParse<Weapon.AnimationTypes>(r.AnimationType, true, out var at))
                        return Fail($"bad animationType '{r.AnimationType}' (HandToHandMelee|OneHandSword|OneHandDagger|OneHandAxe|OneHandMace|TwoHandSword|TwoHandAxe|Bow|Staff|Gun|Grenade|Mine)");
                    weap.AnimationType = at;
                }
                if (r.Keywords is { Count: > 0 })
                {
                    weap.Keywords ??= new();
                    foreach (var kw in r.Keywords)
                    { if (!TryKey(kw, out var kk, out var e)) return Fail(e); weap.Keywords.Add(new FormLink<IKeywordGetter>(kk)); }
                }
                if (r.AttachParentSlots is { Count: > 0 })
                {
                    weap.AttachParentSlots ??= new();
                    foreach (var ap in r.AttachParentSlots)
                    { if (!TryKey(ap, out var apk, out var e)) return Fail(e); weap.AttachParentSlots.Add(new FormLink<IKeywordGetter>(apk)); }
                }
                if (r.Model is { } wmdl)
                {
                    var m = new Model { File = wmdl };
                    if (r.MaterialSwap is { } msw)
                    {
                        if (!TryKey(msw, out var mk, out var me)) return Fail(me);
                        m.MaterialSwap.SetTo(mk);
                    }
                    weap.Model = m;
                }
                // OBND — a non-zero box so the Pip-Boy/Inspect preview frames the weapon (zero box =
                // blank preview, same trap as MISC). Default = a generic rifle box; spec overrides.
                {
                    var ob = r.ObjectBounds ?? new short[] { -30, -5, -10, 30, 5, 10 };
                    if (ob.Length != 6) return Fail($"objectBounds needs 6 ints [x1,y1,z1,x2,y2,z2], got {ob.Length}");
                    weap.ObjectBounds.First = new Noggog.P3Int16(ob[0], ob[1], ob[2]);
                    weap.ObjectBounds.Second = new Noggog.P3Int16(ob[3], ob[4], ob[5]);
                }
                formKey = weap.FormKey.ToString();
                break;
            }
            case "quest":
            {
                var qst = mod.Quests.AddNew(r.EditorId);
                if (r.Name is { } n) qst.Name = n;
                // editorId -> FormKey of topics authored below, so Faz 2.1e scene
                // actions can reference a topic by its editorId within the same spec.
                var topicsByEid = new Dictionary<string, FormKey>(StringComparer.OrdinalIgnoreCase);
                if (!string.IsNullOrWhiteSpace(r.QuestType))
                {
                    if (!Enum.TryParse<Quest.TypeEnum>(r.QuestType, true, out var qt))
                        return Fail($"bad questType '{r.QuestType}'");
                    (qst.Data ??= new QuestData()).Type = qt;
                }
                if (r.Flags is { Count: > 0 })
                {
                    qst.Data ??= new QuestData();
                    foreach (var fn in r.Flags)
                    {
                        if (!Enum.TryParse<Quest.Flag>(fn, true, out var fl))
                            return Fail($"bad quest flag '{fn}'");
                        qst.Data.Flags |= fl;
                    }
                }
                if (r.Stages is { Count: > 0 })
                {
                    foreach (var s in r.Stages)
                    {
                        if (s.Index < 0 || s.Index > ushort.MaxValue)
                            return Fail($"stage index out of range: {s.Index}");
                        var stage = new QuestStage { Index = (ushort)s.Index };
                        // RunOnStart = INDX flag 0x02: the engine runs this stage's fragment
                        // when the quest starts. Real CK startup stages set it (Spriggit ground-truth).
                        if (s.RunOnStart) stage.Flags |= QuestStage.Flag.RunOnStart;
                        if (!string.IsNullOrEmpty(s.LogEntry))
                            // Flags MUST be non-null to emit the QSDT subrecord — the mandatory
                            // marker that opens every QuestLogEntry. Default (Flags=null) writes a
                            // CNAM with no QSDT (CNAM-orphan), which the game engine can't parse →
                            // quest never reaches running-state → stage fragment never binds.
                            // (QuestLogEntry.Flag)0 = no CompleteQuest/FailQuest = a plain journal
                            // entry; QSDT byte 0x00 matches CK's empty-flags log entry exactly.
                            stage.LogEntries.Add(new QuestLogEntry { Entry = s.LogEntry, Flags = default(QuestLogEntry.Flag) });
                        qst.Stages.Add(stage);
                    }
                }
                if (r.Objectives is { Count: > 0 })
                {
                    foreach (var o in r.Objectives)
                    {
                        if (o.Index < 0 || o.Index > ushort.MaxValue)
                            return Fail($"objective index out of range: {o.Index}");
                        var obj = new QuestObjective { Index = (ushort)o.Index };
                        if (o.Text is { } t) obj.DisplayText = t;
                        // W2: objective flags (QuestObjective.Flag — nullable [Flags] enum).
                        if (o.Flags is { Count: > 0 })
                        {
                            QuestObjective.Flag of = 0;
                            foreach (var fn in o.Flags)
                            {
                                if (!Enum.TryParse<QuestObjective.Flag>(fn, true, out var f))
                                    return Fail($"bad objective flag '{fn}' (OrWithPrevious|NoStatsTracking)");
                                of |= f;
                            }
                            obj.Flags = of;
                        }
                        // W2: QSTA targets — AliasID (int, like SceneActor.ID) + TargetFlag +
                        // optional LCRT keyword + optional conditions (reuse the 2.1b builder).
                        if (o.Targets is { Count: > 0 })
                        {
                            // Targets is an init-only ExtendedList (ctor-initialized) -> Add directly.
                            foreach (var tg in o.Targets)
                            {
                                var qt = new QuestObjectiveTarget { AliasID = tg.AliasId };
                                if (tg.Flags is { Count: > 0 })
                                    foreach (var fn in tg.Flags)
                                    {
                                        if (!Enum.TryParse<Quest.TargetFlag>(fn, true, out var f))
                                            return Fail($"bad objective-target flag '{fn}' (CompassMarkerIgnoresLocks|Hostile|UseStraightLinePathing)");
                                        qt.Flags |= f;
                                    }
                                if (!string.IsNullOrWhiteSpace(tg.Keyword))
                                {
                                    if (!TryKey(tg.Keyword, out var kk, out var e)) return Fail(e);
                                    qt.Keyword.SetTo(kk);
                                }
                                if (tg.Conditions is { Count: > 0 })
                                    foreach (var cs in tg.Conditions)
                                    {
                                        if (!BuildCondition(cs, out var cond, out var ce)) return Fail(ce);
                                        qt.Conditions.Add(cond);  // init-only ExtendedList, ctor-initialized
                                    }
                                obj.Targets.Add(qt);
                            }
                        }
                        qst.Objectives.Add(obj);
                    }
                }
                // Faz 2.1: quest-nested dialogue. Each topic is a DIAL (DialogTopic,
                // its own FormKey from the mod allocator), back-linked to this quest;
                // each response is an INFO (DialogResponses) holding the spoken lines
                // (DialogResponse — a sub-record, not a major record, hence no FormKey).
                //
                // Kerem-polish: pre-allocate DLBR branches BEFORE topics so a topic can link to
                // its branch (topic.Branch); the branch's StartingTopic is resolved AFTER topics
                // are built (topicsByEid populated). This breaks the topic<->branch reference cycle.
                var branchesByEid = new Dictionary<string, FormKey>(StringComparer.OrdinalIgnoreCase);
                var branchObjs = new List<(DialogBranch branch, string? startingTopic)>();
                if (r.Branches is { Count: > 0 })
                {
                    foreach (var b in r.Branches)
                    {
                        var branch = string.IsNullOrWhiteSpace(b.EditorId)
                            ? new DialogBranch(mod) : new DialogBranch(mod, b.EditorId);
                        branch.Quest.SetTo(qst.FormKey);
                        var catName = string.IsNullOrWhiteSpace(b.Category) ? "Player" : b.Category;
                        if (!Enum.TryParse<DialogBranch.CategoryType>(catName, true, out var cat))
                            return Fail($"bad branch category '{catName}'");
                        branch.Category = cat;
                        DialogBranch.Flag bff = 0;
                        var bflags = b.Flags is { Count: > 0 } ? b.Flags : new List<string> { "TopLevel" };
                        foreach (var fn in bflags)
                        {
                            if (!Enum.TryParse<DialogBranch.Flag>(fn, true, out var f))
                                return Fail($"bad branch flag '{fn}'");
                            bff |= f;
                        }
                        branch.Flags = bff;
                        if (!string.IsNullOrWhiteSpace(b.EditorId)) branchesByEid[b.EditorId] = branch.FormKey;
                        branchObjs.Add((branch, b.StartingTopic));
                    }
                }
                if (r.Topics is { Count: > 0 })
                {
                    foreach (var t in r.Topics)
                    {
                        var topic = string.IsNullOrWhiteSpace(t.EditorId)
                            ? new DialogTopic(mod) : new DialogTopic(mod, t.EditorId);
                        topic.Quest.SetTo(qst.FormKey);   // dialogue belongs to its quest
                        if (!string.IsNullOrWhiteSpace(t.EditorId)) topicsByEid[t.EditorId] = topic.FormKey;
                        if (t.Name is { } tn) topic.Name = tn;
                        if (!string.IsNullOrWhiteSpace(t.Subtype))
                        {
                            if (!Enum.TryParse<DialogTopic.SubtypeEnum>(t.Subtype, true, out var st))
                                return Fail($"bad topic subtype '{t.Subtype}'");
                            topic.Subtype = st;
                        }
                        if (!string.IsNullOrWhiteSpace(t.Category))
                        {
                            if (!Enum.TryParse<DialogTopic.CategoryEnum>(t.Category, true, out var cat))
                                return Fail($"bad topic category '{t.Category}'");
                            topic.Category = cat;
                        }
                        // Kerem-polish: link this topic to its owning DLBR branch (in-spec editorId
                        // or a raw FormKey) so it surfaces under the player dialogue wheel.
                        if (!string.IsNullOrWhiteSpace(t.Branch))
                        {
                            if (branchesByEid.TryGetValue(t.Branch, out var bk))
                                topic.Branch.SetTo(bk);
                            else
                            {
                                if (!TryKey(t.Branch, out var bk2, out var be)) return Fail(be);
                                topic.Branch.SetTo(bk2);
                            }
                        }
                        if (t.Responses is { Count: > 0 })
                        {
                            foreach (var resp in t.Responses)
                            {
                                // OS-04: optionally pin the INFO FormKey so the TIF_<eid>_<8hex>
                                // fragment-script name stays stable across re-authoring (else the
                                // allocator mints a fresh ID and orphans the .pex).
                                DialogResponses info;
                                if (!string.IsNullOrWhiteSpace(resp.FormKey))
                                {
                                    if (!TryKey(resp.FormKey, out var ifk, out var ife)) return Fail(ife);
                                    if (ifk.ModKey != mod.ModKey)
                                        return Fail($"info formKey {resp.FormKey} is not in this mod's slot ({mod.ModKey})");
                                    info = new DialogResponses(ifk, Fallout4Release.Fallout4);
                                }
                                else info = new DialogResponses(mod);
                                if (resp.Prompt is { } p) info.Prompt = p;
                                if (!string.IsNullOrWhiteSpace(resp.Speaker))
                                {
                                    if (!TryKey(resp.Speaker, out var spk, out var e)) return Fail(e);
                                    info.Speaker.SetTo(spk);
                                }
                                if (resp.Lines is { Count: > 0 })
                                {
                                    byte lineNo = 1;
                                    foreach (var line in resp.Lines)
                                    {
                                        if (line.ResponseNumber < 0 || line.ResponseNumber > byte.MaxValue)
                                            return Fail($"responseNumber out of range: {line.ResponseNumber}");
                                        var dr = new DialogResponse
                                        {
                                            ResponseNumber = line.ResponseNumber > 0 ? (byte)line.ResponseNumber : lineNo,
                                        };
                                        if (line.Text is { } txt) dr.Text = txt;
                                        if (!string.IsNullOrWhiteSpace(line.Emotion))
                                        {
                                            if (!TryKey(line.Emotion, out var em, out var e)) return Fail(e);
                                            dr.Emotion.SetTo(em);
                                        }
                                        info.Responses.Add(dr);
                                        lineNo++;
                                    }
                                }
                                // Faz 2.1b: INFO conditions gate when this response fires.
                                if (resp.Conditions is { Count: > 0 })
                                {
                                    foreach (var cs in resp.Conditions)
                                    {
                                        if (!BuildCondition(cs, out var cond, out var ce)) return Fail(ce);
                                        info.Conditions.Add(cond);
                                    }
                                }
                                // P0: script-free stage advance — picking this wheel line sets the
                                // owning quest's stage with no Papyrus (SNAM). -1 = unused.
                                if (resp.SetParentQuestStage is { } sps && (sps.OnBegin is not null || sps.OnEnd is not null))
                                {
                                    info.SetParentQuestStage = new DialogSetParentQuestStage
                                    {
                                        OnBegin = (short)(sps.OnBegin ?? -1),
                                        OnEnd = (short)(sps.OnEnd ?? -1),
                                    };
                                }
                                // OS-04: TIF VMAD fragment — the line runs arbitrary Papyrus
                                // (Fragment_Begin/Fragment_End). Mirrors the quest stage-fragment
                                // path (DialogResponsesAdapter Version 6 / ObjectFormat 2, the
                                // single fragment script in ScriptFragments.Script, OnBegin/OnEnd
                                // ScriptFragment pointing into it). The .pex is decoupled
                                // (fo4_papyrus_build / Caprica) — metadata only, like QUST.
                                if (resp.Fragment is { } infoFrag)
                                {
                                    if (string.IsNullOrWhiteSpace(infoFrag.ScriptName)) return Fail("info fragment missing scriptName");
                                    if (infoFrag.OnBegin is null && infoFrag.OnEnd is null)
                                        return Fail("info fragment needs at least one of onBegin/onEnd");
                                    if (!BuildScriptEntry(infoFrag.ScriptName, infoFrag.Flags, infoFrag.Properties, out var fragScript, out var fe))
                                        return Fail(fe);
                                    var adapter = new DialogResponsesAdapter { Version = 6, ObjectFormat = 2 };
                                    adapter.ScriptFragments = new ScriptFragments { Script = fragScript };
                                    if (infoFrag.OnBegin is { } ob)
                                        adapter.ScriptFragments.OnBegin = new ScriptFragment { ScriptName = infoFrag.ScriptName, FragmentName = ob };
                                    if (infoFrag.OnEnd is { } oe)
                                        adapter.ScriptFragments.OnEnd = new ScriptFragment { ScriptName = infoFrag.ScriptName, FragmentName = oe };
                                    info.VirtualMachineAdapter = adapter;
                                }
                                topic.Responses.Add(info);
                            }
                        }
                        qst.DialogTopics.Add(topic);
                    }
                }
                // Kerem-polish: finalize DLBR branches — now that topicsByEid is populated,
                // resolve each branch's StartingTopic (in-spec topic editorId or a FormKey) and
                // attach the branch to the quest. A branch with no resolvable starting topic is a
                // spec error (a branch must point at an entry topic to surface in the wheel).
                foreach (var (branch, startingTopic) in branchObjs)
                {
                    if (!string.IsNullOrWhiteSpace(startingTopic))
                    {
                        if (topicsByEid.TryGetValue(startingTopic, out var stk))
                            branch.StartingTopic.SetTo(stk);
                        else
                        {
                            if (!TryKey(startingTopic, out var stk2, out var ste)) return Fail(ste);
                            branch.StartingTopic.SetTo(stk2);
                        }
                    }
                    qst.DialogBranches.Add(branch);
                }
                // Faz 2.1c: quest aliases — the quest's "cast slots". Each is a
                // QuestReferenceAlias keyed by a quest-local ID (NOT a FormKey); other
                // records reference it by that ID (e.g. a dialogue condition
                // GetIsAliasRef with param1=<id>). Fill = ForcedReference (point at a
                // placed REFR), UniqueActor (a unique NPC), or Conditions
                // (find-matching-ref). IDs auto-sequence by list order unless given.
                if (r.Aliases is { Count: > 0 })
                {
                    qst.Aliases ??= new();   // optional group — null until first alias
                    uint autoId = 0;

                    // W6.7: shared AQuestAlias.Flag parser (ref + location aliases).
                    bool ParseAliasFlags(List<string>? names, out AQuestAlias.Flag flags, out string err)
                    {
                        flags = 0; err = "";
                        if (names is { Count: > 0 })
                            foreach (var fn in names)
                            {
                                if (!Enum.TryParse<AQuestAlias.Flag>(fn, true, out var fl)) { err = $"bad alias flag '{fn}'"; return false; }
                                flags |= fl;
                            }
                        return true;
                    }

                    foreach (var a in r.Aliases)
                    {
                        string at = a.Type?.Trim().ToLowerInvariant() ?? "reference";

                        // W6.7: collection aliases are BLOCKED — Mutagen v0.53.1 does not
                        // round-trip a multi-member QuestCollectionAlias (write→reopen spuriously
                        // duplicates the last CollectionAlias member into a second phantom
                        // collection alias; single-member is clean but pointless). Verified via
                        // Spriggit full-parse readback. Reject rather than silently corrupt the QUST.
                        if (at == "collection")
                            return Fail("collection aliases are not supported: Mutagen v0.53.1 does "
                                + "not round-trip multi-member QuestCollectionAlias (duplicates the "
                                + "last member on reopen). Use reference/location aliases instead.");

                        uint useId = a.Id is { } given && given >= 0 ? (uint)given : autoId;

                        // W6.7: location alias — QuestLocationAlias. Fill = exactly one of
                        // SpecificLocation / ReferenceAliasLocation / ExternalAliasLocation / FromEvent.
                        if (at == "location")
                        {
                            var loc = new QuestLocationAlias { ID = useId };
                            if (a.Name is { } ln) loc.Name = ln;
                            if (!ParseAliasFlags(a.Flags, out var lflags, out var lfe)) return Fail(lfe);
                            if (lflags != 0) loc.Flags = lflags;
                            if (!string.IsNullOrWhiteSpace(a.SpecificLocation))
                            {
                                if (!TryKey(a.SpecificLocation, out var sl, out var e)) return Fail(e);
                                loc.SpecificLocation.SetTo(sl);
                            }
                            if (a.ReferenceAliasLocation is { } ral)
                                loc.ReferenceAliasLocation = new ReferenceAliasLocation { AliasID = ral };
                            if (!string.IsNullOrWhiteSpace(a.ExternalAliasQuest))
                            {
                                if (!TryKey(a.ExternalAliasQuest, out var eq, out var e)) return Fail(e);
                                var ext = new ExternalAliasLocation { AliasID = a.ExternalAliasId ?? 0 };
                                ext.Quest.SetTo(eq);
                                loc.ExternalAliasLocation = ext;
                            }
                            if (!string.IsNullOrWhiteSpace(a.FromEvent))
                                loc.FindMatchingRefFromEvent = new FindMatchingRefFromEvent
                                { FromEvent = new Mutagen.Bethesda.Plugins.RecordType(a.FromEvent) };
                            if (a.Conditions is { Count: > 0 })
                                foreach (var cs in a.Conditions)
                                {
                                    if (!BuildCondition(cs, out var cond, out var ce)) return Fail(ce);
                                    loc.Conditions.Add(cond);
                                }
                            qst.Aliases.Add(loc);
                            autoId = useId + 1;
                            continue;
                        }

                        // reference alias (default) — Faz 2.1c + W6.7 event-fill / external.
                        var alias = new QuestReferenceAlias { ID = useId };
                        if (a.Name is { } an) alias.Name = an;
                        if (!ParseAliasFlags(a.Flags, out var flags, out var fe)) return Fail(fe);
                        if (flags != 0) alias.Flags = flags;
                        if (!string.IsNullOrWhiteSpace(a.ForcedReference))
                        {
                            if (!TryKey(a.ForcedReference, out var fr, out var e)) return Fail(e);
                            alias.ForcedReference.SetTo(fr);
                        }
                        if (!string.IsNullOrWhiteSpace(a.UniqueActor))
                        {
                            if (!TryKey(a.UniqueActor, out var ua, out var e)) return Fail(e);
                            alias.UniqueActor.SetTo(ua);
                        }
                        if (!string.IsNullOrWhiteSpace(a.ExternalAliasQuest))
                        {
                            if (!TryKey(a.ExternalAliasQuest, out var eq, out var e)) return Fail(e);
                            var ext = new ExternalAliasReference { AliasID = a.ExternalAliasId ?? 0 };
                            ext.Quest.SetTo(eq);
                            alias.External = ext;
                        }
                        if (!string.IsNullOrWhiteSpace(a.FromEvent))
                            alias.FindMatchingRefFromEvent = new FindMatchingRefFromEvent
                            { FromEvent = new Mutagen.Bethesda.Plugins.RecordType(a.FromEvent) };
                        if (a.Conditions is { Count: > 0 })
                        {
                            foreach (var cs in a.Conditions)
                            {
                                if (!BuildCondition(cs, out var cond, out var ce)) return Fail(ce);
                                alias.Conditions.Add(cond);
                            }
                        }
                        qst.Aliases.Add(alias);
                        autoId = useId + 1;
                    }
                }
                // Faz 2.1d: Papyrus VMAD binding — attach compiled scripts (by .psc
                // class name) to the quest with typed properties. QuestAdapter is a
                // nullable optional group (null until first script); FO4's VMAD header
                // is Version 6 / ObjectFormat 2 (what CK writes).
                if (r.Scripts is { Count: > 0 })
                {
                    var adapter = qst.VirtualMachineAdapter ??=
                        new QuestAdapter { Version = 6, ObjectFormat = 2 };
                    foreach (var s in r.Scripts)
                    {
                        if (!BuildScriptEntry(s.Name, s.Flags, s.Properties, out var entry, out var se)) return Fail(se);
                        adapter.Scripts.Add(entry);
                    }
                }
                // Faz 2.1f: quest stage script fragments. QuestAdapter.Script holds the
                // single auto-generated fragment script (QF_<eid>_<formid>); .Fragments
                // lists per-stage entries pointing into it (FragmentName = the Fragment_*
                // function fired when the quest reaches that stage). Unknown2 is always 1
                // in real CK output (Spriggit ground-truth). The compiled .pex is decoupled
                // (fo4_papyrus_build / Caprica) — this writes the metadata only (structurally
                // valid, not in-game-runnable without the matching .pex). Alias fragments
                // (QuestAdapter.Aliases) deferred.
                if (r.Fragments is { } frag)
                {
                    if (string.IsNullOrWhiteSpace(frag.ScriptName)) return Fail("fragments missing scriptName");
                    var adapter = qst.VirtualMachineAdapter ??=
                        new QuestAdapter { Version = 6, ObjectFormat = 2 };
                    if (!BuildScriptEntry(frag.ScriptName, frag.Flags, frag.Properties, out var fragScript, out var fe))
                        return Fail(fe);
                    adapter.Script = fragScript;
                    if (frag.Stages is { Count: > 0 })
                        foreach (var st in frag.Stages)
                        {
                            if (st.Stage < 0 || st.Stage > ushort.MaxValue) return Fail($"fragment stage out of range (0-65535): {st.Stage}");
                            if (string.IsNullOrWhiteSpace(st.FragmentName)) return Fail("fragment stage missing fragmentName");
                            adapter.Fragments.Add(new QuestScriptFragment
                            {
                                Stage = (ushort)st.Stage,
                                StageIndex = st.StageIndex ?? 0,
                                Unknown2 = 1,
                                ScriptName = frag.ScriptName,
                                FragmentName = st.FragmentName,
                            });
                        }
                }
                // Faz 2.1g: quest ALIAS script fragments. QuestAdapter.Aliases lists
                // per-alias fragment bindings: each QuestFragmentAlias.Property identifies
                // the target alias (Property.Alias = quest-local alias ID, Property.Object
                // = this quest, Property.Name = "") and carries that alias's fragment
                // script(s) (OnBegin/OnEnd). Version 6 / ObjectFormat 2 match the adapter
                // (Spriggit omits them as defaults). Like stage fragments, the .pex bytecode
                // is compiled separately (fo4_papyrus_build / Caprica) — metadata only.
                if (r.AliasFragments is { Count: > 0 })
                {
                    var adapter = qst.VirtualMachineAdapter ??=
                        new QuestAdapter { Version = 6, ObjectFormat = 2 };
                    foreach (var af in r.AliasFragments)
                    {
                        if (af.Alias < 0 || af.Alias > short.MaxValue) return Fail($"alias fragment id out of range (0-32767): {af.Alias}");
                        if (af.Scripts is not { Count: > 0 }) return Fail($"alias fragment (alias {af.Alias}) needs at least one script");
                        var qfa = new QuestFragmentAlias
                        {
                            Version = 6,
                            ObjectFormat = 2,
                            Property = new ScriptObjectProperty { Alias = (short)af.Alias },
                        };
                        qfa.Property.Object.SetTo(qst.FormKey);
                        foreach (var s in af.Scripts)
                        {
                            if (!BuildScriptEntry(s.Name, s.Flags, s.Properties, out var entry, out var se)) return Fail(se);
                            qfa.Scripts.Add(entry);
                        }
                        adapter.Aliases.Add(qfa);
                    }
                }
                // Faz 2.1e: SCEN scenes — scripted multi-actor dialogue. Quest.Scenes
                // is a nested ExtendedList<Scene> (no null guard, like DialogTopics).
                // Each Scene is a major record back-linked to the quest. SceneActor.ID
                // IS the quest alias ID (the cast comes from 2.1c aliases — no separate
                // link). SceneActions are the timeline; MVP = "typical" actions
                // (Dialog/Package/Timer/PlayerDialogue/Radio via SceneActionTypicalType)
                // referencing a topic. ScenePhases gate flow with the 2.1b condition
                // builder. SceneActionStartScene + actor/behavior flags = deferred niche.
                if (r.Scenes is { Count: > 0 })
                {
                    foreach (var sc in r.Scenes)
                    {
                        var scene = string.IsNullOrWhiteSpace(sc.EditorId)
                            ? new Scene(mod) : new Scene(mod, sc.EditorId);
                        scene.Quest.SetTo(qst.FormKey);   // scene belongs to its quest
                        if (sc.Flags is { Count: > 0 })
                        {
                            Scene.Flag flags = 0;
                            foreach (var fn in sc.Flags)
                            {
                                if (!Enum.TryParse<Scene.Flag>(fn, true, out var fl))
                                    return Fail($"bad scene flag '{fn}'");
                                flags |= fl;
                            }
                            scene.Flags = flags;
                        }
                        if (sc.Actors is { Count: > 0 })
                        {
                            foreach (var a in sc.Actors)
                            {
                                if (a.Id < 0) return Fail($"scene actor id out of range: {a.Id}");
                                scene.Actors.Add(new SceneActor { ID = (uint)a.Id });
                            }
                        }
                        if (sc.Phases is { Count: > 0 })
                        {
                            foreach (var ph in sc.Phases)
                            {
                                var phase = new ScenePhase();
                                if (ph.Name is { } pn) phase.Name = pn;
                                if (ph.StartConditions is { Count: > 0 })
                                    foreach (var cs in ph.StartConditions)
                                    { if (!BuildCondition(cs, out var cond, out var ce)) return Fail(ce); phase.StartConditions.Add(cond); }
                                if (ph.CompletionConditions is { Count: > 0 })
                                    foreach (var cs in ph.CompletionConditions)
                                    { if (!BuildCondition(cs, out var cond, out var ce)) return Fail(ce); phase.CompletionConditions.Add(cond); }
                                scene.Phases.Add(phase);
                            }
                        }
                        if (sc.Actions is { Count: > 0 })
                        {
                            foreach (var ac in sc.Actions)
                            {
                                if (string.IsNullOrWhiteSpace(ac.Type)) return Fail("scene action missing type");
                                if (!Enum.TryParse<SceneAction.TypeEnum>(ac.Type, true, out var at))
                                    return Fail($"bad scene action type '{ac.Type}'");
                                var action = new SceneAction { Type = new SceneActionTypicalType { Type = at } };
                                if (ac.Actor is { } actorId) action.AliasID = actorId;
                                if (!string.IsNullOrWhiteSpace(ac.Topic))
                                {
                                    FormKey topicKey;
                                    if (ac.Topic.Contains(':'))
                                    { if (!TryKey(ac.Topic, out topicKey, out var te)) return Fail(te); }
                                    else if (!topicsByEid.TryGetValue(ac.Topic, out topicKey))
                                        return Fail($"scene action topic '{ac.Topic}' not found among this quest's topics");
                                    action.Topic.SetTo(topicKey);
                                }
                                if (ac.StartPhase is { } sp) { if (sp < 0) return Fail($"startPhase out of range: {sp}"); action.StartPhase = (uint)sp; }
                                if (ac.EndPhase is { } ep) { if (ep < 0) return Fail($"endPhase out of range: {ep}"); action.EndPhase = (uint)ep; }
                                if (ac.Flags is { Count: > 0 })
                                {
                                    SceneAction.Flag aflags = 0;
                                    foreach (var fn in ac.Flags)
                                    {
                                        if (!Enum.TryParse<SceneAction.Flag>(fn, true, out var fl))
                                            return Fail($"bad scene action flag '{fn}'");
                                        aflags |= fl;
                                    }
                                    action.Flags = aflags;
                                }
                                scene.Actions.Add(action);
                            }
                        }
                        qst.Scenes.Add(scene);
                    }
                }
                formKey = qst.FormKey.ToString();
                break;
            }
            case "keyword":
            {
                // KYWD MVP = bare keyword: editorId (+ optional name). AddNew mints the
                // FormKey + sets EditorID (same idiom as armor:390); Keyword is concrete,
                // so no explicit-construct dance. Color/Type deferred (System.Drawing /
                // TypeEnum surface, not glue-MVP).
                var kywd = mod.Keywords.AddNew(r.EditorId);
                if (r.Name is { } n) kywd.Name = n;
                // CNAM Color — REQUIRED for a workshop-build-menu category keyword: the menu UI draws
                // the category button from the keyword's color, so a bare (colorless) keyword never
                // renders as a category. [r,g,b] (alpha defaults to vanilla's 0) or [a,r,g,b].
                if (r.Color is { } col)
                {
                    if (col.Length == 3) kywd.Color = System.Drawing.Color.FromArgb(0, col[0], col[1], col[2]);
                    else if (col.Length == 4) kywd.Color = System.Drawing.Color.FromArgb(col[0], col[1], col[2], col[3]);
                    else return Fail("keyword color needs [r,g,b] or [a,r,g,b]");
                }
                formKey = kywd.FormKey.ToString();
                break;
            }
            case "formlist":
            {
                // FLST MVP = editorId (+ optional name) + Items FormLink list. FormList is
                // concrete (AddNew like armor:390). Element type is the GENERAL
                // IFallout4MajorRecordGetter (a FLST holds any record), NOT IKeywordGetter.
                // Items is a non-null ExtendedList, so no ??= new() guard is needed.
                var flst = mod.FormLists.AddNew(r.EditorId);
                if (r.Name is { } n) flst.Name = n;
                if (r.Items is { Count: > 0 })
                {
                    foreach (var it in r.Items)
                    {
                        if (!TryKey(it, out var ik, out var e)) return Fail(e);
                        flst.Items.Add(new FormLink<IFallout4MajorRecordGetter>(ik));
                    }
                }
                formKey = flst.FormKey.ToString();
                break;
            }
            case "flstoverride":
            {
                // Menu/category wiring — override an EXISTING (master) FLST to ADD items (e.g. graft a
                // custom workshop-build category into the vanilla WorkshopMenuMain so a modded recipe
                // shows under your OWN menu node). Mirrors leveleditemoverride: load sourcePlugin, find
                // the FLST by FormKey, DeepCopy (FormKey preserved -> true override, vanilla items carry
                // forward), then ADD the new item FormLinks. Additive; clearExisting is the opt-in footgun.
                if (string.IsNullOrWhiteSpace(r.SourcePlugin)) return Fail("flstOverride missing sourcePlugin");
                if (string.IsNullOrWhiteSpace(r.Target)) return Fail("flstOverride missing target (FLST FormKey)");
                if (!TryKey(r.Target, out var floKey, out var floe)) return Fail(floe);
                if (!sourceCache.TryGetValue(r.SourcePlugin, out var srcFlstMod))
                {
                    if (!File.Exists(r.SourcePlugin)) return Fail($"sourcePlugin not found: {r.SourcePlugin}");
                    try { srcFlstMod = Fallout4Mod.CreateFromBinaryOverlay(new ModPath(r.SourcePlugin), Fallout4Release.Fallout4); }
                    catch (Exception e) { return Fail($"sourcePlugin load error: {e.Message}"); }
                    sourceCache[r.SourcePlugin] = srcFlstMod;
                }
                var srcFlst = srcFlstMod.FormLists.FirstOrDefault(x => x.FormKey == floKey);
                if (srcFlst is null) return Fail($"FLST {r.Target} not found in {Path.GetFileName(r.SourcePlugin)}");
                var floOvl = srcFlst.DeepCopy();
                if (r.ClearExisting ?? false) floOvl.Items.Clear();
                if (r.Items is { Count: > 0 })
                    foreach (var it in r.Items)
                    {
                        if (!TryKey(it, out var ik, out var ie)) return Fail(ie);
                        floOvl.Items.Add(new FormLink<IFallout4MajorRecordGetter>(ik));
                    }
                mod.FormLists.RecordCache.Add(floOvl);
                formKey = floOvl.FormKey.ToString();
                break;
            }
            case "message":
            {
                // MESG = editorId + text (Description, the body) + optional title (Name).
                // Message is concrete (AddNew like armor:390); both fields are TranslatedStrings
                // assigned from a plain string (implicit, like armo.Name). OS-11: + MenuButtons
                // (choice dialogs; needs the MessageBox flag to render) + Flags (Message.Flag).
                // OwnerQuest/DisplayTime still deferred.
                var mesg = mod.Messages.AddNew(r.EditorId);
                if (r.Text is { } body) mesg.Description = body;
                if (r.Name is { } title) mesg.Name = title;
                if (r.Flags is { Count: > 0 })
                    foreach (var fn in r.Flags)
                    {
                        if (!Enum.TryParse<Message.Flag>(fn, true, out var mf))
                            return Fail($"bad message flag '{fn}' (MessageBox|DelayInitialDisplay)");
                        mesg.Flags |= mf;
                    }
                if (r.MenuButtons is { Count: > 0 })
                    foreach (var b in r.MenuButtons)
                    {
                        var btn = new MessageButton();
                        if (b.Text is { } bt) btn.Text = bt;
                        if (b.Conditions is { Count: > 0 })
                            foreach (var cs in b.Conditions)
                            { if (!BuildCondition(cs, out var cond, out var ce)) return Fail(ce); btn.Conditions.Add(cond); }
                        mesg.MenuButtons.Add(btn);
                    }
                formKey = mesg.FormKey.ToString();
                break;
            }
            case "book":
            {
                // BOOK authored as a readable NOTE (coupon MVP). Name = title (FULL);
                // Text -> BookText (CNAM, the body shown when read — vanilla perk-mags leave
                // it empty and grant a perk instead, here it carries the ad copy). Value/Weight/
                // Keywords reuse the shared item fields. Teaches = BookTeachesNothing (set
                // explicitly, matching vanilla) so the coupon grants no perk. Model (paper-note
                // nif) deferred — still readable from the Pip-Boy without one. Concrete record,
                // so AddNew (like message:1921).
                var book = mod.Books.AddNew(r.EditorId);
                if (r.Name is { } bn) book.Name = bn;
                if (r.Text is { } btext) book.BookText = btext;
                book.Teaches = new BookTeachesNothing();
                if (r.Value is { } bval)
                {
                    if (bval < 0) return Fail($"book value out of range: {bval}");
                    book.Value = (uint)bval;   // BOOK DATA value is UInt32 (Armor.Value is Int32)
                }
                if (r.Weight is { } bwt)
                {
                    if (bwt < 0) return Fail($"book weight out of range: {bwt}");
                    book.Weight = bwt;
                }
                if (r.Keywords is { Count: > 0 })
                {
                    book.Keywords ??= new();
                    foreach (var kw in r.Keywords)
                    {
                        if (!TryKey(kw, out var kk, out var e)) return Fail(e);
                        book.Keywords.Add(new FormLink<IKeywordGetter>(kk));
                    }
                }
                // Visual: world-model nif (MODL) + optional MaterialSwap (the MSWP that
                // retextures it). The swap rides on the Model, not the Book — matching the
                // engine (a placed model gets the swap). Without a Model the note is still
                // readable from the Pip-Boy; with one it shows the coupon art in-world.
                if (r.Model is { } bmdl)
                {
                    var m = new Model { File = bmdl };
                    if (r.MaterialSwap is { } msw)
                    {
                        if (!TryKey(msw, out var mk, out var me)) return Fail(me);
                        m.MaterialSwap.SetTo(mk);
                    }
                    book.Model = m;
                }
                formKey = book.FormKey.ToString();
                break;
            }
            case "misc":
            {
                // MISC — pickupable clutter (coupon as a collectible item, NOT a readable BOOK).
                // Natural partner for a money/caps-style DYNAMIC-havok world model: MISC items get
                // picked into inventory on activate, and unlike BOOK they don't open a note UI.
                // Name + Model (+ optional MaterialSwap) + Value/Weight/Keywords reuse the shared
                // item fields. Concrete record -> AddNew (like book:2088).
                var misc = mod.MiscItems.AddNew(r.EditorId);
                if (r.Name is { } mn) misc.Name = mn;
                if (r.Value is { } mval)
                {
                    if (mval < 0) return Fail($"misc value out of range: {mval}");
                    misc.Value = mval;          // MISC DATA value is Int32 (Book.Value is UInt32)
                }
                if (r.Weight is { } mwt)
                {
                    if (mwt < 0) return Fail($"misc weight out of range: {mwt}");
                    misc.Weight = mwt;
                }
                if (r.Keywords is { Count: > 0 })
                {
                    misc.Keywords ??= new();
                    foreach (var kw in r.Keywords)
                    {
                        if (!TryKey(kw, out var kk, out var e)) return Fail(e);
                        misc.Keywords.Add(new FormLink<IKeywordGetter>(kk));
                    }
                }
                if (r.Model is { } mmdl)
                {
                    var m = new Model { File = mmdl };
                    if (r.MaterialSwap is { } msw)
                    {
                        if (!TryKey(msw, out var mk, out var me)) return Fail(me);
                        m.MaterialSwap.SetTo(mk);
                    }
                    misc.Model = m;
                }
                // OBND — non-zero Object Bounds. Mutagen inits ObjectBounds to all-zero, which
                // serializes as a valid-but-degenerate box. FO4 frames the Pip-Boy inventory preview /
                // Inspect camera from OBND, so a zero box = blank preview + dead Inspect (the coupon
                // no-show root cause). Default = PrewarMoney's flat-card box; spec overrides per item.
                {
                    var ob = r.ObjectBounds ?? new short[] { -7, -3, 0, 7, 3, 4 };
                    if (ob.Length != 6) return Fail($"objectBounds needs 6 ints [x1,y1,z1,x2,y2,z2], got {ob.Length}");
                    misc.ObjectBounds.First = new Noggog.P3Int16(ob[0], ob[1], ob[2]);
                    misc.ObjectBounds.Second = new Noggog.P3Int16(ob[3], ob[4], ob[5]);
                }
                // PTRN — Preview Transform (TRNS). Frames the model in the Pip-Boy/Inspect inventory
                // preview, which is a SEPARATE render path from the world model. With PTRN null the
                // engine default-frames by OBND, and a flat card lands edge-on -> blank preview even
                // though the world model renders. Point flat items at a flat-collectible TRNS (e.g.
                // OverdueBook's 1CF028:Fallout4.esm = a +Z-facing book, same orientation as a coupon).
                if (r.PreviewTransform is { } pt)
                {
                    if (!TryKey(pt, out var ptk, out var pte)) return Fail(pte);
                    misc.PreviewTransform.SetTo(ptk);
                }
                formKey = misc.FormKey.ToString();
                break;
            }
            case "materialswap":
            {
                // MSWP: a retexture map. Each substitution swaps an ORIGINAL .bgsm
                // (the one the nif references) for a REPLACEMENT .bgsm (ours, pointing at
                // the coupon .dds). Paths are Data-relative, "Materials\...\x.bgsm".
                // The Book's Model.MaterialSwap links here. Concrete record -> AddNew.
                var mswp = mod.MaterialSwaps.AddNew(r.EditorId);
                if (r.Substitutions is { Count: > 0 })
                {
                    foreach (var s in r.Substitutions)
                    {
                        if (string.IsNullOrWhiteSpace(s.Original) || string.IsNullOrWhiteSpace(s.Replacement))
                            return Fail("materialswap substitution needs both original and replacement");
                        var sub = new MaterialSubstitution
                        {
                            OriginalMaterial = s.Original,
                            ReplacementMaterial = s.Replacement,
                        };
                        mswp.Substitutions.Add(sub);
                    }
                }
                formKey = mswp.FormKey.ToString();
                break;
            }
            case "constructibleobject":
            case "cobj":
            {
                // OS-08 — COBJ crafting recipe. createdObject (the output, REQUIRED) + workbenchKeyword
                // (the bench it shows at, REQUIRED) + components (ingredient FormLinks + counts) +
                // categories (workshop-menu filter KYWDs — NOT an FLST) + conditions (HasPerk/
                // GetItemCount gates, reuses BuildCondition). OMOD attach-mods are a separate gate.
                var cobj = mod.ConstructibleObjects.AddNew(r.EditorId);
                if (string.IsNullOrWhiteSpace(r.CreatedObject))
                    return Fail("constructibleObject needs 'createdObject' (the recipe output FormKey)");
                if (!TryKey(r.CreatedObject, out var cok, out var coe)) return Fail(coe);
                cobj.CreatedObject.SetTo(cok);
                if (string.IsNullOrWhiteSpace(r.WorkbenchKeyword))
                    return Fail("constructibleObject needs 'workbenchKeyword' (the bench-type FormKey)");
                if (!TryKey(r.WorkbenchKeyword, out var wbk, out var wbe)) return Fail(wbe);
                cobj.WorkbenchKeyword.SetTo(wbk);
                {
                    var count = r.CreatedObjectCount ?? 1;
                    if (count < 0 || count > ushort.MaxValue) return Fail($"createdObjectCount out of range (0-65535): {count}");
                    cobj.CreatedObjectCounts ??= new();
                    cobj.CreatedObjectCounts.Add(new ConstructibleCreatedObjectCount { Count = (ushort)count, Priority = 0 });
                }
                if (!string.IsNullOrWhiteSpace(r.MenuArtObject))
                { if (!TryKey(r.MenuArtObject, out var mak, out var mae)) return Fail(mae); cobj.MenuArtObject.SetTo(mak); }
                if (r.Components is { Count: > 0 })
                {
                    cobj.Components ??= new();
                    foreach (var c in r.Components)
                    {
                        if (c.Count < 0) return Fail($"component count out of range: {c.Count}");
                        if (!TryKey(c.Component, out var ck, out var ce)) return Fail(ce);
                        var comp = new ConstructibleObjectComponent { Count = (uint)c.Count };
                        comp.Component.SetTo(ck);
                        cobj.Components.Add(comp);
                    }
                }
                if (r.Categories is { Count: > 0 })
                {
                    cobj.Categories ??= new();
                    foreach (var cat in r.Categories)
                    { if (!TryKey(cat, out var catk, out var cate)) return Fail(cate); cobj.Categories.Add(new FormLink<IKeywordGetter>(catk)); }
                }
                if (r.Conditions is { Count: > 0 })
                    foreach (var cs in r.Conditions)
                    { if (!BuildCondition(cs, out var cond, out var cce)) return Fail(cce); cobj.Conditions.Add(cond); }
                formKey = cobj.FormKey.ToString();
                break;
            }
            case "global":
            {
                // GLOB: Global is ABSTRACT, so AddNew (an IMajorRecord-constrained factory
                // extension) would COMPILE but THROW at runtime. Construct the concrete
                // subclass explicitly, set Data, then mod.Globals.Add(glob). The
                // (mod, editorID) ctor mints the FormKey + sets EditorID in one call (the
                // AddNew equivalent). This is the only explicit-construct-then-Add case.
                Global glob;
                switch ((r.GlobalType ?? "float").Trim().ToLowerInvariant())
                {
                    case "float":
                    {
                        var gf = new GlobalFloat(mod, r.EditorId);
                        if (r.GlobalValue is { } v) gf.Data = (float)v;
                        glob = gf;
                        break;
                    }
                    case "int":
                    {
                        var gi = new GlobalInt(mod, r.EditorId);
                        if (r.GlobalValue is { } v)
                        {
                            if (v < int.MinValue || v > int.MaxValue)
                                return Fail($"global int value out of range: {v}");
                            gi.Data = (int)Math.Round(v);
                        }
                        glob = gi;
                        break;
                    }
                    case "short":
                    {
                        var gs = new GlobalShort(mod, r.EditorId);
                        if (r.GlobalValue is { } v)
                        {
                            if (v < short.MinValue || v > short.MaxValue)
                                return Fail($"global short value out of range: {v}");
                            gs.Data = (short)Math.Round(v);
                        }
                        glob = gs;
                        break;
                    }
                    default:
                        return Fail($"bad globalType '{r.GlobalType}' (expected float|int|short)");
                }
                mod.Globals.Add(glob);
                formKey = glob.FormKey.ToString();
                break;
            }
            case "faction":
            {
                // FACT — MVP: editorId + name + flags (reuses RecordSpec.Flags) + interfaction
                // Relations [{faction, reaction}]. This makes a placed hostile NPC actually
                // hostile (Reaction=Enemy toward the player's faction). Ranks/CrimeValues/
                // VendorValues deferred (richer sub-structures, not needed for the hostility
                // goal). Faction is a concrete record, so AddNew (like armor:390).
                var fact = mod.Factions.AddNew(r.EditorId);
                if (r.Name is { } n) fact.Name = n;
                if (r.Flags is { Count: > 0 })
                {
                    foreach (var fn in r.Flags)
                    {
                        if (!Enum.TryParse<Faction.FactionFlag>(fn, true, out var fl))
                            return Fail($"bad faction flag '{fn}'");
                        fact.Flags |= fl;
                    }
                }
                if (r.InterfactionRelations is { Count: > 0 })
                {
                    foreach (var rs in r.InterfactionRelations)
                    {
                        if (!Enum.TryParse<CombatReaction>(rs.Reaction, true, out var reaction))
                            return Fail($"bad faction reaction '{rs.Reaction}' (Neutral|Enemy|Ally|Friend)");
                        if (!TryKey(rs.Faction, out var tfk, out var e)) return Fail(e);
                        var rel = new Relation { Reaction = reaction };
                        rel.Target.SetTo(tfk);
                        fact.Relations.Add(rel);
                    }
                }
                // OS-11: Ranks (member titles, gendered) + VendorValues (merchant data). CrimeValues
                // still deferred.
                if (r.Ranks is { Count: > 0 })
                    foreach (var rk in r.Ranks)
                    {
                        var rank = new Rank();
                        if (rk.Number is { } num)
                        {
                            if (num < 0) return Fail($"rank number out of range: {num}");
                            rank.Number = (uint)num;
                        }
                        if (rk.Title is { } t)
                            rank.Title = new Mutagen.Bethesda.Plugins.Records.GenderedItem<Mutagen.Bethesda.Strings.TranslatedString>(t, rk.TitleFemale ?? t);
                        if (rk.Insignia is { } ins) rank.Insignia = ins;
                        fact.Ranks.Add(rank);
                    }
                if (r.VendorValues is { } vv)
                {
                    if (vv.StartHour < 0 || vv.StartHour > ushort.MaxValue) return Fail($"vendorValues.startHour out of range (0-65535): {vv.StartHour}");
                    if (vv.EndHour < 0 || vv.EndHour > ushort.MaxValue) return Fail($"vendorValues.endHour out of range (0-65535): {vv.EndHour}");
                    if (vv.Radius < 0 || vv.Radius > ushort.MaxValue) return Fail($"vendorValues.radius out of range (0-65535): {vv.Radius}");
                    fact.VendorValues = new VendorValues
                    {
                        StartHour = (ushort)vv.StartHour,
                        EndHour = (ushort)vv.EndHour,
                        Radius = (ushort)vv.Radius,
                        BuysStolenItems = vv.BuysStolen,
                        BuysNonStolenItems = vv.BuysNonStolen,
                        BuySellEverythingNotInList = vv.BuyEverything,
                    };
                }
                formKey = fact.FormKey.ToString();
                break;
            }
            case "levelednpc":
            {
                // LVLN — MVP: editorId + entries [{reference (INpcSpawn: NPC_/LVLN), level,
                // count}] + flags (reuses RecordSpec.Flags; LeveledNpc.Flag). Each entry wraps
                // a LeveledNpcEntryData (Level/Count Int16, Reference FormLink). chanceNone/
                // Global/MaxCount/FilterKeywordChances deferred (refinements). AddNew (concrete).
                var lvln = mod.LeveledNpcs.AddNew(r.EditorId);
                if (r.Flags is { Count: > 0 })
                {
                    foreach (var fn in r.Flags)
                    {
                        if (!Enum.TryParse<LeveledNpc.Flag>(fn, true, out var fl))
                            return Fail($"bad leveledNpc flag '{fn}' (CalculateFromAllLevelsLessThanOrEqualPlayer|CalculateForEachItemInCount|CalculateAll)");
                        lvln.Flags |= fl;
                    }
                }
                // OS-11: chance the whole list yields nothing (authored 0-100 int -> Percent fraction).
                if (r.ChanceNone is { } cn)
                {
                    if (cn < 0 || cn > 100) return Fail($"chanceNone out of range (0-100): {cn}");
                    lvln.ChanceNone = new Noggog.Percent(cn / 100.0);
                }
                if (r.Entries is { Count: > 0 })
                {
                    lvln.Entries ??= new();
                    foreach (var en in r.Entries)
                    {
                        if (!TryKey(en.Reference, out var ek, out var e)) return Fail(e);
                        var entry = new LeveledNpcEntry { Data = new LeveledNpcEntryData { Level = (short)en.Level, Count = (short)en.Count } };
                        entry.Data!.Reference.SetTo(ek);
                        lvln.Entries.Add(entry);
                    }
                }
                formKey = lvln.FormKey.ToString();
                break;
            }
            case "leveleditem":
            {
                // LVLI — MVP mirrors LVLN: entries [{reference (IItem), level, count}] + flags
                // (LeveledItem.Flag — note bit 4 is UseAll, not LVLN's CalculateAll). Critical
                // for non-naked NPC spawns (inventory leveled lists). EpicLootChance/OverrideName
                // deferred. Reference target type differs but TryKey/SetTo are type-agnostic.
                var lvli = mod.LeveledItems.AddNew(r.EditorId);
                if (r.Flags is { Count: > 0 })
                {
                    foreach (var fn in r.Flags)
                    {
                        if (!Enum.TryParse<LeveledItem.Flag>(fn, true, out var fl))
                            return Fail($"bad leveledItem flag '{fn}' (CalculateFromAllLevelsLessThanOrEqualPlayer|CalculateForEachItemInCount|UseAll)");
                        lvli.Flags |= fl;
                    }
                }
                // OS-11: chanceNone (loot tuning — chance the list yields nothing; the coupon
                // "as-extra not-replace" lever). Authored as 0-100 int -> Noggog.Percent fraction.
                if (r.ChanceNone is { } cn)
                {
                    if (cn < 0 || cn > 100) return Fail($"chanceNone out of range (0-100): {cn}");
                    lvli.ChanceNone = new Noggog.Percent(cn / 100.0);
                }
                if (r.Entries is { Count: > 0 })
                {
                    lvli.Entries ??= new();
                    foreach (var en in r.Entries)
                    {
                        if (!TryKey(en.Reference, out var ek, out var e)) return Fail(e);
                        var entry = new LeveledItemEntry { Data = new LeveledItemEntryData { Level = (short)en.Level, Count = (short)en.Count } };
                        entry.Data!.Reference.SetTo(ek);
                        lvli.Entries.Add(entry);
                    }
                }
                formKey = lvli.FormKey.ToString();
                break;
            }
            case "cell":
            {
                // W4 — a new interior CELL + its nested placed refs (REFR/ACHR). Unlike every
                // other record this is NOT a flat AddNew: the cell is inserted into the block
                // hierarchy (below), and placed refs live in Cell.Temporary / Cell.Persistent.
                // Ground-truth = SanctuaryRosaHouse ("Rosa Residence"): a real furnished
                // residence keeps all refs in Temporary (Persistent empty), flagged IsInteriorCell,
                // with a LightingTemplate (LTMP) — WITHOUT which the cell renders black.
                var cell = new Cell(mod, r.EditorId);
                cell.Flags = Cell.Flag.IsInteriorCell;   // W4 scope = interior-only
                if (r.Name is { } cn) cell.Name = cn;
                if (!string.IsNullOrWhiteSpace(r.LightingTemplate))
                {
                    if (!TryKey(r.LightingTemplate, out var k, out var e)) return Fail(e);
                    cell.LightingTemplate.SetTo(k);
                }
                if (r.WaterHeight is { } wh) cell.WaterHeight = wh;
                if (!string.IsNullOrWhiteSpace(r.Location))
                { if (!TryKey(r.Location, out var k, out var e)) return Fail(e); cell.Location.SetTo(k); }
                if (!string.IsNullOrWhiteSpace(r.EncounterZone))
                { if (!TryKey(r.EncounterZone, out var k, out var e)) return Fail(e); cell.EncounterZone.SetTo(k); }
                if (!string.IsNullOrWhiteSpace(r.ImageSpace))
                { if (!TryKey(r.ImageSpace, out var k, out var e)) return Fail(e); cell.ImageSpace.SetTo(k); }
                if (!string.IsNullOrWhiteSpace(r.AcousticSpace))
                { if (!TryKey(r.AcousticSpace, out var k, out var e)) return Fail(e); cell.AcousticSpace.SetTo(k); }
                if (!string.IsNullOrWhiteSpace(r.Music))
                { if (!TryKey(r.Music, out var k, out var e)) return Fail(e); cell.Music.SetTo(k); }

                // placed refs (REFR/ACHR) + block-hierarchy placement via shared helpers.
                if (!AddPlacedRefs(mod, cell, r.PlacedObjects, r.PlacedNpcs, out var refErr)) return Fail(refErr);
                // A-disk: optional isolated-interior navmesh (auto-triangulated floor). DISK-PROVEN;
                // in-game pathing is the §4 freeze gate.
                if (r.Navmesh is { } nvSpec && !AddNavmesh(mod, cell, nvSpec, out var nvErr)) return Fail(nvErr);
                PlaceCell(mod, cell, cellBlocks, cellSubBlocks);
                formKey = cell.FormKey.ToString();
                break;
            }
            case "celloverride":
            {
                // W5 — add placed refs to an EXISTING (master) cell. DeepCopy the master cell
                // (FormKey stays the master's -> a true override) so its data fields (lighting etc.)
                // carry forward (no black cell); clear the deep-copied child refs (so the override's
                // child group holds ONLY the new refs -> master refs stay in the master, no ITM
                // duplicates); add the new refs; place into the block hierarchy. No LinkCache/
                // LoadOrder needed. Precombine/previs SAFETY is gated Python-side
                // (fo4_check_previs_safety) — editing a precombined cell needs a CK previs regen.
                // Proven: SanctuaryRosaHouse override -> FormKey 01F398:Fallout4.esm preserved.
                if (string.IsNullOrWhiteSpace(r.SourcePlugin)) return Fail("cellOverride missing sourcePlugin");
                if (string.IsNullOrWhiteSpace(r.Cell)) return Fail("cellOverride missing cell (target FormKey)");
                if (!TryKey(r.Cell, out var cellKey, out var ke)) return Fail(ke);
                if (!sourceCache.TryGetValue(r.SourcePlugin, out var srcMod))
                {
                    if (!File.Exists(r.SourcePlugin)) return Fail($"sourcePlugin not found: {r.SourcePlugin}");
                    try { srcMod = Fallout4Mod.CreateFromBinaryOverlay(new ModPath(r.SourcePlugin), Fallout4Release.Fallout4); }
                    catch (Exception e) { return Fail($"sourcePlugin load error: {e.Message}"); }
                    sourceCache[r.SourcePlugin] = srcMod;
                }
                // interior cells first (block hierarchy)
                ICellGetter? srcCell = null;
                foreach (var b in srcMod.Cells)
                {
                    foreach (var s in b.SubBlocks)
                    {
                        foreach (var cc in s.Cells) if (cc.FormKey == cellKey) { srcCell = cc; break; }
                        if (srcCell != null) break;
                    }
                    if (srcCell != null) break;
                }
                if (srcCell != null)
                {
                    var ov = srcCell.DeepCopy();
                    // Safe-by-default: ADDITIVE (default false). Clearing the deep-copied child refs
                    // is destructive on a POPULATED cell — it wipes the master's own refs in the
                    // override (the Kerem RedRocketExt incident: 482 refs gone). Opt in to wipe.
                    if (r.ClearExisting ?? false) { ov.Temporary.Clear(); ov.Persistent.Clear(); }
                    if (!AddPlacedRefs(mod, ov, r.PlacedObjects, r.PlacedNpcs, out var ovRefErr)) return Fail(ovRefErr);
                    PlaceCell(mod, ov, cellBlocks, cellSubBlocks);
                    formKey = ov.FormKey.ToString();
                    break;
                }
                // W5-ext (Kerem): EXTERIOR worldspace cell — place the override under a worldspace
                // override at the SAME block/subblock the master uses (read from the source, no grid
                // math). Adding actor refs (ACHR) is previs-SAFE (previs is static-geometry only) and
                // they path on the existing worldspace navmesh. Master's own refs stay in the master.
                var ext = FindExteriorCell(srcMod, cellKey);
                if (ext is null) return Fail($"cell {r.Cell} not found (interior or exterior) in {Path.GetFileName(r.SourcePlugin)}");
                var (extCell, srcWs, bx, by, sx, sy) = ext.Value;
                var extOv = extCell.DeepCopy();
                if (r.ClearExisting ?? false) { extOv.Temporary.Clear(); extOv.Persistent.Clear(); }
                if (!AddPlacedRefs(mod, extOv, r.PlacedObjects, r.PlacedNpcs, out var extRefErr)) return Fail(extRefErr);
                PlaceExteriorCell(mod, extOv, srcWs, bx, by, sx, sy, wsOverrides, wsBlocks, wsSubBlocks);
                formKey = extOv.FormKey.ToString();
                break;
            }
            case "leveleditemoverride":
            {
                // Loot injection — override an EXISTING (master) LVLI to ADD entries (e.g. graft a
                // coupon rarity sub-list onto a vanilla food-container list). Mirrors celloverride:
                // load sourcePlugin, find the LVLI by FormKey, DeepCopy (FormKey preserved -> a true
                // override, so the vanilla entries carry forward), then ADD the new entries.
                // ADDITIVE by default — clearExisting wipes the vanilla entries (the footgun, opt-in).
                // The master (Fallout4.esm) auto-adds on write via the preserved FormKey, exactly
                // like celloverride. No LinkCache/LoadOrder needed.
                if (string.IsNullOrWhiteSpace(r.SourcePlugin)) return Fail("leveledItemOverride missing sourcePlugin");
                if (string.IsNullOrWhiteSpace(r.Target)) return Fail("leveledItemOverride missing target (LVLI FormKey)");
                if (!TryKey(r.Target, out var tgtKey, out var tke)) return Fail(tke);
                if (!sourceCache.TryGetValue(r.SourcePlugin, out var srcLvliMod))
                {
                    if (!File.Exists(r.SourcePlugin)) return Fail($"sourcePlugin not found: {r.SourcePlugin}");
                    try { srcLvliMod = Fallout4Mod.CreateFromBinaryOverlay(new ModPath(r.SourcePlugin), Fallout4Release.Fallout4); }
                    catch (Exception e) { return Fail($"sourcePlugin load error: {e.Message}"); }
                    sourceCache[r.SourcePlugin] = srcLvliMod;
                }
                var srcLvli = srcLvliMod.LeveledItems.FirstOrDefault(x => x.FormKey == tgtKey);
                if (srcLvli is null) return Fail($"LVLI {r.Target} not found in {Path.GetFileName(r.SourcePlugin)}");
                var ovl = srcLvli.DeepCopy();
                if (r.ClearExisting ?? false) ovl.Entries?.Clear();
                if (r.Flags is { Count: > 0 })
                {
                    foreach (var fn in r.Flags)
                    {
                        if (!Enum.TryParse<LeveledItem.Flag>(fn, true, out var fl))
                            return Fail($"bad leveledItem flag '{fn}'");
                        ovl.Flags |= fl;
                    }
                }
                if (r.Entries is { Count: > 0 })
                {
                    ovl.Entries ??= new();
                    foreach (var en in r.Entries)
                    {
                        if (!TryKey(en.Reference, out var ek, out var e)) return Fail(e);
                        var entry = new LeveledItemEntry { Data = new LeveledItemEntryData { Level = (short)en.Level, Count = (short)en.Count } };
                        entry.Data!.Reference.SetTo(ek);
                        ovl.Entries.Add(entry);
                    }
                }
                mod.LeveledItems.RecordCache.Add(ovl);
                formKey = ovl.FormKey.ToString();
                break;
            }
            case "smqn":
            {
                // W6 — Story Manager Quest Node: event-driven quest auto-start. The node hangs
                // under a vanilla event/branch node (Parent) in the SM tree; when that event
                // fires and the node's Conditions pass, its Quests start. PreviousSibling orders
                // it among its siblings (a wrong sibling = clean load + Spriggit OK but never
                // fires in-game — the silent-fail footgun). Flat AddNew (Fallout4Group, not a
                // block hierarchy). Ground-truth = DmndSchoolhouseEvents (1BC007).
                var node = mod.StoryManagerQuestNodes.AddNew(r.EditorId);
                if (!string.IsNullOrWhiteSpace(r.Parent))
                { if (!TryKey(r.Parent, out var k, out var e)) return Fail(e); node.Parent.SetTo(k); }
                if (!string.IsNullOrWhiteSpace(r.PreviousSibling))
                { if (!TryKey(r.PreviousSibling, out var k, out var e)) return Fail(e); node.PreviousSibling.SetTo(k); }
                if (r.Flags is { Count: > 0 })
                    foreach (var fn in r.Flags)
                    {
                        if (!Enum.TryParse<AStoryManagerNode.Flag>(fn, true, out var fl))
                            return Fail($"bad smqn flag '{fn}' (Random|WarnIfNoChildQuestStarted)");
                        node.Flags |= fl;
                    }
                if (r.MaxConcurrentQuests is { } mc)
                {
                    if (mc < 0) return Fail($"maxConcurrentQuests out of range: {mc}");
                    node.MaxConcurrentQuests = (uint)mc;
                }
                if (r.MaxNumQuestsToRun is { } mn)
                {
                    if (mn < 0) return Fail($"maxNumQuestsToRun out of range: {mn}");
                    node.MaxNumQuestsToRun = (uint)mn;
                }
                if (r.HoursUntilReset is { } hr) node.HoursUntilReset = hr;
                if (r.Conditions is { Count: > 0 })
                    foreach (var cs in r.Conditions)
                    { if (!BuildCondition(cs, out var cond, out var ce)) return Fail(ce); node.Conditions.Add(cond); }
                if (r.Quests is { Count: > 0 })
                    foreach (var sq in r.Quests)
                    {
                        if (string.IsNullOrWhiteSpace(sq.Quest)) return Fail("smqn quest entry missing quest");
                        if (!TryKey(sq.Quest, out var qk, out var e)) return Fail(e);
                        var smq = new StoryManagerQuest();
                        smq.Quest.SetTo(qk);
                        if (sq.HoursUntilReset is { } h) smq.HoursUntilReset = h;
                        node.Quests.Add(smq);
                    }
                formKey = node.FormKey.ToString();
                break;
            }
            case "activator":
            {
                // W6.5 — ACTI base record (script-bound trigger / interactable). name + keywords +
                // VMAD control-script binding (W6.5-gap, 2026-06-21): `scripts[]` attaches a compiled
                // Papyrus control script (by .psc class name) with typed properties — the .pex is
                // compiled separately (fo4_papyrus_build / Caprica), this writes the VMAD metadata
                // (Version 6 / ObjectFormat 2, what CK writes). Model mesh deferred.
                var acti = mod.Activators.AddNew(r.EditorId);
                if (r.Name is { } n) acti.Name = n;
                if (r.Keywords is { Count: > 0 })
                {
                    acti.Keywords ??= new();
                    foreach (var kw in r.Keywords)
                    { if (!TryKey(kw, out var kk, out var e)) return Fail(e); acti.Keywords.Add(new FormLink<IKeywordGetter>(kk)); }
                }
                if (r.Scripts is { Count: > 0 })
                {
                    var adapter = acti.VirtualMachineAdapter ??=
                        new VirtualMachineAdapter { Version = 6, ObjectFormat = 2 };
                    foreach (var s in r.Scripts)
                    {
                        if (!BuildScriptEntry(s.Name, s.Flags, s.Properties, out var entry, out var se)) return Fail(se);
                        adapter.Scripts.Add(entry);
                    }
                }
                formKey = acti.FormKey.ToString();
                break;
            }
            case "outfit":
            {
                // OS-14 — OTFT outfit: a list of worn items (ARMO/LVLI/NPC_ via IOutfitTarget).
                // An NPC's defaultOutfit points here; AddNew + Items (reuses the FormList Items
                // field — both are bare FormLink lists). Concrete record -> AddNew (like book:2130).
                var otft = mod.Outfits.AddNew(r.EditorId);
                if (r.Items is { Count: > 0 })
                {
                    otft.Items ??= new();
                    foreach (var it in r.Items)
                    { if (!TryKey(it, out var ik, out var e)) return Fail(e); otft.Items.Add(new FormLink<IOutfitTargetGetter>(ik)); }
                }
                formKey = otft.FormKey.ToString();
                break;
            }
            case "static":
            {
                // OS-02 — STAT: a static collection prop (settlement clutter). Name + Model(+MSWP) +
                // OBND. No keywords/flags MVP (the bare prop fields). Concrete -> AddNew.
                var st = mod.Statics.AddNew(r.EditorId);
                if (r.Name is { } n) st.Name = n;
                if (r.Model is { } mdl)
                {
                    var m = new Model { File = mdl };
                    if (r.MaterialSwap is { } msw)
                    { if (!TryKey(msw, out var mk, out var me)) return Fail(me); m.MaterialSwap.SetTo(mk); }
                    st.Model = m;
                }
                if (r.ObjectBounds is { } ob)
                {
                    if (ob.Length != 6) return Fail($"objectBounds needs 6 ints [x1,y1,z1,x2,y2,z2], got {ob.Length}");
                    st.ObjectBounds.First = new Noggog.P3Int16(ob[0], ob[1], ob[2]);
                    st.ObjectBounds.Second = new Noggog.P3Int16(ob[3], ob[4], ob[5]);
                }
                formKey = st.FormKey.ToString();
                break;
            }
            case "door":
            {
                // OS-02 — DOOR: Name + Model(+MSWP) + Keywords + Flags (Door.Flag). Concrete -> AddNew.
                var door = mod.Doors.AddNew(r.EditorId);
                if (r.Name is { } n) door.Name = n;
                if (r.Model is { } mdl)
                {
                    var m = new Model { File = mdl };
                    if (r.MaterialSwap is { } msw)
                    { if (!TryKey(msw, out var mk, out var me)) return Fail(me); m.MaterialSwap.SetTo(mk); }
                    door.Model = m;
                }
                if (r.Keywords is { Count: > 0 })
                {
                    door.Keywords ??= new();
                    foreach (var kw in r.Keywords)
                    { if (!TryKey(kw, out var kk, out var e)) return Fail(e); door.Keywords.Add(new FormLink<IKeywordGetter>(kk)); }
                }
                if (r.Flags is { Count: > 0 })
                    foreach (var fn in r.Flags)
                    {
                        if (!Enum.TryParse<Door.Flag>(fn, true, out var fl))
                            return Fail($"bad door flag '{fn}' (Automatic|Hidden|MinimalUse|Sliding|DoNotOpenInCombatSearch|NoToText)");
                        door.Flags |= fl;
                    }
                formKey = door.FormKey.ToString();
                break;
            }
            case "light":
            {
                // OS-02 — LIGH: Name + Model(+MSWP) + Keywords + Value/Weight + Radius + Flags
                // (Light.Flag). Color (System.Drawing.Color) deferred MVP. Concrete -> AddNew.
                var ligh = mod.Lights.AddNew(r.EditorId);
                if (r.Name is { } n) ligh.Name = n;
                if (r.Model is { } mdl)
                {
                    var m = new Model { File = mdl };
                    if (r.MaterialSwap is { } msw)
                    { if (!TryKey(msw, out var mk, out var me)) return Fail(me); m.MaterialSwap.SetTo(mk); }
                    ligh.Model = m;
                }
                if (r.Keywords is { Count: > 0 })
                {
                    ligh.Keywords ??= new();
                    foreach (var kw in r.Keywords)
                    { if (!TryKey(kw, out var kk, out var e)) return Fail(e); ligh.Keywords.Add(new FormLink<IKeywordGetter>(kk)); }
                }
                if (r.Value is { } val) { if (val < 0) return Fail($"light value out of range: {val}"); ligh.Value = (uint)val; }
                if (r.Weight is { } wt) { if (wt < 0) return Fail($"light weight out of range: {wt}"); ligh.Weight = wt; }
                if (r.Radius is { } rad) { if (rad < 0) return Fail($"light radius out of range: {rad}"); ligh.Radius = (uint)rad; }
                if (r.Flags is { Count: > 0 })
                    foreach (var fn in r.Flags)
                    {
                        if (!Enum.TryParse<Light.Flag>(fn, true, out var fl))
                            return Fail($"bad light flag '{fn}' (CanBeCarried|Flicker|OffByDefault|Pulse|...)");
                        ligh.Flags |= fl;
                    }
                formKey = ligh.FormKey.ToString();
                break;
            }
            case "container":
            {
                // OS-02 — CONT: a loot stash. Name + Model(+MSWP) + Keywords + Flags (Container.Flag) +
                // Items (reuses the NPC ContainerEntry/ContainerItem inventory idiom). Concrete -> AddNew.
                var cont = mod.Containers.AddNew(r.EditorId);
                if (r.Name is { } n) cont.Name = n;
                if (r.Model is { } mdl)
                {
                    var m = new Model { File = mdl };
                    if (r.MaterialSwap is { } msw)
                    { if (!TryKey(msw, out var mk, out var me)) return Fail(me); m.MaterialSwap.SetTo(mk); }
                    cont.Model = m;
                }
                if (r.Keywords is { Count: > 0 })
                {
                    cont.Keywords ??= new();
                    foreach (var kw in r.Keywords)
                    { if (!TryKey(kw, out var kk, out var e)) return Fail(e); cont.Keywords.Add(new FormLink<IKeywordGetter>(kk)); }
                }
                if (r.Flags is { Count: > 0 })
                    foreach (var fn in r.Flags)
                    {
                        if (!Enum.TryParse<Container.Flag>(fn, true, out var fl))
                            return Fail($"bad container flag '{fn}' (AllowSoundsWhenAnimation|Respawns|ShowOwner)");
                        cont.Flags |= fl;
                    }
                if (r.Inventory is { Count: > 0 })
                {
                    cont.Items ??= new();
                    foreach (var it in r.Inventory)
                    {
                        if (it.Count < 0) return Fail($"container item count out of range: {it.Count}");
                        if (!TryKey(it.Item, out var ik, out var e)) return Fail(e);
                        var entry = new ContainerEntry { Item = new ContainerItem { Count = it.Count } };
                        entry.Item.Item.SetTo(ik);
                        cont.Items.Add(entry);
                    }
                }
                formKey = cont.FormKey.ToString();
                break;
            }
            case "ingestible":
            case "ingredient":
            {
                // OS-02 — ALCH (ingestible: chem/food/stimpak) / INGR (ingredient). Both carry
                // Name + Model(+MSWP) + Keywords + Value/Weight + Effects (the magic-effect list).
                // ALCH also takes Flags (Ingestible.Flag); INGR's Value is Int32 vs ALCH's UInt32.
                bool isAlch = r.Type!.Trim().ToLowerInvariant() == "ingestible";
                if (isAlch)
                {
                    var alch = mod.Ingestibles.AddNew(r.EditorId);
                    if (r.Name is { } n) alch.Name = n;
                    if (r.Model is { } mdl)
                    {
                        var m = new Model { File = mdl };
                        if (r.MaterialSwap is { } msw)
                        { if (!TryKey(msw, out var mk, out var me)) return Fail(me); m.MaterialSwap.SetTo(mk); }
                        alch.Model = m;
                    }
                    if (r.Keywords is { Count: > 0 })
                    {
                        alch.Keywords ??= new();
                        foreach (var kw in r.Keywords)
                        { if (!TryKey(kw, out var kk, out var e)) return Fail(e); alch.Keywords.Add(new FormLink<IKeywordGetter>(kk)); }
                    }
                    if (r.Value is { } val) { if (val < 0) return Fail($"ingestible value out of range: {val}"); alch.Value = (uint)val; }
                    if (r.Weight is { } wt) { if (wt < 0) return Fail($"ingestible weight out of range: {wt}"); alch.Weight = wt; }
                    if (r.Flags is { Count: > 0 })
                        foreach (var fn in r.Flags)
                        {
                            if (!Enum.TryParse<Ingestible.Flag>(fn, true, out var fl))
                                return Fail($"bad ingestible flag '{fn}' (NoAutoCalc|FoodItem|Medicine|Poison)");
                            alch.Flags |= fl;
                        }
                    if (r.Effects is { Count: > 0 })
                        foreach (var es in r.Effects)
                        { if (!BuildEffect(es, out var ef, out var ee)) return Fail(ee); alch.Effects.Add(ef); }
                    formKey = alch.FormKey.ToString();
                }
                else
                {
                    var ingr = mod.Ingredients.AddNew(r.EditorId);
                    if (r.Name is { } n) ingr.Name = n;
                    if (r.Model is { } mdl)
                    {
                        var m = new Model { File = mdl };
                        if (r.MaterialSwap is { } msw)
                        { if (!TryKey(msw, out var mk, out var me)) return Fail(me); m.MaterialSwap.SetTo(mk); }
                        ingr.Model = m;
                    }
                    if (r.Keywords is { Count: > 0 })
                    {
                        ingr.Keywords ??= new();
                        foreach (var kw in r.Keywords)
                        { if (!TryKey(kw, out var kk, out var e)) return Fail(e); ingr.Keywords.Add(new FormLink<IKeywordGetter>(kk)); }
                    }
                    if (r.Value is { } val) { if (val < 0) return Fail($"ingredient value out of range: {val}"); ingr.Value = val; }
                    if (r.Weight is { } wt) { if (wt < 0) return Fail($"ingredient weight out of range: {wt}"); ingr.Weight = wt; }
                    if (r.Effects is { Count: > 0 })
                        foreach (var es in r.Effects)
                        { if (!BuildEffect(es, out var ef, out var ee)) return Fail(ee); ingr.Effects.Add(ef); }
                    formKey = ingr.FormKey.ToString();
                }
                break;
            }
            case "location":
            {
                // W8 — LCTN. MVP = name + parentLocation + keywords. The many ref-list fields
                // (LocationRefTypeReferences*, persistent/unique actor refs, worldspace cells)
                // deferred (niche; filled by quest/cell context, not bare authoring).
                var lctn = mod.Locations.AddNew(r.EditorId);
                if (r.Name is { } n) lctn.Name = n;
                if (!string.IsNullOrWhiteSpace(r.ParentLocation))
                { if (!TryKey(r.ParentLocation, out var k, out var e)) return Fail(e); lctn.ParentLocation.SetTo(k); }
                if (r.Keywords is { Count: > 0 })
                {
                    lctn.Keywords ??= new();
                    foreach (var kw in r.Keywords)
                    { if (!TryKey(kw, out var kk, out var e)) return Fail(e); lctn.Keywords.Add(new FormLink<IKeywordGetter>(kk)); }
                }
                formKey = lctn.FormKey.ToString();
                break;
            }
            case "locationreftype":
            {
                // W8 — LCRT. A bare reference-type tag (like KYWD); Color/TNAM deferred.
                var lcrt = mod.LocationReferenceTypes.AddNew(r.EditorId);
                formKey = lcrt.FormKey.ToString();
                break;
            }
            case "encounterzone":
            {
                // W8 — ECZN. MVP = flags + location + owner + min/max level + rank. Concrete AddNew.
                var eczn = mod.EncounterZones.AddNew(r.EditorId);
                if (r.Flags is { Count: > 0 })
                    foreach (var fn in r.Flags)
                    {
                        if (!Enum.TryParse<EncounterZone.Flag>(fn, true, out var fl))
                            return Fail($"bad encounterZone flag '{fn}' (NeverResets|MatchPcBelowMinimumLevel|DisableCombatBoundary|Workshop)");
                        eczn.Flags |= fl;
                    }
                if (!string.IsNullOrWhiteSpace(r.Location))
                { if (!TryKey(r.Location, out var k, out var e)) return Fail(e); eczn.Location.SetTo(k); }
                if (!string.IsNullOrWhiteSpace(r.Owner))
                { if (!TryKey(r.Owner, out var k, out var e)) return Fail(e); eczn.Owner.SetTo(k); }
                if (r.MinLevel is { } mnl) { if (mnl < 0 || mnl > 255) return Fail($"minLevel out of range (0-255): {mnl}"); eczn.MinLevel = (byte)mnl; }
                if (r.MaxLevel is { } mxl) { if (mxl < 0 || mxl > 255) return Fail($"maxLevel out of range (0-255): {mxl}"); eczn.MaxLevel = (byte)mxl; }
                if (r.Rank is { } rnk) { if (rnk < 0 || rnk > 255) return Fail($"rank out of range (0-255): {rnk}"); eczn.Rank = (byte)rnk; }
                formKey = eczn.FormKey.ToString();
                break;
            }
            case "package":
            {
                // W7 — PACK template-bind MVP: PackageTemplate + type + flags + conditions +
                // ownerQuest + combatStyle. The Data input-map (sbyte index -> template Public
                // input) is the DEFERRED semantic research gate (wrong index = silently broken AI;
                // needs a per-template index map validated vs live Fallout4.esm templates +
                // fo4_inspect_package_template). ProcedureTree/IdleAnimations also deferred.
                var pack = mod.Packages.AddNew(r.EditorId);
                if (!string.IsNullOrWhiteSpace(r.PackageTemplate))
                { if (!TryKey(r.PackageTemplate, out var k, out var e)) return Fail(e); pack.PackageTemplate.SetTo(k); }
                if (!string.IsNullOrWhiteSpace(r.PackageType))
                {
                    if (!Enum.TryParse<Package.Types>(r.PackageType, true, out var pt))
                        return Fail($"bad packageType '{r.PackageType}' (Package|PackageTemplate)");
                    pack.Type = pt;
                }
                if (r.Flags is { Count: > 0 })
                    foreach (var fn in r.Flags)
                    {
                        if (!Enum.TryParse<Package.Flag>(fn, true, out var fl))
                            return Fail($"bad package flag '{fn}' (OffersServices|MustComplete|...)");
                        pack.Flags |= fl;
                    }
                if (!string.IsNullOrWhiteSpace(r.OwnerQuest))
                { if (!TryKey(r.OwnerQuest, out var k, out var e)) return Fail(e); pack.OwnerQuest.SetTo(k); }
                if (!string.IsNullOrWhiteSpace(r.CombatStyle))
                { if (!TryKey(r.CombatStyle, out var k, out var e)) return Fail(e); pack.CombatStyle.SetTo(k); }
                if (r.Conditions is { Count: > 0 })
                    foreach (var cs in r.Conditions)
                    { if (!BuildCondition(cs, out var cond, out var ce)) return Fail(ce); pack.Conditions.Add(cond); }
                // W7-Data: a single location data-input (Travel "Place to Travel" / Sandbox
                // "Location"). The slot index is resolved by name against the live template, so
                // the child's Data key + DataInputVersion stay aligned with the engine binding.
                if (r.DataLocation is { } dl)
                {
                    if (pack.PackageTemplate.IsNull)
                        return Fail("dataLocation requires packageTemplate (the input index is defined by the template)");
                    if (string.IsNullOrWhiteSpace(mastersDir))
                        return Fail("dataLocation requires --masters-dir to resolve the template input index by name");
                    if (string.IsNullOrWhiteSpace(dl.Target))
                        return Fail("dataLocation requires target (FormKey of the reference/cell/keyword)");
                    if (!ResolvePackageLocationInput(mastersDir!, pack.PackageTemplate.FormKey, dl.Input,
                            out var di, out var dver, out var rie)) return Fail(rie);
                    if (!TryKey(dl.Target, out var gk, out var gke)) return Fail(gke);
                    ALocationTarget locTarget = (dl.TargetType ?? "reference").ToLowerInvariant() switch
                    {
                        "reference" => new LocationTarget { Link = new FormLink<IPlacedGetter>(gk) },
                        "cell" => new LocationCell { Link = new FormLink<ICellGetter>(gk) },
                        "keyword" => new LocationKeyword { Link = new FormLink<IKeywordGetter>(gk) },
                        _ => null!,
                    };
                    if (locTarget is null)
                        return Fail($"bad dataLocation.targetType '{dl.TargetType}' (reference|cell|keyword)");
                    pack.Data[di] = new PackageDataLocation
                    {
                        Name = dl.Input,
                        Location = new LocationTargetRadius { Target = locTarget, Radius = dl.Radius },
                    };
                    pack.DataInputVersion = dver;
                }
                formKey = pack.FormKey.ToString();
                break;
            }
            default:
                return Fail($"unsupported record type: {r.Type}");
        }
        made.Add(new Dictionary<string, object?>
        {
            ["type"] = r.Type, ["editorId"] = r.EditorId, ["formKey"] = formKey,
        });
    }

    try
    {
        var dir = Path.GetDirectoryName(Path.GetFullPath(outPath));
        if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
        mod.WriteToBinary(outPath);
    }
    catch (Exception e) { return Fail($"write error: {e.Message}"); }

    // ---- read-back proof: re-open the written binary and report what persisted ----
    // Proves the records (and any FormLink fields) survived serialize->disk, and
    // that referenced masters were auto-added to the header. A separate process
    // would be more independent, but re-opening the on-disk file from scratch
    // (fresh overlay) already exercises the real binary round-trip.
    var masters = new List<string>();
    try
    {
        var check = Fallout4Mod.CreateFromBinaryOverlay(new ModPath(outPath), Fallout4Release.Fallout4);
        foreach (var m in check.ModHeader.MasterReferences) masters.Add(m.Master.ToString());
        var back = new Dictionary<string, Dictionary<string, object?>>();
        foreach (var g in check.Npcs)
            back[g.FormKey.ToString()] = new Dictionary<string, object?>
            {
                ["race"] = g.Race.FormKeyNullable?.ToString(),
                ["class"] = g.Class.FormKeyNullable?.ToString(),
                ["factionCount"] = g.Factions.Count,
                // W3b full-field read-back
                ["voice"] = g.Voice.FormKeyNullable?.ToString(),
                ["combatStyle"] = g.CombatStyle.FormKeyNullable?.ToString(),
                ["defaultOutfit"] = g.DefaultOutfit.FormKeyNullable?.ToString(),
                ["attackRace"] = g.AttackRace.FormKeyNullable?.ToString(),
                ["skin"] = g.Skin.FormKeyNullable?.ToString(),
                ["aggression"] = g.Aggression.ToString(),
                ["confidence"] = g.Confidence.ToString(),
                ["assistance"] = g.Assistance.ToString(),
                ["responsibility"] = g.Responsibility.ToString(),
                ["mood"] = g.Mood.ToString(),
                ["keywordCount"] = g.Keywords?.Count ?? 0,
                ["itemCount"] = g.Items?.Count ?? 0,
                ["perkCount"] = g.Perks?.Count ?? 0,
                ["packageCount"] = g.Packages?.Count ?? 0,
                // W3c template-chain: DefaultTemplate FormLink + the raw bitfield int
                // (byte-exact round-trip proof — non-[Flags] enum stringifies composites
                // as the number, so the int is the authoritative read-back).
                ["defaultTemplate"] = g.DefaultTemplate.FormKeyNullable?.ToString(),
                ["useTemplateActors"] = (int)g.UseTemplateActors,
                // OS-14: raw actor-flags bitfield (Essential=2|Protected=256|...) — byte-exact proof.
                ["flags"] = (int)g.Flags,
            };
        foreach (var g in check.Armors)
            back[g.FormKey.ToString()] = new Dictionary<string, object?>
            {
                ["name"] = g.Name?.String,
                ["value"] = g.Value,
                ["weight"] = g.Weight,
                ["armorRating"] = g.ArmorRating,
                ["keywordCount"] = g.Keywords?.Count ?? 0,
                ["bipedSlotCount"] = g.BipedBodyTemplate is { } bt
                    ? System.Numerics.BitOperations.PopCount((uint)bt.FirstPersonFlags) : 0,
                // Kerem-polish: armature link count + race — the worn-mesh chain (0 = invisible armor).
                ["armatureCount"] = g.Armatures?.Count ?? 0,
                ["race"] = g.Race.FormKeyNullable?.ToString(),
            };
        // OS-01 WEAP: DNAM stats + FormLinks + keyword/attach-slot/model round-trip proof.
        foreach (var g in check.Weapons)
            back[g.FormKey.ToString()] = new Dictionary<string, object?>
            {
                ["name"] = g.Name?.String,
                ["value"] = (int)g.Value,
                ["weight"] = g.Weight,
                ["baseDamage"] = (int)g.BaseDamage,
                ["speed"] = g.Speed,
                ["reach"] = g.Reach,
                ["minRange"] = g.MinRange,
                ["maxRange"] = g.MaxRange,
                ["ammoCapacity"] = (int)g.Capacity,
                ["ammo"] = g.Ammo.FormKeyNullable?.ToString(),
                ["attackSound"] = g.AttackSound.FormKeyNullable?.ToString(),
                ["equipSound"] = g.EquipSound.FormKeyNullable?.ToString(),
                ["animationType"] = g.AnimationType.ToString(),
                ["keywordCount"] = g.Keywords?.Count ?? 0,
                ["attachSlotCount"] = g.AttachParentSlots?.Count ?? 0,
                ["modelFile"] = g.Model?.File,
            };
        // BOOK/note round-trip: the readable body (BookText) is the proof the coupon copy
        // survived serialize->disk; value/weight/keywords confirm the item fields.
        foreach (var g in check.Books)
            back[g.FormKey.ToString()] = new Dictionary<string, object?>
            {
                ["name"] = g.Name?.String,
                ["bookText"] = g.BookText?.String,
                ["value"] = g.Value,
                ["weight"] = g.Weight,
                ["keywordCount"] = g.Keywords?.Count ?? 0,
                // Visual proof: world-model nif + the MSWP link that retextures it.
                ["modelFile"] = g.Model?.File,
                ["materialSwap"] = g.Model?.MaterialSwap.IsNull == false
                    ? g.Model.MaterialSwap.FormKey.ToString() : null,
            };
        // MISC round-trip: model + item fields prove the clutter coupon survived serialize->disk.
        foreach (var g in check.MiscItems)
            back[g.FormKey.ToString()] = new Dictionary<string, object?>
            {
                ["name"] = g.Name?.String,
                ["value"] = g.Value,
                ["weight"] = g.Weight,
                ["keywordCount"] = g.Keywords?.Count ?? 0,
                ["modelFile"] = g.Model?.File,
                ["materialSwap"] = g.Model?.MaterialSwap.IsNull == false
                    ? g.Model.MaterialSwap.FormKey.ToString() : null,
                // OBND proof: a zero box (the no-show bug) must never ship green again.
                ["objectBounds"] = new[] { g.ObjectBounds.First.X, g.ObjectBounds.First.Y, g.ObjectBounds.First.Z,
                                           g.ObjectBounds.Second.X, g.ObjectBounds.Second.Y, g.ObjectBounds.Second.Z },
                ["objectBoundsZero"] = g.ObjectBounds.First.X == 0 && g.ObjectBounds.First.Y == 0 && g.ObjectBounds.First.Z == 0
                                    && g.ObjectBounds.Second.X == 0 && g.ObjectBounds.Second.Y == 0 && g.ObjectBounds.Second.Z == 0,
                // PTRN proof: the Pip-Boy/Inspect preview transform must be set (null = blank flat-item preview).
                ["previewTransform"] = g.PreviewTransform.FormKeyNullable?.ToString(),
            };
        foreach (var g in check.Quests)
            back[g.FormKey.ToString()] = new Dictionary<string, object?>
            {
                ["name"] = g.Name?.String,
                ["questType"] = g.Data?.Type.ToString(),
                ["stageCount"] = g.Stages.Count,
                // QSDT proof: on re-read, a log entry's Flags is non-null iff its QSDT
                // marker was in the binary. RunOnStart proof: stage INDX flag 0x02.
                ["logEntryQsdtCount"] = g.Stages.Sum(s => s.LogEntries.Count(le => le.Flags != null)),
                ["runOnStartStageCount"] = g.Stages.Count(s => s.Flags.HasFlag(QuestStage.Flag.RunOnStart)),
                ["objectiveCount"] = g.Objectives.Count,
                // W2: QSTA target round-trip (sum across objectives) + objectives carrying flags.
                ["objectiveTargetCount"] = g.Objectives.Sum(o => o.Targets?.Count ?? 0),
                ["objectiveFlaggedCount"] = g.Objectives.Count(o => o.Flags != null && o.Flags != 0),
                ["topicCount"] = g.DialogTopics.Count,
                ["infoCount"] = g.DialogTopics.Sum(dt => dt.Responses.Count),
                ["lineCount"] = g.DialogTopics.Sum(dt => dt.Responses.Sum(rs => rs.Responses.Count)),
                ["conditionCount"] = g.DialogTopics.Sum(dt => dt.Responses.Sum(rs => rs.Conditions.Count)),
                // OS-04: per-INFO TIF VMAD fragment round-trip proof — how many INFOs carry a
                // ScriptFragments adapter + the first fragment script name (re-read from binary).
                ["infoFragmentCount"] = g.DialogTopics.Sum(dt => dt.Responses.Count(rs => rs.VirtualMachineAdapter?.ScriptFragments != null)),
                ["infoFragmentScriptName"] = g.DialogTopics.SelectMany(dt => dt.Responses)
                    .Select(rs => rs.VirtualMachineAdapter?.ScriptFragments?.Script?.Name)
                    .FirstOrDefault(n => n != null),
                // Kerem-polish: DLBR branch round-trip proof — branch count + how many topics are
                // linked to a branch (0 branched topics = bare DIAL/INFO that won't surface in the wheel).
                ["branchCount"] = g.DialogBranches.Count,
                ["branchedTopicCount"] = g.DialogTopics.Count(dt => !dt.Branch.IsNull),
                ["aliasCount"] = g.Aliases?.Count ?? 0,
                ["scriptCount"] = g.VirtualMachineAdapter?.Scripts.Count ?? 0,
                ["scriptPropertyCount"] = g.VirtualMachineAdapter?.Scripts.Sum(se => se.Properties.Count) ?? 0,
                ["fragmentCount"] = g.VirtualMachineAdapter?.Fragments.Count ?? 0,
                ["fragmentScriptName"] = g.VirtualMachineAdapter?.Script?.Name,
                ["aliasFragmentCount"] = g.VirtualMachineAdapter?.Aliases.Count ?? 0,
                ["sceneCount"] = g.Scenes.Count,
                ["sceneActionCount"] = g.Scenes.Sum(s => s.Actions.Count),
            };
        // W1.5 glue records (Faz 3): same round-trip-proof contract.
        foreach (var g in check.Keywords)
            back[g.FormKey.ToString()] = new Dictionary<string, object?>
            {
                ["name"] = g.Name?.String,
            };
        foreach (var g in check.FormLists)
            back[g.FormKey.ToString()] = new Dictionary<string, object?>
            {
                ["name"] = g.Name?.String,
                ["itemCount"] = g.Items.Count,
            };
        foreach (var g in check.Messages)
            back[g.FormKey.ToString()] = new Dictionary<string, object?>
            {
                ["text"] = g.Description?.String,
                ["name"] = g.Name?.String,
                // OS-11: menu-button count + per-button text + the raw flag bitfield (MessageBox=1).
                ["flags"] = (int)g.Flags,
                ["buttonCount"] = g.MenuButtons.Count,
                ["buttons"] = g.MenuButtons.Select(b => new Dictionary<string, object?>
                {
                    ["text"] = b.Text?.String,
                    ["conditionCount"] = b.Conditions.Count,
                }).ToList(),
            };
        // MSWP material-swap: substitution count + each original->replacement pair
        // is the proof the retexture map survived to disk.
        foreach (var g in check.MaterialSwaps)
            back[g.FormKey.ToString()] = new Dictionary<string, object?>
            {
                ["substitutionCount"] = g.Substitutions.Count,
                ["substitutions"] = g.Substitutions.Select(s => new Dictionary<string, object?>
                {
                    ["original"] = s.OriginalMaterial,
                    ["replacement"] = s.ReplacementMaterial,
                }).ToList(),
            };
        // OS-08 COBJ: output/bench + component/category/condition counts round-trip proof.
        foreach (var g in check.ConstructibleObjects)
            back[g.FormKey.ToString()] = new Dictionary<string, object?>
            {
                ["createdObject"] = g.CreatedObject.FormKeyNullable?.ToString(),
                ["workbenchKeyword"] = g.WorkbenchKeyword.FormKeyNullable?.ToString(),
                ["createdObjectCount"] = (int?)g.CreatedObjectCounts?.FirstOrDefault()?.Count,
                ["componentCount"] = g.Components?.Count ?? 0,
                ["components"] = g.Components?.Select(c => new Dictionary<string, object?>
                {
                    ["component"] = c.Component.FormKeyNullable?.ToString(),
                    ["count"] = (int)c.Count,
                }).ToList(),
                ["categoryCount"] = g.Categories?.Count ?? 0,
                ["conditionCount"] = g.Conditions.Count,
                ["menuArt"] = g.MenuArtObject.FormKeyNullable?.ToString(),
            };
        foreach (var g in check.Globals)
            back[g.FormKey.ToString()] = new Dictionary<string, object?>
            {
                // The concrete subclass (interface-matched on the overlay) proves which
                // GlobalType persisted; report it normalized as float|int|short.
                ["globalType"] = g switch
                {
                    IGlobalFloatGetter => "float",
                    IGlobalIntGetter => "int",
                    IGlobalShortGetter => "short",
                    _ => null,
                },
                ["value"] = g switch
                {
                    IGlobalFloatGetter gf => (double?)gf.Data,
                    IGlobalIntGetter gi => (double?)gi.Data,
                    IGlobalShortGetter gs => (double?)gs.Data,
                    _ => null,
                },
            };
        foreach (var g in check.Factions)
            back[g.FormKey.ToString()] = new Dictionary<string, object?>
            {
                ["name"] = g.Name?.String,
                ["flagCount"] = System.Numerics.BitOperations.PopCount((uint)g.Flags),
                ["relationCount"] = g.Relations.Count,
                // OS-11: rank list + vendor-data presence round-trip proof.
                ["rankCount"] = g.Ranks.Count,
                ["hasVendorValues"] = g.VendorValues != null,
            };
        // W3d/W3e leveled lists: entry list + flags round-trip (per-entry reference/level/
        // count proves the Leveled*EntryData persisted).
        foreach (var g in check.LeveledNpcs)
            back[g.FormKey.ToString()] = new Dictionary<string, object?>
            {
                ["entryCount"] = g.Entries?.Count ?? 0,
                ["flags"] = (int)g.Flags,
                // OS-11: chanceNone read back as the authored 0-100 int (Percent fraction *100).
                ["chanceNone"] = (int)Math.Round(g.ChanceNone.Value * 100),
                ["entries"] = g.Entries?.Select(e => new Dictionary<string, object?>
                {
                    ["reference"] = e.Data?.Reference.FormKey.ToString(),
                    ["level"] = (int?)e.Data?.Level,
                    ["count"] = (int?)e.Data?.Count,
                }).ToList(),
            };
        foreach (var g in check.LeveledItems)
            back[g.FormKey.ToString()] = new Dictionary<string, object?>
            {
                ["entryCount"] = g.Entries?.Count ?? 0,
                ["flags"] = (int)g.Flags,
                ["chanceNone"] = (int)Math.Round(g.ChanceNone.Value * 100),
                ["entries"] = g.Entries?.Select(e => new Dictionary<string, object?>
                {
                    ["reference"] = e.Data?.Reference.FormKey.ToString(),
                    ["level"] = (int?)e.Data?.Level,
                    ["count"] = (int?)e.Data?.Count,
                }).ToList(),
            };
        // W6 Story Manager Quest Nodes: parent/sibling links + conditions + quests round-trip.
        foreach (var g in check.StoryManagerQuestNodes)
            back[g.FormKey.ToString()] = new Dictionary<string, object?>
            {
                ["parent"] = g.Parent.FormKeyNullable?.ToString(),
                ["previousSibling"] = g.PreviousSibling.FormKeyNullable?.ToString(),
                ["flags"] = (int)g.Flags,
                ["maxConcurrentQuests"] = g.MaxConcurrentQuests,
                ["maxNumQuestsToRun"] = g.MaxNumQuestsToRun,
                ["hoursUntilReset"] = g.HoursUntilReset,
                ["conditionCount"] = g.Conditions?.Count ?? 0,
                ["questCount"] = g.Quests.Count,
                ["quests"] = g.Quests.Select(sq => sq.Quest.FormKeyNullable?.ToString()).ToList(),
            };
        // W6.5 Activator + W8 Location/LocationReferenceType/EncounterZone round-trip.
        foreach (var g in check.Activators)
            back[g.FormKey.ToString()] = new Dictionary<string, object?>
            {
                ["name"] = g.Name?.String,
                ["keywordCount"] = g.Keywords?.Count ?? 0,
                ["scriptCount"] = g.VirtualMachineAdapter?.Scripts.Count ?? 0,
            };
        // OS-14 OTFT: worn-item count is the round-trip proof the outfit survived to disk.
        foreach (var g in check.Outfits)
            back[g.FormKey.ToString()] = new Dictionary<string, object?>
            {
                ["itemCount"] = g.Items?.Count ?? 0,
            };
        // OS-02 common world base records — model/keyword + per-type round-trip proof.
        foreach (var g in check.Statics)
            back[g.FormKey.ToString()] = new Dictionary<string, object?>
            {
                ["name"] = g.Name?.String,
                ["modelFile"] = g.Model?.File,
            };
        foreach (var g in check.Doors)
            back[g.FormKey.ToString()] = new Dictionary<string, object?>
            {
                ["name"] = g.Name?.String,
                ["modelFile"] = g.Model?.File,
                ["keywordCount"] = g.Keywords?.Count ?? 0,
                ["flags"] = (int)g.Flags,
            };
        foreach (var g in check.Lights)
            back[g.FormKey.ToString()] = new Dictionary<string, object?>
            {
                ["name"] = g.Name?.String,
                ["modelFile"] = g.Model?.File,
                ["keywordCount"] = g.Keywords?.Count ?? 0,
                ["value"] = (int)g.Value,
                ["weight"] = g.Weight,
                ["radius"] = (int)g.Radius,
                ["flags"] = (int)g.Flags,
            };
        foreach (var g in check.Containers)
            back[g.FormKey.ToString()] = new Dictionary<string, object?>
            {
                ["name"] = g.Name?.String,
                ["modelFile"] = g.Model?.File,
                ["keywordCount"] = g.Keywords?.Count ?? 0,
                ["itemCount"] = g.Items?.Count ?? 0,
                ["flags"] = (int)g.Flags,
            };
        foreach (var g in check.Ingestibles)
            back[g.FormKey.ToString()] = new Dictionary<string, object?>
            {
                ["name"] = g.Name?.String,
                ["modelFile"] = g.Model?.File,
                ["keywordCount"] = g.Keywords?.Count ?? 0,
                ["value"] = (int)g.Value,
                ["weight"] = g.Weight,
                ["effectCount"] = g.Effects?.Count ?? 0,
                ["flags"] = (int)g.Flags,
            };
        foreach (var g in check.Ingredients)
            back[g.FormKey.ToString()] = new Dictionary<string, object?>
            {
                ["name"] = g.Name?.String,
                ["modelFile"] = g.Model?.File,
                ["keywordCount"] = g.Keywords?.Count ?? 0,
                ["value"] = g.Value,
                ["weight"] = g.Weight,
                ["effectCount"] = g.Effects?.Count ?? 0,
            };
        foreach (var g in check.Locations)
            back[g.FormKey.ToString()] = new Dictionary<string, object?>
            {
                ["name"] = g.Name?.String,
                ["parentLocation"] = g.ParentLocation.FormKeyNullable?.ToString(),
                ["keywordCount"] = g.Keywords?.Count ?? 0,
            };
        foreach (var g in check.LocationReferenceTypes)
            back[g.FormKey.ToString()] = new Dictionary<string, object?> { ["editorId"] = g.EditorID };
        foreach (var g in check.EncounterZones)
            back[g.FormKey.ToString()] = new Dictionary<string, object?>
            {
                ["flags"] = (int)g.Flags,
                ["location"] = g.Location.IsNull ? null : g.Location.FormKey.ToString(),
                ["owner"] = g.Owner.IsNull ? null : g.Owner.FormKey.ToString(),
                ["minLevel"] = (int)g.MinLevel,
                ["maxLevel"] = (int)g.MaxLevel,
                ["rank"] = (int)g.Rank,
            };
        // W7 AI packages: template-bind round-trip.
        foreach (var g in check.Packages)
            back[g.FormKey.ToString()] = new Dictionary<string, object?>
            {
                ["packageTemplate"] = g.PackageTemplate.IsNull ? null : g.PackageTemplate.FormKey.ToString(),
                ["type"] = g.Type.ToString(),
                ["flagCount"] = System.Numerics.BitOperations.PopCount((ulong)g.Flags),
                ["conditionCount"] = g.Conditions?.Count ?? 0,
                ["ownerQuest"] = g.OwnerQuest.FormKeyNullable?.ToString(),
                // W7-Data: location data-input round-trip proof.
                ["dataInputCount"] = g.Data.Count,
                ["dataInputVersion"] = g.DataInputVersion,
                ["dataLocationCount"] = g.Data.Values.OfType<IPackageDataLocationGetter>().Count(),
            };
        // W4 interior cells: walk the block hierarchy; report which block/subblock the cell
        // landed in (proves the FormID-hash placement) + each nested ref's base/position/scale.
        foreach (var b in check.Cells.Records)
            foreach (var s in b.SubBlocks)
                foreach (var g in s.Cells)
                    back[g.FormKey.ToString()] = new Dictionary<string, object?>
                    {
                        ["name"] = g.Name?.String,
                        ["interior"] = g.Flags.HasFlag(Cell.Flag.IsInteriorCell),
                        ["lightingTemplate"] = g.LightingTemplate.IsNull ? null : g.LightingTemplate.FormKey.ToString(),
                        ["location"] = g.Location.FormKeyNullable?.ToString(),
                        ["block"] = b.BlockNumber,
                        ["subBlock"] = s.BlockNumber,
                        ["persistentCount"] = g.Persistent.Count,
                        ["temporaryCount"] = g.Temporary.Count,
                        ["navmeshCount"] = g.NavigationMeshes.Count,
                        ["navmeshVerts"] = g.NavigationMeshes.FirstOrDefault()?.NavmeshGeometry?.Vertices.Count ?? 0,
                        ["navmeshTris"] = g.NavigationMeshes.FirstOrDefault()?.NavmeshGeometry?.Triangles.Count ?? 0,
                        ["placedObjects"] = g.Temporary.Concat(g.Persistent).OfType<IPlacedObjectGetter>()
                            .Select(p => new Dictionary<string, object?>
                            {
                                ["editorId"] = p.EditorID,
                                ["base"] = p.Base.FormKeyNullable?.ToString(),
                                ["position"] = new[] { p.Position.X, p.Position.Y, p.Position.Z },
                                ["scale"] = p.Scale,
                                ["teleportDoor"] = p.TeleportDestination?.Door.FormKey.ToString(),
                            }).ToList(),
                        ["placedNpcs"] = g.Temporary.Concat(g.Persistent).OfType<IPlacedNpcGetter>()
                            .Select(p => new Dictionary<string, object?>
                            {
                                ["editorId"] = p.EditorID,
                                ["base"] = p.Base.FormKeyNullable?.ToString(),
                                ["position"] = new[] { p.Position.X, p.Position.Y, p.Position.Z },
                            }).ToList(),
                    };
        // W5-ext (Kerem): exterior worldspace cell overrides round-trip proof — walk worldspace
        // sub-cells and report placed refs (the interior walk above misses worldspace-parented cells).
        foreach (var w in check.Worldspaces)
            foreach (var blk in w.SubCells)
                foreach (var sub in blk.Items)
                    foreach (var g in sub.Items)
                        back[g.FormKey.ToString()] = new Dictionary<string, object?>
                        {
                            ["name"] = g.Name?.String,
                            ["interior"] = g.Flags.HasFlag(Cell.Flag.IsInteriorCell),
                            ["worldspace"] = w.FormKey.ToString(),
                            ["persistentCount"] = g.Persistent.Count,
                            ["temporaryCount"] = g.Temporary.Count,
                            ["placedNpcs"] = g.Temporary.Concat(g.Persistent).OfType<IPlacedNpcGetter>()
                                .Select(p => new Dictionary<string, object?>
                                {
                                    ["editorId"] = p.EditorID,
                                    ["base"] = p.Base.FormKeyNullable?.ToString(),
                                    ["formKey"] = p.FormKey.ToString(),
                                    ["position"] = new[] { p.Position.X, p.Position.Y, p.Position.Z },
                                }).ToList(),
                        };
        foreach (var entry in made)
            if (entry["formKey"] is string fk && back.TryGetValue(fk, out var extra))
                foreach (var kv in extra) entry[kv.Key] = kv.Value;
    }
    catch (Exception e) { return Fail($"verify read-back error: {e.Message}"); }

    Console.Out.Write(JsonSerializer.Serialize(new { created = true, plugin = outPath, masters, records = made }));
    return 0;
}

// ---- lint-npc subcommand: stream NPCs + emit template/FaceGen flags ----
//
//   mutagen-cli lint-npc --plugin <path>
//
// stdout: {"plugin":..., "npcs":[{editorId, formKey, useTemplateActors, defaultTemplate,
//   headPartCount, faceMorphCount, faceTintingLayerCount}]}. Read-only binary overlay.
// exit 0 / 2 error. The lint POLICY (rule application + severity) lives in tools.py
// (fo4_lint_npc_template) — this verb is a thin data extractor, like the record query.
static int RunLintNpc(string[] args)
{
    string? pluginPath = null;
    for (int i = 1; i + 1 < args.Length; i += 2)
    {
        switch (args[i])
        {
            case "--plugin": pluginPath = args[i + 1]; break;
            default: return Fail($"unknown arg: {args[i]}");
        }
    }
    if (string.IsNullOrWhiteSpace(pluginPath)) return Fail("usage: mutagen-cli lint-npc --plugin <path>");
    if (!File.Exists(pluginPath)) return Fail($"plugin not found: {pluginPath}");

    var npcs = new List<Dictionary<string, object?>>();
    try
    {
        var mod = Fallout4Mod.CreateFromBinaryOverlay(new ModPath(pluginPath), Fallout4Release.Fallout4);
        foreach (var npc in mod.Npcs)
            npcs.Add(new Dictionary<string, object?>
            {
                ["editorId"] = npc.EditorID,
                ["formKey"] = npc.FormKey.ToString(),
                ["useTemplateActors"] = (int)npc.UseTemplateActors,
                ["defaultTemplate"] = npc.DefaultTemplate.FormKeyNullable?.ToString(),
                ["headPartCount"] = npc.HeadParts?.Count ?? 0,
                ["faceMorphCount"] = npc.FaceMorphs?.Count ?? 0,
                ["faceTintingLayerCount"] = npc.FaceTintingLayers?.Count ?? 0,
            });
    }
    catch (Exception e) { return Fail($"load error: {e.Message}"); }

    Console.Out.Write(JsonSerializer.Serialize(new { plugin = pluginPath, npcs }));
    return 0;
}

// ---- cell-info subcommand: precombine/previs safety signals for one cell (W5) ----
//
//   mutagen-cli cell-info --plugin <path> --record <FormID|EditorID>
//
// stdout: {found, formKey, editorId, interior, combinedMeshes, combinedMeshReferences,
//   preCombinedFilesTimestamp, preVisFilesTimestamp, hasPrecombines, hasPrevis,
//   persistentCount, temporaryCount}. The POLICY (block vs warn) lives in tools.py
// (fo4_check_previs_safety) — this verb is a thin data extractor, like lint-npc.
// exit 0 found / 1 not found / 2 error.
static int RunCellInfo(string[] argv)
{
    string? pluginPath = null, record = null;
    int dumpRefs = 0;   // --refs N: also sample N temporary placed refs (editorId/base/position) so a
                        // caller can pick a real on-ground anchor inside the cell.
    for (int i = 1; i + 1 < argv.Length; i += 2)
        switch (argv[i])
        {
            case "--plugin": pluginPath = argv[i + 1]; break;
            case "--record": record = argv[i + 1]; break;
            case "--refs": int.TryParse(argv[i + 1], out dumpRefs); break;
            default: return Fail($"unknown arg: {argv[i]}");
        }
    if (string.IsNullOrWhiteSpace(pluginPath) || string.IsNullOrWhiteSpace(record))
        return Fail("usage: mutagen-cli cell-info --plugin <path> --record <FormID|EditorID> [--refs N]");
    if (!File.Exists(pluginPath)) return Fail($"plugin not found: {pluginPath}");
    uint? wantId = NormFormId(record);
    string wantEid = record.Trim();
    try
    {
        var mod = Fallout4Mod.CreateFromBinaryOverlay(new ModPath(pluginPath), Fallout4Release.Fallout4);
        bool Match(ICellGetter c) =>
            (wantId is uint id && (c.FormKey.ID & 0xFFFFFF) == id)
            || (c.EditorID is { } e && string.Equals(e, wantEid, StringComparison.OrdinalIgnoreCase));
        int EmitCell(ICellGetter c, string? wrldParent)
        {
            int combinedRefs = c.CombinedMeshReferences?.Count ?? 0;
            int combinedMeshes = c.CombinedMeshes?.Count ?? 0;
            bool hasPrevis = c.PreVisFilesTimestamp is { } pv && pv != 0;
            bool hasPrecombine = (c.PreCombinedFilesTimestamp is { } pc && pc != 0)
                                 || combinedRefs > 0 || combinedMeshes > 0;
            var gp = c.Grid?.Point;  // exterior cell grid (X,Y); null for interiors
            List<object>? refs = null;
            if (dumpRefs > 0)
            {
                refs = new List<object>();
                foreach (var p in c.Temporary)
                {
                    if (refs.Count >= dumpRefs) break;
                    string? bk = null; float? px = null, py = null, pz = null;
                    if (p is IPlacedObjectGetter po) { bk = po.Base.FormKey.ToString(); px = po.Position.X; py = po.Position.Y; pz = po.Position.Z; }
                    else if (p is IPlacedNpcGetter pn) { bk = pn.Base.FormKey.ToString(); px = pn.Position.X; py = pn.Position.Y; pz = pn.Position.Z; }
                    else continue;
                    refs.Add(new { formKey = p.FormKey.ToString(), editorId = p.EditorID, baseKey = bk, x = px, y = py, z = pz });
                }
            }
            Console.Out.Write(JsonSerializer.Serialize(new
            {
                found = true,
                formKey = c.FormKey.ToString(),
                editorId = c.EditorID,
                interior = c.Flags.HasFlag(Cell.Flag.IsInteriorCell),
                worldspaceParent = wrldParent,
                gridX = gp?.X,
                gridY = gp?.Y,
                sampleRefs = refs,
                // world bounds of this exterior cell (4096 units/cell) so callers can test whether a
                // placed ref's XY actually falls inside the cell it was parented to.
                worldMinX = gp is { } g1 ? g1.X * 4096 : (int?)null,
                worldMinY = gp is { } g2 ? g2.Y * 4096 : (int?)null,
                worldMaxX = gp is { } g3 ? (g3.X + 1) * 4096 : (int?)null,
                worldMaxY = gp is { } g4 ? (g4.Y + 1) * 4096 : (int?)null,
                combinedMeshes,
                combinedMeshReferences = combinedRefs,
                preCombinedFilesTimestamp = c.PreCombinedFilesTimestamp,
                preVisFilesTimestamp = c.PreVisFilesTimestamp,
                hasPrecombines = hasPrecombine,
                hasPrevis,
                persistentCount = c.Persistent.Count,
                temporaryCount = c.Temporary.Count,
            }));
            return 0;
        }
        // interior cells (top-level block hierarchy)
        foreach (var b in mod.Cells)
            foreach (var s in b.SubBlocks)
                foreach (var c in s.Cells)
                    if (Match(c)) return EmitCell(c, null);
        // exterior cells (worldspace-parented) — cell-info was interior-only before; an exterior
        // cell (e.g. RedRocketExt 00DD9F) returned {found:false} despite existing.
        foreach (var w in mod.Worldspaces)
        {
            if (w.TopCell is { } tc && Match(tc)) return EmitCell(tc, w.FormKey.ToString());
            foreach (var blk in w.SubCells)
                foreach (var sub in blk.Items)
                    foreach (var c in sub.Items)
                        if (Match(c)) return EmitCell(c, w.FormKey.ToString());
        }
    }
    catch (Exception e) { return Fail($"load error: {e.Message}"); }
    Console.Out.Write(JsonSerializer.Serialize(new { found = false }));
    return 1;
}

// ---- sm-tree subcommand: Story Manager tree reader (W6) ----
//
//   mutagen-cli sm-tree --plugin <path> [--record <node FormID|EditorID>]
//
// No --record: list SM EVENT nodes (auto-start anchor points) with editorId/formKey/type +
//   childCount (nodes whose Parent == it). With --record: that node (any SM family) + its
//   direct children. Helps an author pick the right Parent for a new SMQN. The POLICY lives in
//   tools.py (fo4_inspect_sm_tree). exit 0 / 1 not found / 2 error.
static int RunSmTree(string[] argv)
{
    string? pluginPath = null, record = null;
    for (int i = 1; i + 1 < argv.Length; i += 2)
        switch (argv[i])
        {
            case "--plugin": pluginPath = argv[i + 1]; break;
            case "--record": record = argv[i + 1]; break;
            default: return Fail($"unknown arg: {argv[i]}");
        }
    if (string.IsNullOrWhiteSpace(pluginPath))
        return Fail("usage: mutagen-cli sm-tree --plugin <path> [--record <node>]");
    if (!File.Exists(pluginPath)) return Fail($"plugin not found: {pluginPath}");
    try
    {
        var mod = Fallout4Mod.CreateFromBinaryOverlay(new ModPath(pluginPath), Fallout4Release.Fallout4);
        var childCount = new Dictionary<FormKey, int>();
        void Bump(FormKey? p) { if (p is { } k) childCount[k] = childCount.GetValueOrDefault(k) + 1; }
        foreach (var n in mod.StoryManagerEventNodes) Bump(n.Parent.FormKeyNullable);
        foreach (var n in mod.StoryManagerBranchNodes) Bump(n.Parent.FormKeyNullable);
        foreach (var n in mod.StoryManagerQuestNodes) Bump(n.Parent.FormKeyNullable);

        if (string.IsNullOrWhiteSpace(record))
        {
            var nodes = new List<Dictionary<string, object?>>();
            foreach (var n in mod.StoryManagerEventNodes)
                nodes.Add(new Dictionary<string, object?>
                {
                    ["editorId"] = n.EditorID,
                    ["formKey"] = n.FormKey.ToString(),
                    ["type"] = n.Type?.ToString(),
                    ["childCount"] = childCount.GetValueOrDefault(n.FormKey),
                });
            Console.Out.Write(JsonSerializer.Serialize(new
            {
                plugin = pluginPath, eventNodeCount = nodes.Count, eventNodes = nodes,
            }));
            return 0;
        }

        uint? wantId = NormFormId(record);
        string wantEid = record.Trim();
        bool Match(string? eid, FormKey fk) =>
            (wantId is uint id && (fk.ID & 0xFFFFFF) == id)
            || (eid is { } e && string.Equals(e, wantEid, StringComparison.OrdinalIgnoreCase));
        FormKey? hitKey = null; string? hitEid = null, hitKind = null;
        foreach (var n in mod.StoryManagerEventNodes) if (Match(n.EditorID, n.FormKey)) { hitKey = n.FormKey; hitEid = n.EditorID; hitKind = "event"; }
        foreach (var n in mod.StoryManagerBranchNodes) if (Match(n.EditorID, n.FormKey)) { hitKey = n.FormKey; hitEid = n.EditorID; hitKind = "branch"; }
        foreach (var n in mod.StoryManagerQuestNodes) if (Match(n.EditorID, n.FormKey)) { hitKey = n.FormKey; hitEid = n.EditorID; hitKind = "quest"; }
        if (hitKey is not { } hk) { Console.Out.Write(JsonSerializer.Serialize(new { found = false })); return 1; }
        var children = new List<Dictionary<string, object?>>();
        foreach (var n in mod.StoryManagerBranchNodes)
            if (n.Parent.FormKeyNullable == hk)
                children.Add(new Dictionary<string, object?> { ["kind"] = "branch", ["editorId"] = n.EditorID, ["formKey"] = n.FormKey.ToString(), ["previousSibling"] = n.PreviousSibling.FormKeyNullable?.ToString() });
        foreach (var n in mod.StoryManagerQuestNodes)
            if (n.Parent.FormKeyNullable == hk)
                children.Add(new Dictionary<string, object?> { ["kind"] = "quest", ["editorId"] = n.EditorID, ["formKey"] = n.FormKey.ToString(), ["previousSibling"] = n.PreviousSibling.FormKeyNullable?.ToString(), ["questCount"] = n.Quests.Count });
        Console.Out.Write(JsonSerializer.Serialize(new
        {
            found = true,
            node = new { kind = hitKind, editorId = hitEid, formKey = hk.ToString() },
            childCount = children.Count,
            children,
        }));
        return 0;
    }
    catch (Exception e) { return Fail($"load error: {e.Message}"); }
}

// ---- create-spec model ----
class CreateSpec
{
    public List<RecordSpec> Records { get; set; } = new();
}

class RecordSpec
{
    public string? Type { get; set; }
    public string? EditorId { get; set; }
    public string? Name { get; set; }
    // NPC (Faz 1.1)
    public string? Race { get; set; }              // FormLink "013746:Fallout4.esm"
    public string? Class { get; set; }             // FormLink
    public List<FactionSpec>? Factions { get; set; } // faction memberships
    // NPC full-field (Faz 3 / W3b) — keywords reuses the Armor Keywords field below
    public string? Voice { get; set; }             // FormLink -> Npc.Voice
    public string? CombatStyle { get; set; }       // FormLink -> Npc.CombatStyle
    public string? DefaultOutfit { get; set; }     // FormLink -> Npc.DefaultOutfit
    public string? AttackRace { get; set; }        // FormLink -> Npc.AttackRace
    public string? Skin { get; set; }              // FormLink -> Npc.Skin (worn-armor override)
    public string? Aggression { get; set; }        // Npc.AggressionType name
    public string? Confidence { get; set; }        // Npc.ConfidenceType name
    public string? Assistance { get; set; }        // Npc.AssistanceType name
    public string? Responsibility { get; set; }    // Npc.ResponsibilityType name
    public string? Mood { get; set; }              // Npc.MoodType name
    public List<ItemSpec>? Inventory { get; set; } // CNTO inventory [{item, count}]
    public List<PerkSpec>? Perks { get; set; }     // PerkPlacement [{perk, rank}]
    // NPC template-chain (Faz 3 / W3c) — FaceGen-inheritance pair
    public string? DefaultTemplate { get; set; }         // FormLink -> Npc.DefaultTemplate (INpcSpawn: NPC_ or LVLN)
    public List<string>? UseTemplateActors { get; set; } // Npc.TemplateActorType flag names (OR'd into the bitfield)
    // OS-14 — NPC actor flags (Npc.Flag: Essential|Protected|Invulnerable|Unique|Respawn|...).
    // Distinct from the Quest/Faction `Flags` field below (overloading it would collide in
    // type-shared specs); the author-facing key is `flags` (mapped to npcFlags in tools.py).
    public List<string>? NpcFlags { get; set; }    // Npc.Flag names (OR'd into npc.Flags)
    // Armor (Faz 1.2)
    public List<string>? Keywords { get; set; }    // FormLink list -> armo.Keywords
    public int? Value { get; set; }                // gold value (Int32, >=0)
    public float? Weight { get; set; }             // item weight (Single, >=0)
    public short[]? ObjectBounds { get; set; }     // OBND: [x1,y1,z1,x2,y2,z2] (Int16) — MISC inventory/inspect bounds
    public string? PreviewTransform { get; set; }  // PTRN: FormKey of a TRNS — frames model in Pip-Boy/Inspect preview
    public int[]? Color { get; set; }              // KYWD CNAM color [r,g,b] or [a,r,g,b] — workshop-menu category button
    public int? ArmorRating { get; set; }          // DNAM armor rating (UInt16, 0-65535)
    public List<string>? BipedSlots { get; set; }  // BipedObjectFlag names (OR'd) -> BipedBodyTemplate
    public List<string>? Armatures { get; set; }   // ARMA addon FormLinks -> armo.Armatures (worn mesh; reuses Race below)
    // OS-01 — WEAP weapon stats (reuses Name/Value/Weight/Keywords/Model/MaterialSwap/ObjectBounds).
    public int? BaseDamage { get; set; }           // DNAM BaseDamage (UInt16, 0-65535)
    public float? Speed { get; set; }              // DNAM Speed (Single, >=0)
    public float? Reach { get; set; }              // DNAM Reach (Single, >=0)
    public float? MinRange { get; set; }           // DNAM MinRange (Single, >=0)
    public float? MaxRange { get; set; }           // DNAM MaxRange (Single, >=0)
    public int? AmmoCapacity { get; set; }         // DNAM Capacity (UInt16, 0-65535)
    public string? Ammo { get; set; }              // FormLink -> Weapon.Ammo (AMMO)
    public string? AttackSound { get; set; }       // FormLink -> Weapon.AttackSound (SNDR)
    public string? EquipSound { get; set; }        // FormLink -> Weapon.EquipSound (SNDR)
    public string? AnimationType { get; set; }     // Weapon.AnimationTypes name (Gun|Bow|OneHandSword|...)
    public List<string>? AttachParentSlots { get; set; } // AKEY keyword FormLinks -> Weapon.AttachParentSlots
    // Book/Note visual (coupon MVP) — world-model nif + the MSWP that retextures it
    public string? Model { get; set; }             // Book MODL: world-model nif path (meshes-relative)
    public string? MaterialSwap { get; set; }      // Book Model.MaterialSwap: MSWP FormKey "<6hex>:<master>"
    public List<SubstitutionSpec>? Substitutions { get; set; } // MSWP: [{original, replacement}] .bgsm paths
    // W1.5 glue records (Faz 3)
    public string? Text { get; set; }              // Message: MESG Description (body); title reuses Name
    public List<string>? Items { get; set; }       // FormList: FLST Items (FormLink list, any record); OS-14 OTFT items
    // OS-11 — widen glue-record coverage (reuses Flags for MESG message-box flags).
    public List<MessageButtonSpec>? MenuButtons { get; set; } // MESG MenuButtons [{text, conditions?}]
    public List<RankSpec>? Ranks { get; set; }     // FACT Ranks [{number, title, titleFemale?, insignia?}]
    public VendorValuesSpec? VendorValues { get; set; } // FACT VendorValues (vendor/merchant data)
    public int? ChanceNone { get; set; }           // LVLN/LVLI ChanceNone, 0-100 integer percent -> Noggog.Percent
    // OS-02 — common world base records (STAT/DOOR/LIGH/CONT/ALCH/INGR) reuse Name/Model/
    // MaterialSwap/Keywords/ObjectBounds/Value/Weight/Flags/Inventory.
    public int? Radius { get; set; }               // LIGH Radius (UInt32)
    public List<EffectSpec>? Effects { get; set; } // ALCH/INGR magic effects [{baseEffect, magnitude, area, duration}]
    // OS-08 — COBJ crafting recipe (reuses Conditions for recipe gates).
    public string? CreatedObject { get; set; }     // recipe output FormLink (MISC/ARMO/WEAP/...) — required
    public string? WorkbenchKeyword { get; set; }  // bench-type KYWD FormLink — required
    public int? CreatedObjectCount { get; set; }   // output count (default 1)
    public string? MenuArtObject { get; set; }     // optional ARTO FormLink (recipe menu art)
    public List<CobjComponentSpec>? Components { get; set; } // ingredient list [{component, count}]
    public List<string>? Categories { get; set; }  // workshop-menu filter KYWD FormLinks (NOT an FLST)
    public string? GlobalType { get; set; }        // Global: float|int|short (selects concrete subclass)
    public double? GlobalValue { get; set; }       // Global: Data scalar (distinct from armor Value int?)
    // W3.5 Faction record (Faz 3) — reuses Flags (below) for faction flags
    public List<RelationSpec>? InterfactionRelations { get; set; } // FACT Relations [{faction, reaction}]
    // W3d/W3e leveled lists (Faz 3) — LVLN/LVLI; reuses Flags for LeveledNpc.Flag/LeveledItem.Flag
    public List<LeveledEntrySpec>? Entries { get; set; } // leveled entries [{reference, level, count}]
    // W4 interior CELL + nested placed refs (Faz 3) — reuses Name for the display cell name
    public string? LightingTemplate { get; set; }  // LTMP FormLink (without it the cell renders black)
    public float? WaterHeight { get; set; }         // XCLW
    public string? Location { get; set; }           // XLCN FormLink
    public string? EncounterZone { get; set; }      // XEZN FormLink
    public string? ImageSpace { get; set; }         // XCIM FormLink
    public string? AcousticSpace { get; set; }      // XCAS FormLink
    public string? Music { get; set; }              // XCMO FormLink
    public List<PlacedRefSpec>? PlacedObjects { get; set; } // REFR children (-> Temporary)
    public List<PlacedRefSpec>? PlacedNpcs { get; set; }    // ACHR children (-> Temporary)
    public NavmeshSpec? Navmesh { get; set; }       // A-disk: isolated-interior NAVM (auto-triangulated floor)
    // W5 cellOverride (Faz 3) — add refs to an existing master cell (reuses PlacedObjects/PlacedNpcs)
    public string? SourcePlugin { get; set; }       // path to the plugin holding the target cell
    public string? Cell { get; set; }               // target cell FormKey "<6hex>:<master>"
    public string? Target { get; set; }             // override target FormKey (leveledItemOverride)
    public bool? ClearExisting { get; set; }         // clear deep-copied refs (default FALSE — additive; opt in to wipe)
    // W6 Story Manager Quest Node (Faz 3) — reuses Flags for AStoryManagerNode.Flag
    public string? Parent { get; set; }             // SNAM: parent SM node FormLink
    public string? PreviousSibling { get; set; }    // sibling-ordering FormLink
    public int? MaxConcurrentQuests { get; set; }   // uint
    public int? MaxNumQuestsToRun { get; set; }     // uint
    public float? HoursUntilReset { get; set; }     // node reset window (hours)
    public List<ConditionSpec>? Conditions { get; set; } // node-level conditions (W1 builder)
    public List<SmqnQuestSpec>? Quests { get; set; }     // quests this node can (auto-)start
    // W8 Location / EncounterZone (Faz 3) — reuses Name/Keywords/Flags/Location
    public string? ParentLocation { get; set; }     // LCTN ParentLocation FormLink
    public string? Owner { get; set; }              // ECZN Owner FormLink (faction/npc)
    public int? MinLevel { get; set; }              // ECZN MinLevel (byte)
    public int? MaxLevel { get; set; }              // ECZN MaxLevel (byte)
    public int? Rank { get; set; }                  // ECZN Rank (byte)
    // W7 AI Package (Faz 3) — reuses CombatStyle/Flags/Conditions; npc 'packages' binding too
    public string? PackageTemplate { get; set; }    // PKDT template FormLink (PACK)
    public string? PackageType { get; set; }        // Package.Types name (Package|PackageTemplate)
    public string? OwnerQuest { get; set; }         // PACK OwnerQuest FormLink
    public List<string>? Packages { get; set; }     // NPC: bind existing PACK FormLinks (npc.Packages)
    public PackageDataLocationSpec? DataLocation { get; set; } // W7-Data: PACK location data-input
    // Quest (Faz 2)
    public string? QuestType { get; set; }         // Quest.TypeEnum name
    public List<string>? Flags { get; set; }       // Quest.Flag names (OR'd)
    public List<StageSpec>? Stages { get; set; }   // quest stages + log entries
    public List<ObjectiveSpec>? Objectives { get; set; } // quest objectives
    public List<TopicSpec>? Topics { get; set; }   // quest-nested dialogue (Faz 2.1)
    public List<BranchSpec>? Branches { get; set; } // DLBR dialogue branches — make topics surface in the wheel (Kerem-polish)
    public List<AliasSpec>? Aliases { get; set; }  // quest aliases / cast slots (Faz 2.1c)
    public List<ScriptSpec>? Scripts { get; set; } // Papyrus VMAD script binding (Faz 2.1d)
    public FragmentSpec? Fragments { get; set; }   // quest stage script fragments (Faz 2.1f)
    public List<AliasFragmentSpec>? AliasFragments { get; set; } // quest alias script fragments (Faz 2.1g)
    public List<SceneSpec>? Scenes { get; set; }   // SCEN scenes (Faz 2.1e)
}

// W7-Data: one PackageDataLocation input for a templated PACK. The slot index is NOT given
// here — it is resolved by name against the live template (Travel "Place to Travel", Sandbox
// "Location"); only the target value + radius are authored.
class PackageDataLocationSpec
{
    public string? Input { get; set; }       // template input Name to match (null = first location input)
    public string? TargetType { get; set; }  // reference | cell | keyword (default reference)
    public string? Target { get; set; }      // FormKey of the placed ref / cell / keyword
    public uint Radius { get; set; }         // travel/sandbox radius in units
}

// Faz 2.1e: a SCEN scene — a major record back-linked to the quest, holding the
// cast (actors by alias ID), the timeline (actions), and flow gates (phases).
class SceneSpec
{
    public string? EditorId { get; set; }          // optional; mints a FormKey from the mod
    public List<string>? Flags { get; set; }       // Scene.Flag names (OR'd)
    public List<SceneActorSpec>? Actors { get; set; }   // cast: quest alias IDs in the scene
    public List<ScenePhaseSpec>? Phases { get; set; }   // flow phases (start/completion conditions)
    public List<SceneActionSpec>? Actions { get; set; } // scene timeline
}

class SceneActorSpec
{
    public int Id { get; set; }                    // SceneActor.ID = the quest alias ID
}

class ScenePhaseSpec
{
    public string? Name { get; set; }              // ScenePhase.Name
    public List<ConditionSpec>? StartConditions { get; set; }      // reuses 2.1b BuildCondition
    public List<ConditionSpec>? CompletionConditions { get; set; }
}

// MVP = a "typical" action (SceneActionTypicalType): a dialogue/package/timer step.
class SceneActionSpec
{
    public string? Type { get; set; }              // SceneAction.TypeEnum name (Dialog, PlayerDialogue, ...)
    public int? Actor { get; set; }                // SceneAction.AliasID — the performing actor's alias ID
    public string? Topic { get; set; }             // topic editorId (this spec) | "<6hex>:<ModKey>"
    public int? StartPhase { get; set; }           // phase index this action starts on
    public int? EndPhase { get; set; }             // phase index this action ends on
    public List<string>? Flags { get; set; }       // SceneAction.Flag names (OR'd)
}

// Faz 2.1d: a Papyrus script attached to the quest (ScriptEntry inside QuestAdapter).
class ScriptSpec
{
    public string? Name { get; set; }              // .psc script/class name (e.g. "MyQuestScript")
    public string? Flags { get; set; }             // ScriptEntry.Flag name; default Local
    public List<ScriptPropertySpec>? Properties { get; set; }
}

// One typed Papyrus property. Type picks the ScriptProperty subclass; Value is the
// literal (a FormKey string for "object"). 'object' may instead fill from an alias.
class ScriptPropertySpec
{
    public string? Name { get; set; }              // property name as declared in the script
    public string? Type { get; set; }              // object | int | float | bool | string
    public JsonElement? Value { get; set; }        // type-dependent literal
    public int? Alias { get; set; }                // object property: fill from this alias index
}

// Faz 2.1f: quest stage script fragments. One QF_ fragment script (Script) + per-stage
// entries (Fragments) that fire a Fragment_* function when the quest reaches that stage.
// The .pex bytecode is built separately (fo4_papyrus_build / Caprica) — metadata only.
class FragmentSpec
{
    public string? ScriptName { get; set; }        // QF_<eid>_<formid> class — QuestAdapter.Script.Name + each fragment's ScriptName
    public string? Flags { get; set; }             // ScriptEntry.Flag for the fragment script; default none
    public List<ScriptPropertySpec>? Properties { get; set; } // fragment script properties (reuses ScriptPropertySpec)
    public List<StageFragmentSpec>? Stages { get; set; }
}

class StageFragmentSpec
{
    public int Stage { get; set; }                 // quest stage index (matches QuestStage.Index), cast to ushort
    public int? StageIndex { get; set; }           // log-entry index within the stage; default 0
    public string? FragmentName { get; set; }      // the Fragment_* function name in the QF script
}

// Faz 2.1g: a quest ALIAS script fragment — binds one quest alias (by ID) to its
// fragment script(s). The CLI sets the binding Property (Alias = the quest-local alias
// ID, Object = this quest) + Version 6 / ObjectFormat 2, and reuses ScriptSpec for the
// scripts. The .pex bytecode is compiled separately (fo4_papyrus_build / Caprica) — this
// writes the metadata only.
class AliasFragmentSpec
{
    public int Alias { get; set; }                 // quest-local alias ID -> Property.Alias (Int16)
    public List<ScriptSpec>? Scripts { get; set; } // the alias's fragment script(s) (ScriptEntry list)
}

// Faz 2.1c: a quest alias — QuestReferenceAlias, keyed by a quest-local ID (no FormKey).
// W6.7 (2026-06-21): + location aliases (QuestLocationAlias) + event-fill
// (FindMatchingRefFromEvent) on ref/location aliases. (Collection aliases attempted but
// BLOCKED — Mutagen v0.53.1 can't round-trip multi-member QuestCollectionAlias; see the
// authoring loop's collection branch.)
class AliasSpec
{
    public int? Id { get; set; }                   // quest-local alias ID; null => auto (list order)
    public string? Name { get; set; }              // alias name (e.g. "QuestGiver")
    public string? Type { get; set; }              // W6.7: "reference" (default) | "location"
    public List<string>? Flags { get; set; }       // AQuestAlias.Flag names (OR'd)
    public string? ForcedReference { get; set; }   // [reference] FormLink to a placed REFR ("<6hex>:<ModKey>")
    public string? UniqueActor { get; set; }       // [reference] FormLink to a unique NPC
    public List<ConditionSpec>? Conditions { get; set; } // find-matching-ref conditions (reuses 2.1b)
    // W6.7 location-alias fills (QuestLocationAlias) — set exactly one
    public string? SpecificLocation { get; set; }  // [location] FormLink to a Location (LCTN)
    public int? ReferenceAliasLocation { get; set; } // [location] location = the location of alias <id>
    public string? ExternalAliasQuest { get; set; } // [location/reference] external quest FormLink (pairs ExternalAliasLinked)
    public int? ExternalAliasId { get; set; }      // [location/reference] alias id in the external quest
    // W6.7 event-fill (FindMatchingRefFromEvent) — valid on reference OR location aliases
    public string? FromEvent { get; set; }         // 4-char event signature (e.g. "ADIE","SHIP","CRGN")
}

class FactionSpec
{
    public string? Faction { get; set; }           // FormLink "<6hex>:<ModKey>"
    public int Rank { get; set; }                  // cast to sbyte (-128..127)
}

// W3.5: an interfaction relation on an authored FACT (combat reaction toward another faction).
class RelationSpec
{
    public string? Faction { get; set; }           // Relation.Target FormLink "<6hex>:<ModKey>"
    public string? Reaction { get; set; }          // CombatReaction name (Neutral|Enemy|Ally|Friend)
}

// OS-11: one MESG menu button — the choice text + optional show-conditions (reuses BuildCondition).
class MessageButtonSpec
{
    public string? Text { get; set; }              // MessageButton.Text (TranslatedString)
    public List<ConditionSpec>? Conditions { get; set; } // optional button-visibility conditions
}

// OS-11: one FACT rank. Title is gendered (Male/Female); a single `title` fills both, with an
// optional `titleFemale` override.
class RankSpec
{
    public int? Number { get; set; }               // Rank.Number (UInt32; 0-based rank index)
    public string? Title { get; set; }             // gendered title — male slot (and female when no override)
    public string? TitleFemale { get; set; }       // optional female-title override
    public string? Insignia { get; set; }          // Rank.Insignia (texture path)
}

// OS-11: FACT vendor/merchant data (the 3 buy/sell bools + trade hours + radius).
class VendorValuesSpec
{
    public int StartHour { get; set; }             // VendorValues.StartHour (UInt16)
    public int EndHour { get; set; }               // VendorValues.EndHour (UInt16)
    public int Radius { get; set; }                // VendorValues.Radius (UInt16)
    public bool BuysStolen { get; set; }           // BuysStolenItems
    public bool BuysNonStolen { get; set; }        // BuysNonStolenItems
    public bool BuyEverything { get; set; }        // BuySellEverythingNotInList
}

// W3b: one NPC inventory entry (CNTO) — an item FormLink + count.
class ItemSpec
{
    public string? Item { get; set; }              // FormLink "<6hex>:<ModKey>"
    public int Count { get; set; } = 1;            // ContainerItem.Count (Int32)
}

// OS-02: one magic Effect on an ALCH/INGR — a base MGEF FormLink + EffectData scalars.
class EffectSpec
{
    public string? BaseEffect { get; set; }        // Effect.BaseEffect FormLink (MGEF) — required
    public float Magnitude { get; set; }           // EffectData.Magnitude (Single)
    public int Area { get; set; }                  // EffectData.Area (Int32)
    public int Duration { get; set; }              // EffectData.Duration (Int32)
}

// OS-08: one COBJ ingredient component — a MISC/item FormLink + count.
class CobjComponentSpec
{
    public string? Component { get; set; }         // ConstructibleObjectComponent.Component FormLink (IItem)
    public int Count { get; set; } = 1;            // ConstructibleObjectComponent.Count (UInt32)
}

// W3b: one NPC perk placement (PerkPlacement) — a perk FormLink + rank.
class PerkSpec
{
    public string? Perk { get; set; }              // FormLink "<6hex>:<ModKey>"
    public int Rank { get; set; }                  // cast to byte (0-255)
}

// W3d/W3e: one leveled-list entry — a reference FormLink + spawn level + count.
// Shared by LVLN (reference = INpcSpawn) and LVLI (reference = IItem); the writer
// wraps each in a Leveled{Npc,Item}EntryData (Level/Count cast to Int16).
class LeveledEntrySpec
{
    public string? Reference { get; set; }         // FormLink "<6hex>:<ModKey>"
    public int Level { get; set; } = 1;            // LeveledEntryData.Level (Int16); 1-based
    public int Count { get; set; } = 1;            // LeveledEntryData.Count (Int16)
}

// MSWP one substitution: swap an original .bgsm for a replacement .bgsm (Data-relative).
class SubstitutionSpec
{
    public string? Original { get; set; }          // MaterialSubstitution.OriginalMaterial (nif's .bgsm)
    public string? Replacement { get; set; }       // MaterialSubstitution.ReplacementMaterial (our coupon .bgsm)
}

// W4: one placed reference (REFR or ACHR) nested in a cell — a base object + transform.
class PlacedRefSpec
{
    public string? EditorId { get; set; }          // optional ref EditorID
    public string? Base { get; set; }              // FormLink "<6hex>:<ModKey>" (NAME) — required
    public List<float>? Position { get; set; }     // [x,y,z]; default origin
    public List<float>? Rotation { get; set; }     // [x,y,z] radians; default 0
    public float? Scale { get; set; }              // XSCL; omit when 1.0
    public bool Persistent { get; set; }           // true -> Cell.Persistent, else Temporary
    public TeleportSpec? Teleport { get; set; }    // W8.5: XTEL door-link (placedObject/door only)
}

// W8.5: a door teleport (XTEL) — destination door + spawn position/rotation.
class TeleportSpec
{
    public string? Door { get; set; }              // destination door REFR FormLink "<6hex>:<ModKey>"
    public List<float>? Position { get; set; }     // spawn [x,y,z] at the destination
    public List<float>? Rotation { get; set; }     // spawn rotation [x,y,z]
}

// A-disk: an isolated-interior navmesh — a rectangular floor that auto-triangulates into a grid
// with edge-link adjacency. Disk-proven; in-game pathing is the §4 freeze gate.
class NavmeshSpec
{
    public List<float>? Floor { get; set; }        // [minX, minY, maxX, maxY] floor extent — required
    public float? Z { get; set; }                  // floor height (default 0)
    public int? DivisionsX { get; set; }           // grid columns (default 1 -> 2 tris)
    public int? DivisionsY { get; set; }           // grid rows (default 1)
    public bool? Navi { get; set; }                 // A-in-game RE toggle: also author a NAVI map-info entry (default true)
}

// W6: one Story Manager quest entry — a quest the node can (auto-)start + its reset window.
class SmqnQuestSpec
{
    public string? Quest { get; set; }             // IQuest FormLink "<6hex>:<ModKey>"
    public float? HoursUntilReset { get; set; }    // per-quest reset window (FNAM flags deferred)
}

class StageSpec
{
    public int Index { get; set; }                 // cast to ushort
    public string? LogEntry { get; set; }          // QuestLogEntry.Entry text (always gets a QSDT marker)
    public bool RunOnStart { get; set; }           // QuestStage.Flag.RunOnStart (INDX 0x02) — startup stage
}

class ObjectiveSpec
{
    public int Index { get; set; }                 // cast to ushort
    public string? Text { get; set; }              // QuestObjective.DisplayText
    // W2: objective flags + QSTA targets
    public List<string>? Flags { get; set; }       // QuestObjective.Flag (OrWithPrevious|NoStatsTracking)
    public List<ObjectiveTargetSpec>? Targets { get; set; } // QSTA targets
}

// W2: one QSTA objective target — a compass marker pointing at a quest alias (by ID),
// with target flags, an optional LCRT location keyword, and optional find-ref conditions.
class ObjectiveTargetSpec
{
    public int AliasId { get; set; }               // QuestObjectiveTarget.AliasID (quest-local alias)
    public List<string>? Flags { get; set; }       // Quest.TargetFlag (CompassMarkerIgnoresLocks|Hostile|UseStraightLinePathing)
    public string? Keyword { get; set; }           // FormLink -> LCRT location keyword (optional)
    public List<ConditionSpec>? Conditions { get; set; } // reuses 2.1b BuildCondition
}

// Faz 2.1 dialogue: DialogTopic (DIAL) -> DialogResponses (INFO) -> DialogResponse (line).
class TopicSpec
{
    public string? EditorId { get; set; }          // optional; mints a FormKey from the mod
    public string? Name { get; set; }              // DialogTopic.Name (TranslatedString)
    public string? Subtype { get; set; }           // DialogTopic.SubtypeEnum name
    public string? Category { get; set; }          // DialogTopic.CategoryEnum name
    public string? Branch { get; set; }            // owning DialogBranch editorId (or FormKey) -> topic.Branch (Kerem-polish)
    public List<ResponseSpec>? Responses { get; set; } // nested INFO records
}

// Kerem-polish: a DLBR dialogue branch. A bare DIAL+INFO never surfaces in the dialogue
// wheel; a Player/TopLevel branch pointing at an entry topic is what makes it appear when
// the player activates the NPC. Vanilla recipe (DLCworkshop01 ...SummonedToRelaxBranch):
// {Quest, Category: Player, Flags: [TopLevel], StartingTopic: <DialogTopic>}.
class BranchSpec
{
    public string? EditorId { get; set; }          // optional; mints a FormKey from the mod
    public string? StartingTopic { get; set; }     // entry topic editorId (resolved in-spec) or FormKey
    public string? Category { get; set; }          // DialogBranch.CategoryEnum name; default Player
    public List<string>? Flags { get; set; }       // DialogBranch.Flag names (OR'd); default [TopLevel]
}

class ResponseSpec
{
    public string? Prompt { get; set; }            // DialogResponses.Prompt (TranslatedString)
    public string? Speaker { get; set; }           // FormLink "<6hex>:<ModKey>" (IFormLinkNullable<INpc>)
    public List<LineSpec>? Lines { get; set; }     // spoken lines
    public List<ConditionSpec>? Conditions { get; set; } // INFO conditions (Faz 2.1b)
    public SetStageSpec? SetParentQuestStage { get; set; } // P0: script-free INFO -> owning-quest stage advance (SNAM)
    public string? FormKey { get; set; }           // OS-04: pin the INFO FormKey ("<6hex>:<ModKey>") so the TIF script name stays stable across re-authoring; null => mint
    public InfoFragmentSpec? Fragment { get; set; } // OS-04: TIF VMAD fragment — run Papyrus on this line (docs/fo4-quest-dialogue-system.md mechanism B)
}

// OS-04 (docs/fo4-quest-dialogue-system.md mechanism B): a per-INFO Papyrus fragment (TIF VMAD).
// The line's TIF_<questEID>_<8hexINFOFormID> script's Fragment_Begin/Fragment_End run when the
// line begins/ends, letting it do arbitrary Papyrus (AddItem + Notification + conditional reward)
// beyond the script-free SNAM stage-advance. Mirrors the quest FragmentSpec shape; the compiled
// .pex is decoupled (fo4_papyrus_build / Caprica) — the writer emits VMAD metadata only.
class InfoFragmentSpec
{
    public string? ScriptName { get; set; }        // TIF_<eid>_<8hex> class — DialogResponsesAdapter ScriptFragments + each fragment's ScriptName
    public string? Flags { get; set; }             // ScriptEntry.Flag for the fragment script; default none
    public List<ScriptPropertySpec>? Properties { get; set; } // fragment script properties (reuses ScriptPropertySpec)
    public string? OnBegin { get; set; }           // Fragment_* function fired when the line BEGINS; null => no OnBegin fragment
    public string? OnEnd { get; set; }             // Fragment_* function fired when the line ENDS (turn-in reward); null => no OnEnd fragment
}

// P0 (docs/fo4-quest-dialogue-system.md): DialogResponses.SetParentQuestStage (SNAM). OnEnd=N
// sets the OWNING quest to stage N when the line ENDS; OnBegin=N when it begins. null => -1
// (unused). 4112 vanilla INFOs use this — it lets a dialogue-wheel pick advance the quest with
// NO Papyrus fragment (the lowest-friction "pick line -> SetStage" primitive). A TIF VMAD
// fragment (P2) is only needed when the line must also run arbitrary Papyrus (e.g. AddItem).
class SetStageSpec
{
    public int? OnBegin { get; set; }
    public int? OnEnd { get; set; }
}

// Faz 2.1b: a single condition -> ConditionFloat + generic FunctionConditionData.
class ConditionSpec
{
    public string? Function { get; set; }          // Condition.Function name (e.g. GetStage)
    public string? Comparison { get; set; }        // CompareOperator name; default EqualTo
    public float Value { get; set; } = 1f;         // ConditionFloat.ComparisonValue
    public string? Param1 { get; set; }            // FormKey "<hex>:<modkey>" | int | string
    public string? Param2 { get; set; }
    public string? RunOn { get; set; }             // Condition.RunOnType name; default Subject
    public int? AliasRunOn { get; set; }           // RunOn=QuestAlias -> Unknown3 (alias id; 0 valid, explicit)
    public string? Reference { get; set; }         // RunOn=Reference -> Reference FormLink "<hex>:<ModKey>"
}

class LineSpec
{
    public string? Text { get; set; }              // DialogResponse.Text (TranslatedString)
    public int ResponseNumber { get; set; }        // Byte; 0 => auto-sequence (1-based)
    public string? Emotion { get; set; }           // FormLink "<6hex>:<ModKey>" (IFormLink<IKeyword>)
}
