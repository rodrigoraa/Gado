from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("rebanho", "0002_alter_animal_foto"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="animal",
            name="rebanho_animal_tem_identificacao",
        ),
        migrations.AddField(
            model_name="animal",
            name="cor",
            field=models.CharField(blank=True, max_length=80, verbose_name="cor"),
        ),
        migrations.AlterField(
            model_name="animal",
            name="data_nascimento",
            field=models.DateField(
                blank=True,
                null=True,
                verbose_name="data de nascimento",
            ),
        ),
        migrations.AlterField(
            model_name="animal",
            name="nome",
            field=models.CharField(blank=True, max_length=100, verbose_name="nome"),
        ),
        migrations.AlterField(
            model_name="animal",
            name="sexo",
            field=models.CharField(
                blank=True,
                choices=[("M", "Macho"), ("F", "Fêmea")],
                default="",
                max_length=1,
                verbose_name="sexo",
            ),
        ),
    ]
