import uuid
from django.db import models


class Template(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    source_file_name = models.CharField(max_length=255, blank=True, null=True)
    source_template_note = models.TextField(
        blank=True,
        help_text="Which template this was exported from, and where it came from.",
    )
    copied_from = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="copies"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.name

    @property
    def section_count(self):
        return self.sections.count()

    @property
    def item_count(self):
        return sum(s.items.count() for s in self.sections.all())

    @property
    def comment_count(self):
        return sum(i.comments.count() for s in self.sections.all() for i in s.items.all())


class Section(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    template = models.ForeignKey(Template, on_delete=models.CASCADE, related_name="sections")
    name = models.CharField(max_length=255)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"{self.template.name} / {self.name}"


class Item(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name="items")
    name = models.CharField(max_length=255)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"{self.section.name} / {self.name}"


class Comment(models.Model):
    COMMENT_TYPE_CHOICES = [
        ("info", "Info"),
        ("limit", "Limit"),
        ("defect", "Defect"),
    ]
    CATEGORY_CHOICES = [
        (-1, "Low"),
        (0, "Med"),
        (1, "High"),
    ]
    ANSWER_TYPE_CHOICES = [
        ("boolean", "Boolean"),
        ("checkbox", "Checkbox"),
        ("date", "Date"),
        ("number", "Number"),
        ("range", "Range"),
        ("text", "Text"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="comments")
    order = models.PositiveIntegerField(default=0)

    # --- Core spreadsheet columns (1:1 with the Spectora export) ---
    name = models.CharField(max_length=500, blank=True)  # Comment Name
    text_html = models.TextField(blank=True)              # Comment Text (raw HTML preserved)
    comment_type = models.CharField(
        max_length=10, choices=COMMENT_TYPE_CHOICES, blank=True
    )  # Comment Type (info, limit, defect)
    category = models.SmallIntegerField(
        choices=CATEGORY_CHOICES, blank=True, null=True
    )  # Category (-1/0/1)
    multiple_choice_options = models.TextField(blank=True)  # comma-separated
    unit_type_options = models.TextField(blank=True)        # comma-separated, numeric
    recommendation = models.TextField(blank=True)           # from list
    answer_type = models.CharField(
        max_length=20, choices=ANSWER_TYPE_CHOICES, blank=True
    )
    default_value = models.TextField(blank=True)
    default_value_2 = models.TextField(blank=True)          # for "range" types
    default_unit_type = models.CharField(max_length=100, blank=True)
    default_location = models.CharField(max_length=255, blank=True)
    default_estimate_min = models.DecimalField(
        max_digits=12, decimal_places=2, blank=True, null=True
    )
    default_estimate_max = models.DecimalField(
        max_digits=12, decimal_places=2, blank=True, null=True
    )
    locked = models.BooleanField(default=False)
    simple_format = models.BooleanField(default=False)
    disable_photos = models.BooleanField(default=False)
    uses = models.PositiveIntegerField(blank=True, null=True)

    # Default Photo 1-10 (url + caption pairs) — not imported (no image fetch in v1),
    # kept as fields so nothing is silently dropped from the schema; importer
    # records the raw URL/caption text even though it doesn't fetch the image.
    photo_1_url = models.URLField(max_length=1000, blank=True)
    photo_1_caption = models.CharField(max_length=500, blank=True)
    photo_2_url = models.URLField(max_length=1000, blank=True)
    photo_2_caption = models.CharField(max_length=500, blank=True)
    photo_3_url = models.URLField(max_length=1000, blank=True)
    photo_3_caption = models.CharField(max_length=500, blank=True)
    photo_4_url = models.URLField(max_length=1000, blank=True)
    photo_4_caption = models.CharField(max_length=500, blank=True)
    photo_5_url = models.URLField(max_length=1000, blank=True)
    photo_5_caption = models.CharField(max_length=500, blank=True)
    photo_6_url = models.URLField(max_length=1000, blank=True)
    photo_6_caption = models.CharField(max_length=500, blank=True)
    photo_7_url = models.URLField(max_length=1000, blank=True)
    photo_7_caption = models.CharField(max_length=500, blank=True)
    photo_8_url = models.URLField(max_length=1000, blank=True)
    photo_8_caption = models.CharField(max_length=500, blank=True)
    photo_9_url = models.URLField(max_length=1000, blank=True)
    photo_9_caption = models.CharField(max_length=500, blank=True)
    photo_10_url = models.URLField(max_length=1000, blank=True)
    photo_10_caption = models.CharField(max_length=500, blank=True)

    last_modified_source = models.CharField(
        max_length=255, blank=True, help_text="Raw 'Last Modified' value from the export."
    )

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.name or f"Comment {self.id}"


class ImportIssue(models.Model):
    """
    Records anything the importer skipped, couldn't map, or didn't support,
    so it's visible to the user instead of silently dropped.
    """
    SEVERITY_CHOICES = [
        ("info", "Info"),
        ("warning", "Warning"),
        ("error", "Error"),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    template = models.ForeignKey(Template, on_delete=models.CASCADE, related_name="import_issues")
    row_number = models.PositiveIntegerField(blank=True, null=True)
    column_name = models.CharField(max_length=255, blank=True)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default="info")
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["row_number"]

    def __str__(self):
        return f"{self.severity}: {self.message[:50]}"
