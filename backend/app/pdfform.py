"""Places the candidate's saved answers onto the real scanned HAL form pages.

One list of "ops" (what to draw and where) feeds both the live web view and the downloadable PDF, so the two
always agree. Coordinates are in a 827 x 1169 space (the A4 page rendered at 100 dpi); one unit is 0.72 pt."""
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

import pymupdf

from . import formschema as fs

W, H = 827, 1169
PT = 595.32 / W
ASSETS = Path(__file__).parent / "assets"
IST = timezone(timedelta(hours=5, minutes=30))

# Wide description column of the main table.
_A = 430
_AW = 368
_B = 462
_BW = 320

# (path, page, box, opts). A "kind" other than text is drawn as a mark.
_ITI = [
    ("apprenticeship_reg_no", 0, [_A, 247, _AW, 44], {}),
    ("candidate_name", 0, [_A, 291, _AW, 42], {}),
    ("father_name", 0, [_A, 333, _AW, 44], {}),
    ("mother_name", 0, [_A, 377, _AW, 42], {}),
    ("dob", 0, [_A, 419, 232, 35], {}),
    ("gender", 0, [_A, 454, 232, 33], {}),
    ("aadhaar_no", 0, [_A, 487, 232, 33], {}),
    ("pan_no", 0, [_A, 520, 232, 32], {}),
    ("hs_marks_obtained", 0, [534, 574, 78, 28], {}),
    ("hs_total_marks", 0, [712, 574, 82, 28], {}),
    ("hs_percentage", 0, [_A, 606, _AW, 42], {}),
    ("iti_institute", 0, [_A, 650, _AW, 144], {"wrap": True}),
    ("iti_trade", 0, [_A, 796, _AW, 33], {}),
    ("iti_pass_year", 0, [_A, 829, _AW, 42], {}),
    ("iti_percentage", 0, [_A, 972, _AW, 45], {}),
    ("caste_name", 0, [_A, 1063, _AW, 50], {}),
    ("certificate_type=NCVT", 0, [486, 1028, 40, 18], {"kind": "tick"}),
    ("certificate_type=SCVT", 0, [674, 1028, 40, 18], {"kind": "tick"}),
]
_ITI_SEM_X = [476, 537, 597, 657, 737, 802]
_ITI_TOTAL_Y = (898, 26)
_ITI_OBT_Y = (925, 47)

_CAT_A = [("SC", 377, 435), ("ST", 437, 493), ("OBC", 494, 565), ("PWD", 566, 645), ("EWS", 646, 734), ("GEN", 735, 785)]
_CAT_B = [("SC", 373, 426), ("ST", 428, 481), ("OBC", 483, 576), ("PWD", 578, 645), ("EWS", 647, 739), ("GEN", 741, 785)]

_ITI_P2 = {
    "cat_y": (107, 25), "cats": _CAT_A,
    "yes_no": {"category_cert_enclosed": 238, "domicile_cert_enclosed": 388}, "yes_x": 470, "no_x": 676,
    "addr": [(447, 36), (483, 38), (521, 38), (559, 37)], "addr_x": (380, 402),
    "pin": (634, 36, [437, 497, 566, 621, 677, 731, 786]),
    "mobile": (500, 676, 30), "email": (472, 710, 30), "parent": (632, 744, 28),
    "place": (158, 978, 126, 24), "date": (164, 1010, 118, 24),
}
_VOC = [
    ("apprenticeship_reg_no", 0, [_B, 214, _BW, 71], {}),
    ("candidate_name", 0, [_B, 285, _BW, 45], {}),
    ("father_name", 0, [_B, 330, _BW, 43], {}),
    ("mother_name", 0, [_B, 373, _BW, 44], {}),
    ("dob", 0, [_B, 417, 192, 42], {}),
    ("gender", 0, [_B, 459, 192, 41], {}),
    ("aadhaar_no", 0, [_B, 500, 192, 38], {}),
    ("pan_no", 0, [_B, 538, 192, 39], {}),
    ("hs_marks_obtained", 0, [572, 600, 46, 28], {}),
    ("hs_total_marks", 0, [718, 600, 46, 28], {}),
    ("hs_percentage", 0, [_B, 633, _BW, 56], {}),
    ("voc_subject", 0, [_B, 689, _BW, 52], {}),
    ("voc_board", 0, [_B, 741, _BW, 50], {}),
    ("voc_pass_year", 0, [_B, 791, _BW, 47], {}),
    ("voc_institute", 0, [_B, 840, _BW, 104], {"wrap": True}),
    ("voc_marks_obtained", 0, [570, 971, 46, 28], {}),
    ("voc_total_marks", 0, [714, 971, 52, 28], {}),
    ("voc_percentage", 0, [_B, 1008, _BW, 46], {}),
    ("caste_name", 0, [_B, 1054, _BW, 53], {}),
]
_VOC_P2 = {
    "cat_y": (117, 25), "cats": _CAT_B,
    "yes_no": {"category_cert_enclosed": 246, "domicile_cert_enclosed": 398}, "yes_x": 470, "no_x": 672,
    "addr": [(470, 40), (510, 38), (548, 43), (591, 42)], "addr_x": (378, 402),
    "pin": (672, 25, [447, 503, 577, 615, 672, 728, 785]),
    "mobile": (480, 702, 28), "email": (470, 732, 28), "parent": (608, 760, 28),
    "place": (184, 1007, 98, 24), "date": (186, 1039, 96, 24),
}
LAYOUT = {
    "ITI": {"pdf": "form_a.pdf", "pages": ["a1", "a2"], "main": _ITI, "p2": _ITI_P2},
    "VOCATIONAL": {"pdf": "form_b.pdf", "pages": ["b1", "b2"], "main": _VOC, "p2": _VOC_P2},
}


