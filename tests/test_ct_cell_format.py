"""CT cell format compatibility: bare `Cnnnnn` (KB <= kb-2026.11.25) and
`(SHORTNAME) Cnnnnn` (KB S-CT batch, pedia 44fb042), '; '-joined when multiple.
Synthetic inputs only, so CI (old-KB submodule) exercises the new format too."""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.build_meta import _split_ct, _variables
from scripts.spec_loader import SpecLoader, ct_code_of
from server.validator import validate


@pytest.mark.parametrize("cell,code", [
    ("C66769", "C66769"),
    ("(AESEV) C66769", "C66769"),
    ("(NY) C66742", "C66742"),
    ("(EGTESTCD) C71153", "C71153"),
    ("  (SEX) C66731  ", "C66731"),
    ("", None),
    ("*", None),
    ("AE", None),
    ("MedDRA", None),
    ("ISO 8601 datetime or interval", None),
    ("(AESEV)", None),
    ("(AESEV) C66769 extra", None),
    ("C66769; C66790", None),  # multi-codelist cell is not ONE code
    ("(NCOMPLT) C66727; (PROTMLST) C114118", None),
])
def test_ct_code_of(cell, code):
    assert ct_code_of(cell) == code


def test_split_ct_both_formats():
    assert _split_ct("C66769") == (["C66769"], [])
    assert _split_ct("(AESEV) C66769") == (["C66769"], [])
    assert _split_ct("(NCOMPLT) C66727; (PROTMLST) C114118; (OTHEVENT) C150811") == (
        ["C66727", "C114118", "C150811"], [])
    assert _split_ct("C85494; C128684") == (["C85494", "C128684"], [])
    assert _split_ct("MedDRA") == ([], ["MedDRA"])
    assert _split_ct("ISO 8601 duration") == ([], ["ISO 8601 duration"])
    assert _split_ct("") == ([], [])
    # '*' is an open-CT marker, never a dictionary token
    assert _split_ct("*") == ([], [])
    # domain code is dropped only when it is THIS variable's literal
    assert _split_ct("AE", domain_literal="AE") == ([], [])
    assert _split_ct("AE") == ([], ["AE"])
    assert _split_ct("VS", domain_literal="AE") == ([], ["VS"])
    assert _split_ct("MedDRA", domain_literal="AE") == ([], ["MedDRA"])


def test_variables_drop_star_and_domain_literal(tmp_path):
    (tmp_path / "domains" / "XX").mkdir(parents=True)
    (tmp_path / "domains" / "XX" / "spec.md").write_text(_SPEC.format(sev="(AESEV) C66769")
        + "\n### XXTERM\n- **Order:** 5\n- **Controlled Terms:** MedDRA\n"
        + "\n### XXOTHER\n- **Order:** 6\n- **Controlled Terms:** XX\n", encoding="utf-8")
    vs = {v["name"]: v for v in _variables(SpecLoader(tmp_path).domains["XX"])}
    assert (vs["XXSEV"]["ct_codes"], vs["XXSEV"]["ct_dict"]) == (["C66769"], [])
    assert vs["XXCAT"]["ct_dict"] == []            # '*'
    assert vs["DOMAIN"]["ct_dict"] == []           # literal domain code
    assert vs["XXTERM"]["ct_dict"] == ["MedDRA"]   # real dictionary token kept
    assert vs["XXOTHER"]["ct_dict"] == ["XX"]      # same text, not DOMAIN -> kept
    assert vs["XXMULTI"]["ct_codes"] == ["C66769", "C66742"]


_SPEC = """# XX — Test Events

> Class: Events | Structure: One record per event

### XXSEV
- **Order:** 1
- **Controlled Terms:** {sev}

### XXCAT
- **Order:** 2
- **Controlled Terms:** *

### DOMAIN
- **Order:** 3
- **Controlled Terms:** XX

### XXMULTI
- **Order:** 4
- **Controlled Terms:** (AESEV) C66769; (NY) C66742
"""

_TERM = """# Test terminology

## Severity/Intensity Scale (C66769)

Extensible: No

| Code | CDISC Submission Value |
|---|---|
| C41338 | MILD |
| C41339 | MODERATE |
"""


@pytest.mark.parametrize("sev", ["C66769", "(AESEV) C66769"])
def test_validator_checks_ct_in_both_formats(tmp_path, sev):
    (tmp_path / "domains" / "XX").mkdir(parents=True)
    (tmp_path / "domains" / "XX" / "spec.md").write_text(_SPEC.format(sev=sev), encoding="utf-8")
    (tmp_path / "terminology").mkdir()
    (tmp_path / "terminology" / "t.md").write_text(_TERM, encoding="utf-8")
    loader = SpecLoader(tmp_path)
    assert loader.is_ct_code(sev)

    df = pd.DataFrame({
        "DOMAIN": ["XX", "XX"], "XXSEV": ["MILD", "BOGUS"],
        "XXCAT": ["A", "B"], "XXMULTI": ["MILD", "BOGUS"],
    })
    ct = [f for f in validate(df, "XX", loader).findings if f.rule == "CT"]
    assert len(ct) == 1, ct
    f = ct[0]
    assert (f.severity, f.variable) == ("ERROR", "XXSEV")
    assert "codelist C66769 (Severity/Intensity Scale)" in f.message
    assert "BOGUS" in f.message and "(AESEV)" not in f.message
