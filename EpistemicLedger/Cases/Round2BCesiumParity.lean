import EpistemicLedger.AuditRules

/-
Blind record: "Numerical Studies of Ground State Atomic Parity Violation
Measurements in Cesium" (paper/paper.txt). Two abstract claims.
-/
namespace EpistemicLedger.Cases.Round2B.CesiumParity

inductive Dep where
  /-- Sec. III, Eqs. (1)-(3): "we numerically integrate the equations of motion
  of the state vector ... where ψg is the 6s,(F,m)=(3,3) state, and ψe is the
  6s,(F,m)=(4,3) state". Model chosen by the authors. -/
  | twoStateEquationsOfMotion
  /-- Sec. III, Eq. (5): "the interaction Hamiltonian describing the magnetic
  dipole interaction is of the form Vm = ..." (from Ref. [15]). -/
  | magneticDipoleInteractionForm
  /-- Sec. III: "Epnc = iκ 1.82 × 10−11 ea0 ... The value of κ = 0.117 was
  derived from the 1997 APV measurements of Wood et al. [1]". External input
  read off cesium by an earlier measurement. -/
  | epncValueFromKappa
  /-- Sec. III: "an electric field amplitude of erf_z = 251 kV/m, as calculated
  from numerical simulations of our rf cavity with 1 Watt of power delivered to
  each of the four inputs". -/
  | rfFieldAmplitudeFromCavityModel
  /-- Sec. III: "In the computed spectra shown in the following sections, we
  have set the field amplitude hrf_z-component equal to zero." -/
  | hzSetToZero
  /-- Sec. III, Fig. 2: effusive-beam distribution "f(v) = 2β²v³e^(−βv²) ...
  T = 443 K"; velocity and position "chosen randomly ... using a Monte Carlo
  technique". -/
  | effusiveVelocityDistribution
  /-- Sec. III: "We follow the evolution of 20,000 atoms to generate each data
  point within a spectrum." -/
  | monteCarloAtomSample
  /-- Sec. IV.A: "we treated the static magnetic field as if it were perfectly
  uniform throughout the Raman region and rf cavity" (gradients probed in Fig. 6). -/
  | uniformStaticField
  /-- Sec. IV, Figs. 3-10: the scanned values of By, Bx, Δx, Δy, θy and the
  differential ac Stark shift (e.g. "Bx = 0.1 mG", "Δx = 0.1 µm", "2 to 24 kHz"). -/
  | scannedParameterValues
  /-- Sec. IV.D: polarizability from "the frequency-dependent polarizability
  expression given by Milroy, Safronova, and Clark [21]", with "√(P1P2) = 10 mW"
  and "a laser detuning of 250 MHz below the 6P3/2, F'=2 excited state". -/
  | starkShiftModelSettings
  /-- Sec. IV.A / Fig. 5: "in order to reduce the effect of Vm to less than 10%
  of the Vpnc interaction"; "±10% tolerance bands around the reference". -/
  | tenPercentTolerance
  deriving DecidableEq, Repr

inductive Hyp where
  /-- Sec. III: the equations of motion are "derived from the Schrödinger
  Equation [16, 17]"; "We previously discussed these equations of motion in
  detail in Ref. [15]" (for this same apparatus). -/
  | twoStateDynamicsValidForApparatus
  /-- Sec. III: hrf_z is "as small as ∼ 2 × 10−4 A/m in our latest simulation,
  and decreasing significantly with each decrease in the computational grid
  spacing ... we can only report this value as an upper bound on hrf_z."
  Openly stated as not settled. -/
  | hzNegligibleInRealCavity
  /-- Sec. IV.D: "The spectra that we have collected to this point in the
  laboratory are much more complex than the relatively simple spectra
  calculated here." Limits for the real apparatus need the model to capture
  its background; the paper does not validate the model against lab data and
  does not state that the limits rest on that. -/
  | modelCapturesApparatusBackground
  deriving DecidableEq, Repr

