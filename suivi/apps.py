from django.apps import AppConfig


class SuiviConfig(AppConfig):
    name = 'suivi'

    def ready(self):
        from . import acces_double_facteur  # noqa: F401  (signal user_logged_in)
