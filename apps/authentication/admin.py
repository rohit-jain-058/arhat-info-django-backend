from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display    = ('email', 'full_name', 'is_active', 'is_staff', 'is_verified', 'date_joined')
    list_filter     = ('is_active', 'is_staff', 'is_verified', 'date_joined')
    search_fields   = ('email', 'first_name', 'last_name')
    ordering        = ('-date_joined',)
    readonly_fields = ('id', 'date_joined', 'last_login')

    fieldsets = (
        (None,               {'fields': ('id', 'email', 'password')}),
        (_('Personal info'), {'fields': ('first_name', 'last_name', 'avatar')}),
        (_('Permissions'),   {'fields': ('is_active', 'is_staff', 'is_superuser',
                                         'is_verified', 'groups', 'user_permissions')}),
        (_('Important dates'),{'fields': ('last_login', 'date_joined')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'first_name', 'last_name', 'password1', 'password2'),
        }),
    )
