from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("leite", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="ordenha",
            name="periodo",
            field=models.CharField(
                choices=[
                    ("MANHA", "Matutino"),
                    ("TARDE", "Vespertino"),
                    ("NOITE", "Noite"),
                    ("OUTRO", "2 Turnos"),
                ],
                max_length=10,
                verbose_name="turno",
            ),
        ),
    ]
