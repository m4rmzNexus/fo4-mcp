# Faz C — Geometri Writer (NiflySharp subprocess-shim) — Design Artifact

**Tarih:** 2026-06-24
**Roadmap:** `docs/blender-asset-pipeline-completion-roadmap.md` Faz C (blokör #2 keyfi geometri + #4 `fo4_nif_build` aracı yok)
**Durum:** DESIGN + Python shim landed (autonomous). dotnet build = **GATED** (C1 GPL kararı + ağır `dotnet publish`).

Bu belge, FO4 `.nif` için keyfi mesh + tangent yazan, **MIT-temiz Python orkestrasyonu + GPL-izole bir
exe** mimarisini tarif eder. Python tarafı (`mcp-server/fo4_mcp/geometry_ops.py`) **diskte hazır ve
gated-error ile sınanmış**; exe henüz inşa edilmedi (kullanıcı tetikler).

---

## 1. Neden bir writer (nif_ops byte-poking yerine)

`nif_ops._tri_header()` (`nif_ops.py:73-84`) BSTriShape vertex datasını `base = 100 + nE*4` offset
**tahmini** ile bulur. Bu bir **READ-side sezgiseli** — doğrulama/inspect için yeterli ama **yazma için
güvenli değil**. FO4'ün packed vertex'i şunları içerir:

- `BSVertexDesc` bitfield (UV/NORMAL/TANGENT/COLOR bayrakları, `vertex_flags` `>>44`'te okur),
- half-float pozisyonlar (`<e`),
- SNORM-paketli normal + tangent (UDEC3 / byte4),
- per-vertex tangent space (FO4 lit shader'ın ZORUNLU kıldığı tangent+bitangent).

Bunu sıfırdan byte-author etmek `_tri_header`'ın kıramayacağı bir iş. **NiflySharp'ın BSTriShape'i bunu
NiVersion 20.2.0.7 / BSVERSION 130+ için zaten doğru encode ediyor.** Yani **yazma yolu exe'nin**,
okuma/gate yolu `nif_ops`'un.

**Kapsam (MVP):** TEMPLATE-EDIT — bir template `.nif` yükle, **TEK** plain static BSTriShape'in
geometrisini JSON mesh'ten değiştir, tangent+bounds yeniden hesapla, kaydet. **Diğer her blok**
(collision `bhkPhysicsSystem`, `BSLightingShaderProperty`, NiNode ağacı) **byte-korunur** → PyNifly'ın
yaptığı gibi Havok regenere ETMEZ (memory: `blender-fo4-collision-splice`). Sıfırdan nif synthesis =
V2 (önce TASKS.md kalemi aç).

---

## 2. GPL-izolasyon gerekçesi (mutagen-cli deseni)

NiflySharp (ousnius) ve altındaki nifly = **GPL-3.0**. Karar 7 (`docs/karar-7-license-strategy.md`):
GPL araçları subprocess-only + dağıtılmaz → MIT temiz kalır. Bu **yeni bir mekanizma değil** — birebir
`tools/mutagen-cli/` (Mutagen.Bethesda GPL-3.0) ve `tools/spriggit/` deseni:

1. **Ayrı süreç:** NiflySharp standalone net9 console exe'ye sarılır. MIT Python'umuz **asla `import`
   etmez / link etmez** — sadece `run_tool()` ile shell-out eder (`subprocess_wrap.py`, GPL firewall'un
   tek geçiş noktası). `tools.py:_cell_info`'nun mutagen-cli'yi çağırması ile birebir aynı.
2. **Gitignored:** exe + `NiflySharp.dll` → `tools/nifsharp-cli/` altında gitignored (mutagen-cli /
   spriggit gibi). Source-of-truth kaynak `tools/nifsharp-cli/src/` altında tutulur.
3. **Dağıtılmaz:** MIT ürünle birlikte gönderilmez (Karar 7).

MIT-temiz yarılar in-process kalır: BGSM (MaterialLib-MIT, `bgsm_ops.py`), DDS (texconv-MIT), convex
hull (scipy-BSD / CoACD-MIT — Faz D). **Yalnız NiflySharp geometri write GPL sınırını geçer.**

**C1 karar (gated bekleme-noktası):** subprocess-izolasyon (**önerilen**, desene uygun). Alternatif
("byte-poking'de kal") write yolu için **reddedildi** (yukarıda §1). Kullanıcı NuGet ref eklemeden önce
onaylar.

---

## 3. C# console projesi (tools/nifsharp-cli/)

`tools/mutagen-cli/src/` yapısını birebir kopyalar.

### 3.1 Dosya düzeni

```text
tools/nifsharp-cli/
  src/
    NifSharp.Build.csproj      # PackageReference NiflySharp (versiyon PIN'li)
    Program.cs                 # argv dispatch + Fail() + JsonSerializer -> stdout
  nifsharp-cli.exe             # build çıktısı (GITIGNORED)
  NiflySharp.dll               # (GITIGNORED)
  ... (bağımlı dll'ler, GITIGNORED)
```

### 3.2 csproj (mutagen-cli'nin `Mutagen.RecordQuery.csproj`'unu yansıtır)

```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>net9.0</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
    <AssemblyName>nifsharp-cli</AssemblyName>
  </PropertyGroup>
  <ItemGroup>
    <!-- versiyonu BUILD ANINDA pinle; symbol'leri compile-doğrula (CLAUDE.md: reality-checked) -->
    <PackageReference Include="NiflySharp" Version="<PIN_AT_BUILD>" />
  </ItemGroup>
</Project>
```

> **RISK / reality-check:** Aşağıdaki NiflySharp metod adları (`SetVertsForShape`, `CalcTangentSpace`,
> `UpdateBounds`, `SetTangentsForShape`, `VertexDesc`) nifly/NiflySharp soyağacındandır ve **pinlenen
> NuGet sürümünde derlenerek doğrulanmalı** (CLAUDE.md: elle test edilmiş komut olmadan tool signature
> dondurma). Verb sözleşmesini dondurmadan önce `dotnet build` ile sembolleri teyit et.

### 3.3 Program.cs — verb şekli

mutagen-cli'nin `create` / `navmesh-dump` argv dispatch'ini yansıtır. **Tek verb (MVP):**

```text
nifsharp-cli build-trishape --in <template.nif> --mesh <mesh.json> --out <out.nif> [--shape <index|name>] [--flip-bitangent]
```

- `args[0] == "build-trishape"` → `RunBuildTriShape(args)` (mutagen-cli'deki `if (args[0]=="create")`
  deseni).
- `Fail(string msg)` helper: `Console.Error.WriteLine(msg); return 2;` (mutagen-cli `Program.cs:739`).
- stdout = **tek satır JSON** (`JsonSerializer.Serialize`). stderr = hatalar. exit: `0` ok / `2` bad
  args / load / shape-not-found / count-mismatch.

### 3.4 NiflySharp çağrı dizisi (load → edit → tangent → bounds → save)

```csharp
// 1) Template'i yükle — DİĞER her bloğu (collision, shader, node tree) korur
var nif = new NifFile();
nif.Load(inPath);                                  // NifFile.Load(path)

// 2) Hedef BSTriShape'i çöz (index ya da isim). Plain static BSTriShape ŞART.
//    Skinned/sub-indexed (BSSubIndexTriShape / BSDynamicTriShape) ise Fail() (segment handling = V2).
var shape = ResolveShape(nif, shapeSelector);      // GetShapes() içinde ara; tip kontrolü
if (shape is BSSubIndexTriShape || shape is BSDynamicTriShape)
    return Fail("target is skinned/sub-indexed; MVP supports plain BSTriShape only");

// 3) Geometriyi JSON'dan it (high-level NiflySharp API)
nif.SetVertsForShape(shape, verts);                // List<Vector3>
nif.SetUvsForShape(shape, uvs);                    // List<Vector2>
if (normals != null) nif.SetNormalsForShape(shape, normals);
shape.SetTriangles(tris);                          // List<Triangle>

// 4) Tangent space — verilmediyse türet (NifSkope "Update Tangent Space" muadili)
bool tangentsCalculated = false;
if (tangents != null) { nif.SetTangentsForShape(shape, tangents); }
else { nif.CalcTangentSpace(shape); tangentsCalculated = true; }   // a.k.a. RecalcTangentSpace
if (flipBitangent) FlipBitangentSign(shape);       // mirror-UV escape hatch (opsiyonel)

// 5) Vertex flag bitfield'i deklare et — UV(0x2)|NORMAL(0x8)|TANGENT(0x10), yoksa lit shader yok sayar
//    (NiflySharp normals+tangents push edilince shape.VertexDesc / SetVertexAttributes ile set eder)
EnsureVertexFlags(shape);                          // VERTEX|UV|NORMAL|TANGENT

// 6) Bounding sphere — yoksa culling item'ı boş gösterir
nif.UpdateBounds();                                // ya da shape.UpdateBounds()

// 7) Tüm container'ı yaz — dokunulmamış her blok (collision/shader/node) byte-korunur
nif.Save(outPath);

// 8) stdout JSON raporu
Console.Out.Write(JsonSerializer.Serialize(new {
    @out = outPath, shape = resolvedShapeName, numVerts, numTris,
    vertexFlags = new[]{"VERTEX","UV","NORMAL","TANGENT"},
    boundsCenter = new[]{c.X, c.Y, c.Z}, boundsRadius = r,
    tangentsCalculated
}));
return 0;
```

> **Half-float / SNORM precision (RISK):** NiflySharp pozisyonları half-float'a, normal/tangent'i
> SNORM'a quantize eder → çıktı float64 kaynakla **bit-identik OLMAZ**. Authoring için doğru (motor tam
> bu formatı okur), ama validator **byte-eşitlik iddia ETMEMELİ** — sadece yapısal doğruluk (flag'ler
> var, bounds dejenere değil, tangent space geçerli).

---

## 4. Mesh JSON sözleşmesi

Python yazar, exe okur + sayıları doğrular (uyuşmazlıkta `Fail()` exit 2).

```jsonc
{
  "shape": "<name|index, optional>",          // hangi BSTriShape (yoksa tek shape varsay / --shape arg)
  "vertices": [[x,y,z], ...],                 // ZORUNLU
  "uvs":      [[u,v],   ...],                  // ZORUNLU, count == vertices
  "normals":  [[x,y,z], ...],                 // opsiyonel, count == vertices
  "tangents": [[x,y,z], ...],                 // opsiyonel, count == vertices
  "triangles":[[a,b,c], ...]                  // ZORUNLU (vertex indeksleri)
}
```

Çıktı JSON: `{"out", "shape", "numVerts", "numTris", "vertexFlags":[...], "boundsCenter":[x,y,z],
"boundsRadius", "tangentsCalculated"}`.

---

## 5. Python tarafı (mcp-server/fo4_mcp/geometry_ops.py) — LANDED

`bgsm_ops.py` konvansiyonlarına uyar; **NiflySharp import etmez** (saf orkestrasyon).

| Parça | Davranış | Ayna |
|---|---|---|
| `_resolve(cfg, p)` | repo-relative → absolute | `bgsm_ops._resolve` |
| `_nifsharp_cli_binary(cfg, manifest)` | exe'yi çöz ya da **None** (asla raise) | `tools._mutagen_cli_binary` |
| `validate_mesh(mesh)` | client-side mesh gate (eksik/bilinmeyen key, count mismatch) | `bgsm_ops.apply_fields` ruhuyla |
| `fo4_nif_build(cfg, manifest, template_nif, mesh, output_nif, shape, flip_bitangent)` | MCP wrapper | `bgsm_ops.fo4_create_bgsm` |

`fo4_nif_build` akışı:
1. `out = _resolve(...)` → `check_write(out, cfg.repo_root)` (`safety.py` — Steam Data DENY raise).
2. Template var mı? (yoksa `INVALID_ARGUMENT`).
3. `validate_mesh(mesh)` (client-side).
4. `cli = _nifsharp_cli_binary(...)` → **None ise** `Fo4McpError(TOOL_BINARY_MISSING, "geometry shim
   not built (gated): ...", {"gated": True})` raise. **Hiçbir çıktı yazılmaz** (false-artifact yok).
5. mesh JSON'u `out.suffix + ".mesh.json"` geçici dosyasına yaz → `run_tool(cli, ["build-trishape",
   ...], timeout=cfg.subprocess_timeout)` → `finally` temp'i sil.
6. stdout boş / non-JSON → `SUBPROCESS_FAILED` / `SUBPROCESS_OUTPUT_UNPARSEABLE` (+ `stderr_tail`).
7. **Layer-0 gate:** `nif_ops.validate(out)` (kendi read-side decode'umuz — read yolunda NiflySharp
   yok). Geometri **yapısal** sınanır (flags/bounds/thickness), JSON girdiyle byte-karşılaştırılmaz.
8. `ok({...})` döner.

**Gated davranış (kanıtlı):** exe inşa edilene kadar `fo4_nif_build` **net bir hata** atar, asla sahte
başarı dönmez. Test: `test_build_raises_clear_gated_error_when_shim_missing`.

### 5.1 MCP tool tablosuna register (henüz YAPILMADI — build sonrası)

`fo4_postprocess_nif` / `fo4_create_bgsm` yanına (`server.py:499-544` deseni):

```python
# Tool N5 — FO4 geometry writer (template-edit BSTriShape, GPL-isolated nifsharp-cli)
@mcp.tool()
def fo4_nif_build(
    template_nif: str, mesh: dict[str, Any], output_nif: str,
    shape: str | int | None = None, flip_bitangent: bool = False,
) -> dict[str, Any]:
    """Author FO4 geometry by replacing ONE BSTriShape in a template .nif from a JSON mesh, via the
    GPL-isolated nifsharp-cli subprocess. Other blocks (collision/shader/node tree) byte-preserved
    (no PyNifly Havok regen). Tangents+bounds recomputed; output gated to staging/fixtures; result
    run through nif_ops.validate(). GATED: raises until nifsharp-cli is built."""
    return _safe(lambda: geometry_ops.fo4_nif_build(
        cfg, manifest, template_nif, mesh, output_nif, shape, flip_bitangent))
