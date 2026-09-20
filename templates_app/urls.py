from django.urls import path
from . import views

urlpatterns = [
    path('', views.template_list, name='template_list'),
]