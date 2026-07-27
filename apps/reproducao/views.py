from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, ListView

from .forms import (
    AlterarDataCoberturaForm,
    BezerroFormSet,
    CoberturaForm,
    CorrecaoPartoForm,
    DiagnosticoGestacaoForm,
    JustificativaForm,
    PartoForm,
    PerdaGestacionalForm,
)
from .models import Cobertura, Parto
from .selectors import (
    listar_coberturas,
    listar_coberturas_por_touro,
    listar_partos,
    obter_cobertura,
    obter_parto,
)
from .services import (
    TRATAMENTO_SUBSTITUIR,
    alterar_data_cobertura,
    cancelar_cobertura,
    cancelar_parto,
    corrigir_parto,
    registrar_cobertura,
    registrar_diagnostico,
    registrar_parto,
    registrar_perda_gestacional,
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


class CoberturaListView(LoginRequiredMixin, ListView):
    template_name = "reproducao/cobertura_list.html"
    context_object_name = "coberturas"
    paginate_by = 24

    def get_template_names(self) -> list[str]:
        if self.request.headers.get("HX-Request") == "true":
            return ["reproducao/partials/cobertura_cards.html"]
        return [self.template_name]

    def get_queryset(self):  # type: ignore[no-untyped-def]
        return listar_coberturas(
            busca=self.request.GET.get("q", ""),
            situacao=self.request.GET.get("situacao", ""),
        )

    def get_context_data(self, **kwargs):  # type: ignore[no-untyped-def]
        contexto = super().get_context_data(**kwargs)
        contexto["situacoes"] = Cobertura.Situacao.choices
        contexto["filtros"] = self.request.GET
        return contexto


class CoberturaPorTouroListView(LoginRequiredMixin, ListView):
    template_name = "reproducao/cobertura_por_touro_list.html"
    context_object_name = "coberturas"
    paginate_by = 30

    def get_queryset(self):  # type: ignore[no-untyped-def]
        return listar_coberturas_por_touro(busca=self.request.GET.get("q", ""))

    def get_context_data(self, **kwargs):  # type: ignore[no-untyped-def]
        contexto = super().get_context_data(**kwargs)
        contexto["filtros"] = self.request.GET
        return contexto


class CoberturaDetailView(LoginRequiredMixin, DetailView):
    template_name = "reproducao/cobertura_detail.html"
    context_object_name = "cobertura"
    pk_url_kwarg = "cobertura_id"

    def get_object(self, queryset=None):  # type: ignore[no-untyped-def]
        return obter_cobertura(cobertura_id=str(self.kwargs["cobertura_id"]))

    def get_context_data(self, **kwargs):  # type: ignore[no-untyped-def]
        contexto = super().get_context_data(**kwargs)
        contexto["parto_ativo"] = next(
            (
                parto
                for parto in self.object.partos.all()
                if parto.situacao != Parto.Situacao.CANCELADO
            ),
            None,
        )
        return contexto


class CoberturaCreateView(LoginRequiredMixin, View):
    template_name = "reproducao/form.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        form = CoberturaForm(
            initial={
                "data": timezone.localdate(),
                "vaca": request.GET.get("vaca", ""),
            }
        )
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "titulo": "Registrar cobertura",
                "subtitulo": (
                    "Informe a vaca, o boi e a data. O possível nascimento será calculado."
                ),
            },
        )

    def post(self, request: HttpRequest) -> HttpResponse:
        form = CoberturaForm(request.POST)
        if form.is_valid():
            try:
                registrar_cobertura(
                    vaca=form.cleaned_data["vaca"],
                    touro=form.cleaned_data["touro"],
                    data_cobertura=form.cleaned_data["data"],
                    tipo=Cobertura.Tipo.MONTA_NATURAL,
                    forma_identificacao=Cobertura.FormaIdentificacao.OBSERVADA,
                    tratamento_cobertura_aberta=TRATAMENTO_SUBSTITUIR,
                )
            except ValidationError as erro:
                _erros_servico(form, erro)
            else:
                messages.success(request, "Cobertura registrada com previsão calculada.")
                return redirect(request.get_full_path())
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "titulo": "Registrar cobertura",
                "subtitulo": "Informe a vaca, o boi e a data.",
            },
            status=422,
        )


