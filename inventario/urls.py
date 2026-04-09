from django.urls import path
from . import views

app_name = 'inventario'

urlpatterns = [
    # Productos
    path('',                   views.producto_list,          name='producto_list'),
    path('crear/',             views.producto_create,        name='producto_create'),
    path('<int:pk>/editar/',   views.producto_edit,          name='producto_edit'),
    path('<int:pk>/eliminar/', views.producto_delete,        name='producto_delete'),
    path('bulk/',              views.producto_bulk_upload,   name='producto_bulk_upload'),
    path('bulk/template/',     views.download_template_producto, name='download_template'),

    # Categorías
    path('categorias/',                  views.categoria_list,   name='categoria_list'),
    path('categorias/crear/',            views.categoria_create, name='categoria_create'),
    path('categorias/<int:pk>/editar/',  views.categoria_edit,   name='categoria_edit'),
    path('categorias/<int:pk>/eliminar/', views.categoria_delete, name='categoria_delete'),

    # Proveedores
    path('proveedores/',                   views.proveedor_list,   name='proveedor_list'),
    path('proveedores/crear/',             views.proveedor_create, name='proveedor_create'),
    path('proveedores/<int:pk>/editar/',   views.proveedor_edit,   name='proveedor_edit'),
    path('proveedores/<int:pk>/eliminar/', views.proveedor_delete, name='proveedor_delete'),


    # Stock
    path('stock/',                  views.stock_list,    name='stock_list'),
    path('stock/entrada/',          views.stock_entrada, name='stock_entrada'),
    path('stock/movimientos/',      views.stock_movimientos, name='stock_movimientos'),

    # Ajustes de inventario
    path('ajustes/',                    views.ajuste_inventario,     name='ajuste_inventario'),
    path('ajustes/historial/',          views.historial_ajustes,     name='historial_ajustes'),
]