from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.db import models as db_models
from django.db import transaction
from django.db.models import ProtectedError
import csv
import io

from users.models import UserRole
from .models import Producto, Categoria, Proveedor, MovimientoStock
from .forms import ProductoForm, CsvUploadForm
from tiendas.models import Tienda


def get_max_permission(user):
    """Helper para obtener el nivel de permiso del usuario en inventario."""
    return UserRole.objects.filter(
        user=user
    ).aggregate(
        max_perm=db_models.Max('role__inventario')
    )['max_perm'] or 0


def get_tienda_actual(user):
    """Retorna la tienda del usuario. Si es superadmin, retorna None (sin filtro)."""
    if user.is_superuser:
        return None
    return user.tienda


@login_required
def producto_list(request):
    max_perm = get_max_permission(request.user)
    if max_perm == 0:
        return redirect('dashboard')

    tienda_actual = get_tienda_actual(request.user)
    if tienda_actual:
        productos = Producto.objects.select_related('categoria', 'proveedor', 'creado_por').filter(tienda=tienda_actual)
    else:
        productos = Producto.objects.select_related('categoria', 'proveedor', 'creado_por').all()

    # Filtros
    nombre       = request.GET.get('nombre')
    codigo_barra = request.GET.get('codigo_barra')
    categoria_id = request.GET.get('categoria')
    activo       = request.GET.get('activo')

    if nombre:
        productos = productos.filter(nombre__icontains=nombre)
    if codigo_barra:
        productos = productos.filter(codigo_barra__icontains=codigo_barra)
    if categoria_id:
        productos = productos.filter(categoria__id=categoria_id)
    if activo in ['True', 'False']:
        productos = productos.filter(activo=(activo == 'True'))

    # Exportar CSV
    if request.GET.get('export') == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="productos.csv"'
        response.write('\ufeff'.encode('utf-8'))
        writer = csv.writer(response)
        writer.writerow([
            'Nombre', 'Descripción', 'Código de Barra', 'SKU',
            'Precio Compra', 'Precio Venta', 'Stock',
            'Categoría', 'Proveedor', 'Activo', 'Creado Por', 'Creado En'
        ])
        for p in productos:
            writer.writerow([
                p.nombre, p.descripcion, p.codigo_barra, p.sku,
                p.precio_compra, p.precio_venta, p.stock,
                p.categoria.nombre if p.categoria else '',
                p.proveedor.nombre if p.proveedor else '',
                'Sí' if p.activo else 'No',
                p.creado_por.username if p.creado_por else '',
                p.creado_en.strftime('%Y-%m-%d %H:%M:%S'),
            ])
        return response

    # Paginación
    paginator  = Paginator(productos, 10)
    page_obj   = paginator.get_page(request.GET.get('page'))
    
    if tienda_actual:
        categorias = Categoria.objects.filter(activa=True, tienda=tienda_actual).order_by('nombre')
    else:
        categorias = Categoria.objects.filter(activa=True).order_by('nombre')

    return render(request, 'inventario/producto_list.html', {
        'page_obj':   page_obj,
        'categorias': categorias,
        'max_perm':   max_perm,
    })


@login_required
def producto_create(request):
    max_perm = get_max_permission(request.user)
    if max_perm < 2:
        return redirect('inventario:producto_list')

    tienda_actual = get_tienda_actual(request.user)
    
    # Obtener categorías y proveedores filtrados por tienda
    if tienda_actual:
        categorias = Categoria.objects.filter(activa=True, tienda=tienda_actual)
        proveedores = Proveedor.objects.filter(activo=True, tienda=tienda_actual)
    else:
        categorias = Categoria.objects.filter(activa=True)
        proveedores = Proveedor.objects.filter(activo=True)

    if request.method == 'POST':
        form = ProductoForm(request.POST)
        if form.is_valid():
            producto = form.save(commit=False)
            producto.creado_por = request.user
            producto.tienda = request.user.tienda
            producto.save()
            messages.success(request, f'Producto "{producto.nombre}" creado exitosamente.')
            return redirect('inventario:producto_list')
    else:
        form = ProductoForm()

    return render(request, 'inventario/producto_form.html', {
        'form': form,
        'categorias': categorias,
        'proveedores': proveedores,
    })


