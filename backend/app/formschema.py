"""Loads the versioned form schema and implements validation, normalization,
derived values and completion rules. The JSON file is the single contract."""
import json
import re
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import regex

SCHEMA = json.loads((Path(__file__).parent / "form_schema.v1.json").read_text(encoding="utf8"))
SCHEMA_VERSION = SCHEMA["version"]
FIELDS = {f["id"]: f for f in SCHEMA["fields"]}
GROUPS = {g["id"]: g for g in SCHEMA["groups"]}
AGE_REF_DATE = date(2026, 1, 31)
UPPER_AGE_BASE = 27
AGE_RELAX = {"SC": 5, "ST": 5, "OBC": 3, "PWD": 10}

_VD = [[0,1,2,3,4,5,6,7,8,9],[1,2,3,4,0,6,7,8,9,5],[2,3,4,0,1,7,8,9,5,6],[3,4,0,1,2,8,9,5,6,7],[4,0,1,2,3,9,5,6,7,8],
       [5,9,8,7,6,0,4,3,2,1],[6,5,9,8,7,1,0,4,3,2],[7,6,5,9,8,2,1,0,4,3],[8,7,6,5,9,3,2,1,0,4],[9,8,7,6,5,4,3,2,1,0]]
_VP = [[0,1,2,3,4,5,6,7,8,9],[1,5,7,6,2,8,3,0,9,4],[5,8,0,3,7,9,6,1,4,2],[8,9,1,6,0,4,3,5,2,7],
       [9,4,5,3,1,2,6,8,7,0],[4,2,8,6,5,7,3,9,0,1],[2,7,9,3,8,0,6,4,1,5],[7,0,4,6,9,1,3,2,5,8]]


def verhoeff_ok(num: str) -> bool:
    c = 0
    for i, ch in enumerate(reversed(num)):
        c = _VD[c][_VP[i % 8][int(ch)]]
    return c == 0


class ValidationError(Exception):
    def __init__(self, field: str, code: str, message: str):
        self.field, self.code, self.message = field, code, message
        super().__init__(message)

    def as_dict(self):
        return {"field": self.field, "code": self.code, "message": self.message}


def _normalize(value: str, rule: str | None) -> str:
    v = value.strip()
    if rule == "uppercase_latin":
        return re.sub(r"\s+", " ", v).upper()
    if rule == "uppercase_strip_spaces":
        return re.sub(r"\s+", "", v).upper()
    if rule == "digits_only":
        return re.sub(r"\D", "", v)
    if rule == "digits_only_strip_91":
        d = re.sub(r"\D", "", v)
        if len(d) == 12 and d.startswith("91"):
            d = d[2:]
        if len(d) == 11 and d.startswith("0"):
            d = d[1:]
        return d
    if rule == "lowercase":
        return v.lower()
    return v


