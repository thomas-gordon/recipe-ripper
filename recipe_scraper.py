"""
Universal Recipe → Metric PDF Converter
========================================
Works with virtually any recipe website that uses schema.org/Recipe markup
(AllRecipes, BBC Good Food, Serious Eats, Epicurious, NYT Cooking,
Bon Appétit, RecipeTin Eats, Tasty, Delish, King Arthur Baking, and
hundreds more).

USAGE
─────
  python recipe_scraper.py https://www.anyrecipesite.com/recipe-url/

DEPENDENCIES
────────────
  pip install requests beautifulsoup4 reportlab

HOW IT WORKS
────────────
1. Fetches the page HTML
2. Extracts the embedded schema.org/Recipe JSON-LD block (the industry
   standard structured data format — virtually every major recipe site
   uses it, because it powers Google's rich recipe snippets)
3. Parses ingredients strings to split qty / unit / ingredient name
4. Converts US volume measures to metric weight using known density tables
5. Generates a polished A4 PDF with: title, metadata bar, ingredients table
   (original US | metric weight), numbered method steps, notes/tips
"""

import sys
import re
import json
import os
import requests
from bs4 import BeautifulSoup
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether
)
from reportlab.lib.enums import TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Register elegant fonts — looks for .ttf files next to this script
_HERE = os.path.dirname(os.path.abspath(__file__))
def _font(filename):
    return os.path.join(_HERE, filename)

pdfmetrics.registerFont(TTFont("Lora",          _font("Lora-Regular.ttf")))
pdfmetrics.registerFont(TTFont("Lora-Italic",   _font("Lora-Italic.ttf")))
pdfmetrics.registerFont(TTFont("Poppins",       _font("Poppins-Regular.ttf")))
pdfmetrics.registerFont(TTFont("Poppins-Bold",  _font("Poppins-Bold.ttf")))
pdfmetrics.registerFont(TTFont("Poppins-Medium",_font("Poppins-Medium.ttf")))

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — FETCH & EXTRACT  (schema.org/Recipe JSON-LD)
# ─────────────────────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}

def fetch_recipe_jsonld(url: str) -> dict:
    """
    Fetches a recipe page and extracts the schema.org/Recipe JSON-LD block.
    Also accepts a local file path (e.g. ~/Downloads/recipe.html) as a fallback
    for sites that block automated requests (Cloudflare-protected sites like
    Serious Eats, NYT Cooking).  To use: open the page in your browser,
    File → Save Page As → Webpage, HTML Only, then pass the saved path.
    Returns a raw dict of the recipe data, or raises ValueError if not found.
    """
    # ── Local file fallback ──────────────────────────────────────────────────
    expanded = os.path.expanduser(url)
    if os.path.isfile(expanded):
        with open(expanded, "r", encoding="utf-8", errors="replace") as fh:
            html = fh.read()
        soup = BeautifulSoup(html, "html.parser")
        # Use the filename stem as a stand-in URL for the recipe dict
        url = f"file://{os.path.abspath(expanded)}"
    else:
        # ── Live fetch ───────────────────────────────────────────────────────
        from urllib.parse import urlparse
        session = requests.Session()
        session.headers.update(HEADERS)
        parsed = urlparse(url)
        session.headers["Referer"] = f"https://www.google.com/search?q={parsed.netloc}+recipe"
        response = session.get(url, timeout=15, allow_redirects=True)
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            if response.status_code == 403:
                raise ValueError(
                    f"403 Forbidden — {parsed.netloc} blocks automated requests "
                    f"(likely Cloudflare protection).\n\n"
                    f"Workaround: open the page in your browser, choose\n"
                    f"  File → Save Page As → Webpage, HTML Only\n"
                    f"then run:  python recipe_scraper.py ~/Downloads/recipe.html"
                ) from e
            raise
        soup = BeautifulSoup(response.text, "html.parser")

    # Find ALL <script type="application/ld+json"> tags
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue

        # Could be a single object or a list
        items = data if isinstance(data, list) else [data]

        # Also handle @graph wrapping (common on WordPress / Yoast sites)
        for item in items:
            if isinstance(item, dict) and "@graph" in item:
                items = item["@graph"]
                break

        for item in items:
            if not isinstance(item, dict):
                continue
            rtype = item.get("@type", "")
            # @type can be a string or a list
            if isinstance(rtype, list):
                rtype = " ".join(rtype)
            if "Recipe" in rtype:
                return item

    raise ValueError(
        "No schema.org/Recipe JSON-LD found on this page.\n"
        "The site may not use structured data, or requires JavaScript rendering.\n"
        "Try a different URL, or use the manual RECIPE dict in recipe_to_pdf.py."
    )


