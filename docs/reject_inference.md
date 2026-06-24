# Reject inference (under grade)

Reject inference is the credit-risk practice of recovering information about the
applicants a prior policy **declined** — whose repayment outcomes are never
observed — so a new model is not trained on the accepted book alone. CLDD ships
four classic methods, but **only as `Corrector`s graded against planted truth**,
not as a toolkit to run on real data. That distinction is the whole point: the
harness can score each method against the declined applicants' *known* labels,
which real data does not have. There is deliberately no `run_reject_inference(df)`
entry point — exposing a method for users' real data would remove the oracle that
makes the grade meaningful.

## The four methods (v1)

All four route their constructed training set through the same
`model_pd.train_pd_model` the naive lever uses, so a comparison over {naive, IPW,
these four} holds the downstream PD model fixed and varies only the training-set
construction.

| Method | Construction |
|---|---|
| `reclassification` | hard-cutoff: pseudo-label the declined fold by thresholding the KGB score, add those rows to training |
| `augmentation` | score-band reweighting: reweight *accepted* rows by the inverse of their KGB-score band's empirical acceptance rate (no declined rows added) |
| `fuzzy_augmentation` | each declined applicant enters twice — good (weight `1−p`) and bad (weight `p`) — using the KGB-predicted PD `p`; no hard label |
| `parcelling` | bin the declined fold by KGB score; assign bad labels at the accepted band rate scaled up by a factor, drawn from a seeded RNG |

`augmentation` is **not** a rename of {class}`~cldd.correctors.IPWReweightCorrector`:
the IPW lever fits a continuous propensity *classifier* `P(approved | features)`,
while augmentation bins by the KGB risk *score* and uses each band's empirical
acceptance rate (the classic credit-scoring construction). A test asserts the two
weight vectors differ.

## Integrity invariant

A reject-inference corrector may use the declined applicants' **features** but
never their planted `true_default` at fit time — the same no-leakage discipline
the naive lever already follows (it fits approved rows only). This is enforced
*structurally*: a method's `_augment` step is handed the feature matrix, the
**approved** rows' observable labels, and a KGB model, but never the declined
labels. A parametrized test additionally corrupts every declined label and asserts
the fitted model is unchanged.

## What the numbers certify

Declined-cohort calibration is measured on a **held-out fold** of the declines
(`config.RI_EVAL_FRACTION`, default one half): a method may pseudo-label one fold
for training and is graded on the *other* fold it never saw. So a number certifies
**recovery of this declined population's labels on held-out applicants**, not
generalization of the pseudo-labeling rule to a fresh cohort (a different claim).
`scripts/run_reject_inference.py` writes the full grid to
`artifacts/reject_inference_frontier.csv`.

## Honest framing

Read the frontier honestly. Reject-inference lift over the naive detector is
**modest at best and can be negative**: under selection-at-random there is nothing
to correct, and as selection severity rises the harness's **unobserved confounder**
defeats every observational method — for the same structural reason inverse-
propensity weighting fails — until at full severity none of them recovers
declined-cohort calibration. The one honest exception worth stating: **parcelling**
reliably *reduces* declined-ECE once selection is non-random — it beats the naive
detector in every mid-to-high-severity run, in both synthetic worlds — but never by
enough to clear the calibration target. A directional improvement, not a fix. This
matches the literature: Kozodoi et al. (2025) find reject inference's profit lift is
modest and that correcting the **evaluation** bias is the more valuable lever. CLDD's
contribution is therefore the *validated comparison against ground truth*: a method may
nudge calibration, but the frontier — where the confounder wins — is the real finding.

*Conceptual anchor (a pointer for later, not a section): the reweighting family is
the importance-sampling dual of rejection sampling against the selection policy,
and both fail at the positivity boundary — so the operating frontier is where the
inverse map stops existing.*
