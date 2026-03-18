"""
Recipe PDF Server
=================
A small local server that powers the browser extension.
It receives recipe JSON-LD extracted by the extension from any recipe page,
converts measurements to metric, and returns a polished PDF.

SETUP
─────
  pip install flask flask-cors
  (requests, beautifulsoup4, reportlab already required by recipe_scraper.py)

RUN
───
  python server.py

Then install the browser extension from the recipe_extension/ folder.
The server listens on http://localhost:5432 — keep this terminal open
while using the extension.
"""

import importlib
import importlib.util
import json
import re
import os
import subprocess
import sys
import tempfile

# Auto-install missing dependencies
_REQUIRED = ["flask", "flask_cors", "requests", "bs4", "reportlab"]
_INSTALL = {"flask_cors": "flask-cors", "bs4": "beautifulsoup4"}
for _pkg in _REQUIRED:
    if importlib.util.find_spec(_pkg) is None:
        _pip_name = _INSTALL.get(_pkg, _pkg)
        print(f"Installing {_pip_name}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", _pip_name])

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS

# recipe_scraper.py must be in the same folder as this script
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import recipe_scraper as rs  # noqa: E402  (import after path setup)

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def find_recipe_in_jsonld(blocks: list) -> dict | None:
    """Search a list of raw JSON-LD strings for a schema.org/Recipe object."""
    for block_str in blocks:
        try:
            data = json.loads(block_str or "")
        except (json.JSONDecodeError, TypeError):
            continue

        items = data if isinstance(data, list) else [data]

        # Unwrap @graph (WordPress / Yoast pattern)
        for item in items:
            if isinstance(item, dict) and "@graph" in item:
                items = item["@graph"]
                break

        for item in items:
            if not isinstance(item, dict):
                continue
            rtype = item.get("@type", "")
            if isinstance(rtype, list):
                rtype = " ".join(rtype)
            if "Recipe" in rtype:
                return item

    return None


# ─────────────────────────────────────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "version": "1.0"})


@app.route("/convert", methods=["POST"])
def convert():
    """
    Accepts JSON body:
      {
        "jsonld_blocks": ["<raw JSON-LD string>", ...],
        "url": "https://..."          // original page URL
      }
    Returns the generated PDF as application/pdf.
    """
    body = request.get_json(silent=True) or {}
    url = body.get("url", "unknown")
    blocks = body.get("jsonld_blocks", [])

    if not blocks:
        return jsonify({"error": "No JSON-LD blocks provided"}), 400

    recipe_data = find_recipe_in_jsonld(blocks)
    if not recipe_data:
        return jsonify({
            "error": "No recipe found on this page. "
                     "The site may not use schema.org/Recipe markup."
        }), 404

    try:
        recipe = rs.jsonld_to_recipe(recipe_data, url)
    except Exception as exc:
        return jsonify({"error": f"Failed to parse recipe: {exc}"}), 500

    # Write PDF to a temp file, then stream it back
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp_path = tmp.name
        rs.generate_pdf(recipe, tmp_path)
    except Exception as exc:
        return jsonify({"error": f"PDF generation failed: {exc}"}), 500

    import re
    safe_name = re.sub(r"[^a-z0-9]+", "_", recipe["title"].lower()).strip("_")
    download_name = f"{safe_name}_metric.pdf"

    return send_file(
        tmp_path,
        as_attachment=True,
        download_name=download_name,
        mimetype="application/pdf",
    )


# ─────────────────────────────────────────────────────────────────────────────
# APPLE NOTES
# ─────────────────────────────────────────────────────────────────────────────

