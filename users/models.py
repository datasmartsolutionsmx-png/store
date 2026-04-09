from django.db import models
from django.contrib.auth.models import AbstractUser
from tiendas.models import Tienda

class User(AbstractUser):
    """
    Extendemos AbstractUser para poder agregar campos
    extra en el futuro sin romper nada.
    """

    tienda = models.ForeignKey(Tienda, on_delete=models.PROTECT, null=True, blank=True) 

    class Meta:
        db_table = 'users'
        verbose_name = 'User'
        verbose_name_plural = 'Users'

    def __str__(self):
        return self.username

    def get_role(self):
        """Retorna el rol del usuario o None si no tiene."""
        user_role = UserRole.objects.filter(user=self).first()
        return user_role.role if user_role else None

    def has_permission(self, module, level=1):
        """
        Verifica si el usuario tiene acceso a un módulo.
        Uso: user.has_permission('sales', level=2)
        """
        role = self.get_role()
        if not role:
            return False
        return getattr(role, module, 0) >= level


class Role(models.Model):
    PERMISSION_CHOICE = [
        (0, 'No access'),
        (1, 'View only'),
        (2, 'Create and modify'),
    ]

    role_name  = models.CharField(max_length=50, primary_key=True)
    ventas     = models.IntegerField(choices=PERMISSION_CHOICE, default=0)
    compras    = models.IntegerField(choices=PERMISSION_CHOICE, default=0)
    inventario = models.IntegerField(choices=PERMISSION_CHOICE, default=0)
    usuarios   = models.IntegerField(choices=PERMISSION_CHOICE, default=0)
    reportes   = models.IntegerField(choices=PERMISSION_CHOICE, default=0)

    class Meta:
        db_table = 'roles'
        verbose_name = 'Role'
        verbose_name_plural = 'Roles'

    def __str__(self):
        return self.role_name


class UserRole(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)  # ← OneToOne: un usuario, un rol
    role = models.ForeignKey(Role, on_delete=models.CASCADE)

    class Meta:
        db_table = 'user_roles'
        verbose_name = 'User Role'
        verbose_name_plural = 'User Roles'

    def __str__(self):
        return f"{self.user.username} - {self.role.role_name}"