def _num(v) -> str:
    if v is None:
        return ""
    return str(int(v)) if float(v) == int(v) else f"{float(v):g}"


def _enum_label(spec: dict, code) -> str:
    o = next((o for o in fs._enum_options(spec) if o["code"] == code), None)
    return (o or {}).get("en", str(code))


class _Ctx:
    def __init__(self, data: dict, derived: dict):
        self.data, self.derived = data, derived

    def entry(self, key):
        return self.data.get(key) or {}

    def value(self, key):
        return self.entry(key).get("value")

    def status(self, key):
        return self.entry(key).get("status")

    def text(self, key: str) -> str:
        spec = fs.FIELDS.get(key)
        if spec and spec.get("derived"):
            v = self.derived.get(key)
            return "" if v is None else f"{v:.2f} %"
        v = self.value(key)
        if v is None:
            return ""
        if key == "dob":
            return f"{v[8:10]}/{v[5:7]}/{v[:4]}"
        if key == "aadhaar_no":
            return " ".join(v[i:i + 4] for i in range(0, len(v), 4))
        if spec and spec["type"] == "enum":
            return _enum_label(spec, v)
        if spec and spec["type"] in ("integer", "number"):
            return _num(v)
        return str(v)


def _fit(text: str, w: int, h: int, wrap: bool) -> tuple[list[str], float]:
    """Choose a font size (layout units) and line breaks that fit the box."""
    width = lambda s, z: pymupdf.get_text_length(s, fontname="helv", fontsize=z)
    if not wrap:
        size = min(17.0, h * 0.62)
        while size > 8 and width(text, size) > w - 8:
            size -= 0.5
        return [text], size
    size = 15.0
    while True:
        lines, cur = [], ""
        for word in text.split():
            trial = (cur + " " + word).strip()
            if width(trial, size) <= w - 10:
                cur = trial
            else:
                if cur:
                    lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
        if len(lines) * size * 1.3 <= h - 6 or size <= 9:
            return lines, size
        size -= 1


def _text_op(page, box, text, path, status, wrap=False, align="l"):
    lines, size = _fit(text, box[2], box[3], wrap)
    return {"page": page, "kind": "text", "box": box, "lines": lines, "size": round(size, 1),
            "align": align, "path": path, "status": status}


def _mark(page, box, kind, path, status):
    return {"page": page, "kind": kind, "box": box, "path": path, "status": status}