def parse_iso_duration(iso: str) -> str:
    """Convert ISO 8601 duration (PT1H30M) to readable string."""
    if not iso:
        return "—"
    iso = iso.upper()
    hours = re.search(r"(\d+)H", iso)
    mins  = re.search(r"(\d+)M", iso)
    parts = []
    if hours:
        h = int(hours.group(1))
        parts.append(f"{h} hr{'s' if h > 1 else ''}")
    if mins:
        m = int(mins.group(1))
        parts.append(f"{m} min{'s' if m > 1 else ''}")
    return " ".join(parts) if parts else iso


def extract_instructions(raw) -> list:
    """
    Handle the many ways sites encode recipeInstructions:
    - A plain string
    - A list of strings
    - A list of HowToStep dicts
    - A list of HowToSection dicts (each containing HowToStep items)
    Returns a list of (label, text) tuples.
    """
    if not raw:
        return []

    if isinstance(raw, str):
        # Split on double-newlines or numbered lines
        lines = [l.strip() for l in re.split(r"\n\n+|\r\n\r\n+", raw) if l.strip()]
        return [(f"Step {i+1}", l) for i, l in enumerate(lines)]

    steps = []
    step_num = 1
    for item in raw:
        if isinstance(item, str) and item.strip():
            steps.append((f"Step {step_num}", item.strip()))
            step_num += 1
        elif isinstance(item, dict):
            t = item.get("@type", "")
            if "HowToStep" in t:
                name = item.get("name", "").strip()
                text = item.get("text", "").strip()
                label = name if name and name.lower() != text.lower()[:len(name)] else f"Step {step_num}"
                steps.append((label, text or name))
                step_num += 1
            elif "HowToSection" in t:
                section_name = item.get("name", f"Section {step_num}")
                for sub in item.get("itemListElement", []):
                    if isinstance(sub, dict):
                        text = sub.get("text", sub.get("name", "")).strip()
                        if text:
                            steps.append((f"{section_name} — Step {step_num}", text))
                            step_num += 1
    return steps


def jsonld_to_recipe(data: dict, url: str) -> dict:
    """Convert raw JSON-LD dict into our standardised RECIPE format."""
    name      = data.get("name", "Untitled Recipe")
    desc      = data.get("description", "")
    prep      = parse_iso_duration(data.get("prepTime", ""))
    cook      = parse_iso_duration(data.get("cookTime", ""))
    total     = parse_iso_duration(data.get("totalTime", ""))
    yld       = data.get("recipeYield", "—")
    if isinstance(yld, list):
        yld = yld[0]

    raw_ingredients   = data.get("recipeIngredient", [])
    raw_instructions  = data.get("recipeInstructions", [])

    # Author
    author = data.get("author", {})
    if isinstance(author, list):
        author = author[0]
    source = author.get("name", url) if isinstance(author, dict) else str(author)

    instructions = extract_instructions(raw_instructions)

    # Convert all Fahrenheit temperatures to Celsius across every text field
    desc         = convert_temps_to_celsius(desc)
    instructions = [(label, convert_temps_to_celsius(body)) for label, body in instructions]
    raw_ingredients = [convert_temps_to_celsius(i) for i in raw_ingredients]

    return {
        "title":       name,
        "source":      source,
        "url":         url,
        "description": desc,
        "prep_time":   prep or "—",
        "cook_time":   cook or "—",
        "total_time":  total or "—",
        "yield":       str(yld),
        "raw_ingredients": raw_ingredients,   # raw strings; parsed in next step
        "method":      instructions,
        "notes":       [],   # sites rarely embed tips in JSON-LD; add manually
    }


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1b — FAHRENHEIT → CELSIUS  (applied to all text fields)
# ─────────────────────────────────────────────────────────────────────────────