class AcaoCoberturaView(LoginRequiredMixin, View):
    template_name = "reproducao/form.html"
    acao = ""

    def get_cobertura(self, cobertura_id: str) -> Cobertura:
        return get_object_or_404(Cobertura, pk=cobertura_id)

    def get(self, request: HttpRequest, cobertura_id: str) -> HttpResponse:
        cobertura = self.get_cobertura(cobertura_id)
        if self.acao == "data":
            form = AlterarDataCoberturaForm(initial={"nova_data": cobertura.data})
            titulo = "Corrigir data da cobertura"
        else:
            form = JustificativaForm()
            titulo = "Cancelar cobertura"
        return render(request, self.template_name, {"form": form, "titulo": titulo})

    def post(self, request: HttpRequest, cobertura_id: str) -> HttpResponse:
        cobertura = self.get_cobertura(cobertura_id)
        form = (
            AlterarDataCoberturaForm(request.POST)
            if self.acao == "data"
            else JustificativaForm(request.POST)
        )
        if form.is_valid():
            try:
                if self.acao == "data":
                    alterar_data_cobertura(
                        cobertura=cobertura,
                        nova_data=form.cleaned_data["nova_data"],
                    )
                    mensagem = "Data corrigida e histórico preservado."
                else:
                    cancelar_cobertura(
                        cobertura=cobertura,
                    )
                    mensagem = "Cobertura cancelada sem exclusão do histórico."
            except ValidationError as erro:
                _erros_servico(form, erro)
            else:
                messages.success(request, mensagem)
                return redirect("reproducao:cobertura_detalhe", cobertura_id=cobertura.pk)
        return render(
            request,
            self.template_name,
            {"form": form, "titulo": "Alterar cobertura"},
            status=422,
        )


class CoberturaAlterarDataView(AcaoCoberturaView):
    acao = "data"


class CoberturaCancelarView(AcaoCoberturaView):
    acao = "cancelar"


class DiagnosticoCreateView(LoginRequiredMixin, View):
    template_name = "reproducao/form.html"

    def _cobertura(self, cobertura_id: str | None) -> Cobertura | None:
        return get_object_or_404(Cobertura, pk=cobertura_id) if cobertura_id else None

    def get(self, request: HttpRequest, cobertura_id: str | None = None) -> HttpResponse:
        cobertura = self._cobertura(cobertura_id)
        form = DiagnosticoGestacaoForm(
            cobertura=cobertura,
            initial={"cobertura": cobertura, "data": timezone.localdate()},
        )
        return render(
            request, self.template_name, {"form": form, "titulo": "Diagnóstico de gestação"}
        )

    def post(self, request: HttpRequest, cobertura_id: str | None = None) -> HttpResponse:
        cobertura_url = self._cobertura(cobertura_id)
        form = DiagnosticoGestacaoForm(request.POST, cobertura=cobertura_url)
        if form.is_valid():
            try:
                registrar_diagnostico(
                    cobertura=form.cleaned_data["cobertura"],
                    data_diagnostico=form.cleaned_data["data"],
                    resultado=form.cleaned_data["resultado"],
                    metodo=form.cleaned_data["metodo"],
                    responsavel=form.cleaned_data["responsavel"],
                    idade_gestacional_estimada_dias=form.cleaned_data[
                        "idade_gestacional_estimada_dias"
                    ],
                    nova_previsao_parto=form.cleaned_data["nova_previsao_parto"],
                    observacoes=form.cleaned_data["observacoes"],
                )
            except ValidationError as erro:
                _erros_servico(form, erro)
            else:
                messages.success(request, "Diagnóstico registrado e situação atualizada.")
                return redirect(request.get_full_path())
        return render(
            request,
            self.template_name,
            {"form": form, "titulo": "Diagnóstico de gestação"},
            status=422,
        )


class PerdaCreateView(LoginRequiredMixin, View):
    template_name = "reproducao/form.html"

    def _cobertura(self, cobertura_id: str | None) -> Cobertura | None:
        return get_object_or_404(Cobertura, pk=cobertura_id) if cobertura_id else None

    def get(self, request: HttpRequest, cobertura_id: str | None = None) -> HttpResponse:
        cobertura = self._cobertura(cobertura_id)
        form = PerdaGestacionalForm(
            cobertura=cobertura,
            initial={"cobertura": cobertura, "data": timezone.localdate()},
        )
        return render(
            request, self.template_name, {"form": form, "titulo": "Registrar perda gestacional"}
        )

    def post(self, request: HttpRequest, cobertura_id: str | None = None) -> HttpResponse:
        cobertura_url = self._cobertura(cobertura_id)
        form = PerdaGestacionalForm(request.POST, cobertura=cobertura_url)
        if form.is_valid():
            try:
                registrar_perda_gestacional(
                    cobertura=form.cleaned_data["cobertura"],
                    data_perda=form.cleaned_data["data"],
                    tipo=form.cleaned_data["tipo"],
                    responsavel=form.cleaned_data["responsavel"],
                    observacoes=form.cleaned_data["observacoes"],
                )
            except ValidationError as erro:
                _erros_servico(form, erro)
            else:
                messages.success(request, "Ocorrência gestacional registrada.")
                return redirect(request.get_full_path())
        return render(
            request,
            self.template_name,
            {"form": form, "titulo": "Registrar perda gestacional"},
            status=422,
        )


class PartoListView(LoginRequiredMixin, ListView):
    template_name = "reproducao/parto_list.html"
    context_object_name = "partos"
    paginate_by = 24

    def get_queryset(self):  # type: ignore[no-untyped-def]
        return listar_partos()


