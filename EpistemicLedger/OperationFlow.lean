import EpistemicLedger.ClaimRecordTypes

/-
Epistemic Ledger v2 — Operation-Graph & Structure-Flow (Taint) Verifier.

Why v2 exists (learned from blind test rounds 1 & 2):
In v0/v1, a claim record held a flat list of dependencies and a `kind : intrinsic | conditional`
flag. Across all 38 blind records, Rule 4 fired iff the auditor marked `kind = .intrinsic`,
because every real experiment has at least one `setByExperimenter` dependency. As a result,
v1 could not distinguish:
  (a) structure smuggling — claiming X emerges while X (or a copy of X) is injected upstream
      and flows into the output through an operation chain, vs.
  (b) genuine emergence — an experimenter-configured setup whose inputs do NOT carry X,
      yet X arises in the output.

In v2, a study is encoded as a directed graph of typed *operations*:
  - Inputs declare which structural properties (`carries : List σ`) they already contain.
  - Operations propagate structure tags from inputs to outputs (and may inject new tags,
    partition a domain into `(output, remainder)`, mark a channel `.lossy`, or explicitly
    attempt `forget tag evidence`).
  - A `forget` step blocks propagation of `tag` ONLY when `evidence = .shown`.
    A `.notShown` or `.contradicted` forget step fails to block propagation and is flagged.
  - Claims assert structural flow properties (`emergesWithout`, `independentConvergence`,
    `uniqueRecovery`, `conditionalFlow`), checked mechanically over multi-hop paths.
-/
namespace EpistemicLedger.OperationFlow

/-- What kind of operation connects `inputs` to `output`. -/
inductive OpKind (σ : Type) where
  /-- Standard transformation: propagates all input structures plus `introduces`. -/
  | transform (introduces : List σ)
  /-- Domain partition / cut: propagates all input structures plus `cutStructures`
      (representing structure introduced by the boundary/cut itself). -/
  | partition (cutStructures : List σ)
  /-- Many-to-one / information-destroying projection (e.g., lossy observation,
      forcing conflicting interpretations into one positive pair). Propagates input
      structures and blocks `uniqueRecovery` claims downstream. -/
  | lossy (introduces : List σ)
  /-- Explicit attempt to drop structure `tag`. Blocks `tag` iff `evidence = .shown`. -/
  | forget (tag : σ) (evidence : Invariance)
  deriving DecidableEq, Repr

/-- One directed operation step in a study's derivation graph. -/
structure Op (ν σ : Type) where
  name : String
  inputs : List ν
  output : ν
  kind : OpKind σ
  deriving DecidableEq, Repr

/-- An entry node of the derivation graph with its origin and pre-existing structures. -/
structure SourceNode (ν σ : Type) where
  node : ν
  origin : Source
  carries : List σ
  deriving DecidableEq, Repr

/-- A study's operational derivation graph. -/
structure FlowGraph (ν σ : Type) where
  sources : List (SourceNode ν σ)
  ops : List (Op ν σ)
  deriving DecidableEq, Repr

/-- Quantitative resource expenditure for one arm of an effectiveness comparison (v2.3.1).
Binds each exact natural-number quantity (`unit`, `amount`) to the specific `source` node
carrying `dimension` so numbers cannot float free of their measured cost source. -/
structure ResourceUsage (ν σ : Type) where
  source : ν
  dimension : σ
  unit : String
  amount : Nat
  deriving DecidableEq, Repr

/-- What a claim asserts about structural flow in the graph. -/
inductive FlowClaimKind (ν σ : Type) where
  /-- "Structure `tag` emerges at `target` without `tag` being injected upstream." -/
  | emergesWithout (target : ν) (tag : σ)
  /-- Policy 3 (v2.1): "Structure `tag` arises at `target` while excluding `tag` from
      `excludedChannel` (Alarm 1: any source/op carrying `tag` into `excludedChannel`), AND
      without `tag` supplied by any unforgotten `setByExperimenter` source or op upstream of
      `target` (Alarm 2: author-supplied structure, Rule 4)."
      Both alarms emit distinct findings; under Policy 3, EITHER finding rejects the claim. -/
  | emergesWithExclusion (target : ν) (excludedChannel : ν) (tag : σ)
  /-- "Branches `branchA` and `branchB` independently converge on `tag`
      (no shared upstream node carrying `tag`, nor shared unforgotten experimenter source)." -/
  | independentConvergence (branchA branchB : ν) (tag : σ)
  /-- "`target` uniquely recovers `tag` (no lossy channel on any path to `target`,
      and `tag` is actually accessible via a source carrying `tag`)." -/
  | uniqueRecovery (target : ν) (tag : σ)
  /-- "Given `declaredSources`, `target` holds (all upstream sources reaching `target`
      are declared)." -/
  | conditionalFlow (target : ν) (declaredSources : List ν)
  /-- Tier 2 (v2.3): "Method `methodNode` demonstrates effectiveness/efficiency at
      `evaluationNode` under cost dimension `costTag`, compared against independent control
      `controlNode` and metered via `costLedgerNode` with explicit resource expenditures
      `methodUsage` and `controlUsage`."
      Fixes all Codex R1 v2.2 counterexamples:
      - Physical cost uses raw `ancestors` (a `.forget .shown` step CANNOT erase spent cost).
      - `methodNode` and `controlNode` must be mutually independent (no directed path either way).
      - Post-hoc metering (`methodNode → billMeter`) is allowed; `ledger` simply cannot equal
        `methodNode` or `controlNode` and must cover every raw cost source spent by either arm.
      - Budget parity is checked numerically on `(dimension, unit, amount)` (catches 1 vs 100
        GPU-hours on the same cluster, while allowing equal $500 across two separate accounts). -/
  | effectivenessClaim
      (methodNode : ν)
      (evaluationNode : ν)
      (controlNode : Option ν)
      (costLedgerNode : Option ν)
      (costTag : σ)
      (methodUsage : List (ResourceUsage ν σ))
      (controlUsage : List (ResourceUsage ν σ))
  /-- Claim explicitly lies outside structural operation-flow verification
      (e.g., normative legal balancing, value judgments, policy weighing, or financial bookkeeping). -/
  | outOfScope (reason : String)
  deriving DecidableEq, Repr

/-- A claim audited against an operation graph. -/
structure FlowClaim (ν σ : Type) where
  statement : String
  graph : FlowGraph ν σ
  kind : FlowClaimKind ν σ
  deriving DecidableEq, Repr