```

> Bu register'ı **build sonrası** ekle — `_safe` Fo4McpError'u zaten envelope'a çevirir, yani register'lı
> da olsa gated-error temiz serileşir. Şimdiden eklemek de güvenli (tool çağrılınca net gated-error döner).

---

## 6. Build + wire runbook (kullanıcı-tetikli, GATED)

> **C1 GPL kararı + `dotnet publish` ağır** → kullanıcı onayı + tetiği. Aşağıdaki adımları Claude
> OTONOM çalıştırmaz; kullanıcı "build et" dediğinde uygulanır.

1. **C1 onayı:** NiflySharp (GPL-3.0) NuGet ref'ini tools/ firewall'una ekleme kararını onayla
   (subprocess-izolasyon, mutagen-cli precedent'i).
2. **Proje iskelesi:**
   ```text
   tools/nifsharp-cli/src/NifSharp.Build.csproj   (§3.2)
   tools/nifsharp-cli/src/Program.cs              (§3.3-3.4)
   ```
3. **Sembol reality-check:** `dotnet build tools/nifsharp-cli/src/NifSharp.Build.csproj` → NiflySharp
   metod adlarının (`SetVertsForShape` / `CalcTangentSpace` / `UpdateBounds` / `SetTangentsForShape` /
   `VertexDesc`) pinlenen sürümde derlendiğini DOĞRULA. Uyuşmazsa verb'i dondurma; adları düzelt.
4. **Publish:**
   ```bash
   dotnet publish tools/nifsharp-cli/src/NifSharp.Build.csproj \
     -c Release -r win-x64 --self-contained false -o tools/nifsharp-cli
   ```
   → `tools/nifsharp-cli/nifsharp-cli.exe` (+ `NiflySharp.dll`).
5. **MANIFEST girdisi** (`tools/MANIFEST.md`, `## mutagen-cli` bloğunu kopyala):
   ```yaml
   name: nifsharp-cli
   version: <PINNED_NIFLYSHARP_VERSION>
   source: custom (tools/nifsharp-cli/src/ — NiflySharp GPL-3.0 wrap)
   asset: built from source via dotnet publish (net9.0, framework-dependent, win-x64)
   binary_path: tools/nifsharp-cli/nifsharp-cli.exe
   license: GPL-3.0
   notes: |
     One verb: build-trishape --in <template.nif> --mesh <mesh.json> --out <out.nif>
     [--shape <index|name>] [--flip-bitangent]. Template-edit ONE plain BSTriShape's geometry
     from a JSON mesh (vertices/uvs/triangles + optional normals/tangents); recompute tangent
     space + bounds; byte-preserve every other block (collision/shader/node tree — no PyNifly
     Havok regen). stdout = one JSON {out, shape, numVerts, numTris, vertexFlags, boundsCenter,
     boundsRadius, tangentsCalculated}; exit 0 ok / 2 error. GPL-3.0 (NiflySharp): subprocess-only,
     gitignored under tools/, never distributed (Karar 7). Source under tools/nifsharp-cli/src/.
     Rebuild: dotnet publish src/NifSharp.Build.csproj -c Release -r win-x64 --self-contained false
     -o tools/nifsharp-cli.
   ```
   `manifest.get("nifsharp-cli")` slug'u `nifsharp-cli` adından doğru üretir mi teyit et
   (`_slug` ilk token'ı alır → `nifsharp-cli`; alt çizgi değil tire, `.split()[0]` tireyi bölmez ✓).
6. **gitignore:** `tools/nifsharp-cli/` exe + dll'lerini (mutagen-cli gibi) yoksay, `src/` izlenir.
7. **Register:** `server.py`'ye §5.1 `fo4_nif_build` tool'unu ekle (diff sun, onay al — kod `mcp-server/`
   altında, diff-gated).
8. **Doğrula:**
   - `test_geometry_ops.py` artık `require_or_skip_nifsharp_cli` skip'i geçer; gerçek round-trip
     test'ini bir vanilla plain-BSTriShape template + `_good_mesh()` ile somutlaştır.
   - Roadmap C-validation: düz olmayan test mesh (eğri kart) → export → NifSkope "Update Tangent
     Space" diff → tangent/bounds doğru. **Görsel lighting doğruluğu Faz E vision-verify'e kadar
     iddia EDİLMEZ** (mirror-UV bitangent işaret riski).

---

## 7. Riskler (özet — detay research findings'te)

1. **NiflySharp API drift** → sürümü pinle, sembolleri compile-doğrula (§3.2 reality-check).
2. **Half-float/SNORM precision** → validator byte-eşitlik İDDİA ETMESİN, sadece yapısal.
3. **Mirror-UV bitangent handedness** → `--flip-bitangent` escape hatch + Faz E vision-verify; doğru
   lighting'i o check'siz iddia etme.
4. **Skinned/sub-indexed shape** → MVP plain BSTriShape hedefler; skinned ise yüksek sesle `Fail()`
   (segment handling = follow-up V2).
5. **Scope creep → from-scratch synthesis** → MVP = template-edit TEK shape. Sıfırdan writer = V2,
   önce TASKS.md kalemi.
6. **Yanlış --shape hedefi** → explicit shape selector ZORUNLU + exe çözülen shape adını/index'ini
   stdout'a echo etsin → Python intent eşleşmesini assert eder.

---

## 8. nif_ops ile ilişki (silinmeyen, tamamlayıcı)

- `nif_ops._tri_header()` / `vertex_flags()` = READ-ONLY validation/inspect sezgiselleri. **Faz C
  silmez.** Exe write yolunu sahiplenir; biz asla BSTriShape byte-author etmeyiz.
- `nif_ops.parse() / validate() / splice_collision_bytes()` = post-process + gate katmanı kalır.
- Pipeline: **NiflySharp geometri build → (Faz D collision) → `nif_ops.validate()`**.
- Donör-collision splice (`splice_collision_bytes` / `transplant_physics_system`) Faz D'ye kadar
  collision yolu kalır. nifsharp-cli template'i yerinde edit ettiği için donör'ün `bhkPhysicsSystem`
  byte'larını korur (PyNifly Havok regen YOK) → template-edit akışında splice **gereksiz bile olabilir**.

---

## 9. Bağımlılık + sonraki adım

- **Faz D** (headless convex collision) aynı exe'ye **ikinci verb** ekler (`bhkConvexVerticesShape` /
  `bhkListShape` writer); ikisi de NiflySharp blok-writer'ını paylaşır.
- **Faz E** (vision-verify) C'nin geometrisini + tangent-space lighting'ini oyun-içi doğrular (gated:
  oyun launch).
- **In-game render iddiası YOK** — görsel kanıt Faz E (ayrıca gated).