@login_required
def producto_edit(request, pk):
    max_perm = get_max_permission(request.user)
    if max_perm == 0:
        return redirect('dashboard')
    if max_perm == 1:
        return redirect('inventario:producto_list')

    tienda_actual = get_tienda_actual(request.user)
    
    if tienda_actual:
        producto = get_object_or_404(Producto, pk=pk, tienda=tienda_actual)
        categorias = Categoria.objects.filter(activa=True, tienda=tienda_actual)
        proveedores = Proveedor.objects.filter(activo=True, tienda=tienda_actual)
    else:
        producto = get_object_or_404(Producto, pk=pk)
        categorias = Categoria.objects.filter(activa=True)
        proveedores = Proveedor.objects.filter(activo=True)

    if request.method == 'POST':
        form = ProductoForm(request.POST, instance=producto)
        if form.is_valid():
            form.save()
            messages.success(request, f'Producto "{producto.nombre}" actualizado.')
            return redirect('inventario:producto_list')
    else:
        form = ProductoForm(instance=producto)

    return render(request, 'inventario/producto_form.html', {
        'form': form,
        'producto': producto,
        'categorias': categorias,
        'proveedores': proveedores,
    })


@login_required
def producto_delete(request, pk):
    if get_max_permission(request.user) < 2:
        return redirect('inventario:producto_list')

    tienda_actual = get_tienda_actual(request.user)
    if tienda_actual:
        producto = get_object_or_404(Producto, pk=pk, tienda=tienda_actual)
    else:
        producto = get_object_or_404(Producto, pk=pk)
        
    if request.method == 'POST':
        try:
            nombre = producto.nombre
            producto.delete()
            messages.success(request, f'Producto "{nombre}" eliminado correctamente.')
        except ProtectedError:
            messages.error(
                request,
                f'No se puede eliminar "{producto.nombre}" porque ya tiene '
                f'movimientos de stock o ventas registradas. '
                f'Si deseas desactivarlo, edítalo y desmarca la opción "Activo".'
            )
    return redirect('inventario:producto_list')


