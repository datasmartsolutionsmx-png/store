from django import forms
from .models import Producto, Categoria, Proveedor,Tienda


class ProductoForm(forms.ModelForm):
    class Meta:
        model  = Producto
        fields = [
            'nombre', 'descripcion', 'codigo_barra', 'sku',
            'precio_compra', 'precio_venta',
            'categoria', 'proveedor', 'activo'
        ]
        
        widgets = {
            'descripcion': forms.Textarea(attrs={'rows': 3}),
        }


class CsvUploadForm(forms.Form):
    csv_file = forms.FileField(label='Archivo CSV')
    tienda = forms.ModelChoiceField(
        queryset=Tienda.objects.filter(activa=True),
        required=False,
        label='Tienda (solo para superusuario)',
        help_text='Si eres superusuario, selecciona la tienda destino. Si no, se usará tu tienda.'
    )