/-- Mechanical findings emitted by the operation-flow auditor. -/
inductive FlowFinding (ν σ : Type) where
  /-- Structure `tag` was smuggled into `target` from `origin` along `path`. -/
  | smuggledStructure (tag : σ) (origin : ν) (path : List ν)
  /-- Policy 3 Alarm 1: `tag` leaked into the claim's explicitly excluded channel (from either
      a `.measured` or `.setByExperimenter` source, or an `Op`). -/
  | excludedChannelLeak (tag : σ) (origin : ν) (path : List ν)
  /-- Policy 3 Alarm 2 (Rule 4): `tag` was supplied to `target` by an unforgotten
      `setByExperimenter` source or an `Op` injection, independent of narrow channel wording. -/
  | authorSuppliedStructure (tag : σ) (origin : ν) (path : List ν)
  /-- A `forget tag` operation on a path to `target` had `.notShown` or `.contradicted` evidence. -/
  | failedForgetOnPath (opName : String) (tag : σ) (evidence : Invariance)
  /-- Two allegedly independent branches share upstream node `shared` carrying `tag`. -/
  | sharedUpstreamStructure (shared : ν) (tag : σ)
  /-- Two allegedly independent branches share an unforgotten `setByExperimenter` source. -/
  | sharedExperimenterSource (shared : ν)
  /-- A lossy (many-to-one) operation sits on a path to a `uniqueRecovery` target. -/
  | lossyChannelOnPath (opName : String) (output : ν)
  /-- Target of `uniqueRecovery` has no upstream `SourceNode` granting access to `tag`. -/
  | unaccessedTargetStructure (target : ν) (tag : σ)
  /-- An upstream source node reaches `target` but is omitted from `declaredSources`. -/
  | undeclaredUpstreamSource (source : ν)
  /-- Graph completeness error: an upstream operation consumes a node that has neither a
      `SourceNode` nor a producing `Op` in the graph. -/
  | danglingInput (opName : String) (missing : ν)
  /-- Tier 2: `methodNode` has no raw upstream `SourceNode` carrying `costTag`, or no cost ledger was provided. -/
  | missingCostAccounting (methodNode : ν) (costTag : σ)
  /-- Tier 2: `costLedgerNode` is identical to `methodNode` or `controlNode` (not a distinct metering/ledger node). -/
  | trivialCostLedger (costLedgerNode : ν) (armNode : ν)
  /-- Tier 2: `costLedgerNode` does not feed `evaluationNode`. -/
  | unusedCostLedger (costLedgerNode : ν) (evaluationNode : ν)
  /-- Tier 2: raw cost source `costSource` feeds an arm (ignoring `.forget`) but is NOT accounted in `costLedgerNode`. -/
  | unaccountedCostSource (costSource : ν) (costLedgerNode : ν) (costTag : σ)
  /-- Tier 2: `methodNode` itself does not feed `evaluationNode`. -/
  | unusedMethodNode (methodNode : ν) (evaluationNode : ν)
  /-- Tier 2: effectiveness claim provides no control arm (`controlNode = none`). -/
  | missingMatchedControl (methodNode : ν)
  /-- Tier 2: claim compares `methodNode` against itself (`controlNode = some methodNode`). -/
  | trivialSelfControl (methodNode : ν)
  /-- Tier 2: `controlNode` is derived from `methodNode` or vice versa (not an independent experimental arm). -/
  | dependentControlArm (methodNode : ν) (controlNode : ν)
  /-- Tier 2: `controlNode` is declared in the graph but does not feed `evaluationNode`. -/
  | unusedControlNode (controlNode : ν) (evaluationNode : ν)
  /-- Tier 2: quantitative resource budgets (`methodUsage` / `controlUsage`) for `costTag` are missing (unquantified). -/
  | unquantifiedBudget (methodNode : ν) (costTag : σ)
  /-- Tier 2: a `ResourceUsage` entry cites `source` that does not belong to that arm's raw `costTag` origins,
      or a raw `costTag` source of an arm has no positive `ResourceUsage` entry. -/
  | unboundUsageSource (armNode : ν) (sourceNode : ν) (costTag : σ)
  /-- Tier 2: quantitative `costTag` budgets differ between `methodNode` and `controlNode` (e.g. 1 vs 100 GPU-hrs). -/
  | unmatchedControlBudget (methodNode : ν) (controlNode : ν) (costTag : σ)
  /-- Claim explicitly declared out of scope for structural operation-flow auditing. -/
  | claimOutOfScope (reason : String)
  deriving DecidableEq, Repr

/-- Legacy two-state verdict for a flow claim (retained untouched for backwards compatibility). -/
inductive FlowVerdict where
  | admissible
  | rejected
  deriving DecidableEq, Repr

/-- Four-state epistemic verdict separating:
    - `admissible`: no structural findings inside the declared observation slice
      (consistent within declared slice — never certifies reality outside the graph).
    - `unestablished`: data or experimental design stops at the edge of the map
      (missing control, missing cost ledger, unquantified budget, `.notShown` forget,
      undeclared upstream source, or dangling graph input — not a proven structural contradiction).
    - `rejected`: direct structural or empirical contradiction inside the declared graph.
    - `outOfScope`: claim lies outside structural operation-flow verification
      (e.g., normative legal balancing, value judgments, or financial bookkeeping). -/
inductive EpistemicVerdict where
  | admissible
  | unestablished
  | rejected
  | outOfScope
  deriving DecidableEq, Repr

variable {ν σ : Type} [DecidableEq ν] [DecidableEq σ]

/-! ### Core graph semantics (order-independent, fuel-bounded, decidable) -/

/-- Structures directly injected by an operation itself (not merely passed through). -/
def opIntroduces : OpKind σ → List σ
  | .transform xs => xs
  | .partition xs => xs
  | .lossy xs => xs
  | .forget _ _ => []

/-- Does operation `op` explicitly block tag `tag` via proven invariance (`.shown`)? -/
def opBlocksTag (op : Op ν σ) (tag : σ) : Bool :=
  match op.kind with
  | .forget t .shown => decide (t = tag)
  | _ => false

/-- Does operation `op` propagate tag `tag` from its inputs to its output? -/
def opPropagatesTag (op : Op ν σ) (tag : σ) : Bool :=
  !opBlocksTag op tag

/-- Does `source` carry `tag` (regardless of `origin`)? -/
def sourceCarries (g : FlowGraph ν σ) (n : ν) (tag : σ) : Bool :=
  g.sources.any (fun s => s.node = n ∧ tag ∈ s.carries)

/-- Does an experimenter-set (`setByExperimenter`) source carry `tag`? -/
def experimenterSourceCarries (g : FlowGraph ν σ) (n : ν) (tag : σ) : Bool :=
  g.sources.any (fun s => s.node = n ∧ s.origin = .setByExperimenter ∧ tag ∈ s.carries)

/-- Does any operation producing `n` directly introduce `tag`? -/
def opInjectsAt (g : FlowGraph ν σ) (n : ν) (tag : σ) : Bool :=
  g.ops.any (fun op => op.output = n ∧ tag ∈ opIntroduces op.kind)

/--
Backward reachability with explicit witness path:
finds a path `[origin, ..., target]` along which `tag` is injected at `origin`
(either by a `SourceNode` carrying `tag` or an `Op` introducing `tag`) and
propagates to `target` without being blocked by a `.forget tag .shown` step.
-/
def findSmugglingPathAux (g : FlowGraph ν σ) (tag : σ) : Nat → ν → Option (List ν)
  | 0, _ => none
  | fuel + 1, cur =>
    if sourceCarries g cur tag || opInjectsAt g cur tag then
      some [cur]
    else
      let incoming := g.ops.filter (fun op => op.output = cur && opPropagatesTag op tag)
      incoming.findSome? fun op =>
        op.inputs.findSome? fun inp =>
          (findSmugglingPathAux g tag fuel inp).map (· ++ [cur])