@login_required
def producto_bulk_upload(request):
    # Solo superusuario puede hacer carga masiva
    if not request.user.is_superuser:
        messages.error(request, 'Solo el superusuario puede realizar la carga masiva.')
        return redirect('inventario:producto_list')

    if request.method == 'POST':
        form = CsvUploadForm(request.POST, request.FILES)
        if form.is_valid():
            csv_file = request.FILES['csv_file']
            
            # Determinar la tienda destino
            tienda_id = request.POST.get('tienda')
            if tienda_id:
                from tiendas.models import Tienda
                tienda_destino = Tienda.objects.get(id=tienda_id)
            else:
                tienda_destino = request.user.tienda
            
            if not tienda_destino:
                messages.error(request, 'No se pudo determinar la tienda destino. Selecciona una tienda en el formulario.')
                return redirect('inventario:producto_bulk_upload')

            try:
                data_set = csv_file.read().decode('UTF-8')
            except UnicodeDecodeError:
                csv_file.seek(0)
                data_set = csv_file.read().decode('ISO-8859-1')

            io_string = io.StringIO(data_set)
            reader = csv.DictReader(io_string)

            # Limpiar BOM y espacios en encabezados
            if reader.fieldnames:
                reader.fieldnames = [
                    k.strip().lower().lstrip('\ufeff')
                    for k in reader.fieldnames
                ]

            # Mapas para FK (filtrados por tienda destino)
            cat_map = {c.nombre.lower(): c for c in Categoria.objects.filter(tienda=tienda_destino)}
            prov_map = {p.nombre.lower(): p for p in Proveedor.objects.filter(tienda=tienda_destino)}

            exitosos = []
            errores = []

            for i, row in enumerate(reader, start=1):
                row = {k: v.strip() for k, v in row.items()}
                errores_fila = []

                # Validaciones obligatorias
                if not row.get('nombre'):
                    errores_fila.append('El nombre es obligatorio.')
                if not row.get('precio_venta'):
                    errores_fila.append('El precio de venta es obligatorio.')

                # Validar stock_inicial numérico
                stock_inicial = 0
                if row.get('stock_inicial'):
                    try:
                        stock_inicial = int(row['stock_inicial'])
                        if stock_inicial < 0:
                            errores_fila.append('El stock inicial no puede ser negativo.')
                    except ValueError:
                        errores_fila.append('El stock inicial debe ser un número entero.')

                # Validar stock_minimo numérico
                stock_minimo = 5
                if row.get('stock_minimo'):
                    try:
                        stock_minimo = int(row['stock_minimo'])
                    except ValueError:
                        errores_fila.append('El stock mínimo debe ser un número entero.')

                # Validar precio_venta numérico
                try:
                    precio_venta = float(row.get('precio_venta', 0))
                except ValueError:
                    errores_fila.append('El precio de venta debe ser un número.')
                    precio_venta = 0

                # Validar precio_compra numérico
                try:
                    precio_compra = float(row.get('precio_compra', 0))
                except ValueError:
                    precio_compra = 0

                if errores_fila:
                    errores.append({
                        'row': i,
                        'data': row,
                        'errors': {'validación': ', '.join(errores_fila)}
                    })
                    continue

                # Resolver FK — si no existe la categoría/proveedor, la crea automáticamente en la tienda destino
                categoria = cat_map.get(row.get('categoria', '').lower())
                if not categoria and row.get('categoria'):
                    categoria = Categoria.objects.create(
                        nombre=row['categoria'].strip(),
                        activa=True,
                        tienda=tienda_destino
                    )
                    cat_map[row['categoria'].lower()] = categoria

                proveedor = prov_map.get(row.get('proveedor', '').lower())
                if not proveedor and row.get('proveedor'):
                    proveedor = Proveedor.objects.create(
                        nombre=row['proveedor'].strip(),
                        activo=True,
                        tienda=tienda_destino
                    )
                    prov_map[row['proveedor'].lower()] = proveedor

                # Verificar si el producto ya existe por código de barra o SKU en la misma tienda
                codigo_barra = row.get('codigo_barra') or None
                sku = row.get('sku') or None
                existe = False

                if codigo_barra:
                    existe = Producto.objects.filter(codigo_barra=codigo_barra, tienda=tienda_destino).exists()
                elif sku:
                    existe = Producto.objects.filter(sku=sku, tienda=tienda_destino).exists()

                if existe:
                    errores.append({
                        'row': i,
                        'data': row,
                        'errors': {'duplicado': f'Ya existe un producto con código "{codigo_barra or sku}" en esta tienda'}
                    })
                    continue

                try:
                    with transaction.atomic():
                        producto = Producto.objects.create(
                            nombre=row.get('nombre', ''),
                            descripcion=row.get('descripcion', ''),
                            codigo_barra=codigo_barra,
                            sku=sku,
                            precio_compra=precio_compra,
                            precio_venta=precio_venta,
                            stock=stock_inicial,
                            stock_minimo=stock_minimo,
                            categoria=categoria,
                            proveedor=proveedor,
                            activo=row.get('activo', 'true').lower() != 'false',
                            creado_por=request.user,
                            tienda=tienda_destino,
                        )

                        # Registrar movimiento de stock si hay stock inicial
                        if stock_inicial > 0:
                            MovimientoStock.objects.create(
                                producto=producto,
                                tipo='entrada',
                                cantidad=stock_inicial,
                                stock_anterior=0,
                                stock_nuevo=stock_inicial,
                                motivo='Carga inicial de inventario',
                                usuario=request.user,
                                tienda=tienda_destino,
                            )

                    exitosos.append({'row': i, 'data': row})

                except Exception as e:
                    errores.append({
                        'row': i,
                        'data': row,
                        'errors': {'error': str(e)}
                    })

            messages.success(
                request,
                f'{len(exitosos)} productos cargados exitosamente en la tienda "{tienda_destino.nombre}".'
            )

            return render(request, 'inventario/producto_bulk_upload.html', {
                'form': CsvUploadForm(),
                'report_generated': True,
                'total_rows': len(exitosos) + len(errores),
                'successful_count': len(exitosos),
                'error_count': len(errores),
                'exitosos': exitosos,
                'errores': errores,
            })
    else:
        form = CsvUploadForm()
        context = {'form': form}
        
        # Si es superusuario, pasar lista de tiendas para el selector
        if request.user.is_superuser:
            from tiendas.models import Tienda
            context['tiendas'] = Tienda.objects.filter(activa=True)
        
        return render(request, 'inventario/producto_bulk_upload.html', context)