# Matches °F values not already inside a "(…°F)" reference added by a prior pass
_TEMP_F_RE = re.compile(
    r"(?<!\()\b(\d+(?:\.\d+)?)\s*(?:°\s*F|degrees?\s+F(?:ahrenheit)?|°\s*Fahrenheit)(?!\))",
    re.IGNORECASE
)

def f_to_c(f: float) -> int:
    """Convert Fahrenheit to Celsius, rounded to nearest 5° for oven temps."""
    c = (f - 32) * 5 / 9
    # Round to nearest 5 for cleaner oven temperatures
    return int(round(c / 5) * 5)

def convert_temps_to_celsius(text: str) -> str:
    """
    Find every Fahrenheit temperature in a string and replace it with
    '°C (°F)' format.  e.g. '375°F'  →  '190°C (375°F)'
    """
    def replacer(m):
        f_val = float(m.group(1))
        c_val = f_to_c(f_val)
        orig_f = int(f_val) if f_val == int(f_val) else f_val
        return f"{c_val}\u00b0C ({orig_f}\u00b0F)"

    return _TEMP_F_RE.sub(replacer, text)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — PARSE INGREDIENT STRINGS
# ─────────────────────────────────────────────────────────────────────────────

# Recognise unicode fractions
UNICODE_FRACTIONS = {
    "½": 0.5, "¼": 0.25, "¾": 0.75,
    "⅓": 1/3, "⅔": 2/3, "⅛": 0.125, "⅜": 0.375, "⅝": 0.625, "⅞": 0.875,
}
FRAC_RE = re.compile(r"[½¼¾⅓⅔⅛⅜⅝⅞]")

UNITS_RE = re.compile(
    r"""^(
        \d[\d\s/\.]*          # leading number (may include fractions like 1 1/2)
        [½¼¾⅓⅔⅛⅜⅝⅞]?         # optional unicode fraction
    )\s*
    (cups?|tbsps?|tablespoons?|tsps?|teaspoons?|oz|ounces?|
     lbs?|pounds?|g|grams?|kg|kilograms?|ml|milliliters?|
     liters?|litres?|l|fl\.?\s*oz|pinch(?:es)?|
     large|medium|small|cloves?|whole|slices?|pieces?|sticks?|
     cans?|packages?|pkg|bunches?|sprigs?|stalks?|
     handfuls?|dashes?|drops?)?\s*
    (.+)?$""",
    re.IGNORECASE | re.VERBOSE
)

def parse_fraction(s: str) -> float:
    """Parse '1 1/2', '2/3', '1.5' etc. into a float."""
    s = s.strip()
    # Replace unicode fractions
    def replace_uf(m):
        return str(UNICODE_FRACTIONS[m.group(0)])
    s = FRAC_RE.sub(replace_uf, s)

    # Handle 'whole number fraction' like '1 1/2'
    parts = s.split()
    total = 0.0
    for part in parts:
        if "/" in part:
            n, d = part.split("/", 1)
            try:
                total += float(n) / float(d)
            except (ValueError, ZeroDivisionError):
                pass
        else:
            try:
                total += float(part)
            except ValueError:
                pass
    return total