/-- Find a smuggling path of `tag` reaching `target` (fuel = `ops.length + 1`). -/
def findSmugglingPath (g : FlowGraph ν σ) (tag : σ) (target : ν) : Option (List ν) :=
  findSmugglingPathAux g tag (g.ops.length + 1) target

/--
Backward reachability restricted to author-supplied origins (`origin = .setByExperimenter`
sources and `Op` introductions). Measured sources carrying `tag` are NOT counted as
author-supplied structure (Alarm 2 / Rule 4).
-/
def findAuthorSuppliedPathAux (g : FlowGraph ν σ) (tag : σ) : Nat → ν → Option (List ν)
  | 0, _ => none
  | fuel + 1, cur =>
    if experimenterSourceCarries g cur tag || opInjectsAt g cur tag then
      some [cur]
    else
      let incoming := g.ops.filter (fun op => op.output = cur && opPropagatesTag op tag)
      incoming.findSome? fun op =>
        op.inputs.findSome? fun inp =>
          (findAuthorSuppliedPathAux g tag fuel inp).map (· ++ [cur])

/-- Find an author-supplied (`setByExperimenter` / `Op`) path of `tag` reaching `target`. -/
def findAuthorSuppliedPath (g : FlowGraph ν σ) (tag : σ) (target : ν) : Option (List ν) :=
  findAuthorSuppliedPathAux g tag (g.ops.length + 1) target

/-- Pure reachability of upstream nodes (ignoring forget barriers) to find ancestors of `target`. -/
def ancestorsAux (ops : List (Op ν σ)) : Nat → List ν → List ν
  | 0, visited => visited
  | fuel + 1, visited =>
    let preds := ops.foldl
      (fun acc op => if op.output ∈ visited then acc ++ op.inputs else acc) []
    let next := preds.foldl (fun acc x => if x ∈ acc then acc else x :: acc) visited
    if next.length = visited.length then visited
    else ancestorsAux ops fuel next

/-- All nodes (including `target` itself) from which a directed path reaches `target`. -/
def ancestors (g : FlowGraph ν σ) (target : ν) : List ν :=
  ancestorsAux g.ops (g.ops.length + 1) [target]

/-- Upstream nodes from which `tag` can propagate to `target` (respecting `.shown` forget blocks). -/
def tagAncestorsAux (ops : List (Op ν σ)) (tag : σ) : Nat → List ν → List ν
  | 0, visited => visited
  | fuel + 1, visited =>
    let preds := ops.foldl
      (fun acc op =>
        if op.output ∈ visited && opPropagatesTag op tag then acc ++ op.inputs else acc) []
    let next := preds.foldl (fun acc x => if x ∈ acc then acc else x :: acc) visited
    if next.length = visited.length then visited
    else tagAncestorsAux ops tag fuel next

/-- All nodes from which `tag` flows unblocked into `target`. -/
def tagAncestors (g : FlowGraph ν σ) (tag : σ) (target : ν) : List ν :=
  tagAncestorsAux g.ops tag (g.ops.length + 1) [target]

