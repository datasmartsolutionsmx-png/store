# core/urls.py
from django.urls import path
from . import views          # ← punto = esta misma app (core)

urlpatterns = [
    path('dashboard/', views.dashboard_view, name='dashboard'),
    
]