def _parse_date(s: str) -> str:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(s.strip(), fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError("date")


def _enum_options(spec: dict) -> list[dict]:
    if "enum_ref" in spec:
        return SCHEMA["enums"][spec["enum_ref"]]
    return [{"code": c, "en": c} for c in spec["enum"]]


def validate_scalar(path: str, spec: dict, raw, ctx: dict | None = None):
    """Return the normalized value or raise ValidationError.
    ctx maps sibling field ids to values, for max_ref bounds."""
    t = spec["type"]
    rules = spec.get("validate", {})
    ctx = ctx or {}
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        raise ValidationError(path, "empty", "No value was given.")
    if t == "enum":
        s = str(raw).strip().lower()
        for opt in _enum_options(spec):
            if s in (opt["code"].lower(), opt.get("en", "").lower(), opt.get("hi", "")):
                return opt["code"]
        raise ValidationError(path, "invalid_choice", "Not one of the allowed choices.")
    if t == "boolean":
        if isinstance(raw, bool):
            return raw
        s = str(raw).strip().lower()
        if s in ("true", "yes", "y", "1", "haan", "हाँ"):
            return True
        if s in ("false", "no", "n", "0", "nahi", "नहीं"):
            return False
        raise ValidationError(path, "invalid_boolean", "Expected yes or no.")
    if t == "date":
        try:
            return _parse_date(str(raw))
        except ValueError:
            raise ValidationError(path, "invalid_date", "Could not read a valid date; need day, month and year.")
    if t in ("integer", "number"):
        try:
            n = Decimal(re.sub(r"[,\s]", "", str(raw)))
        except Exception:
            raise ValidationError(path, "invalid_number", "Expected a number.")
        if t == "integer" and n != n.to_integral_value():
            raise ValidationError(path, "invalid_number", "Expected a whole number.")
        if "decimals" in rules and -n.as_tuple().exponent > rules["decimals"]:
            raise ValidationError(path, "too_many_decimals", f"At most {rules['decimals']} decimal places.")
        if "min" in rules and n < rules["min"]:
            raise ValidationError(path, "too_small", f"Must be at least {rules['min']}.")
        if "max" in rules and n > rules["max"]:
            raise ValidationError(path, "too_large", f"Must be at most {rules['max']}.")
        ref = rules.get("max_ref")
        if ref and ctx.get(ref) is not None and n > Decimal(str(ctx[ref])):
            raise ValidationError(path, "exceeds_total", "Marks obtained cannot be more than total marks.")
        if "allowed" in rules and int(n) not in rules["allowed"]:
            raise ValidationError(path, "not_allowed", "Only these values are accepted: " + ", ".join(str(a) for a in rules["allowed"]) + ". Tell the candidate this and ask again.")
        return int(n) if t == "integer" else float(n)
    v = _normalize(str(raw), rules.get("normalize"))
    if "min_len" in rules and len(v) < rules["min_len"]:
        raise ValidationError(path, "too_short", "Too short.")
    if "max_len" in rules and len(v) > rules["max_len"]:
        raise ValidationError(path, "too_long", "Too long.")
    if "pattern" in rules and not regex.fullmatch(rules["pattern"], v):
        raise ValidationError(path, "invalid_format", "Format is not valid.")
    if rules.get("format") == "email" and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v):
        raise ValidationError(path, "invalid_email", "Not a valid email address.")
    if rules.get("checksum") == "verhoeff" and not verhoeff_ok(v):
        raise ValidationError(path, "invalid_checksum", "These digits are not a valid number. Ask the candidate to repeat them.")
    return v


def resolve_path(path: str):
    """Return (field spec, child spec or None, item key or None, child id or None).
    Paths: `candidate_name`, `address.line1`, `iti_semester_marks.2.total`."""
    parts = path.split(".")
    spec = FIELDS.get(parts[0])
    if not spec:
        raise ValidationError(path, "unknown_field", "Unknown field.")
    if spec["type"] == "group":
        if len(parts) != 2:
            raise ValidationError(path, "needs_child", "Specify which part, for example address.pin.")
        child = next((c for c in spec["children"] if c["id"] == parts[1]), None)
        if not child:
            raise ValidationError(path, "unknown_field", "Unknown part of this group.")
        return spec, child, None, parts[1]
    if spec["type"] == "repeatable":
        if len(parts) != 3 or not parts[1].isdigit():
            raise ValidationError(path, "needs_child", "Use iti_semester_marks.<semester number>.<total or obtained>.")
        child = next((c for c in spec["item"] if c["id"] == parts[2]), None)
        if not child or child["id"] == "semester":
            raise ValidationError(path, "unknown_field", "Unknown part of this item.")
        n = int(parts[1])
        if not (1 <= n <= spec["max_items"]):
            raise ValidationError(path, "invalid_item", "Semester number out of range.")
        return spec, child, f"sem{n}", parts[2]
    if len(parts) != 1:
        raise ValidationError(path, "unknown_field", "This field has no parts.")
    return spec, None, None, None


