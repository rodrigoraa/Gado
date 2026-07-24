from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views import View
from django.views.generic import DetailView, ListView

from .forms import (
    CancelamentoForm,
    DescarteLeiteForm,
    EventoSaudeForm,
    ProdutoSaudeForm,
    TratamentoForm,
)
from .models import EventoSaude, ProdutoSaude, Tratamento
from .selectors import listar_eventos_saude, listar_produtos, listar_tratamentos
from .services import cancelar_evento_saude, cancelar_tratamento, registrar_descarte_leite


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
    template_name = "saude/lista.html"
    context_object_name = "objetos"
    paginate_by = 24
    titulo = ""
    nome_url_novo = ""
    nome_url_editar = ""
    nome_url_detalhe = ""
    nome_url_cancelar = ""

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        contexto = super().get_context_data(**kwargs)
        contexto.update(
            {
                "titulo": self.titulo,
                "nome_url_novo": self.nome_url_novo,
                "nome_url_editar": self.nome_url_editar,
                "nome_url_detalhe": self.nome_url_detalhe,
                "nome_url_cancelar": self.nome_url_cancelar,
            }
        )
        return contexto


class ProdutoListView(CadastroListView):
    model = ProdutoSaude
    titulo = "Produtos de saúde"
    nome_url_novo = "saude:produto_novo"
    nome_url_editar = "saude:produto_editar"

    def get_queryset(self):  # type: ignore[no-untyped-def]
        return listar_produtos(somente_ativos=False)


class TratamentoListView(CadastroListView):
    model = Tratamento
    titulo = "Tratamentos"
    nome_url_novo = "saude:tratamento_novo"
    nome_url_editar = "saude:tratamento_editar"
    nome_url_detalhe = "saude:tratamento_detalhe"
    nome_url_cancelar = "saude:tratamento_cancelar"

    def get_queryset(self):  # type: ignore[no-untyped-def]
        return listar_tratamentos(
            animal_id=self.request.GET.get("animal") or None,
            data_inicial=_data_filtro(self.request.GET.get("data_inicial", "")),
            data_final=_data_filtro(self.request.GET.get("data_final", "")),
        )


class TratamentoDetailView(LoginRequiredMixin, DetailView):
    model = Tratamento
    template_name = "saude/tratamento_detail.html"
    context_object_name = "tratamento"

    def get_queryset(self):  # type: ignore[no-untyped-def]
        return Tratamento.objects.select_related("animal", "produto").prefetch_related(
            "descartes_leite"
        )


class CadastroFormView(LoginRequiredMixin, View):
    template_name = "shared/form.html"
    model = ProdutoSaude
    form_class = ProdutoSaudeForm
    titulo = "Cadastro"
    sucesso_url = reverse_lazy("saude:inicio")
    campos_iniciais_url: tuple[str, ...] = ()
    objeto: Any = None

    def get_object_queryset(self):  # type: ignore[no-untyped-def]
        return self.model.objects.all()

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if object_id := kwargs.get("pk"):
            self.objeto = get_object_or_404(self.get_object_queryset(), pk=object_id)
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
                messages.success(request, "Registro salvo com sucesso.")
                return redirect(request.get_full_path())
        return render(
            request, self.template_name, {"form": form, "titulo": self.titulo}, status=422
        )


class ProdutoFormView(CadastroFormView):
    model = ProdutoSaude
    form_class = ProdutoSaudeForm
    titulo = "Produto de saúde"
    sucesso_url = reverse_lazy("saude:produtos")


class TratamentoFormView(CadastroFormView):
    model = Tratamento
    form_class = TratamentoForm
    titulo = "Registrar tratamento"
    sucesso_url = reverse_lazy("saude:tratamentos")
    campos_iniciais_url = ("animal",)


class TratamentoCancelarView(LoginRequiredMixin, View):
    template_name = "shared/confirm.html"

    def _tratamento(self, pk: object) -> Tratamento:
        return get_object_or_404(Tratamento, pk=pk, ativo_registro=True)

    def get(self, request: HttpRequest, pk: object) -> HttpResponse:
        tratamento = self._tratamento(pk)
        return render(
            request,
            self.template_name,
            {
                "form": CancelamentoForm(),
                "titulo": "Cancelar tratamento",
                "mensagem": f"{tratamento} será mantido no histórico.",
            },
        )

    def post(self, request: HttpRequest, pk: object) -> HttpResponse:
        tratamento = self._tratamento(pk)
        form = CancelamentoForm(request.POST)
        if form.is_valid():
            try:
                cancelar_tratamento(tratamento=tratamento, motivo=form.cleaned_data["motivo"])
            except ValidationError as erro:
                _adicionar_erros(form, erro)
            else:
                messages.success(request, "Tratamento cancelado sem apagar o histórico.")
                return redirect("saude:tratamentos")
        return render(
            request,
            self.template_name,
            {"form": form, "titulo": "Cancelar tratamento", "mensagem": f"Cancelar {tratamento}?"},
            status=422,
        )


