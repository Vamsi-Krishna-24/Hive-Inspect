from django import template

register = template.Library()


@register.filter
def split_comma(value):
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]