def _h(text: str) -> str:
    """Escape text for HTML."""
    return (text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;"))


def recipe_to_html(recipe: dict) -> str:
    """
    Format a recipe dict as Apple Notes-compatible HTML.
    Notes expects a full HTML document with UTF-8 charset to render
    headings, bold, italic, and lists correctly.
    """
    body_parts = []

    BR = "<br>"

    # Note: title is omitted from the body — Apple Notes already renders
    # the note's `name` property as a heading at the top of every note.

    body_parts.append(BR)

    # ── Source line
    if recipe.get("source") and recipe["source"] != recipe.get("url", ""):
        body_parts.append(f"<p><i>By {_h(recipe['source'])}</i></p>")

    # ── Description
    if recipe.get("description"):
        body_parts.append(f"<p>{_h(recipe['description'])}</p>")

    # ── Meta: Prep / Cook / Total / Yield
    meta = []
    if recipe.get("prep_time")  and recipe["prep_time"]  != "—": meta.append(("Prep",  recipe["prep_time"]))
    if recipe.get("cook_time")  and recipe["cook_time"]  != "—": meta.append(("Cook",  recipe["cook_time"]))
    if recipe.get("total_time") and recipe["total_time"] != "—": meta.append(("Total", recipe["total_time"]))
    if recipe.get("yield")      and recipe["yield"]      != "—": meta.append(("Yield", recipe["yield"]))
    if meta:
        cells = "&nbsp;&nbsp;·&nbsp;&nbsp;".join(
            f"<b>{_h(label)}:</b> {_h(value)}" for label, value in meta
        )
        body_parts.append(f"<p>{cells}</p>")

    body_parts.append(BR)

    # ── Ingredients (bulleted list, metric bold, original US in grey italic)
    raw_ingredients = recipe.get("raw_ingredients", [])
    if raw_ingredients:
        metric_rows = rs.build_metric_rows(raw_ingredients)
        body_parts.append("<h2>Ingredients</h2>")
        body_parts.append("<ul>")
        for row in metric_rows:
            qty  = f"<b>{_h(row['metric'])}</b>&nbsp;" if row["metric"] else ""
            name = _h(row["ingredient"])
            note = f" <i>{_h(row['note'])}</i>" if row.get("note") else ""
            orig = (f" <i>({_h(row['original'])})</i>"
                    if row["original"] != row["metric"] and row["original"] else "")
            body_parts.append(f"<li>{qty}{name}{note}{orig}</li>")
        body_parts.append("</ul>")
        body_parts.append(BR)

    # ── Method (numbered list, with section sub-headings if present)
    method = recipe.get("method", [])
    if method:
        body_parts.append("<h2>Method</h2>")

        # Detect whether steps carry section prefixes like "Sauce — Step 1"
        _SEC_RE = re.compile(r"^(.+?)\s+—\s+Step\s+\d+$", re.IGNORECASE)

        def parse_step(label, step_body):
            """Return (section_name_or_None, display_label, body)."""
            m = _SEC_RE.match(label or "")
            if m:
                return m.group(1).strip(), None, step_body
            # Descriptive label (not "Step N")
            if label and not re.match(r"^Step\s+\d+$", label, re.IGNORECASE):
                return None, label, step_body
            return None, None, step_body

        current_section = "__NONE__"   # sentinel so first iteration always opens a list
        in_list = False

        for label, step_body in method:
            section, display_label, body = parse_step(label, step_body)

            if section != current_section:
                # Close previous list if open
                if in_list:
                    body_parts.append("</ol>")
                    in_list = False
                current_section = section
                if section:
                    body_parts.append(f"<h3>{_h(section)}</h3>")
                body_parts.append("<ol>")
                in_list = True

            if display_label:
                body_parts.append(f"<li><b>{_h(display_label)}</b><br>{_h(body)}</li>")
            else:
                body_parts.append(f"<li>{_h(body)}</li>")

        if in_list:
            body_parts.append("</ol>")
        body_parts.append(BR)

    # ── Notes / Tips
    notes = recipe.get("notes", [])
    if notes:
        body_parts.append("<h2>Notes &amp; Tips</h2>")
        body_parts.append("<ul>")
        for title_note, body_note in notes:
            body_parts.append(f"<li><b>{_h(title_note)}:</b> {_h(body_note)}</li>")
        body_parts.append("</ul>")
        body_parts.append(BR)

    # ── Source URL
    if recipe.get("url") and recipe["url"] != "unknown":
        url = recipe["url"]
        body_parts.append(f'<p><i>Source: <a href="{_h(url)}">{_h(url)}</a></i></p>')

    # Full HTML document — required for Notes to apply native paragraph styles
    # (Heading, Subheading, etc.). Passed via a temp file rather than inlined
    # into an AppleScript string, so Notes receives clean unescaped HTML.
    inner = "\n".join(body_parts)
    return (
        "<!DOCTYPE html>"
        "<html><head><meta charset='UTF-8'></head>"
        f"<body>{inner}</body></html>"
    )


@app.route("/apple-note", methods=["POST"])
def apple_note():
    """
    Accepts JSON body:
      {
        "jsonld_blocks": ["<raw JSON-LD string>", ...],
        "url": "https://..."
      }
    Creates an Apple Note with the recipe content via osascript.
    """
    body = request.get_json(silent=True) or {}
    url = body.get("url", "unknown")
    blocks = body.get("jsonld_blocks", [])

    if not blocks:
        return jsonify({"error": "No JSON-LD blocks provided"}), 400

    recipe_data = find_recipe_in_jsonld(blocks)
    if not recipe_data:
        return jsonify({
            "error": "No recipe found on this page. "
                     "The site may not use schema.org/Recipe markup."
        }), 404

    try:
        recipe = rs.jsonld_to_recipe(recipe_data, url)
    except Exception as exc:
        return jsonify({"error": f"Failed to parse recipe: {exc}"}), 500

    title = recipe.get("title", "Recipe")
    body_html = recipe_to_html(recipe)

    # Write HTML to a temp file so AppleScript reads it directly —
    # avoids string-escaping corruption that prevents Notes from applying
    # its native paragraph styles (Heading, Subheading, lists, etc.)
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8"
        ) as f:
            f.write(body_html)
            tmp_path = f.name

        def esc(s):
            return s.replace("\\", "\\\\").replace('"', '\\"')

        script = f'''
tell application "Notes"
    activate
    set htmlContent to (read POSIX file "{esc(tmp_path)}" as «class utf8»)
    make new note at folder "Notes" of default account ¬
        with properties {{name:"{esc(title)}", body:htmlContent}}
end tell
'''

        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return jsonify({"error": f"AppleScript error: {result.stderr.strip()}"}), 500

    except FileNotFoundError:
        return jsonify({"error": "osascript not found — are you on macOS?"}), 500
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Apple Notes took too long to respond"}), 500
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

    return jsonify({"status": "ok", "title": title})


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = 5050
    print(f"\n  Recipe PDF server running → http://localhost:{port}")
    print("  Keep this terminal open while using the browser extension.")
    print("  Press Ctrl+C to stop.\n")
    app.run(host="127.0.0.1", port=port, debug=False)