@login_required
def download_template_producto(request):
    if not request.user.is_superuser:
        return redirect('inventario:producto_list')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="template_productos.csv"'
    response.write('\ufeff'.encode('utf-8'))
    writer = csv.writer(response)
    writer.writerow([
        'nombre', 'descripcion', 'codigo_barra', 'sku',
        'precio_compra', 'precio_venta',
        'stock_inicial', 'stock_minimo',
        'categoria', 'proveedor', 'activo'
    ])
    writer.writerow([
        'Producto Ejemplo', 'Descripción del producto', 'COD001', 'SKU001',
        '50.00', '100.00', '10', '5',
        'Categoría Ejemplo', 'Proveedor Ejemplo', 'true'
    ])
    return response


# ─── Categorías ────────────────────────────────────────────

@login_required
def categoria_list(request):
    if get_max_permission(request.user) == 0:
        return redirect('dashboard')

    tienda_actual = get_tienda_actual(request.user)
    if tienda_actual:
        categorias = Categoria.objects.filter(tienda=tienda_actual).order_by('nombre')
    else:
        categorias = Categoria.objects.all().order_by('nombre')

    nombre = request.GET.get('nombre')
    if nombre:
        categorias = categorias.filter(nombre__icontains=nombre)

    paginator = Paginator(categorias, 10)
    page_obj  = paginator.get_page(request.GET.get('page'))

    return render(request, 'inventario/categoria_list.html', {
        'page_obj': page_obj,
        'max_perm': get_max_permission(request.user),
    })


@login_required
def categoria_create(request):
    if get_max_permission(request.user) < 2:
        return redirect('inventario:categoria_list')

    if request.method == 'POST':
        nombre    = request.POST.get('nombre', '').strip()
        descripcion = request.POST.get('descripcion', '').strip()
        activa    = request.POST.get('activa') == 'on'

        if not nombre:
            messages.error(request, 'El nombre es obligatorio.')
        elif Categoria.objects.filter(nombre__iexact=nombre, tienda=request.user.tienda).exists():
            messages.error(request, f'Ya existe una categoría con el nombre "{nombre}" en tu tienda.')
        else:
            Categoria.objects.create(
                nombre=nombre, 
                descripcion=descripcion, 
                activa=activa,
                tienda=request.user.tienda
            )
            messages.success(request, f'Categoría "{nombre}" creada exitosamente.')
            return redirect('inventario:categoria_list')

    return render(request, 'inventario/categoria_form.html')


@login_required
def categoria_edit(request, pk):
    if get_max_permission(request.user) < 2:
        return redirect('inventario:categoria_list')

    tienda_actual = get_tienda_actual(request.user)
    if tienda_actual:
        categoria = get_object_or_404(Categoria, pk=pk, tienda=tienda_actual)
    else:
        categoria = get_object_or_404(Categoria, pk=pk)

    if request.method == 'POST':
        nombre      = request.POST.get('nombre', '').strip()
        descripcion = request.POST.get('descripcion', '').strip()
        activa      = request.POST.get('activa') == 'on'

        if not nombre:
            messages.error(request, 'El nombre es obligatorio.')
        elif Categoria.objects.filter(nombre__iexact=nombre, tienda=request.user.tienda).exclude(pk=pk).exists():
            messages.error(request, f'Ya existe otra categoría con el nombre "{nombre}" en tu tienda.')
        else:
            categoria.nombre      = nombre
            categoria.descripcion = descripcion
            categoria.activa      = activa
            categoria.save()
            messages.success(request, f'Categoría "{nombre}" actualizada.')
            return redirect('inventario:categoria_list')

    return render(request, 'inventario/categoria_form.html', {'categoria': categoria})


@login_required
def categoria_delete(request, pk):
    if get_max_permission(request.user) < 2:
        return redirect('inventario:categoria_list')

    tienda_actual = get_tienda_actual(request.user)
    if tienda_actual:
        categoria = get_object_or_404(Categoria, pk=pk, tienda=tienda_actual)
    else:
        categoria = get_object_or_404(Categoria, pk=pk)
        
    if request.method == 'POST':
        try:
            nombre = categoria.nombre
            categoria.delete()
            messages.success(request, f'Categoría "{nombre}" eliminada.')
        except ProtectedError:
            messages.error(
                request,
                f'No se puede eliminar "{categoria.nombre}" porque tiene '
                f'productos asociados. Reasigna o elimina esos productos primero.'
            )
    return redirect('inventario:categoria_list')


# ─── Proveedores ───────────────────────────────────────────

