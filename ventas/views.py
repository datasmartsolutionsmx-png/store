from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db import transaction
from django.core.paginator import Paginator
from django.db import models as db_models
import json
from decimal import Decimal
from django.utils import timezone
from .models import Venta, DetalleVenta, CorteCaja, Devolucion,DetalleDevolucion

from users.models import UserRole
from inventario.models import Producto
from .models import Venta, DetalleVenta
from django.db.models import Max

def generar_folio(tienda):
    """Genera el siguiente folio para una tienda"""
    from .models import Venta  # Importación local para evitar circular imports
    ultima_venta = Venta.objects.filter(tienda=tienda).aggregate(max_folio=Max('folio'))
    siguiente = (ultima_venta['max_folio'] or 0) + 1
    return siguiente


def get_max_permission(user):
    return UserRole.objects.filter(
        user=user
    ).aggregate(
        max_perm=db_models.Max('role__ventas')
    )['max_perm'] or 0

def get_tienda_actual(user):
    """Retorna la tienda del usuario. Si es superadmin, retorna None (sin filtro)."""
    if user.is_superuser:
        return None
    return user.tienda


@login_required
def punto_venta(request):
    if get_max_permission(request.user) == 0:
        return redirect('dashboard')

    # Si no hay corte abierto, pide abrir caja primero
    corte = get_corte_activo(request.user)
    if not corte:
        return redirect('ventas:abrir_caja')

    return render(request, 'ventas/punto_venta.html', {
        'corte': corte,
    })


@login_required
def buscar_producto(request):
    if get_max_permission(request.user) == 0:
        return JsonResponse({'error': 'Sin permisos'}, status=403)

    query = request.GET.get('q', '').strip()
    if not query:
        return JsonResponse({'error': 'Búsqueda vacía'}, status=400)

    tienda_actual = get_tienda_actual(request.user)
    
    # Primero busca por código de barra EXACTO
    if tienda_actual:
        producto = Producto.objects.filter(
            codigo_barra=query, activo=True, tienda=tienda_actual
        ).first()
    else:
        producto = Producto.objects.filter(
            codigo_barra=query, activo=True
        ).first()

    # Si no encuentra por código, busca por nombre
    if not producto:
        if tienda_actual:
            producto = Producto.objects.filter(
                nombre__icontains=query, activo=True, tienda=tienda_actual
            ).first()
        else:
            producto = Producto.objects.filter(
                nombre__icontains=query, activo=True
            ).first()

    if not producto:
        return JsonResponse({'error': 'Producto no encontrado'}, status=404)

    if producto.stock <= 0:
        return JsonResponse({'error': f'"{producto.nombre}" sin stock disponible'}, status=400)

    return JsonResponse({
        'id':           producto.id,
        'nombre':       producto.nombre,
        'codigo_barra': producto.codigo_barra or '',
        'precio_venta': float(producto.precio_venta),
        'stock':        producto.stock,
        'stock_minimo': producto.stock_minimo,
    })


