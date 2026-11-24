// nifsharp-cli — GPL-isolated FO4 geometry writer (NiflySharp 1.3.0 = SWIG binding over nifly).
// Rewritten 2026-11-24 after the original source was lost; contract: docs/faz-c-geometry-writer-design.md.
//
//   nifsharp-cli build-trishape --in <template.nif> --mesh <mesh.json> --out <out.nif>
//                               [--shape <index|name>] [--flip-bitangent]
//
// Template-edit: replace ONE plain BSTriShape's geometry from a JSON mesh, recompute
// normals (if absent) + tangent space + bounds, save. Every other block (collision, shader,
// node tree) is left as loaded. stdout = one JSON line; stderr = error; exit 0 ok / 2 error.
using System.Text.Json;
using nifly;

static int Fail(string msg)
{
    Console.Error.WriteLine(msg);
    return 2;
}

if (args.Length == 0 || args[0] != "build-trishape")
    return Fail("usage: nifsharp-cli build-trishape --in <template.nif> --mesh <mesh.json> --out <out.nif> "
                + "[--shape <index|name>] [--flip-bitangent]");

string? inPath = null, meshPath = null, outPath = null, shapeArg = null;
bool flipBitangent = false;
for (int i = 1; i < args.Length; i++)
{
    string Next() => i + 1 < args.Length ? args[++i] : throw new ArgumentException($"{args[i]} needs a value");
    try
    {
        switch (args[i])
        {
            case "--in": inPath = Next(); break;
            case "--mesh": meshPath = Next(); break;
            case "--out": outPath = Next(); break;
            case "--shape": shapeArg = Next(); break;
            case "--flip-bitangent": flipBitangent = true; break;
            default: return Fail($"unknown argument: {args[i]}");
        }
    }
    catch (ArgumentException e) { return Fail(e.Message); }
}
if (inPath is null || meshPath is null || outPath is null)
    return Fail("--in, --mesh and --out are required");
if (!File.Exists(inPath)) return Fail($"template not found: {inPath}");
if (!File.Exists(meshPath)) return Fail($"mesh json not found: {meshPath}");

// ---- mesh JSON ----
List<float[]> verts, uvs, tris;
List<float[]>? normals = null, tangents = null;
using (var doc = JsonDocument.Parse(File.ReadAllText(meshPath)))
{
    var root = doc.RootElement;
    static List<float[]>? Rows(JsonElement root, string key, int width)
    {
        if (!root.TryGetProperty(key, out var arr) || arr.ValueKind == JsonValueKind.Null) return null;
        var rows = new List<float[]>();
        foreach (var row in arr.EnumerateArray())
        {
            var vals = row.EnumerateArray().Select(v => v.GetSingle()).ToArray();
            if (vals.Length != width) throw new FormatException($"{key}: each row needs {width} numbers, got {vals.Length}");
            rows.Add(vals);
        }
        return rows;
    }
    try
    {
        verts = Rows(root, "vertices", 3) ?? throw new FormatException("mesh.vertices is required");
        uvs = Rows(root, "uvs", 2) ?? throw new FormatException("mesh.uvs is required");
        tris = Rows(root, "triangles", 3) ?? throw new FormatException("mesh.triangles is required");
        normals = Rows(root, "normals", 3);
        tangents = Rows(root, "tangents", 3);
    }
    catch (Exception e) when (e is FormatException or InvalidOperationException)
    {
        return Fail($"bad mesh json: {e.Message}");
    }
    if (shapeArg is null && root.TryGetProperty("shape", out var sh) && sh.ValueKind != JsonValueKind.Null)
        shapeArg = sh.ValueKind == JsonValueKind.Number ? sh.GetInt32().ToString() : sh.GetString();
}
int nV = verts.Count;
if (nV == 0 || tris.Count == 0) return Fail("mesh needs at least one vertex and one triangle");
if (nV > ushort.MaxValue) return Fail($"too many vertices for a BSTriShape: {nV} (max {ushort.MaxValue})");
if (uvs.Count != nV) return Fail($"uvs count {uvs.Count} != vertices {nV}");
if (normals is not null && normals.Count != nV) return Fail($"normals count {normals.Count} != vertices {nV}");
if (tangents is not null && tangents.Count != nV) return Fail($"tangents count {tangents.Count} != vertices {nV}");
foreach (var t in tris)
    foreach (var idx in t)
        if (idx < 0 || idx >= nV || idx != Math.Floor(idx)) return Fail($"triangle index out of range: {idx}");

