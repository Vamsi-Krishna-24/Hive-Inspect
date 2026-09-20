from django.contrib import admin
from .models import Template, Section, Item, Comment, ImportIssue


class SectionInline(admin.TabularInline):
    model = Section
    extra = 0


class ItemInline(admin.TabularInline):
    model = Item
    extra = 0


class CommentInline(admin.TabularInline):
    model = Comment
    extra = 0
    fields = ("name", "comment_type", "category", "order")


@admin.register(Template)
class TemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "section_count", "item_count", "comment_count", "updated_at")
    inlines = [SectionInline]


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ("name", "template", "order")
    inlines = [ItemInline]


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("name", "section", "order")
    inlines = [CommentInline]


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("name", "item", "comment_type", "category", "order")
    list_filter = ("comment_type", "category")


@admin.register(ImportIssue)
class ImportIssueAdmin(admin.ModelAdmin):
    list_display = ("template", "row_number", "column_name", "severity")
    list_filter = ("severity",)