def claim1 : Claim Dep Hyp where
  statement := "We report results of numerical simulations of an ongoing measurement designed to measure the electric dipole (E1) transition moment between hyperfine components of the ground state of atomic cesium."
  kind := .conditional
  used :=
    [ ⟨.twoStateEquationsOfMotion, .setByExperimenter⟩,
      ⟨.magneticDipoleInteractionForm, .setByExperimenter⟩,
      ⟨.epncValueFromKappa, .measured⟩,
      ⟨.rfFieldAmplitudeFromCavityModel, .setByExperimenter⟩,
      ⟨.hzSetToZero, .setByExperimenter⟩,
      ⟨.effusiveVelocityDistribution, .setByExperimenter⟩,
      ⟨.monteCarloAtomSample, .setByExperimenter⟩,
      ⟨.uniformStaticField, .setByExperimenter⟩,
      ⟨.scannedParameterValues, .setByExperimenter⟩,
      ⟨.starkShiftModelSettings, .setByExperimenter⟩ ]
  declared :=
    [ .twoStateEquationsOfMotion, .magneticDipoleInteractionForm, .epncValueFromKappa,
      .rfFieldAmplitudeFromCavityModel, .hzSetToZero, .effusiveVelocityDistribution,
      .monteCarloAtomSample, .uniformStaticField, .scannedParameterValues,
      .starkShiftModelSettings ]
  forgets := []
  hypotheses :=
    [ ⟨.twoStateDynamicsValidForApparatus, .discharged⟩,
      ⟨.hzNegligibleInRealCavity, .bet⟩ ]
  declaredBets := [.hzNegligibleInRealCavity]

def claim2 : Claim Dep Hyp where
  statement := "The results of these simulations help place limits on the experimental parameters, and help guide the future experimental procedures."
  kind := .conditional
  used :=
    [ ⟨.twoStateEquationsOfMotion, .setByExperimenter⟩,
      ⟨.magneticDipoleInteractionForm, .setByExperimenter⟩,
      ⟨.epncValueFromKappa, .measured⟩,
      ⟨.rfFieldAmplitudeFromCavityModel, .setByExperimenter⟩,
      ⟨.hzSetToZero, .setByExperimenter⟩,
      ⟨.effusiveVelocityDistribution, .setByExperimenter⟩,
      ⟨.monteCarloAtomSample, .setByExperimenter⟩,
      ⟨.uniformStaticField, .setByExperimenter⟩,
      ⟨.scannedParameterValues, .setByExperimenter⟩,
      ⟨.starkShiftModelSettings, .setByExperimenter⟩,
      ⟨.tenPercentTolerance, .setByExperimenter⟩ ]
  declared :=
    [ .twoStateEquationsOfMotion, .magneticDipoleInteractionForm, .epncValueFromKappa,
      .rfFieldAmplitudeFromCavityModel, .hzSetToZero, .effusiveVelocityDistribution,
      .monteCarloAtomSample, .uniformStaticField, .scannedParameterValues,
      .starkShiftModelSettings, .tenPercentTolerance ]
  forgets := []
  hypotheses :=
    [ ⟨.twoStateDynamicsValidForApparatus, .discharged⟩,
      ⟨.hzNegligibleInRealCavity, .bet⟩,
      ⟨.modelCapturesApparatusBackground, .bet⟩ ]
  declaredBets := [.hzNegligibleInRealCavity]

#eval audit claim1
#eval verdictV1 claim1
#eval rule4Fired claim1
#eval audit claim2
#eval verdictV1 claim2
#eval rule4Fired claim2

theorem claim1_v1 : verdictV1 claim1 = .passed := by decide
theorem claim1_rule4 : rule4Fired claim1 = false := by decide
theorem claim2_v1 : verdictV1 claim2 = .passedWithNotes := by decide
theorem claim2_rule4 : rule4Fired claim2 = false := by decide

end EpistemicLedger.Cases.Round2B.CesiumParity
