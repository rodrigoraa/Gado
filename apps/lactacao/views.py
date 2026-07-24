from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, ListView

from apps.reproducao.models import Parto

from .forms import CancelarLactacaoForm, DataObservacaoForm, LactacaoForm
from .models import Lactacao
from .selectors import (
    comparar_lactacoes,
    indicadores_lactacao,
    listar_lactacoes,
    obter_lactacao,
)
from .services import (
    cancelar_lactacao,
    encerrar_lactacao,
    iniciar_lactacao,
    secar_lactacao,
)


def _erros_servico(form, erro: ValidationError) -> None:  # type: ignore[no-untyped-def]
    if hasattr(erro, "message_dict"):
        for campo, mensagens_erro in erro.message_dict.items():
            destino = campo if campo in form.fields else None
            for mensagem in mensagens_erro:
                form.add_error(destino, mensagem)
    else:
        for mensagem in erro.messages:
            form.add_error(None, mensagem)


class LactacaoListView(LoginRequiredMixin, ListView):
    template_name = "lactacao/lactacao_list.html"
    context_object_name = "lactacoes"
    paginate_by = 24

    def get_queryset(self):  # type: ignore[no-untyped-def]
        return listar_lactacoes(
            situacao=self.request.GET.get("situacao", ""),
            busca=self.request.GET.get("q", ""),
        )

    def get_context_data(self, **kwargs):  # type: ignore[no-untyped-def]
        contexto = super().get_context_data(**kwargs)
        contexto["situacoes"] = Lactacao.Situacao.choices
        contexto["filtros"] = self.request.GET
        return contexto


class LactacaoDetailView(LoginRequiredMixin, DetailView):
    template_name = "lactacao/lactacao_detail.html"
    context_object_name = "lactacao"
    pk_url_kwarg = "lactacao_id"

    def get_object(self, queryset=None):  # type: ignore[no-untyped-def]
        return obter_lactacao(lactacao_id=str(self.kwargs["lactacao_id"]))

    def get_context_data(self, **kwargs):  # type: ignore[no-untyped-def]
        contexto = super().get_context_data(**kwargs)
        contexto["indicadores"] = indicadores_lactacao(lactacao=self.object)
        contexto["comparacao"] = comparar_lactacoes(vaca=self.object.vaca)
        return contexto


class LactacaoCreateView(LoginRequiredMixin, View):
    template_name = "lactacao/form.html"

    def _parto(self, parto_id: str | None) -> Parto | None:
        return get_object_or_404(Parto, pk=parto_id) if parto_id else None

    def get(self, request: HttpRequest, parto_id: str | None = None) -> HttpResponse:
        parto = self._parto(parto_id)
        initial = {"data_inicio": timezone.localdate(), "parto": parto}
        if parto:
            initial["vaca"] = parto.vaca
            initial["data_inicio"] = timezone.localtime(parto.data_hora).date()
        form = LactacaoForm(parto=parto, initial=initial)
        return render(request, self.template_name, {"form": form, "titulo": "Iniciar lactação"})

    def post(self, request: HttpRequest, parto_id: str | None = None) -> HttpResponse:
        parto_url = self._parto(parto_id)
        form = LactacaoForm(request.POST, parto=parto_url)
        if form.is_valid():
            try:
                iniciar_lactacao(
                    vaca=form.cleaned_data["vaca"],
                    parto=form.cleaned_data["parto"],
                    data_inicio=form.cleaned_data["data_inicio"],
                    observacoes=form.cleaned_data["observacoes"],
                )
            except ValidationError as erro:
                _erros_servico(form, erro)
            else:
                messages.success(request, "Lactação iniciada.")
                return redirect(request.get_full_path())
        return render(
            request,
            self.template_name,
            {"form": form, "titulo": "Iniciar lactação"},
            status=422,
        )


class AcaoLactacaoView(LoginRequiredMixin, View):
    template_name = "lactacao/form.html"
    acao = ""

    def get_lactacao(self, lactacao_id: str) -> Lactacao:
        return get_object_or_404(Lactacao, pk=lactacao_id)

    def get(self, request: HttpRequest, lactacao_id: str) -> HttpResponse:
        form = DataObservacaoForm(initial={"data": timezone.localdate()})
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "titulo": ("Secar lactação" if self.acao == "secar" else "Encerrar lactação"),
            },
        )

    def post(self, request: HttpRequest, lactacao_id: str) -> HttpResponse:
        lactacao = self.get_lactacao(lactacao_id)
        form = DataObservacaoForm(request.POST)
        if form.is_valid():
            try:
                if self.acao == "secar":
                    secar_lactacao(
                        lactacao=lactacao,
                        data_secagem=form.cleaned_data["data"],
                        observacoes=form.cleaned_data["observacoes"],
                    )
                    mensagem = "Secagem registrada."
                else:
                    encerrar_lactacao(
                        lactacao=lactacao,
                        data_encerramento=form.cleaned_data["data"],
                        observacoes=form.cleaned_data["observacoes"],
                    )
                    mensagem = "Lactação encerrada."
            except ValidationError as erro:
                _erros_servico(form, erro)
            else:
                messages.success(request, mensagem)
                return redirect("lactacao:detalhe", lactacao_id=lactacao.pk)
        return render(
            request,
            self.template_name,
            {"form": form, "titulo": "Atualizar lactação"},
            status=422,
        )


class LactacaoSecarView(AcaoLactacaoView):
    acao = "secar"


class LactacaoEncerrarView(AcaoLactacaoView):
    acao = "encerrar"


class LactacaoCancelarView(LoginRequiredMixin, View):
    template_name = "lactacao/form.html"

    def get(self, request: HttpRequest, lactacao_id: str) -> HttpResponse:
        return render(
            request,
            self.template_name,
            {"form": CancelarLactacaoForm(), "titulo": "Cancelar lactação"},
        )

    def post(self, request: HttpRequest, lactacao_id: str) -> HttpResponse:
        lactacao = get_object_or_404(Lactacao, pk=lactacao_id)
        form = CancelarLactacaoForm(request.POST)
        if form.is_valid():
            try:
                cancelar_lactacao(
                    lactacao=lactacao,
                    justificativa=form.cleaned_data["justificativa"],
                )
            except ValidationError as erro:
                _erros_servico(form, erro)
            else:
                messages.success(request, "Lactação cancelada sem exclusão física.")
                return redirect("lactacao:detalhe", lactacao_id=lactacao.pk)
        return render(
            request,
            self.template_name,
            {"form": form, "titulo": "Cancelar lactação"},
            status=422,
        )