def parse_ingredient_string(raw: str):
    """
    Returns (qty_float, unit_str, ingredient_str, notes_str).
    E.g. '2 1/4 cups all-purpose flour, spooned and levelled'
      -> (2.25, 'cups', 'all-purpose flour', 'spooned and levelled')
    """
    raw = raw.strip()
    # Strip parenthetical notes
    note_match = re.search(r"\(([^)]+)\)", raw)
    note = note_match.group(1) if note_match else ""
    clean = re.sub(r"\([^)]+\)", "", raw).strip()

    # Comma-separated note (e.g. "butter, softened")
    comma_note = ""
    if "," in clean:
        parts = clean.split(",", 1)
        clean = parts[0].strip()
        comma_note = parts[1].strip()
    note = (note + " " + comma_note).strip() if (note or comma_note) else ""

    m = UNITS_RE.match(clean)
    if not m:
        return (0, "", raw, "")

    qty_str  = m.group(1).strip()
    unit_str = (m.group(2) or "").strip()
    ingr_str = (m.group(3) or "").strip().rstrip(".")

    qty = parse_fraction(qty_str) if qty_str else 0

    # Normalise units
    unit_lower = unit_str.lower()
    if unit_lower in ("cup", "cups"):          unit_str = "cup"
    elif unit_lower in ("tbsp", "tablespoon", "tablespoons", "tbsps"): unit_str = "tbsp"
    elif unit_lower in ("tsp", "teaspoon", "teaspoons", "tsps"):       unit_str = "tsp"
    elif unit_lower in ("oz", "ounce", "ounces"):                       unit_str = "oz"
    elif unit_lower in ("lb", "lbs", "pound", "pounds"):               unit_str = "lb"
    elif unit_lower in ("g", "gram", "grams"):                         unit_str = "g"
    elif unit_lower in ("kg", "kilogram", "kilograms"):                unit_str = "kg"
    elif unit_lower in ("ml", "milliliter", "milliliters"):            unit_str = "ml"
    elif unit_lower in ("l", "liter", "litre", "liters", "litres"):   unit_str = "l"

    return (qty, unit_str, ingr_str or raw, note)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — METRIC CONVERSION
# ─────────────────────────────────────────────────────────────────────────────

# Grams per 1 cup (based on standard scooped or spooned measurements)
GRAMS_PER_CUP = {
    "all-purpose flour":          120,
    "flour":                      120,
    "whole wheat flour":          130,
    "bread flour":                120,
    "almond flour":               96,
    "cocoa powder":               85,
    "granulated sugar":           200,
    "granulated white sugar":     200,
    "caster sugar":               200,
    "powdered sugar":             120,
    "icing sugar":                120,
    "brown sugar":                220,
    "light brown sugar":          220,
    "dark brown sugar":           220,
    "butter":                     227,
    "vegetable oil":              218,
    "olive oil":                  216,
    "honey":                      340,
    "maple syrup":                322,
    "milk":                       245,
    "heavy cream":                238,
    "sour cream":                 230,
    "yogurt":                     245,
    "rolled oats":                90,
    "oats":                       90,
    "rice":                       185,
    "chocolate chips":            170,
    "semi-sweet chocolate chips": 170,
    "chopped nuts":               120,
    "walnuts":                    120,
    "chopped walnuts":            120,
    "pecans":                     110,
    "almonds":                    143,
    "raisins":                    165,
    "breadcrumbs":                108,
    "panko":                      60,
    "parmesan":                   100,
    "shredded cheese":            113,
    "cornstarch":                 128,
    "baking powder":              230,   # density ~per cup
    "baking soda":                274,
}

# Grams per 1 tsp of dense powders / small measures
GRAMS_PER_TSP = {
    "baking soda":      6,
    "baking powder":    4,
    "salt":             6,
    "cinnamon":         2.6,
    "cumin":            2.5,
    "paprika":          2.3,
    "turmeric":         3.0,
    "chili powder":     2.5,
    "garlic powder":    3.1,
    "onion powder":     2.5,
    "dried oregano":    1.5,
    "dried thyme":      1.4,
    "black pepper":     2.3,
    "cayenne":          2.0,
    "vanilla extract":  4.2,
    "cream of tartar":  3.0,
    "cornstarch":       2.5,
    "yeast":            4.0,
}

