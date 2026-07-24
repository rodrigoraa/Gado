from datetime import date

from django.db import migrations, models


def preencher_tipos_existentes(apps, schema_editor):  # type: ignore[no-untyped-def]
    Animal = apps.get_model("rebanho", "Animal")
    Parto = apps.get_model("reproducao", "Parto")
    hoje = date.today()
    animais = list(Animal.objects.all())

    for animal in animais:
        nascimento = animal.data_nascimento
        idade_meses = None
        if nascimento:
            idade_meses = (hoje.year - nascimento.year) * 12
            idade_meses += hoje.month - nascimento.month
            if hoje.day < nascimento.day:
                idade_meses -= 1

        if idade_meses is not None and idade_meses < 12:
            animal.tipo_animal = "BEZERRO"
        elif animal.sexo == "M":
            animal.tipo_animal = "BOI"
        elif animal.sexo == "F":
            tem_parto = (
                Parto.objects.filter(vaca_id=animal.pk)
                .exclude(situacao="CANCELADO")
                .exists()
            )
            animal.tipo_animal = "VACA" if tem_parto else "NOVILHA"
        else:
            animal.tipo_animal = "BEZERRO"

    if animais:
        Animal.objects.bulk_update(animais, ["tipo_animal"])


class Migration(migrations.Migration):
    dependencies = [
        ("rebanho", "0003_simplifica_cadastro_animal"),
        ("reproducao", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="animal",
            name="tipo_animal",
            field=models.CharField(
                choices=[
                    ("VACA", "Vaca"),
                    ("NOVILHA", "Novilha"),
                    ("BEZERRO", "Bezerro"),
                    ("BOI", "Boi"),
                ],
                max_length=10,
                null=True,
                verbose_name="tipo de animal",
            ),
        ),
        migrations.RunPython(preencher_tipos_existentes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="animal",
            name="tipo_animal",
            field=models.CharField(
                choices=[
                    ("VACA", "Vaca"),
                    ("NOVILHA", "Novilha"),
                    ("BEZERRO", "Bezerro"),
                    ("BOI", "Boi"),
                ],
                default="BEZERRO",
                max_length=10,
                verbose_name="tipo de animal",
            ),
        ),
    ]
