from django import forms


class TemplateImportForm(forms.Form):
    export_file = forms.FileField()
    template_name = forms.CharField(max_length=255, required=False)