@login_required
@transaction.atomic
def procesar_venta(request):
    """
    Recibe el carrito en JSON, valida stock,
    crea la Venta + DetalleVenta y descuenta el stock.
    """
    if get_max_permission(request.user) < 2:
        return JsonResponse({'error': 'Sin permisos para vender'}, status=403)

    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)

    try:
        data        = json.loads(request.body)
        carrito     = data.get('carrito', [])
        metodo_pago = data.get('metodo_pago', 'efectivo')
        descuento   = Decimal(str(data.get('descuento', 0)))  # ← Convertir a Decimal
        notas       = data.get('notas', '')
        efectivo_recibido = data.get('efectivo_recibido', None)  # ← Nuevo campo

        if not carrito:
            return JsonResponse({'error': 'El carrito está vacío'}, status=400)

        # Validar stock de todos los productos antes de crear la venta
        errores = []
        items   = []
        for item in carrito:
            producto = Producto.objects.select_for_update().get(id=item['id'])
            cantidad = int(item['cantidad'])

            if producto.stock < cantidad:
                errores.append(
                    f'"{producto.nombre}": stock insuficiente (disponible: {producto.stock})'
                )
            else:
                items.append((producto, cantidad))

        if errores:
            return JsonResponse({'error': '\n'.join(errores)}, status=400)

        # Calcular totales
        subtotal = sum(p.precio_venta * c for p, c in items)
        total    = subtotal - descuento

        if total < 0:
            return JsonResponse({'error': 'El descuento no puede ser mayor al subtotal'}, status=400)

        # Validar efectivo recibido si aplica
        cambio = None
        if metodo_pago == 'efectivo' and efectivo_recibido:
            efectivo_recibido_dec = Decimal(str(efectivo_recibido))
            if efectivo_recibido_dec < total:
                return JsonResponse({'error': f'El efectivo recibido (${efectivo_recibido}) es insuficiente. Total a pagar: ${total}'}, status=400)
            cambio = efectivo_recibido_dec - total

        # Crear la venta
        venta = Venta.objects.create(
            usuario     = request.user,
            subtotal    = subtotal,
            descuento   = descuento,
            total       = total,
            metodo_pago = metodo_pago,
            notas       = notas,
            tienda      = request.user.tienda,
            folio       = generar_folio(request.user.tienda),
        )

        # Crear detalles y descontar stock
        alertas_stock = []
        for producto, cantidad in items:
            DetalleVenta.objects.create(
                venta           = venta,
                producto        = producto,
                cantidad        = cantidad,
                precio_unitario = producto.precio_venta,
            )
            producto.stock -= cantidad
            producto.save()

            if producto.stock <= producto.stock_minimo:
                alertas_stock.append(
                    f'⚠️ "{producto.nombre}" tiene stock bajo ({producto.stock} unidades)'
                )

        return JsonResponse({
            'ok':           True,
            'venta_id':     venta.id,
            'total':        float(total),
            'cambio':       float(cambio) if cambio else None,
            'alertas':      alertas_stock,
        })

    except Producto.DoesNotExist:
        return JsonResponse({'error': 'Producto no encontrado'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def historial(request):
    if get_max_permission(request.user) == 0:
        return redirect('dashboard')

    tienda_actual = get_tienda_actual(request.user)
    
    # Base query con select_related para optimizar
    if tienda_actual:
        ventas = Venta.objects.select_related('usuario').filter(tienda=tienda_actual)
    else:
        ventas = Venta.objects.select_related('usuario').all()
    
    # Si NO es staff, filtrar solo sus ventas
    if not request.user.is_staff:
        ventas = ventas.filter(usuario=request.user)

    # Filtros
    fecha_desde = request.GET.get('fecha_desde')
    fecha_hasta = request.GET.get('fecha_hasta')
    metodo_pago = request.GET.get('metodo_pago')
    estado      = request.GET.get('estado')

    if fecha_desde:
        ventas = ventas.filter(fecha__date__gte=fecha_desde)
    if fecha_hasta:
        ventas = ventas.filter(fecha__date__lte=fecha_hasta)
    if metodo_pago:
        ventas = ventas.filter(metodo_pago=metodo_pago)
    if estado:
        ventas = ventas.filter(estado=estado)

    paginator = Paginator(ventas, 15)
    page_obj  = paginator.get_page(request.GET.get('page'))

    return render(request, 'ventas/historial.html', {
        'page_obj':   page_obj,
        'is_staff':   request.user.is_staff,
        'metodos':    Venta.METODO_PAGO,
        'estados':    Venta.ESTADO,
    })

@login_required
def buscar_producto_sugerencias(request):
    """Vista para autocompletado de productos"""
    if get_max_permission(request.user) == 0:
        return JsonResponse({'error': 'Sin permisos'}, status=403)
    
    query = request.GET.get('q', '').strip()
    if not query or len(query) < 2:
        return JsonResponse({'productos': []})
    
    tienda_actual = get_tienda_actual(request.user)
    
    # Buscar productos por nombre o código de barra
    if tienda_actual:
        productos = Producto.objects.filter(
            activo=True,
            stock__gt=0,
            tienda=tienda_actual
        ).filter(
            db_models.Q(nombre__icontains=query) |
            db_models.Q(codigo_barra__icontains=query)
        )[:10]
    else:
        productos = Producto.objects.filter(
            activo=True,
            stock__gt=0
        ).filter(
            db_models.Q(nombre__icontains=query) |
            db_models.Q(codigo_barra__icontains=query)
        )[:10]
    
    resultados = []
    for producto in productos:
        resultados.append({
            'id': producto.id,
            'nombre': producto.nombre,
            'codigo_barra': producto.codigo_barra or '',
            'precio_venta': float(producto.precio_venta),
            'stock': producto.stock,
            'stock_minimo': producto.stock_minimo,
        })
    
    return JsonResponse({'productos': resultados})

# ─── Corte de caja ─────────────────────────────────────────

def get_corte_activo(user):
    """Retorna el corte abierto del usuario o None."""
    return CorteCaja.objects.filter(
        usuario=user, estado='abierto'
    ).first()


@login_required
def abrir_caja(request):
    if get_max_permission(request.user) == 0:
        return redirect('dashboard')

    # Si ya tiene un corte abierto lo manda al punto de venta
    corte = get_corte_activo(request.user)
    if corte:
        return redirect('ventas:punto_venta')

    if request.method == 'POST':
        try:
            fondo_inicial = float(request.POST.get('fondo_inicial', 0))
            if fondo_inicial < 0:
                raise ValueError
        except ValueError:
            messages.error(request, 'El fondo inicial debe ser un número positivo.')
            return render(request, 'ventas/abrir_caja.html')

        CorteCaja.objects.create(
            usuario       = request.user,
            fondo_inicial = fondo_inicial,
            tienda        = request.user.tienda, 
        )
        messages.success(request, f'Caja abierta con fondo inicial de ${fondo_inicial:.2f}')
        return redirect('ventas:punto_venta')

    return render(request, 'ventas/abrir_caja.html')


@login_required
@transaction.atomic
def cerrar_caja(request):
    if get_max_permission(request.user) == 0:
        return redirect('dashboard')

    corte = get_corte_activo(request.user)
    if not corte:
        messages.error(request, 'No tienes una caja abierta.')
        return redirect('ventas:punto_venta')

    # Calcular totales de ventas del turno
    ventas = Venta.objects.filter(

        usuario = request.user,
        fecha__gte = corte.fecha_apertura,
        estado = 'completada',
    )

    total_efectivo      = sum(v.total for v in ventas if v.metodo_pago == 'efectivo')
    total_tarjeta       = sum(v.total for v in ventas if v.metodo_pago == 'tarjeta')
    total_transferencia = sum(v.total for v in ventas if v.metodo_pago == 'transferencia')
    total_ventas        = total_efectivo + total_tarjeta + total_transferencia
    num_ventas          = ventas.count()

    if request.method == 'POST':
        try:
            conteo_efectivo      = float(request.POST.get('conteo_efectivo', 0))
            conteo_tarjeta       = float(request.POST.get('conteo_tarjeta', 0))
            conteo_transferencia = float(request.POST.get('conteo_transferencia', 0))
            notas                = request.POST.get('notas', '').strip()
        except ValueError:
            messages.error(request, 'Los conteos deben ser números válidos.')
            return redirect('ventas:cerrar_caja')

        efectivo_esperado = float(corte.fondo_inicial) + float(total_efectivo)

        corte.total_efectivo         = total_efectivo
        corte.total_tarjeta          = total_tarjeta
        corte.total_transferencia    = total_transferencia
        corte.total_ventas           = total_ventas
        corte.num_ventas             = num_ventas
        corte.conteo_efectivo        = conteo_efectivo
        corte.conteo_tarjeta         = conteo_tarjeta
        corte.conteo_transferencia   = conteo_transferencia
        corte.diferencia_efectivo    = conteo_efectivo - efectivo_esperado
        corte.diferencia_tarjeta     = conteo_tarjeta - float(total_tarjeta)
        corte.diferencia_transferencia = conteo_transferencia - float(total_transferencia)
        corte.fecha_cierre           = timezone.now()
        corte.estado                 = 'cerrado'
        corte.notas                  = notas
        corte.save()

        messages.success(request, f'Corte #{corte.id} cerrado exitosamente.')
        return redirect('ventas:detalle_corte', pk=corte.id)

    context = {
        'corte':               corte,
        'ventas':              ventas,
        'total_efectivo':      total_efectivo,
        'total_tarjeta':       total_tarjeta,
        'total_transferencia': total_transferencia,
        'total_ventas':        total_ventas,
        'num_ventas':          num_ventas,
        'efectivo_esperado':   float(corte.fondo_inicial) + float(total_efectivo),
    }
    return render(request, 'ventas/cerrar_caja.html', context)


@login_required
def detalle_corte(request, pk):
    if get_max_permission(request.user) == 0:
        return redirect('dashboard')

    tienda_actual = get_tienda_actual(request.user)
    
    if tienda_actual:
        corte = get_object_or_404(CorteCaja, pk=pk, tienda=tienda_actual)
    else:
        corte = get_object_or_404(CorteCaja, pk=pk)

    # Si no es staff, solo puede ver sus propios cortes
    if not request.user.is_staff and corte.usuario != request.user:
        messages.error(request, 'No tienes permiso para ver este corte.')
        return redirect('ventas:historial_cortes')

    ventas = Venta.objects.filter(
        usuario    = corte.usuario,
        fecha__gte = corte.fecha_apertura,
        estado     = 'completada',
    )
    if corte.fecha_cierre:
        ventas = ventas.filter(fecha__lte=corte.fecha_cierre)

    return render(request, 'ventas/detalle_corte.html', {
        'corte':  corte,
        'ventas': ventas,
        'is_staff': request.user.is_staff,
    })

@login_required
def historial_cortes(request):
    if get_max_permission(request.user) == 0:
        return redirect('dashboard')

    # Obtener parámetros de filtro
    fecha_desde = request.GET.get('fecha_desde', '')
    fecha_hasta = request.GET.get('fecha_hasta', '')
    
    tienda_actual = get_tienda_actual(request.user)

    # Si NO es staff, solo sus cortes
    if not request.user.is_staff:
        if tienda_actual:
            cortes = CorteCaja.objects.filter(usuario=request.user, tienda=tienda_actual)
        else:
            cortes = CorteCaja.objects.filter(usuario=request.user)
    else:
        if tienda_actual:
            cortes = CorteCaja.objects.select_related('usuario').filter(tienda=tienda_actual)
        else:
            cortes = CorteCaja.objects.select_related('usuario').all()

    # Aplicar filtros de fecha
    if fecha_desde:
        cortes = cortes.filter(fecha_apertura__date__gte=fecha_desde)
    if fecha_hasta:
        cortes = cortes.filter(fecha_apertura__date__lte=fecha_hasta)

    # Ordenar por fecha de apertura descendente
    cortes = cortes.order_by('-fecha_apertura')

    # Exportar CSV (sin cambios)
    if request.GET.get('export') == 'csv':
        import csv
        from django.http import HttpResponse
        
        response = HttpResponse(content_type='text/csv')
        
        if fecha_desde and fecha_hasta:
            filename = f'cortes_caja_{fecha_desde}_a_{fecha_hasta}.csv'
        elif fecha_desde:
            filename = f'cortes_caja_desde_{fecha_desde}.csv'
        elif fecha_hasta:
            filename = f'cortes_caja_hasta_{fecha_hasta}.csv'
        else:
            filename = 'cortes_caja_completo.csv'
        
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response.write('\ufeff'.encode('utf-8'))
        
        writer = csv.writer(response)
        writer.writerow([
            'ID', 'Cajero', 'Fecha apertura', 'Fecha cierre', 
            'Fondo inicial', 'Total ventas', 'Total efectivo', 
            'Total tarjeta', 'Total transferencia', 'Número ventas',
            'Conteo efectivo', 'Conteo tarjeta', 'Conteo transferencia',
            'Diferencia efectivo', 'Diferencia tarjeta', 'Diferencia transferencia',
            'Estado', 'Notas'
        ])
        
        for corte in cortes:
            writer.writerow([
                corte.id,
                corte.usuario.username,
                corte.fecha_apertura.strftime('%Y-%m-%d %H:%M:%S'),
                corte.fecha_cierre.strftime('%Y-%m-%d %H:%M:%S') if corte.fecha_cierre else '',
                float(corte.fondo_inicial),
                float(corte.total_ventas),
                float(corte.total_efectivo),
                float(corte.total_tarjeta),
                float(corte.total_transferencia),
                corte.num_ventas,
                float(corte.conteo_efectivo),
                float(corte.conteo_tarjeta),
                float(corte.conteo_transferencia),
                float(corte.diferencia_efectivo),
                float(corte.diferencia_tarjeta),
                float(corte.diferencia_transferencia),
                corte.get_estado_display(),
                corte.notas,
            ])
        
        return response

    paginator = Paginator(cortes, 15)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'page_obj': page_obj,
        'is_staff': request.user.is_staff,
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
    }
    return render(request, 'ventas/historial_cortes.html', context)



# ─── Devoluciones ─────────────────────────────────────────

@login_required
def buscar_venta_devolucion(request):
    """Vista para buscar una venta para devolución"""
    if get_max_permission(request.user) == 0:
        return redirect('dashboard')
    
    from django.utils import timezone
    from datetime import timedelta
    
    ventas_recientes = []
    error = None
    venta = None
    
    # Obtener ventas de los últimos 3 días (que se pueden devolver)
    fecha_limite = timezone.now() - timedelta(days=3)

    tienda_actual = get_tienda_actual(request.user)

    if tienda_actual:
        ventas_recientes = Venta.objects.filter(
            estado='completada',
            fecha__gte=fecha_limite,
            tienda=tienda_actual
        ).order_by('-fecha')[:20]
    else:
        ventas_recientes = Venta.objects.filter(
            estado='completada',
            fecha__gte=fecha_limite
        ).order_by('-fecha')[:20]

    if request.method == 'POST':
        ticket = request.POST.get('ticket', '').strip()
        
        if not ticket:
            error = 'Ingrese un número de ticket'
        else:
            try:
                ticket_num = int(ticket)
                
                # Construir query base
                query = Venta.objects.filter(
                    folio=ticket_num,
                    estado='completada'
                )
                
                # Solo filtrar por tienda si no es superadmin
                if tienda_actual:
                    query = query.filter(tienda=tienda_actual)
                
                venta = query.first()
                
                if not venta:
                    error = f'No se encontró la venta #{ticket}'
                else:
                    # Verificar plazo máximo de 3 días
                    ahora = timezone.now()
                    limite = venta.fecha + timedelta(days=3)
                    
                    if ahora > limite:
                        error = f'La venta #{ticket} tiene más de 3 días. No se puede devolver.'
                        venta = None
                    else:
                        # Verificar si ya tiene devoluciones completas
                        devoluciones = Devolucion.objects.filter(venta=venta, estado='aprobada')
                        total_devuelto = sum(d.total_devuelto for d in devoluciones)
                        
                        if total_devuelto >= venta.total:
                            error = f'La venta #{ticket} ya fue devuelta completamente.'
                            venta = None
                        else:
                            # Obtener detalles de la venta
                            detalles = venta.detalles.all()
                            # Calcular cantidades ya devueltas por producto
                            devueltos_por_producto = {}
                            for dev in devoluciones:
                                for detalle_dev in dev.detalles.all():
                                    producto_id = detalle_dev.producto_id
                                    devueltos_por_producto[producto_id] = devueltos_por_producto.get(producto_id, 0) + detalle_dev.cantidad
                            
                            # Preparar lista de detalles con disponibilidad
                            detalles_con_disponibilidad = []
                            for detalle in detalles:
                                ya_devuelto = devueltos_por_producto.get(detalle.producto_id, 0)
                                disponible = detalle.cantidad - ya_devuelto
                                detalles_con_disponibilidad.append({
                                    'detalle': detalle,
                                    'ya_devuelto': ya_devuelto,
                                    'disponible': disponible
                                })
                            
                            return render(request, 'ventas/registrar_devolucion.html', {
                                'venta': venta,
                                'detalles_con_disponibilidad': detalles_con_disponibilidad,
                                'total_devuelto_anterior': total_devuelto,
                            })
            except ValueError:
                error = 'El número de ticket debe ser válido'
    
    return render(request, 'ventas/buscar_venta_devolucion.html', {
        'ventas_recientes': ventas_recientes,
        'error': error,
    })



@login_required
@transaction.atomic
def registrar_devolucion(request, venta_id):
    """Registra la devolución de productos"""
    if get_max_permission(request.user) == 0:
        return redirect('dashboard')
    
    venta = get_object_or_404(Venta, id=venta_id, estado='completada')
    
    # Verificar plazo máximo de 3 días
    from django.utils import timezone
    from datetime import timedelta
    
    ahora = timezone.now()
    limite = venta.fecha + timedelta(days=3)
    
    if ahora > limite:
        messages.error(request, f'La venta #{venta.id} tiene más de 3 días. No se puede devolver.')
        return redirect('ventas:buscar_venta_devolucion')
    
    if request.method == 'POST':
        motivo = request.POST.get('motivo', '').strip()
        total_devuelto = Decimal('0')
        productos_devueltos = []
        
        # Procesar cada detalle de la venta
        for detalle in venta.detalles.all():
            cantidad_key = f'cantidad_{detalle.id}'
            cantidad_str = request.POST.get(cantidad_key, '0')
            
            try:
                cantidad = int(cantidad_str)
                if cantidad > 0:
                    if cantidad <= detalle.cantidad:
                        productos_devueltos.append({
                            'detalle': detalle,
                            'cantidad': cantidad,
                            'precio': detalle.precio_unitario,
                            'subtotal': detalle.precio_unitario * cantidad
                        })
                        total_devuelto += detalle.precio_unitario * cantidad
                    else:
                        messages.error(request, f'La cantidad devuelta de "{detalle.producto.nombre}" no puede ser mayor a {detalle.cantidad}')
                        return redirect('ventas:registrar_devolucion', venta_id=venta.id)
            except ValueError:
                pass
        
        if not productos_devueltos:
            messages.error(request, 'Debe seleccionar al menos un producto para devolver.')
            return redirect('ventas:registrar_devolucion', venta_id=venta.id)
        
        # Crear la devolución

        devolucion = Devolucion.objects.create(
        venta=venta,
        usuario=request.user,
        motivo=motivo if motivo else 'Devolución de productos',
        total_devuelto=total_devuelto,
        estado='aprobada',
        tienda=request.user.tienda,  
        )
        
        # Crear detalles de devolución y actualizar inventario
        for item in productos_devueltos:
            detalle = item['detalle']
            cantidad = item['cantidad']
            
            # Registrar detalle de devolución
            DetalleDevolucion.objects.create(
                devolucion=devolucion,
                producto=detalle.producto,
                cantidad=cantidad,
                precio_unitario=detalle.precio_unitario
            )
            
            # Actualizar inventario (sumar stock)
            producto = detalle.producto
            stock_anterior = producto.stock
            producto.stock += cantidad
            producto.save()
            
            # Registrar movimiento de stock
            from inventario.models import MovimientoStock
            MovimientoStock.objects.create(
                producto=producto,
                tipo='entrada',
                cantidad=cantidad,
                stock_anterior=stock_anterior,
                stock_nuevo=producto.stock,
                motivo=f'Devolución de venta #{venta.id}',
                usuario=request.user
            )
        
        # Actualizar total devuelto en la venta
        venta.total_devuelto = (venta.total_devuelto or 0) + total_devuelto
        
        # Si se devolvió todo, cambiar estado a 'devuelta'
        if venta.total_devuelto >= venta.total:
            venta.estado = 'devuelta'
        
        venta.save()
        
        # Si la devolución fue en efectivo, actualizar el corte de caja
        if venta.metodo_pago == 'efectivo':
            corte = get_corte_activo(request.user)
            if corte:
                # Restar del total de efectivo en el corte abierto
                corte.total_efectivo -= total_devuelto
                corte.total_ventas -= total_devuelto
                corte.save()
        
        messages.success(
            request,
            f'✅ Devolución registrada exitosamente. Total devuelto: ${total_devuelto}'
        )
        
        return redirect('ventas:buscar_venta_devolucion')
    
    # GET: Mostrar formulario
    detalles = venta.detalles.all()
    devoluciones_existentes = Devolucion.objects.filter(venta=venta, estado='aprobada')
    
    # Calcular cantidades ya devueltas por producto
    devueltos_por_producto = {}
    for dev in devoluciones_existentes:
        for detalle_dev in dev.detalles.all():
            producto_id = detalle_dev.producto_id
            devueltos_por_producto[producto_id] = devueltos_por_producto.get(producto_id, 0) + detalle_dev.cantidad
    
    total_devuelto_anterior = sum(float(d.total_devuelto) for d in devoluciones_existentes)
    
    # Preparar lista de detalles con disponibilidad
    detalles_con_disponibilidad = []
    for detalle in detalles:
        ya_devuelto = devueltos_por_producto.get(detalle.producto_id, 0)
        disponible = detalle.cantidad - ya_devuelto
        detalles_con_disponibilidad.append({
            'detalle': detalle,
            'ya_devuelto': ya_devuelto,
            'disponible': disponible
        })
    
    return render(request, 'ventas/registrar_devolucion.html', {
        'venta': venta,
        'detalles_con_disponibilidad': detalles_con_disponibilidad,
        'total_devuelto_anterior': total_devuelto_anterior,
    })