from __future__ import annotations

from typing import Any

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, ListView

from .forms import (
    AnimalForm,
    CadastroBezerroForm,
    CadastroNovilhaForm,
    InativacaoAnimalForm,
    LoteForm,
    MovimentacaoLoteForm,
    PesagemForm,
    RacaForm,
)
from .models import Animal, Lote, Raca
from .selectors import listar_animais, obter_animal, resumo_rebanho
from .services import (
    excluir_animal,
    inativar_animal,
    movimentar_animal,
    registrar_pesagem,
    salvar_animal,
    salvar_lote,
    salvar_raca,
)


def _adicionar_erro_servico(form, erro: ValidationError) -> None:  # type: ignore[no-untyped-def]
    if hasattr(erro, "message_dict"):
        for campo, mensagens_erro in erro.message_dict.items():
            destino = campo if campo in form.fields else None
            for mensagem in mensagens_erro:
                form.add_error(destino, mensagem)
    else:
        for mensagem in erro.messages:
            form.add_error(None, mensagem)


def _dados_model_form(form, *, excluir: set[str] | None = None) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    excluir = excluir or set()
    return {
        campo: form.cleaned_data[campo]
        for campo in form._meta.fields
        if campo not in excluir and campo in form.cleaned_data
    }


class AnimalListView(LoginRequiredMixin, ListView):
    model = Animal
    template_name = "rebanho/animal_list.html"
    context_object_name = "animais"
    paginate_by = 24

    def get_template_names(self) -> list[str]:
        if self.request.headers.get("HX-Request") == "true":
            return ["rebanho/partials/animal_cards.html"]
        return [self.template_name]

    def get_queryset(self):  # type: ignore[no-untyped-def]
        return listar_animais(
            busca=self.request.GET.get("q", ""),
            sexo=self.request.GET.get("sexo", ""),
            tipo_animal=self.request.GET.get("tipo_animal", ""),
        )

    def get_context_data(self, **kwargs):  # type: ignore[no-untyped-def]
        contexto = super().get_context_data(**kwargs)
        contexto.update(
            {
                "resumo": resumo_rebanho(),
                "sexos": Animal.Sexo.choices,
                "filtros": self.request.GET,
            }
        )
        return contexto


class AnimalDetailView(LoginRequiredMixin, DetailView):
    model = Animal
    template_name = "rebanho/animal_detail.html"
    context_object_name = "animal"
    pk_url_kwarg = "animal_id"

    def get_object(self, queryset=None):  # type: ignore[no-untyped-def]
        return obter_animal(animal_id=str(self.kwargs["animal_id"]))

    def get_context_data(self, **kwargs):  # type: ignore[no-untyped-def]
        contexto = super().get_context_data(**kwargs)
        contexto.update(
            {
                "filhos": self.object.filhos,
                "coberturas": self.object.coberturas.exclude(situacao="CANCELADA")
                .select_related("touro")
                .order_by("-data"),
                "coberturas_como_touro": self.object.coberturas_como_touro.exclude(
                    situacao="CANCELADA"
                )
                .select_related("vaca")
                .order_by("-data"),
            }
        )
        return contexto


