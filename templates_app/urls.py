from django.urls import path
from . import views

app_name = "templates_app"

urlpatterns = [
    path("", views.template_list, name="list"),
    path("import/", views.template_import, name="import"),
    path("<uuid:template_id>/editor/", views.template_editor, name="editor"),
    path("<uuid:template_id>/copy/", views.copy_template, name="copy"),
    path("<uuid:template_id>/issues/", views.template_import_issues, name="import_issues"),
    path("comment/<uuid:comment_id>/save/", views.save_comment, name="save_comment"),
]
