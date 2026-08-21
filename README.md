# CCS Screening & Investment Decision Framework

Streamlit application for the MSc CCS Screening and Investment Decision Framework.

## Phase-1 rule
Fields that fail the **Phase-1 hard cut-off screening** are permanently eliminated. They are not available for selection or processing anywhere in Phase 2.

## Phase-2 rule
Only fields that passed Phase 1 can enter Phase 2. A field that later fails the **Phase-2 CAPEX/OPEX gate** may still be selected for subsequent economic analysis, consistent with the framework design.

## Run locally
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Included files
- `app.py` — Streamlit user interface
- `ccs_engine.py` — reference parsing, Phase-1 screening, economic calculations and sensitivity analysis
- `requirements.txt` — dependencies
- `test_ccs_framework.py` — offline regression tests
- `.gitignore` — standard Python/Streamlit ignores
