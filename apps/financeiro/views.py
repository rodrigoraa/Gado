from __future__ import annotations

from pathlib import Path
from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView

from .forms import (
    AjusteFechamentoForm,
    CancelamentoForm,
    EntregaLeiteForm,
    FechamentoLeiteForm,
    LaticinioForm,
    PrecoLeiteForm,
    RecebimentoLeiteForm,
)
from .models import EntregaLeite, FechamentoLeite, Laticinio, PrecoLeite, RecebimentoLeite
from .selectors import conferencia_mensal, listar_entregas, listar_fechamentos
from .services import (
    cancelar_entrega,
    cancelar_fechamento,
    cancelar_recebimento,
    finalizar_fechamento,
)


def _data_filtro(valor: str):  # type: ignore[no-untyped-def]
    try:
        return parse_date(valor)
    except ValueError:
        return None


def _adicionar_erros(form: Any, erro: ValidationError) -> None:
    if hasattr(erro, "message_dict"):
        for campo, mensagens_erro in erro.message_dict.items():
            destino = campo if campo in form.fields else None
            for mensagem in mensagens_erro:
                form.add_error(destino, mensagem)
    else:
        for mensagem in erro.messages:
            form.add_error(None, mensagem)


class CadastroListView(LoginRequiredMixin, ListView):
    template_name = "financeiro/lista.html"
    context_object_name = "objetos"
    paginate_by = 24
    titulo = ""
    nome_url_novo = ""
    nome_url_editar = ""
    nome_url_detalhe = ""
    nome_url_cancelar = ""
    tipo_arquivo_privado = ""
    mostrar_filtro_datas = False

    def get_template_names(self) -> list[str]:
        if self.request.headers.get("HX-Request") == "true":
            return ["financeiro/_lista.html"]
        return [self.template_name]

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        contexto = super().get_context_data(**kwargs)
        contexto.update(
            {
                "titulo": self.titulo,
                "nome_url_novo": self.nome_url_novo,
                "nome_url_editar": self.nome_url_editar,
                "nome_url_detalhe": self.nome_url_detalhe,
                "nome_url_cancelar": self.nome_url_cancelar,
                "tipo_arquivo_privado": self.tipo_arquivo_privado,
                "mostrar_filtro_datas": self.mostrar_filtro_datas,
            }
        )
        return contexto


class LaticinioListView(CadastroListView):
    model = Laticinio
    titulo = "Laticínios"
    nome_url_novo = "financeiro:laticinio_novo"
    nome_url_editar = "financeiro:laticinio_editar"


class PrecoListView(CadastroListView):
    model = PrecoLeite
    titulo = "Histórico de preços"
    nome_url_novo = "financeiro:preco_novo"
    nome_url_editar = "financeiro:preco_editar"

    def get_queryset(self):  # type: ignore[no-untyped-def]
        return PrecoLeite.objects.select_related("laticinio")


class EntregaListView(CadastroListView):
    model = EntregaLeite
    titulo = "Entregas de leite"
    nome_url_novo = "financeiro:entrega_nova"
    nome_url_editar = "financeiro:entrega_editar"
    nome_url_detalhe = "financeiro:entrega_detalhe"
    nome_url_cancelar = "financeiro:entrega_cancelar"
    mostrar_filtro_datas = True

    def get_queryset(self):  # type: ignore[no-untyped-def]
        return listar_entregas(
            data_inicial=_data_filtro(self.request.GET.get("data_inicial", "")),
            data_final=_data_filtro(self.request.GET.get("data_final", "")),
        )


class FechamentoListView(CadastroListView):
    model = FechamentoLeite
    titulo = "Fechamentos"
    nome_url_novo = "financeiro:fechamento_novo"
    nome_url_editar = "financeiro:fechamento_editar"
    nome_url_detalhe = "financeiro:fechamento_detalhe"
    nome_url_cancelar = "financeiro:fechamento_cancelar"

    def get_queryset(self):  # type: ignore[no-untyped-def]
        return listar_fechamentos()


class RecebimentoListView(CadastroListView):
    model = RecebimentoLeite
    titulo = "Recebimentos"
    nome_url_novo = "financeiro:recebimento_novo"
    nome_url_cancelar = "financeiro:recebimento_cancelar"
    tipo_arquivo_privado = "recebimento"

    def get_queryset(self):  # type: ignore[no-untyped-def]
        return RecebimentoLeite.objects.filter(ativo_registro=True).select_related(
            "fechamento", "fechamento__laticinio"
        )


class EntregaDetailView(LoginRequiredMixin, DetailView):
    model = EntregaLeite
    template_name = "financeiro/entrega_detail.html"
    context_object_name = "entrega"

    def get_queryset(self):  # type: ignore[no-untyped-def]
        return EntregaLeite.objects.select_related("laticinio").prefetch_related("fechamentos")


