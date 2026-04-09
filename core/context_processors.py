from users.models import UserRole
from tiendas.models import Tienda


def user_role(request):
    permissions = {
        'ventas':     0,
        'compras':    0,
        'inventario': 0,
        'usuarios':   0,
        'reportes':   0,
    }
    roles = []

    if request.user.is_authenticated:
        try:
            user_role_obj = UserRole.objects.select_related('role').get(user=request.user)
            role = user_role_obj.role
            roles = [role.role_name]

            for module in permissions.keys():
                permissions[module] = getattr(role, module, 0)

        except UserRole.DoesNotExist:
            pass

    return {'permissions': permissions, 'roles': roles}


from tiendas.models import Tienda

def tienda_context(request):
    """Agrega la tienda del usuario al contexto global"""
    if request.user.is_authenticated and hasattr(request.user, 'tienda'):
        return {'user_tienda': request.user.tienda}
    return {'user_tienda': None}