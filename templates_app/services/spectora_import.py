"""
Parses a Spectora "Export to spreadsheet -> Export HTML Text" .xls file into
Template / Section / Item / Comment rows.

Design rules (agreed in planning):
- Read columns by HEADER NAME, never by position — so a reordered or
  differently-versioned export still works.
- Never hard-crash on unexpected data. Anything that doesn't fit cleanly
  (bad choice value, missing column, unparsable number) gets recorded as
  an ImportIssue and the field is left blank — nothing is silently dropped,
  nothing kills the whole import.
- HTML entities (&amp; etc.) show up outside the comment body too (e.g. in
  Item Name), so we unescape every text cell, not just Comment Text.
"""
import html
import openpyxl

from templates_app.models import Template, Section, Item, Comment, ImportIssue

# Exact header names from the Spectora export (row 1 of the sheet).
EXPECTED_HEADERS = [
    "Section Name", "Item Name", "Comment Name", "Comment Text",
    "Comment Type (info, limit, defect)", "Category (-1: Low, 0: Med, 1: High)",
    "Multiple Choice Options (comma-separated)",
    "Unit Type Options (numeric answers only, comma-separated)",
    "Recommendation (from list)", "Order (w/i item)",
    "Answer Type (boolean, checkbox, date, number, range, text)",
    "Default Value", "Default Value 2 (for \"range\" types)",
    "Default Unit Type (for \"number\" and \"range\" types)",
    "Default Location", "Default Estimate Min", "Default Estimate Max",
    "Locked", "Simple Format", "Disable Photos", "Uses",
] + [
    f"Default Photo {n}{suffix}"
    for n in range(1, 11)
    for suffix in ("", " Caption")
] + ["Last Modified"]

VALID_COMMENT_TYPES = {"info", "limit", "defect"}
VALID_ANSWER_TYPES = {"boolean", "checkbox", "date", "number", "range", "text"}
VALID_CATEGORIES = {"-1": -1, "0": 0, "1": 1}


def _clean(value):
    """Unescape HTML entities and normalize blanks. Works on any cell."""
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() == "none":
        return ""
    return html.unescape(text)


def _to_decimal(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value):
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _to_bool(value):
    return _clean(value).lower() in ("true", "1", "yes", "y")


def import_spectora_export(file_obj, template_name, source_file_name):
    """
    Parses the uploaded file and creates a Template with its full
    Section > Item > Comment tree. Returns (template, issues_list).
    """
    wb = openpyxl.load_workbook(file_obj, data_only=True)
    sheet = wb.active

    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        raise ValueError("The uploaded file has no rows.")

    header_row = [_clean(h) for h in rows[0]]
    col_index = {name: i for i, name in enumerate(header_row)}

    def cell(row, header_name, default=""):
        idx = col_index.get(header_name)
        if idx is None or idx >= len(row):
            return default
        return _clean(row[idx])

    template = Template.objects.create(
        name=template_name,
        source_file_name=source_file_name,
    )

    issues = []

    def log(row_number, column_name, message, severity="warning"):
        issue = ImportIssue.objects.create(
            template=template,
            row_number=row_number,
            column_name=column_name,
            severity=severity,
            message=message,
        )
        issues.append(issue)

    # Flag any expected header that's missing from this file up front.
    for expected in EXPECTED_HEADERS:
        if expected not in col_index:
            log(None, expected, f"Column '{expected}' was not found in this export — left blank for all rows.", "warning")

    sections_by_name = {}
    items_by_key = {}  # (section_name, item_name) -> Item
    section_order = 0
    item_order_by_section = {}

    for row_number, row in enumerate(rows[1:], start=2):
        if row is None or all(v is None for v in row):
            continue

        section_name = cell(row, "Section Name")
        item_name = cell(row, "Item Name")
        comment_name = cell(row, "Comment Name")

        if not section_name:
            log(row_number, "Section Name", "Row skipped — no Section Name value.", "error")
            continue

        # --- Section (create once per name) ---
        if section_name not in sections_by_name:
            section_order += 1
            sections_by_name[section_name] = Section.objects.create(
                template=template, name=section_name, order=section_order
            )
            item_order_by_section[section_name] = 0
        section = sections_by_name[section_name]

        # --- Item (create once per section+name) ---
        item_key = (section_name, item_name or "General")
        if item_key not in items_by_key:
            item_order_by_section[section_name] += 1
            items_by_key[item_key] = Item.objects.create(
                section=section,
                name=item_name or "General",
                order=item_order_by_section[section_name],
            )
        item = items_by_key[item_key]

        # --- Comment type / category with graceful fallback ---
        raw_comment_type = cell(row, "Comment Type (info, limit, defect)").lower()
        comment_type = raw_comment_type if raw_comment_type in VALID_COMMENT_TYPES else ""
        if raw_comment_type and not comment_type:
            log(row_number, "Comment Type", f"Unexpected value '{raw_comment_type}' — left blank.", "error")

        raw_category = cell(row, "Category (-1: Low, 0: Med, 1: High)")
        category = VALID_CATEGORIES.get(raw_category)
        if raw_category and category is None:
            log(row_number, "Category", f"Unexpected value '{raw_category}' — left blank.", "warning")

        raw_answer_type = cell(row, "Answer Type (boolean, checkbox, date, number, range, text)").lower()
        answer_type = raw_answer_type if raw_answer_type in VALID_ANSWER_TYPES else ""
        if raw_answer_type and not answer_type:
            log(row_number, "Answer Type", f"Unexpected value '{raw_answer_type}' — left blank.", "warning")

        comment_kwargs = dict(
            item=item,
            order=row_number,
            name=comment_name,
            text_html=cell(row, "Comment Text"),
            comment_type=comment_type,
            category=category,
            multiple_choice_options=cell(row, "Multiple Choice Options (comma-separated)"),
            unit_type_options=cell(row, "Unit Type Options (numeric answers only, comma-separated)"),
            recommendation=cell(row, "Recommendation (from list)"),
            answer_type=answer_type,
            default_value=cell(row, "Default Value"),
            default_value_2=cell(row, 'Default Value 2 (for "range" types)'),
            default_unit_type=cell(row, 'Default Unit Type (for "number" and "range" types)'),
            default_location=cell(row, "Default Location"),
            default_estimate_min=_to_decimal(cell(row, "Default Estimate Min")),
            default_estimate_max=_to_decimal(cell(row, "Default Estimate Max")),
            locked=_to_bool(cell(row, "Locked")),
            simple_format=_to_bool(cell(row, "Simple Format")),
            disable_photos=_to_bool(cell(row, "Disable Photos")),
            uses=_to_int(cell(row, "Uses")),
            last_modified_source=cell(row, "Last Modified"),
        )

        has_photo = False
        for n in range(1, 11):
            url = cell(row, f"Default Photo {n}")
            caption = cell(row, f"Default Photo {n} Caption")
            comment_kwargs[f"photo_{n}_url" if url else f"photo_{n}_url"] = url
            comment_kwargs[f"photo_{n}_caption"] = caption
            if url:
                has_photo = True

        Comment.objects.create(**comment_kwargs)

        if has_photo:
            log(row_number, "Default Photo", "Default photo referenced in export — URL/caption stored, image itself not fetched.", "info")

    return template, issues