class FechamentoDetailView(LoginRequiredMixin, DetailView):
    model = FechamentoLeite
    template_name = "financeiro/fechamento_detail.html"
    context_object_name = "fechamento"

    def get_queryset(self):  # type: ignore[no-untyped-def]
        return FechamentoLeite.objects.select_related("laticinio").prefetch_related(
            "entregas", "recebimentos"
        )


class CadastroFormView(LoginRequiredMixin, View):
    template_name = "shared/form.html"
    model = Laticinio
    form_class = LaticinioForm
    titulo = "Cadastro"
    sucesso_url = reverse_lazy("financeiro:inicio")
    mensagem_sucesso = "Registro salvo com sucesso."
    campos_iniciais_url: tuple[str, ...] = ()
    objeto: Any = None

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if object_id := kwargs.get("pk"):
            self.objeto = get_object_or_404(self.model, pk=object_id)
        return super().dispatch(request, *args, **kwargs)

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        initial = {
            campo: request.GET[campo]
            for campo in self.campos_iniciais_url
            if request.GET.get(campo)
        }
        return render(
            request,
            self.template_name,
            {
                "form": self.form_class(instance=self.objeto, initial=initial),
                "titulo": self.titulo,
            },
        )

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        form = self.form_class(request.POST, request.FILES, instance=self.objeto)
        if form.is_valid():
            try:
                form.save()
            except ValidationError as erro:
                _adicionar_erros(form, erro)
            else:
                messages.success(request, self.mensagem_sucesso)
                return redirect(request.get_full_path())
        return render(
            request, self.template_name, {"form": form, "titulo": self.titulo}, status=422
        )


class LaticinioFormView(CadastroFormView):
    model = Laticinio
    form_class = LaticinioForm
    titulo = "Laticínio"
    sucesso_url = reverse_lazy("financeiro:laticinios")


class PrecoFormView(CadastroFormView):
    model = PrecoLeite
    form_class = PrecoLeiteForm
    titulo = "Preço do leite"
    sucesso_url = reverse_lazy("financeiro:precos")


class EntregaFormView(CadastroFormView):
    model = EntregaLeite
    form_class = EntregaLeiteForm
    titulo = "Entrega de leite"
    sucesso_url = reverse_lazy("financeiro:entregas")


class FechamentoCreateView(CadastroFormView):
    model = FechamentoLeite
    form_class = FechamentoLeiteForm
    titulo = "Criar fechamento"
    sucesso_url = reverse_lazy("financeiro:fechamentos")


class FechamentoUpdateView(CadastroFormView):
    model = FechamentoLeite
    form_class = AjusteFechamentoForm
    titulo = "Conferir/ajustar fechamento"
    sucesso_url = reverse_lazy("financeiro:fechamentos")


class FechamentoFinalizarView(LoginRequiredMixin, View):
    template_name = "shared/confirm.html"

    def _fechamento(self, pk: object) -> FechamentoLeite:
        return get_object_or_404(
            FechamentoLeite,
            pk=pk,
            ativo_registro=True,
            situacao=FechamentoLeite.Situacao.ABERTO,
        )

    def get(self, request: HttpRequest, pk: object) -> HttpResponse:
        fechamento = self._fechamento(pk)
        return render(
            request,
            self.template_name,
            {
                "titulo": "Finalizar fechamento",
                "mensagem": (
                    f"Conferir e finalizar {fechamento}. As entregas incluídas "
                    "serão marcadas como fechadas."
                ),
                "voltar_url": reverse_lazy("financeiro:fechamento_detalhe", kwargs={"pk": pk}),
            },
        )

    def post(self, request: HttpRequest, pk: object) -> HttpResponse:
        fechamento = self._fechamento(pk)
        try:
            finalizar_fechamento(fechamento=fechamento)
        except ValidationError as erro:
            return render(
                request,
                self.template_name,
                {
                    "titulo": "Finalizar fechamento",
                    "mensagem": " ".join(erro.messages),
                    "voltar_url": reverse_lazy("financeiro:fechamento_detalhe", kwargs={"pk": pk}),
                },
                status=422,
            )
        messages.success(request, "Fechamento finalizado e entregas conciliadas.")
        return redirect("financeiro:fechamento_detalhe", pk=pk)


class RecebimentoFormView(CadastroFormView):
    model = RecebimentoLeite
    form_class = RecebimentoLeiteForm
    titulo = "Registrar recebimento"
    sucesso_url = reverse_lazy("financeiro:recebimentos")
    campos_iniciais_url = ("fechamento",)

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if kwargs.get("pk"):
            return redirect("financeiro:recebimentos")
        return super().dispatch(request, *args, **kwargs)