def field_visible(spec: dict, data: dict, variant: str | None) -> bool:
    g = GROUPS.get(spec.get("group"), {})
    for cond in (g.get("when"), spec.get("when")):
        if not cond:
            continue
        if "variant" in cond and cond["variant"] != variant:
            return False
        if "field" in cond and data.get(cond["field"], {}).get("value") not in cond["in"]:
            return False
    return True


def compute_derived(data: dict) -> dict:
    """Derived percentage fields, two decimals. None while inputs are incomplete."""
    def pct(num, den):
        if num is None or not den:
            return None
        return float((Decimal(str(num)) * 100 / Decimal(str(den))).quantize(Decimal("0.01"), ROUND_HALF_UP))

    val = lambda k: data.get(k, {}).get("value")
    items = (val("iti_semester_marks") or {}).values()
    done = [i for i in items if i.get("total") is not None and i.get("obtained") is not None]
    return {
        "hs_percentage": pct(val("hs_marks_obtained"), val("hs_total_marks")),
        "voc_percentage": pct(val("voc_marks_obtained"), val("voc_total_marks")),
        "iti_percentage": pct(sum(i["obtained"] for i in done), sum(i["total"] for i in done)) if done else None,
    }


def _missing_parts(spec: dict, entry) -> list[str]:
    ident = spec["id"]
    if spec["type"] == "group":
        have = (entry or {}).get("value") or {}
        return [f"{ident}.{c['id']}" for c in spec["children"] if c.get("required") and c["id"] not in have]
    if spec["type"] == "repeatable":
        items = (entry or {}).get("value") or {}
        full = [k for k, i in items.items() if "total" in i and "obtained" in i]
        if len(full) >= spec.get("min_items", 1):
            return []
        if not items:
            return [f"{ident}.1.total", f"{ident}.1.obtained"]
        return [f"{ident}.{k[3:]}.{p}" for k, i in items.items() for p in ("total", "obtained") if p not in i][:2]
    return [] if entry and entry.get("value") is not None else [ident]


def missing_fields(data: dict, variant: str | None) -> list[str]:
    if variant is None:
        return ["variant"]
    out = []
    for spec in sorted(SCHEMA["fields"], key=lambda f: (GROUPS[f["group"]]["order"], f["order"])):
        if not spec.get("required") or spec.get("derived") or not field_visible(spec, data, variant):
            continue
        out += _missing_parts(spec, data.get(spec["id"]))
    return out


def unconfirmed_fields(data: dict, variant: str | None) -> list[str]:
    out = []
    for spec in SCHEMA["fields"]:
        c = spec.get("confirm")
        # Only values that are risky to mishear need a read-back; "spell_on_request" etc. do not block submission.
        needs = c is True or (isinstance(c, str) and c.startswith(("read_back", "explicit")))
        if not needs or spec.get("derived") or not field_visible(spec, data, variant):
            continue
        e = data.get(spec["id"])
        if e and e.get("status") != "confirmed":
            out.append(spec["id"])
    return out


def warnings_for(data: dict) -> list[dict]:
    w = []
    dob = data.get("dob", {}).get("value")
    if dob:
        d = date.fromisoformat(dob)
        age = AGE_REF_DATE.year - d.year - ((AGE_REF_DATE.month, AGE_REF_DATE.day) < (d.month, d.day))
        upper = UPPER_AGE_BASE + AGE_RELAX.get(data.get("category", {}).get("value"), 0)
        if age < 18 or age > upper:
            w.append({"field": "dob", "code": "age_outside_range",
                      "message": f"Age on 31 Jan 2026 is {age}; the notice allows 18 to {upper} for this category. Rule needs HAL review, so this is not blocked."})
    return w


def mask(spec: dict, value):
    pol = spec.get("log", "full")
    if pol == "never":
        return "[restricted]"
    if pol == "mask" and isinstance(value, str) and len(value) > 4:
        return "*" * (len(value) - 4) + value[-4:]
    return value


def label(path: str, lang: str = "en") -> str:
    spec = FIELDS[path.split(".")[0]]
    return spec["label"].get(lang) or spec["label"]["en"]