def render_ops(data: dict, derived: dict, variant: str | None, now: datetime | None = None) -> list[dict]:
    lay = LAYOUT.get(variant or "")
    if not lay:
        return []
    c = _Ctx(data, derived)
    ops: list[dict] = []

    for path, page, box, o in lay["main"]:
        if "=" in path:  # a tick box that applies when the field has this value
            key, want = path.split("=")
            if c.value(key) == want:
                ops.append(_mark(page, box, "tick", key, c.status(key)))
            continue
        t = c.text(path)
        if t:
            ops.append(_text_op(page, box, t, path, c.status(path), wrap=o.get("wrap", False)))

    if variant == "ITI":
        sems = c.value("iti_semester_marks") or {}
        tot_sum = obt_sum = 0
        have = False
        for n in range(1, 5):
            it = sems.get(f"sem{n}") or {}
            x0, x1 = _ITI_SEM_X[n - 1], _ITI_SEM_X[n]
            for key, (y, h) in (("total", _ITI_TOTAL_Y), ("obtained", _ITI_OBT_Y)):
                if it.get(key) is not None:
                    ops.append(_text_op(0, [x0 + 2, y, x1 - x0 - 4, h], _num(it[key]),
                                        f"iti_semester_marks.{n}.{key}", c.status("iti_semester_marks"), align="c"))
            if it.get("total") is not None and it.get("obtained") is not None:
                have = True
                tot_sum += it["total"]
                obt_sum += it["obtained"]
        if have:
            x0, x1 = _ITI_SEM_X[4], _ITI_SEM_X[5]
            ops.append(_text_op(0, [x0 + 2, _ITI_TOTAL_Y[0], x1 - x0 - 4, _ITI_TOTAL_Y[1]], _num(tot_sum), "iti_semester_marks", None, align="c"))
            ops.append(_text_op(0, [x0 + 2, _ITI_OBT_Y[0], x1 - x0 - 4, _ITI_OBT_Y[1]], _num(obt_sum), "iti_semester_marks", None, align="c"))

    p2 = lay["p2"]
    cat = c.value("category")
    for code, x0, x1 in p2["cats"]:
        if cat == code:
            y, h = p2["cat_y"]
            ops.append(_mark(1, [x0 + 2, y, x1 - x0 - 4, h], "tick", "category", c.status("category")))
    for key, y in p2["yes_no"].items():
        v = c.value(key)
        if v is not None:
            x = p2["yes_x"] if v else p2["no_x"]
            ops.append(_mark(1, [x - 46, y - 17, 92, 34], "ring", key, c.status(key)))

    addr = c.value("address") or {}
    ast = c.status("address")
    ax, aw = p2["addr_x"]
    lines = [addr.get("line1"), addr.get("line2"), addr.get("district"), addr.get("state")]
    paths = ["address.line1", "address.line2", "address.district", "address.state"]
    for (y, h), t, pth in zip(p2["addr"], lines, paths):
        if t:
            ops.append(_text_op(1, [ax, y, 786 - ax - 4, h], str(t), pth, ast))
    pin = str(addr.get("pin") or "")
    py, ph, xs = p2["pin"]
    for i, d in enumerate(pin[:6]):
        ops.append(_text_op(1, [xs[i] + 1, py, xs[i + 1] - xs[i] - 2, ph], d, "address.pin", ast, align="c"))

    for key in ("mobile", "email", "parent_mobile"):
        x, y, h = p2["parent" if key == "parent_mobile" else key]
        t = c.text(key)
        if t:
            ops.append(_text_op(1, [x, y, 784 - x, h], t, key, c.status(key)))

    place = c.text("place")
    if place:
        ops.append(_text_op(1, p2["place"], place, "place", c.status("place")))
    if c.value("declaration_accepted") is True:
        ops.append(_text_op(1, p2["date"], (now or datetime.now(IST)).strftime("%d/%m/%Y"), "declaration_accepted",
                            c.status("declaration_accepted")))
    return ops


def build_pdf(ops: list[dict], variant: str) -> bytes:
    """Draw the ops onto the original scanned pages and return the PDF."""
    doc = pymupdf.open(str(ASSETS / LAYOUT[variant]["pdf"]))
    ink = (0.06, 0.2, 0.62)
    for op in ops:
        page = doc[op["page"]]
        x, y, w, h = (v * PT for v in op["box"])
        if op["kind"] == "text":
            size = op["size"] * PT
            line_h = size * 1.3
            n = len(op["lines"])
            top = y + (h - n * line_h) / 2 if n == 1 else y + 3
            for i, ln in enumerate(op["lines"]):
                ln = ln.encode("latin-1", "replace").decode("latin-1")
                tw = pymupdf.get_text_length(ln, fontname="helv", fontsize=size)
                tx = x + (w - tw) / 2 if op["align"] == "c" else x + 4
                page.insert_text((tx, top + i * line_h + size * 0.95), ln, fontname="helv", fontsize=size, color=ink)
        elif op["kind"] == "tick":
            cx, cy = x + w / 2, y + h / 2
            s = min(w, h) * 0.5
            page.draw_polyline([(cx - s, cy), (cx - s * 0.3, cy + s * 0.8), (cx + s * 1.1, cy - s)], color=ink, width=2.2)
        elif op["kind"] == "ring":
            page.draw_oval(pymupdf.Rect(x, y, x + w, y + h), color=ink, width=1.8)
    out = BytesIO()
    doc.save(out, garbage=3, deflate=True)
    return out.getvalue()