// ---- load + resolve the target shape ----
var nif = new NifFile();
if (nif.Load(inPath) != 0) return Fail($"failed to load nif: {inPath}");
var shapes = nif.GetShapes();
var names = nif.GetShapeNames();
int pick = -1;
if (shapeArg is null)
{
    if (shapes.Count != 1)
        return Fail($"template has {shapes.Count} shapes; pass --shape <index|name> ({string.Join(", ", names)})");
    pick = 0;
}
else if (int.TryParse(shapeArg, out var si))
{
    if (si < 0 || si >= shapes.Count) return Fail($"shape index {si} out of range (0..{shapes.Count - 1})");
    pick = si;
}
else
{
    for (int i = 0; i < names.Count; i++) if (names[i] == shapeArg) { pick = i; break; }
    if (pick < 0) return Fail($"no shape named '{shapeArg}' ({string.Join(", ", names)})");
}
var shape = shapes[pick];
// SWIG returns base NiShape proxies, so `is BSTriShape` is unreliable — ask the C++ block type.
var blockName = shape.GetBlockName();
if (blockName != "BSTriShape")
    return Fail($"target shape '{names[pick]}' is {blockName}; only plain BSTriShape is supported "
                + "(skinned/sub-indexed/dynamic shapes need segment handling)");

// ---- write geometry. Order matters: verts resize the shape and clear its triangles. ----
static Vector3 V3(float[] a) => new(a[0], a[1], a[2]);
nif.SetVertsForShape(shape, new vectorVector3(verts.Select(V3)));
shape.SetTriangles(new vectorTriangle(tris.Select(t => new Triangle((ushort)t[0], (ushort)t[1], (ushort)t[2]))));
shape.SetUVs(true);
nif.SetUvsForShape(shape, new vectorVector2(uvs.Select(u => new Vector2(u[0], u[1]))));
shape.SetNormals(true);
if (normals is not null) nif.SetNormalsForShape(shape, new vectorVector3(normals.Select(V3)));
else nif.CalcNormalsForShape(shape, true);

shape.SetTangents(true);
bool tangentsCalculated;
if (tangents is not null)
{
    nif.SetTangentsForShape(shape, new vectorVector3(tangents.Select(V3)));
    // bitangent = normal x tangent, so a caller-supplied tangent frame stays orthogonal
    var ns = nif.GetNormalsForShape(shape);
    var bit = new List<Vector3>(nV);
    for (int i = 0; i < nV; i++)
    {
        var b = ns[i].cross(V3(tangents[i]));
        b.Normalize();
        bit.Add(b);
    }
    nif.SetBitangentsForShape(shape, new vectorVector3(bit));
    tangentsCalculated = false;
}
else
{
    nif.CalcTangentsForShape(shape);
    tangentsCalculated = true;
}
if (flipBitangent)
{
    var bs = nif.GetBitangentsForShape(shape);
    nif.SetBitangentsForShape(shape, new vectorVector3(Enumerable.Range(0, bs.Count)
        .Select(i => new Vector3(-bs[i].x, -bs[i].y, -bs[i].z))));
}
shape.UpdateBounds();

// ---- save + report ----
var outDir = Path.GetDirectoryName(Path.GetFullPath(outPath));
if (!string.IsNullOrEmpty(outDir)) Directory.CreateDirectory(outDir);
if (nif.Save(outPath) != 0) return Fail($"failed to save nif: {outPath}");

var flags = new List<string> { "VERTEX" };
if (shape.HasUVs()) flags.Add("UV");
if (shape.HasNormals()) flags.Add("NORMAL");
if (shape.HasTangents()) flags.Add("TANGENT");
var bounds = shape.GetBounds();
Console.Out.Write(JsonSerializer.Serialize(new Dictionary<string, object?>
{
    ["out"] = outPath,
    ["shape"] = names[pick],
    ["shapeIndex"] = pick,
    ["numVerts"] = (int)shape.GetNumVertices(),
    ["numTris"] = (int)shape.GetNumTriangles(),
    ["vertexFlags"] = flags,
    ["boundsCenter"] = new[] { bounds.center.x, bounds.center.y, bounds.center.z },
    ["boundsRadius"] = bounds.radius,
    ["tangentsCalculated"] = tangentsCalculated,
    ["flipBitangent"] = flipBitangent,
}));
return 0;
