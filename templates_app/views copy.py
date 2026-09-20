from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib import messages

from .models import Template, Comment, Section, Item
from .forms import TemplateImportForm
from .services.spectora_import import import_spectora_export


def template_list(request):
    templates = Template.objects.all()
    return render(request, "templates_app/list.html", {"templates": templates, "active": "templates"})


def template_import(request):
    imported_template = None
    issues = []

    if request.method == "POST":
        form = TemplateImportForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded = request.FILES["export_file"]
            name = form.cleaned_data.get("template_name") or uploaded.name.rsplit(".", 1)[0]
            try:
                imported_template, issues = import_spectora_export(
                    uploaded, template_name=name, source_file_name=uploaded.name
                )
                messages.success(request, f'Imported "{imported_template.name}".')
            except Exception as e:
                messages.error(request, f"Import failed: {e}")
    else:
        form = TemplateImportForm()

    return render(request, "templates_app/import.html", {
        "form": form,
        "imported_template": imported_template,
        "issues": issues,
        "active": "templates",
    })


def template_import_issues(request, template_id):
    template = get_object_or_404(Template, id=template_id)
    return render(request, "templates_app/import_issues.html", {
        "template": template,
        "issues": template.import_issues.all(),
        "active": "templates",
    })


def template_editor(request, template_id):
    template = get_object_or_404(Template, id=template_id)

    section_id = request.GET.get("section")
    item_id = request.GET.get("item")

    selected_section = None
    selected_item = None
    if section_id and section_id != "overview":
        selected_section = template.sections.filter(id=section_id).first()
        if selected_section and item_id:
            selected_item = selected_section.items.filter(id=item_id).first()

    return render(request, "templates_app/editor.html", {
        "template": template,
        "selected_section": selected_section,
        "selected_section_id": section_id,
        "selected_item": selected_item,
        "selected_item_id": item_id,
        "comment_type_choices": Comment.COMMENT_TYPE_CHOICES,
        "category_choices": Comment.CATEGORY_CHOICES,
        "active": "templates",
    })


def save_comment(request, comment_id):
    comment = get_object_or_404(Comment, id=comment_id)
    if request.method == "POST":
        comment.name = request.POST.get("name", comment.name)
        comment.text_html = request.POST.get("text_html", comment.text_html)
        comment.comment_type = request.POST.get("comment_type", comment.comment_type)
        category = request.POST.get("category")
        comment.category = int(category) if category not in (None, "") else None
        comment.save()
        messages.success(request, "Saved.")

    section = comment.item.section
    template = section.template
    base_url = reverse("templates_app:editor", args=[template.id])
    return redirect(f"{base_url}?section={section.id}&item={comment.item.id}")


def copy_template(request, template_id):
    original = get_object_or_404(Template, id=template_id)
    if request.method == "POST":
        copy = Template.objects.create(
            name=f"{original.name} (copy)",
            source_file_name=original.source_file_name,
            copied_from=original,
        )
        for section in original.sections.all():
            new_section = _clone(section, template=copy)
            for item in section.items.all():
                new_item = _clone(item, section=new_section)
                for comment in item.comments.all():
                    _clone(comment, item=new_item)
        messages.success(request, f'Duplicated as "{copy.name}".')
    return redirect("templates_app:list")


def delete_template(request, template_id):
    template = get_object_or_404(Template, id=template_id)
    if request.method == "POST":
        name = template.name
        template.delete()
        messages.success(request, f'Deleted "{name}".')
    return redirect("templates_app:list")


def save_section(request, section_id):
    section = get_object_or_404(Section, id=section_id)
    if request.method == "POST":
        section.name = request.POST.get("name", section.name)
        section.save()
        messages.success(request, "Saved.")
    base_url = reverse("templates_app:editor", args=[section.template.id])
    return redirect(f"{base_url}?section={section.id}")


def save_item(request, item_id):
    item = get_object_or_404(Item, id=item_id)
    if request.method == "POST":
        item.name = request.POST.get("name", item.name)
        item.save()
        messages.success(request, "Saved.")
    section = item.section
    base_url = reverse("templates_app:editor", args=[section.template.id])
    return redirect(f"{base_url}?section={section.id}&item={item.id}")


def _clone(instance, **override_fk):
    """Copies a model instance's fields into a new row, leaving the original untouched."""
    model = instance.__class__
    data = {
        f.name: getattr(instance, f.name)
        for f in model._meta.fields
        if f.name not in ("id",) and f.name not in override_fk
    }
    data.update(override_fk)
    return model.objects.create(**data)
