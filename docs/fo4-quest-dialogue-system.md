# FO4 Quest & Dialogue System — Engineering Reference + Implementation Plan

> Scope: the canonical Fallout 4 quest/dialogue record graph, how a dialogue choice
> drives quest progression, the root cause of the broken "Yolcu Kerem" reward chain,
> the Mutagen-CLI writer capability gaps, and a phased roadmap that fixes Kerem first
> and then generalizes into a reusable quest-authoring system.
>
> Runtime: Fallout 4 1.11.221 (AE/NG). Writer: `tools/mutagen-cli/src/Program.cs`
> (Mutagen.Bethesda.Fallout4). Evidence base: on-disk census of
> `Fallout4.esm` (78,087 INFOs), Mutagen DLL reflection, the deployed
> `FO4MCP_Kerem.esp`, and 5 adversarial verdicts. Web (CK/UESP wikis) is
> corroboration only — those hosts 403 WebFetch in this environment, so **on-disk
> Mutagen evidence is load-bearing throughout**.

---

## 1. Executive Summary

**Root cause.** The Kerem talk→accept→kill→return→reward loop is broken because the
Mutagen-CLI writer cannot make a dialogue choice *do* anything. The INFO/`DialogResponses`
build block (`Program.cs:1695–1738`) emits only `Prompt`, `Speaker`, `Lines`, and
`Conditions`; it never sets `info.VirtualMachineAdapter` (a Papyrus topic-info fragment)
or `info.SetParentQuestStage` (the script-free SNAM stage-advance field). With no way for
a wheel pick to call `SetStage`, the quest is forced to auto-flow: stage 0 `RunOnStart`
immediately `SetStage(10)`, stage 10 shows the kill objective, and the alias `OnDeath`
(gated to the from-load stage 10) fires `SetStage(30)`, which auto-grants the reward. The
six dialogue topics are decorative narration; the reported symptom — *"stage 10'da raiderlar
var vurunca aninda bitiyor, Kerem sana armor verdi"* — is the exact consequence.

**The one missing primitive.** A way for an INFO to advance the owning quest's stage. FO4
offers **two** mechanisms and a fragment is *not* required (adversarial correction — see §2.6):

1. `DialogResponses.SetParentQuestStage` (SNAM, `{OnBegin:Int16, OnEnd:Int16}`, `-1`=unused)
   — sets the stage with **no Papyrus**. Used by **4,112** vanilla INFOs.
2. `DialogResponses.VirtualMachineAdapter` (`DialogResponsesAdapter` → `ScriptFragments
   {Script, OnBegin, OnEnd}`, compiled `TIF_*` `Fragment_Begin`/`Fragment_End`) — runs
   arbitrary Papyrus. Used by **1,796** vanilla INFOs; needed only when the line must do
   more than set a stage (e.g. `AddItem` + `Notification`).

Both are settable in Mutagen and emitted by **neither** today. Ship (1) first (zero
toolchain coupling), then (2) for reward-granting lines.

**Roadmap at a glance:**

| Phase | Goal | Writer change | Gating | Headless? |
|------|------|---------------|--------|-----------|
| **P0** | INFO can set a quest stage (script-free) | `ResponseSpec.setParentQuestStage{onBegin,onEnd}` → `info.SetParentQuestStage` | Mutagen | Yes |
| **P1** | Fix Kerem flow (data + Papyrus) | re-author stage graph; gate `OnDeath` to post-accept stage; `speaker=None` on player INFOs | mutagen + Papyrus | Yes (dump + in-game) |
| **P2** | INFO Papyrus fragment (TIF) | `ResponseSpec.fragment{scriptName,onBegin,onEnd}` → `info.VirtualMachineAdapter` (reuse `BuildScriptEntry`) | mutagen + Caprica (asset) | Yes |
| **P3** | dialogue-dump surfaces fragments + SNAM | extend dump readback | Mutagen | Yes |
| **P4** | INFO chaining: link-topic / StartScene / PreviousDialog | `ResponseSpec` link fields (reuse editorId resolver) | Mutagen | Yes |
| **P5** | NPC polish: outfit / Essential·Protected flags / packages / factions | `npc.Flags`, `case "outfit"`, use existing fields in spec | mutagen (mostly) | Yes (dump) |
| **P6** | Voice + FaceGen automation | external bake step (FaceFXWrapper / CK) | asset / CK-gated | Partial |
| **P7** | Reusable quest-author template + MCP tool surface + test matrix | spec scaffolder + `fo4_*` docstrings | mixed | Yes |

---

## 2. FO4 Quest / Dialogue Engine Model (authoritative reference)

### 2.1 The record graph: QUST → DLBR → DIAL → INFO

**[high]** The graph is `QUST → DialogBranch (DLBR) → DialogTopic (DIAL) → DialogInfo
(INFO / DialogResponses) → DialogResponse (line)`. In FO4 the DIAL topics **and** the DLBR
branches are stored **nested under the owning QUST** (`quest.DialogTopics`,
`quest.DialogBranches`), **not** as global record groups — there is no flat
`mod.DialogResponses`/`mod.DialogBranches` accessor (compile error if attempted).
*Source: Mutagen overlay iteration of `Fallout4.esm` + writer (`qst.DialogTopics.Add`,
`Program.cs:1738`).*

Linking fields:
- `DialogTopic.Branch` (`IFormLinkNullable`) → its DLBR; `DialogTopic.Quest` → owning QUST.
- `DialogBranch.Quest` → owning QUST; `DialogBranch.StartingTopic` → the entry topic.
- INFO (`DialogResponses`) is a sub-style major record held in `DialogTopic.Responses`;
  each `DialogResponse` line is a sub-record (no FormKey).

