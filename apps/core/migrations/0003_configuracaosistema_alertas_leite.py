from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_arquivoanexo"),
    ]

    operations = [
        migrations.AddField(
            model_name="configuracaosistema",
            name="antecedencia_alerta_secagem_dias",
            field=models.PositiveSmallIntegerField(default=7),
        ),
        migrations.AddField(
            model_name="configuracaosistema",
            name="dias_sem_ordenha_alerta",
            field=models.PositiveSmallIntegerField(default=2),
        ),
    ]
