"""Reproduce the open-source iXBRL tool check behind slide 12.

Setup:
  pip install ixbrlparse ixbrl-parse
  git clone --depth 1 https://github.com/ONSBigData/parsing_company_accounts.git ons
Run:
  python tool-comparison-check.py
Sample: 379 real Companies House filings (205 iXBRL, 174 XML), hand-picked by ONS,
made-up dates 2016-2018. Not a random sample.
"""
import collections, glob, re, time

from ixbrlparse import IXBRL
from lxml import etree as ET
from ixbrl_parse.ixbrl import parse as ixbrl_parse_parse

DIR = "ons/example_data_XBRL_iXBRL"
html = sorted(glob.glob(f"{DIR}/*.html"))
xml = sorted(glob.glob(f"{DIR}/*.xml"))
dash = re.compile(r"^\s*[-\u2013\u2014]\s*$")

# --- ixbrlparse on iXBRL ---
c = collections.Counter(); secs = 0.0
for f in html:
    t = time.perf_counter()
    x = IXBRL(open(f, encoding="utf8"), raise_on_error=False)
    secs += time.perf_counter() - t
    c["parsed"] += 1
    groups = collections.defaultdict(list)
    cred = {"total": False, "parts": False}
    for n in x.numeric:
        tag = n.soup_tag
        if tag is not None and dash.match(tag.get_text() or ""):
            c["dash_facts"] += 1; c["dash_as_zero"] += n.value == 0
        if tag is not None and tag.get("sign") == "-":
            c["sign_minus"] += 1; c["sign_ok"] += (n.value or 0) <= 0
        if n.context.segments: c["dimensional_facts"] += 1
        groups[(n.name, n.context.id)].append(n.value)
        if n.name == "Creditors":
            cred["parts" if n.context.segments else "total"] = True
    c["repeat_groups"] += sum(len(v) > 1 for v in groups.values())
    c["repeat_disagree"] += sum(len(v) > 1 and len(set(map(repr, v))) > 1 for v in groups.values())
    if cred["total"] or cred["parts"]:
        c["creditors_filings"] += 1
        c["creditors_parts_only"] += cred["parts"] and not cred["total"]
print("ixbrlparse iXBRL:", dict(c), f"ms/file={1000*secs/len(html):.1f}")

# --- ixbrlparse on plain XML ---
ok = sum(1 for f in xml if IXBRL(open(f, encoding="utf8"), raise_on_error=False) is not None)
print(f"ixbrlparse XML: {ok}/{len(xml)} parsed")

# --- ixbrl-parse (cybermaggedon) ---
fails = collections.Counter()
for f in html:
    try:
        ixbrl_parse_parse(ET.parse(f))
    except Exception as e:  # noqa: BLE001 - counting failure types is the point
        fails[type(e).__name__] += 1
print(f"ixbrl-parse: {len(html) - sum(fails.values())}/{len(html)} parsed; failures {dict(fails)}")