class CancelarView(LoginRequiredMixin, View):
    template_name = "shared/confirm.html"
    model = EntregaLeite
    titulo = "Cancelar registro"
    sucesso_url = "financeiro:inicio"
    service = staticmethod(cancelar_entrega)

    def _objeto(self, pk: object):  # type: ignore[no-untyped-def]
        return get_object_or_404(self.model, pk=pk, ativo_registro=True)

    def get(self, request: HttpRequest, pk: object) -> HttpResponse:
        objeto = self._objeto(pk)
        return render(
            request,
            self.template_name,
            {
                "form": CancelamentoForm(),
                "titulo": self.titulo,
                "mensagem": f"{objeto} será mantido no histórico.",
            },
        )

    def post(self, request: HttpRequest, pk: object) -> HttpResponse:
        objeto = self._objeto(pk)
        form = CancelamentoForm(request.POST)
        if form.is_valid():
            try:
                self.service(
                    **{self.model._meta.model_name.replace("leite", ""): objeto},
                )
            except TypeError:
                # As subclasses usam argumentos explícitos; este ramo não deve ocorrer.
                raise
            except ValidationError as erro:
                _adicionar_erros(form, erro)
            else:
                messages.success(request, "Registro cancelado sem apagar o histórico.")
                return redirect(self.sucesso_url)
        return render(
            request,
            self.template_name,
            {"form": form, "titulo": self.titulo, "mensagem": f"Cancelar {objeto}?"},
            status=422,
        )


class EntregaCancelarView(CancelarView):
    model = EntregaLeite
    titulo = "Cancelar entrega"
    sucesso_url = "financeiro:entregas"
    service = staticmethod(cancelar_entrega)

    def post(self, request: HttpRequest, pk: object) -> HttpResponse:
        return self._post_explicito(request, pk, "entrega")

    def _post_explicito(self, request: HttpRequest, pk: object, argumento: str) -> HttpResponse:
        objeto = self._objeto(pk)
        form = CancelamentoForm(request.POST)
        if form.is_valid():
            try:
                self.service(**{argumento: objeto})
            except ValidationError as erro:
                _adicionar_erros(form, erro)
            else:
                messages.success(request, "Registro cancelado sem apagar o histórico.")
                return redirect(self.sucesso_url)
        return render(
            request,
            self.template_name,
            {"form": form, "titulo": self.titulo, "mensagem": f"Cancelar {objeto}?"},
            status=422,
        )


class FechamentoCancelarView(EntregaCancelarView):
    model = FechamentoLeite
    titulo = "Cancelar fechamento"
    sucesso_url = "financeiro:fechamentos"
    service = staticmethod(cancelar_fechamento)

    def post(self, request: HttpRequest, pk: object) -> HttpResponse:
        return self._post_explicito(request, pk, "fechamento")


class RecebimentoCancelarView(EntregaCancelarView):
    model = RecebimentoLeite
    titulo = "Cancelar recebimento"
    sucesso_url = "financeiro:recebimentos"
    service = staticmethod(cancelar_recebimento)

    def post(self, request: HttpRequest, pk: object) -> HttpResponse:
        return self._post_explicito(request, pk, "recebimento")


class ConferenciaMensalView(LoginRequiredMixin, TemplateView):
    template_name = "financeiro/conferencia_mensal.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        contexto = super().get_context_data(**kwargs)
        hoje = timezone.localdate()
        try:
            ano = int(self.request.GET.get("ano", hoje.year))
            mes = int(self.request.GET.get("mes", hoje.month))
            if not 1 <= mes <= 12:
                raise ValueError
        except (TypeError, ValueError):
            ano, mes = hoje.year, hoje.month
        indice = ano * 12 + mes - 1
        anterior_indice = indice - 1
        proximo_indice = indice + 1
        contexto.update(conferencia_mensal(ano=ano, mes=mes))
        contexto.update(
            {
                "titulo": "Conferência mensal",
                "ano": ano,
                "mes": mes,
                "anterior_ano": anterior_indice // 12,
                "anterior_mes": anterior_indice % 12 + 1,
                "proximo_ano": proximo_indice // 12,
                "proximo_mes": proximo_indice % 12 + 1,
            }
        )
        return contexto


class ArquivoFinanceiroView(LoginRequiredMixin, View):
    arquivos = {
        "entrega": (EntregaLeite, "anexo"),
        "fechamento": (FechamentoLeite, "arquivo_demonstrativo"),
        "recebimento": (RecebimentoLeite, "anexo"),
    }

    def get(self, request: HttpRequest, tipo: str, pk: object) -> FileResponse:
        del request
        configuracao = self.arquivos.get(tipo)
        if not configuracao:
            raise Http404
        model, nome_campo = configuracao
        objeto = get_object_or_404(model, pk=pk)
        arquivo = getattr(objeto, nome_campo)
        if not arquivo:
            raise Http404
        try:
            arquivo_aberto = arquivo.open("rb")
        except (FileNotFoundError, OSError) as exc:
            raise Http404 from exc
        response = FileResponse(
            arquivo_aberto,
            as_attachment=True,
            filename=Path(arquivo.name).name,
        )
        response["Cache-Control"] = "private, no-store"
        return response
