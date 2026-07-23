from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from apps.core import views as core_views

urlpatterns = [
    path("health/", core_views.health_live, name="health"),
    path("health/live/", core_views.health_live, name="health_live"),
    path("health/ready/", core_views.health_ready, name="health_ready"),
    path(
        "entrar/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path("sair/", auth_views.LogoutView.as_view(), name="logout"),
    path(
        "senha/alterar/",
        auth_views.PasswordChangeView.as_view(
            template_name="registration/password_change_form.html",
            success_url="/senha/alterada/",
        ),
        name="password_change",
    ),
    path(
        "senha/alterada/",
        auth_views.PasswordChangeDoneView.as_view(
            template_name="registration/password_change_done.html"
        ),
        name="password_change_done",
    ),
    path("admin/", admin.site.urls),
    path("rebanho/", include("apps.rebanho.urls")),
    path("reproducao/", include("apps.reproducao.urls")),
    path("lactacoes/", include("apps.lactacao.urls")),
    path("leite/", include("apps.leite.urls")),
    path("saude/", include("apps.saude.urls")),
    path("financeiro/", include("apps.financeiro.urls")),
    path("relatorios/", include("apps.relatorios.urls")),
    path("auditoria/", include("apps.auditoria.urls")),
    path("", include("apps.core.urls")),
]

handler400 = "apps.core.views.manipulador_erro_400"
handler403 = "apps.core.views.manipulador_erro_403"
handler404 = "apps.core.views.manipulador_erro_404"
handler500 = "apps.core.views.manipulador_erro_500"

admin.site.site_header = "Gestão Rural — Administração"
admin.site.site_title = "Gestão Rural"
admin.site.index_title = "Administração técnica"
