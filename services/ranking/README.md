# Ranking Service

Purpose:

- combine semantic similarity with explicit candidate features
- compute candidate relevance scores
- generate shortlist outputs

Suggested implementation:

- initial weighted scoring
- later `LightGBM` or `XGBoost`
- explainable component-level score breakdown
