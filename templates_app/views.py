from django.shortcuts import render

def template_list(request):
    return render(request, 'template_app/template_app.html')