OZ_TO_G = 28.35
LB_TO_G = 453.592


def find_density(ingredient: str, table: dict) -> float | None:
    """Fuzzy lookup: return density value if ingredient matches any key."""
    ingr_lower = ingredient.lower()
    # Exact
    if ingr_lower in table:
        return table[ingr_lower]
    # Partial match: key is substring of ingredient or vice versa
    for key, val in table.items():
        if key in ingr_lower or ingr_lower in key:
            return val
    return None


def convert_to_metric(qty: float, unit: str, ingredient: str):
    """Returns (metric_qty, metric_unit) or original if no conversion known."""
    u = unit.lower()

    if u == "cup":
        density = find_density(ingredient, GRAMS_PER_CUP)
        if density:
            return (round(qty * density), "g")
        return (round(qty * 240), "ml")   # fallback: volume

    if u in ("tbsp",):
        density = find_density(ingredient, GRAMS_PER_TSP)
        if density:
            return (round(qty * density * 3, 1), "g")
        return (round(qty * 15, 1), "ml")

    if u in ("tsp",):
        density = find_density(ingredient, GRAMS_PER_TSP)
        if density:
            return (round(qty * density, 1), "g")
        return (round(qty * 5, 1), "ml")

    if u == "oz":
        return (round(qty * OZ_TO_G), "g")

    if u == "lb":
        return (round(qty * LB_TO_G), "g")

    if u in ("g", "kg", "ml", "l"):
        return (qty, unit)   # already metric

    return (qty, unit)   # count / unknown


def build_metric_rows(raw_ingredients: list) -> list:
    rows = []
    for raw in raw_ingredients:
        qty, unit, ingredient, note = parse_ingredient_string(raw)
        m_qty, m_unit = convert_to_metric(qty, unit, ingredient)

        def fmt(v, u):
            if v == 0 and not u:
                return raw   # unparseable — show original
            v_str = str(int(v)) if isinstance(v, (int, float)) and v == int(v) else str(v)
            return f"{v_str} {u}".strip() if u else v_str

        rows.append({
            "ingredient": ingredient,
            "original":   fmt(qty, unit),
            "metric":     fmt(m_qty, m_unit),
            "note":       note,
        })
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — PDF GENERATION  (same engine as recipe_to_pdf.py)
# ─────────────────────────────────────────────────────────────────────────────

ACCENT   = colors.HexColor("#1A1A1A")
DARK     = colors.HexColor("#1A1A1A")
LIGHT_BG = colors.HexColor("#F4F4F4")
MID_GREY = colors.HexColor("#666666")
RULE_CLR = colors.HexColor("#CCCCCC")
PAGE_W, PAGE_H = A4
MARGIN = 12 * mm


def build_styles():
    base = getSampleStyleSheet()
    def ps(name, parent="Normal", **kw):
        return ParagraphStyle(name, parent=base[parent], **kw)

    return {
        "title":      ps("T",  fontSize=30, leading=36, textColor=DARK,
                          spaceAfter=1*mm, fontName="Lora-Italic"),
        "source":     ps("S",  fontSize=9,  textColor=MID_GREY,
                          spaceAfter=5*mm, fontName="Poppins"),
        "desc":       ps("D",  fontSize=10.5, leading=16, textColor=DARK,
                          spaceAfter=3*mm, fontName="Lora-Italic"),
        "section":    ps("H",  fontSize=9.5, leading=14, textColor=DARK,
                          spaceBefore=7*mm, spaceAfter=3*mm,
                          fontName="Poppins-Bold", charSpace=1.5),
        "step_label": ps("SL", fontSize=9.5, textColor=DARK,
                          fontName="Poppins-Bold", charSpace=0.5, spaceAfter=1*mm),
        "step_body":  ps("SB", fontSize=10, leading=15.5, textColor=DARK,
                          fontName="Lora", spaceAfter=4.5*mm),
        "note_label": ps("NL", fontSize=9.5, fontName="Poppins-Bold",
                          textColor=DARK, charSpace=0.5, spaceAfter=1*mm),
        "note_body":  ps("NB", fontSize=10, leading=15.5, textColor=DARK,
                          fontName="Lora", spaceAfter=4.5*mm),
        "meta":       ps("M",  fontSize=8.5, textColor=MID_GREY,
                          fontName="Lora-Italic", alignment=TA_CENTER),
    }


