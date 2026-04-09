from django.urls import path
from . import views

app_name = 'reportes'

urlpatterns = [
    path('',                views.dashboard_reportes, name='dashboard'),
    path('ventas/',         views.reporte_ventas,     name='ventas'),
    path('productos/',      views.reporte_productos,  name='productos'),
    path('devoluciones/',     views.reporte_devoluciones,  name='devoluciones'),
]