class PartoDetailView(LoginRequiredMixin, DetailView):
    template_name = "reproducao/parto_detail.html"
    context_object_name = "parto"
    pk_url_kwarg = "parto_id"

    def get_object(self, queryset=None):  # type: ignore[no-untyped-def]
        return obter_parto(parto_id=str(self.kwargs["parto_id"]))


class PartoCreateView(LoginRequiredMixin, View):
    template_name = "reproducao/parto_form.html"

    def _cobertura(self, cobertura_id: str | None) -> Cobertura | None:
        return get_object_or_404(Cobertura, pk=cobertura_id) if cobertura_id else None

    def _contexto(self, *, form, formset, cobertura: Cobertura | None):  # type: ignore[no-untyped-def]
        return {
            "form": form,
            "formset": formset,
            "cobertura_origem": cobertura,
            "titulo": "Confirmar nascimento" if cobertura else "Registrar parto",
        }

    def get(self, request: HttpRequest, cobertura_id: str | None = None) -> HttpResponse:
        cobertura = self._cobertura(cobertura_id)
        form = PartoForm(
            cobertura=cobertura,
            initial={"data_hora": timezone.localtime().strftime("%Y-%m-%dT%H:%M")},
        )
        formset = BezerroFormSet(prefix="bezerros")
        return render(
            request,
            self.template_name,
            self._contexto(form=form, formset=formset, cobertura=cobertura),
        )

    def post(self, request: HttpRequest, cobertura_id: str | None = None) -> HttpResponse:
        cobertura_url = self._cobertura(cobertura_id)
        form = PartoForm(request.POST, cobertura=cobertura_url)
        formset = BezerroFormSet(request.POST, request.FILES, prefix="bezerros")
        if form.is_valid() and formset.is_valid():
            bezerros = [
                dados
                for formulario in formset.forms
                if (dados := formulario.cleaned_data)
                and not dados.get("DELETE")
                and dados.get("nome")
            ]
            for dados in bezerros:
                dados.pop("DELETE", None)
            try:
                parto = registrar_parto(
                    vaca=form.cleaned_data["vaca"],
                    cobertura=form.cleaned_data["cobertura"],
                    data_hora=form.cleaned_data["data_hora"],
                    resultado=form.cleaned_data["resultado"],
                    bezerros=bezerros,
                    necessitou_auxilio=form.cleaned_data["necessitou_auxilio"],
                    responsavel=form.cleaned_data["responsavel"],
                    observacoes=form.cleaned_data["observacoes"],
                )
            except ValidationError as erro:
                _erros_servico(form, erro)
            else:
                messages.success(request, "Parto e nascimentos registrados em conjunto.")
                if cobertura_url:
                    return redirect("reproducao:parto_detalhe", parto_id=parto.pk)
                return redirect(request.get_full_path())
        return render(
            request,
            self.template_name,
            self._contexto(form=form, formset=formset, cobertura=cobertura_url),
            status=422,
        )


class PartoCorrigirView(LoginRequiredMixin, View):
    template_name = "reproducao/form.html"

    def get_parto(self, parto_id: str) -> Parto:
        return get_object_or_404(Parto, pk=parto_id)

    def get(self, request: HttpRequest, parto_id: str) -> HttpResponse:
        form = CorrecaoPartoForm(instance=self.get_parto(parto_id))
        return render(request, self.template_name, {"form": form, "titulo": "Corrigir parto"})

    def post(self, request: HttpRequest, parto_id: str) -> HttpResponse:
        parto = self.get_parto(parto_id)
        form = CorrecaoPartoForm(request.POST, instance=parto)
        if form.is_valid():
            try:
                corrigido = corrigir_parto(
                    parto=parto,
                    **{campo: form.cleaned_data[campo] for campo in CorrecaoPartoForm._meta.fields},
                )
            except ValidationError as erro:
                _erros_servico(form, erro)
            else:
                messages.success(request, "Parto corrigido; versão anterior preservada.")
                return redirect("reproducao:parto_detalhe", parto_id=corrigido.pk)
        return render(
            request,
            self.template_name,
            {"form": form, "titulo": "Corrigir parto"},
            status=422,
        )


class PartoCancelarView(LoginRequiredMixin, View):
    template_name = "reproducao/form.html"

    def get(self, request: HttpRequest, parto_id: str) -> HttpResponse:
        return render(
            request,
            self.template_name,
            {"form": JustificativaForm(), "titulo": "Cancelar parto"},
        )

    def post(self, request: HttpRequest, parto_id: str) -> HttpResponse:
        parto = get_object_or_404(Parto, pk=parto_id)
        form = JustificativaForm(request.POST)
        if form.is_valid():
            try:
                cancelar_parto(parto=parto)
            except ValidationError as erro:
                _erros_servico(form, erro)
            else:
                messages.success(request, "Parto cancelado sem exclusão física.")
                return redirect("reproducao:parto_detalhe", parto_id=parto.pk)
        return render(
            request,
            self.template_name,
            {"form": form, "titulo": "Cancelar parto"},
            status=422,
        )