On-disk proof (BunkerHill, quest `05FD31`): `BRANCH 05FD31 → startTopic 05FB73`; `TOPIC
05FB73 branch=05FD31`.

### 2.2 Branch category vs Topic category — a common misconception

**[high]** `DialogBranch.CategoryType` has **only** `{Player, Command}`.
`DialogBranch.Flag` = `{TopLevel, Blocking, Exclusive}` (bit flags). The full
Player/Scene/Combat/Favor/Detection/Service/Misc split lives on the **TOPIC**
(`DialogTopic.CategoryEnum`), **not** the branch. *Source: reflection over
`Mutagen.Bethesda.Fallout4.dll`.* **Pitfall to flag in any tutorial we generate:**
"branch Category = Player/Scene/Combat…" is **wrong**.

### 2.3 What makes a Player topic surface on the 4-option wheel

**[high]** All four must hold:
1. the owning DLBR branch has `Category=Player` and `Flag` includes `TopLevel`;
2. the topic itself has `Category=Player`;
3. the topic is linked to that branch (`DialogTopic.Branch` set);
4. at least one INFO under the topic passes its conditions for the addressed NPC.

`TopLevel` is the wheel-surfacing flag. Vanilla distribution: 130 Player branches → 128
`TopLevel`, 1 `Blocking`, 1 none. **`Blocking` branches preempt** other dialogue (forced
flow), they are not normal wheel options. **Subtype** (`DialogTopic.SubtypeEnum`, ~150
values) is a classification tag, **not** a hard gate — `Custom0` is valid and used by both
Kerem and vanilla (e.g. BunkerHill `05FB73` uses subtype `Rumors`). `Priority` (default 50)
orders competing topics; higher = checked first.

### 2.4 Subject vs Target run-on (final, corrected)

**[high]** In a **Player-category wheel** topic INFO, the speaker is implicitly the PLAYER
and the addressed NPC is the **Subject**. NPC-scoping conditions (`GetIsID` / `GetIsAliasRef`
to gate which NPC shows the option) **must use `RunOn=Subject`**. `RunOn=Target` on a
player-wheel NPC-scope condition is the classic empty-wheel bug (already fixed in Kerem).

Vanilla confirms both NPC-scoping forms on real Player/`Custom0` wheel topics:
- `GetIsAliasRef` Subject==`alias4` (Min02 `Min02SharedTopic` → PrestonGarvey).
- `GetIsID` Subject==`019FD9` (`MinRadiantOwned02Intro`, `DN121MinRadiantIntro` →
  PrestonGarvey **base**).

