from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.dateparse import parse_date
from django.views import View
from django.views.generic import DetailView, ListView

from .forms import (
    CancelarOrdenhaForm,
    ConciliacaoOrdenhaForm,
    DestinoLeiteForm,
    OrdenhaForm,
    ProducaoAnimalForm,
)
from .models import DestinoLeite, Ordenha, ProducaoAnimal
from .selectors import listar_destinos, listar_ordenhas
from .services import cancelar_ordenha, conciliar_ordenha, vaca_em_carencia


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
    template_name = "leite/lista.html"
    context_object_name = "objetos"
    paginate_by = 24
    titulo = ""
    nome_url_novo = ""
    nome_url_editar = ""
    nome_url_detalhe = ""
    nome_url_cancelar = ""
    mostrar_filtro_datas = False

    def get_template_names(self) -> list[str]:
        if self.request.headers.get("HX-Request") == "true":
            return ["leite/_lista.html"]
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
                "mostrar_filtro_datas": self.mostrar_filtro_datas,
            }
        )
        return contexto


class OrdenhaListView(CadastroListView):
    model = Ordenha
    titulo = "Ordenhas"
    nome_url_novo = "leite:ordenha_nova"
    nome_url_editar = "leite:ordenha_editar"
    nome_url_detalhe = "leite:ordenha_detalhe"
    mostrar_filtro_datas = True

    def get_queryset(self):  # type: ignore[no-untyped-def]
        return listar_ordenhas(
            data_inicial=_data_filtro(self.request.GET.get("data_inicial", "")),
            data_final=_data_filtro(self.request.GET.get("data_final", "")),
        )


class ProducaoListView(CadastroListView):
    model = ProducaoAnimal
    titulo = "Produções individuais"
    nome_url_novo = "leite:producao_nova"
    nome_url_editar = "leite:producao_editar"

    def get_queryset(self):  # type: ignore[no-untyped-def]
        return ProducaoAnimal.objects.select_related("ordenha", "vaca", "lactacao").order_by(
            "-ordenha__data", "vaca__identificacao"
        )


class DestinoListView(CadastroListView):
    model = DestinoLeite
    titulo = "Destinos do leite"
    nome_url_novo = "leite:destino_novo"
    nome_url_editar = "leite:destino_editar"
    mostrar_filtro_datas = True

    def get_queryset(self):  # type: ignore[no-untyped-def]
        return listar_destinos(
            data_inicial=_data_filtro(self.request.GET.get("data_inicial", "")),
            data_final=_data_filtro(self.request.GET.get("data_final", "")),
        )


class OrdenhaDetailView(LoginRequiredMixin, DetailView):
    model = Ordenha
    template_name = "leite/ordenha_detail.html"
    context_object_name = "ordenha"

    def get_queryset(self):  # type: ignore[no-untyped-def]
        return Ordenha.objects.select_related("lote").prefetch_related(
            "producoes__vaca", "producoes__lactacao", "destinos"
        )

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        contexto = super().get_context_data(**kwargs)
        if self.object.modo == Ordenha.Modo.INDIVIDUAL:
            contexto["form_conciliacao"] = ConciliacaoOrdenhaForm()
        return contexto


class OrdenhaConciliarView(LoginRequiredMixin, View):
    template_name = "leite/ordenha_detail.html"

    def post(self, request: HttpRequest, pk: object) -> HttpResponse:
        ordenha = get_object_or_404(
            Ordenha.objects.select_related("lote").prefetch_related(
                "producoes__vaca", "producoes__lactacao", "destinos"
            ),
            pk=pk,
            ativo_registro=True,
            modo=Ordenha.Modo.INDIVIDUAL,
        )
        form = ConciliacaoOrdenhaForm(request.POST)
        if form.is_valid():
            try:
                conciliar_ordenha(
                    ordenha=ordenha,
                )
            except ValidationError as erro:
                _adicionar_erros(form, erro)
            else:
                messages.success(request, "Conciliação individual conferida.")
                return redirect("leite:ordenha_detalhe", pk=ordenha.pk)
        return render(
            request,
            self.template_name,
            {"ordenha": ordenha, "form_conciliacao": form},
            status=422,
        )


class CadastroFormView(LoginRequiredMixin, View):
    template_name = "shared/form.html"
    model = Ordenha
    form_class = OrdenhaForm
    titulo = "Cadastro"
    sucesso_url = reverse_lazy("leite:ordenhas")
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

    def apos_salvar(self, request: HttpRequest, objeto: Any) -> None:
        del request, objeto

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        form = self.form_class(request.POST, request.FILES, instance=self.objeto)
        if form.is_valid():
            try:
                objeto = form.save()
            except ValidationError as erro:
                _adicionar_erros(form, erro)
            else:
                messages.success(request, self.mensagem_sucesso)
                self.apos_salvar(request, objeto)
                return redirect(request.get_full_path())
        return render(
            request, self.template_name, {"form": form, "titulo": self.titulo}, status=422
        )


class OrdenhaFormView(CadastroFormView):
    model = Ordenha
    form_class = OrdenhaForm
    titulo = "Registrar leite"
    sucesso_url = reverse_lazy("leite:ordenhas")
    mensagem_sucesso = "Leite registrado com sucesso."


class ProducaoFormView(CadastroFormView):
    model = ProducaoAnimal
    form_class = ProducaoAnimalForm
    titulo = "Registrar produção individual"
    sucesso_url = reverse_lazy("leite:producoes")
    mensagem_sucesso = "Produção individual salva com sucesso."
    campos_iniciais_url = ("ordenha", "vaca")

    def apos_salvar(self, request: HttpRequest, objeto: ProducaoAnimal) -> None:
        if vaca_em_carencia(vaca=objeto.vaca, ordenha=objeto.ordenha):
            messages.warning(
                request,
                "Atenção: esta vaca está em carência. Separe e registre o descarte do leite.",
            )


class DestinoFormView(CadastroFormView):
    model = DestinoLeite
    form_class = DestinoLeiteForm
    titulo = "Registrar destino do leite"
    sucesso_url = reverse_lazy("leite:destinos")
    mensagem_sucesso = "Destino salvo com sucesso."
    campos_iniciais_url = ("ordenha",)


class OrdenhaCancelarView(LoginRequiredMixin, View):
    template_name = "shared/confirm.html"

    def _ordenha(self, pk: object) -> Ordenha:
        return get_object_or_404(Ordenha, pk=pk, ativo_registro=True)

    def get(self, request: HttpRequest, pk: object) -> HttpResponse:
        ordenha = self._ordenha(pk)
        return render(
            request,
            self.template_name,
            {
                "form": CancelarOrdenhaForm(),
                "titulo": "Cancelar ordenha",
                "mensagem": f"A ordenha {ordenha} será mantida no histórico.",
            },
        )

    def post(self, request: HttpRequest, pk: object) -> HttpResponse:
        ordenha = self._ordenha(pk)
        form = CancelarOrdenhaForm(request.POST)
        if form.is_valid():
            try:
                cancelar_ordenha(ordenha=ordenha)
            except ValidationError as erro:
                _adicionar_erros(form, erro)
            else:
                messages.success(request, "Ordenha cancelada sem apagar o histórico.")
                return redirect("leite:ordenhas")
        return render(
            request,
            self.template_name,
            {"form": form, "titulo": "Cancelar ordenha", "mensagem": f"Cancelar {ordenha}?"},
            status=422,
        )
