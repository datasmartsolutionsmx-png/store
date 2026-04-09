from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Role, UserRole

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'tienda', 'is_staff', 'is_active')
    list_filter = ('is_staff', 'is_active', 'date_joined', 'tienda')
    search_fields = ('username', 'email', 'first_name', 'last_name')
    list_editable = ('tienda',)  
    
    
    fieldsets = UserAdmin.fieldsets + (
        ('Información de tienda', {
            'fields': ('tienda',),
        }),
    )
    
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Información de tienda', {
            'fields': ('tienda',),
        }),
    )


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('role_name', 'ventas', 'compras', 'inventario', 'usuarios', 'reportes')
    list_filter = ('ventas', 'compras', 'inventario', 'usuarios', 'reportes')
    search_fields = ('role_name',)


@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    list_display = ('get_username', 'role')
    list_filter = ('role',)
    search_fields = ('user__username', 'role__role_name')

    def get_username(self, obj):
        return obj.user.username
    get_username.short_description = 'Usuario'