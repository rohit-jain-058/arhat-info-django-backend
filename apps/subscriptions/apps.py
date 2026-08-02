from django.apps import AppConfig


class SubscriptionsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name               = 'apps.subscriptions'
    verbose_name       = 'Subscriptions'

    def ready(self):
        # Import signals when app loads
        try:
            from . import signals  # noqa
        except ImportError:
            pass
