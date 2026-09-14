from django import forms
from .models import Producto

class ProductoForm(forms.ModelForm):
    class Meta:
        model = Producto
        fields = [
            'nombre', 'proveedor', 'precio_compra',
            'porcentaje_ganancia', 'stock_actual', 'stock_minimo',
        ]
        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'Ej: Coca-Cola 1.5L'
            }),
            'proveedor': forms.Select(attrs={'class': 'form-select'}),
            'precio_compra': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.01', 'min': '0'
            }),
            'porcentaje_ganancia': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.01', 'min': '0'
            }),
            'stock_actual': forms.NumberInput(attrs={
                'class': 'form-control', 'min': '0'
            }),
            'stock_minimo': forms.NumberInput(attrs={
                'class': 'form-control', 'min': '0'
            }),
        }