def make_meta_bar(recipe):
    lbl = ParagraphStyle("MetaLbl", fontName="Poppins-Bold", fontSize=7.5,
                         textColor=ACCENT, alignment=1, charSpace=0.8, spaceAfter=1)
    val = ParagraphStyle("MetaVal", fontName="Lora", fontSize=10,
                         textColor=DARK, alignment=1)

    def cell(label, value):
        return [Paragraph(label.upper(), lbl), Paragraph(value, val)]

    data = [[
        cell("Prep",  recipe["prep_time"]),
        cell("Cook",  recipe["cook_time"]),
        cell("Total", recipe["total_time"]),
        cell("Yield", recipe["yield"]),
    ]]
    col_w = (PAGE_W - 2 * MARGIN) / 4
    t = Table(data, colWidths=[col_w]*4, rowHeights=[16*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND",   (0,0),(-1,-1), LIGHT_BG),
        ("BOX",          (0,0),(-1,-1), 0.75, RULE_CLR),
        ("INNERGRID",    (0,0),(-1,-1), 0.5,  RULE_CLR),
        ("ALIGN",        (0,0),(-1,-1), "CENTER"),
        ("VALIGN",       (0,0),(-1,-1), "MIDDLE"),
        ("TOPPADDING",   (0,0),(-1,-1), 5),
        ("BOTTOMPADDING",(0,0),(-1,-1), 5),
    ]))
    return t


def _ingredient_paragraphs(rows):
    col_lbl = ParagraphStyle("IColLbl", fontName="Poppins-Bold", fontSize=7.5,
                             textColor=DARK, charSpace=1.5, spaceAfter=3*mm,
                             spaceBefore=0)
    line_style = ParagraphStyle("IngLine", fontName="Lora", fontSize=9.5,
                                leading=16, textColor=DARK,
                                spaceAfter=0, spaceBefore=0)
    items = [Paragraph("INGREDIENTS", col_lbl)]
    for r in rows:
        show_orig = r["original"] != r["metric"]
        orig_part = (
            f'  <font name="Lora-Italic" size="8.5" color="#888888">({r["original"]})</font>'
            if show_orig else ""
        )
        note_part = (
            f'  <font name="Lora-Italic" size="8.5" color="#888888">{r["note"]}</font>'
            if r["note"] else ""
        )
        line = (
            f'<font name="Poppins-Bold" size="9.5">{r["metric"]}</font>'
            f'  {r["ingredient"]}{note_part}{orig_part}'
        )
        items.append(Paragraph(line, line_style))
    return items


def make_ingredients_section(rows, styles):
    """Return a list of flowables: INGREDIENTS heading + one line per ingredient."""
    return _ingredient_paragraphs(rows)


def make_method_section(method, styles):
    """Return a list of flowables: METHOD heading + numbered steps."""
    col_lbl = ParagraphStyle("MColLbl", fontName="Poppins-Bold", fontSize=7.5,
                             textColor=DARK, charSpace=1.5, spaceAfter=3*mm,
                             spaceBefore=0)
    items = [Paragraph("METHOD", col_lbl)]
    for step_num, (label, body) in enumerate(method, start=1):
        items.append(Paragraph(f"<b>{step_num}.</b>  {label}", styles["step_label"]))
        items.append(Paragraph(body, styles["step_body"]))
    return items