class AnimalFormView(LoginRequiredMixin, View):
    template_name = "rebanho/form.html"
    animal: Animal | None = None
    bezerro = False
    novilha = False

    def dispatch(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        self.bezerro = bool(kwargs.get("bezerro"))
        self.novilha = bool(kwargs.get("novilha"))
        if "animal_id" in kwargs:
            self.animal = get_object_or_404(Animal, pk=kwargs["animal_id"])
        return super().dispatch(request, *args, **kwargs)

    def _form_class(self):  # type: ignore[no-untyped-def]
        if self.bezerro:
            return CadastroBezerroForm
        if self.novilha:
            return CadastroNovilhaForm
        return AnimalForm

    def _contexto(self, form: AnimalForm) -> dict[str, object]:
        if self.animal:
            titulo = f"Editar {self.animal.nome or 'animal'}"
            descricao = "Altere somente os dados necessários."
        elif self.bezerro:
            titulo = "Cadastrar bezerro"
            descricao = (
                "Informe nome e sexo. Cor e mãe são opcionais. "
                "O nascimento será registrado como hoje."
            )
        elif self.novilha:
            titulo = "Cadastrar novilha"
            descricao = (
                "Informe o nome. A data de nascimento é opcional e o sexo será registrado "
                "como fêmea."
            )
        else:
            titulo = "Cadastrar animal"
            descricao = "Informe nome, sexo e tipo de animal. A cor é opcional."
        return {
            "form": form,
            "animal": self.animal,
            "titulo": titulo,
            "descricao": descricao,
            "cadastro_bezerro": self.bezerro,
            "cadastro_novilha": self.novilha,
        }

    def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        initial = {}
        if self.bezerro and request.GET.get("mae"):
            initial["mae"] = get_object_or_404(
                Animal,
                pk=request.GET["mae"],
                sexo=Animal.Sexo.FEMEA,
                situacao=Animal.Situacao.ATIVO,
            )
        form = self._form_class()(instance=self.animal, initial=initial)
        return render(request, self.template_name, self._contexto(form))

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        form = self._form_class()(request.POST, request.FILES, instance=self.animal)
        if form.is_valid():
            dados = _dados_model_form(form)
            if self.bezerro and self.animal is None:
                hoje = timezone.localdate()
                dados.update(
                    {
                        "data_nascimento": hoje,
                        "data_entrada": hoje,
                        "origem": Animal.Origem.NASCIDO_SITIO,
                    }
                )
            elif self.novilha and self.animal is None:
                dados["sexo"] = Animal.Sexo.FEMEA
            try:
                salvar_animal(
                    animal=self.animal,
                    justificativa_correcao=(
                        "Sexo atualizado pelo cadastro simplificado." if self.animal else ""
                    ),
                    **dados,
                )
            except ValidationError as erro:
                _adicionar_erro_servico(form, erro)
            else:
                messages.success(request, "Animal salvo com sucesso.")
                return redirect(request.get_full_path())
        return render(
            request,
            self.template_name,
            self._contexto(form),
            status=422,
        )


class AnimalInativarView(LoginRequiredMixin, View):
    template_name = "rebanho/form.html"

    def _animal(self, animal_id: str) -> Animal:
        return get_object_or_404(Animal, pk=animal_id)

    def get(self, request: HttpRequest, animal_id: str) -> HttpResponse:
        animal = self._animal(animal_id)
        form = InativacaoAnimalForm(initial={"data_saida": timezone.localdate()})
        return render(
            request,
            self.template_name,
            {"form": form, "titulo": f"Registrar saída de {animal}"},
        )

    def post(self, request: HttpRequest, animal_id: str) -> HttpResponse:
        animal = self._animal(animal_id)
        form = InativacaoAnimalForm(request.POST)
        if form.is_valid():
            try:
                inativar_animal(
                    animal=animal,
                    situacao=form.cleaned_data["situacao"],
                    motivo=form.cleaned_data["motivo"],
                    data_saida=form.cleaned_data["data_saida"],
                )
            except ValidationError as erro:
                _adicionar_erro_servico(form, erro)
            else:
                messages.success(request, "Saída registrada sem apagar o histórico.")
                return redirect("rebanho:animal_detalhe", animal_id=animal.pk)
        return render(
            request,
            self.template_name,
            {"form": form, "titulo": f"Registrar saída de {animal}"},
            status=422,
        )


class AnimalExcluirView(LoginRequiredMixin, View):
    template_name = "shared/confirm.html"

    def _animal(self, animal_id: str) -> Animal:
        return get_object_or_404(Animal, pk=animal_id)

    def get(self, request: HttpRequest, animal_id: str) -> HttpResponse:
        animal = self._animal(animal_id)
        quantidade_bezerros = animal.filhos_como_mae.count()
        quantidade_coberturas = animal.coberturas.count()
        mensagem = f"Tem certeza que deseja excluir {animal}?"
        if quantidade_bezerros == 1:
            mensagem += " 1 bezerro continuará cadastrado, mas sem mãe vinculada."
        elif quantidade_bezerros > 1:
            mensagem += (
                f" {quantidade_bezerros} bezerros continuarão cadastrados, mas sem mãe vinculada."
            )
        if quantidade_coberturas == 1:
            mensagem += " 1 cobertura desta vaca também será excluída."
        elif quantidade_coberturas > 1:
            mensagem += f" {quantidade_coberturas} coberturas desta vaca também serão excluídas."
        return render(
            request,
            self.template_name,
            {
                "titulo": f"Excluir {animal}",
                "mensagem": mensagem,
                "voltar_url": reverse(
                    "rebanho:animal_detalhe",
                    kwargs={"animal_id": animal.pk},
                ),
            },
        )

    def post(self, request: HttpRequest, animal_id: str) -> HttpResponse:
        animal = self._animal(animal_id)
        nome = str(animal)
        try:
            quantidade_bezerros = excluir_animal(animal=animal)
        except ValidationError as erro:
            messages.error(request, erro.messages[0])
            return redirect("rebanho:animal_detalhe", animal_id=animal.pk)

        mensagem = f"{nome} foi excluído."
        if quantidade_bezerros == 1:
            mensagem += " 1 bezerro continua cadastrado, sem mãe vinculada."
        elif quantidade_bezerros > 1:
            mensagem += f" {quantidade_bezerros} bezerros continuam cadastrados, sem mãe vinculada."
        messages.success(request, mensagem)
        return redirect("rebanho:animais")


class MovimentacaoCreateView(LoginRequiredMixin, View):
    template_name = "rebanho/form.html"

    def _animal(self, request: HttpRequest) -> Animal | None:
        animal_id = request.GET.get("animal") or request.POST.get("animal")
        return get_object_or_404(Animal, pk=animal_id) if animal_id else None

    def get(self, request: HttpRequest) -> HttpResponse:
        animal = self._animal(request)
        form = MovimentacaoLoteForm(
            animal=animal, initial={"animal": animal, "data": timezone.localdate()}
        )
        return render(request, self.template_name, {"form": form, "titulo": "Mudar lote"})

    def post(self, request: HttpRequest) -> HttpResponse:
        animal = self._animal(request)
        form = MovimentacaoLoteForm(request.POST, animal=animal)
        if form.is_valid():
            try:
                movimentar_animal(
                    animal=form.cleaned_data["animal"],
                    novo_lote=form.cleaned_data["novo_lote"],
                    data_movimentacao=form.cleaned_data["data"],
                    motivo=form.cleaned_data["motivo"],
                    observacoes=form.cleaned_data["observacoes"],
                )
            except ValidationError as erro:
                _adicionar_erro_servico(form, erro)
            else:
                messages.success(request, "Mudança de lote registrada.")
                return redirect(request.get_full_path())
        return render(
            request,
            self.template_name,
            {"form": form, "titulo": "Mudar lote"},
            status=422,
        )


class PesagemCreateView(LoginRequiredMixin, View):
    template_name = "rebanho/form.html"

    def _animal(self, request: HttpRequest) -> Animal | None:
        animal_id = request.GET.get("animal") or request.POST.get("animal")
        return get_object_or_404(Animal, pk=animal_id) if animal_id else None

    def get(self, request: HttpRequest) -> HttpResponse:
        animal = self._animal(request)
        form = PesagemForm(animal=animal, initial={"animal": animal, "data": timezone.localdate()})
        return render(request, self.template_name, {"form": form, "titulo": "Registrar pesagem"})

    def post(self, request: HttpRequest) -> HttpResponse:
        animal = self._animal(request)
        form = PesagemForm(request.POST, animal=animal)
        if form.is_valid():
            try:
                registrar_pesagem(
                    animal=form.cleaned_data["animal"],
                    data_pesagem=form.cleaned_data["data"],
                    peso_kg=form.cleaned_data["peso_kg"],
                    responsavel=form.cleaned_data["responsavel"],
                    observacoes=form.cleaned_data["observacoes"],
                )
            except ValidationError as erro:
                _adicionar_erro_servico(form, erro)
            else:
                messages.success(request, "Pesagem registrada.")
                return redirect(request.get_full_path())
        return render(
            request,
            self.template_name,
            {"form": form, "titulo": "Registrar pesagem"},
            status=422,
        )


class CadastroSimplesListView(LoginRequiredMixin, ListView):
    template_name = "rebanho/cadastro_list.html"
    context_object_name = "objetos"
    paginate_by = 30
    titulo = ""
    nome_url_novo = ""
    nome_url_editar = ""

    def get_context_data(self, **kwargs):  # type: ignore[no-untyped-def]
        contexto = super().get_context_data(**kwargs)
        contexto.update(
            {
                "titulo": self.titulo,
                "nome_url_novo": self.nome_url_novo,
                "nome_url_editar": self.nome_url_editar,
            }
        )
        return contexto


class RacaListView(CadastroSimplesListView):
    model = Raca
    titulo = "Raças"
    nome_url_novo = "rebanho:raca_nova"
    nome_url_editar = "rebanho:raca_editar"


class LoteListView(CadastroSimplesListView):
    model = Lote
    titulo = "Lotes e pastos"
    nome_url_novo = "rebanho:lote_novo"
    nome_url_editar = "rebanho:lote_editar"


class CadastroSimplesFormView(LoginRequiredMixin, View):
    template_name = "rebanho/form.html"
    model = Raca
    form_class = RacaForm
    titulo = ""
    url_sucesso = ""
    service = staticmethod(salvar_raca)
    objeto = None

    def dispatch(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        if object_id := kwargs.get("object_id"):
            self.objeto = get_object_or_404(self.model, pk=object_id)
        return super().dispatch(request, *args, **kwargs)

    def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        return render(
            request,
            self.template_name,
            {"form": self.form_class(instance=self.objeto), "titulo": self.titulo},
        )

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        form = self.form_class(request.POST, instance=self.objeto)
        if form.is_valid():
            argumento = self.model._meta.model_name
            try:
                self.service(**{argumento: self.objeto}, **_dados_model_form(form))
            except ValidationError as erro:
                _adicionar_erro_servico(form, erro)
            else:
                messages.success(request, "Cadastro salvo com sucesso.")
                return redirect(request.get_full_path())
        return render(
            request,
            self.template_name,
            {"form": form, "titulo": self.titulo},
            status=422,
        )


class RacaFormView(CadastroSimplesFormView):
    model = Raca
    form_class = RacaForm
    titulo = "Raça"
    url_sucesso = "rebanho:racas"
    service = staticmethod(salvar_raca)


class LoteFormView(CadastroSimplesFormView):
    model = Lote
    form_class = LoteForm
    titulo = "Lote/pasto"
    url_sucesso = "rebanho:lotes"
    service = staticmethod(salvar_lote)
