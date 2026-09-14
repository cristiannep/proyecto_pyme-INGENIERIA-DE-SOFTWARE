# core/models.py
from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from decimal import Decimal
import random

# ========================================================== 
# CONFIGURACIÓN GLOBAL 
# ========================================================== 
IVA = Decimal('0.19')  # IVA del 19%

# ========================================================== 
# MODELO: PROVEEDOR 
# ========================================================== 
class Proveedor(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    telefono = models.CharField(max_length=20, blank=True, null=True)
    
    def __str__(self):
        return self.nombre

# ========================================================== 
# MODELO: PRODUCTO 
# ========================================================== 
class Producto(models.Model):
    nombre = models.CharField(max_length=100)
    proveedor = models.ForeignKey(
        Proveedor, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='productos'
    )
    codigo_barras = models.CharField(max_length=13, unique=True, null=True, blank=True)
    precio_compra = models.DecimalField(max_digits=10, decimal_places=2)
    porcentaje_ganancia = models.DecimalField(max_digits=5, decimal_places=2)
    stock_actual = models.PositiveIntegerField(default=0)
    stock_minimo = models.PositiveIntegerField(default=5)
    
    def save(self, *args, **kwargs):
        if not self.codigo_barras:
            self.codigo_barras = str(random.randint(1000000000000, 9999999999999))
        super().save(*args, **kwargs)
    
    @property
    def precio_venta(self):
        """Calcula el precio de venta con ganancia + IVA"""
        if not self.precio_compra or not self.porcentaje_ganancia:
            return Decimal('0.00')
        ganancia = self.porcentaje_ganancia / Decimal('100')
        precio_base = self.precio_compra * (Decimal('1') + ganancia)
        precio_con_iva = precio_base * (Decimal('1') + IVA)
        return precio_con_iva.quantize(Decimal('0.01'))
    
    def __str__(self):
        return self.nombre

# ========================================================== 
# MODELO: COMPRA
# ========================================================== 
class Compra(models.Model):
    fecha = models.DateTimeField(auto_now_add=True)
    proveedor = models.ForeignKey(Proveedor, on_delete=models.PROTECT)
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT)
    cantidad = models.PositiveIntegerField()
    precio_compra_unitario = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Para rastrear cambios en edición
    _cantidad_anterior = None
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cantidad_anterior = self.cantidad if self.pk else None
    
    @property
    def total_compra(self):
        """Total = cantidad * precio unitario"""
        if not self.precio_compra_unitario:
            return Decimal('0.00')
        return (self.cantidad * self.precio_compra_unitario).quantize(Decimal('0.01'))
    
    def save(self, *args, **kwargs):
        """
        Al guardar una compra:
        - Autoasigna el precio de compra del producto si no existe
        - Aumenta el stock del producto
        - Si es edición, ajusta la diferencia
        """
        # Autoasignar precio de compra del producto si no se especificó
        if not self.precio_compra_unitario and self.producto:
            self.precio_compra_unitario = self.producto.precio_compra
        
        nuevo = self.pk is None
        
        if nuevo:
            # Compra nueva: aumentar stock
            self.producto.stock_actual += self.cantidad
            self.producto.save()
        elif self._cantidad_anterior is not None:
            # Edición: ajustar la diferencia
            diferencia = self.cantidad - self._cantidad_anterior
            if diferencia != 0:
                self.producto.stock_actual += diferencia
                self.producto.save()
                self._cantidad_anterior = self.cantidad
        
        super().save(*args, **kwargs)
    
    def delete(self, *args, **kwargs):
        """Al eliminar compra, disminuir el stock"""
        self.producto.stock_actual -= self.cantidad
        self.producto.save()
        super().delete(*args, **kwargs)
    
    def __str__(self):
        return f"Compra #{self.id} - {self.producto.nombre} ({self.cantidad} unidades)"