@login_required
def proveedor_list(request):
    if get_max_permission(request.user) == 0:
        return redirect('dashboard')

    tienda_actual = get_tienda_actual(request.user)
    if tienda_actual:
        proveedores = Proveedor.objects.filter(tienda=tienda_actual).order_by('nombre')
    else:
        proveedores = Proveedor.objects.all().order_by('nombre')

    nombre = request.GET.get('nombre')
    activo = request.GET.get('activo')

    if nombre:
        proveedores = proveedores.filter(nombre__icontains=nombre)
    if activo in ['True', 'False']:
        proveedores = proveedores.filter(activo=(activo == 'True'))

    paginator = Paginator(proveedores, 10)
    page_obj  = paginator.get_page(request.GET.get('page'))

    return render(request, 'inventario/proveedor_list.html', {
        'page_obj': page_obj,
        'max_perm': get_max_permission(request.user),
    })


@login_required
def proveedor_create(request):
    if get_max_permission(request.user) < 2:
        return redirect('inventario:proveedor_list')

    if request.method == 'POST':
        nombre    = request.POST.get('nombre', '').strip()
        contacto  = request.POST.get('contacto', '').strip()
        telefono  = request.POST.get('telefono', '').strip()
        email     = request.POST.get('email', '').strip()
        direccion = request.POST.get('direccion', '').strip()
        activo    = request.POST.get('activo') == 'on'

        if not nombre:
            messages.error(request, 'El nombre es obligatorio.')
        else:
            Proveedor.objects.create(
                nombre=nombre, contacto=contacto,
                telefono=telefono, email=email,
                direccion=direccion, activo=activo,
                tienda=request.user.tienda
            )
            messages.success(request, f'Proveedor "{nombre}" creado exitosamente.')
            return redirect('inventario:producto_list')

    return render(request, 'inventario/proveedor_form.html')


@login_required
def proveedor_edit(request, pk):
    if get_max_permission(request.user) < 2:
        return redirect('inventario:proveedor_list')

    tienda_actual = get_tienda_actual(request.user)
    if tienda_actual:
        proveedor = get_object_or_404(Proveedor, pk=pk, tienda=tienda_actual)
    else:
        proveedor = get_object_or_404(Proveedor, pk=pk)

    if request.method == 'POST':
        nombre    = request.POST.get('nombre', '').strip()
        contacto  = request.POST.get('contacto', '').strip()
        telefono  = request.POST.get('telefono', '').strip()
        email     = request.POST.get('email', '').strip()
        direccion = request.POST.get('direccion', '').strip()
        activo    = request.POST.get('activo') == 'on'

        if not nombre:
            messages.error(request, 'El nombre es obligatorio.')
        else:
            proveedor.nombre    = nombre
            proveedor.contacto  = contacto
            proveedor.telefono  = telefono
            proveedor.email     = email
            proveedor.direccion = direccion
            proveedor.activo    = activo
            proveedor.save()
            messages.success(request, f'Proveedor "{nombre}" actualizado.')
            return redirect('inventario:proveedor_list')

    return render(request, 'inventario/proveedor_form.html', {'proveedor': proveedor})


@login_required
def proveedor_delete(request, pk):
    if get_max_permission(request.user) < 2:
        return redirect('inventario:proveedor_list')

    tienda_actual = get_tienda_actual(request.user)
    if tienda_actual:
        proveedor = get_object_or_404(Proveedor, pk=pk, tienda=tienda_actual)
    else:
        proveedor = get_object_or_404(Proveedor, pk=pk)
        
    if request.method == 'POST':
        try:
            nombre = proveedor.nombre
            proveedor.delete()
            messages.success(request, f'Proveedor "{nombre}" eliminado.')
        except ProtectedError:
            messages.error(
                request,
                f'No se puede eliminar "{proveedor.nombre}" porque tiene '
                f'productos asociados. Reasigna o elimina esos productos primero.'
            )
    return redirect('inventario:proveedor_list')


# ─── Stock ─────────────────────────────────────────────────

