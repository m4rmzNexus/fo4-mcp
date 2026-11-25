---
name: fo4-asset-adapt
description: Adapt an existing asset into a Fallout 4-native design. Use for art direction, scale, mesh and material conversion and an in-game comparison against a vanilla or DLC reference.
---

# Adapt an existing asset to Fallout 4

Start from the source the user actually wants to preserve. Record its editable mesh, texture set, units, ground or attachment pivot and intended player interaction. Write the local features someone should recognize at playing distance. Trace a comparable game record by plugin and local FormID with [asset trace](../fo4-asset-trace/SKILL.md). A visual reference, a collision reference and an animation reference may be different objects.

## Choose the adaptation

- **World object or set dressing.** Match physical dimensions against the reference at scale 1. Keep the source silhouette where it conveys identity. Choose construction, finish and a specific use or repair history. Add modeled details where they change the outline or the shadow at playing distance. Calibrate painted metal, rubber, glass and organic surfaces separately under the same light.
- **Architecture and Workshop.** Preserve the defining facade and plan. Read actual snap transforms and facing from the corresponding kit pieces. Size the playable opening, floor and collision separately from the decorative envelope. Exercise the entrance in both directions and check adjoining modules and save persistence when the request includes building.
- **Equipped object.** Use the game's corresponding attachment transforms, first-person camera and existing animation set as references. Check both equipped and world views, silhouettes and hand contact through the in-game animation.

## Build and inspect

Keep project-specific choices in the asset recipe. Trace dependencies, including source geometry, maps, art recipe, fonts or stamps, native material parameters and exporter version. Bind them to the build receipt so a paint-only edit can refresh the result. Keep published plugin filenames, FormIDs and model paths stable across art changes.

Use the existing Blender and NIF tools for geometry and collision. Inspect UVs and the source mask semantics before converting material channels. FO4 consumes diffuse, tangent-space normal and smooth/specular textures through its material. Read the donor BGSM or BGEM flags and compare the response in-game. Keep editable artwork outside the player package. Reference stock records and stock dependencies by their installed IDs and paths.

For a generated FO4 static, check that the `bhkNPCollisionObject` points to a body that actually exists inside its Havok system. A single-body PyNifly export takes `body_id=0` in `add_collision`. The default unsigned sentinel can survive a successful NIF readback and close the game as the object appears. Check the written index as well as the decoded geometry.

For a docked vessel, measure both ends of the gangway on the installed landscape, then walk from the actual deck onto the pier and back. Check the shore-facing rail opening in the visual mesh and in the collision hulls. The [Heybeli ferry builder](../../../projects/Heybeli/tools/asset_adapt/ferry.py) preserves the ship sections' shared waterline pivot and authors the gangway as a separate static.

When reviewing old Heybeli assets with the BGC map team, follow its dated [handoff contract](C:/GameDev/BGC/Saved/Session-Handoffs/2026-11-22/asset-inceleme/OKU.md). Match each source mesh to the catalogue's exact /Game/ path. Measure the original FBX and identify which editable derivative or FO4 output contains the fix. Keep BGC materials, signage, and import checks specific to that game. The [UE import audit](../../../projects/Heybeli/tools/asset_adapt/ue_asset_check.py) tests dimensions, material slots, convex collision and named sockets in an isolated project.

For the Heybeli SharedKit static workflow, [the simit recipe](../../../projects/Heybeli/tools/asset_adapt/simit.json) and [its builder](../../../projects/Heybeli/tools/asset_adapt/build.py) are a worked example. It generates the custom static and a separate A/B cell. The source family uses blue in its Dirt atlas for a linear paint tint. Other families can use different masks. For Workshop geometry start from the existing [E01 builder](../../../projects/Heybeli/tools/build_e01.py). For attached models the [equipped-item builder](../../../projects/Heybeli/tools/build_g3.py) preserves native transforms and records.

## Verify the player view

Run the project example from the Fallout workspace. The second command installs two dedicated profiles, starts the QA profile when the game slot is free, captures the wide and close views and puts the comparison save in the player profile.

~~~powershell
python projects/Heybeli/tools/asset_adapt/build.py projects/Heybeli/tools/asset_adapt/simit.json
python projects/Heybeli/tools/asset_adapt/compare.py projects/Heybeli/tools/asset_adapt/simit.json
~~~

Reopen the emitted NIF and check bounds, normals, UVs, material paths and collision. Check the final player archive with [package release](../fo4-package-release/SKILL.md). Place the custom object and the native reference on the same ground, at scale 1, in the same cell and lighting. Inspect the actual game frame, including any text orientation, material response, ground contact and relative scale. For a family, prove one representative, then batch its siblings and review them together. Report what was built, what was seen in Fallout and any remaining player or art judgment.