# ========================================================== 
# MODELO: VENTA 
# ========================================================== 
class Venta(models.Model):
    fecha = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    producto = models.ForeignKey('Producto', on_delete=models.PROTECT, null=True, blank=True)
    cantidad = models.PositiveIntegerField(default=1)
    
    #Campo para rastrear cantidad anterior (usado en edición)
    _cantidad_anterior = None
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Guardar cantidad original al cargar el objeto
        self._cantidad_anterior = self.cantidad if self.pk else None
    
    @property
    def total(self):
        """Calcula total desde el producto asociado"""
        if self.producto and self.cantidad:
            return self.producto.precio_venta * self.cantidad
        elif self.detalles.exists():
            return sum(detalle.subtotal for detalle in self.detalles.all())
        return Decimal('0.00')
    
    def clean(self):
        """ Validación antes de guardar"""
        if self.producto and self.cantidad:
            # Si es una venta nueva
            if not self.pk:
                if self.cantidad > self.producto.stock_actual:
                    raise ValidationError(
                        f"Stock insuficiente para '{self.producto.nombre}'. "
                        f"Disponible: {self.producto.stock_actual} unidades. "
                        f"Solicitado: {self.cantidad} unidades."
                    )
            # Si es una edición
            else:
                diferencia = self.cantidad - self._cantidad_anterior
                stock_disponible = self.producto.stock_actual + self._cantidad_anterior
                
                if self.cantidad > stock_disponible:
                    raise ValidationError(
                        f"Stock insuficiente para '{self.producto.nombre}'. "
                        f"Stock disponible (incluyendo esta venta): {stock_disponible} unidades. "
                        f"Solicitado: {self.cantidad} unidades."
                    )
    
    def save(self, *args, **kwargs):
        """Guarda venta, asigna usuario y crea/actualiza DetalleVenta automáticamente."""
        # Validar antes de guardar
        self.full_clean()
        
        nuevo = self.pk is None
        super().save(*args, **kwargs)
        
        if nuevo and self.producto:
            # Crear automáticamente el detalle (que se encargará del stock)
            DetalleVenta.objects.create(
                venta=self,
                producto=self.producto,
                cantidad=self.cantidad,
                precio_venta_registrado=self.producto.precio_venta
            )
        elif not nuevo and self.producto and self._cantidad_anterior is not None:
            # Si se editó la cantidad, actualizar el detalle
            diferencia = self.cantidad - self._cantidad_anterior
            
            if diferencia != 0:
                # Actualizar el detalle de venta (sin tocar el stock aquí)
                detalle = self.detalles.first()
                if detalle:
                    # Primero devolver el stock anterior
                    self.producto.stock_actual += self._cantidad_anterior
                    # Luego descontar la nueva cantidad
                    self.producto.stock_actual -= self.cantidad
                    self.producto.save()
                    
                    # Actualizar el detalle
                    detalle.cantidad = self.cantidad
                    detalle.precio_venta_registrado = self.producto.precio_venta
                    detalle._cantidad_anterior = self.cantidad  # Actualizar su tracking
                    detalle.save(update_fields=['cantidad', 'precio_venta_registrado'])
                
                # Actualizar cantidad anterior para próximas ediciones
                self._cantidad_anterior = self.cantidad
    
    def delete(self, *args, **kwargs):
        """ Al eliminar venta, el DetalleVenta se encarga de devolver el stock (CASCADE)"""
        # No tocamos el stock aquí, el CASCADE elimina DetalleVenta
        # y su método delete() devuelve el stock automáticamente
        super().delete(*args, **kwargs)
    
    def __str__(self):
        return f"Venta #{self.id} del {self.fecha.strftime('%d-%m-%Y')}"

# ========================================================== 
# MODELO: DETALLE DE VENTA 
# ========================================================== 
class DetalleVenta(models.Model):
    venta = models.ForeignKey(
        Venta, 
        related_name='detalles', 
        on_delete=models.CASCADE
    )
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT)
    cantidad = models.PositiveIntegerField()
    precio_venta_registrado = models.DecimalField(max_digits=10, decimal_places=2)
    proveedor = models.ForeignKey(Proveedor, on_delete=models.SET_NULL, null=True, blank=True)
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Para rastrear cambios en edición
    _cantidad_anterior = None
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cantidad_anterior = self.cantidad if self.pk else None
    
    @property
    def subtotal(self):
        """Subtotal = cantidad * precio unitario"""
        if not self.precio_venta_registrado:
            return Decimal('0.00')
        return (self.cantidad * self.precio_venta_registrado).quantize(Decimal('0.01'))
    
    def clean(self):
        """ Validación antes de guardar el detalle"""
        if not self.pk:  # Creación nueva
            if self.producto.stock_actual < self.cantidad:
                raise ValidationError(
                    f"No hay stock suficiente para '{self.producto.nombre}'. "
                    f"Stock disponible: {self.producto.stock_actual} unidades. "
                    f"Cantidad solicitada: {self.cantidad} unidades."
                )
        else:  # Edición
            if self._cantidad_anterior is not None:
                diferencia = self.cantidad - self._cantidad_anterior
                stock_disponible = self.producto.stock_actual + self._cantidad_anterior
                
                if self.cantidad > stock_disponible:
                    raise ValidationError(
                        f"No hay stock suficiente para '{self.producto.nombre}'. "
                        f"Stock disponible (incluyendo esta venta): {stock_disponible} unidades. "
                        f"Solicitado: {self.cantidad} unidades."
                    )
    
    def save(self, *args, **kwargs):
        """
        Al guardar un detalle:
        - Autoasigna el precio si no existe.
        - Autoasigna el proveedor del producto.
        - Autoasigna el usuario de la venta.
        - Verifica que haya stock suficiente.
        - Descuenta/ajusta el inventario.
        """
        if not self.pk:
            if not self.precio_venta_registrado:
                self.precio_venta_registrado = self.producto.precio_venta
            
            if not self.proveedor and self.producto.proveedor:
                self.proveedor = self.producto.proveedor
            
            if not self.usuario and self.venta.usuario:
                self.usuario = self.venta.usuario
        
        # Validar antes de guardar
        if 'update_fields' not in kwargs:  # Evitar validación en updates internos
            self.full_clean()
        
        # Manejo de stock
        if not self.pk:
            # Creación: descontar stock
            self.producto.stock_actual -= self.cantidad
            self.producto.save()
        elif self._cantidad_anterior is not None:
            # Edición: ajustar la diferencia
            diferencia = self.cantidad - self._cantidad_anterior
            if diferencia != 0:
                self.producto.stock_actual -= diferencia
                self.producto.save()
                self._cantidad_anterior = self.cantidad
        
        super().save(*args, **kwargs)
    
    def delete(self, *args, **kwargs):
        """ Al eliminar el detalle, devolver el stock al producto."""
        self.producto.stock_actual += self.cantidad
        self.producto.save()
        super().delete(*args, **kwargs)
    
    def __str__(self):
        return f"{self.cantidad} x {self.producto.nombre}"