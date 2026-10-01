# Run from a folder containing ons/ (see tool-comparison-check.py) and ours/ (open-company-uk src/ukcompany copied into ours/ukcompany).
import glob, time, collections, re, sys
from decimal import Decimal
sys.path.insert(0, "ours")
from ukcompany.accounts.core import extract_filing
from ixbrlparse import IXBRL

def ln(q): return (q or "").split(":")[-1]
files = sorted(glob.glob("ons/example_data_XBRL_iXBRL/*.html"))
c = collections.Counter(); t_ours = t_ix = 0.0; examples = collections.defaultdict(list)
for f in files:
    data = open(f, "rb").read()
    m = re.search(r"_(\w{8})_(\d{8})\.html$", f); comp, mud = m.group(1), m.group(2)
    t = time.perf_counter(); r = extract_filing(data, comp, mud); t_ours += time.perf_counter() - t
    t = time.perf_counter(); x = IXBRL(open(f, encoding="utf8"), raise_on_error=False); t_ix += time.perf_counter() - t
    ours = collections.defaultdict(set)
    for o in r.observations:
        if o.fact_kind != "numeric": continue
        key = (o.concept, o.period_end, ((o.dimension, o.member),) if o.dimension else ())
        v = o.numeric_value
        if v is None and o.raw_value.strip() in {"-", "–", "—"}: v = "0"   # pipeline treats dash as 0 downstream
        ours[key].add(None if v is None else Decimal(v).normalize())
        if o.status != "selected": c["ours_conflict_rows"] += 1
    ix = collections.defaultdict(set); ix_kind = {}
    for n in x.numeric:
        ctx = n.context; pe = str(ctx.instant or ctx.enddate)
        segs = ctx.segments or []
        dims = tuple(sorted((ln(s.get("dimension")), ln(s.get("value"))) for s in segs))
        key = (n.name, pe, dims)
        ix[key].add(None if n.value is None else Decimal(str(n.value)).normalize())
        kind = "typed" if any(s.get("tag") == "typedMember" for s in segs) else ("multi" if len(segs) > 1 else "ok")
        ix_kind[key] = kind
    for k in set(ours) | set(ix):
        if k in ours and k in ix:
            c["both"] += 1
            if ours[k] == ix[k]: c["both_agree"] += 1
            else:
                c["both_disagree"] += 1
                if len(examples["disagree"]) < 6: examples["disagree"].append((f[-30:], k, ours[k], ix[k]))
        elif k in ix:
            c["ix_only_" + ix_kind[k]] += 1
            if ix_kind[k] == "ok" and len(examples["ix_only"]) < 6: examples["ix_only"].append((f[-30:], k, ix[k]))
        else:
            c["ours_only"] += 1
            if len(examples["ours_only"]) < 6: examples["ours_only"].append((f[-30:], k, ours[k]))
print(dict(c))
print(f"speed ms/file: ours={1000*t_ours/len(files):.1f}  ixbrlparse={1000*t_ix/len(files):.1f}")
for k, v in examples.items():
    print("\n--", k)
    for e in v: print(" ", e)
