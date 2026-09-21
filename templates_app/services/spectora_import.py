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

Performance note: writes are batched with bulk_create (one INSERT per
table, not one per row) inside a single transaction. With a remote DB
(Supabase) each individual round-trip costs real latency — a 366-row
import done as 366 separate .create() calls can take well over a minute;
batched, it's a handful of round-trips regardless of row count.
"""
import html
import openpyxl
from django.db import transaction

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


@transaction.atomic
def import_spectora_export(file_obj, template_name, source_file_name):
    """
    Parses the uploaded file and creates a Template with its full
    Section > Item > Comment tree. Returns (template, issues_list).
    """
    wb = openpyxl.load_workbook(file_obj, data_only=True, read_only=True)
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

    issue_rows = []  # collected as plain dicts, bulk_created once at the end

    def log(row_number, column_name, message, severity="warning"):
        issue_rows.append(dict(
            template=template, row_number=row_number, column_name=column_name,
            severity=severity, message=message,
        ))

    for expected in EXPECTED_HEADERS:
        if expected not in col_index:
            log(None, expected, f"Column '{expected}' was not found in this export — left blank for all rows.", "warning")

    data_rows = [r for r in rows[1:] if r is not None and not all(v is None for v in r)]

    # ---- Pass 1: figure out the unique, ordered Section and Item names ----
    section_names_in_order = []
    seen_sections = set()
    item_keys_in_order = []  # (section_name, item_name), first-seen order
    seen_items = set()

    for row_number, row in enumerate(data_rows, start=2):
        section_name = cell(row, "Section Name")
        if not section_name:
            continue  # logged again in pass 2, skip here to avoid double-logging
        if section_name not in seen_sections:
            seen_sections.add(section_name)
            section_names_in_order.append(section_name)

        item_name = cell(row, "Item Name") or "General"
        key = (section_name, item_name)
        if key not in seen_items:
            seen_items.add(key)
            item_keys_in_order.append(key)

    # ---- Bulk-create Sections, then look them back up by name ----
    Section.objects.bulk_create([
        Section(template=template, name=name, order=i + 1)
        for i, name in enumerate(section_names_in_order)
    ])
    sections_by_name = {
        s.name: s for s in Section.objects.filter(template=template)
    }

    # ---- Bulk-create Items, then look them back up by (section, name) ----
    item_order_counters = {}
    item_instances = []
    for section_name, item_name in item_keys_in_order:
        item_order_counters[section_name] = item_order_counters.get(section_name, 0) + 1
        item_instances.append(Item(
            section=sections_by_name[section_name],
            name=item_name,
            order=item_order_counters[section_name],
        ))
    Item.objects.bulk_create(item_instances)

    items_by_key = {}
    for item in Item.objects.filter(section__template=template).select_related("section"):
        items_by_key[(item.section.name, item.name)] = item

    # ---- Pass 2: build Comment rows (in memory) against the now-known items ----
    comment_instances = []
    for row_number, row in enumerate(data_rows, start=2):
        section_name = cell(row, "Section Name")
        if not section_name:
            log(row_number, "Section Name", "Row skipped — no Section Name value.", "error")
            continue

        item_name = cell(row, "Item Name") or "General"
        item = items_by_key[(section_name, item_name)]
        comment_name = cell(row, "Comment Name")

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
            comment_kwargs[f"photo_{n}_url"] = url
            comment_kwargs[f"photo_{n}_caption"] = caption
            if url:
                has_photo = True

        comment_instances.append(Comment(**comment_kwargs))
        if has_photo:
            log(row_number, "Default Photo", "Default photo referenced in export — URL/caption stored, image itself not fetched.", "info")

    Comment.objects.bulk_create(comment_instances, batch_size=500)

    # ---- Bulk-create all logged issues in one shot ----
    issues = [ImportIssue(**kwargs) for kwargs in issue_rows]
    ImportIssue.objects.bulk_create(issues)

    return template, issues