@login_required
def stock_list(request):
    if get_max_permission(request.user) == 0:
        return redirect('dashboard')

    tienda_actual = get_tienda_actual(request.user)
    if tienda_actual:
        productos = Producto.objects.select_related('categoria', 'proveedor').filter(activo=True, tienda=tienda_actual).order_by('stock')
    else:
        productos = Producto.objects.select_related('categoria', 'proveedor').filter(activo=True).order_by('stock')

    # Filtros
    nombre   = request.GET.get('nombre')
    categoria_id = request.GET.get('categoria')
    solo_bajo = request.GET.get('solo_bajo')

    if nombre:
        productos = productos.filter(nombre__icontains=nombre)
    if categoria_id:
        productos = productos.filter(categoria__id=categoria_id)
    if solo_bajo:
        productos = productos.filter(stock__lte=db_models.F('stock_minimo'))

    paginator  = Paginator(productos, 15)
    page_obj   = paginator.get_page(request.GET.get('page'))
    
    if tienda_actual:
        categorias = Categoria.objects.filter(activa=True, tienda=tienda_actual).order_by('nombre')
    else:
        categorias = Categoria.objects.filter(activa=True).order_by('nombre')

    return render(request, 'inventario/stock_list.html', {
        'page_obj':   page_obj,
        'categorias': categorias,
        'max_perm':   get_max_permission(request.user),
    })


@login_required
def stock_entrada(request):
    if get_max_permission(request.user) < 2:
        return redirect('inventario:stock_list')

    tienda_actual = get_tienda_actual(request.user)

    if request.method == 'POST':
        producto_id = request.POST.get('producto')
        cantidad    = request.POST.get('cantidad', 0)
        motivo      = request.POST.get('motivo', '').strip()

        try:
            cantidad = int(cantidad)
            if cantidad <= 0:
                raise ValueError
        except ValueError:
            messages.error(request, 'La cantidad debe ser un número mayor a 0.')
            return redirect('inventario:stock_entrada')

        try:
            if tienda_actual:
                producto = Producto.objects.get(id=producto_id, activo=True, tienda=tienda_actual)
            else:
                producto = Producto.objects.get(id=producto_id, activo=True)
        except Producto.DoesNotExist:
            messages.error(request, 'Producto no encontrado.')
            return redirect('inventario:stock_entrada')

        stock_anterior = producto.stock
        producto.stock += cantidad
        producto.save()

        MovimientoStock.objects.create(
            producto       = producto,
            tipo           = 'entrada',
            cantidad       = cantidad,
            stock_anterior = stock_anterior,
            stock_nuevo    = producto.stock,
            motivo         = motivo or 'Entrada manual',
            usuario        = request.user,
            tienda         = tienda_actual or producto.tienda,
        )

        messages.success(
            request,
            f'Se agregaron {cantidad} unidades a "{producto.nombre}". Stock actual: {producto.stock}'
        )
        return redirect('inventario:stock_list')

    if tienda_actual:
        productos = Producto.objects.filter(activo=True, tienda=tienda_actual).order_by('nombre')
    else:
        productos = Producto.objects.filter(activo=True).order_by('nombre')
        
    return render(request, 'inventario/stock_entrada.html', {
        'productos': productos,
    })


@login_required
def stock_movimientos(request):
    if get_max_permission(request.user) == 0:
        return redirect('dashboard')

    tienda_actual = get_tienda_actual(request.user)
    if tienda_actual:
        movimientos = MovimientoStock.objects.select_related('producto', 'usuario').filter(tienda=tienda_actual)
    else:
        movimientos = MovimientoStock.objects.select_related('producto', 'usuario').all()

    nombre = request.GET.get('nombre')
    tipo   = request.GET.get('tipo')

    if nombre:
        movimientos = movimientos.filter(producto__nombre__icontains=nombre)
    if tipo:
        movimientos = movimientos.filter(tipo=tipo)

    paginator = Paginator(movimientos, 15)
    page_obj  = paginator.get_page(request.GET.get('page'))

    return render(request, 'inventario/stock_movimientos.html', {
        'page_obj': page_obj,
    })


# ─── Ajustes de inventario ─────────────────────────────────

