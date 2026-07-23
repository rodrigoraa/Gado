from django.urls import path

from .views import lista

app_name = "auditoria"
urlpatterns = [path("", lista, name="lista")]
