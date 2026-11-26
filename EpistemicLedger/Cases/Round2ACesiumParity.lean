import EpistemicLedger.AuditRules

/-
Blind record for paper/paper.txt:
"Numerical Studies of Ground State Atomic Parity Violation Measurements in Cesium".

The record says what the two abstract sentences lean on, as far as the paper
itself states it. It does not say whether the sentences are true.
-/
namespace EpistemicLedger.Cases.Round2A.CesiumParity

inductive Dep where
  /-- Sec. II, Fig. 1(a): "In this section, we describe the experimental set-up
  used in our prior work [15], setting the stage for the discussions of the
  simulations that follow." The measurement scheme that is simulated. -/
  | measurementSchemeOfRef15
  /-- Sec. III, Eqs. (1)-(3): "we numerically integrate the equations of motion
  of the state vector" for the two states (F, m) = (3, 3) and (4, 3). -/
  | twoLevelEquationsOfMotion
  /-- Sec. III, Eq. (5): "We showed in Ref. [15] that the interaction
  Hamiltonian describing the magnetic dipole interaction is of the form".
  Sec. IV.A: "This behavior is completely consistent with the interaction term
  Vm given in Eq. (5)". -/
  | magneticDipoleInteractionForm
  /-- Sec. III: "The transition dipole moment for this ground state transition
  has been calculated in the Random Phase Approximation (RPA) [18, 19]"; the
  value used is Epnc = iκ 1.82 × 10−11 ea0. A calculated input taken from
  other work: neither a knob nor a reading, tagged `setByExperimenter` as the
  nearer of the two. -/
  | epncTheoryValue
  /-- Sec. III: "The value of κ = 0.117 was derived from the 1997 APV
  measurements of Wood et al. [1], as reported in Refs. [18] and [19]." -/
  | kappaFromBoulder1997
  /-- Sec. III, Fig. 1(c): rf electric field amplitude 251 kV/m "as calculated
  from numerical simulations of our rf cavity with 1 Watt of power delivered to
  each of the four inputs", with J0 and J1 radial profiles of the TM010 mode. -/
  | rfCavityFieldModel
  /-- Sec. III: "In the computed spectra shown in the following sections, we
  have set the field amplitude [h_z^rf]-component equal to zero." -/
  | hzRfSetToZero
  /-- Sec. III, Eq. (5): the transverse-field term of Vm is
  (h_x B_x + h_y B_y) / B_z. B_z appears only in Eq. (5); the value used in
  the simulations is not given anywhere in the text. -/
  | longitudinalBiasFieldBzValue
  /-- Sec. III, Fig. 2: "The velocity v (magnitude and direction) and initial
  position (x, y) of each atom are chosen randomly from the distribution for
  the apertured thermal atomic beam using a Monte Carlo technique."; "We follow
  the evolution of 20,000 atoms to generate each data point within a
  spectrum." -/
  | monteCarloThermalBeamSampling
  /-- Sec. IV.A: "For each of the simulations discussed above, we treated the
  static magnetic field as if it were perfectly uniform throughout the Raman
  region and rf cavity." -/
  | uniformStaticFieldTreatment
  /-- Sec. IV.D, Eqs. (6)-(8), Figs. 9-10: "we treat the differential shift as
  an additional detuning of the Raman transition"; polarizabilities "evaluated
  at a laser detuning of 250 MHz". -/
  | acStarkShiftModel
  /-- Sec. IV.A, Fig. 5: "in order to reduce the effect of Vm to less than 10%
  of the Vpnc interaction"; Fig. 8 caption: "±10% tolerance band around the
  reference". -/
  | tenPercentToleranceCriterion
  /-- Sec. IV.A, Figs. 4, 5, 8: "we plot in Fig. 5 the amplitude ∆P at zero
  detuning versus the product By ∆x". The limits are read off the amplitude at
  zero detuning, not off the shape of the spectrum. -/
  | zeroDetuningAmplitudeAsMeasure
  /-- Sec. IV.A: "for a transverse static magnetic field of 0.1 mG, the
  displacement of the atomic beam from the cavity axis must be less than
  60 nm". Sec. IV.C: "if we can reduce By to below 0.1 mG, the cavity rotation
  angle θy must be kept below approximately 1.6 mrad". -/
  | assumedResidualTransverseField
  deriving DecidableEq, Repr

inductive Hyp where
  /-- Sec. III, Eq. (5): "We showed in Ref. [15] that the interaction
  Hamiltonian describing the magnetic dipole interaction is of the form".
  Discharged by the paper's reference to its earlier work. -/
  | effectiveM1InteractionHolds
  /-- Sec. III: "The actual cavity, however, deviates from this ideal case";
  "so we can only report this value as an upper bound"; "While the
  [h_z^rf]-component may be sufficiently reduced". The simulations take the
  longitudinal rf magnetic field of the real cavity to be negligible. -/
  | hzRfNegligibleInRealCavity
  /-- Sec. IV.D: "The spectra that we have collected to this point in the
  laboratory are much more complex than the relatively simple spectra
  calculated here."; "identify possible causes for the complexity of the
  spectra". No comparison of calculated and measured spectra is shown, so that
  the model describes the real apparatus is unchecked. -/
  | simulationModelRepresentsLaboratoryApparatus
  /-- Sec. I: "This value of the anapole moment, however, is in tension with
  the constraints on the weak meson-nucleon coupling constants"; "either
  confirm the value reported by the Boulder group or to provide a new
  determination". The reference amplitude that the 10% limits are measured
  against assumes this value. -/
  | assumedEpncMagnitudeHoldsForCesium
  deriving DecidableEq, Repr