@login_required
def ajuste_inventario(request):
    """Vista para realizar ajustes de inventario (merma, corrección, robo)"""
    max_perm = get_max_permission(request.user)
    
    # Solo usuarios con permiso >= 2 pueden hacer ajustes
    if max_perm < 2:
        messages.error(request, 'No tienes permiso para realizar ajustes de inventario.')
        return redirect('dashboard')
    
    tienda_actual = get_tienda_actual(request.user)
    
    if request.method == 'POST':
        producto_id = request.POST.get('producto')
        tipo_ajuste = request.POST.get('tipo_ajuste')
        cantidad = request.POST.get('cantidad', 0)
        motivo = request.POST.get('motivo', '').strip()
        
        # Validaciones
        try:
            cantidad = int(cantidad)
            if cantidad <= 0:
                raise ValueError
        except ValueError:
            messages.error(request, 'La cantidad debe ser un número mayor a 0.')
            return redirect('inventario:ajuste_inventario')
        
        try:
            if tienda_actual:
                producto = Producto.objects.get(id=producto_id, activo=True, tienda=tienda_actual)
            else:
                producto = Producto.objects.get(id=producto_id, activo=True)
        except Producto.DoesNotExist:
            messages.error(request, 'Producto no encontrado.')
            return redirect('inventario:ajuste_inventario')
        
        # Validar que no exceda el stock disponible para ajustes negativos
        if cantidad > producto.stock:
            messages.error(request, f'No puedes ajustar más de {producto.stock} unidades. Stock actual: {producto.stock}')
            return redirect('inventario:ajuste_inventario')
        
        # Registrar el ajuste
        stock_anterior = producto.stock
        producto.stock -= cantidad
        producto.save()
        
        # Mapeo de tipos de ajuste
        tipos_ajuste = {
            'merma': 'Merma',
            'correccion': 'Corrección de conteo',
            'robo': 'Robo o pérdida'
        }
        
        motivo_completo = f"{tipos_ajuste.get(tipo_ajuste, 'Ajuste')}: {motivo}" if motivo else tipos_ajuste.get(tipo_ajuste, 'Ajuste')
        
        MovimientoStock.objects.create(
            producto=producto,
            tipo='ajuste',
            cantidad=cantidad,
            stock_anterior=stock_anterior,
            stock_nuevo=producto.stock,
            motivo=motivo_completo,
            usuario=request.user,
            tienda=tienda_actual or producto.tienda,
        )
        
        messages.success(
            request,
            f'Ajuste de inventario aplicado a "{producto.nombre}". '
            f'Se redujeron {cantidad} unidades. Stock actual: {producto.stock}'
        )
        return redirect('inventario:ajuste_inventario')
    
    # GET: Mostrar formulario
    if tienda_actual:
        productos = Producto.objects.filter(activo=True, tienda=tienda_actual).order_by('nombre')
    else:
        productos = Producto.objects.filter(activo=True).order_by('nombre')
    
    context = {
        'productos': productos,
        'tipos_ajuste': [
            ('merma', 'Merma (producto dañado o vencido)'),
            ('correccion', 'Corrección de conteo (error en inventario)'),
            ('robo', 'Robo o pérdida'),
        ],
    }
    return render(request, 'inventario/ajuste_inventario.html', context)


@login_required
def historial_ajustes(request):
    """Vista para ver el historial de ajustes de inventario"""
    max_perm = get_max_permission(request.user)
    
    if max_perm == 0:
        return redirect('dashboard')
    
    tienda_actual = get_tienda_actual(request.user)
    
    # Solo mostrar ajustes (tipo='ajuste')
    if tienda_actual:
        ajustes = MovimientoStock.objects.filter(tipo='ajuste', tienda=tienda_actual).select_related('producto', 'usuario').order_by('-fecha')
    else:
        ajustes = MovimientoStock.objects.filter(tipo='ajuste').select_related('producto', 'usuario').order_by('-fecha')
    
    # Filtros opcionales
    producto_id = request.GET.get('producto')
    fecha_desde = request.GET.get('fecha_desde')
    fecha_hasta = request.GET.get('fecha_hasta')
    
    if producto_id:
        ajustes = ajustes.filter(producto_id=producto_id)
    if fecha_desde:
        ajustes = ajustes.filter(fecha__date__gte=fecha_desde)
    if fecha_hasta:
        ajustes = ajustes.filter(fecha__date__lte=fecha_hasta)
    
    paginator = Paginator(ajustes, 20)
    page_obj = paginator.get_page(request.GET.get('page'))
    
    if tienda_actual:
        productos = Producto.objects.filter(activo=True, tienda=tienda_actual).order_by('nombre')
    else:
        productos = Producto.objects.filter(activo=True).order_by('nombre')
    
    context = {
        'page_obj': page_obj,
        'productos': productos,
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'producto_id': producto_id,
    }
    return render(request, 'inventario/historial_ajustes.html', context)