from django.contrib import admin
from .models import Tienda

@admin.register(Tienda)
class TiendaAdmin(admin.ModelAdmin):
    list_display = ['id', 'nombre', 'slug', 'direccion', 'telefono', 'email', 'activa', 'fecha_creacion']
    list_editable = ['activa']
    list_filter = ['activa', 'fecha_creacion']
    search_fields = ['nombre', 'slug', 'direccion', 'telefono', 'email']
    prepopulated_fields = {'slug': ('nombre',)}
    readonly_fields = ['fecha_creacion']
    
    fieldsets = (
        ('Información básica', {
            'fields': ('nombre', 'slug', 'activa')
        }),
        ('Información de contacto', {
            'fields': ('direccion', 'telefono', 'email')
        }),
        ('Logo', {
            'fields': ('logo',),
            'classes': ('collapse',)
        }),
        ('Información del sistema', {
            'fields': ('fecha_creacion',),
            'classes': ('collapse',)
        }),
    )