def estimate_prep_time(raw_ingredients: list) -> str:
    """
    Estimate prep time from ingredient strings when the recipe omits it.
    Pantry / instant-use items score 0; fresh / active-prep items score 3 mins each.
    """
    PANTRY = {
        "salt", "sugar", "flour", "oil", "butter", "baking soda", "baking powder",
        "vanilla", "pepper", "spice", "paprika", "cumin", "cinnamon", "oregano",
        "thyme", "basil", "bay", "nutmeg", "turmeric", "cornstarch", "vinegar",
        "soy sauce", "hot sauce", "mustard", "honey", "syrup", "extract",
        "milk", "cream", "water", "broth", "stock", "canned", "can of",
        "egg", "eggs", "cheese", "chocolate chip", "yeast",
    }
    active = sum(
        1 for raw in raw_ingredients
        if not any(p in raw.lower() for p in PANTRY)
    )
    minutes = int(round((5 + active * 3) / 5) * 5)
    return f"~{max(minutes, 5)} mins (est.)"


def generate_pdf(recipe: dict, output_path: str):
    styles = build_styles()
    metric_rows = build_metric_rows(recipe["raw_ingredients"])

    # Estimate prep time if missing
    recipe = dict(recipe)
    if recipe.get("prep_time", "—") in ("—", "", None):
        recipe["prep_time"] = estimate_prep_time(recipe["raw_ingredients"])

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN,  bottomMargin=MARGIN,
        title=recipe["title"],
    )
    story = []

    story.append(Paragraph(recipe["title"], styles["title"]))
    story.append(Paragraph(
        f'Source: <a href="{recipe["url"]}" color="#1A1A1A">{recipe["source"]}</a>',
        styles["source"]
    ))
    story.append(HRFlowable(width="100%", thickness=1, color=RULE_CLR, spaceAfter=4*mm))
    if recipe["description"]:
        story.append(Paragraph(recipe["description"], styles["desc"]))
    story.append(make_meta_bar(recipe))
    story.append(Spacer(1, 5*mm))

    if recipe["raw_ingredients"]:
        for flowable in make_ingredients_section(metric_rows, styles):
            story.append(flowable)

    if recipe["method"]:
        story.append(HRFlowable(width="100%", thickness=0.5, color=RULE_CLR,
                                spaceBefore=5*mm, spaceAfter=5*mm))
        for flowable in make_method_section(recipe["method"], styles):
            story.append(flowable)

    if recipe["notes"]:
        story.append(Spacer(1, 2*mm))
        story.append(HRFlowable(width="100%", thickness=0.5, color=RULE_CLR, spaceAfter=4*mm))
        story.append(Paragraph("Notes & Tips", styles["section"]))
        for title_note, body_note in recipe["notes"]:
            story.append(KeepTogether([
                Paragraph(f"&#x2022;  {title_note}", styles["note_label"]),
                Paragraph(body_note, styles["note_body"]),
            ]))

    story.append(Spacer(1, 4*mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=RULE_CLR, spaceAfter=2*mm))
    story.append(Paragraph(
        "Measurements converted from US volume to metric weight. "
        "A kitchen scale gives the most consistent results.",
        styles["meta"]
    ))

    doc.build(story)
    print(f"Saved: {output_path}")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: python recipe_scraper.py <recipe-url-or-html-file>")
        print("  URL:  python recipe_scraper.py https://www.allrecipes.com/recipe/10813/")
        print("  File: python recipe_scraper.py ~/Downloads/recipe.html  (for blocked sites)")
        sys.exit(1)

    url = sys.argv[1]
    print(f"Fetching: {url}")

    jsonld   = fetch_recipe_jsonld(url)
    recipe   = jsonld_to_recipe(jsonld, url)

    print(f"Found: {recipe['title']}")
    print(f"Ingredients: {len(recipe['raw_ingredients'])}")
    print(f"Steps: {len(recipe['method'])}")

    # Build output filename from recipe title
    safe_name = re.sub(r"[^a-z0-9]+", "_", recipe["title"].lower()).strip("_")
    out_path  = os.path.join(os.path.dirname(__file__), f"{safe_name}_metric.pdf")

    generate_pdf(recipe, out_path)


if __name__ == "__main__":
    main()