**Adversarial correction (verdict "partial").** `GetIsID` is a **base-form test** — it is
only unambiguous when exactly one reference carries that base (a unique NPC). It can be
preempted/unreliable when the quest has aliases the NPC fills, on templated/leveled/duplicated
bases. `GetIsAliasRef` Subject==`<npcAlias>` ties the check to the quest's actually-filled
reference and is robust to all of those. **Recommendation for Kerem: prefer `GetIsAliasRef`
Subject==alias 0** (the forced-filled Kerem alias), keeping `GetIsID` Subject==`000802` only
as the documented fallback. *Implementation note:* the `GetIsAliasRef` alias index goes in
the condition's **number/alias slot** (`ParameterOneNumber` / `Unknown3`), **not** as a
FormKey — and `dialogue-dump` currently mis-renders that slot as a FormKey (a known display
artifact; `_re_min02.json`'s `param1:000004` is really alias 4, not a Door).

### 2.5 Player choice → NPC reply: speaker and "Link To" (final, corrected)

**[high]** A player wheel option is **NOT** "set Speaker=NPC on the player INFO". The
canonical vanilla pattern:

- Player-category topic on a Player/`TopLevel` DLBR branch.
- INFO `Speaker = None`.
- `Prompt` = the short wheel label (e.g. *"Your store?"*, *"Charge Card?"*).
- `Responses[].Text` = the **PLAYER's** spoken line (e.g. *"This your store?"*). 319 vanilla
  player INFOs carry **both** a prompt and response text — all `Speaker=None`.
- NPC-scoping via `GetIsID`/`GetIsAliasRef` runOn=Subject (**not** via Speaker).
- The NPC's **reply is a separate construct**: either a different condition-gated sibling
  INFO in the same branch, or a **Scene** (`StartScene`).

**Adversarial census (verdict "partial" → confirms speaker half).** Of 8,661 Player-category
INFOs, **8,595 (99.24%) have `Speaker=None`**; the 66 that set a speaker are **all** Radio/
remote-start topics using the single fixed Minutemen radio voice `0AA78E` — none are
face-to-face wheel options. Kerem sets `speaker=000802 (Kerem)` on all 6 player INFOs →
**non-vanilla**. It is not merely cosmetic: a set Speaker "acts like `GetIsID` … only that
NPC can say this line" (CK), so it is **redundant** with Kerem's existing `GetIsID Subject==
Kerem` condition (which is why the wheel still surfaces), but it mislabels the player's own
line as spoken by Kerem and can mis-route `.fuz`/LIP/facegen lookups. **Fix: drop `speaker`
on every player response** (one-line spec change; the writer already emits speaker only when
supplied — `Program.cs:1701–1705`).

**"Link To" correction.** FO4 has **no** Skyrim-style per-INFO "Link To" topic list. Across
all 8,661 player INFOs: `Topic(LinkTo)=0` uses, `PreviousDialog=0` uses; the only populated
reply-handoff field is **`StartScene`** (271 uses, e.g. DiamondCity `08659B` → Scene
`0865AE`). So the reply mechanism is a condition-gated sibling INFO and/or a Scene, never a
topic-level link table. `DialogResponses` does expose `PreviousDialog`/`SharedDialog`/
`DialogGroup` for chaining when needed, but vanilla rarely uses them for this.

### 2.6 HOW dialogue drives a quest stage (the key mechanism, corrected)

**[high]** Two engine mechanisms; **a Papyrus fragment is NOT required**:

**(A) Script-free — `DialogResponses.SetParentQuestStage` (SNAM).** `{OnBegin:Int16,
OnEnd:Int16}`, `-1` = unused. `OnEnd=N` sets the owning quest to stage `N` when the line
**ends**; `OnBegin=N` when it **begins**. **4,112** vanilla INFOs use this — including
player-wheel ones (e.g. MS13 `0003A60F` `OnEnd=30`, VMAD null). The CK exposes it as the
"Set Parent Quest Stage" radio button and recommends it over a fragment `SetStage` for
efficiency. **Lowest-friction path** for "pick line → SetStage"; no `.pex` needed.

**(B) Papyrus fragment — `DialogResponses.VirtualMachineAdapter`.** Type
`DialogResponsesAdapter` → `.ScriptFragments {Script (ScriptEntry), OnBegin (ScriptFragment),
OnEnd (ScriptFragment)}`; each `ScriptFragment = {ScriptName, FragmentName}`. Canonical class
name `TIF_<QuestEditorID>_<8hexFormID>`, functions `Fragment_Begin` / `Fragment_End`,
canonical body `GetOwningQuest().SetStage(N)` (topic data is stored separately from quest
data, so you reach the quest via `GetOwningQuest()`). Locals `akSpeaker`/`akActor` available.
**1,796** vanilla INFOs use this; 39 use both. Needed when the line must run more than a bare
stage set (e.g. `player.AddItem(reward)` + `Debug.Notification`).

**Both are AUTHORABLE OUTSIDE THE CK** (both Mutagen properties are `canWrite=True`) and are
**missing from the writer** — the central gap. The QUST path already emits the identical
`{ScriptName, FragmentName}` shape (`QuestScriptFragment`, `Program.cs:1908–1917`), so the
INFO-fragment plumbing is a pattern-replica, not new research.

### 2.7 GREETING vs Scene vs branch

**[medium]** `SubtypeEnum` includes `Greeting`, `Hello`, `ForceGreet`. A **Greeting** topic
(NPC-side, Speaker=NPC) is what the NPC says when first engaged, *before* the wheel;
`ForceGreet` pushes the NPC to initiate. For **scripted multi-line beats** (back-and-forth,
choreography, paired NPC lines) the canonical structure is a **Scene (SCEN)** with phases/
actions referencing topics — Scenes can also run quest-stage actions and must check **End
Running Scene** on terminal responses or the scene never closes. Branch dialogue is for the
interactive wheel; Scenes for authored cinematic/sequenced beats. The radiant Minutemen Outro
topics are prompt-only (`responseCount=0`) and fully scene-driven. *Scene records not deeply
probed this session; medium confidence.*

---

## 3. Canonical Quest-Loop Anatomy (reverse-engineered from vanilla)

This is the **blueprint to reproduce** for any talk→accept→kill→return→reward quest. Ground
truth: Min02 (`03A457`, hand-authored, the exact "kill raiders to clear a settlement" shape),
plus MinRadiantOwned02 (`03DF95`) and DN121 (`026340`).

**Core mechanism: the NPC's wheel CHANGES as the quest advances** because each topic INFO is
condition-gated on the quest's own `GetStage`/`GetStageDone`. You never delete/re-add topics;
you gate them so the available options flip automatically.

```
STAGE   BEAT            WHO ADVANCES IT                       WHAT THE BEAT DOES
-----   -------------   -----------------------------------   --------------------------------
  0     setup           RunOnStart fragment                   SetObjectiveDisplayed(10 talk)
                                                              (do NOT auto-advance)
 10/20  accept (talk)   ACCEPT INFO (SetParentQuestStage or   SetObjectiveCompleted(10)
                        TIF Fragment_End → SetStage)          + SetObjectiveDisplayed(20 kill)
 20→30  kill            alias OnDeath (gated to accept stage) SetObjectiveCompleted(20)
                        → SetStage(cleared)                   + SetObjectiveDisplayed(30 return)
 100    turn-in/reward  TURN-IN INFO (gated GetStage==ready)  player.AddItem(reward)
                        → SetStage(complete)                  + Notification + complete + Stop
```

Observed vanilla gates and conventions:
- **Offer vs Turn-in are TWO separate topics on the same NPC**, distinguished purely by their
  `GetStageDone` gate: Offer requires `GetStageDone(self,obj)==0`, Turn-in requires `==1`
  (MinRadiantOwned02 Intro `GetStageDone==0` / Outro `22B511` `GetStageDone==1`).
- **Completion is gated by `GetStageDone`, never by a kill-counter on the dialogue.** No
  `GetDead`/`GetDeadCount` condition appears on any vanilla turn-in INFO across the 4 quests.
  Kill detection lives in **Papyrus** (alias `OnDeath` → `SetStage`); the dialogue only
  *reads* the resulting stage.
- **Speaker=None on every player wheel INFO**; identify the speaker via `GetIsID`/
  `GetIsAliasRef` runOn=Subject. (Only Radio remote-start topics carry a fixed Speaker.)
- **Reward is delivered on the RETURN conversation**, at the ending stage (CK `[QE40][END]`),
  never on the kill.
- **`GetStageDone` for idempotency** — gate beats on "has this stage ever run" so they don't
  re-fire. Min02 condition census: `GetStageDone ×66`, `GetStage ×16`.
- **Objective markers (compass + Pip-Boy)** require simultaneously: (1) the objective is
  **Displayed** (`SetObjectiveDisplayed` — there is **no** per-objective "displayed" bit on
  the record; `QuestObjective.Flag` = only `{OrWithPrevious, NoStatsTracking}`, so display is
  runtime state); (2) the objective carries a **QSTA target** (`QuestObjectiveTarget
  {AliasID, Flags, Keyword, Conditions}`) pointing at a **filled** Reference Alias that
  resolves to a placed/loaded ref with a world position; (3) any per-target conditions pass.
  Multiple targets per objective are allowed (two raider aliases → two pips). *Vanilla
  return/meet objectives set `CompassMarkerIgnoresLocks` (DN121 obj10/20) — a benign polish
  flag Kerem omits.*
- **Reference alias fill:** `ForcedReference` fills **deterministically** the moment the quest
  runs (the robust path for fixed hand-placed actors; alternatives = Unique Actor or
  Conditions/find-matching-ref). An **empty alias is the #1 silent-failure trap**: it kills
  BOTH the marker AND every `GetIsAliasRef` on it.
- **Radiant abstraction (skip for hand-authored):** DN121/MinRadiantOwned02 gate on
  `GetVMQuestVariable(067FF9)` of the Min04 radiant controller. A standalone quest must use
  direct `GetStage`/`GetStageDone(self)` gates (as hand-authored Min02 does) — copying the
  radiant variable silently never satisfies.

---

## 4. Kerem Defect Analysis

### 4.1 Intended flow (stage-by-stage)

```
Stage 0 (RunOnStart)  -> SetObjectiveDisplayed(10 "Talk to Kerem"); marker -> alias0 (Kerem).
                         Do NOT auto-SetStage. Raiders exist but kill objective hidden.
Player talks to Kerem -> greeting/offer wheel (gated pre-accept). Kerem explains the problem.
Player picks "Accept" -> that INFO sets quest -> Stage 20 (script-free SNAM or TIF fragment).
Stage 20 (accepted)   -> SetObjectiveCompleted(10) + SetObjectiveDisplayed(20 "Kill raiders");
                         marker -> alias1/alias2. (Optionally aggro raiders NOW.)
Player kills both     -> alias OnDeath, gated GetStageDone(20)==1, -> SetStage(30).
Stage 30 (cleared)    -> SetObjectiveCompleted(20) + SetObjectiveDisplayed(30 "Return");
                         marker -> alias0. NO reward yet.
Player returns, talks -> turn-in INFO (gated GetStage==30) sets quest -> Stage 100 AND grants
                         reward: player.AddItem(armor) + Debug.Notification.
Stage 100 (complete)  -> SetObjectiveCompleted(30) + CompleteAllObjectives + Stop().
```

Four player-driven gates (accept dialogue, kill, return dialogue, reward); reward is the
payoff of the **return conversation**.

### 4.2 Current flow (as authored on disk)

```
Stage 0 (RunOnStart)  -> SetStage(10)  [auto-advance; no talk beat]
Stage 10              -> SetObjectiveDisplayed(20)  [kill objective shown at game load]
Raiders (02898B)         placed PRE-HOSTILE on the open forecourt; no gate to acceptance.
Player kills both     -> KeremRaiderAlias.OnDeath, gated GetStage()==10 (true from load),
                         both-dead -> SetStage(30).
Stage 30              -> SetObjectiveCompleted(20) + AddItem(reward) + Notification + SetStage(100)
                         [REWARD GRANTED ON KILL]
Stage 100             -> SetObjectiveCompleted(30) + CompleteAllObjectives + Stop()
6 topics (greeting/offer/accept/inProgress gated ==10, turnIn ==30, idle >=100), all
Player/TopLevel/Custom0, speaker=Kerem(000802). NONE carries a fragment -> all decorative.
```

Objectives 10 ("Talk to Kerem") and 30 ("Return to Kerem") are authored with targets but
**never `SetObjectiveDisplayed`** — only objective 20 is ever shown. The reported symptom is
reproduced exactly.

### 4.3 Defect table

| ID | Title | Severity | Root cause | Fix direction |
|----|-------|----------|------------|---------------|
| **F1** | Stage 0 auto-advances to kill phase; obj 10 never displayed | critical | `Fragment_Stage_0000` unconditionally `SetStage(10)`; obj 10 has a target but no `SetObjectiveDisplayed(10)` | Stage 0 → `SetObjectiveDisplayed(10)` only; advance via accept INFO |
| **F2** | Kill objective shown + counted before acceptance → incidental kills auto-complete (**the reported bug**) | critical | obj 20 displayed at load; `OnDeath` gated to `GetStage==10`, the from-load stage | Add a post-accept kill stage reachable only via accept INFO; display obj 20 there; gate `OnDeath` on `GetStageDone(acceptStage)==1` |
| **F3** | Raiders pre-hostile, no gate to acceptance | major | raider ACHRs (base `02898B`) placed already-hostile via cellOverride | Gate hostility/enable to post-accept stage (robust), or rely on F2's stage-gated count (minimum) |
| **F4** | Dialogue INFOs run no fragment → greeting/offer/accept/turn-in decorative | critical | `ResponseSpec` has no fragment/SNAM field; INFO build loop never sets `info.VirtualMachineAdapter`/`info.SetParentQuestStage` (`Program.cs:1695–1738`) | **Writer: add INFO stage-advance (P0 SNAM, then P2 TIF). Highest-leverage system fix.** |
| **F5** | Reward auto-granted on kill instead of turn-in; return beat collapsed | critical | `Stage 30` (set by `OnDeath`) does `AddItem`+`Notification`+`SetStage(100)`; obj 30 never displayed | On both-dead, advance to a "cleared" stage that displays obj 30, no reward; move reward into the turn-in INFO |
| **F6** | Obj 10 & 30 never displayed (display-orphans) | major | only `SetObjectiveDisplayed(20)` is ever called | One objective transition per beat (10 in stage 0; complete-10/display-20 in accept; complete-20/display-30 in cleared; complete-30 in done) |
| **F7** | `speaker=Kerem` on player-wheel INFOs is non-vanilla | minor | spec sets `speaker=KEREM_NPC` on every response (`author_kerem.py:100`) | Set `speaker=None` on player responses; deliver Kerem's reply as the response text or a paired NPC info |
| **F8** | `OnDeath` gate keyed to the from-load stage; no dedicated kill stage | minor | alias logic is correct in isolation but gated on `GetStage==10` (active from load) | Re-point gate to the post-accept stage; keep both-dead re-derivation and forced-fill aliases |

*Note: GLOB `KeremRaidersKilled` (`000800`) is declared but unused — harmless dead code; drop
from the design narrative or wire a real counter.*

---

## 5. Writer Capability Gap Analysis

### 5.1 Already supported (do NOT re-implement)

| Primitive | Evidence (`Program.cs`) |
|-----------|-------------------------|
| QUST stages + `RunOnStart` (INDX 0x02) + QSDT log entries | 1555–1574 |
| Objectives + QSTA targets (AliasID, flags, per-target conditions) | 1576–1626 |
| Reference/location aliases (forcedReference/uniqueActor/event-fill/external; collection aliases blocked) | 1766–1871 |
| QUST stage fragments (`QuestAdapter.Script` + `QuestScriptFragment`) | 1887–1917 |
| Alias fragments (per-alias OnBegin/OnEnd) | 1918–1947 |
| Whole-quest VMAD + typed properties (`BuildScriptEntry`/`BuildScriptProperty`) | 933–1010, 1877–1886 |
| DIAL topics → INFO responses → lines (text/responseNumber/emotion), prompt, speaker | 1662–1740 |
| DLBR branches (Player/TopLevel; any `DialogBranch.Flag`) | 1638–1661, 1746–1759 |
| INFO conditions (full `BuildCondition`: 479 functions, op, 2 auto-typed params, runOn, alias-runOn, reference) | 874–927 |
| SCEN scenes (actors/phases/typical actions referencing a topic) | 1948–2033 |
| `dialogue-dump` audit verb (Player+TopLevel candidates; per-topic/INFO fields) | 474–557 |
| NPC polish fields (DefaultOutfit, Factions, Aggression/Confidence/Assistance, Inventory, CombatStyle, Class, Voice, Packages-bind, DefaultTemplate/UseTemplateActors) | 1323–1469 |
| `type=faction` (flags + interfaction relations) | 2241–2272 |
| `type=package` (single DataLocation input) | 2596–2657 |

### 5.2 Missing / partial (the gaps)

| Gap | canEmit | Why needed | Effort | Mutagen-authorable? |
|-----|---------|-----------|--------|---------------------|
| **INFO `SetParentQuestStage` (SNAM)** | **no** | Script-free "pick line → SetStage" — lowest-friction Kerem fix; no Caprica | **S** | Yes (`canWrite=True`, unused) |
| **INFO Papyrus fragment (TIF VMAD)** | **no** | Arbitrary Papyrus on a line (`AddItem`+`Notification`+conditional) — reward-granting turn-in | **M** | Yes (API ready; reuse `BuildScriptEntry`) |
| **INFO chaining (Topic link / StartScene / StartScenePhase / PreviousDialog)** | **no** | Real branching (choice → specific NPC reply / kick a Scene) beyond flat one-INFO-per-topic | **M** | Yes (fields exist, unwired) |
| **NPC `Flags` (Essential/Protected/…)** | **no** | Keep Kerem alive through the ambush until turn-in. `npc.Flags` never set; `RecordSpec.Flags` is consumed by quest/faction/leveled cases, not NPC | **S** | Yes (plain bitfield) |
| **`type=outfit` (OTFT record)** | **no** | Author a bespoke outfit. (Kerem can reuse a vanilla OTFT, so this is not on the critical path) | **S** | Yes (`mod.Outfits.AddNew`, `Items` list) |
| **Multi-input `Package.Data` map** | partial | Only single `DataLocation` wired; full input index-map deferred (wrong sbyte index silently breaks AI) | **M** | Yes (research gate on the index-map) |
| **`dialogue-dump` of script-bearing INFOs** | partial | Dump reads prompt/speaker/responseCount/conditions only (529–542); blind to SNAM/VMAD → cannot verify P0/P2 by dump alone | **S** | Yes |
| **Player-topic speaker convention** | partial | Writer faithfully emits whatever speaker is given; needs a "player topic ⇒ force speaker None" authoring rule or guard | **S** | Authoring convention |
| **GetIsAliasRef alias-index param** | partial | `BuildCondition` must emit the alias index in the number/alias slot, not as a FormKey (for the §2.4 recommendation) | **S** | Verify `SetParam`/`AliasRunOn` path |

**Decisive finding:** `canEmitInfoFragment = NO` today, but it is **plumbing, not a library
limitation**. The writer emits VMAD adapters only for QUST (1879) and ACTI (2539); the
`DialogResponses` build (1695–1738) never touches `info.VirtualMachineAdapter` /
`info.SetParentQuestStage`. `author_kerem.py:50–52` documents the workaround verbatim
("Dialogue can't drive stage transitions … so the quest auto-flows and DWELLS at stage 10").

---

## 6. Phased Implementation Roadmap

Phases are ordered so **P0 + P1 unblock Kerem with zero new toolchain coupling**, then
generalize. All phases are headless-testable (disk round-trip via `dialogue-dump` /
serialize + the Tier-3 `fo4_run_ingame_test` runner).

### P0 — INFO `SetParentQuestStage` (script-free stage advance) · gating: Mutagen · headless: yes

- **Goal:** an INFO can set the owning quest's stage with no Papyrus.
- **Writer change (`Program.cs`):**
  - `ResponseSpec` (~3562): add `public SetStageSpec? SetParentQuestStage { get; set; }`
    where `SetStageSpec = { int? OnBegin; int? OnEnd }`.
  - INFO build loop (~1736, before `topic.Responses.Add(info)`): if present,
    `info.SetParentQuestStage = new DialogSetParentQuestStage { OnBegin = (short)(spec.OnBegin ?? -1), OnEnd = (short)(spec.OnEnd ?? -1) }`.
  - Python normalizer (`mcp-server/fo4_mcp/tools.py`, response normalization ~1377–1439):
    pass through `setParentQuestStage`.
- **Tests:** writer round-trip — author an INFO with `setParentQuestStage.onEnd=20`, reopen
  the ESP via Mutagen overlay, assert `info.SetParentQuestStage.OnEnd == 20`.
- **Acceptance:** SNAM survives round-trip; `dialogue-dump` (after P3) reports it.
- **Mutagen-authorable.** Likely the **first thing to ship** — alone it could fix Kerem's
  accept (→20) and turn-in (→100) with no `.pex`. (Reward `AddItem` still needs P2.)

### P1 — Fix the Kerem flow (data + Papyrus) · gating: mixed · headless: yes (dump + in-game)

Concrete corrected design (uses P0 for accept; uses P2 TIF only for the reward-bearing
turn-in — until P2 lands, accept and stage-flow can be P0-only and reward can stay in a stage
fragment gated to the **return** stage as an interim):

**New stage graph** (re-author `staging/kerem/author_kerem.py` + `QF_KeremQuest.psc`):

| Stage | Fragment body | Set by |
|------|----------------|--------|
| 0 (RunOnStart) | `SetObjectiveDisplayed(10)` | engine on quest start |
| 20 (accepted) | `SetObjectiveCompleted(10)` + `SetObjectiveDisplayed(20)` (+ optional aggro raiders) | **accept INFO** `SetParentQuestStage.OnEnd=20` |
| 30 (cleared) | `SetObjectiveCompleted(20)` + `SetObjectiveDisplayed(30)` | alias `OnDeath` → `SetStage(30)` |
| 100 (complete) | `SetObjectiveCompleted(30)` + `CompleteAllObjectives()` + `Stop()` | **turn-in INFO** (P2 TIF: `player.AddItem(reward)` + `Notification` + `SetStage(100)`) |

**Papyrus changes:**
- `QF_KeremQuest.psc`: `Fragment_Stage_0000` → `SetObjectiveDisplayed(10)` (remove
  `SetStage(10)`); add `Fragment_Stage_0020` (complete 10, display 20); `Fragment_Stage_0030`
  (complete 20, display 30, **no reward**); `Fragment_Stage_0100` (complete 30,
  CompleteAllObjectives, Stop). Move `AddItem(reward)`+`Notification` into the **turn-in TIF**.
- `KeremRaiderAlias.psc`: change gate from `owner.GetStage()==10` to
  `owner.GetStageDone(20)` (or `GetStage()>=20 && GetStage()<30`); on both-dead → `SetStage(30)`.

**Dialogue/spec changes:**
- `speaker=None` on all 6 player responses (drop `"speaker": KEREM_NPC`).
- Prefer `GetIsAliasRef` Subject==alias0 over `GetIsID` Subject==`000802` (§2.4).
- Re-gate topics to the new windows: greeting/offer `GetStage<20`; accept `GetStage<20`
  (its INFO carries `setParentQuestStage.onEnd=20`); inProgress `GetStage==20`; turnIn
  `GetStage==30` (its INFO carries the reward TIF + `SetStage(100)`); idle `GetStage>=100`.
- Objective 10/30 markers: confirm QSTA targets + forced-filled aliases (already correct);
  add `CompassMarkerIgnoresLocks` on obj 10/30 for vanilla parity (optional polish).

**Tests / acceptance (headless):**
- `dialogue-dump --quest 000806` readback: 6 topics, `speaker=None`, accept INFO shows SNAM
  `OnEnd=20`, turn-in INFO shows VMAD/SNAM (after P3).
- `fo4_run_ingame_test` console asserts: `startquest` → assert stage 0 + obj 10 displayed;
  `setstage <q> 20` (sim accept) → obj 20 displayed; kill both raiders → assert stage 30 +
  obj 30 displayed + **no reward yet**; trigger turn-in → assert reward in inventory + stage
  100 + quest stopped. (Console `setstage` bypasses the wheel, so an in-wheel pass is the
  final manual check; the asserts prove the *graph* is correct headlessly.)
- **SEQ:** after authoring, run `fo4_build_seq(plugin, dry_run=False)` (CK `-GenerateSEQ` via
  MO2) so the StartGameEnabled quest auto-starts on a clean new game — the `.seq` high byte is
  the runtime load-order index and **cannot** be hand-rolled. The Tier-3 `startquest` smoke
  bypasses SEQ, so add a clean-new-game check to the matrix.

### P2 — INFO Papyrus fragment (TIF) · gating: mutagen + Caprica (asset) · headless: yes

- **Goal:** arbitrary Papyrus on a line (the reward-bearing turn-in).
- **Writer change:** `ResponseSpec.Fragment { string ScriptName; string? OnBegin; string? OnEnd }`
  → `info.VirtualMachineAdapter = new DialogResponsesAdapter { Version=6, ObjectFormat=2 }`;
  populate `.ScriptFragments` with a `ScriptFragment{ScriptName, FragmentName}` on OnEnd (and/
  or OnBegin), reusing `BuildScriptEntry` for `ScriptFragments.Script`. Match the QUST
  adapter's `Version=6/ObjectFormat=2` (wrong version → unreadable record).
- **Papyrus:** emit/author `Fragments/TopicInfos/TIF_<questEID>_<8hexINFOFormID>.psc` with
  `Fragment_End` body `GetOwningQuest().SetStage(100)` + reward; compile via `fo4_papyrus_build`
  (Caprica), same as `QF_`. **Asset gate:** the `.pex` must deploy alongside the ESP and the
  `ScriptName`/`FragmentName` must match exactly, or the wheel option silently does nothing
  (the current bug in a subtler form). **FormID stability matters** — INFO FormIDs name the
  TIF; pin them so re-authoring doesn't break the binding.
- **Tests/acceptance:** round-trip asserts `info.VirtualMachineAdapter.ScriptFragments.OnEnd
  .ScriptName/FragmentName`; in-game assert reward granted only via the turn-in line.

### P3 — `dialogue-dump` surfaces fragments + SNAM · gating: Mutagen · headless: yes

- **Goal:** verification readback for P0/P2/P4 (dump is currently blind to them).
- **Writer change:** in the dump (529–542) emit per-INFO `setParentQuestStage{onBegin,onEnd}`,
  `fragment{onBegin,onEnd scriptName/fragmentName}`, and link/scene fields. Also fix the
  `GetIsAliasRef` param mis-render (§2.4) — show alias index, not a spurious FormKey.
- **Acceptance:** dump of a P0/P2-authored quest reports the new fields; diff vs Min02 shape.

### P4 — INFO chaining (link-topic / StartScene / PreviousDialog) · gating: Mutagen · headless: yes

- **Goal:** true choice→reply branching and Scene kick-off.
- **Writer change:** `ResponseSpec` link fields (`linkTopic`, `startScene`, `startScenePhase`,
  `previousDialog`) resolved against in-spec `topicsByEid`/scene editorIds (extend the resolver
  at `Program.cs:2006–2014`). Set `info.Topic`/`info.StartScene`/`info.StartScenePhase`/
  `info.PreviousDialog`.
- **Acceptance:** authored chain round-trips; in-game a player line kicks the named Scene.

### P5 — NPC polish · gating: mostly Mutagen · headless: yes (dump)

Most NPC-polish fields are **already in the writer** — the gap is the **spec doesn't use
them**, plus two small additions. Hostility is driven by **faction reaction, not aggression**.

- **Writer additions:** `npc.Flags |= Npc.Flag.<name>` (Essential/Protected) — genuine gap;
  `case "outfit"` (OTFT) if a bespoke outfit is wanted.
- **Use existing fields in the Kerem spec:** `DefaultOutfit` (vanilla clothing OTFT) +
  Inventory weapon (auto-drawn in combat); `Factions` membership; `Aggression`/`Confidence`
  (≥Average so Kerem fights, not flees)/`Assistance=HelpsAllies`; bind a Sandbox PACK (vanilla
  `DefaultSandboxExteriorEditorLocation 023331`) so Kerem mills around instead of T-posing.
- **Ambush recipe:** raider faction `Relations`: `PlayerFaction(01C21C)=Enemy` **and**
  Kerem-faction=Enemy; Kerem **not** in any player-hostile faction; set `Essential` (or
  `Protected`) so he survives the fight until turn-in.
- **Acceptance:** Mutagen probe confirms flags/factions/outfit/packages on the NPC record.

### P6 — Voice + FaceGen automation · gating: asset / CK · headless: partial

- **Already baked for Kerem** (23 `.fuz` under `Sound/Voice/FO4MCP_Kerem.esp/MaleEvenToned/`
  named by INFO FormID; FaceGeom `00000802.NIF` + tint `_d/_msn/_s.dds`). **Not Mutagen-
  authorable** — external bake.
- **Productionize:** after authoring INFOs, read back their FormIDs and bake a silent `.fuz`+
  LIP per response via **FaceFXWrapper** (headless, CK-independent; inputs = FonixData.cdf +
  16kHz/16-bit/mono wav + line text) into the matching VoiceType folder. FaceGen FaceGeom NIF
  + tint DDS is **CK Ctrl+F4** (GPU-bound, human/CK-gated) unless the NPC is templated
  (inherits the template's face, losing the unique look). **Critical:** FormIDs name the
  `.fuz`; if record order shifts, re-bake or pin FormIDs.

### P7 — Reusable quest-author template + MCP surface + test matrix · gating: mixed · headless: yes

- A spec scaffolder that emits the canonical 3-beat stage graph, the Offer/Turn-in topic pair
  (gated `GetStageDone==0`/`==1`), forced-filled aliases + QSTA markers, and the accept/turn-in
  INFO stage-advances. Docstring/MCP surface to expose (`fo4_create_record` JSON, plus a
  higher-level `fo4_author_quest` helper). Test matrix: disk round-trip + Tier-3 in-game +
  clean-new-game SEQ check. See §8.

---

## 7. Risks, Open Questions & Headless Verification Strategy

**Open questions / thin evidence (stated honestly):**
- **In-wheel verification of P0/P1 is the one thing console asserts cannot fully prove.**
  `setstage`/`startquest` bypass the wheel, so the *graph* is headlessly verifiable but the
  final "pick the option, watch the stage move" is a manual pass. We accept disk readback +
  console-driven stage asserts as the headless gate, with an in-wheel check flagged for the
  user's return.
- **Scene (SCEN) records** were not deeply probed this session (medium confidence in §2.7).
  P4's `StartScene` path needs a small SCEN probe before relying on it for the turn-in.
- **`speaker=None` suppression risk (F7):** vanilla strongly implies player INFOs want
  `Speaker=None`; we have not in-game-confirmed that clearing it doesn't change surfacing.
  Mitigation: the `GetIsID`/`GetIsAliasRef` Subject condition already scopes the NPC, so
  clearing Speaker should be safe — verify with a dump diff + one in-game wheel check.
- **`GetIsAliasRef` param encoding:** confirm `BuildCondition`/`SetParam` puts the alias index
  in the number slot (not a FormKey) before switching Kerem off `GetIsID`.
- **CK/UESP web hosts 403 WebFetch** here; all web claims are WebSearch-snippet corroboration.
  On-disk Mutagen evidence is authoritative throughout.

**Per-phase headless verification:**
- **P0/P2/P3/P4:** Mutagen overlay round-trip — author, reopen the ESP, assert the new field
  (`SetParentQuestStage.OnEnd`, `VirtualMachineAdapter.ScriptFragments`, link/scene). Then
  `dialogue-dump` readback once P3 surfaces them.
- **P1:** `fo4_run_ingame_test` console asserts walking the stage graph (start → sim-accept →
  kill → assert no-reward-yet → turn-in → assert reward + stop), **plus** the clean-new-game
  SEQ auto-start check (the Tier-3 `startquest` hides the SEQ requirement).
- **P5:** Mutagen probe of the NPC record (flags/factions/outfit/packages).
- **P6:** filesystem assert that `.fuz`/NIF/DDS exist under the correct FormID-named paths;
  partial because the bake quality is not headlessly judgeable.

---

## 8. System-Wide Reusability

These primitives generalize **every** quest, not just Kerem:

**Reusable quest+dialogue template** (the P7 scaffolder). A single spec shape produces:
- A canonical **3-beat stage graph** (setup / accepted / cleared / complete) with one
  objective transition per beat and `GetStageDone`-based idempotency.
- An **Offer/Turn-in topic pair** on one NPC, gated `GetStageDone==0` / `==1`, both
  Player/`TopLevel`/`Custom0`, `Speaker=None`, NPC-scoped via `GetIsAliasRef` Subject==alias.
- **Stage-advancing INFOs**: accept INFO `setParentQuestStage.onEnd=<acceptStage>` (P0);
  turn-in INFO TIF fragment `AddItem`+`SetStage(<complete>)` (P2).
- **Forced-filled aliases + QSTA markers** for each actionable objective (the #1 silent-failure
  trap is designed out by construction).
- A **SEQ build step** baked into the publish path.

**MCP tool surface to expose:** keep `fo4_create_record` (the JSON spec) as the primitive, and
add a higher-level `fo4_author_quest` helper whose docstring documents the canonical loop,
the SNAM-vs-TIF choice, and the `Speaker=None` / `GetIsAliasRef`-Subject rules — so the
authoring agent reproduces the vanilla blueprint by default instead of re-deriving it.
Extend `dialogue-dump` (P3) into the standard **vanilla-parity diff** tool: dump the authored
quest and diff its branch/topic/condition/SNAM/fragment shape against Min02 (`03A457`).

**Slotting into the world-content roadmap.** This work is the dialogue-progression spine that
the existing `docs/world-content-quest-roadmap.md` phases (W7 packages, W9 voice, W10 FaceGen)
hang off: P0–P4 deliver the missing INFO-progression primitive that makes *any* talk-driven
quest possible; P5–P6 fold the already-supported NPC-polish fields and the (already-baked, to-be-
automated) voice/FaceGen pipeline into the template; P7 productizes the whole thing as a
reusable author flow. The Mutagen-vs-CK boundary is explicit at every phase: **Mutagen-
authorable** = INFO SNAM/VMAD, NPC flags, OTFT, factions, packages, the whole record graph;
**CK/asset-gated** = the `.fuz`/LIP bake (headless via FaceFXWrapper but external) and the
FaceGeom NIF + tint DDS (CK Ctrl+F4, GPU-bound).