/-- Backward reachability from `target` that NEVER expands through any node in `forbidden`.
Used to ensure a cost ledger meters cost sources directly (allowing post-hoc edges from
`method`/`control` for timing, while rejecting a fake ledger that merely clones an arm's output). -/
def ancestorsExcludingAux (ops : List (Op ν σ)) (forbidden : List ν) : Nat → List ν → List ν
  | 0, visited => visited
  | fuel + 1, visited =>
    let preds := ops.foldl
      (fun acc op =>
        if op.output ∈ visited && op.output ∉ forbidden then
          acc ++ op.inputs.filter (fun inp => inp ∉ forbidden)
        else acc) []
    let next := preds.foldl (fun acc x => if x ∈ acc then acc else x :: acc) visited
    if next.length = visited.length then visited
    else ancestorsExcludingAux ops forbidden fuel next

def ancestorsExcluding (g : FlowGraph ν σ) (forbidden : List ν) (target : ν) : List ν :=
  if target ∈ forbidden then []
  else ancestorsExcludingAux g.ops forbidden (g.ops.length + 1) [target]

/-- Raw upstream `SourceNode`s carrying `tag` reachable without traversing `forbidden` nodes. -/
def rawSourceOriginsExcluding (g : FlowGraph ν σ) (tag : σ) (forbidden : List ν) (target : ν) : List ν :=
  let reach := ancestorsExcluding g forbidden target
  (g.sources.filter (fun s => s.node ∈ reach && tag ∈ s.carries)).map (·.node)

/-- Every raw upstream `SourceNode` carrying `tag` reachable via `ancestors` (IGNORING `.forget`
barriers). Used for physical cost accounting: a `.forget .shown` ablation cannot erase
resources physically spent during a run. -/
def rawSourceOrigins (g : FlowGraph ν σ) (tag : σ) (target : ν) : List ν :=
  let reach := ancestors g target
  (g.sources.filter (fun s => s.node ∈ reach && tag ∈ s.carries)).map (·.node)

/-- Total positive quantity recorded for `(costTag, unit)` in a usage list. -/
def usageAmountFor (us : List (ResourceUsage ν σ)) (costTag : σ) (unit : String) : Nat :=
  (us.filter (fun u => u.dimension = costTag && u.unit = unit)).foldl (fun acc u => acc + u.amount) 0

/-- Distinct units recorded for `costTag` in a usage list. -/
def usageUnitsFor (us : List (ResourceUsage ν σ)) (costTag : σ) : List String :=
  ((us.filter (fun u => u.dimension = costTag)).map (·.unit)).eraseDups

/-- Do two resource-usage lists declare identical positive totals on every `(costTag, unit)`? -/
def budgetsMatchNumerically
    (methodUsage controlUsage : List (ResourceUsage ν σ)) (costTag : σ) : Bool :=
  let mUnits := usageUnitsFor methodUsage costTag
  let cUnits := usageUnitsFor controlUsage costTag
  let allUnits := (mUnits ++ cUnits).eraseDups
  !allUnits.isEmpty &&
    allUnits.all fun u =>
      let ma := usageAmountFor methodUsage costTag u
      let ca := usageAmountFor controlUsage costTag u
      ma > 0 && ma = ca

/-- Check that every `ResourceUsage` entry for `costTag` binds to a real raw cost source of `armNode`,
and every raw cost source of `armNode` has at least one positive usage entry. -/
def usageBindingFindings
    (armNode : ν) (armRawCosts : List ν) (us : List (ResourceUsage ν σ)) (costTag : σ) :
    List (FlowFinding ν σ) :=
  let relevant := us.filter (fun u => u.dimension = costTag && u.amount > 0)
  let stray := relevant.filterMap fun u =>
    if u.source ∉ armRawCosts then some (.unboundUsageSource armNode u.source costTag) else none
  let coveredSources := relevant.map (·.source)
  let missing := armRawCosts.filterMap fun src =>
    if src ∉ coveredSources then some (.unboundUsageSource armNode src costTag) else none
  stray ++ missing

/-- Every upstream `SourceNode` carrying `tag` that can flow unblocked into `target`
(excludes tags fabricated solely by intermediate operations). -/
def sourceOrigins (g : FlowGraph ν σ) (tag : σ) (target : ν) : List ν :=
  let reach := tagAncestors g tag target
  (g.sources.filter (fun s => s.node ∈ reach && tag ∈ s.carries)).map (·.node)

/-- Every upstream `SourceNode` or `Op` introducing `tag` that can flow unblocked into `target`. -/
def smugglingOrigins (g : FlowGraph ν σ) (tag : σ) (target : ν) : List ν :=
  let reach := tagAncestors g tag target
  let fromSources := (g.sources.filter (fun s => s.node ∈ reach && tag ∈ s.carries)).map (·.node)
  let fromOps := (g.ops.filter (fun op => op.output ∈ reach && tag ∈ opIntroduces op.kind)).map (·.output)
  (fromSources ++ fromOps).eraseDups

/-- Every `setByExperimenter` source node reachable along unblocked `tag` paths into `target`. -/
def experimenterSourcesUpstream (g : FlowGraph ν σ) (tag : σ) (target : ν) : List ν :=
  let reach := tagAncestors g tag target
  ((g.sources.filter (fun s => s.origin = .setByExperimenter && s.node ∈ reach)).map (·.node)).eraseDups

/-- Graph completeness check: any input consumed by an operation upstream of `target`
that is neither declared in `g.sources` nor produced as the output of an `Op` in `g.ops`. -/
def danglingInputsUpstream (g : FlowGraph ν σ) (target : ν) : List (FlowFinding ν σ) :=
  let reach := ancestors g target
  let definedNodes := g.sources.map (·.node) ++ g.ops.map (·.output)
  g.ops.flatMap fun op =>
    if op.output ∈ reach then
      op.inputs.filterMap fun inp =>
        if inp ∉ definedNodes then some (.danglingInput op.name inp) else none
    else []

/-- Failed forget operations (`notShown` or `contradicted`) for `tag` sitting upstream of `target`
whose inputs actually receive `tag` (an idle forget with no upstream origin carrying `tag`
is not flagged). -/
def failedForgetsUpstream (g : FlowGraph ν σ) (tag : σ) (target : ν) : List (FlowFinding ν σ) :=
  let reach := tagAncestors g tag target
  g.ops.filterMap fun op =>
    if op.output ∈ reach && op.inputs.any (fun inp => (findSmugglingPath g tag inp).isSome) then
      match op.kind with
      | .forget t .notShown =>
        if t = tag then some (.failedForgetOnPath op.name t .notShown) else none
      | .forget t .contradicted =>
        if t = tag then some (.failedForgetOnPath op.name t .contradicted) else none
      | _ => none
    else none

/-- Failed forget operations (`notShown` or `contradicted`) for `tag` sitting upstream of `target`
whose inputs actually receive author-supplied `tag`. -/
def failedAuthorForgetsUpstream (g : FlowGraph ν σ) (tag : σ) (target : ν) : List (FlowFinding ν σ) :=
  let reach := tagAncestors g tag target
  g.ops.filterMap fun op =>
    if op.output ∈ reach && op.inputs.any (fun inp => (findAuthorSuppliedPath g tag inp).isSome) then
      match op.kind with
      | .forget t .notShown =>
        if t = tag then some (.failedForgetOnPath op.name t .notShown) else none
      | .forget t .contradicted =>
        if t = tag then some (.failedForgetOnPath op.name t .contradicted) else none
      | _ => none
    else none

/-- Lossy operations sitting anywhere upstream of `target`. -/
def lossyOpsUpstream (g : FlowGraph ν σ) (target : ν) : List (FlowFinding ν σ) :=
  let reach := ancestors g target
  g.ops.filterMap fun op =>
    if op.output ∈ reach then
      match op.kind with
      | .lossy _ => some (.lossyChannelOnPath op.name op.output)
      | _ => none
    else none

/-- Arms excluded from direct cost-metering traversal so a ledger cannot simply mirror an arm output. -/
def ledgerExcludedArms (methodNode : ν) : Option ν → List ν
  | some ctrl => [methodNode, ctrl]
  | none      => [methodNode]

/-- Audit a `FlowClaim` against its operation graph. -/
def auditFlow (c : FlowClaim ν σ) : List (FlowFinding ν σ) :=
  match c.kind with
  | .emergesWithout target tag =>
    let smuggled : List (FlowFinding ν σ) :=
      match findSmugglingPath c.graph tag target with
      | some path =>
        match path with
        | origin :: _ => [.smuggledStructure tag origin path]
        | [] => []
      | none => []
    smuggled ++ failedForgetsUpstream c.graph tag target ++ danglingInputsUpstream c.graph target
  | .emergesWithExclusion target excludedChannel tag =>
    let alarm1 : List (FlowFinding ν σ) :=
      match findSmugglingPath c.graph tag excludedChannel with
      | some path =>
        match path with
        | origin :: _ => [.excludedChannelLeak tag origin path]
        | [] => []
      | none => []
    let alarm2 : List (FlowFinding ν σ) :=
      match findAuthorSuppliedPath c.graph tag target with
      | some path =>
        match path with
        | origin :: _ => [.authorSuppliedStructure tag origin path]
        | [] => []
      | none => []
    alarm1 ++ alarm2
      ++ failedForgetsUpstream c.graph tag excludedChannel
      ++ failedAuthorForgetsUpstream c.graph tag target
      ++ danglingInputsUpstream c.graph target
      ++ danglingInputsUpstream c.graph excludedChannel
  | .independentConvergence branchA branchB tag =>
    let originsA := smugglingOrigins c.graph tag branchA
    let originsB := smugglingOrigins c.graph tag branchB
    let sharedTag := (originsA.filter (fun n => n ∈ originsB)).map (fun n => .sharedUpstreamStructure n tag)
    let expA := experimenterSourcesUpstream c.graph tag branchA
    let expB := experimenterSourcesUpstream c.graph tag branchB
    let sharedExp := (expA.filter (fun n => n ∈ expB)).map (fun n => .sharedExperimenterSource n)
    sharedTag ++ sharedExp
      ++ danglingInputsUpstream c.graph branchA
      ++ danglingInputsUpstream c.graph branchB
  | .uniqueRecovery target tag =>
    let lossy := lossyOpsUpstream c.graph target
    let access :=
      if (sourceOrigins c.graph tag target).isEmpty then
        [.unaccessedTargetStructure target tag]
      else []
    lossy ++ access ++ danglingInputsUpstream c.graph target
  | .conditionalFlow target declaredSources =>
    let reach := ancestors c.graph target
    let undeclared := c.graph.sources.filterMap fun s =>
      if s.node ∈ reach && s.node ∉ declaredSources then
        some (.undeclaredUpstreamSource s.node)
      else none
    undeclared ++ danglingInputsUpstream c.graph target
  | .effectivenessClaim methodNode evaluationNode controlNode costLedgerNode costTag methodUsage controlUsage =>
    let methodRawCosts := rawSourceOrigins c.graph costTag methodNode
    let evalAnc := ancestors c.graph evaluationNode
    let costMissing : List (FlowFinding ν σ) :=
      if methodRawCosts.isEmpty then [.missingCostAccounting methodNode costTag] else []
    let methodUnused : List (FlowFinding ν σ) :=
      if methodNode ∉ evalAnc then [.unusedMethodNode methodNode evaluationNode] else []
    let ledgerFindings : List (FlowFinding ν σ) :=
      match costLedgerNode with
      | none => [.missingCostAccounting methodNode costTag]
      | some ledger =>
        let trivMethod : List (FlowFinding ν σ) :=
          if ledger = methodNode then [.trivialCostLedger ledger methodNode] else []
        let trivCtrl : List (FlowFinding ν σ) :=
          match controlNode with
          | some ctrl => if ledger = ctrl then [.trivialCostLedger ledger ctrl] else []
          | none => []
        let unusedLedgerErr : List (FlowFinding ν σ) :=
          if ledger ∉ evalAnc then [.unusedCostLedger ledger evaluationNode] else []
        let armNodes : List ν := ledgerExcludedArms methodNode controlNode
        -- Ledger must meter cost sources directly (without merely passing through `methodNode` or `ctrl`!)
        let ledgerDirectCosts := rawSourceOriginsExcluding c.graph costTag armNodes ledger
        let allArmRawCosts :=
          match controlNode with
          | some ctrl => (methodRawCosts ++ rawSourceOrigins c.graph costTag ctrl).eraseDups
          | none => methodRawCosts
        let unchargedErr : List (FlowFinding ν σ) :=
          allArmRawCosts.filterMap fun src =>
            if src ∉ ledgerDirectCosts then some (.unaccountedCostSource src ledger costTag) else none
        trivMethod ++ trivCtrl ++ unusedLedgerErr ++ unchargedErr ++ danglingInputsUpstream c.graph ledger
    let controlFindings : List (FlowFinding ν σ) :=
      match controlNode with
      | none => [.missingMatchedControl methodNode]
      | some ctrl =>
        let selfErr : List (FlowFinding ν σ) :=
          if ctrl = methodNode then [.trivialSelfControl methodNode] else []
        let depErr : List (FlowFinding ν σ) :=
          if ctrl ≠ methodNode &&
              (methodNode ∈ ancestors c.graph ctrl || ctrl ∈ ancestors c.graph methodNode) then
            [.dependentControlArm methodNode ctrl]
          else []
        let unusedErr : List (FlowFinding ν σ) :=
          if ctrl ∉ evalAnc then [.unusedControlNode ctrl evaluationNode] else []
        let ctrlRawCosts := rawSourceOrigins c.graph costTag ctrl
        let mUnits := usageUnitsFor methodUsage costTag
        let cUnits := usageUnitsFor controlUsage costTag
        let budgetErr : List (FlowFinding ν σ) :=
          if mUnits.isEmpty || cUnits.isEmpty then
            [.unquantifiedBudget methodNode costTag]
          else if budgetsMatchNumerically methodUsage controlUsage costTag then
            []
          else
            [.unmatchedControlBudget methodNode ctrl costTag]
        let bindErr :=
          usageBindingFindings methodNode methodRawCosts methodUsage costTag
            ++ usageBindingFindings ctrl ctrlRawCosts controlUsage costTag
        selfErr ++ depErr ++ unusedErr ++ budgetErr ++ bindErr ++ danglingInputsUpstream c.graph ctrl
    costMissing ++ ledgerFindings ++ methodUnused ++ controlFindings
      ++ danglingInputsUpstream c.graph methodNode
      ++ danglingInputsUpstream c.graph evaluationNode
  | .outOfScope reason => [.claimOutOfScope reason]

def flowVerdict (c : FlowClaim ν σ) : FlowVerdict :=
  if (auditFlow c).isEmpty then .admissible else .rejected

/-- Classify a finding as a direct structural/empirical contradiction (`true` → `rejected`)
    versus a data/design/graph-boundary gap (`false` → `unestablished`). -/
def FlowFinding.isContradiction : FlowFinding ν σ → Bool
  | .smuggledStructure _ _ _              => true
  | .excludedChannelLeak _ _ _            => true
  | .authorSuppliedStructure _ _ _        => true
  | .failedForgetOnPath _ _ .contradicted => true
  | .failedForgetOnPath _ _ .notShown     => false
  | .failedForgetOnPath _ _ .shown        => false
  | .sharedUpstreamStructure _ _          => true
  | .sharedExperimenterSource _           => true
  | .lossyChannelOnPath _ _               => true
  | .unaccessedTargetStructure _ _        => true
  | .undeclaredUpstreamSource _           => false
  | .danglingInput _ _                    => false
  | .missingCostAccounting _ _            => false
  | .trivialCostLedger _ _                => true
  | .unusedCostLedger _ _                 => false
  | .unaccountedCostSource _ _ _          => true
  | .unusedMethodNode _ _                 => false
  | .missingMatchedControl _              => false
  | .trivialSelfControl _                 => true
  | .dependentControlArm _ _              => true
  | .unusedControlNode _ _                => false
  | .unquantifiedBudget _ _               => false
  | .unboundUsageSource _ _ _             => false
  | .unmatchedControlBudget _ _ _         => true
  | .claimOutOfScope _                    => false

/-- Four-state epistemic verdict for a flow claim.
    Preserves legacy `flowVerdict` untouched for full backwards compatibility. -/
def epistemicVerdict (c : FlowClaim ν σ) : EpistemicVerdict :=
  match c.kind with
  | .outOfScope _ => .outOfScope
  | _ =>
    let findings := auditFlow c
    if findings.isEmpty then .admissible
    else if findings.any FlowFinding.isContradiction then .rejected
    else .unestablished

/-! ### General Soundness & Anti-Degeneration Theorems (no Classical.choice) -/

/-- Helper: `findSmugglingPathAux` never returns `some []`. -/
theorem findSmugglingPathAux_ne_nil (g : FlowGraph ν σ) (tag : σ) (fuel : Nat) (cur : ν) :
    findSmugglingPathAux g tag fuel cur ≠ some [] := by
  cases fuel with
  | zero => simp [findSmugglingPathAux]
  | succ k =>
    unfold findSmugglingPathAux
    split
    · simp
    · intro h
      have ⟨_, op, _, _, hop, _⟩ := List.findSome?_eq_some_iff.mp h
      have ⟨_, inp, _, _, hinp, _⟩ := List.findSome?_eq_some_iff.mp hop
      cases hm : findSmugglingPathAux g tag k inp with
      | none => simp [hm] at hinp
      | some p => simp [hm] at hinp

/--
Theorem 1 (Soundness of `emergesWithout`):
If an `emergesWithout target tag` claim is `admissible`, then no unblocked smuggling
path carries `tag` to `target`.
-/
theorem admissible_emerges_has_no_smuggling_path
    (c : FlowClaim ν σ) (target : ν) (tag : σ)
    (hkind : c.kind = .emergesWithout target tag)
    (hadm : flowVerdict c = .admissible) :
    findSmugglingPath c.graph tag target = none := by
  unfold flowVerdict at hadm
  split at hadm
  · rename_i hempty
    have hnil : auditFlow c = [] := List.isEmpty_iff.mp hempty
    rw [auditFlow, hkind] at hnil
    dsimp only at hnil
    have hleft1 := (List.append_eq_nil_iff.mp hnil).1
    have hleft := (List.append_eq_nil_iff.mp hleft1).1
    cases hp : findSmugglingPath c.graph tag target with
    | none => rfl
    | some p =>
      rw [hp] at hleft
      cases p with
      | nil => exact False.elim (findSmugglingPathAux_ne_nil c.graph tag (c.graph.ops.length + 1) target hp)
      | cons _ _ => simp at hleft
  · cases hadm

/--
Theorem 2 (Anti-Degeneration — fixes v1's Rule 4 flaw):
Adding an experimenter-set source node that does NOT carry `tag` never creates
a smuggling path for `tag` and never turns an admissible `emergesWithout` claim
into a rejected one.
-/
theorem sourceCarries_add_unrelated_source
    (g : FlowGraph ν σ) (s : SourceNode ν σ) (tag : σ) (hnot : tag ∉ s.carries) (n : ν) :
    sourceCarries { g with sources := s :: g.sources } n tag = sourceCarries g n tag := by
  unfold sourceCarries
  simp only [List.any_cons]
  have hf : decide (s.node = n ∧ tag ∈ s.carries) = false := by
    simp [hnot]
  simp [hf]

theorem findSmugglingPathAux_add_unrelated_source
    (g : FlowGraph ν σ) (s : SourceNode ν σ) (tag : σ) (hnot : tag ∉ s.carries)
    (fuel : Nat) (cur : ν) :
    findSmugglingPathAux { g with sources := s :: g.sources } tag fuel cur =
      findSmugglingPathAux g tag fuel cur := by
  induction fuel generalizing cur with
  | zero => simp [findSmugglingPathAux]
  | succ k ih =>
    unfold findSmugglingPathAux
    rw [sourceCarries_add_unrelated_source g s tag hnot cur]
    have hinj : opInjectsAt { g with sources := s :: g.sources } cur tag = opInjectsAt g cur tag := rfl
    rw [hinj]
    split
    · rfl
    · have hfn :
          (fun op : Op ν σ => op.inputs.findSome? fun inp =>
              (findSmugglingPathAux { g with sources := s :: g.sources } tag k inp).map (· ++ [cur])) =
          (fun op : Op ν σ => op.inputs.findSome? fun inp =>
              (findSmugglingPathAux g tag k inp).map (· ++ [cur])) := by
        funext op
        congr 1
        funext inp
        rw [ih inp]
      exact congrArg (List.findSome? · _) hfn

omit [DecidableEq σ] in
/-- Adding a source node preserves graph completeness (`danglingInputsUpstream = []`). -/
theorem danglingInputsUpstream_add_source_of_empty
    (g : FlowGraph ν σ) (s : SourceNode ν σ) (target : ν)
    (hclean : danglingInputsUpstream g target = []) :
    danglingInputsUpstream { g with sources := s :: g.sources } target = [] := by
  unfold danglingInputsUpstream at hclean ⊢
  rw [List.flatMap_eq_nil_iff] at hclean ⊢
  intro op hop
  have h1 := hclean op hop
  have hanc : ancestors { g with sources := s :: g.sources } target = ancestors g target := rfl
  rw [hanc]
  split at h1
  · rename_i hin
    simp only [hin, ↓reduceIte]
    rw [List.filterMap_eq_nil_iff] at h1 ⊢
    intro inp hinp
    have h2 := h1 inp hinp
    split at h2
    · simp at h2
    · rename_i hdef
      have hdef' : inp ∈ (s :: g.sources).map (·.node) ++ g.ops.map (·.output) := by
        simp only [List.map_cons, List.cons_append, List.mem_cons]
        exact Or.inr (Decidable.byContradiction hdef)
      exact ite_eq_right_iff.mpr (fun hn => False.elim (hn hdef'))
  · rename_i hnot
    simp [hnot]

theorem unrelated_experimenter_source_preserves_emerges_audit
    (c : FlowClaim ν σ) (target : ν) (tag : σ) (s : SourceNode ν σ)
    (hkind : c.kind = .emergesWithout target tag)
    (hnot : tag ∉ s.carries)
    (hclean : danglingInputsUpstream c.graph target = []) :
    auditFlow { c with graph := { c.graph with sources := s :: c.graph.sources } } = auditFlow c := by
  rw [auditFlow, auditFlow, hkind]
  dsimp only
  have hpath :
      findSmugglingPath { c.graph with sources := s :: c.graph.sources } tag target =
        findSmugglingPath c.graph tag target :=
    findSmugglingPathAux_add_unrelated_source c.graph s tag hnot (c.graph.ops.length + 1) target
  have hforgets :
      failedForgetsUpstream { c.graph with sources := s :: c.graph.sources } tag target =
        failedForgetsUpstream c.graph tag target := by
    have hpathIn : ∀ inp,
        findSmugglingPath { c.graph with sources := s :: c.graph.sources } tag inp =
          findSmugglingPath c.graph tag inp :=
      fun inp => findSmugglingPathAux_add_unrelated_source c.graph s tag hnot (c.graph.ops.length + 1) inp
    unfold failedForgetsUpstream tagAncestors
    dsimp only
    congr 1
    funext op
    simp only [hpathIn]
  have hdang :
      danglingInputsUpstream { c.graph with sources := s :: c.graph.sources } target =
        danglingInputsUpstream c.graph target := by
    rw [hclean, danglingInputsUpstream_add_source_of_empty c.graph s target hclean]
  rw [hpath, hforgets, hdang]

omit [DecidableEq ν] in
/--
Theorem 3 (Failed forget never blocks propagation):
Any `forget tag .notShown` or `forget tag .contradicted` operation propagates `tag`
just like a pass-through transformation.
-/
theorem failed_forget_propagates (name : String) (inps : List ν) (out : ν) (tag : σ) :
    opPropagatesTag ⟨name, inps, out, .forget tag .notShown⟩ tag = true ∧
    opPropagatesTag ⟨name, inps, out, .forget tag .contradicted⟩ tag = true := by
  simp [opPropagatesTag, opBlocksTag]

omit [DecidableEq ν] in
/--
Theorem 4 (Proven invariance DOES block propagation):
A `forget tag .shown` operation blocks `tag` from propagating across it.
-/
theorem shown_forget_blocks (name : String) (inps : List ν) (out : ν) (tag : σ) :
    opPropagatesTag ⟨name, inps, out, .forget tag .shown⟩ tag = false := by
  simp [opPropagatesTag, opBlocksTag]

/-- Helper: `findAuthorSuppliedPathAux` never returns `some []`. -/
theorem findAuthorSuppliedPathAux_ne_nil (g : FlowGraph ν σ) (tag : σ) (fuel : Nat) (cur : ν) :
    findAuthorSuppliedPathAux g tag fuel cur ≠ some [] := by
  cases fuel with
  | zero => simp [findAuthorSuppliedPathAux]
  | succ k =>
    unfold findAuthorSuppliedPathAux
    split
    · simp
    · intro h
      have ⟨_, op, _, _, hop, _⟩ := List.findSome?_eq_some_iff.mp h
      have ⟨_, inp, _, _, hinp, _⟩ := List.findSome?_eq_some_iff.mp hop
      cases hm : findAuthorSuppliedPathAux g tag k inp with
      | none => simp [hm] at hinp
      | some p => simp [hm] at hinp

/--
Theorem 5 (Soundness of Policy 3 — `emergesWithExclusion`):
If an `emergesWithExclusion target excludedChannel tag` claim is `admissible`,
then BOTH Alarm 1 (any leak into `excludedChannel`) AND Alarm 2 (any author-supplied
`setByExperimenter`/op path into `target`) are absent.
-/
theorem admissible_policy3_clean_both_alarms
    (c : FlowClaim ν σ) (target excludedChannel : ν) (tag : σ)
    (hkind : c.kind = .emergesWithExclusion target excludedChannel tag)
    (hadm : flowVerdict c = .admissible) :
    findSmugglingPath c.graph tag excludedChannel = none ∧
    findAuthorSuppliedPath c.graph tag target = none := by
  unfold flowVerdict at hadm
  split at hadm
  · rename_i hempty
    have hnil : auditFlow c = [] := List.isEmpty_iff.mp hempty
    rw [auditFlow, hkind] at hnil
    dsimp only at hnil
    have h12 := (List.append_eq_nil_iff.mp (List.append_eq_nil_iff.mp (List.append_eq_nil_iff.mp (List.append_eq_nil_iff.mp hnil).1).1).1).1
    have ha1 := (List.append_eq_nil_iff.mp h12).1
    have ha2 := (List.append_eq_nil_iff.mp h12).2
    constructor
    · cases hp : findSmugglingPath c.graph tag excludedChannel with
      | none => rfl
      | some p =>
        rw [hp] at ha1
        cases p with
        | nil => exact False.elim (findSmugglingPathAux_ne_nil c.graph tag (c.graph.ops.length + 1) excludedChannel hp)
        | cons _ _ => simp at ha1
    · cases hp : findAuthorSuppliedPath c.graph tag target with
      | none => rfl
      | some p =>
        rw [hp] at ha2
        cases p with
        | nil => exact False.elim (findAuthorSuppliedPathAux_ne_nil c.graph tag (c.graph.ops.length + 1) target hp)
        | cons _ _ => simp at ha2
  · cases hadm

/--
Theorem 6 (Soundness of Tier 2 v2.3 — `effectivenessClaim`):
If an `effectivenessClaim` is `admissible`, then:
  (1) `methodNode` has at least one raw upstream `costTag` source (ignoring `.forget`),
  (2) `methodNode ∈ ancestors c.graph evaluationNode`,
  (3) `costLedgerNode = some ledger` with `ledger ≠ methodNode`, `ledger ∈ ancestors evaluationNode`,
      and EVERY raw `costTag` source of `methodNode` (ignoring `.forget`) is metered directly by
      `ledger` without passing through `methodNode` or `controlNode`
      (`src ∈ rawSourceOriginsExcluding c.graph costTag (ledgerExcludedArms methodNode controlNode) ledger`),
  (4) `controlNode = some ctrl` with `ctrl ≠ methodNode`, `methodNode ∉ ancestors ctrl`,
      `ctrl ∉ ancestors methodNode`, `ctrl ∈ ancestors evaluationNode`, and
      `budgetsMatchNumerically methodUsage controlUsage costTag = true`.
-/
theorem admissible_effectiveness_has_control_and_charged_cost
    (c : FlowClaim ν σ) (methodNode evaluationNode : ν)
    (controlNode costLedgerNode : Option ν) (costTag : σ)
    (methodUsage controlUsage : List (ResourceUsage ν σ))
    (hkind : c.kind = .effectivenessClaim methodNode evaluationNode controlNode costLedgerNode costTag methodUsage controlUsage)
    (hadm : flowVerdict c = .admissible) :
    (rawSourceOrigins c.graph costTag methodNode ≠ []) ∧
    (methodNode ∈ ancestors c.graph evaluationNode) ∧
    (∃ ledger,
      costLedgerNode = some ledger ∧
      ledger ≠ methodNode ∧
      ledger ∈ ancestors c.graph evaluationNode ∧
      ∀ src ∈ rawSourceOrigins c.graph costTag methodNode,
        src ∈ rawSourceOriginsExcluding c.graph costTag
          (ledgerExcludedArms methodNode controlNode) ledger) ∧
    (∃ ctrl,
      controlNode = some ctrl ∧
      ctrl ≠ methodNode ∧
      methodNode ∉ ancestors c.graph ctrl ∧
      ctrl ∉ ancestors c.graph methodNode ∧
      ctrl ∈ ancestors c.graph evaluationNode ∧
      budgetsMatchNumerically methodUsage controlUsage costTag = true) := by
  unfold flowVerdict at hadm
  split at hadm
  · rename_i hempty
    have hnil : auditFlow c = [] := List.isEmpty_iff.mp hempty
    rw [auditFlow, hkind] at hnil
    dsimp only at hnil
    have h1 := (List.append_eq_nil_iff.mp hnil).1
    have h2 := (List.append_eq_nil_iff.mp h1).1
    have hctrl := (List.append_eq_nil_iff.mp h2).2
    have h3 := (List.append_eq_nil_iff.mp h2).1
    have hmethUnused := (List.append_eq_nil_iff.mp h3).2
    have h4 := (List.append_eq_nil_iff.mp h3).1
    have hcostMiss := (List.append_eq_nil_iff.mp h4).1
    have hledger := (List.append_eq_nil_iff.mp h4).2
    have hnonempty : rawSourceOrigins c.graph costTag methodNode ≠ [] := by
      intro hzero
      simp [hzero] at hcostMiss
    have hmethInEval : methodNode ∈ ancestors c.graph evaluationNode := by
      split at hmethUnused
      · simp at hmethUnused
      · rename_i hnot
        exact Decidable.byContradiction hnot
    have hledgerExists : ∃ ledger,
        costLedgerNode = some ledger ∧
        ledger ≠ methodNode ∧
        ledger ∈ ancestors c.graph evaluationNode ∧
        ∀ src ∈ rawSourceOrigins c.graph costTag methodNode,
          src ∈ rawSourceOriginsExcluding c.graph costTag
            (ledgerExcludedArms methodNode controlNode) ledger := by
      cases hl : costLedgerNode with
      | none =>
        rw [hl] at hledger
        simp at hledger
      | some ledger =>
        rw [hl] at hledger
        dsimp only at hledger
        have hl1 := (List.append_eq_nil_iff.mp hledger).1
        have hl2 := (List.append_eq_nil_iff.mp hl1).1
        have hl3 := (List.append_eq_nil_iff.mp hl2).1
        have htrivM := (List.append_eq_nil_iff.mp hl3).1
        have hunusedL := (List.append_eq_nil_iff.mp hl2).2
        have huncharged := (List.append_eq_nil_iff.mp hl1).2
        have hneM : ledger ≠ methodNode := by
          split at htrivM
          · simp at htrivM
          · assumption
        have hlInEval : ledger ∈ ancestors c.graph evaluationNode := by
          split at hunusedL
          · simp at hunusedL
          · rename_i hnot
            exact Decidable.byContradiction hnot
        have hallCharged : ∀ src ∈ rawSourceOrigins c.graph costTag methodNode,
            src ∈ rawSourceOriginsExcluding c.graph costTag
              (ledgerExcludedArms methodNode controlNode) ledger := by
          intro src hsrc
          have hmemAll : src ∈ (match controlNode with
              | some ctrl => (rawSourceOrigins c.graph costTag methodNode ++ rawSourceOrigins c.graph costTag ctrl).eraseDups
              | none => rawSourceOrigins c.graph costTag methodNode) := by
            cases controlNode with
            | none => exact hsrc
            | some ctrl =>
              rw [List.mem_eraseDups]
              exact List.mem_append_left _ hsrc
          have hfm := List.filterMap_eq_nil_iff.mp huncharged src hmemAll
          split at hfm
          · simp at hfm
          · rename_i hnot
            exact Decidable.byContradiction hnot
        exact ⟨ledger, rfl, hneM, hlInEval, hallCharged⟩
    have hctrlExists : ∃ ctrl,
        controlNode = some ctrl ∧
        ctrl ≠ methodNode ∧
        methodNode ∉ ancestors c.graph ctrl ∧
        ctrl ∉ ancestors c.graph methodNode ∧
        ctrl ∈ ancestors c.graph evaluationNode ∧
        budgetsMatchNumerically methodUsage controlUsage costTag = true := by
      cases hc : controlNode with
      | none =>
        rw [hc] at hctrl
        simp at hctrl
      | some ctrl =>
        rw [hc] at hctrl
        dsimp only at hctrl
        have hc0 := (List.append_eq_nil_iff.mp hctrl).1
        have hc1 := (List.append_eq_nil_iff.mp hc0).1
        have hc2 := (List.append_eq_nil_iff.mp hc1).1
        have hc3 := (List.append_eq_nil_iff.mp hc2).1
        have hself := (List.append_eq_nil_iff.mp hc3).1
        have hdep := (List.append_eq_nil_iff.mp hc3).2
        have hunused := (List.append_eq_nil_iff.mp hc2).2
        have hbud := (List.append_eq_nil_iff.mp hc1).2
        have hne : ctrl ≠ methodNode := by
          split at hself
          · simp at hself
          · assumption
        have hnotDep : methodNode ∉ ancestors c.graph ctrl ∧ ctrl ∉ ancestors c.graph methodNode := by
          split at hdep
          · simp at hdep
          · rename_i hcond
            have hfalse : (methodNode ∈ ancestors c.graph ctrl || ctrl ∈ ancestors c.graph methodNode) = false := by
              cases hb : (methodNode ∈ ancestors c.graph ctrl || ctrl ∈ ancestors c.graph methodNode) with
              | false => rfl
              | true =>
                exfalso
                apply hcond
                simp [hne, hb]
            simp only [Bool.or_eq_false_iff, decide_eq_false_iff_not] at hfalse
            exact hfalse
        have hctrlInEval : ctrl ∈ ancestors c.graph evaluationNode := by
          split at hunused
          · simp at hunused
          · rename_i hnot
            exact Decidable.byContradiction hnot
        have hmatch : budgetsMatchNumerically methodUsage controlUsage costTag = true := by
          split at hbud
          · simp at hbud
          · split at hbud
            · assumption
            · simp at hbud
        exact ⟨ctrl, rfl, hne, hnotDep.1, hnotDep.2, hctrlInEval, hmatch⟩
    exact ⟨hnonempty, hmethInEval, hledgerExists, hctrlExists⟩
  · cases hadm

/--
Theorem 7a (Equivalence of `admissible` between 4-state `epistemicVerdict` and legacy `flowVerdict`):
A claim is `EpistemicVerdict.admissible` if and only if it is `FlowVerdict.admissible`.
In particular, an `outOfScope` claim is never `admissible` under either verdict.
-/
theorem epistemicVerdict_admissible_iff_flowVerdict_admissible (c : FlowClaim ν σ) :
    epistemicVerdict c = .admissible ↔ flowVerdict c = .admissible := by
  cases hk : c.kind with
  | outOfScope r =>
    simp [epistemicVerdict, flowVerdict, auditFlow, hk]
  | emergesWithout _ _
  | emergesWithExclusion _ _ _
  | independentConvergence _ _ _
  | uniqueRecovery _ _
  | conditionalFlow _ _
  | effectivenessClaim _ _ _ _ _ _ _ =>
    unfold epistemicVerdict flowVerdict
    rw [hk]
    dsimp only
    cases hempty : (auditFlow c).isEmpty with
    | true => simp
    | false =>
      simp only [Bool.false_eq_true, ↓reduceIte]
      cases (auditFlow c).any FlowFinding.isContradiction <;> simp

/--
Theorem 7b (Characterization of `EpistemicVerdict.outOfScope`):
`epistemicVerdict c = .outOfScope` if and only if `c.kind` is `.outOfScope r` for some reason `r`.
-/
theorem epistemicVerdict_outOfScope_iff (c : FlowClaim ν σ) :
    epistemicVerdict c = .outOfScope ↔ ∃ r, c.kind = .outOfScope r := by
  constructor
  · intro h
    cases hk : c.kind with
    | outOfScope r => exact ⟨r, rfl⟩
    | emergesWithout _ _
    | emergesWithExclusion _ _ _
    | independentConvergence _ _ _
    | uniqueRecovery _ _
    | conditionalFlow _ _
    | effectivenessClaim _ _ _ _ _ _ _ =>
      unfold epistemicVerdict at h
      rw [hk] at h
      dsimp only at h
      split at h
      · cases h
      · split at h <;> cases h
  · rintro ⟨r, hr⟩
    simp [epistemicVerdict, hr]

/--
Theorem 7c (Characterization of `EpistemicVerdict.rejected`):
`epistemicVerdict c = .rejected` if and only if `c` is not `outOfScope` and `auditFlow c`
contains a direct structural/empirical contradiction finding (`f.isContradiction = true`).
-/
theorem epistemicVerdict_rejected_iff (c : FlowClaim ν σ) :
    epistemicVerdict c = .rejected ↔
    (∀ r, c.kind ≠ .outOfScope r) ∧ ∃ f ∈ auditFlow c, f.isContradiction = true := by
  cases hk : c.kind with
  | outOfScope r =>
    constructor
    · intro h
      simp [epistemicVerdict, hk] at h
    · rintro ⟨hnot, _⟩
      exact absurd rfl (hnot r)
  | emergesWithout _ _
  | emergesWithExclusion _ _ _
  | independentConvergence _ _ _
  | uniqueRecovery _ _
  | conditionalFlow _ _
  | effectivenessClaim _ _ _ _ _ _ _ =>
    unfold epistemicVerdict
    rw [hk]
    dsimp only
    constructor
    · intro h
      refine ⟨(fun _ hEq => by cases hEq), ?_⟩
      cases hempty : (auditFlow c).isEmpty with
      | true => simp [hempty] at h
      | false =>
        simp only [hempty, Bool.false_eq_true, ↓reduceIte] at h
        cases hany : (auditFlow c).any FlowFinding.isContradiction with
        | false => simp [hany] at h
        | true => exact List.any_eq_true.mp hany
    · rintro ⟨_, f, hf, hcontra⟩
      have hne : (auditFlow c).isEmpty = false := by
        cases hl : auditFlow c with
        | nil => rw [hl] at hf; cases hf
        | cons _ _ => rfl
      have hany : (auditFlow c).any FlowFinding.isContradiction = true :=
        List.any_eq_true.mpr ⟨f, hf, hcontra⟩
      simp [hne, hany]

end EpistemicLedger.OperationFlow