/-- Abstract, sentence 1. Worded as a report of what was done; nothing in it
says that something arises by itself. -/
def claim1 : Claim Dep Hyp where
  statement := "We report results of numerical simulations of an ongoing measurement designed to measure the electric dipole (E1) transition moment between hyperfine components of the ground state of atomic cesium."
  kind := .conditional
  used :=
    [ ⟨.measurementSchemeOfRef15, .setByExperimenter⟩,
      ⟨.twoLevelEquationsOfMotion, .setByExperimenter⟩,
      ⟨.magneticDipoleInteractionForm, .setByExperimenter⟩,
      ⟨.epncTheoryValue, .setByExperimenter⟩,
      ⟨.kappaFromBoulder1997, .measured⟩,
      ⟨.rfCavityFieldModel, .setByExperimenter⟩,
      ⟨.hzRfSetToZero, .setByExperimenter⟩,
      ⟨.longitudinalBiasFieldBzValue, .setByExperimenter⟩,
      ⟨.monteCarloThermalBeamSampling, .setByExperimenter⟩,
      ⟨.uniformStaticFieldTreatment, .setByExperimenter⟩,
      ⟨.acStarkShiftModel, .setByExperimenter⟩ ]
  -- Everything above is stated in the paper except the value of B_z.
  declared :=
    [ .measurementSchemeOfRef15,
      .twoLevelEquationsOfMotion,
      .magneticDipoleInteractionForm,
      .epncTheoryValue,
      .kappaFromBoulder1997,
      .rfCavityFieldModel,
      .hzRfSetToZero,
      .monteCarloThermalBeamSampling,
      .uniformStaticFieldTreatment,
      .acStarkShiftModel ]
  -- The reported results include the field-gradient runs (Fig. 6), so no
  -- dependency is dropped from this sentence.
  forgets := []
  hypotheses :=
    [ ⟨.effectiveM1InteractionHolds, .discharged⟩,
      ⟨.hzRfNegligibleInRealCavity, .bet⟩,
      ⟨.simulationModelRepresentsLaboratoryApparatus, .bet⟩ ]
  declaredBets :=
    [ .hzRfNegligibleInRealCavity,
      .simulationModelRepresentsLaboratoryApparatus ]

/-- Abstract, last sentence. Worded as "given these simulations, limits and
guidance follow"; nothing in it says that something arises by itself. -/
def claim2 : Claim Dep Hyp where
  statement := "The results of these simulations help place limits on the experimental parameters, and help guide the future experimental procedures."
  kind := .conditional
  used :=
    [ ⟨.measurementSchemeOfRef15, .setByExperimenter⟩,
      ⟨.twoLevelEquationsOfMotion, .setByExperimenter⟩,
      ⟨.magneticDipoleInteractionForm, .setByExperimenter⟩,
      ⟨.epncTheoryValue, .setByExperimenter⟩,
      ⟨.kappaFromBoulder1997, .measured⟩,
      ⟨.rfCavityFieldModel, .setByExperimenter⟩,
      ⟨.hzRfSetToZero, .setByExperimenter⟩,
      ⟨.longitudinalBiasFieldBzValue, .setByExperimenter⟩,
      ⟨.monteCarloThermalBeamSampling, .setByExperimenter⟩,
      ⟨.uniformStaticFieldTreatment, .setByExperimenter⟩,
      ⟨.acStarkShiftModel, .setByExperimenter⟩,
      ⟨.tenPercentToleranceCriterion, .setByExperimenter⟩,
      ⟨.zeroDetuningAmplitudeAsMeasure, .setByExperimenter⟩,
      ⟨.assumedResidualTransverseField, .setByExperimenter⟩ ]
  -- Everything above is stated in the paper except the value of B_z, which
  -- the limit on the product By ∆x scales with (Eq. 5).
  declared :=
    [ .measurementSchemeOfRef15,
      .twoLevelEquationsOfMotion,
      .magneticDipoleInteractionForm,
      .epncTheoryValue,
      .kappaFromBoulder1997,
      .rfCavityFieldModel,
      .hzRfSetToZero,
      .monteCarloThermalBeamSampling,
      .uniformStaticFieldTreatment,
      .acStarkShiftModel,
      .tenPercentToleranceCriterion,
      .zeroDetuningAmplitudeAsMeasure,
      .assumedResidualTransverseField ]
  -- Sec. IV.A, Fig. 6: with gradients of ±0.4 G/m "the value of ∆P at zero
  -- detuning (∆ = 0) remains nearly unchanged" (shown for By0 = 0 and
  -- ∆x = 0.1 µm only; the spectral shape does change). The limits are read
  -- off ∆P at zero detuning, so for them the evidence is `shown`.
  forgets := [⟨.uniformStaticFieldTreatment, .shown⟩]
  hypotheses :=
    [ ⟨.effectiveM1InteractionHolds, .discharged⟩,
      ⟨.hzRfNegligibleInRealCavity, .bet⟩,
      ⟨.simulationModelRepresentsLaboratoryApparatus, .bet⟩,
      ⟨.assumedEpncMagnitudeHoldsForCesium, .bet⟩ ]
  declaredBets :=
    [ .hzRfNegligibleInRealCavity,
      .simulationModelRepresentsLaboratoryApparatus,
      .assumedEpncMagnitudeHoldsForCesium ]

#eval audit claim1
#eval verdictV1 claim1
#eval rule4Fired claim1

#eval audit claim2
#eval verdictV1 claim2
#eval rule4Fired claim2

theorem claim1_v1 : verdictV1 claim1 = .passedWithNotes := by decide
theorem claim1_rule4 : rule4Fired claim1 = false := by decide

theorem claim2_v1 : verdictV1 claim2 = .passedWithNotes := by decide
theorem claim2_rule4 : rule4Fired claim2 = false := by decide

end EpistemicLedger.Cases.Round2A.CesiumParity