class DescarteLeiteView(LoginRequiredMixin, View):
    template_name = "shared/form.html"

    def _tratamento(self, pk: object) -> Tratamento:
        return get_object_or_404(Tratamento, pk=pk, ativo_registro=True)

    def get(self, request: HttpRequest, pk: object) -> HttpResponse:
        tratamento = self._tratamento(pk)
        form = DescarteLeiteForm(initial={"data": timezone.localdate()})
        return render(
            request,
            self.template_name,
            {"form": form, "titulo": f"Registrar descarte — {tratamento.animal}"},
        )

    def post(self, request: HttpRequest, pk: object) -> HttpResponse:
        tratamento = self._tratamento(pk)
        form = DescarteLeiteForm(request.POST)
        if form.is_valid():
            try:
                registrar_descarte_leite(tratamento=tratamento, **form.cleaned_data)
            except ValidationError as erro:
                _adicionar_erros(form, erro)
            else:
                messages.success(request, "Descarte de leite registrado.")
                return redirect(request.get_full_path())
        return render(
            request,
            self.template_name,
            {"form": form, "titulo": f"Registrar descarte — {tratamento.animal}"},
            status=422,
        )


class EventoSaudeListView(LoginRequiredMixin, ListView):
    template_name = "saude/evento_list.html"
    context_object_name = "eventos"
    paginate_by = 24

    def get_queryset(self):  # type: ignore[no-untyped-def]
        tipo = self.request.GET.get("tipo", "")
        tipos_validos = {valor for valor, _rotulo in EventoSaude.Tipo.choices}
        return listar_eventos_saude(
            animal_id=self.request.GET.get("animal") or None,
            tipo=tipo if tipo in tipos_validos else None,
            data_inicial=_data_filtro(self.request.GET.get("data_inicial", "")),
            data_final=_data_filtro(self.request.GET.get("data_final", "")),
        )

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        contexto = super().get_context_data(**kwargs)
        contexto["tipos_evento"] = EventoSaude.Tipo.choices
        return contexto


class EventoSaudeDetailView(LoginRequiredMixin, DetailView):
    model = EventoSaude
    template_name = "saude/evento_detail.html"
    context_object_name = "evento"

    def get_queryset(self):  # type: ignore[no-untyped-def]
        return EventoSaude.objects.select_related("animal")


class EventoSaudeFormView(CadastroFormView):
    model = EventoSaude
    form_class = EventoSaudeForm
    titulo = "Registrar evento de saúde"
    sucesso_url = reverse_lazy("saude:eventos")
    campos_iniciais_url = ("animal",)

    def get_object_queryset(self):  # type: ignore[no-untyped-def]
        return EventoSaude.objects.filter(ativo_registro=True)


class EventoSaudeCancelarView(LoginRequiredMixin, View):
    template_name = "shared/confirm.html"

    def _evento(self, pk: object) -> EventoSaude:
        return get_object_or_404(
            EventoSaude.objects.select_related("animal"),
            pk=pk,
            ativo_registro=True,
        )

    def get(self, request: HttpRequest, pk: object) -> HttpResponse:
        evento = self._evento(pk)
        return render(
            request,
            self.template_name,
            {
                "form": CancelamentoForm(),
                "titulo": "Cancelar evento de saúde",
                "mensagem": f"{evento} será mantido no prontuário do animal.",
                "voltar_url": reverse_lazy("saude:evento_detalhe", kwargs={"pk": evento.pk}),
            },
        )

    def post(self, request: HttpRequest, pk: object) -> HttpResponse:
        evento = self._evento(pk)
        form = CancelamentoForm(request.POST)
        if form.is_valid():
            try:
                cancelar_evento_saude(evento=evento, motivo=form.cleaned_data["motivo"])
            except ValidationError as erro:
                _adicionar_erros(form, erro)
            else:
                messages.success(request, "Evento cancelado sem apagar o histórico clínico.")
                return redirect("saude:evento_detalhe", pk=evento.pk)
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "titulo": "Cancelar evento de saúde",
                "mensagem": f"Cancelar {evento}?",
                "voltar_url": reverse_lazy("saude:evento_detalhe", kwargs={"pk": evento.pk}),
            },
            status=422,
        )
